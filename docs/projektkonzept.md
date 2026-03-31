# Jarvis — Open Source Voice Agent Framework

## Projektkonzept v1.1

**Autor:** Andreas Zeisler / Logiphys Datensysteme GmbH
**Datum:** 31. März 2026
**Status:** Konzeptphase — Prototyp v3 läuft stabil
**Lizenz:** MIT (geplant)
**Repository:** github.com/logiphys/jarvis *(geplant)*

---

## 1. Vision & USP

Jarvis ist ein Open-Source-Framework für sprachgesteuerte KI-Agenten auf Basis der Claude Agent SDK. Der zentrale Unterschied zu bestehenden Voice Assistants: Jarvis gibt einem lokalen Sprachagenten vollen Zugriff auf Claudes Tool-Ökosystem via MCP — Dateien lesen, Befehle ausführen, APIs ansprechen, Datenbanken abfragen — alles per Stimme.

**Was Jarvis einzigartig macht:**

- **Voller Agent, nicht nur Chat:** Claude Agent SDK liefert denselben Agent-Loop wie Claude Code — autonomes Tool-Use, Subagents, Hooks, Sessions. Jarvis macht das per Stimme zugänglich.
- **MCP als Plugin-System:** Jeder MCP-Server wird automatisch zum Voice-Plugin. GitHub, Slack, Datenbanken, Home Assistant, eigene APIs — alles über dieselbe Schnittstelle.
- **Lokal wo möglich:** Wake Word Detection, STT und TTS laufen vollständig lokal. Nur der LLM-Call geht an die Claude API (oder Bedrock/Vertex für Enterprise).
- **Beliebig erweiterbar:** Eigene Tools per `@tool`-Decorator in Python definieren, als In-Process MCP-Server registrieren — fertig.
- **Structured Output:** Antworten können je nach Kontext als Text, JSON, UI-Kommandos oder Aktions-Sequenzen strukturiert zurückkommen.

**Zielgruppe:** Entwickler und Power-User, die einen programmierbaren, erweiterbaren Voice Agent wollen — kein Consumer-Produkt à la Alexa, sondern ein Developer-Framework.

---

## 2. Bestehender Prototyp — Jarvis4Gamba v3

Bevor die Zielarchitektur beschrieben wird, ist der aktuelle Stand dokumentiert. Der Prototyp **läuft stabil** auf einem Mac Mini M2 Pro (32 GB RAM) und besteht aus vier Dateien mit unterschiedlichen Ansätzen:

### 2.1 Aktuelle Dateien

| Datei | Zweck | Status |
|---|---|---|
| `jarvis.py` | CLI-Version v3, durchgehender Recorder, Session-Modus | Stabil, Hauptversion |
| `jarvis_app.py` | macOS Menu Bar App via `rumps` + Cocoa Log-Fenster | Stabil, vollständig |
| `jarvis_gui.py` | Tkinter-basierte GUI-Variante | Funktional, nicht weiterentwickelt |
| `claude_bridge.py` | tmux-basierte Claude Code Session mit MCP-Zugriff | Konzept, nicht integriert |

### 2.2 Aktueller Stack

