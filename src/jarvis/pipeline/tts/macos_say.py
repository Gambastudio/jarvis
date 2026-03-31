"""macOS native TTS via the `say` command.

Ported from Jarvis4Gamba v3. Uses the system Siri voice.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

from jarvis.pipeline.base import TTSEngine

log = logging.getLogger("jarvis")


class MacOSSayEngine(TTSEngine):
    """TTS engine using macOS built-in `say` command."""

    def __init__(self, rate: int = 200, voice: str | None = None) -> None:
        self.rate = rate
        self.voice = voice
        self._process: subprocess.Popen | None = None

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        clean = text.replace('"', "").replace("'", "").replace("`", "")
        cmd = ["say", "-r", str(self.rate)]
        if self.voice:
            cmd.extend(["-v", self.voice])
        cmd.append(clean)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(proc.wait(), timeout=60)
        except asyncio.TimeoutError:
            log.warning("TTS timeout after 60s")
        except Exception as e:
            log.error(f"TTS error: {e}")

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._process = None
