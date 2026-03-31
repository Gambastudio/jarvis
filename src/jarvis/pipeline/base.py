"""Abstract base classes for pluggable pipeline components."""

from abc import ABC, abstractmethod


class STTEngine(ABC):
    """Speech-to-Text engine interface."""

    @abstractmethod
    async def transcribe(self, audio_buffer: bytes) -> str:
        """Transcribe audio buffer to text."""
        ...

    @abstractmethod
    async def start_stream(self) -> None:
        """Start continuous audio stream for real-time transcription."""
        ...

    @abstractmethod
    async def stop_stream(self) -> None:
        """Stop the audio stream."""
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
    async def start(self, callback: 'callable') -> None:
        """Start listening for wake word. Calls callback when detected."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop wake word detection."""
        ...