```
┌──────────────────────────────────────────────────────┐
│                    Mac Mini M2 Pro                     │
│                                                        │
│  ┌────────────────┐   ┌───────────────────────────┐  │
│  │ Universal Audio │──>│ RealtimeSTT               │  │
│  │ Thunderbolt Mic │   │ + faster-whisper (base)   │  │
│  └────────────────┘   │ + Silero VAD              │  │
│                        │ + Whisper-Varianten als    │  │
│                        │   Wake Word (kein oww)     │  │
│                        └───────────┬───────────────┘  │
│                                    │                   │
│  ┌─────────────────────────────────┼────────────────┐ │
│  │ jarvis_app.py (rumps Menu Bar)  │                │ │
│  │  ┌──────────────┐              │                │ │
│  │  │ Cocoa Native │              │                │ │
│  │  │ Log Window   │              │                │ │
│  │  └──────────────┘              │                │ │
│  │  Config: LLM, Whisper-Modell,  │                │ │
│  │  Wake/Stop Word, Speech Rate   │                │ │
│  └─────────────────────────────────┼────────────────┘ │
│                                    │                   │
│                          ┌─────────▼─────────┐        │
│                          │ Anthropic SDK      │        │
│                          │ client.messages    │        │
│                          │ .create()          │        │
│                          │ (Sonnet, max 200t) │        │
│                          └─────────┬─────────┘        │
│                                    │                   │
│                          ┌─────────▼─────────┐        │
│                          │ macOS `say`        │        │
│                          │ Siri Stimme 3      │        │
│                          │ Rate: 200 wpm      │        │
│                          └───────────────────┘        │
│                                                        │
│  (Nicht integriert:)                                   │
│  ┌──────────────────────────────────────────────┐     │
│  │ claude_bridge.py                              │     │
│  │ tmux → Claude Code CLI → MCP-Server           │     │
│  │ Blocked Tools: create, delete, move, update   │     │
│  │ Screen-Scraping für Antwort-Extraktion        │     │
│  └──────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

### 2.3 Was bereits funktioniert

- **Voice Pipeline** — RealtimeSTT mit Silero VAD, faster-whisper `base` Modell, Deutsch
- **Wake Word** — Whisper-Transkription + Varianten-Liste (26 Varianten von "Jarvis"), kein separater Wake Word Detector
- **Session-Modus** — "Jarvis" aktiviert, "Danke" beendet, "Jarvis beenden" stoppt das Programm
- **Feedback-Loop-Schutz** — Mic wird während TTS stumm geschaltet + Audio-Queue geleert
- **Auto-Recovery** — Recorder-Crash wird abgefangen, automatischer Neustart nach 2s
- **macOS Menu Bar App** — Nativer rumps-App mit Cocoa NSWindow für Live-Log, farbige Ausgabe, konfigurierbar über Menü
- **Konfiguration** — JSON-Config mit LLM-Modell, Whisper-Modell, Wake/Stop Word, Sprechgeschwindigkeit
- **LaunchDaemon** — `com.logiphys.jarvis.plist` für Autostart

### 2.4 Was NICHT funktioniert / fehlt

- **Kein Tool-Zugriff** — `client.messages.create()` ist ein reiner Chat-Call, keine Tool-Ausführung
- **ClaudeBridge nie integriert** — Der tmux-basierte Ansatz (`claude_bridge.py`) mit Screen-Scraping wurde konzipiert, aber nicht in die Voice Pipeline eingebaut
- **Kein MCP-Zugriff** — Datto RMM, Autotask, Filesystem etc. sind nicht erreichbar
- **Keine Sessions** — Jede Konversation geht nach "Danke" verloren, max 16 Messages History
- **macOS-only** — `say`, `rumps`, `AppKit` sind macOS-spezifisch, kein Cross-Platform
- **max_tokens=200** — Antworten sind künstlich gekürzt
- **Kein Hintergrund-Betrieb** — Mic-Berechtigung erfordert Terminal-Fokus

### 2.5 Was übernommen wird

Aus dem Prototyp kommen bewährte Patterns ins neue Framework:

| Pattern | Prototyp | Jarvis Framework |
|---|---|---|
| Wake Word via Whisper-Varianten | `JARVIS_VARIANTS` Liste | Optionaler `whisper-wake` Engine neben `openwakeword` |
| Feedback-Loop-Schutz | `set_microphone(False)` + `clear_audio_queue()` | Standardverhalten in der Pipeline |
| Session-Modus (Aktivierung/Deaktivierung) | "Jarvis" / "Danke" | Konfigurierbar, default Verhalten |
| Menu Bar App (macOS) | rumps + Cocoa LogWindow | Platform-native UI als Option neben Tauri |
| Blocked Tools Konzept | `BLOCKED_TOOLS` Liste in claude_bridge.py | `disallowed_tools` in Agent SDK Options |
| System Prompt für Sprachausgabe | "Antworte in 1-3 kurzen Sätzen" | CLAUDE.md mit Voice-optimierten Anweisungen |
| Auto-Recovery | while-Loop mit try/except | Watchdog-Pattern mit Health Checks |
| Config über JSON | `config.json` | Erweitert zu YAML mit mehr Optionen |

---

## 3. Architektur-Übersicht (Ziel)

### 3.1 Systemdiagramm

```
┌──────────────────────────────────────────────────────────────┐
│                Desktop App Layer (wählbar)                     │
│                                                                │
│  Option A: macOS Menu Bar    Option B: Tauri     Option C: CLI │
│  ┌──────────────────────┐   ┌──────────────┐   ┌───────────┐ │
│  │ rumps + Cocoa Window  │   │ WebView UI   │   │ Terminal  │ │
│  │ (bewährt aus v3)      │   │ (Cross-Plat) │   │ rich/tui  │ │
│  └──────────┬───────────┘   └──────┬───────┘   └─────┬─────┘ │
│             └─────────────────────┼───────────────────┘       │
│                             Event Bus / Callbacks              │
└─────────────────────────────────┬────────────────────────────┘
                                  │
