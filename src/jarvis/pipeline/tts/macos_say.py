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
            # Run synchronously in a thread-pool executor — avoids asyncio
            # subprocess issues when called from non-main-thread event loops.
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: subprocess.run(cmd, timeout=60)),
                timeout=65,
            )
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            log.warning("TTS timeout after 60s")
        except Exception as e:
            log.error(f"TTS error: {e}")

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._process = None
