"""Feedback loop protection — mute mic during TTS output.

Ported from Jarvis4Gamba v3. Prevents the TTS output from being
picked up by the microphone and re-transcribed.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("jarvis")


class FeedbackGuard:
    """Manages microphone muting during speech output to prevent feedback loops."""

    def __init__(self, recorder: Any = None) -> None:
        self._recorder = recorder

    def set_recorder(self, recorder: Any) -> None:
        self._recorder = recorder

    def mute(self) -> None:
        """Mute microphone before TTS playback."""
        if self._recorder:
            try:
                self._recorder.set_microphone(False)
                log.debug("Mic muted")
            except Exception as e:
                log.warning(f"Failed to mute mic: {e}")

    def unmute(self) -> None:
        """Unmute microphone and clear audio queue after TTS playback."""
        if self._recorder:
            try:
                self._recorder.clear_audio_queue()
                self._recorder.set_microphone(True)
                log.debug("Mic unmuted, queue cleared")
            except Exception as e:
                log.warning(f"Failed to unmute mic: {e}")