┌─────────────────────────────────┼────────────────────────────┐
│                      Python Core                              │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │                  Voice Pipeline                         │   │
│  │                                                         │   │
│  │  ┌──────────────────┐  ┌───────────┐  ┌────────────┐  │   │
│  │  │ Wake Word Engine │→│    STT     │→│ Agent SDK   │  │   │
│  │  │                  │  │            │  │             │  │   │
│  │  │ ● openwakeword   │  │ ● faster-  │  │ ● query()   │  │   │
│  │  │ ● whisper-wake   │  │   whisper  │  │ ● Client()  │  │   │
│  │  │   (aus v3)       │  │ ● whisper  │  │ ● Sessions  │  │   │
│  │  │ ● custom         │  │   .cpp     │  │ ● Hooks     │  │   │
│  │  └──────────────────┘  │ ● cloud    │  │ ● Subagents │  │   │
│  │                        └───────────┘  └──────┬──────┘  │   │
│  │                                               │         │   │
│  │  ┌───────────┐   ┌────────────────┐          │         │   │
│  │  │    TTS    │◄──│ Response Router │◄─────────┘         │   │
│  │  │           │   │                │                     │   │
│  │  │ ● piper   │   │ speak → TTS    │                     │   │
│  │  │ ● macos   │   │ confirm → Beep │                     │   │
│  │  │   say     │   │ display → UI   │                     │   │
│  │  │ ● kokoro  │   │ error → Alert  │                     │   │
│  │  │ ● cloud   │   └────────────────┘                     │   │
│  │  └───────────┘                                          │   │
│  │                                                         │   │
│  │  Feedback-Loop-Schutz: Mic-Mute + Queue-Clear (aus v3) │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              MCP Server Registry                        │   │
│  │                                                         │   │
│  │  stdio:                    http/sse:    in-process:     │   │
│  │  ┌────────┐ ┌─────────┐  ┌────────┐  ┌────────────┐  │   │
│  │  │FS/Shell│ │ GitHub  │  │  HA    │  │ @tool deco │  │   │
│  │  │ Datto  │ │ Slack   │  │ Custom │  │ Custom Py  │  │   │
│  │  │Autotask│ │ Postgres│  │  APIs  │  │ Functions  │  │   │
│  │  └────────┘ └─────────┘  └────────┘  └────────────┘  │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              Permissions Layer                           │   │
│  │                                                         │   │
│  │  allowed_tools:   ["Read", "Glob", "mcp__datto__*"]    │   │
│  │  disallowed_tools: ["mcp__datto__create*", "Write"]     │   │
│  │  can_use_tool:     custom callback für Voice-Confirm    │   │
│  │                                                         │   │
│  │  (übernommen aus claude_bridge.py BLOCKED_TOOLS)        │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │              Konfiguration                              │   │
│  │  CLAUDE.md │ Skills │ .mcp.json │ jarvis.yaml          │   │
│  └────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Der zentrale Upgrade: Anthropic SDK → Agent SDK

Dies ist der wichtigste architektonische Wandel. Der Prototyp nutzt `client.messages.create()` — einen einfachen Chat-Call ohne Tool-Zugriff:

```python
# Prototyp (jarvis.py) — Nur Chat, keine Tools
r = client.messages.create(
    model=CLAUDE_MODEL, max_tokens=200,
    system=SYSTEM_PROMPT, messages=history
)
reply = r.content[0].text
```

Die Claude Agent SDK ersetzt das durch einen vollständigen Agent-Loop:

```python
# Jarvis Framework — Voller Agent mit Tools
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=ClaudeAgentOptions(
    system_prompt=load_claude_md(),
    allowed_tools=["Read", "Bash", "Glob", "Grep", "WebSearch",
                    "mcp__datto-rmm__list-*", "mcp__datto-rmm__get-*",
                    "mcp__homeassistant__*"],
    disallowed_tools=[
        "mcp__datto-rmm__create-*", "mcp__datto-rmm__delete-*",
        "mcp__datto-rmm__update-*", "mcp__datto-rmm__move-*",
    ],
    mcp_servers=load_mcp_config(),
    max_turns=15,
    max_budget_usd=0.50,
    permission_mode="acceptEdits",
    thinking={"type": "adaptive"},
    setting_sources=["project"],
)) as client:
    await client.query(transcribed_text)
    async for message in client.receive_response():
        if isinstance(message, ResultMessage) and message.subtype == "success":
            response_text = message.result
```

**Was sich dadurch ändert:**

| Fähigkeit | `messages.create()` | Agent SDK |
|---|---|---|
| Tool-Ausführung | Nicht möglich | Automatisch (Read, Bash, etc.) |
| MCP-Server | Nicht möglich | Nativ via `.mcp.json` |
| Mehrstufige Aufgaben | Nicht möglich | Agent-Loop iteriert autonom |
| Sessions mit Kontext | Manuell (history array) | `ClaudeSDKClient` mit `receive_response()` |
| Subagents | Nicht möglich | `AgentDefinition` |
| Permission Control | Nicht möglich | `allowed_tools`, `disallowed_tools`, Callbacks |
| Hooks (Logging, Security) | Nicht möglich | PreToolUse, PostToolUse, Stop |
| Structured Output | Manuell parsen | JSON-Schema validiert |
| Cost Tracking | Nicht möglich | `total_cost_usd` in ResultMessage |
| Unterbrechung | Nicht möglich | `client.interrupt()` |

### 3.3 ClaudeBridge-Ersatz

Die `claude_bridge.py` war der Versuch, Claude Code CLI-Features (MCP-Server, Tools) über tmux Screen-Scraping nutzbar zu machen. Das wird komplett ersetzt:

```python
# ALT: claude_bridge.py — tmux Screen-Scraping
_tmux("send-keys", "-t", SESSION_NAME, msg, "Enter")
# ... 60s Poll-Loop, ANSI-Strip, instabil

# NEU: Agent SDK — Native Python API
async for message in query(prompt=msg, options=options):
    if hasattr(message, "result"):
        return message.result
```

