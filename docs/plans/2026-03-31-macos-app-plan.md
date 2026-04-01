# Jarvis macOS Menu Bar App — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a native macOS Menu Bar App that wraps `VoicePipeline` — double-click to start, no Terminal needed, with live log window, full settings menu, Keychain API key storage, and optional autostart.

**Architecture:** `JarvisMenuBarApp(rumps.App)` owns the Main Thread (Cocoa/rumps). `VoicePipeline` runs in a background `threading.Thread` with its own `asyncio` event loop. State changes flow back to the menu bar icon via a thread-safe callback. Log lines flow via `queue.Queue` + `rumps.Timer` polling into a Cocoa `NSWindow`.

**Tech Stack:** Python 3.12, rumps, PyObjC (AppKit/Foundation), py2app, `security` CLI for Keychain, `launchctl` for LaunchAgent

**Design doc:** `docs/plans/2026-03-31-macos-app-design.md`

---

### Task 1: Add `state_callback` to VoicePipeline + `save()` to JarvisConfig

The app needs to react to state changes and persist config edits from the GUI.

**Files:**
- Modify: `src/jarvis/pipeline/orchestrator.py`
- Modify: `src/jarvis/config.py`
- Test: `tests/test_orchestrator.py` (add 1 test)
- Test: `tests/test_config.py` (add 1 test)

**Step 1: Write failing tests**

Add to `tests/test_orchestrator.py`:
```python
def test_state_callback_called_on_transition(mock_components):
    """state_callback should be called whenever state changes."""
    stt, tts, wake, agent, config = mock_components
    states_seen = []
    pipeline = VoicePipeline(
        stt=stt, tts=tts, wake=wake, agent=agent, config=config,
        state_callback=lambda s: states_seen.append(s),
    )
    wake.check_transcription.return_value = ""
    pipeline._on_transcription("Jarvis")
    assert PipelineState.LISTENING in states_seen
```

Add to `tests/test_config.py`:
```python
def test_config_save(tmp_path):
    """save() should write config to YAML file."""
    cfg = JarvisConfig()
    cfg.session.wake_word = "hey jarvis"
    out = tmp_path / "jarvis.yaml"
    cfg.save(out)
    assert out.exists()
    loaded = JarvisConfig.load(out)
    assert loaded.session.wake_word == "hey jarvis"
```

**Step 2: Run to verify FAIL**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/test_orchestrator.py::test_state_callback_called_on_transition tests/test_config.py::test_config_save -v
```
Expected: 2 FAILs

**Step 3: Add `state_callback` to VoicePipeline**

In `src/jarvis/pipeline/orchestrator.py`, update `__init__` signature:
```python
from collections.abc import Callable

def __init__(
    self,
    stt: STTEngine,
    tts: TTSEngine,
    wake: WakeWordEngine,
    agent: JarvisAgent,
    config: JarvisConfig,
    state_callback: Callable[[PipelineState], None] | None = None,
) -> None:
    self.stt = stt
    self.tts = tts
    self.wake = wake
    self.agent = agent
    self.config = config
    self.state_callback = state_callback
    self._state = PipelineState.IDLE
```

Replace `self.state = ...` throughout with a property that fires the callback:
```python
@property
def state(self) -> PipelineState:
    return self._state

@state.setter
def state(self, value: PipelineState) -> None:
    self._state = value
    if self.state_callback:
        try:
            self.state_callback(value)
        except Exception as e:
            log.warning(f"state_callback error: {e}")
