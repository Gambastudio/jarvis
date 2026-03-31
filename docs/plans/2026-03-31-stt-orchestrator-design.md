# Design: STT Engine + Voice Pipeline Orchestrator

**Date:** 2026-03-31
**Status:** Approved

## Summary

Refactor the voice pipeline from a monolithic `cli.py` implementation into a pluggable, event-driven architecture with:
1. A callback-based STT interface (replacing the current stream-based one)
2. A RealtimeSTT engine implementation
3. A state-machine-based Voice Pipeline Orchestrator
4. FeedbackGuard logic absorbed into the Orchestrator

## Decisions

- **STT Interface:** Callback-based (`on_text`) instead of `transcribe(audio_buffer)` — matches RealtimeSTT's real behavior
- **Orchestrator scope:** Full pipeline ownership (recorder lifecycle, auto-recovery, session state, wake/stop/exit handling)
- **Orchestrator pattern:** Event-driven state machine with explicit states and transitions
- **FeedbackGuard:** Eliminated as separate class; mute/unmute becomes part of STT interface, orchestrated by the pipeline
- **Threading:** RealtimeSTT's blocking `text()` loop runs in a thread; events bridge back to async via callback

## STT Interface (base.py)

Replace current `STTEngine` with:

```python
class STTEngine(ABC):
    @abstractmethod
    async def start(self, on_text: Callable[[str], None]) -> None:
        """Start listening. Calls on_text(transcription) for each recognized utterance."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and release resources."""

    @abstractmethod
    def mute(self) -> None:
        """Disable microphone input (for feedback loop prevention)."""

    @abstractmethod
    def unmute(self) -> None:
        """Re-enable microphone and clear buffered audio."""
```

Rationale: `set_microphone` and `clear_audio_queue` live on the STT engine because:
- Shortest path for mic control = lowest latency for natural conversations
- Orchestrator works against the interface, never touches the concrete recorder
- No separate FeedbackGuard object needed

## RealtimeSTT Engine (stt/realtimestt.py)

```python
class RealtimeSTTEngine(STTEngine):
    def __init__(self, model, compute_type, language, initial_prompt, vad_config):
        self._recorder = None
        self._config = {...}

    async def start(self, on_text: Callable[[str], None]) -> None:
        self._recorder = AudioToTextRecorder(**self._config)
        # Run blocking recorder.text() loop in a thread
        await asyncio.to_thread(self._listen_loop, on_text)

    def _listen_loop(self, on_text):
        while self._running:
            self._recorder.text(on_text)

    async def stop(self) -> None:
        self._running = False
        if self._recorder:
            self._recorder.stop()

    def mute(self) -> None:
        if self._recorder:
            self._recorder.set_microphone(False)

    def unmute(self) -> None:
        if self._recorder:
            self._recorder.clear_audio_queue()
            self._recorder.set_microphone(True)
```

## Voice Pipeline Orchestrator (orchestrator.py)

### State Machine

```
States:
  IDLE        — waiting for wake word
  LISTENING   — session active, accepting commands
  PROCESSING  — agent working on a query
  SPEAKING    — TTS output (mic muted)

Transitions:
  IDLE       + wake_word_detected   → LISTENING (or PROCESSING if command attached)
  LISTENING  + transcription        → PROCESSING
  LISTENING  + stop_word            → IDLE
  LISTENING  + exit_phrase          → SHUTDOWN
  PROCESSING + agent_response       → SPEAKING
  SPEAKING   + speech_complete      → LISTENING
```

### Class Structure

```python
class PipelineState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"

class VoicePipeline:
    def __init__(self, stt: STTEngine, tts: TTSEngine,
                 wake: WakeWordEngine, agent: JarvisAgent,
                 config: JarvisConfig):
        self.state = PipelineState.IDLE
        self.stt = stt
        self.tts = tts
        self.wake = wake
        self.agent = agent
        self.config = config

    async def run(self) -> None:
        """Main loop with auto-recovery."""
        while True:
            try:
                await self._speak("Jarvis online.")
                await self.stt.start(on_text=self._on_transcription)
            except SystemExit:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.warning(f"Pipeline error: {e} — restarting in 2s...")
                await asyncio.sleep(2)
        await self.agent.close()

    def _on_transcription(self, text: str) -> None:
        """Route transcription based on current state."""
        text = text.strip()
        if not text or len(text) < 2:
            return

        match self.state:
            case PipelineState.IDLE:
                self._handle_idle(text)
            case PipelineState.LISTENING:
                self._handle_listening(text)
            case PipelineState.SPEAKING | PipelineState.PROCESSING:
                pass  # ignore input during these states

    def _handle_idle(self, text: str) -> None:
        cmd = self.wake.check_transcription(text)
        if cmd is None:
            return
        self.state = PipelineState.LISTENING
        if cmd:
            self._process_command(cmd)
        else:
            asyncio.run(self._speak("Ja?"))

    def _handle_listening(self, text: str) -> None:
        t = text.lower().strip().rstrip(".!,")
        # Stop word check
        if t in [self.config.session.stop_word, ...]:
            self.state = PipelineState.IDLE
            asyncio.run(self.agent.reset_session())
            asyncio.run(self._speak("Alles klar."))
            return
        # Exit phrase check
        if text.lower() in [self.config.session.exit_phrase, "programm beenden"]:
            asyncio.run(self._speak("Bis spaeter!"))
            raise SystemExit(0)
        # Process command
        self._process_command(text)

    def _process_command(self, text: str) -> None:
        self.state = PipelineState.PROCESSING
        response = asyncio.run(self.agent.ask(text))
        asyncio.run(self._speak(response))

    async def _speak(self, text: str) -> None:
        """Feedback-safe speech: mute → speak → unmute."""
        prev_state = self.state
        self.state = PipelineState.SPEAKING
        self.stt.mute()
        await self.tts.speak(text)
        self.stt.unmute()
        self.state = PipelineState.LISTENING if prev_state != PipelineState.IDLE else PipelineState.IDLE
```

### Threading Note

Since `RealtimeSTTEngine.start()` runs `recorder.text()` in a thread, the `_on_transcription` callback executes in that thread. The callback uses `asyncio.run()` for async operations (agent.ask, tts.speak). This matches the current cli.py pattern. A future improvement could use `asyncio.run_coroutine_threadsafe()` for cleaner async bridging.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pipeline/base.py` | **Modify** | Replace STTEngine with callback + mute/unmute interface |
| `pipeline/stt/realtimestt.py` | **Create** | RealtimeSTT wrapper implementing STTEngine |
| `pipeline/orchestrator.py` | **Create** | VoicePipeline state machine |
| `pipeline/feedback_guard.py` | **Delete** | Logic absorbed into STTEngine.mute/unmute + Orchestrator._speak |
| `cli.py` | **Simplify** | `_run_pipeline` delegates to `VoicePipeline.run()` |
| `pipeline/stt/__init__.py` | **Update** | Export RealtimeSTTEngine |

## Testing Strategy

- **Unit tests:** State transitions (mock STT/TTS/Agent, verify state changes)
- **Integration test:** Full pipeline with mock audio (verify wake → process → speak flow)
- **Edge cases:** Auto-recovery on crash, stop word during processing, empty transcriptions
