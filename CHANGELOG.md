# Changelog

All notable changes to Jarvis are documented here.
Versioning follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

- `MINOR` — new features
- `PATCH` — bug fixes
- `1.0.0` — first stable release for public use

---

## [0.3.0] - 2026-04-02

### Added
- Deepgram Nova-3 STT engine as alternative to RealtimeSTT (cloud-based, low-latency)
- STT engine selector in settings menu (RealtimeSTT local vs Deepgram cloud)
- Deepgram API key management via macOS Keychain
- `stt-deepgram` optional dependency group (`deepgram-sdk`, `pyaudio`)

---

## [0.2.0] - 2026-04-01

### Added
- Persistent `ClaudeSDKClient` in dedicated background event loop — eliminates per-query startup overhead
- Agent warmup on app start — client connects immediately, first query has no delay
- Dynamic context injection per query: date, time, timezone, username, hostname
- Memory system: configurable path + file list, loaded from `~/Documents/Claude/Memory/` by default
- Memory settings in menu bar: path and file list configurable at runtime
- High-quality app icon: dark deep-space design with glowing orb and "J" lettermark
- Safety rule in agent system prompt: never delete or modify without explicit confirmation
- `credentials.md` permanently excluded from memory loading (security policy)

### Fixed
- Event loop conflict: agent now runs in its own dedicated loop — no more asyncio collisions with STT/TTS
- macOS folder permission dialogs no longer appear at startup (memory loaded on first query only)
- Context time/date stays fresh — rebuilt on every query, not frozen at connect time

---

## [0.1.0] - 2026-03-31

### Added
- Initial project structure (src-layout, pyproject.toml)
- Voice pipeline: RealtimeSTT → Wake Word → Claude Agent SDK → macOS `say`
- macOS Menu Bar App (rumps + PyObjC) with full settings menu
- Whisper-based wake word detection with German variant list
- Session management: wake word → LISTENING → stop word → IDLE
- Feedback loop prevention: mic muted during TTS
- Auto-recovery: pipeline restarts on crash
- Log window: native NSWindow with colored live output
- API key storage via macOS Keychain
- Configurable: Whisper model, language, TTS rate, Claude model, budget, max turns
- Autostart via LaunchAgent
- Distributable `.app` bundle via `scripts/build_app.sh`
- C launcher for correct macOS process identity (Jarvis.app in menu bar)
- Text cleaner for markdown-to-speech conversion
- YAML configuration with legacy JSON migration support
