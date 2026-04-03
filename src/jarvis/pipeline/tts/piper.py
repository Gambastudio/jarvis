"""Piper TTS engine — fast, local, cross-platform neural TTS.

Uses PiperVoice Python API to synthesize WAV audio, then plays it via
subprocess (afplay on macOS, aplay on Linux) for thread-safe playback.
Models are auto-downloaded from HuggingFace on first use.

Requires: pip install jarvis-voice[tts-piper]
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from jarvis.pipeline.base import TTSEngine

log = logging.getLogger("jarvis")

_MODELS_DIR = Path.home() / ".jarvis" / "models" / "piper"
_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

# Voice name → HuggingFace path segment
_VOICE_PATHS: dict[str, str] = {
    "de_DE-thorsten-high": "de/de_DE/thorsten/high",
    "de_DE-thorsten-medium": "de/de_DE/thorsten/medium",
    "de_DE-thorsten-low": "de/de_DE/thorsten/low",
    "de_DE-thorsten_emotional-medium": "de/de_DE/thorsten_emotional/medium",
    "en_US-lessac-high": "en/en_US/lessac/high",
    "en_US-lessac-medium": "en/en_US/lessac/medium",
    "en_GB-alan-medium": "en/en_GB/alan/medium",
}

# Temp file for WAV output — reused across calls
_WAV_PATH = Path(tempfile.gettempdir()) / "jarvis_piper_tts.wav"


def _model_path(voice: str) -> Path:
    """Return local path to the .onnx model file."""
    return _MODELS_DIR / f"{voice}.onnx"


def _model_exists(voice: str) -> bool:
    """Check if both .onnx and .onnx.json are downloaded."""
    base = _model_path(voice)
    return base.exists() and base.with_suffix(".onnx.json").exists()


def download_voice(voice: str) -> Path:
    """Download a Piper voice model from HuggingFace if not cached.

    Returns the path to the .onnx file.
    """
    import urllib.request

    onnx_path = _model_path(voice)
    json_path = onnx_path.with_suffix(".onnx.json")

    if onnx_path.exists() and json_path.exists():
        return onnx_path

    hf_segment = _VOICE_PATHS.get(voice)
    if not hf_segment:
        raise ValueError(
            f"Unknown Piper voice: {voice}. "
            f"Available: {', '.join(sorted(_VOICE_PATHS))}"
        )

    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for suffix, target in [(".onnx", onnx_path), (".onnx.json", json_path)]:
        if target.exists():
            continue
        url = f"{_HF_BASE}/{hf_segment}/{voice}{suffix}"
        log.info(f"Downloading {voice}{suffix}...")
        urllib.request.urlretrieve(url, target)
        log.info(f"Saved to {target} ({target.stat().st_size // 1024 // 1024}MB)")

    return onnx_path


class PiperTTSEngine(TTSEngine):
    """TTS engine using Piper for local neural speech synthesis.

    Synthesizes to a WAV file, then plays via afplay/aplay subprocess.
    This avoids PyAudio thread-safety issues on macOS.
    Models are auto-downloaded on first use (~60-114MB depending on quality).
    """

    def __init__(
        self,
        voice: str = "de_DE-thorsten-high",
        rate: int = 200,
    ) -> None:
        self.voice_name = voice
        # Convert WPM rate to Piper length_scale
        # 1.0 = normal speed (~170 WPM), lower = faster, higher = slower
        # 170 WPM → 1.0, 200 WPM → 0.85, 250 WPM → 0.68, 140 WPM → 1.21
        self.length_scale = max(0.5, min(2.0, 170.0 / rate))
        self._piper_voice = None
        self._syn_config = None
        self._process: subprocess.Popen | None = None

    def _ensure_voice(self) -> None:
        """Lazy-load the Piper voice model (downloads if needed)."""
        if self._piper_voice is not None:
            return
        try:
            from piper.voice import PiperVoice
        except ImportError:
            raise RuntimeError(
                "Piper TTS not installed. Run: pip install piper-tts"
            )
        model_path = download_voice(self.voice_name)
        self._piper_voice = PiperVoice.load(str(model_path))

        from piper.config import SynthesisConfig
        self._syn_config = SynthesisConfig(length_scale=self.length_scale)

        log.info(
            f"Piper voice loaded: {self.voice_name} "
            f"({self._piper_voice.config.sample_rate}Hz, "
            f"length_scale={self.length_scale:.2f})"
        )

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, self._speak_sync, text),
            timeout=65,
        )

    def _speak_sync(self, text: str) -> None:
        """Synthesize text to WAV, then play via subprocess."""
        self._ensure_voice()
        assert self._piper_voice is not None

        sample_rate = self._piper_voice.config.sample_rate

        # Synthesize to WAV file
        with wave.open(str(_WAV_PATH), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            for chunk in self._piper_voice.synthesize(text, syn_config=self._syn_config):
                wav_file.writeframes(chunk.audio_int16_bytes)

        # Play via subprocess (thread-safe on macOS)
        if sys.platform == "darwin":
            cmd = ["afplay", str(_WAV_PATH)]
        else:
            cmd = ["aplay", str(_WAV_PATH)]

        try:
            self._process = subprocess.Popen(cmd)
            self._process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            log.warning("Piper TTS playback timeout")
            self.stop_speaking()
        except Exception as e:
            log.error(f"Piper TTS playback error: {e}")
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
