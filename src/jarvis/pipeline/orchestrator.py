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
    PERMISSION_PENDING = "permission_pending"


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
        # Voice permission flow
        self._permission_event = threading.Event()
        self._permission_granted = False
        self._prev_state_before_permission: PipelineState | None = None

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
        self._command_lock = threading.Lock()
        # Wire voice permission: agent asks → pipeline speaks & listens
        self.agent.permission_handler = self.ask_permission
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
        self._say_direct("Jarvis online.")

    def _on_transcription(self, text: str) -> None:
        """Route transcription based on current state.

        Called from the STT engine's background thread. Long-running operations
        (_handle_idle, _handle_listening) are dispatched to a separate thread
        so the STT callback returns immediately — this prevents Deepgram's
        WebSocket listener from blocking and timing out.
        """
        text = text.strip()
        if not text or len(text) < 2:
            return

        log.info(f'STT: "{text}"')

        match self.state:
            case PipelineState.IDLE:
                threading.Thread(
                    target=self._handle_idle, args=(text,), daemon=True
                ).start()
            case PipelineState.LISTENING:
                threading.Thread(
                    target=self._handle_listening, args=(text,), daemon=True
                ).start()
            case PipelineState.PROCESSING:
                self._handle_processing(text)
            case PipelineState.SPEAKING:
                self._handle_speaking(text)
            case PipelineState.PERMISSION_PENDING:
                self._handle_permission_pending(text)

    # ── Voice Permission Flow ─────────────────────────────────────────────────

    # Words recognized as approval
    _APPROVE_WORDS = {"ja", "yes", "ok", "okay", "mach", "mach das", "tu es", "go", "klar",
                      "jawohl", "bitte", "gerne", "sicher", "auf jeden fall", "genau"}
    # Words recognized as denial
    _DENY_WORDS = {"nein", "no", "nicht", "stopp", "stop", "abbruch", "abbrechen",
                   "cancel", "halt", "nee", "lass", "lass das", "lieber nicht"}

    def ask_permission(self, tool_name: str, description: str) -> bool:
        """Ask the user for tool permission via voice. Blocks until answered.

        Called from the agent's can_use_tool callback (runs in agent thread).
        Speaks the question, waits for STT to deliver Ja/Nein, returns result.
        """
        self._permission_event.clear()
        self._permission_granted = False
        self._prev_state_before_permission = self._state
        self.state = PipelineState.PERMISSION_PENDING

        # Speak the permission question
        self._say_direct(description)
        log.info(f"🔐 Warte auf Genehmigung: {tool_name}")

        # Wait for user response (timeout after 30s → deny)
        answered = self._permission_event.wait(timeout=30)
        if not answered:
            log.info("🔐 Keine Antwort — Genehmigung verweigert (Timeout)")
            self._say_direct("Keine Antwort, ich überspringe das.")

        # Restore previous state
        self.state = self._prev_state_before_permission or PipelineState.PROCESSING
        self._prev_state_before_permission = None

        result = self._permission_granted if answered else False
        log.info(f"🔐 Genehmigung: {'✓ Erlaubt' if result else '✗ Verweigert'}")
        return result

    def _handle_permission_pending(self, text: str) -> None:
        """Handle transcription during PERMISSION_PENDING — listen for Ja/Nein."""
        import re
        normalized = re.sub(r"[.,!?;:\-]", " ", text.lower()).strip()
        normalized = re.sub(r"\s+", " ", normalized)

        if any(normalized == w or normalized.startswith(w + " ") for w in self._APPROVE_WORDS):
            log.info(f'🔐 Genehmigt: "{text}"')
            self._permission_granted = True
            self._permission_event.set()
            return

        if any(normalized == w or normalized.startswith(w + " ") for w in self._DENY_WORDS):
            log.info(f'🔐 Verweigert: "{text}"')
            self._permission_granted = False
            self._permission_event.set()
            return

        # Unrecognized — ask again
        log.info(f'🔐 Nicht erkannt: "{text}" — frage erneut')
        self._say_direct("Bitte antworte mit Ja oder Nein.")

    # Words that cancel a running agent task or interrupt speech
    _CANCEL_WORDS = {"abbruch", "abbrechen", "stopp", "stop", "ende", "cancel", "halt"}

    def _handle_speaking(self, text: str) -> None:
        """Handle transcription during SPEAKING — listen for interrupt commands."""
        if self._is_cancel(text):
            log.info("⛔ Sprache unterbrochen")
            self.tts.stop_speaking()
            self.state = PipelineState.LISTENING

    def _is_cancel(self, text: str) -> bool:
        """Check if text starts with a cancel word (handles 'Stopp Jarvis' etc.)."""
        import re
        normalized = re.sub(r"[.,!?;:\-]", " ", text.lower()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        return any(normalized == w or normalized.startswith(w + " ") for w in self._CANCEL_WORDS)

    def _handle_processing(self, text: str) -> None:
        """Handle transcription during PROCESSING — listen for cancel/stop commands."""
        t = text.lower().strip().rstrip(".!,?")

        # Stop word ends session AND cancels current task
        stop = self.config.session.stop_word
        if t in [stop, f"{stop}schoen", f"{stop}schön", f"vielen {stop}"]:
            log.info("⛔ Task abgebrochen + Session beendet")
            self.agent.interrupt()
            self._processing_done = True
            self.agent.save_memory()
            self.agent.reset_session()
            self._say_direct("Alles klar.")
            self.state = PipelineState.IDLE
            log.info("SESSION ENDED")
            return

        if self._is_cancel(t):
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
        """Speak text directly, with mic muted to avoid feedback.

        Uses the TTS engine's sync method if available, otherwise falls back
        to macOS `say` command.
        """
        self.stt.mute()
        try:
            if hasattr(self.tts, '_speak_sync'):
                # Piper TTS has a sync method
                self.tts._speak_sync(text)
            else:
                import subprocess
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

        Thread-safe: uses a lock to prevent concurrent agent calls when
        multiple transcriptions arrive in quick succession.
        """
        if not self._command_lock.acquire(blocking=False):
            log.debug("Ignoring overlapping command while agent is busy")
            return
        try:
            self._process_command_inner(text)
        finally:
            self._command_lock.release()

    def _process_command_inner(self, text: str) -> None:
        """Inner command processing (called under lock)."""
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
            # Unmute mic after short delay so user can interrupt or say stop word
            async def _delayed_unmute() -> None:
                await asyncio.sleep(1.0)
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
