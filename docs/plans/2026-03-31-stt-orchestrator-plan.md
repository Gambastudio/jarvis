# STT Engine + Voice Pipeline Orchestrator — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the voice pipeline into a pluggable, event-driven state machine with callback-based STT, eliminating the monolithic `cli.py` pipeline loop.

**Architecture:** Event-driven state machine (IDLE → LISTENING → PROCESSING → SPEAKING) in `VoicePipeline`. STT uses callback-based interface matching RealtimeSTT's real behavior. FeedbackGuard logic absorbed into STT `mute()`/`unmute()` called by the orchestrator.

**Tech Stack:** Python 3.12, RealtimeSTT, asyncio, asyncio.to_thread for blocking recorder bridge

**Design doc:** `docs/plans/2026-03-31-stt-orchestrator-design.md`

---

### Task 1: Update STT Interface in base.py

**Files:**
- Modify: `src/jarvis/pipeline/base.py:6-22`
- Test: `tests/test_base_interfaces.py`

**Step 1: Write the failing test**

```python
# tests/test_base_interfaces.py
"""Tests for pipeline base interfaces."""

from jarvis.pipeline.base import STTEngine, TTSEngine, WakeWordEngine


def test_stt_engine_has_callback_interface():
    """STTEngine must define start(on_text), stop(), mute(), unmute()."""
    import inspect
    methods = {name for name, _ in inspect.getmembers(STTEngine, predicate=inspect.isfunction)}
    assert "start" in methods
    assert "stop" in methods
    assert "mute" in methods
    assert "unmute" in methods


def test_stt_engine_start_signature():
    """start() must accept an on_text callback parameter."""
    import inspect
    sig = inspect.signature(STTEngine.start)
    params = list(sig.parameters.keys())
    assert "on_text" in params


def test_stt_engine_no_transcribe():
    """Old transcribe() method should be removed."""
    assert not hasattr(STTEngine, "transcribe")


def test_stt_engine_no_start_stream():
    """Old start_stream() method should be removed."""
    assert not hasattr(STTEngine, "start_stream")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_base_interfaces.py -v`
Expected: FAIL — `mute`/`unmute` not found, `transcribe` still exists

**Step 3: Write minimal implementation**

Replace `STTEngine` in `src/jarvis/pipeline/base.py:6-22` with:

```python
class STTEngine(ABC):
    """Speech-to-Text engine interface.

    Uses callback-based transcription: call start(on_text) and the engine
    invokes on_text(transcription) for each recognized utterance.
    Includes mute/unmute for feedback loop prevention during TTS.
    """

    @abstractmethod
    async def start(self, on_text: 'Callable[[str], None]') -> None:
        """Start listening. Calls on_text(transcription) for each result."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and release resources."""
        ...

    @abstractmethod
    def mute(self) -> None:
        """Disable microphone input (for feedback loop prevention)."""
        ...

    @abstractmethod
    def unmute(self) -> None:
        """Re-enable microphone and clear buffered audio."""
        ...
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_base_interfaces.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/jarvis/pipeline/base.py tests/test_base_interfaces.py
git commit -m "refactor: replace STTEngine with callback-based interface

Replace transcribe()/start_stream()/stop_stream() with start(on_text),
stop(), mute(), unmute(). Matches RealtimeSTT's real callback behavior
and absorbs FeedbackGuard mic control into the STT interface."
```

---

### Task 2: Implement RealtimeSTT Engine

**Files:**
- Create: `src/jarvis/pipeline/stt/realtimestt.py`
- Modify: `src/jarvis/pipeline/stt/__init__.py`
- Test: `tests/test_stt_engine.py`

**Step 1: Write the failing test**

