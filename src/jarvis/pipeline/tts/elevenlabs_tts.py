"""ElevenLabs TTS engine — high-quality, expressive cloud TTS.

Uses the ElevenLabs API for natural-sounding speech synthesis.
Supports voice selection and multilingual output.

Requires: pip install elevenlabs
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path

from jarvis.pipeline.base import TTSEngine

log = logging.getLogger("jarvis")

_AUDIO_PATH = Path(tempfile.gettempdir()) / "jarvis_elevenlabs_tts.mp3"

# Curated voice presets — voice_id from ElevenLabs library
ELEVENLABS_VOICES: dict[str, dict[str, str]] = {
    "daniel": {
        "id": "onwK4e9ZLuTAKqWW03F9",
        "label": "Daniel (britisch, Jarvis-Stil)",
    },
    "george": {
        "id": "JBFqnCBsd6RMkjVDRZzb",
        "label": "George (britisch, warm)",
    },
    "adam": {
        "id": "pNInz6obpgDQGcFmaJgB",
        "label": "Adam (tief, klar)",
    },
    "charlie": {
        "id": "IKne3meq5aSn9XLyUdCD",
        "label": "Charlie (natürlich, freundlich)",
    },
    "aria": {
        "id": "9BWtsMINqrJLrRacOk9x",
        "label": "Aria (weiblich, expressiv)",
    },
}


class ElevenLabsTTSEngine(TTSEngine):
    """TTS engine using ElevenLabs for high-quality speech synthesis.

    Synthesizes to MP3 via the ElevenLabs API, then plays via afplay.
    """

    def __init__(
        self,
        api_key: str,
        voice: str = "daniel",
        model: str = "eleven_multilingual_v2",
    ) -> None:
        self._api_key = api_key
        self._voice_id = ELEVENLABS_VOICES.get(voice, {}).get("id", voice)
        self._model = model
        self._process: subprocess.Popen | None = None
        self._client = None

    def _ensure_client(self) -> None:
        """Lazy-init the ElevenLabs client."""
        if self._client is not None:
            return
        try:
            from elevenlabs import ElevenLabs
        except ImportError:
            raise RuntimeError("ElevenLabs not installed. Run: pip install elevenlabs")
        self._client = ElevenLabs(api_key=self._api_key)
        voice_label = next(
            (v["label"] for v in ELEVENLABS_VOICES.values() if v["id"] == self._voice_id),
            self._voice_id,
        )
        log.info(f"ElevenLabs TTS ready (voice: {voice_label}, model: {self._model})")

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, self._speak_sync, text),
            timeout=65,
        )

    def _speak_sync(self, text: str) -> None:
        """Synthesize text via ElevenLabs API and play."""
        self._ensure_client()
        assert self._client is not None

        try:
            from elevenlabs.types import VoiceSettings

            audio_iter = self._client.text_to_speech.convert(
                voice_id=self._voice_id,
                text=text,
                model_id=self._model,
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(
                    stability=0.55,           # Konsistent aber nicht steif
                    similarity_boost=0.78,     # Nah am Voice-Charakter
                    style=0.35,                # Subtile Expressivität
                    use_speaker_boost=True,    # Klarere Stimme
                ),
            )

            # Write MP3 to temp file
            with open(_AUDIO_PATH, "wb") as f:
                for chunk in audio_iter:
                    f.write(chunk)

            # Play via afplay (macOS) — supports MP3 natively
            self._process = subprocess.Popen(["afplay", str(_AUDIO_PATH)])
            self._process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            log.warning("ElevenLabs TTS playback timeout")
            self.stop_speaking()
        except Exception as e:
            log.error(f"ElevenLabs TTS error: {e}")
        finally:
            self._process = None

    def stop_speaking(self) -> None:
        """Kill the running playback process immediately."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    async def stop(self) -> None:
        self.stop_speaking()