Die `BLOCKED_TOOLS` Liste aus der Bridge wird zum `disallowed_tools` Parameter:

```python
# ALT: Manuelle String-Liste
BLOCKED_TOOLS = [
    "mcp__datto-rmm__create-account-variable",
    "mcp__datto-rmm__create-quick-job",
    # ... 20 weitere Einträge
]

# NEU: Wildcard-Patterns in Agent SDK
disallowed_tools = [
    "mcp__datto-rmm__create-*",
    "mcp__datto-rmm__delete-*",
    "mcp__datto-rmm__update-*",
    "mcp__datto-rmm__move-*",
    "mcp__datto-rmm__set-*",
    "mcp__datto-rmm__resolve-*",
]
```

### 3.4 Voice-spezifische Hooks

Die Agent SDK bietet Hooks für Logging und Security. Für Voice-Agents kommen spezifische Hooks dazu:

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

async def voice_confirm_destructive(input_data, tool_use_id, context):
    """Bei destruktiven Aktionen: Sprachbestätigung einholen."""
    tool = input_data["tool_name"]
    if any(kw in tool for kw in ["delete", "create", "update", "move"]):
        speak("Soll ich das wirklich ausführen?")
        confirmation = await listen_for_yes_no()
        if not confirmation:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Vom Nutzer per Sprache abgelehnt",
                }
            }
    return {}

async def log_tool_usage(input_data, tool_use_id, context):
    """Jede Tool-Nutzung loggen für Transparenz."""
    tool = input_data["tool_name"]
    log.info(f"Tool aufgerufen: {tool}")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="mcp__*", hooks=[voice_confirm_destructive]),
            HookMatcher(hooks=[log_tool_usage]),
        ]
    }
)
```

### 3.5 Skills & CLAUDE.md Konfiguration

Jarvis nutzt das Skills-System der Agent SDK. Skills sind Markdown-Dateien mit spezialisierten Anweisungen:

```
.jarvis/
├── CLAUDE.md                    # Globale Agent-Instruktionen
├── skills/
│   ├── smart-home/SKILL.md     # Smart Home Steuerung
│   ├── msp-monitoring/SKILL.md # Datto RMM / Autotask
│   ├── music/SKILL.md          # Musik-Steuerung
│   └── coding/SKILL.md         # Code-Assistenz
├── commands/
│   ├── status.md               # /status Slash Command
│   └── alerts.md               # /alerts Slash Command
└── .mcp.json                    # MCP Server Konfiguration
```

Die `CLAUDE.md` kombiniert das System Prompt aus dem Prototyp mit Agent-spezifischen Regeln:

```markdown
# Jarvis Voice Agent

Du bist Jarvis, ein sprachgesteuerter KI-Assistent.

## Antwort-Stil
- Antworte knapp und präzise — du wirst vorgelesen.
- Keine Markdown-Formatierung, keine Listen, keine Sonderzeichen.
- Natürliche, kurze Sätze. Du duzt den Nutzer.
- Bestätige Aktionen kurz: "Erledigt", "Licht ist an", "3 offene Alerts".
- Bei langen Ergebnissen: zusammenfassen, nicht alles vorlesen.

## Tool-Nutzung
- Lesende Aktionen autonom ausführen (Alerts prüfen, Geräte auflisten).
- Schreibende Aktionen immer bestätigen lassen (Ticket erstellen, Gerät verschieben).
- Bei Fehlern kurz erklären was passiert ist, keine Stack Traces vorlesen.