```python
# tests/test_stt_engine.py
"""Tests for RealtimeSTT engine wrapper."""

from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import pytest

from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine
from jarvis.pipeline.base import STTEngine
from jarvis.config import STTConfig, VADConfig


def test_realtimestt_implements_stt_engine():
    """RealtimeSTTEngine must be a subclass of STTEngine."""
    assert issubclass(RealtimeSTTEngine, STTEngine)


def test_realtimestt_init():
    """Should store config without creating a recorder."""
    engine = RealtimeSTTEngine(
        stt_config=STTConfig(),
        vad_config=VADConfig(),
    )
    assert engine._recorder is None
    assert engine._running is False


def test_mute_without_recorder():
    """mute() should be safe to call without a recorder."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine.mute()  # should not raise


def test_unmute_without_recorder():
    """unmute() should be safe to call without a recorder."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine.unmute()  # should not raise


def test_mute_delegates_to_recorder():
    """mute() should call recorder.set_microphone(False)."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine._recorder = MagicMock()
    engine.mute()
    engine._recorder.set_microphone.assert_called_once_with(False)


def test_unmute_delegates_to_recorder():
    """unmute() should clear queue and re-enable mic."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine._recorder = MagicMock()
    engine.unmute()
    engine._recorder.clear_audio_queue.assert_called_once()
    engine._recorder.set_microphone.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_stop_sets_running_false():
    """stop() should set _running to False and stop recorder."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine._running = True
    engine._recorder = MagicMock()
    await engine.stop()
    assert engine._running is False
    engine._recorder.stop.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_stt_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.pipeline.stt.realtimestt'`

**Step 3: Write minimal implementation**

```python
# src/jarvis/pipeline/stt/realtimestt.py
"""RealtimeSTT engine wrapper — callback-based STT using faster-whisper.

Wraps the RealtimeSTT library's AudioToTextRecorder into the STTEngine
interface. The recorder's blocking text() loop runs in a thread via
asyncio.to_thread, bridging back to async via the on_text callback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from jarvis.config import STTConfig, VADConfig
from jarvis.pipeline.base import STTEngine

log = logging.getLogger("jarvis")


class RealtimeSTTEngine(STTEngine):
    """STTEngine implementation using RealtimeSTT + faster-whisper."""

    def __init__(self, stt_config: STTConfig, vad_config: VADConfig) -> None:
        self._stt_config = stt_config
        self._vad_config = vad_config
        self._recorder = None
        self._running = False

    async def start(self, on_text: Callable[[str], None]) -> None:
        """Start the recorder and listen for speech in a background thread."""
        from RealtimeSTT import AudioToTextRecorder

        self._recorder = AudioToTextRecorder(
            model=self._stt_config.model,
            compute_type=self._stt_config.compute_type,
            language=self._stt_config.language,
            initial_prompt=self._stt_config.initial_prompt,
            spinner=False,
            silero_sensitivity=self._vad_config.sensitivity,
            post_speech_silence_duration=self._vad_config.post_speech_silence,
            min_length_of_recording=self._vad_config.min_recording_length,
            min_gap_between_recordings=0.05,
            on_transcription_start=lambda *a: None,
        )
        self._running = True
        log.info("RealtimeSTT recorder started")
        await asyncio.to_thread(self._listen_loop, on_text)

    def _listen_loop(self, on_text: Callable[[str], None]) -> None:
        """Blocking loop — runs in a thread."""
        while self._running:
            try:
                self._recorder.text(on_text)
            except Exception as e:
                if self._running:
                    log.warning(f"Recorder error in listen loop: {e}")
                    break

    async def stop(self) -> None:
        """Stop the recorder and release resources."""
        self._running = False
        if self._recorder:
            try:
                self._recorder.stop()
            except Exception:
                pass
            self._recorder = None
        log.info("RealtimeSTT recorder stopped")

    def mute(self) -> None:
        """Disable microphone input."""
        if self._recorder:
            try:
                self._recorder.set_microphone(False)
                log.debug("Mic muted")
            except Exception as e:
                log.warning(f"Failed to mute mic: {e}")

    def unmute(self) -> None:
        """Re-enable microphone and clear buffered audio."""
        if self._recorder:
            try:
                self._recorder.clear_audio_queue()
                self._recorder.set_microphone(True)
                log.debug("Mic unmuted, queue cleared")
            except Exception as e:
                log.warning(f"Failed to unmute mic: {e}")
```

Update `src/jarvis/pipeline/stt/__init__.py`:

```python
"""Speech-to-Text engines."""

from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine

__all__ = ["RealtimeSTTEngine"]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_stt_engine.py -v`
Expected: PASS (all 7 tests). Note: `test_stop_sets_running_false` needs `pytest-asyncio` — install with `pip install pytest-asyncio --break-system-packages`

**Step 5: Commit**

```bash
git add src/jarvis/pipeline/stt/realtimestt.py src/jarvis/pipeline/stt/__init__.py tests/test_stt_engine.py
git commit -m "feat: add RealtimeSTT engine implementing callback-based STTEngine

Wraps AudioToTextRecorder with asyncio.to_thread for the blocking
listen loop. Includes mute/unmute for feedback loop prevention."
```

---

