"""Wake word detection via Whisper transcription + variant matching.

Ported from Jarvis4Gamba v3 — uses the STT engine itself to detect
the wake word by matching against a list of phonetic variants.
This avoids an extra dependency (openWakeWord) at the cost of higher CPU.
"""

from __future__ import annotations

import logging

from jarvis.pipeline.base import WakeWordEngine

log = logging.getLogger("jarvis")


class WhisperWakeEngine(WakeWordEngine):
    """Detect wake word by matching Whisper transcription against variants."""

    def __init__(self, variants: list[str] | None = None) -> None:
        self.variants = variants or [
            "jarvis", "dschawis", "jervis", "jarwis", "schavis", "chavez",
            "jogges", "jarves", "jarfis", "jarvice", "charvis", "tschawis",
            "ja bis", "ja, bis", "job ist", "ciao bis", "ciao, bis", "javis",
            "jarbis", "tschabis", "schawis", "dscharvis", "dschavis", "travis",
            "bis monat",
        ]
        self._callback: callable | None = None

    def matches(self, text: str) -> bool:
        """Check if transcribed text contains the wake word."""
        t = text.lower().strip().rstrip(".!,?")
        if t in self.variants:
            return True
        return any(v in t for v in self.variants)

    def strip_wake_word(self, text: str) -> str:
        """Remove wake word from transcribed text, return the command part."""
        cmd = text.lower()
        for prefix in ["hey " + v for v in self.variants] + self.variants:
            cmd = cmd.replace(prefix, "").strip()
        return cmd

    async def start(self, callback: callable) -> None:
        self._callback = callback
        log.info(f"WhisperWake: listening for {len(self.variants)} variants")

    async def stop(self) -> None:
        self._callback = None

    def check_transcription(self, text: str) -> str | None:
        """Check transcription for wake word. Returns command text or None."""
        if not self.matches(text):
            return None
        cmd = self.strip_wake_word(text)
        if self._callback:
            self._callback()
        return cmd if cmd and len(cmd) > 2 else ""