## Verfügbare Systeme
- Datto RMM: Geräte, Alerts, Sites, Jobs (nur lesend ohne Bestätigung)
- Autotask: Tickets, Kontakte, Rechnungen (nur lesend ohne Bestätigung)
- Home Assistant: Licht, Heizung, Jalousien, Sensoren
- Dateisystem: Lesen, Suchen
- Web: Suchen, Seiten abrufen
```

### 3.6 Structured Output für Antwort-Typen

```python
options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "response_type": {
                    "type": "string",
                    "enum": ["speak", "action_confirm", "data_display", "error"]
                },
                "spoken_text": {"type": "string"},
                "display_data": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "items": {"type": "array"}
                    }
                },
                "actions_taken": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["response_type", "spoken_text"]
        }
    }
)
```

So kann die UI entscheiden: nur vorlesen, eine Liste anzeigen, oder eine Bestätigung mit Details rendern.

---

## 4. Tech-Stack Empfehlung

### 4.1 Frontend: Drei Optionen — Platform-Native First

Anders als im ersten Entwurf empfehle ich **nicht** sofort Tauri. Der Prototyp hat eine funktionierende macOS Menu Bar App. Die Strategie:

**Option A: macOS Native (rumps + Cocoa) — Default für macOS**

Bereits vorhanden und bewährt. Wird als `jarvis[macos]` Optional-Dependency ausgeliefert:
- rumps für Menu Bar Integration
- Cocoa NSWindow für Log-Fenster (bereits implementiert)
- System Tray mit Status-Icons
- Nativer Look & Feel, minimaler RAM-Overhead

**Option B: Tauri 2.x — Cross-Platform Desktop (Phase 2+)**

Für Linux/Windows oder wenn eine reichere UI gewünscht ist:
- 5-10 MB Bundle Size
- WebView-basiert (Svelte oder React Frontend)
- Python Backend als Sidecar-Prozess
- Waveform-Visualisierung, Conversation History

**Option C: CLI — Universell**

Immer verfügbar, kein UI-Framework nötig:
- `jarvis listen` — Voice Pipeline im Terminal
- `jarvis query "..."` — Einzelne Text-Anfrage
- `jarvis config` — Konfiguration bearbeiten
- Optional: `rich`/`textual` für Terminal-UI

**Empfehlung:** CLI + macOS Native für v1.0, Tauri als Phase 2 für Cross-Platform.

### 4.2 Backend: Python + Claude Agent SDK

```
pip install claude-agent-sdk
```

**Python 3.10+** ist Pflicht (Agent SDK Requirement). Der Prototyp läuft bereits auf 3.12.

Zwei API-Stufen:
- `query()` — Einfache Einzelanfragen (ersetzt `messages.create()`)
- `ClaudeSDKClient` — Bidirektionale Konversation mit Session-Erhalt, Interrupts, Multi-Turn

**LLM-Provider:** Standardmäßig Claude API (Anthropic). Alternativ:
- Amazon Bedrock: `CLAUDE_CODE_USE_BEDROCK=1`
- Google Vertex AI: `CLAUDE_CODE_USE_VERTEX=1`
- Microsoft Azure: `CLAUDE_CODE_USE_FOUNDRY=1`

### 4.3 STT: RealtimeSTT + faster-whisper (beibehalten)

Der Prototyp nutzt bereits **RealtimeSTT** mit faster-whisper. Das funktioniert gut und wird beibehalten, aber konfigurierbar gemacht:

| Engine | Beschreibung | Use Case |
|---|---|---|
| `realtimestt` | RealtimeSTT Bibliothek (aktuell) | Default, bewährt |
| `faster-whisper` | Standalone faster-whisper | Mehr Kontrolle über Pipeline |
| `whisper-cpp` | whisper.cpp via Python Binding | Max Performance auf Apple Silicon |
| `cloud-google` | Google Cloud Speech-to-Text | Höchste Genauigkeit |
| `cloud-azure` | Azure Speech Services | Enterprise |

**Default:** `realtimestt` mit faster-whisper backend, Modell `base`, Sprache `de`.
**Upgrade-Empfehlung:** Modell auf `small` oder `medium` wechseln für bessere Erkennung.

### 4.4 TTS: Pluggable mit macOS `say` als Default

Der Prototyp nutzt `macOS say` — das funktioniert, klingt aber nicht premium. Die Architektur wird pluggable:

| Engine | Lokal | Qualität | Latenz | Cross-Platform |
|---|---|---|---|---|
| `macos-say` | Ja | Mittel | Sehr niedrig | Nur macOS |
| `piper` | Ja | Gut | 20-30ms | Ja |
| `kokoro` | Ja | Sehr gut | ~100ms | Ja |
| `coqui-xtts` | Ja | Exzellent | ~500ms | Ja |
| `elevenlabs` | Nein | Premium | ~200ms | Ja |

**Default macOS:** `macos-say` (Zero Setup)
**Default Cross-Platform:** `piper` mit `de_DE-thorsten-high`
**Upgrade-Pfad:** Piper → Kokoro → ElevenLabs

### 4.5 Wake Word: Zwei Strategien

Der Prototyp hat einen **kreativen Ansatz**: Kein separater Wake Word Detector, sondern Whisper transkribiert alles und eine Varianten-Liste erkennt "Jarvis". Das ist simpel, aber CPU-intensiver als ein dedizierter Detector.

| Engine | Beschreibung | CPU | Genauigkeit | Custom Words |
|---|---|---|---|---|
| `whisper-wake` | Whisper + Varianten (aktuell) | Hoch | Gut (mit 26 Varianten) | Einfach (Liste erweitern) |
| `openwakeword` | Dedizierter Detector | Minimal | Sehr gut | Training nötig (~1h) |
| `porcupine` | Picovoice Porcupine | Minimal | Exzellent | Picovoice Console |

**Default:** `whisper-wake` (aus dem Prototyp, funktioniert, keine Extra-Dependency)
**Empfehlung für Community:** `openwakeword` als Alternative anbieten

### 4.6 Packaging

| Plattform | Phase 1 | Phase 2 |
|---|---|---|
| macOS | PyPI + `start.sh` | Homebrew Cask + DMG |
| Linux | PyPI | AppImage + .deb |
| Windows | PyPI | MSI via Tauri |
| Universal | `pip install jarvis-voice` | Docker Image |

---

## 5. MVP Scope (v0.1)

### Basiert auf dem Prototyp — nicht bei Null

Das MVP baut direkt auf dem funktionierenden Prototyp auf. Der Voice-Zyklus existiert bereits. Der Fokus liegt auf dem **Agent SDK Upgrade** und der **Modularisierung**.

### Must-Have

1. **Agent SDK statt `messages.create()`** — Der zentrale Wechsel. `ClaudeSDKClient` für Session-Konversation mit Tool-Zugriff.
2. **MCP-Server Loading** — `.mcp.json` wird geladen, Tools via `allowed_tools` freigeschaltet. Datto RMM und Filesystem als Proof of Concept.
3. **Permission Layer** — `disallowed_tools` für schreibende MCP-Aktionen (übernommen aus `BLOCKED_TOOLS`). Optional: Voice-Bestätigung via Hook.
4. **CLAUDE.md Support** — System Prompt als Datei statt hardcoded String. Skills-Ordner vorbereitet.
5. **Pluggable Pipeline** — STT, TTS, Wake Word als austauschbare Interfaces mit Default-Implementierungen (aktueller Stack als Default).
6. **CLI Interface** — `jarvis listen` (Voice Pipeline), `jarvis query "..."` (Text-Modus), `jarvis config` (Setup).
7. **Saubere Repo-Struktur** — pyproject.toml, src-Layout, Tests, CI/CD.
8. **README + Quickstart** — Von `pip install` zum funktionierenden Voice Agent in 5 Minuten.

### Übernommen aus Prototyp (bereits fertig)

- RealtimeSTT + faster-whisper Pipeline
- Session-Modus (Aktivierung/Deaktivierung)
- Feedback-Loop-Schutz (Mic-Mute)
- macOS Menu Bar App (als optionales UI-Modul)
- Whisper-Varianten Wake Word Detection
- Auto-Recovery bei Recorder-Crash
- JSON/YAML Config

### Explizit NICHT im MVP

- Tauri Desktop App
- Multi-User Support
- Streaming STT
- Plugin Marketplace
- Voice Cloning

---

## 6. Roadmap

### Phase 1: Agent SDK Migration (2-3 Wochen)

Aufgabe: Den bestehenden Prototyp auf Agent SDK umstellen und modularisieren.

- `messages.create()` → `ClaudeSDKClient` mit Session-Support
- `.mcp.json` Loading + `allowed_tools` / `disallowed_tools`
- CLAUDE.md als externe System Prompt Datei
- Voice Pipeline als Interface (STT/TTS/WakeWord austauschbar)
- CLI: `jarvis listen`, `jarvis query`, `jarvis config`
- pyproject.toml + Tests + GitHub Actions CI
- PyPI Release (`pip install jarvis-voice`)
- README, Quickstart, LICENSE (MIT)

### Phase 2: Stabilisierung + Features (3-4 Wochen)

- Structured Output Router (Sprache vs. UI-Update vs. Aktion)
- Hooks für Logging, Cost Tracking, Voice-Confirmation
- Subagent-Support (z.B. "recherchiere im Hintergrund")
- Piper TTS Integration als Cross-Platform Default
- openWakeWord als Alternative zum Whisper-Wake Ansatz
- Conversation History mit Session-Resume
- macOS Menu Bar App als `jarvis[macos]` Optional-Dependency
- Homebrew Tap für macOS

### Phase 3: Cross-Platform Desktop (4-6 Wochen)

- Tauri 2.x Shell (Svelte Frontend)
- Waveform-Visualisierung
- Settings UI (MCP-Server, Modelle, Wake Word)
- System Tray (macOS, Linux, Windows)
- AppImage für Linux
- Docker Image für Headless/Server Deployment

### Phase 4: Community & Ecosystem (Ongoing)

- Skills Repository (`jarvis-skills`)
- Community Wake Words Repository
- Custom TTS Voice Training Guide
- Home Assistant Add-on
- Plugin Marketplace (GitHub-basiert)
- Comprehensive Documentation Site
- Discord Server + monatlicher Community Call

---

## 7. Repository-Struktur

```
jarvis/
├── README.md
├── LICENSE                        # MIT
├── CONTRIBUTING.md
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── pyproject.toml                 # Python Package Config
│
├── src/
│   └── jarvis/                    # Python Package
│       ├── __init__.py
│       ├── __main__.py            # CLI Entry Point
│       ├── cli.py                 # Typer CLI (listen, query, config)
│       ├── config.py              # Config Loading (YAML + JSON Compat)
│       │
│       ├── pipeline/              # Voice Pipeline
│       │   ├── __init__.py
│       │   ├── base.py            # Abstract Interfaces (STT, TTS, WakeWord)
│       │   ├── orchestrator.py    # Pipeline Orchestrator
│       │   ├── audio.py           # Audio I/O (PyAudio/sounddevice)
│       │   ├── vad.py             # Voice Activity Detection (Silero)
│       │   ├── feedback_guard.py  # Mic-Mute + Queue-Clear (aus v3)
│       │   │
│       │   ├── stt/               # STT Engines
│       │   │   ├── __init__.py
│       │   │   ├── realtimestt.py # RealtimeSTT (Default, aus v3)
│       │   │   ├── faster_whisper.py
│       │   │   └── cloud.py       # Google/Azure Cloud STT
│       │   │
│       │   ├── tts/               # TTS Engines
│       │   │   ├── __init__.py
│       │   │   ├── macos_say.py   # macOS say (Default macOS, aus v3)
│       │   │   ├── piper.py       # Piper TTS (Default Cross-Platform)
│       │   │   └── cloud.py       # ElevenLabs etc.
│       │   │
│       │   └── wake/              # Wake Word Engines
│       │       ├── __init__.py
│       │       ├── whisper_wake.py # Whisper + Varianten (aus v3)
│       │       └── openwakeword.py
│       │
│       ├── agent/                 # Agent SDK Integration
│       │   ├── __init__.py
│       │   ├── core.py            # ClaudeSDKClient Wrapper
│       │   ├── session.py         # Session Management
│       │   ├── hooks.py           # Voice-spezifische Hooks
│       │   ├── permissions.py     # Permission Handler + Blocked Tools
│       │   └── response.py        # Response Router (Text/JSON/Action)
│       │
│       ├── mcp/                   # MCP Server Management
│       │   ├── __init__.py
│       │   ├── loader.py          # .mcp.json Loader
│       │   └── builtin/           # Built-in Custom Tools
│       │       ├── __init__.py
│       │       └── system_info.py
│       │
│       ├── ui/                    # UI Modules (optional)
│       │   ├── __init__.py
│       │   ├── macos_menubar.py   # rumps + Cocoa (aus v3, refactored)
│       │   └── terminal.py        # rich/textual Terminal UI
│       │
│       └── utils/
│           ├── __init__.py
│           ├── logging.py         # Structured Logging
│           ├── audio_utils.py     # Audio Processing
│           ├── text_cleaner.py    # Markdown → Speech (aus v3)
│           └── cost_tracker.py    # API Cost Tracking
│
├── skills/                        # Default Skills
│   ├── general/SKILL.md
│   ├── smart-home/SKILL.md
│   ├── msp-monitoring/SKILL.md
│   └── coding/SKILL.md
│
├── config/                        # Default Configs
│   ├── jarvis.default.yaml
│   ├── CLAUDE.md.example
│   └── .mcp.json.example
│
├── app/                           # Tauri Desktop App (Phase 3)
│   ├── src-tauri/
│   └── src/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   ├── architecture.md
│   ├── quickstart.md
│   ├── configuration.md
│   ├── migration-from-v3.md       # Guide für Prototyp-Migration
│   ├── creating-skills.md
│   └── creating-mcp-plugins.md
│
├── scripts/
│   ├── setup.sh
│   ├── download-models.sh
│   └── migrate-from-v3.py         # Migriert Config aus Prototyp
│
└── .github/
    ├── workflows/
    │   ├── ci.yml
    │   ├── release.yml
    │   └── build-desktop.yml
    ├── ISSUE_TEMPLATE/
    └── PULL_REQUEST_TEMPLATE.md
