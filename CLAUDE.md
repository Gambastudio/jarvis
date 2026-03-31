# Jarvis — Open Source Voice Agent Framework

## Projekt-Kontext

Du arbeitest am Repository `GambaStudio/jarvis` — ein Open Source Voice Agent Framework auf Basis der Claude Agent SDK.

### Bestehender Prototyp (Referenz)
Der Code in `/Users/zeisler/Documents/Claude/Projects/Jarvis4Gamba/` ist der funktionierende Prototyp v3:
- `jarvis.py` — CLI-Version, RealtimeSTT + faster-whisper + Anthropic SDK + macOS say
- `jarvis_app.py` — macOS Menu Bar App (rumps + Cocoa NSWindow)
- `claude_bridge.py` — tmux-basierte Claude Code Session mit BLOCKED_TOOLS (nie integriert)
- `config.json` — Konfiguration (LLM, Whisper, Wake/Stop Word, Speech Rate)

### Projektkonzept
Das vollständige Konzept liegt unter `/Users/zeisler/jarvis/docs/projektkonzept.md`.
Lies es bei Bedarf — es beschreibt Architektur, Tech-Stack, MVP Scope, Roadmap und Repo-Struktur.

## Aufgabe: Repository aufsetzen

### 1. Projekt-Struktur (src-Layout)
```
jarvis/
├── README.md                    # Englisch, Community-facing
├── LICENSE                      # MIT
├── CONTRIBUTING.md
├── CHANGELOG.md
├── pyproject.toml               # Package: jarvis-voice
├── .gitignore
│
├── src/jarvis/
│   ├── __init__.py
│   ├── __main__.py              # python -m jarvis
│   ├── cli.py                   # Typer CLI: listen, query, config
│   ├── config.py                # YAML + JSON Config Loading
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── base.py              # ABC Interfaces: STTEngine, TTSEngine, WakeWordEngine
│   │   ├── orchestrator.py      # Voice Pipeline Orchestrator
│   │   ├── audio.py             # Audio I/O
│   │   ├── vad.py               # Silero VAD
│   │   ├── feedback_guard.py    # Mic-Mute während TTS (aus Prototyp)
│   │   │
│   │   ├── stt/
│   │   │   ├── __init__.py
│   │   │   └── realtimestt.py   # RealtimeSTT Engine (Default)
│   │   │
│   │   ├── tts/
│   │   │   ├── __init__.py
│   │   │   ├── macos_say.py     # macOS say (Default macOS)
│   │   │   └── piper.py         # Piper TTS (Default Cross-Platform)
│   │   │
│   │   └── wake/
│   │       ├── __init__.py
│   │       └── whisper_wake.py  # Whisper-Varianten (aus Prototyp)
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── core.py              # ClaudeSDKClient / query() Wrapper
│   │   ├── session.py           # Session Management
│   │   ├── hooks.py             # Voice-spezifische Hooks
│   │   ├── permissions.py       # allowed/disallowed Tools
│   │   └── response.py          # Response Router
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   └── terminal.py          # rich/textual Terminal UI
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       ├── text_cleaner.py      # Markdown → Speech (aus Prototyp)
│       └── cost_tracker.py
│
├── skills/
│   └── general/SKILL.md
│
├── config/
│   ├── jarvis.default.yaml
│   ├── CLAUDE.md.example
│   └── .mcp.json.example
│
├── tests/
│   ├── __init__.py
│   └── test_config.py
│
├── docs/
│   ├── projektkonzept.md        # Konzept v1.1
│   └── architecture.md
│
└── .github/
    └── workflows/
        └── ci.yml
```

### 2. Kern-Migration: messages.create() → Agent SDK

Der zentrale Wechsel. Aus:
```python
r = client.messages.create(model=MODEL, max_tokens=200, system=PROMPT, messages=history)
reply = r.content[0].text
```

Wird:
```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
async with ClaudeSDKClient(options=ClaudeAgentOptions(
    system_prompt=load_claude_md(),
    allowed_tools=["Read", "Bash", "Glob", "Grep", "WebSearch"],
    mcp_servers=load_mcp_config(),
    max_turns=15,
    permission_mode="acceptEdits",
)) as client:
    await client.query(text)
    async for msg in client.receive_response():
        if isinstance(msg, ResultMessage): return msg.result
```

### 3. Aus Prototyp übernehmen
- Whisper-Varianten Liste (JARVIS_VARIANTS) → whisper_wake.py
- Feedback-Loop-Schutz (set_microphone + clear_audio_queue) → feedback_guard.py
- Session-Modus (Jarvis/Danke) → orchestrator.py
- Text-Cleaner (_clean_for_speech) → text_cleaner.py
- Auto-Recovery Pattern → orchestrator.py
- BLOCKED_TOOLS → permissions.py als disallowed_tools

### 4. GitHub
- Remote: git@github.com:GambaStudio/jarvis.git
- Branch: main
- Erster Commit: "Initial project structure with Agent SDK integration"

## Konventionen
- Python 3.12, Type Hints überall
- Ruff für Linting + Formatting
- pytest für Tests
- Docstrings für alle Public APIs
- README und CONTRIBUTING auf Englisch (Community)
- Code-Kommentare auf Englisch
- Commit Messages auf Englisch

## Wichtig
- pip install immer mit --break-system-packages
- Keine interaktiven Editoren (nano etc.)
- Absolute Pfade
- Bei destruktiven Aktionen (Löschen, Überschreiben): vorher fragen
