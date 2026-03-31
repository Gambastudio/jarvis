"""Piper TTS engine — fast, local, cross-platform neural TTS."""

from __future__ import annotations

import logging

from jarvis.pipeline.base import TTSEngine

log = logging.getLogger("jarvis")


class PiperTTSEngine(TTSEngine):
    """TTS engine using Piper for cross-platform local synthesis.

    Requires: pip install jarvis-voice[tts-piper]
    """

    def __init__(self, voice: str = "de_DE-thorsten-high", speed: float = 1.0) -> None:
        self.voice = voice
        self.speed = speed
        self._piper = None

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        try:
            # Lazy import — only needed when piper engine is selected
            import piper  # noqa: F811
            if self._piper is None:
                self._piper = piper.PiperVoice.load(self.voice)
            # TODO: Implement Piper audio playback
            log.warning("Piper TTS not yet fully implemented")
        except ImportError:
            log.error("Piper TTS not installed. Run: pip install jarvis-voice[tts-piper]")

    async def stop(self) -> None:
        pass
