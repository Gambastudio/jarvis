"""Voice Pipeline Orchestrator — event-driven state machine.

Coordinates STT → Wake Word → Agent → TTS with explicit state management,
auto-recovery, and feedback loop prevention.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING

from jarvis.config import JarvisConfig
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
        machine. On crash, waits 2s and restarts. Exits cleanly on
        SystemExit or KeyboardInterrupt.
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

        Called from the STT engine's background thread. Uses asyncio.run()
        to bridge sync→async for agent and TTS calls.
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
        """Feedback-safe speech output: mute → speak → unmute.

        Preserves state correctly: IDLE stays IDLE after startup
        announcement; all other states return to LISTENING after speech.
        """
        prev_state = self.state
        self.state = PipelineState.SPEAKING
        self.stt.mute()
        await self.tts.speak(text)
        self.stt.unmute()
        self.state = (
            PipelineState.IDLE if prev_state == PipelineState.IDLE else PipelineState.LISTENING
        )
