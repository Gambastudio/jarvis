"""Abstract base classes for pluggable pipeline components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class STTEngine(ABC):
    """Speech-to-Text engine interface.

    Uses callback-based transcription: call start(on_text) and the engine
    invokes on_text(transcription) for each recognized utterance.
    Includes mute/unmute for feedback loop prevention during TTS.
    """

    @abstractmethod
    async def start(self, on_text: Callable[[str], None]) -> None:
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


class TTSEngine(ABC):
    """Text-to-Speech engine interface."""

    @abstractmethod
    async def speak(self, text: str) -> None:
        """Convert text to speech and play it."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop current speech output."""
        ...


class WakeWordEngine(ABC):
    """Wake word detection engine interface."""

    @abstractmethod
    async def start(self, callback: Callable[[], None]) -> None:
        """Start listening for wake word. Calls callback when detected."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop wake word detection."""
        ...
