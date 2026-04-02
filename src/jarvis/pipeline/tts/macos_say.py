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
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, self._run_say, cmd),
                timeout=65,
            )
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            log.warning("TTS timeout after 60s")
            self.stop_speaking()
        except Exception as e:
            log.error(f"TTS error: {e}")

    def _run_say(self, cmd: list[str]) -> None:
        """Run say command with a trackable Popen process."""
        self._process = subprocess.Popen(cmd)
        self._process.wait(timeout=60)
        self._process = None

    def stop_speaking(self) -> None:
        """Kill the running say process immediately."""
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
