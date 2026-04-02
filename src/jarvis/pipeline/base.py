"""Abstract base classes for pluggable pipeline components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Union


class STTEngine(ABC):
    """Speech-to-Text engine interface.

    Uses callback-based transcription: call start(on_text) and the engine
    invokes on_text(transcription) for each recognized utterance.
    Includes mute/unmute for feedback loop prevention during TTS.
    """

    @abstractmethod
    async def start(
        self,
        on_text: Callable[[str], None],
        on_ready: Union[Callable[[], Awaitable[None]], Callable[[], None], None] = None,
    ) -> None:
        """Start listening. Calls on_text(transcription) for each result.

        on_ready is called once the engine is fully initialised and listening,
        so callers can announce readiness only after hardware is actually up.
        May be sync or async.
        """
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
