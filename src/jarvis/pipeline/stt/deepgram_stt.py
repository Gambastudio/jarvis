"""Deepgram real-time streaming STT engine.

Uses Deepgram's Nova-3 model via WebSocket for low-latency, high-accuracy
speech-to-text. Requires a DEEPGRAM_API_KEY environment variable.

Tested with deepgram-sdk 6.x.
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

# Pre-built silence frame (zeros = silence for int16 PCM)
_SILENCE = b"\x00" * (CHUNK_SIZE * 2)  # 2 bytes per sample (int16)


class DeepgramSTTEngine(STTEngine):
    """STTEngine implementation using Deepgram real-time streaming API (SDK v6)."""

    def __init__(self, stt_config: STTConfig, vad_config: VADConfig) -> None:
        self._stt_config = stt_config
        self._vad_config = vad_config
        self._running = False
        self._muted = False
        self._connection = None
        self._audio_thread: threading.Thread | None = None

    async def start(
        self,
        on_text: Callable[[str], None],
        on_ready: Union[Callable[[], Awaitable[None]], Callable[[], None], None] = None,
    ) -> None:
        """Start Deepgram streaming STT with microphone input."""
        from deepgram import DeepgramClient
        from deepgram.core.events import EventType
        from deepgram.listen.v1.types.listen_v1results import ListenV1Results

        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            raise ValueError(
                "DEEPGRAM_API_KEY environment variable not set. "
                "Get a key at https://console.deepgram.com"
            )

        # Deepgram model selection — map whisper names to nova-3
        model = self._stt_config.model
        if model in ("tiny", "base", "small", "medium", "large"):
            model = "nova-3"

        self._client = DeepgramClient(api_key=api_key)
        self._on_text = on_text

        # v6 SDK: connect returns a context manager yielding V1SocketClient
        endpointing_ms = int(self._vad_config.post_speech_silence * 1000)
        # Note: v6 SDK has a bug serializing booleans (smart_format, punctuate)
        # into WebSocket query params — pass them as strings via extra params
        self._conn_ctx = self._client.listen.v1.connect(
            model=model,
            language=self._stt_config.language,
            encoding="linear16",
            sample_rate=SAMPLE_RATE,
            endpointing=endpointing_ms,
            request_options={
                "additional_query_parameters": {
                    "punctuate": "true",
                    "smart_format": "true",
                },
            },
        )

        self._running = True

        log.info(f"Deepgram STT started (model: {model}, lang: {self._stt_config.language})")

        if on_ready:
            result = on_ready()
            if inspect.isawaitable(result):
                await result

        # Run the blocking WebSocket + mic capture in a background thread
        await asyncio.to_thread(self._run_connection)

    def _run_connection(self) -> None:
        """Run Deepgram WebSocket connection + mic capture. Blocks until stopped."""
        from deepgram.core.events import EventType
        from deepgram.listen.v1.types.listen_v1results import ListenV1Results

        with self._conn_ctx as socket_client:
            self._connection = socket_client

            # Register event handler for transcription results
            def on_message(message):
                if isinstance(message, ListenV1Results):
                    try:
                        transcript = message.channel.alternatives[0].transcript
                        if transcript and message.is_final:
                            self._on_text(transcript)
                    except (IndexError, AttributeError) as e:
                        log.debug(f"Deepgram message parse: {e}")

            socket_client.on(EventType.MESSAGE, on_message)
            socket_client.on(EventType.ERROR, lambda e: log.error(f"Deepgram error: {e}"))

            # Start listening thread (processes incoming WebSocket messages)
            listen_thread = threading.Thread(
                target=socket_client.start_listening, daemon=True
            )
            listen_thread.start()

            # Capture microphone audio
            self._capture_audio(socket_client)

            # Clean shutdown
            try:
                socket_client.send_close_stream()
            except Exception:
                pass

        self._connection = None

    def _capture_audio(self, socket_client) -> None:
        """Capture microphone audio and send to Deepgram.

        When muted, sends silence frames instead of real audio to keep the
        WebSocket connection alive (Deepgram closes idle connections after ~60s).
        """
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

            log.info("⚙️ Deepgram mic capture started")

            while self._running:
                try:
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    if self._connection:
                        if not self._muted:
                            socket_client.send_media(data)
                        else:
                            # Send silence to keep WebSocket alive
                            socket_client.send_media(_SILENCE)
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
                self._connection.send_close_stream()
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