### Task 3: Implement Voice Pipeline Orchestrator

**Files:**
- Create: `src/jarvis/pipeline/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
"""Tests for the VoicePipeline orchestrator state machine."""

from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import pytest

from jarvis.pipeline.orchestrator import VoicePipeline, PipelineState
from jarvis.config import JarvisConfig


@pytest.fixture
def mock_components():
    """Create mock STT, TTS, Wake, and Agent components."""
    stt = MagicMock()
    stt.mute = MagicMock()
    stt.unmute = MagicMock()
    stt.start = AsyncMock()
    stt.stop = AsyncMock()

    tts = MagicMock()
    tts.speak = AsyncMock()
    tts.stop = AsyncMock()

    wake = MagicMock()
    wake.check_transcription = MagicMock(return_value=None)

    agent = MagicMock()
    agent.ask = AsyncMock(return_value="Test response")
    agent.reset_session = AsyncMock()
    agent.close = AsyncMock()

    config = JarvisConfig()

    return stt, tts, wake, agent, config


def test_initial_state(mock_components):
    """Pipeline should start in IDLE state."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    assert pipeline.state == PipelineState.IDLE


def test_idle_ignores_non_wake_word(mock_components):
    """In IDLE state, non-wake-word text should be ignored."""
    stt, tts, wake, agent, config = mock_components
    wake.check_transcription.return_value = None
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("random text")
    assert pipeline.state == PipelineState.IDLE
    agent.ask.assert_not_called()


def test_idle_wake_word_no_command(mock_components):
    """Wake word without command should transition to LISTENING and say 'Ja?'."""
    stt, tts, wake, agent, config = mock_components
    wake.check_transcription.return_value = ""  # empty = wake word only
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("Jarvis")
    assert pipeline.state == PipelineState.LISTENING
    tts.speak.assert_called()


def test_idle_wake_word_with_command(mock_components):
    """Wake word with command should process immediately."""
    stt, tts, wake, agent, config = mock_components
    wake.check_transcription.return_value = "wie ist das wetter"
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("Jarvis wie ist das wetter")
    agent.ask.assert_called_once_with("wie ist das wetter")
    tts.speak.assert_called()
    assert pipeline.state == PipelineState.LISTENING


def test_listening_stop_word(mock_components):
    """Stop word in LISTENING state should transition to IDLE."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    pipeline._on_transcription("danke")
    assert pipeline.state == PipelineState.IDLE
    agent.reset_session.assert_called_once()


def test_listening_command(mock_components):
    """Regular text in LISTENING state should be processed."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    pipeline._on_transcription("was ist Python")
    agent.ask.assert_called_once_with("was ist Python")
    tts.speak.assert_called()


def test_listening_exit_phrase(mock_components):
    """Exit phrase should raise SystemExit."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    with pytest.raises(SystemExit):
        pipeline._on_transcription("jarvis beenden")


def test_speak_mutes_and_unmutes(mock_components):
    """_speak() should mute before TTS and unmute after."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    asyncio.run(pipeline._speak("hello"))
    stt.mute.assert_called_once()
    tts.speak.assert_called_once_with("hello")
    stt.unmute.assert_called_once()


def test_empty_text_ignored(mock_components):
    """Empty or very short text should be ignored."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("")
    pipeline._on_transcription("a")
    pipeline._on_transcription("  ")
    agent.ask.assert_not_called()
    wake.check_transcription.assert_not_called()


def test_speaking_state_ignores_input(mock_components):
    """Input during SPEAKING state should be ignored."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.SPEAKING
    pipeline._on_transcription("some text")
    agent.ask.assert_not_called()
    wake.check_transcription.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jarvis.pipeline.orchestrator'`

**Step 3: Write minimal implementation**

