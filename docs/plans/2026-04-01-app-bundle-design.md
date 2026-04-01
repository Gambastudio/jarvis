# Jarvis.app Bundle — Design Doc

**Date:** 2026-04-01
**Status:** Approved

## Goal

Build a distributable `Jarvis.app` for macOS that:
- Opens with a double-click (no Terminal needed)
- Includes a fully embedded Python environment with all dependencies
- Downloads Whisper model weights on demand (only the selected model)
- Works on any Mac without prior installation
- Can be signed with Developer ID later (currently ad-hoc)

## Decisions Made

| Topic | Decision | Reason |
|---|---|---|
| Bundle approach | Embedded venv in `.app/Contents/Resources/venv/` | Reliable with torch; py2app breaks with heavy ML deps |
| VAD | Silero VAD (torch) | Best quality, no compromise |
| Whisper models | Downloaded on demand to `~/.cache/huggingface/hub/` | Keeps bundle small; user chooses model |
| Code signing | Ad-hoc (`codesign --sign -`) | Developer subscription inactive; can upgrade later |
| Distribution | Zip → GitHub Releases | Simple; DMG can be added later |

## App Structure

```
Jarvis.app/
├── Contents/
│   ├── Info.plist                      ← LSUIElement: True, bundle metadata
│   ├── MacOS/
│   │   └── jarvis                      ← Shell launcher (executable)
│   └── Resources/
│       ├── AppIcon.icns                ← App icon
│       └── venv/                       ← Embedded Python environment
│           ├── bin/
│           │   └── python3.12
│           └── lib/
│               └── python3.12/
│                   └── site-packages/  ← All packages incl. torch
```

## Shell Launcher (`Contents/MacOS/jarvis`)

```bash
#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV="$DIR/../Resources/venv"
exec "$VENV/bin/python3.12" -m jarvis.ui.macos_app "$@"
```

Uses `exec` to replace the shell process — no extra process in Activity Monitor.

## Info.plist

```xml
<key>LSUIElement</key><true/>          ← No Dock icon (menu bar app)
<key>CFBundleName</key><string>Jarvis</string>
<key>CFBundleIdentifier</key><string>com.gambastudio.jarvis</string>
<key>CFBundleVersion</key><string>0.1.0</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>NSMicrophoneUsageDescription</key><string>Jarvis needs microphone access for voice input.</string>
```

`NSMicrophoneUsageDescription` is required — without it macOS silently denies mic access.

## Build Script (`scripts/build_app.sh`)

1. Clean `build/` directory
2. Create `build/Jarvis.app/` directory structure
3. Create fresh venv: `python3.12 -m venv build/Jarvis.app/Contents/Resources/venv`
4. Install package: `pip install -e ".[macos,stt]"` into embedded venv
5. Write `Info.plist`
6. Write shell launcher, `chmod +x`
7. Copy `AppIcon.icns` to Resources (if exists)
8. Ad-hoc codesign: `codesign --deep --force --sign - build/Jarvis.app`
9. Zip: `cd build && zip -r Jarvis-v$(version).zip Jarvis.app`

## Whisper Model Download UX

`faster-whisper` downloads models via `huggingface_hub` on first `WhisperModel()` init.
This happens inside the pipeline thread — without UI feedback the app looks frozen.

**Fix in `macos_app.py`:**
Before starting the pipeline, check if the model is cached:

```python
from huggingface_hub import try_to_load_from_cache

def _is_model_cached(model: str) -> bool:
    result = try_to_load_from_cache(
        f"Systran/faster-whisper-{model}", "model.bin"
    )
    return result is not None

# In _start_pipeline():
if not _is_model_cached(self.cfg.stt.model):
    size = {"tiny": "75MB", "base": "150MB", "small": "500MB"}.get(
        self.cfg.stt.model, "?"
    )
    self._update_status(f"📥 Lade {self.cfg.stt.model}-Modell herunter (~{size})...")
```

The download happens naturally during pipeline init — the status message appears
while the model downloads. Once the pipeline is ready, `_on_state_change` updates
the status to the normal "Wartet auf Wake Word..." state.

## Bundle Size Estimate

| Component | Size |
|---|---|
| Python 3.12 interpreter | ~30 MB |
| PyTorch (Silero VAD) | ~550 MB |
| CTranslate2 (faster-whisper) | ~50 MB |
| rumps, PyObjC, RealtimeSTT, other deps | ~100 MB |
| **Total .app** | **~730 MB** |
| Whisper tiny (on demand) | +75 MB |
| Whisper base (on demand) | +150 MB |
| Whisper small (on demand) | +500 MB |

## Code Signing

```bash
# Ad-hoc (current — works on same-architecture Macs, requires right-click → Open on others)
codesign --deep --force --sign - Jarvis.app

# With Developer ID (future — passes Gatekeeper on all Macs)
codesign --deep --force --sign "Developer ID Application: Name (TEAMID)" Jarvis.app
xcrun notarytool submit Jarvis.zip --apple-id ... --team-id ... --password ...
```

## Files to Create/Modify

| File | Action |
|---|---|
| `scripts/build_app.sh` | Create — main build script |
| `resources/AppIcon.icns` | Create — app icon (placeholder or real) |
| `src/jarvis/ui/macos_app.py` | Modify — add `_is_model_cached()` + download status |
| `README.md` | Modify — add "Download & Install" section |

## Out of Scope

- DMG packaging (can be added in a follow-up)
- GitHub Actions automated build (can be added later)
- Notarization (requires active Developer subscription)
- Auto-update mechanism
