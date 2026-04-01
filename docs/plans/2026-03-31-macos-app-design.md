# Design: Jarvis macOS Menu Bar App

**Date:** 2026-03-31
**Status:** Approved

## Summary

A native macOS Menu Bar App that wraps the `VoicePipeline` orchestrator.
No Terminal needed — double-click `.app` to start, optional LaunchAgent for autostart.

## Decisions

- **UI Framework:** rumps (Menu Bar) + PyObjC/Cocoa (Log-Fenster)
- **Threading:** VoicePipeline runs in a background thread with its own asyncio event loop; Cocoa/rumps owns the Main Thread
- **State Indication:** Menu Bar icon changes emoji per PipelineState
- **API Key:** macOS Keychain via `security` CLI — never stored in YAML or logs
- **Distribution:** py2app `.app` Bundle + optional LaunchAgent plist

## Menu Bar Icons

| State | Icon | Bedeutung |
|-------|------|-----------|
| IDLE | 🎙 | Wartet auf Wake Word |
| LISTENING | 🟢 | Session aktiv |
| SPEAKING | 🔵 | TTS läuft |
| ERROR | 🔴 | Fehler / Crash |

## Menu Structure

```
🎙 Jarvis
├── [State-Text, nicht klickbar]   e.g. "Wartet auf 'Jarvis'..."
├── ─────────────
├── Log anzeigen
├── ─────────────
├── ⚙️ Einstellungen
│   ├── 🔑 API Key setzen...       → Passwort-Dialog, speichert in Keychain
│   ├── ─────────
│   ├── Wake Word: jarvis          → Text-Dialog
│   ├── Stop Word: danke           → Text-Dialog
│   ├── Exit-Phrase: jarvis beenden → Text-Dialog
│   ├── ─────────
│   ├── Whisper: ✓ base            → Submenu: tiny / base / small
│   ├── Sprache: de                → Submenu: de / en / fr / es
│   ├── Sprechgeschwindigkeit...   → Slider-Dialog (100–300 wpm)
│   ├── ─────────
│   ├── Claude Modell: ✓ sonnet    → Submenu: haiku / sonnet / opus
│   ├── Budget-Limit: $0.50        → Zahl-Dialog
│   ├── Max. Runden: 20            → Zahl-Dialog
│   ├── Kosten-Tracking: ✓         → Toggle
│   └── ── Erweitert ──
│       ├── VAD Sensitivity: 0.4   → Zahl-Dialog
│       ├── Pause-Dauer: 0.8s      → Zahl-Dialog
│       └── Max. Verlauf: 16       → Zahl-Dialog
├── ─────────────
├── Autostart: aktivieren          → installiert/deinstalliert LaunchAgent
├── ─────────────
└── Beenden
```

## Architecture

```
Main Thread (Cocoa/rumps)
    │
    ├── JarvisMenuBarApp(rumps.App)
    │       ├── title/icon wechselt via on_state_change(state) callback
    │       ├── Einstellungs-Dialoge (rumps.Window / AppKit input panels)
    │       └── LogWindow (Cocoa NSWindow)
    │               ├── Thread-safe Queue für Log-Events
    │               └── rumps.Timer (100ms) pollt Queue → NSTextView append
    │
    └── VoicePipelineThread (daemon=True)
            └── asyncio.run(pipeline.run())
                    └── on_state_change callback → thread-safe icon update
```

## File Structure

```
src/jarvis/ui/
├── __init__.py
├── macos_app.py        # JarvisMenuBarApp(rumps.App) — Einstiegspunkt
└── log_window.py       # LogWindow — Cocoa NSWindow mit farbigem Log

scripts/
├── build_app.py        # py2app setup
└── install_agent.py    # LaunchAgent install/uninstall

config/
└── com.gambastudio.jarvis.plist.template  # LaunchAgent template
```

## API Key — Keychain Integration

```python
# Speichern (aus Dialog)
subprocess.run([
    "security", "add-generic-password",
    "-s", "jarvis-voice", "-a", "jarvis",
    "-w", api_key, "-U"  # -U = update if exists
])

# Lesen (beim Start)
result = subprocess.run([
    "security", "find-generic-password",
    "-s", "jarvis-voice", "-w"
], capture_output=True, text=True)
api_key = result.stdout.strip()
```

## VoicePipeline Integration

`JarvisMenuBarApp` übergibt einen `on_state_change` Callback an `VoicePipeline`:

```python
def on_state_change(state: PipelineState) -> None:
    icons = {
        PipelineState.IDLE: "🎙",
        PipelineState.LISTENING: "🟢",
        PipelineState.SPEAKING: "🔵",
        PipelineState.PROCESSING: "🟢",  # same as LISTENING
    }
    # Thread-safe: rumps.App.title update
    app.title = icons.get(state, "🔴")
```

`VoicePipeline` bekommt dafür einen optionalen `state_callback` Parameter.

## py2app Bundle

```python
# scripts/build_app.py
setup(
    app=["src/jarvis/ui/macos_app.py"],
    options={"py2app": {
        "argv_emulation": False,
        "plist": {
            "LSUIElement": True,          # Kein Dock-Icon
            "CFBundleName": "Jarvis",
            "CFBundleIdentifier": "com.gambastudio.jarvis",
        },
        "packages": ["jarvis", "rumps", "RealtimeSTT"],
    }},
)
```

## LaunchAgent

Installiert in `~/Library/LaunchAgents/com.gambastudio.jarvis.plist`.
Startet die `.app` beim Login. Menüpunkt "Autostart aktivieren/deaktivieren"
ruft `scripts/install_agent.py` auf.

## Changes to Existing Code

| File | Change |
|------|--------|
| `src/jarvis/pipeline/orchestrator.py` | Add optional `state_callback` param to `VoicePipeline.__init__` and `run()` |
| `src/jarvis/config.py` | Add `save()` method to write changes back to YAML |
| `src/jarvis/ui/macos_app.py` | **New** — Main app entry point |
| `src/jarvis/ui/log_window.py` | **New** — Cocoa log window |
| `scripts/build_app.py` | **New** — py2app build script |
| `scripts/install_agent.py` | **New** — LaunchAgent helper |