```

---

## 8. Vergleich: Prototyp v3 → Jarvis Framework

| Aspekt | Prototyp v3 (jarvis_app.py) | Jarvis Framework |
|---|---|---|
| **LLM Integration** | `anthropic.Anthropic.messages.create()` | `claude_agent_sdk.ClaudeSDKClient` |
| **Tool-Zugriff** | Keiner (nur Chat) | Voller Agent-Loop mit Built-in + MCP Tools |
| **MCP-Server** | Nur konzipiert (claude_bridge.py) | Nativ via `.mcp.json` + `allowed_tools` |
| **Permissions** | BLOCKED_TOOLS Liste (nicht integriert) | `disallowed_tools` + `can_use_tool` Callback |
| **Session-Management** | 16 Messages Array, geht bei "Danke" verloren | Session-IDs, Resume, Fork, persistent |
| **Wake Word** | Whisper-Varianten (26 Strings) | Pluggable: `whisper-wake` + `openwakeword` |
| **STT** | RealtimeSTT + faster-whisper base | Pluggable: multiple Engines, konfigurierbar |
| **TTS** | macOS `say` (Siri Stimme) | Pluggable: `macos-say` + `piper` + Cloud |
| **UI** | rumps Menu Bar + Cocoa NSWindow | CLI + macOS Native + Tauri (Phase 3) |
| **Config** | JSON, 7 Parameter | YAML, 30+ Parameter, CLAUDE.md, Skills |
| **Error Handling** | while-Loop + 2s sleep | Hooks, Health Checks, Structured Errors |
| **Subagents** | Nicht möglich | `AgentDefinition` für spezialisierte Tasks |
| **Structured Output** | Nicht möglich | JSON-Schema validiert (speak/confirm/display) |
| **Cost Tracking** | Nicht vorhanden | `total_cost_usd` pro Interaktion |
| **Cross-Platform** | Nur macOS | macOS + Linux + Windows |
| **Community** | Privat | Open Source MIT, Contributing Guidelines |

---

## 9. Community & Open Source

### Lizenz

**MIT License** — maximal permissiv, konsistent mit dem MCP-Ökosystem.

### Was das Projekt einzigartig macht

1. **Erster Open-Source Voice Agent auf Claude Agent SDK.** Kein Voice-Wrapper für OpenAI, sondern ein vollwertiger Agent-Stack mit MCP-Integration — direkt die Claude Code Engine per Stimme nutzen.

2. **MCP als Universal-Plugin-System.** Kein proprietäres Plugin-Format — hunderte existierende MCP-Server (GitHub, Slack, Postgres, Home Assistant, Datto RMM etc.) funktionieren out-of-the-box.

3. **Privacy-First.** Wake Word, STT und TTS laufen lokal. Nur der LLM-Call verlässt das Gerät. Enterprise: Bedrock/Vertex für Datenresidenz.

4. **Battle-Tested Voice Pipeline.** Nicht theoretisch — basiert auf einem produktiv laufenden Prototyp mit gelösten Problemen (Feedback-Loop, Whisper-Varianten, Auto-Recovery, Mic-Permissions).

5. **Modular und austauschbar.** Jede Komponente ist ein Interface. Community kann STT, TTS, Wake Word Implementierungen beisteuern.

### Contributing Guidelines

- **Code Style:** Ruff, Type Hints, Docstrings
- **Branching:** `main` → stable, `develop` → next, `feat/xxx` → Features
- **Skills/Plugins:** Eigener Contribution-Pfad via `jarvis-skills` Repository

### Community-Aufbau

- GitHub Discussions
- Discord Server
- Awesome Jarvis Liste (Skills, MCP-Server, Wake Words)

---

## 10. Konfigurationsbeispiel

```yaml
# jarvis.yaml — Vollständige Konfiguration
version: "1.0"

