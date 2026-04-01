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
        from RealtimeSTT import AudioToTextRecorder  # noqa: PLC0415

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
        """Blocking loop — runs in a thread via asyncio.to_thread."""
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
