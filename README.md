# Jarvis

**Open Source Voice Agent Framework powered by Claude Agent SDK**

Give Claude a voice. Jarvis connects local speech processing with Claude's full agent capabilities — tool use, MCP servers, sessions, subagents — all controlled by voice.

---

## What makes Jarvis different

- **Full agent, not just chat.** Claude Agent SDK provides the same agent loop as Claude Code — autonomous tool use, multi-step reasoning, file access, web search. Jarvis makes it voice-accessible.
- **MCP as a plugin system.** Every MCP server becomes a voice plugin. GitHub, Slack, databases, Home Assistant, custom APIs — all through the same interface.
- **Local where possible.** Wake word detection, STT, and TTS run entirely on-device. Only the LLM call goes to the Claude API (or Bedrock/Vertex for enterprise).
- **Extensible.** Define custom tools with a Python decorator, register them as in-process MCP servers — done.

## Quick Start

```bash
pip install jarvis-voice[stt]

# Set your API key
export ANTHROPIC_API_KEY=your-key

# Start listening
jarvis listen
```

Say **"Jarvis"** to activate, ask your question, say **"Danke"** to end the session.

## Text mode (no microphone needed)

```bash
jarvis query "What files are in this directory?"
```

## Architecture

```
Microphone → Wake Word Detection → STT (Whisper) → Claude Agent SDK → TTS → Speaker
                                                          ↕
                                                     MCP Servers
                                                  (GitHub, DB, HA, ...)
```

### Voice Pipeline

The pipeline runs a continuous loop:

1. **Wake Word** — Whisper transcription matched against phonetic variants (or openWakeWord)
2. **STT** — RealtimeSTT with faster-whisper, running locally
3. **Agent SDK** — `claude_agent_sdk.query()` with full tool access
4. **TTS** — macOS `say` (default) or Piper for cross-platform
5. **Feedback Guard** — Mic muted during TTS to prevent loops

### Pluggable Components

Every pipeline component is an interface. Swap implementations via config:

| Component | Default | Alternatives |
|-----------|---------|-------------|
| Wake Word | `whisper-wake` | `openwakeword` |
| STT | `realtimestt` (faster-whisper) | `whisper-cpp`, cloud |
| TTS | `macos-say` | `piper`, `kokoro`, `elevenlabs` |
| LLM | Claude Sonnet | Claude Opus, Haiku, Bedrock, Vertex |

## Configuration

Create `jarvis.yaml` in your project or `~/.jarvis/`:

```yaml
stt:
  model: base           # tiny | base | small | medium
  language: de

tts:
  engine: macos-say
  rate: 200

agent:
  model: claude-sonnet-4-6
  max_turns: 20
  max_budget_usd: 0.50

session:
  wake_word: jarvis
  stop_word: danke
```

### MCP Servers

Add MCP servers via `.mcp.json` or in `jarvis.yaml`:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" }
    }
  }
}
```

Every tool from connected MCP servers becomes available to the voice agent.

### CLAUDE.md

Customize the agent personality and rules via `CLAUDE.md`:

```markdown
# Jarvis Voice Agent

You are Jarvis, a voice-controlled AI assistant.
- Keep answers short — they will be read aloud.
- No markdown formatting in spoken responses.
- Confirm actions briefly: "Done", "Light is on", "3 open alerts".
```

## Project Structure

```
src/jarvis/
├── cli.py              # CLI: listen, query, config
├── config.py           # YAML/JSON config management
├── pipeline/
│   ├── base.py         # Abstract interfaces (STT, TTS, WakeWord)
│   ├── feedback_guard.py
│   ├── stt/            # Speech-to-Text engines
│   ├── tts/            # Text-to-Speech engines
│   └── wake/           # Wake word engines
├── agent/
│   ├── core.py         # Claude Agent SDK integration
│   ├── permissions.py  # Tool access control
│   ├── hooks.py        # Logging, security hooks
│   └── response.py     # Response routing
└── utils/
    ├── text_cleaner.py # Markdown → speech
    └── cost_tracker.py # API cost tracking
```

## Requirements

- Python 3.10+
- macOS, Linux, or Windows
- Microphone (for voice mode)
- Anthropic API key (or Bedrock/Vertex credentials)

## Development

```bash
git clone https://github.com/GambaStudio/jarvis.git
cd jarvis
pip install -e ".[dev,stt]"
pytest
```

## License

MIT License. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

*Jarvis — Give Claude a Voice.*