```python
# src/jarvis/pipeline/orchestrator.py
"""Voice Pipeline Orchestrator — event-driven state machine.

Coordinates STT → Wake Word → Agent → TTS with explicit state management,
auto-recovery, and feedback loop prevention.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from jarvis.config import JarvisConfig
from jarvis.pipeline.base import STTEngine, TTSEngine, WakeWordEngine

log = logging.getLogger("jarvis")


class PipelineState(Enum):
    """Voice pipeline states."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class VoicePipeline:
    """Event-driven voice pipeline orchestrator.

    Owns the full lifecycle: recorder management, session state,
    wake/stop/exit word handling, feedback loop prevention, and auto-recovery.
    """

    def __init__(
        self,
        stt: STTEngine,
        tts: TTSEngine,
        wake: WakeWordEngine,
        agent: 'JarvisAgent',
        config: JarvisConfig,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.wake = wake
        self.agent = agent
        self.config = config
        self.state = PipelineState.IDLE

    async def run(self) -> None:
        """Main pipeline loop with auto-recovery.

        Starts the STT engine and routes transcriptions through the state
        machine. On crash, waits 2s and restarts. Exits on SystemExit
        or KeyboardInterrupt.
        """
        while True:
            try:
                await self._speak("Jarvis online.")
                self.state = PipelineState.IDLE
                log.info(f"Waiting for '{self.config.session.wake_word}'...")
                await self.stt.start(on_text=self._on_transcription)
            except SystemExit:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.warning(f"Pipeline error: {e} — restarting in 2s...")
                try:
                    await self.stt.stop()
                except Exception:
                    pass
                await asyncio.sleep(2)
        await self.agent.close()

    def _on_transcription(self, text: str) -> None:
        """Route transcription based on current state.

        Called from the STT engine's thread. Uses asyncio.run() to bridge
        back to async for agent and TTS calls.
        """
        text = text.strip()
        if not text or len(text) < 2:
            return

        log.info(f'STT: "{text}"')

        match self.state:
            case PipelineState.IDLE:
                self._handle_idle(text)
            case PipelineState.LISTENING:
                self._handle_listening(text)
            case PipelineState.SPEAKING | PipelineState.PROCESSING:
                pass  # ignore input during these states

    def _handle_idle(self, text: str) -> None:
        """Handle transcription in IDLE state — look for wake word."""
        cmd = self.wake.check_transcription(text)
        if cmd is None:
            return

        self.state = PipelineState.LISTENING
        log.info("SESSION STARTED")

        if cmd:
            self._process_command(cmd)
        else:
            asyncio.run(self._speak("Ja?"))

    def _handle_listening(self, text: str) -> None:
        """Handle transcription in LISTENING state — route commands."""
        t = text.lower().strip().rstrip(".!,")

        # Stop word variants
        stop = self.config.session.stop_word
        if t in [stop, f"{stop}schoen", f"{stop}schön", f"vielen {stop}"]:
            self.state = PipelineState.IDLE
            asyncio.run(self.agent.reset_session())
            log.info("SESSION ENDED")
            asyncio.run(self._speak("Alles klar."))
            return

        # Exit phrase
        if text.lower() in [self.config.session.exit_phrase, "programm beenden"]:
            asyncio.run(self._speak("Bis spaeter!"))
            log.info("PROGRAM EXIT")
            raise SystemExit(0)

        # Regular command
        self._process_command(text)

    def _process_command(self, text: str) -> None:
        """Send text to the agent and speak the response."""
        self.state = PipelineState.PROCESSING
        response = asyncio.run(self.agent.ask(text))
        log.info(f"Jarvis: {response}")
        asyncio.run(self._speak(response))

    async def _speak(self, text: str) -> None:
        """Feedback-safe speech: mute → speak → unmute.

        Preserves the previous state so IDLE stays IDLE after startup
        announcement, while LISTENING resumes after command responses.
        """
        prev_state = self.state
        self.state = PipelineState.SPEAKING
        self.stt.mute()
        await self.tts.speak(text)
        self.stt.unmute()
        self.state = prev_state if prev_state == PipelineState.IDLE else PipelineState.LISTENING
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (all 10 tests)

**Step 5: Commit**

```bash
git add src/jarvis/pipeline/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add VoicePipeline orchestrator with state machine

Event-driven state machine with IDLE/LISTENING/PROCESSING/SPEAKING states.
Handles wake word, stop word, exit phrase, auto-recovery, and
feedback-safe speech (mute → speak → unmute)."
```

---

### Task 4: Simplify CLI to use VoicePipeline

**Files:**
- Modify: `src/jarvis/cli.py:45-165`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/test_cli.py
"""Tests for CLI commands."""

from unittest.mock import patch, MagicMock, AsyncMock
from typer.testing import CliRunner

from jarvis.cli import app


runner = CliRunner()


def test_version():
    """version command should print version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Jarvis v" in result.output


def test_query_command():
    """query command should send text to agent and print response."""
    with patch("jarvis.cli.JarvisConfig") as MockConfig, \
         patch("jarvis.cli.JarvisAgent") as MockAgent, \
         patch("jarvis.cli.setup_logging"):
        mock_agent = MagicMock()
        mock_agent.ask = AsyncMock(return_value="Test response")
        mock_agent.close = AsyncMock()
        MockAgent.return_value = mock_agent
        MockConfig.load.return_value = MagicMock()

        result = runner.invoke(app, ["query", "hello"])
        assert result.exit_code == 0


def test_listen_imports_voice_pipeline():
    """listen command should use VoicePipeline, not inline loop."""
    import inspect
    from jarvis.cli import _run_pipeline
    source = inspect.getsource(_run_pipeline)
    assert "VoicePipeline" in source
    # Should NOT contain raw recorder loop
    assert "AudioToTextRecorder" not in source
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_cli.py::test_listen_imports_voice_pipeline -v`
Expected: FAIL — `_run_pipeline` still contains `AudioToTextRecorder`

