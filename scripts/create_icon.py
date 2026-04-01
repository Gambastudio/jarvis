#!/usr/bin/env python3
"""Generate a minimal Jarvis app icon (AppIcon.icns) using only stdlib + macOS tools.

Creates a solid-color 1024x1024 PNG, resizes to all required icon sizes with sips,
then converts to .icns with iconutil. Run from the repo root.
"""

from __future__ import annotations

import struct
import subprocess
import zlib
from pathlib import Path


def _make_png(path: Path, size: int, r: int, g: int, b: int) -> None:
    """Write a minimal solid-color RGB PNG using stdlib only."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + bytes([r, g, b]) * size for _ in range(size))
    idat = chunk(b"IDAT", zlib.compress(raw, 9))
    iend = chunk(b"IEND", b"")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)


def main() -> None:
    repo = Path(__file__).parent.parent
    iconset = repo / "resources" / "AppIcon.iconset"
    icns = repo / "resources" / "AppIcon.icns"

    iconset.mkdir(parents=True, exist_ok=True)

    # Indigo background (#4F46E5)
    r, g, b = 79, 70, 229

    # Create base 1024x1024
    base_png = iconset / "icon_1024x1024.png"
    _make_png(base_png, 1024, r, g, b)

    # Required iconset sizes
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for px in sizes:
        if px == 1024:
            continue  # base 1024x1024 already written by _make_png
        target = iconset / f"icon_{px}x{px}.png"
        subprocess.run(
            ["sips", "-z", str(px), str(px), str(base_png), "--out", str(target)],
            capture_output=True,
            check=True,
        )
        if px <= 512:
            retina = iconset / f"icon_{px}x{px}@2x.png"
            retina_size = px * 2
            subprocess.run(
                [
                    "sips",
                    "-z",
                    str(retina_size),
                    str(retina_size),
                    str(base_png),
                    "--out",
                    str(retina),
                ],
                capture_output=True,
                check=True,
            )

    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"iconutil failed: {result.stderr.decode().strip()}")
    print(f"✅ Created {icns} ({icns.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