```

**Step 4: Add `save()` to JarvisConfig**

In `src/jarvis/config.py`, add this method to `JarvisConfig`:
```python
def save(self, path: Path | None = None) -> None:
    """Write current config to YAML file."""
    target = path or DEFAULT_CONFIG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "wake_word": {"engine": self.wake_word.engine, "variants": self.wake_word.variants},
        "stt": {"engine": self.stt.engine, "model": self.stt.model,
                "language": self.stt.language, "compute_type": self.stt.compute_type,
                "initial_prompt": self.stt.initial_prompt},
        "tts": {"engine": self.tts.engine, "rate": self.tts.rate,
                "voice": self.tts.voice, "piper_voice": self.tts.piper_voice},
        "vad": {"sensitivity": self.vad.sensitivity,
                "post_speech_silence": self.vad.post_speech_silence,
                "min_recording_length": self.vad.min_recording_length},
        "session": {"wake_word": self.session.wake_word, "stop_word": self.session.stop_word,
                    "exit_phrase": self.session.exit_phrase, "max_history": self.session.max_history},
        "agent": {"api_key_env": self.agent.api_key_env, "model": self.agent.model,
                  "max_turns": self.agent.max_turns, "max_budget_usd": self.agent.max_budget_usd,
                  "permission_mode": self.agent.permission_mode},
        "audio": {"input_device": self.audio.input_device, "output_device": self.audio.output_device,
                  "sample_rate": self.audio.sample_rate},
        "logging": {"level": self.logging.level, "file": self.logging.file,
                    "cost_tracking": self.logging.cost_tracking},
    }
    with open(target, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
```

**Step 5: Run to verify PASS**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/test_orchestrator.py::test_state_callback_called_on_transition tests/test_config.py::test_config_save -v
```
Expected: 2 PASS

**Step 6: Run full suite**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/ -q
```
Expected: 29 passed

**Step 7: Commit**
```bash
cd /Users/zeisler/jarvis && git add src/jarvis/pipeline/orchestrator.py src/jarvis/config.py tests/test_orchestrator.py tests/test_config.py
git commit -m "feat: add state_callback to VoicePipeline and save() to JarvisConfig"
```

---

### Task 2: Keychain helper

A small utility to store/retrieve/check the API key via macOS Keychain.

**Files:**
- Create: `src/jarvis/utils/keychain.py`
- Test: `tests/test_keychain.py`

**Step 1: Write failing test**

Create `tests/test_keychain.py`:
```python
"""Tests for macOS Keychain helper."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from jarvis.utils.keychain import set_api_key, get_api_key, has_api_key


def test_set_api_key_calls_security():
    """set_api_key should call 'security add-generic-password'."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        set_api_key("sk-test-key")
        cmd = mock_run.call_args[0][0]
        assert "security" in cmd
        assert "add-generic-password" in cmd
        assert "sk-test-key" in cmd


def test_get_api_key_returns_stripped_output():
    """get_api_key should return stripped stdout from security command."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="sk-test-key\n")
        result = get_api_key()
        assert result == "sk-test-key"


def test_get_api_key_returns_none_on_error():
    """get_api_key should return None if key not found."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=44, stdout="")
        result = get_api_key()
        assert result is None


def test_has_api_key_true():
    """has_api_key should return True when key exists."""
    with patch("jarvis.utils.keychain.get_api_key", return_value="sk-key"):
        assert has_api_key() is True


def test_has_api_key_false():
    """has_api_key should return False when key missing."""
    with patch("jarvis.utils.keychain.get_api_key", return_value=None):
        assert has_api_key() is False
```

**Step 2: Run to verify FAIL**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/test_keychain.py -v
```
Expected: ImportError

**Step 3: Create `src/jarvis/utils/keychain.py`**
```python
"""macOS Keychain integration for secure API key storage.

Uses the 'security' CLI tool to store/retrieve the Anthropic API key
in the macOS Keychain — never written to disk or environment files.
"""
from __future__ import annotations

import subprocess
import logging

log = logging.getLogger("jarvis")

_SERVICE = "jarvis-voice"
_ACCOUNT = "anthropic-api-key"


def set_api_key(api_key: str) -> bool:
    """Store API key in macOS Keychain. Overwrites existing entry."""
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", _SERVICE, "-a", _ACCOUNT,
         "-w", api_key, "-U"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        log.info("API key saved to Keychain")
        return True
    log.warning(f"Failed to save API key: {result.stderr.strip()}")
    return False


def get_api_key() -> str | None:
    """Retrieve API key from macOS Keychain. Returns None if not found."""
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", _SERVICE, "-a", _ACCOUNT, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def has_api_key() -> bool:
    """Check whether an API key is stored in the Keychain."""
    return get_api_key() is not None
```

Update `src/jarvis/utils/__init__.py` to export:
```python
"""Jarvis utilities."""
from __future__ import annotations
```
(leave it minimal — keychain is imported directly where needed)

**Step 4: Run to verify PASS**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/test_keychain.py -v
```
Expected: 5 PASS

**Step 5: Commit**
```bash
cd /Users/zeisler/jarvis && git add src/jarvis/utils/keychain.py tests/test_keychain.py
git commit -m "feat: add macOS Keychain helper for API key storage"
```

---

### Task 3: LogWindow (Cocoa NSWindow)

Thread-safe live log window with colored output by log type.

**Files:**
- Create: `src/jarvis/ui/log_window.py`
- No automated test (Cocoa UI — test manually)

**Step 1: Create `src/jarvis/ui/log_window.py`**

```python
"""Cocoa NSWindow log viewer — thread-safe colored live log.

Uses a queue.Queue for thread safety: background threads call enqueue(),
the Main Thread polls via flush() (called from a rumps.Timer every 100ms).
"""
from __future__ import annotations

import logging
import queue

log = logging.getLogger("jarvis")

# Color map: log category → (R, G, B)
_COLORS = {
    "stt":     (0.4, 0.8, 1.0),   # light blue
    "jarvis":  (0.4, 1.0, 0.4),   # green
    "session": (1.0, 0.85, 0.2),  # yellow
    "error":   (1.0, 0.3, 0.3),   # red
    "system":  (0.7, 0.5, 1.0),   # purple
    "default": (0.75, 0.75, 0.75),# grey
    "time":    (0.5, 0.5, 0.5),   # dark grey
}
_EMOJIS = {
    "stt": "🎙", "jarvis": "🤖", "session": "●",
    "error": "❌", "system": "⚙️", "default": "  ",
}
_BG = (0.1, 0.1, 0.12)
_MAX_LINES = 500


def _classify(text: str) -> str:
    t = text.lower()
    if "stt:" in t:        return "stt"
    if "jarvis:" in t:     return "jarvis"
    if "session" in t:     return "session"
    if "error" in t or "fehler" in t: return "error"
    if "recorder" in t or "pipeline" in t: return "system"
    return "default"


class LogWindow:
    """Native macOS log window. Call enqueue() from any thread, flush() from Main Thread."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._window = None
        self._text_view = None
        self._font = None
        self._color_cache: dict = {}

    def _nscolor(self, rgb: tuple) -> object:
        if rgb not in self._color_cache:
            from AppKit import NSColor
            self._color_cache[rgb] = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                rgb[0], rgb[1], rgb[2], 1.0
            )
        return self._color_cache[rgb]

    def create(self) -> None:
        """Create and show the window. Must be called from Main Thread."""
        if self._window is not None:
            self._window.makeKeyAndOrderFront_(None)
            return

        from AppKit import (
            NSWindow, NSTextView, NSScrollView, NSFont, NSColor,
            NSMakeRect, NSBackingStoreBuffered,
            NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
            NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
            NSBezelBorder, NSWindowCollectionBehaviorCanJoinAllSpaces,
        )

        bg = self._nscolor(_BG)
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskResizable | NSWindowStyleMaskMiniaturizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(100, 200, 720, 480), style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("Jarvis — Log")
        self._window.setMinSize_((400, 200))
        self._window.setLevel_(3)
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
        self._window.setBackgroundColor_(bg)
        self._window.setReleasedWhenClosed_(False)

        content = self._window.contentView()
        frame = content.bounds()

        scroll = NSScrollView.alloc().initWithFrame_(frame)
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(False)
        scroll.setAutoresizingMask_(0x12)
        scroll.setBorderType_(NSBezelBorder)
        scroll.setBackgroundColor_(bg)

        self._text_view = NSTextView.alloc().initWithFrame_(frame)
        self._text_view.setEditable_(False)
        self._text_view.setSelectable_(True)
        self._text_view.setRichText_(True)
        self._text_view.setBackgroundColor_(bg)
        self._text_view.setTextContainerInset_((8, 8))
        self._text_view.setAutoresizingMask_(0x12)

        self._font = NSFont.fontWithName_size_("Menlo", 12)
        if not self._font:
            self._font = NSFont.monospacedSystemFontOfSize_weight_(12, 0)
        self._text_view.setFont_(self._font)
        scroll.setDocumentView_(self._text_view)
        content.addSubview_(scroll)
        self._window.makeKeyAndOrderFront_(None)

    def close(self) -> None:
        if self._window:
            self._window.orderOut_(None)

    def enqueue(self, text: str) -> None:
        """Thread-safe: add a log line to the display queue."""
        self._queue.put(text)

    def flush(self) -> None:
        """Drain queue into NSTextView. Must be called from Main Thread."""
        if not self._text_view:
            while not self._queue.empty():
                try: self._queue.get_nowait()
                except queue.Empty: break
            return

        count = 0
        while not self._queue.empty() and count < 50:
            try:
                text = self._queue.get_nowait()
                self._append(text)
                count += 1
            except queue.Empty:
                break

    def _append(self, text: str) -> None:
        from AppKit import NSAttributedString, NSForegroundColorAttributeName, NSFontAttributeName
        from Foundation import NSMutableAttributedString, NSDictionary

        category = _classify(text)
        color = self._nscolor(_COLORS.get(category, _COLORS["default"]))
        time_color = self._nscolor(_COLORS["time"])
        emoji = _EMOJIS.get(category, "  ")

        full = NSMutableAttributedString.alloc().init()

        parts = text.split("] ", 1)
        if len(parts) == 2:
            time_part, msg_part = parts[0] + "] ", parts[1]
        else:
            time_part, msg_part = "", text

        def _attr_str(s: str, clr: object) -> object:
            attrs = NSDictionary.dictionaryWithObjects_forKeys_(
                [clr, self._font],
                [NSForegroundColorAttributeName, NSFontAttributeName],
            )
            return NSAttributedString.alloc().initWithString_attributes_(s, attrs)

        if time_part:
            full.appendAttributedString_(_attr_str(time_part, time_color))
        full.appendAttributedString_(_attr_str(f"{emoji} {msg_part}\n", color))

        storage = self._text_view.textStorage()
        storage.appendAttributedString_(full)
        self._text_view.scrollRangeToVisible_((storage.length(), 0))

        # Trim to _MAX_LINES
        text_str = storage.string()
        lines = text_str.split("\n")
        if len(lines) > _MAX_LINES:
            cut = 0
            for _ in range(100):
                idx = text_str.find("\n", cut)
                if idx == -1: break
                cut = idx + 1
            if cut > 0:
                storage.deleteCharactersInRange_((0, cut))


class WindowLogHandler(logging.Handler):
    """Logging handler that forwards records to LogWindow.enqueue()."""

    def __init__(self, log_window: LogWindow) -> None:
        super().__init__()
        self.log_window = log_window
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_window.enqueue(self.format(record))
        except Exception:
            pass
```

**Step 2: Verify import works (no Cocoa crash)**
```bash
cd /Users/zeisler/jarvis && python3.12 -c "from jarvis.ui.log_window import LogWindow, WindowLogHandler; print('LogWindow import OK')"
```
Expected: `LogWindow import OK`

**Step 3: Commit**
```bash
cd /Users/zeisler/jarvis && git add src/jarvis/ui/log_window.py
git commit -m "feat: add Cocoa LogWindow with thread-safe queue and colored log lines"
```

---

### Task 4: JarvisMenuBarApp (main app)

The rumps Menu Bar App that wires everything together.

**Files:**
- Create: `src/jarvis/ui/macos_app.py`
- Modify: `src/jarvis/ui/__init__.py`

**Step 1: Create `src/jarvis/ui/macos_app.py`**

```python
"""Jarvis macOS Menu Bar App.

Entry point for the .app bundle. Runs VoicePipeline in a background thread,
updates the menu bar icon on state changes, and provides a full settings menu.

Usage:
    python3.12 -m jarvis.ui.macos_app
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
from pathlib import Path

import rumps

from jarvis.config import JarvisConfig, DEFAULT_CONFIG_FILE
from jarvis.pipeline.orchestrator import PipelineState, VoicePipeline
from jarvis.ui.log_window import LogWindow, WindowLogHandler
from jarvis.utils.keychain import get_api_key, set_api_key, has_api_key

log = logging.getLogger("jarvis")

# State → Menu Bar emoji
STATE_ICONS: dict[PipelineState, str] = {
    PipelineState.IDLE:       "🎙",
    PipelineState.LISTENING:  "🟢",
    PipelineState.PROCESSING: "🟢",
    PipelineState.SPEAKING:   "🔵",
}
ERROR_ICON = "🔴"

WHISPER_MODELS = ["tiny", "base", "small"]
CLAUDE_MODELS = {
    "claude-haiku-4-5":  "Haiku (schnell)",
    "claude-sonnet-4-6": "Sonnet (empfohlen)",
    "claude-opus-4-0":   "Opus (leistungsstark)",
}
LANGUAGES = {"de": "Deutsch", "en": "English", "fr": "Français", "es": "Español"}


class JarvisMenuBarApp(rumps.App):
    """Jarvis Menu Bar App — wraps VoicePipeline with full macOS UI."""

    def __init__(self) -> None:
        super().__init__("🎙", quit_button=None)
        self.cfg = JarvisConfig.load()
        self._log_window = LogWindow()
        self._pipeline_thread: threading.Thread | None = None
        self._pipeline: VoicePipeline | None = None
        self._setup_logging()
        self._build_menu()

    # ── Logging ────────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        handler = WindowLogHandler(self._log_window)
        root.addHandler(handler)
        logging.getLogger("RealtimeSTT").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    # ── Menu ───────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        """Build the full menu structure."""
        self.menu.clear()

        # Status (non-clickable)
        self._status_item = rumps.MenuItem("Wartet auf Start...")
        self._status_item.set_callback(None)

        self.menu = [
            self._status_item,
            None,
            rumps.MenuItem("📋 Log anzeigen", callback=self._show_log),
            None,
            self._build_settings_menu(),
            None,
            rumps.MenuItem(self._autostart_label(), callback=self._toggle_autostart),
            None,
            rumps.MenuItem("⏹ Beenden", callback=self._quit),
        ]

        # Start pipeline immediately
        self._start_pipeline()
        # Poll log queue every 100ms
        rumps.Timer(self._flush_log, 0.1).start()

    def _build_settings_menu(self) -> rumps.MenuItem:
        settings = rumps.MenuItem("⚙️ Einstellungen")

        # API Key
        settings["🔑 API Key setzen..."] = rumps.MenuItem(
            "🔑 API Key setzen...", callback=self._set_api_key
        )
        settings.update({None: None})

        # Wake/Stop/Exit words
        settings[f"Wake Word: {self.cfg.session.wake_word}"] = rumps.MenuItem(
            f"Wake Word: {self.cfg.session.wake_word}", callback=self._set_wake_word
        )
        settings[f"Stop Word: {self.cfg.session.stop_word}"] = rumps.MenuItem(
            f"Stop Word: {self.cfg.session.stop_word}", callback=self._set_stop_word
        )
        settings[f"Exit-Phrase: {self.cfg.session.exit_phrase}"] = rumps.MenuItem(
            f"Exit-Phrase: {self.cfg.session.exit_phrase}", callback=self._set_exit_phrase
        )
        settings.update({None: None})

        # Whisper model submenu
        whisper_menu = rumps.MenuItem(f"Whisper: {self.cfg.stt.model}")
        for m in WHISPER_MODELS:
            item = rumps.MenuItem(f"{'✓ ' if m == self.cfg.stt.model else '  '}{m}",
                                  callback=self._set_whisper_model)
            item.title = f"{'✓ ' if m == self.cfg.stt.model else '  '}{m}"
            whisper_menu[m] = item
        settings["whisper"] = whisper_menu

        # Language submenu
        lang_menu = rumps.MenuItem(f"Sprache: {self.cfg.stt.language}")
        for code, name in LANGUAGES.items():
            item = rumps.MenuItem(
                f"{'✓ ' if code == self.cfg.stt.language else '  '}{name}",
                callback=self._set_language,
            )
            lang_menu[code] = item
        settings["language"] = lang_menu

        # TTS rate
        settings[f"Sprechgeschwindigkeit: {self.cfg.tts.rate} wpm"] = rumps.MenuItem(
            f"Sprechgeschwindigkeit: {self.cfg.tts.rate} wpm", callback=self._set_tts_rate
        )
        settings.update({None: None})

        # Claude model submenu
        current_label = CLAUDE_MODELS.get(self.cfg.agent.model, self.cfg.agent.model)
        claude_menu = rumps.MenuItem(f"Claude: {current_label}")
        for model_id, label in CLAUDE_MODELS.items():
            item = rumps.MenuItem(
                f"{'✓ ' if model_id == self.cfg.agent.model else '  '}{label}",
                callback=self._set_claude_model,
            )
            claude_menu[model_id] = item
        settings["claude"] = claude_menu

        settings[f"Budget: ${self.cfg.agent.max_budget_usd:.2f}"] = rumps.MenuItem(
            f"Budget: ${self.cfg.agent.max_budget_usd:.2f}", callback=self._set_budget
        )
        settings[f"Max. Runden: {self.cfg.agent.max_turns}"] = rumps.MenuItem(
            f"Max. Runden: {self.cfg.agent.max_turns}", callback=self._set_max_turns
        )
        cost_check = "✓ " if self.cfg.logging.cost_tracking else "  "
        settings[f"{cost_check}Kosten-Tracking"] = rumps.MenuItem(
            f"{cost_check}Kosten-Tracking", callback=self._toggle_cost_tracking
        )

        return settings

    # ── Pipeline ───────────────────────────────────────────────────

    def _start_pipeline(self) -> None:
        """Start VoicePipeline in background thread."""
        if not has_api_key():
            self._update_status("⚠️ API Key fehlt — bitte in Einstellungen setzen")
            self.title = ERROR_ICON
            return

        def run() -> None:
            import os
            from jarvis.agent.core import JarvisAgent
            from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine
            from jarvis.pipeline.tts.macos_say import MacOSSayEngine
            from jarvis.pipeline.wake.whisper_wake import WhisperWakeEngine

            # Inject API key from Keychain into environment
            api_key = get_api_key()
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

            stt = RealtimeSTTEngine(stt_config=self.cfg.stt, vad_config=self.cfg.vad)
            tts = MacOSSayEngine(rate=self.cfg.tts.rate, voice=self.cfg.tts.voice)
            wake = WhisperWakeEngine(self.cfg.wake_word.variants)
            agent = JarvisAgent(self.cfg)

            self._pipeline = VoicePipeline(
                stt=stt, tts=tts, wake=wake, agent=agent, config=self.cfg,
                state_callback=self._on_state_change,
            )
            try:
                asyncio.run(self._pipeline.run())
            except Exception as e:
                log.error(f"Pipeline crashed: {e}")
                self.title = ERROR_ICON

        self._pipeline_thread = threading.Thread(target=run, daemon=True, name="VoicePipeline")
        self._pipeline_thread.start()
        self._update_status(f"Wartet auf '{self.cfg.session.wake_word}'...")

    def _on_state_change(self, state: PipelineState) -> None:
        """Called from pipeline thread — update icon thread-safely."""
        self.title = STATE_ICONS.get(state, ERROR_ICON)
        labels = {
            PipelineState.IDLE:       f"Wartet auf '{self.cfg.session.wake_word}'...",
            PipelineState.LISTENING:  "🟢 Lauscht...",
            PipelineState.PROCESSING: "🧠 Denkt...",
            PipelineState.SPEAKING:   "🔵 Spricht...",
        }
        self._update_status(labels.get(state, ""))

    def _update_status(self, text: str) -> None:
        if hasattr(self, "_status_item"):
            self._status_item.title = text

    # ── Log Window ─────────────────────────────────────────────────

    def _show_log(self, _) -> None:
        self._log_window.create()

    def _flush_log(self, _) -> None:
        self._log_window.flush()

    # ── Settings Callbacks ─────────────────────────────────────────

    def _set_api_key(self, _) -> None:
        response = rumps.Window(
            message="Anthropic API Key eingeben:",
            title="🔑 API Key setzen",
            secure=True,
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            if set_api_key(response.text.strip()):
                rumps.alert("API Key gespeichert", "Key wurde sicher im Keychain hinterlegt.")
                if not self._pipeline_thread or not self._pipeline_thread.is_alive():
                    self._start_pipeline()

    def _set_wake_word(self, _) -> None:
        response = rumps.Window(
            message="Wake Word eingeben:",
            title="Wake Word",
            default_text=self.cfg.session.wake_word,
            ok="Speichern", cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            self.cfg.session.wake_word = response.text.strip().lower()
            self.cfg.save()
            self._rebuild_menu_labels()

    def _set_stop_word(self, _) -> None:
        response = rumps.Window(
            message="Stop Word eingeben:",
            title="Stop Word",
            default_text=self.cfg.session.stop_word,
            ok="Speichern", cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            self.cfg.session.stop_word = response.text.strip().lower()
            self.cfg.save()
            self._rebuild_menu_labels()

    def _set_exit_phrase(self, _) -> None:
        response = rumps.Window(
            message="Exit-Phrase eingeben:",
            title="Exit-Phrase",
            default_text=self.cfg.session.exit_phrase,
            ok="Speichern", cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            self.cfg.session.exit_phrase = response.text.strip().lower()
            self.cfg.save()
            self._rebuild_menu_labels()

    def _set_whisper_model(self, sender) -> None:
        model = sender.title.strip().lstrip("✓").strip()
        self.cfg.stt.model = model
        self.cfg.save()
        self._rebuild_menu_labels()

    def _set_language(self, sender) -> None:
        code = [k for k, v in LANGUAGES.items() if v in sender.title]
        if code:
            self.cfg.stt.language = code[0]
            self.cfg.save()

    def _set_tts_rate(self, _) -> None:
        response = rumps.Window(
            message="Sprechgeschwindigkeit (100–300 wpm):",
            title="Sprechgeschwindigkeit",
            default_text=str(self.cfg.tts.rate),
            ok="Speichern", cancel="Abbrechen",
        ).run()
        if response.clicked:
            try:
                rate = int(response.text.strip())
                self.cfg.tts.rate = max(100, min(300, rate))
                self.cfg.save()
                self._rebuild_menu_labels()
            except ValueError:
                pass

    def _set_claude_model(self, sender) -> None:
        for model_id, label in CLAUDE_MODELS.items():
            if label in sender.title:
                self.cfg.agent.model = model_id
                self.cfg.save()
                break

    def _set_budget(self, _) -> None:
        response = rumps.Window(
            message="Budget-Limit in USD (z.B. 0.50):",
            title="Budget-Limit",
            default_text=str(self.cfg.agent.max_budget_usd),
            ok="Speichern", cancel="Abbrechen",
        ).run()
        if response.clicked:
            try:
                self.cfg.agent.max_budget_usd = float(response.text.strip())
                self.cfg.save()
                self._rebuild_menu_labels()
            except ValueError:
                pass

    def _set_max_turns(self, _) -> None:
        response = rumps.Window(
            message="Maximale Gesprächsrunden (1–50):",
            title="Max. Runden",
            default_text=str(self.cfg.agent.max_turns),
            ok="Speichern", cancel="Abbrechen",
        ).run()
        if response.clicked:
            try:
                turns = int(response.text.strip())
                self.cfg.agent.max_turns = max(1, min(50, turns))
                self.cfg.save()
                self._rebuild_menu_labels()
            except ValueError:
                pass

    def _toggle_cost_tracking(self, _) -> None:
        self.cfg.logging.cost_tracking = not self.cfg.logging.cost_tracking
        self.cfg.save()
        self._rebuild_menu_labels()

    def _rebuild_menu_labels(self) -> None:
        """Rebuild menu to reflect updated config values."""
        self._build_menu()

    # ── Autostart ──────────────────────────────────────────────────

    def _autostart_label(self) -> str:
        return "✓ Autostart aktiv" if self._autostart_installed() else "Autostart aktivieren"

    def _autostart_installed(self) -> bool:
        plist = Path.home() / "Library/LaunchAgents/com.gambastudio.jarvis.plist"
        return plist.exists()

    def _toggle_autostart(self, _) -> None:
        plist = Path.home() / "Library/LaunchAgents/com.gambastudio.jarvis.plist"
        if self._autostart_installed():
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
            plist.unlink(missing_ok=True)
            rumps.alert("Autostart deaktiviert")
        else:
            self._install_autostart(plist)
            rumps.alert("Autostart aktiviert", "Jarvis startet beim nächsten Login automatisch.")
        self._rebuild_menu_labels()

    def _install_autostart(self, plist: Path) -> None:
        app_path = Path(__file__).parent.parent.parent.parent  # src → jarvis root
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gambastudio.jarvis</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3.12</string>
        <string>-m</string>
        <string>jarvis.ui.macos_app</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>{app_path}</string>
</dict>
</plist>
""")
        subprocess.run(["launchctl", "load", str(plist)], capture_output=True)

    # ── Quit ───────────────────────────────────────────────────────

    def _quit(self, _) -> None:
        if self._pipeline:
            log.info("Shutting down pipeline...")
        rumps.quit_application()


def main() -> None:
    """Entry point for the macOS Menu Bar App."""
    JarvisMenuBarApp().run()


if __name__ == "__main__":
    main()
```

Update `src/jarvis/ui/__init__.py`:
```python
"""Jarvis UI components."""
from __future__ import annotations
```

**Step 2: Verify import (no rumps crash)**
```bash
cd /Users/zeisler/jarvis && python3.12 -c "
import sys
sys.argv = ['test']
# Don't actually run, just check imports
from jarvis.ui.macos_app import JarvisMenuBarApp, STATE_ICONS
from jarvis.pipeline.orchestrator import PipelineState
assert STATE_ICONS[PipelineState.IDLE] == '🎙'
print('macos_app import OK')
"
```
Expected: `macos_app import OK`

**Step 3: Commit**
```bash
cd /Users/zeisler/jarvis && git add src/jarvis/ui/macos_app.py src/jarvis/ui/__init__.py
git commit -m "feat: add JarvisMenuBarApp with full settings menu and state icons"
```

---

### Task 5: Add `__main__` entry for UI + install rumps

Make `python3.12 -m jarvis.ui.macos_app` work and install rumps.

**Files:**
- No new files — verify rumps installable and entry point works

**Step 1: Install rumps**
```bash
python3.12 -m pip install rumps --break-system-packages -q
```

**Step 2: Verify rumps works**
```bash
python3.12 -c "import rumps; print('rumps', rumps.__version__)"
```
Expected: `rumps <version>`

**Step 3: Verify PyObjC available**
```bash
python3.12 -c "import AppKit; from Foundation import NSMutableAttributedString; print('PyObjC OK')"
```
Expected: `PyObjC OK`

If PyObjC missing:
```bash
python3.12 -m pip install pyobjc-framework-Cocoa --break-system-packages -q
```

**Step 4: Add rumps to pyproject.toml optional dependencies**

In `pyproject.toml`, find the `[project.optional-dependencies]` section (or add it after `[project]`) and add:
```toml
[project.optional-dependencies]
stt = ["RealtimeSTT"]
macos = ["rumps", "pyobjc-framework-Cocoa"]
dev = ["pytest", "pytest-asyncio", "ruff"]
```

**Step 5: Add `jarvis-app` entry point to pyproject.toml**

In the `[project.scripts]` section:
```toml
[project.scripts]
jarvis = "jarvis.cli:app"
jarvis-app = "jarvis.ui.macos_app:main"
```

**Step 6: Commit**
```bash
cd /Users/zeisler/jarvis && git add pyproject.toml
git commit -m "chore: add rumps/pyobjc to optional deps, add jarvis-app entry point"
```

---

### Task 6: Run full test suite + manual smoke test

**Step 1: Run all automated tests**
```bash
cd /Users/zeisler/jarvis && python3.12 -m pytest tests/ -q
```
Expected: 34 passed (29 existing + 2 new orchestrator/config + 5 keychain)

**Step 2: Run ruff**
```bash
cd /Users/zeisler/jarvis && ruff check src/ tests/ && ruff format --check src/ tests/
```
Fix any issues, then re-run.

**Step 3: Manual smoke test — launch the app**
```bash
cd /Users/zeisler/jarvis && python3.12 -m jarvis.ui.macos_app
```

**Verify manually:**
- [ ] 🎙 icon appears in menu bar
- [ ] Clicking icon shows menu with all items
- [ ] "Log anzeigen" opens dark Cocoa window
- [ ] "API Key setzen" opens password dialog
- [ ] After setting key: pipeline starts, icon changes to 🟢 when "Jarvis" said
- [ ] Icon changes to 🔵 while speaking
- [ ] Stop word "Danke" returns to 🎙
- [ ] Settings changes save to `~/.jarvis/jarvis.yaml`
- [ ] "Autostart aktivieren" installs LaunchAgent

**Step 4: Commit any fixes**
```bash
cd /Users/zeisler/jarvis && git add -A && git commit -m "fix: smoke test fixes for macOS app"
```

**Step 5: Push**
```bash
cd /Users/zeisler/jarvis && git push origin main
```
