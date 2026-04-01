# Jarvis.app Bundle — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a distributable `Jarvis.app` with embedded Python venv, ad-hoc codesign, and on-demand Whisper model download.

**Architecture:** Shell launcher at `MacOS/jarvis` activates an embedded venv at `Resources/venv/` and runs `python3.12 -m jarvis.ui.macos_app`. A build script creates the full `.app` structure from scratch. The app detects if the selected Whisper model is cached and shows a download status before the pipeline starts.

**Tech Stack:** Python 3.12, bash, macOS `codesign`, `sips`, `iconutil`, `huggingface_hub`

---

### Task 1: Add `_is_model_cached()` + download status to `macos_app.py`

Before starting the pipeline, check if the selected Whisper model weights are already in the
huggingface cache. If not, show "📥 Lade Modell herunter..." so the user knows what's happening.

**Files:**
- Modify: `src/jarvis/ui/macos_app.py`
- Create: `tests/test_model_cache.py`

**Step 1: Write failing test**

Create `tests/test_model_cache.py`:
```python
"""Tests for _is_model_cached helper."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


def test_is_model_cached_returns_false_when_none(monkeypatch):
    """Returns False when huggingface_hub reports model not cached."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.return_value = None
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    # Import after patching so the lazy import inside the function sees the mock
    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("tiny") is False


def test_is_model_cached_returns_true_when_path(monkeypatch):
    """Returns True when huggingface_hub returns a path to cached weights."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.return_value = "/some/path/model.bin"
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("base") is True


def test_is_model_cached_returns_false_on_exception(monkeypatch):
    """Returns False (safe default) if huggingface_hub check raises."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.side_effect = Exception("network error")
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("small") is False


def test_is_model_cached_checks_correct_repo(monkeypatch):
    """Checks the Systran/faster-whisper-{model} HuggingFace repo."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.return_value = None
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    _is_model_cached("tiny")

    mock_hf.try_to_load_from_cache.assert_called_once_with(
        "Systran/faster-whisper-tiny", "model.bin"
    )
```

**Step 2: Run to verify FAIL**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/test_model_cache.py -v
```
Expected: ImportError (`_is_model_cached` does not exist yet)

**Step 3: Add `_is_model_cached()` to `macos_app.py`**

After the `LANGUAGES` dict (around line 42), add this module-level function:

```python
# Model size hints for download status message
_MODEL_SIZES = {"tiny": "75MB", "base": "150MB", "small": "500MB"}


def _is_model_cached(model: str) -> bool:
    """Check if the faster-whisper model weights are in the huggingface cache."""
    try:
        from huggingface_hub import try_to_load_from_cache

        result = try_to_load_from_cache(f"Systran/faster-whisper-{model}", "model.bin")
        return result is not None
    except Exception:
        return False  # safe default: assume not cached
```

**Step 4: Update `_start_pipeline()` to show download status**

In `_start_pipeline`, replace the current end of the method (after the `has_api_key` guard):

Find this block (around line 226-228):
```python
        self._pipeline_thread = threading.Thread(target=run, daemon=True, name="VoicePipeline")
        self._pipeline_thread.start()
        self._update_status(f"Wartet auf '{self.cfg.session.wake_word}'...")
```

Replace with:
```python
        self._pipeline_thread = threading.Thread(target=run, daemon=True, name="VoicePipeline")
        self._pipeline_thread.start()
        if not _is_model_cached(self.cfg.stt.model):
            size = _MODEL_SIZES.get(self.cfg.stt.model, "?")
            self._update_status(
                f"📥 Lade {self.cfg.stt.model}-Modell herunter (~{size})..."
            )
        else:
            self._update_status(f"Wartet auf '{self.cfg.session.wake_word}'...")
```

**Step 5: Run tests to verify PASS**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/test_model_cache.py -v
```
Expected: 4 PASS

