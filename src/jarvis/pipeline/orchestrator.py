"""Voice Pipeline Orchestrator — event-driven state machine.

Coordinates STT → Wake Word → Agent → TTS with explicit state management,
auto-recovery, and feedback loop prevention.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

from jarvis.config import JarvisConfig
from jarvis.utils.text_cleaner import clean_for_speech
from jarvis.pipeline.base import STTEngine, TTSEngine, WakeWordEngine

if TYPE_CHECKING:
    from jarvis.agent.core import JarvisAgent

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

    State machine transitions:
        IDLE       + wake_word   → LISTENING (or PROCESSING if command attached)
        LISTENING  + text        → PROCESSING
        LISTENING  + stop_word   → IDLE
        LISTENING  + exit_phrase → SHUTDOWN
        PROCESSING + response    → SPEAKING
        SPEAKING   + done        → LISTENING
    """

    def __init__(
        self,
        stt: STTEngine,
        tts: TTSEngine,
        wake: WakeWordEngine,
        agent: JarvisAgent,
        config: JarvisConfig,
        state_callback: Callable[[PipelineState], None] | None = None,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self.stt = stt
        self.tts = tts
        self.wake = wake
        self.agent = agent
        self.config = config
        self.state_callback = state_callback
        self.on_exit = on_exit
        self._state = PipelineState.IDLE
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def state(self) -> PipelineState:
        return self._state

    @state.setter
    def state(self, value: PipelineState) -> None:
        self._state = value
        if self.state_callback:
            try:
                self.state_callback(value)
            except Exception as e:
                log.warning(f"state_callback error: {e}")

    async def run(self) -> None:
        """Main pipeline loop with auto-recovery.

        Starts the STT engine and routes transcriptions through the state
        machine. On crash, waits 2s and restarts. Exits cleanly on
        SystemExit or KeyboardInterrupt.
        """
        self._loop = asyncio.get_running_loop()
        while True:
            try:
                self.state = PipelineState.IDLE
                log.info(f"Waiting for '{self.config.session.wake_word}'...")
                await self.stt.start(
                    on_text=self._on_transcription,
                    on_ready=self._on_stt_ready,
                )
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
        self._loop = None
        self.agent.close()

    def _run_async(self, coro: object) -> None:
        """Bridge sync callback (STT background thread) → running event loop.

        Uses run_coroutine_threadsafe so we never nest asyncio.run() inside
        an already-running loop.
        """
        assert self._loop is not None, "Pipeline event loop not set"
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]
        future.result()  # block the callback thread until the coroutine completes

    async def _on_stt_ready(self) -> None:
        """Called once the STT recorder is fully initialised and listening."""
        log.info("All systems ready")
        await self._speak("Jarvis online.")

    def _on_transcription(self, text: str) -> None:
        """Route transcription based on current state.

        Called from the STT engine's background thread. Uses
        run_coroutine_threadsafe to bridge sync→async for agent and TTS calls.
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
            case PipelineState.PROCESSING:
                self._handle_processing(text)
            case PipelineState.SPEAKING:
                self._handle_speaking(text)

    # Words that cancel a running agent task or interrupt speech
    _CANCEL_WORDS = {"abbruch", "abbrechen", "stopp", "stop", "ende", "cancel", "halt"}

    def _handle_speaking(self, text: str) -> None:
        """Handle transcription during SPEAKING — listen for interrupt commands."""
        t = text.lower().strip().rstrip(".!,?")
        if t in self._CANCEL_WORDS:
            log.info("⛔ Sprache unterbrochen")
            self.tts.stop_speaking()
            self.state = PipelineState.LISTENING

    def _handle_processing(self, text: str) -> None:
        """Handle transcription during PROCESSING — listen for cancel commands."""
        t = text.lower().strip().rstrip(".!,?")
        if t in self._CANCEL_WORDS:
            log.info("⛔ Task abgebrochen durch Sprachbefehl")
            self.agent.interrupt()
            self._processing_done = True
            self._say_direct("Abgebrochen.")
            self.state = PipelineState.LISTENING

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
            self._run_async(self._speak("Ja?"))

    def _handle_listening(self, text: str) -> None:
        """Handle transcription in LISTENING state — route commands."""
        t = text.lower().strip().rstrip(".!,")

        # Stop word variants
        stop = self.config.session.stop_word
        if t in [stop, f"{stop}schoen", f"{stop}schön", f"vielen {stop}"]:
            self.state = PipelineState.IDLE
            self.agent.save_memory()   # fire-and-forget background save
            self.agent.reset_session()
            log.info("SESSION ENDED")
            self._run_async(self._speak("Alles klar."))
            return

        # Exit phrase
        if text.lower() in [self.config.session.exit_phrase, "programm beenden"]:
            self._run_async(self._speak("Bis spaeter!"))
            log.info("PROGRAM EXIT")
            if self.on_exit:
                self.on_exit()
            raise SystemExit(0)

        # Regular command
        self._process_command(text)

    def _say_direct(self, text: str) -> None:
        """Speak text directly via subprocess, with mic muted to avoid feedback."""
        import subprocess
        self.stt.mute()
        try:
            subprocess.run(
                ["say", "-r", str(self.config.tts.rate), text],
                timeout=10,
            )
        except Exception as e:
            log.warning(f"Direct say failed: {e}")
        finally:
            self.stt.unmute()

    def _process_command(self, text: str) -> None:
        """Send text to the agent and speak the response.

        Gives periodic spoken feedback while the agent is processing,
        so the user knows Jarvis is still working.
        """
        self.state = PipelineState.PROCESSING
        self._processing_done = False

        def _wait_unless_done(seconds: int) -> bool:
            """Sleep in 0.5s increments, return True if processing finished."""
            for _ in range(int(seconds * 2)):
                if self._processing_done:
                    return True
                time.sleep(0.5)
            return self._processing_done

        def _periodic_feedback() -> None:
            """First announcement after 4s, then repeat every 20s."""
            if _wait_unless_done(4):
                return
            log.info("⏳ Jarvis denkt nach...")
            self._say_direct("Moment, ich arbeite daran.")
            while not self._processing_done:
                if _wait_unless_done(20):
                    return
                elapsed = int(time.time() - start_time)
                log.info(f"⏳ Jarvis arbeitet noch... ({elapsed}s)")
                self._say_direct("Ich bin noch dran, bitte Geduld.")

        def _on_tool_progress(label: str) -> None:
            """Log tool use so user sees activity in the log window."""
            log.info(f"🔧 {label}...")

        start_time = time.time()

        # Start periodic feedback thread
        feedback_thread = threading.Thread(target=_periodic_feedback, daemon=True)
        feedback_thread.start()

        # Wire up progress callback
        self.agent._progress_callback = _on_tool_progress
        response = self.agent.ask(text)
        self.agent._progress_callback = None
        self._processing_done = True

        elapsed = int(time.time() - start_time)
        log.info(f"Jarvis ({elapsed}s): {response}")
        self._run_async(self._speak(clean_for_speech(response)))

    async def _speak(self, text: str) -> None:
        """Feedback-safe speech output: mute → speak → unmute.

        For longer responses (>80 chars), the mic is re-enabled after 1.5s
        so the user can say 'Stopp' to interrupt the speech.
        Preserves state correctly: IDLE stays IDLE after startup
        announcement; all other states return to LISTENING after speech.
        """
        prev_state = self.state
        self.state = PipelineState.SPEAKING
        should_mute = self.config.tts.mute_mic_during_speech

        if should_mute:
            self.stt.mute()
            if len(text) > 80:
                # Long text: unmute mic after 1.5s so user can interrupt
                async def _delayed_unmute() -> None:
                    await asyncio.sleep(1.5)
                    if self.state == PipelineState.SPEAKING:
                        self.stt.unmute()

                asyncio.ensure_future(_delayed_unmute())

        await self.tts.speak(text)
        if should_mute:
            self.stt.unmute()
        # Only transition if we weren't interrupted (still SPEAKING)
        if self.state == PipelineState.SPEAKING:
            self.state = (
                PipelineState.IDLE if prev_state == PipelineState.IDLE else PipelineState.LISTENING
            )
