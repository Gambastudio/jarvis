"""Deepgram real-time streaming STT engine.

Uses Deepgram's Nova-3 model via WebSocket for low-latency, high-accuracy
speech-to-text. Requires a DEEPGRAM_API_KEY environment variable.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from typing import Union

from jarvis.config import STTConfig, VADConfig
from jarvis.pipeline.base import STTEngine

log = logging.getLogger("jarvis")

# Audio capture settings
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 4096


class DeepgramSTTEngine(STTEngine):
    """STTEngine implementation using Deepgram real-time streaming API."""

    def __init__(self, stt_config: STTConfig, vad_config: VADConfig) -> None:
        self._stt_config = stt_config
        self._vad_config = vad_config
        self._running = False
        self._muted = False
        self._connection = None
        self._microphone = None
        self._audio_thread: threading.Thread | None = None

    async def start(
        self,
        on_text: Callable[[str], None],
        on_ready: Union[Callable[[], Awaitable[None]], Callable[[], None], None] = None,
    ) -> None:
        """Start Deepgram streaming STT with microphone input."""
        from deepgram import (
            DeepgramClient,
            LiveOptions,
            LiveTranscriptionEvents,
        )

        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            raise ValueError(
                "DEEPGRAM_API_KEY environment variable not set. "
                "Get a key at https://console.deepgram.com"
            )

        client = DeepgramClient(api_key)
        self._connection = client.listen.live.v("1")

        # Event handlers
        def on_open(self_dg, open_event, **kwargs):
            log.info("Deepgram connection opened")

        def on_message(self_dg, result, **kwargs):
            try:
                transcript = result.channel.alternatives[0].transcript
                if transcript and result.is_final:
                    on_text(transcript)
            except (IndexError, AttributeError) as e:
                log.debug(f"Deepgram message parse: {e}")

        def on_error(self_dg, error, **kwargs):
            log.error(f"Deepgram error: {error}")

        def on_close(self_dg, close_event, **kwargs):
            log.info("Deepgram connection closed")

        self._connection.on(LiveTranscriptionEvents.Open, on_open)
        self._connection.on(LiveTranscriptionEvents.Transcript, on_message)
        self._connection.on(LiveTranscriptionEvents.Error, on_error)
        self._connection.on(LiveTranscriptionEvents.Close, on_close)

        # Deepgram model selection
        model = self._stt_config.model
        if model in ("tiny", "base", "small", "medium", "large"):
            # User has a whisper model name — use Deepgram's best
            model = "nova-3"

        options = LiveOptions(
            model=model,
            language=self._stt_config.language,
            smart_format=True,
            encoding="linear16",
            sample_rate=SAMPLE_RATE,
            channels=CHANNELS,
            interim_results=False,
            utterance_end_ms=str(int(self._vad_config.post_speech_silence * 1000)),
            vad_events=True,
        )

        started = self._connection.start(options)
        if not started:
            raise RuntimeError("Failed to start Deepgram connection")

        self._running = True
        log.info(f"Deepgram STT started (model: {model}, lang: {self._stt_config.language})")

        if on_ready:
            result = on_ready()
            if inspect.isawaitable(result):
                await result

        # Start microphone capture in background thread
        await asyncio.to_thread(self._capture_audio)

    def _capture_audio(self) -> None:
        """Capture microphone audio and send to Deepgram. Runs in a thread."""
        import pyaudio

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            log.debug("Microphone stream opened for Deepgram")

            while self._running:
                try:
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    if not self._muted and self._connection:
                        self._connection.send(data)
                except OSError as e:
                    if self._running:
                        log.warning(f"Audio capture error: {e}")
                        break
                except Exception as e:
                    if self._running:
                        log.warning(f"Deepgram send error: {e}")
                        break
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            pa.terminate()
            log.debug("Microphone stream closed")

    async def stop(self) -> None:
        """Stop the Deepgram connection and release resources."""
        self._running = False
        if self._connection:
            try:
                self._connection.finish()
            except Exception as e:
                log.warning(f"Deepgram close error: {e}")
            self._connection = None
        log.info("Deepgram STT stopped")

    def mute(self) -> None:
        """Disable microphone input (stops sending audio to Deepgram)."""
        self._muted = True
        log.debug("Mic muted (Deepgram)")

    def unmute(self) -> None:
        """Re-enable microphone input."""
        self._muted = False
        log.debug("Mic unmuted (Deepgram)")
