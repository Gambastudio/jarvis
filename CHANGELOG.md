# Changelog

## [0.1.0-alpha] - 2026-03-31

### Added
- Initial project structure with src layout
- Claude Agent SDK integration (`ClaudeSDKClient` + `query()`)
- Pluggable voice pipeline: STT, TTS, Wake Word as abstract interfaces
- RealtimeSTT engine (faster-whisper) ported from Jarvis4Gamba v3
- macOS `say` TTS engine
- Whisper-wake engine (wake word via transcription variant matching)
- Feedback loop protection (mic mute during TTS)
- CLI: `jarvis listen`, `jarvis query`, `jarvis config`
- YAML configuration with legacy JSON migration support
- Permission system with default blocked tools for MCP servers
- Agent hooks for logging and dangerous command blocking
- Response router for structured output
- Text cleaner for markdown-to-speech conversion
- API cost tracker