**Step 6: Run full suite**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/ -q
```
Expected: 38 passed

**Step 7: Run ruff**
```bash
cd /Users/zeisler/jarvis && ruff check src/ tests/ && ruff format --check src/ tests/
```
Fix any issues.

**Step 8: Commit**
```bash
cd /Users/zeisler/jarvis && git add src/jarvis/ui/macos_app.py tests/test_model_cache.py
git commit -m "feat: add Whisper model cache check with download status"
```

---

### Task 2: App icon (placeholder)

Create a simple `.icns` using only macOS built-in tools (`sips`, `iconutil`) and Python stdlib.
The icon is a solid indigo circle — minimal but recognizable.

**Files:**
- Create: `scripts/create_icon.py`
- Create: `resources/AppIcon.icns` (generated artifact)

**Step 1: Create `scripts/create_icon.py`**

```python
#!/usr/bin/env python3
"""Generate a minimal Jarvis app icon (AppIcon.icns) using only stdlib + macOS tools.

Creates a solid-color 1024x1024 PNG, resizes to all required icon sizes with sips,
then converts to .icns with iconutil. Run from the repo root.
"""
from __future__ import annotations

import os
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

    # Indigo background (#4F46E5) — same as Jarvis status color palette
    R, G, B = 79, 70, 229

    # Required sizes: icon_SIZExSIZE.png and icon_SIZExSIZE@2x.png
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for px in sizes:
        base = iconset / f"icon_{px}x{px}.png"
        _make_png(base, px, R, G, B)
        if px <= 512:
            retina = iconset / f"icon_{px}x{px}@2x.png"
            # @2x is double resolution — resize base using sips
            retina.write_bytes(base.read_bytes())
            subprocess.run(
                ["sips", "-z", str(px * 2), str(px * 2), str(retina)],
                capture_output=True,
                check=True,
            )

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
        check=True,
    )
    print(f"✅ Created {icns} ({icns.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
```

**Step 2: Run to generate icon**
```bash
cd /Users/zeisler/jarvis && python3.12 scripts/create_icon.py
```
Expected: `✅ Created resources/AppIcon.icns (... KB)`

**Step 3: Verify icon exists**
```bash
ls -lh /Users/zeisler/jarvis/resources/AppIcon.icns
```
Expected: file present, non-zero size.

**Step 4: Commit**
```bash
cd /Users/zeisler/jarvis && git add scripts/create_icon.py resources/AppIcon.icns resources/AppIcon.iconset/
git commit -m "feat: add app icon generation script and placeholder AppIcon.icns"
```

---

### Task 3: Build script `scripts/build_app.sh`

The main build script that produces `build/Jarvis.app` and `build/Jarvis-vX.Y.Z.zip`.

**Files:**
- Create: `scripts/build_app.sh`

No unit tests for a shell script. Verification is done by running it.

**Step 1: Create `scripts/build_app.sh`**

```bash
#!/usr/bin/env bash
# Build Jarvis.app — distributable macOS Menu Bar App
# Usage: bash scripts/build_app.sh
# Requires: macOS, python3.12, codesign
set -euo pipefail

REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$REPO_ROOT"

APP_NAME="Jarvis"
BUNDLE_ID="com.gambastudio.jarvis"
VERSION="$(python3.12 -c "from importlib.metadata import version; print(version('jarvis-voice'))" 2>/dev/null || echo "0.1.0")"
BUILD_DIR="$REPO_ROOT/build"
APP_DIR="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
RESOURCES="$CONTENTS/Resources"
MACOS_DIR="$CONTENTS/MacOS"
VENV="$RESOURCES/venv"

echo "▶ Building $APP_NAME.app v$VERSION"

# ── Clean ──────────────────────────────────────────────────────────────────────
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES"

# ── Embedded venv ──────────────────────────────────────────────────────────────
echo "▶ Creating embedded venv..."
python3.12 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -e "$REPO_ROOT[macos,stt]" -q
echo "   Done ($(du -sh "$VENV" | cut -f1))"

# ── Info.plist ─────────────────────────────────────────────────────────────────
cat > "$CONTENTS/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleExecutable</key>
    <string>jarvis</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Jarvis uses the microphone to listen for your voice commands.</string>
</dict>
</plist>
PLIST

# ── Shell launcher ─────────────────────────────────────────────────────────────
cat > "$MACOS_DIR/jarvis" << 'LAUNCHER'
#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV="$DIR/../Resources/venv"
exec "$VENV/bin/python3.12" -m jarvis.ui.macos_app "$@"
LAUNCHER
chmod +x "$MACOS_DIR/jarvis"

# ── Icon ───────────────────────────────────────────────────────────────────────
if [ -f "$REPO_ROOT/resources/AppIcon.icns" ]; then
    cp "$REPO_ROOT/resources/AppIcon.icns" "$RESOURCES/AppIcon.icns"
    echo "▶ Icon copied"
else
    echo "⚠  No icon found at resources/AppIcon.icns — skipping"
fi

# ── Code sign (ad-hoc) ─────────────────────────────────────────────────────────
echo "▶ Signing (ad-hoc)..."
codesign --deep --force --sign - "$APP_DIR"
codesign --verify --verbose "$APP_DIR" 2>&1 | head -3

# ── Zip for distribution ───────────────────────────────────────────────────────
ARCHIVE="$BUILD_DIR/$APP_NAME-v$VERSION.zip"
echo "▶ Creating archive..."
cd "$BUILD_DIR"
zip -r "$APP_NAME-v$VERSION.zip" "$APP_NAME.app" -q
cd "$REPO_ROOT"

echo ""
echo "✅ Build complete!"
echo "   App:     $APP_DIR"
echo "   Size:    $(du -sh "$APP_DIR" | cut -f1)"
echo "   Archive: $ARCHIVE"
echo "   Size:    $(du -sh "$ARCHIVE" | cut -f1)"
echo ""
echo "To install: cp -r $APP_DIR /Applications/"
```

**Step 2: Make executable**
```bash
chmod +x /Users/zeisler/jarvis/scripts/build_app.sh
```

**Step 3: Commit**
```bash
cd /Users/zeisler/jarvis && git add scripts/build_app.sh
git commit -m "feat: add build_app.sh script for distributable Jarvis.app"
```

---

### Task 4: Run the build + verify + push

**Step 1: Run the build**
```bash
cd /Users/zeisler/jarvis && bash scripts/build_app.sh
```
Expected output:
```
▶ Building Jarvis.app v0.1.0
▶ Creating embedded venv...
   Done (~700MB)
▶ Icon copied
▶ Signing (ad-hoc)...
build/Jarvis.app: valid on disk
✅ Build complete!
```
This will take several minutes (pip installs torch).

**Step 2: Verify app structure**
```bash
echo "--- Structure ---"
ls build/Jarvis.app/Contents/
ls build/Jarvis.app/Contents/MacOS/
ls build/Jarvis.app/Contents/Resources/ | head -5

echo "--- Launcher executable ---"
test -x build/Jarvis.app/Contents/MacOS/jarvis && echo "jarvis is executable ✅"

echo "--- Python in venv ---"
test -f build/Jarvis.app/Contents/Resources/venv/bin/python3.12 && echo "python3.12 found ✅"

echo "--- jarvis importable ---"
build/Jarvis.app/Contents/Resources/venv/bin/python3.12 -c "import jarvis; print('jarvis importable ✅')"

echo "--- Codesign valid ---"
codesign -v build/Jarvis.app 2>&1 && echo "signature valid ✅"
```
Expected: all ✅

**Step 3: Smoke test — launch the app**

Open a second Terminal and run:
```bash
open /Users/zeisler/jarvis/build/Jarvis.app
```
Or double-click the `.app` in Finder.

Verify manually:
- [ ] 🎙 icon appears in menu bar (macOS may prompt for mic access)
- [ ] Menu shows all items
- [ ] App stays running (it's a background/menu bar app, no Dock icon)

To quit: click the icon → "⏹ Beenden"

**Step 4: Test copying to /Applications (optional)**
```bash
cp -r build/Jarvis.app /Applications/Jarvis.app
open /Applications/Jarvis.app
```

**Step 5: Commit the zip to gitignore, push**

Add `build/` to `.gitignore` if not already there:
```bash
grep -q "^build/" /Users/zeisler/jarvis/.gitignore || echo "build/" >> /Users/zeisler/jarvis/.gitignore
git add .gitignore
git commit -m "chore: ignore build/ directory"
```

Push:
```bash
cd /Users/zeisler/jarvis && git push origin main
```
