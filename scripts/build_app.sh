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
echo "▶ Creating embedded venv (this takes a few minutes — torch is large)..."
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
codesign --verify --verbose "$APP_DIR"

# ── Zip for distribution ───────────────────────────────────────────────────────
ARCHIVE="$BUILD_DIR/$APP_NAME-v$VERSION.zip"
echo "▶ Creating archive..."
( cd "$BUILD_DIR" && zip -r "$APP_NAME-v$VERSION.zip" "$APP_NAME.app" -q )

echo ""
echo "✅ Build complete!"
echo "   App:     $APP_DIR"
echo "   Size:    $(du -sh "$APP_DIR" | cut -f1)"
echo "   Archive: $ARCHIVE"
echo "   Size:    $(du -sh "$ARCHIVE" | cut -f1)"
echo ""
echo "To install: cp -r $APP_DIR /Applications/"