**Step 3: Write minimal implementation**

Replace `_run_pipeline` in `src/jarvis/cli.py` (lines 45-165) with:

```python
async def _run_pipeline(cfg) -> None:
    """Main voice pipeline — delegates to VoicePipeline orchestrator."""
    from jarvis.agent.core import JarvisAgent
    from jarvis.pipeline.orchestrator import VoicePipeline
    from jarvis.pipeline.wake.whisper_wake import WhisperWakeEngine
    from jarvis.pipeline.tts.macos_say import MacOSSayEngine

    try:
        from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine
    except ImportError:
        from rich.console import Console
        Console().print("[red]RealtimeSTT not installed.[/red] Run: pip install jarvis-voice[stt]")
        raise SystemExit(1)

    stt = RealtimeSTTEngine(stt_config=cfg.stt, vad_config=cfg.vad)
    tts = MacOSSayEngine(rate=cfg.tts.rate, voice=cfg.tts.voice)
    wake = WhisperWakeEngine(cfg.wake_word.variants)
    agent = JarvisAgent(cfg)

    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=cfg)
    await pipeline.run()
```

Also remove the `from jarvis.pipeline.feedback_guard import FeedbackGuard` import that no longer exists in cli.py (line 50).

**Step 4: Run test to verify it passes**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/jarvis/cli.py tests/test_cli.py
git commit -m "refactor: simplify CLI to delegate to VoicePipeline

Replace 120-line inline pipeline loop with 15-line delegation to
VoicePipeline orchestrator. CLI now only wires components and calls run()."
```

---

### Task 5: Delete FeedbackGuard and update pipeline __init__

**Files:**
- Delete: `src/jarvis/pipeline/feedback_guard.py`
- Modify: `src/jarvis/pipeline/__init__.py`
- Test: run all existing tests

**Step 1: Verify no remaining imports of FeedbackGuard**

Run: `cd /Users/zeisler/jarvis && grep -r "feedback_guard\|FeedbackGuard" src/ tests/`
Expected: No matches (cli.py was already updated in Task 4)

**Step 2: Delete the file**

```bash
git rm src/jarvis/pipeline/feedback_guard.py
```

**Step 3: Update pipeline __init__.py**

```python
# src/jarvis/pipeline/__init__.py
"""Voice pipeline components."""

from jarvis.pipeline.base import STTEngine, TTSEngine, WakeWordEngine
from jarvis.pipeline.orchestrator import PipelineState, VoicePipeline

__all__ = [
    "STTEngine",
    "TTSEngine",
    "WakeWordEngine",
    "PipelineState",
    "VoicePipeline",
]
```

**Step 4: Run full test suite**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove FeedbackGuard, update pipeline exports

FeedbackGuard logic is now handled by STTEngine.mute()/unmute()
called from VoicePipeline._speak(). Pipeline __init__ exports
new public API."
```

---

### Task 6: Run full test suite and verify everything works

**Files:**
- No new files

**Step 1: Run all tests**

Run: `cd /Users/zeisler/jarvis && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 2: Verify imports work**

Run: `cd /Users/zeisler/jarvis && python -c "from jarvis.pipeline import VoicePipeline, PipelineState, STTEngine; print('All imports OK')"`
Expected: "All imports OK"

**Step 3: Verify CLI help still works**

Run: `cd /Users/zeisler/jarvis && python -m jarvis --help`
Expected: Shows CLI help with listen, query, version, config commands

**Step 4: Run ruff**

Run: `cd /Users/zeisler/jarvis && pip install ruff --break-system-packages -q && ruff check src/ tests/`
Expected: No errors (or fix any that appear)

**Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address linting issues from ruff"
```