# Voice Pipeline
wake_word:
  engine: whisper-wake           # whisper-wake | openwakeword | porcupine
  variants:                       # Nur für whisper-wake
    - jarvis
    - dschawis
    - jervis
    # ... (26 Varianten aus Prototyp)

stt:
  engine: realtimestt            # realtimestt | faster-whisper | whisper-cpp | cloud
  model: base                    # tiny | base | small | medium | large-v3-turbo
  language: de
  compute_type: int8
  initial_prompt: "Jarvis"       # Hilft Whisper bei der Erkennung

tts:
  engine: macos-say              # macos-say | piper | kokoro | elevenlabs
  rate: 200                      # Wörter pro Minute (nur macos-say)
  voice: null                    # null = System-Default
  # piper_voice: de_DE-thorsten-high  # Nur für piper
  # elevenlabs_voice_id: "..."        # Nur für elevenlabs

vad:
  engine: silero
  sensitivity: 0.4
  post_speech_silence: 0.8       # Sekunden Stille bis Aufnahme endet
  min_recording_length: 0.2

session:
  wake_word: "jarvis"            # Aktivierungswort
  stop_word: "danke"             # Deaktivierungswort
  exit_phrase: "jarvis beenden"  # Programm beenden
  max_history: 16                # Messages in einer Session

# Agent SDK
agent:
  api_key_env: ANTHROPIC_API_KEY
  model: claude-sonnet-4-6       # sonnet | opus | haiku
  max_turns: 20
  max_budget_usd: 0.50
  permission_mode: acceptEdits
  thinking:
    type: adaptive

# MCP Server (oder via .mcp.json)
mcp_servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "~"]
  datto-rmm:
    command: npx
    args: ["-y", "@logiphys/datto-rmm-mcp"]

# Permissions
allowed_tools:
  - "Read"
  - "Glob"
  - "Grep"
  - "WebSearch"
  - "mcp__datto-rmm__list-*"
  - "mcp__datto-rmm__get-*"
  - "mcp__filesystem__*"

disallowed_tools:
  - "mcp__datto-rmm__create-*"
  - "mcp__datto-rmm__delete-*"
  - "mcp__datto-rmm__update-*"
  - "mcp__datto-rmm__move-*"

# Audio
audio:
  input_device: default
  output_device: default
  sample_rate: 16000

# UI
ui:
  mode: menubar                  # menubar | cli | tauri
  show_log_window: true          # Nur für menubar

# Feedback Sounds
sounds:
  session_start: /System/Library/Sounds/Tink.aiff
  session_end: /System/Library/Sounds/Blow.aiff

# Logging
logging:
  level: INFO
  file: ~/.jarvis/logs/jarvis.log
  cost_tracking: true
```

---

## 11. Nächste Schritte

1. **GitHub Repository anlegen** — `logiphys/jarvis`, MIT License, README mit Vision
2. **Prototyp-Code refactoren** — jarvis.py + jarvis_app.py in src-Layout mit Interfaces
3. **Agent SDK Integration** — `messages.create()` durch `ClaudeSDKClient` ersetzen
4. **MCP-Server anbinden** — `.mcp.json` mit Datto RMM als erster Test
5. **Permission Layer** — `BLOCKED_TOOLS` → `disallowed_tools` + Voice-Confirm Hook
6. **CLI bauen** — `jarvis listen` als Universal-Einstiegspunkt
7. **Tests + CI** — GitHub Actions, Ruff, pytest
8. **Erster Release** — v0.1.0-alpha auf PyPI

---

*Jarvis — Give Claude a Voice.*
