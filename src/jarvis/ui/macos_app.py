"""Jarvis macOS Menu Bar App.

Entry point for the .app bundle. Runs VoicePipeline in a background thread,
updates the menu bar icon on state changes, and provides a full settings menu.

Usage:
    python3.12 -m jarvis.ui.macos_app
"""

from __future__ import annotations

import atexit
import asyncio
import logging
import multiprocessing
import os
import signal
import subprocess
import threading
from pathlib import Path

import rumps

from jarvis.config import JarvisConfig, MemoryConfig
from jarvis.pipeline.orchestrator import PipelineState, VoicePipeline
from jarvis.ui.log_window import LogWindow, WindowLogHandler
from jarvis.utils.keychain import (
    get_api_key,
    get_deepgram_key,
    get_elevenlabs_key,
    has_api_key,
    has_deepgram_key,
    has_elevenlabs_key,
    set_api_key,
    set_deepgram_key,
    set_elevenlabs_key,
)

log = logging.getLogger("jarvis")

# State → Menu Bar emoji
STATE_ICONS: dict[PipelineState, str] = {
    PipelineState.IDLE: "🎙",
    PipelineState.LISTENING: "🟢",
    PipelineState.PROCESSING: "🟢",
    PipelineState.SPEAKING: "🔵",
    PipelineState.PERMISSION_PENDING: "🔐",
}
ERROR_ICON = "🔴"

STT_ENGINES = {
    "realtimestt": "RealtimeSTT (lokal)",
    "deepgram": "Deepgram Nova-3 (cloud)",
}
TTS_ENGINES = {
    "macos-say": "macOS Say (System)",
    "piper": "Piper (lokal, neural)",
    "elevenlabs": "ElevenLabs (cloud, premium)",
}
PIPER_VOICES = {
    "de_DE-thorsten-high": "Thorsten High (DE)",
    "de_DE-thorsten-medium": "Thorsten Medium (DE)",
    "en_US-lessac-high": "Lessac High (EN)",
    "en_US-lessac-medium": "Lessac Medium (EN)",
}
WHISPER_MODELS = ["tiny", "base", "small"]
CLAUDE_MODELS = {
    "claude-haiku-4-5": "Haiku (schnell)",
    "claude-sonnet-4-6": "Sonnet (empfohlen)",
    "claude-opus-4-0": "Opus (leistungsstark)",
}
LANGUAGES = {"de": "Deutsch", "en": "English", "fr": "Français", "es": "Español"}

# Model size hints for download status message
_MODEL_SIZES = {"tiny": "75MB", "base": "150MB", "small": "500MB"}


def _is_model_cached(model: str) -> bool:
    """Check if the faster-whisper model weights are in the huggingface cache."""
    try:
        from huggingface_hub import try_to_load_from_cache

        result = try_to_load_from_cache(f"Systran/faster-whisper-{model}", "model.bin")
        return isinstance(result, str)
    except Exception:
        return False  # safe default: assume not cached


class JarvisMenuBarApp(rumps.App):
    """Jarvis Menu Bar App — wraps VoicePipeline with full macOS UI."""

    def __init__(self) -> None:
        super().__init__("🎙", quit_button=None)
        self.cfg = JarvisConfig.load()
        self._log_window = LogWindow()
        self._pipeline_thread: threading.Thread | None = None
        self._pipeline: VoicePipeline | None = None
        self._timer_started = False
        self._pipeline_started = False
        self._restart_attempts = 0
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

        # Only start pipeline and timer once
        if not self._pipeline_started:
            self._pipeline_started = True
            self._start_pipeline()
        if not self._timer_started:
            self._timer_started = True
            rumps.Timer(self._flush_log, 0.1).start()

    def _build_settings_menu(self) -> rumps.MenuItem:
        settings = rumps.MenuItem("⚙️ Einstellungen")

        # ── API Keys ──────────────────────────────────────────────
        keys_menu = rumps.MenuItem("🔑 API Keys")
        ant_label = "Anthropic" + (" ✓" if has_api_key() else " ✗")
        keys_menu[ant_label] = rumps.MenuItem(ant_label, callback=self._set_api_key)
        dg_label = "Deepgram" + (" ✓" if has_deepgram_key() else " ✗")
        keys_menu[dg_label] = rumps.MenuItem(dg_label, callback=self._set_deepgram_key)
        el_label = "ElevenLabs" + (" ✓" if has_elevenlabs_key() else " ✗")
        keys_menu[el_label] = rumps.MenuItem(el_label, callback=self._set_elevenlabs_key)
        settings["keys"] = keys_menu

        settings.update([None])

        # ── Spracheingabe (STT) ───────────────────────────────────
        stt_section = rumps.MenuItem("🎙 Spracheingabe")

        # Engine
        for engine_id, label in STT_ENGINES.items():
            check = "✓ " if engine_id == self.cfg.stt.engine else "  "
            item = rumps.MenuItem(f"{check}{label}", callback=self._set_stt_engine)
            stt_section[engine_id] = item

        stt_section.update([None])

        # Whisper model (only for RealtimeSTT)
        if self.cfg.stt.engine == "realtimestt":
            whisper_menu = rumps.MenuItem(f"Modell: {self.cfg.stt.model}")
            for m in WHISPER_MODELS:
                check = "✓ " if m == self.cfg.stt.model else "  "
                whisper_menu[m] = rumps.MenuItem(f"{check}{m}", callback=self._set_whisper_model)
            stt_section["whisper"] = whisper_menu

        # Language
        lang_menu = rumps.MenuItem(f"Sprache: {LANGUAGES.get(self.cfg.stt.language, self.cfg.stt.language)}")
        for code, name in LANGUAGES.items():
            check = "✓ " if code == self.cfg.stt.language else "  "
            lang_menu[code] = rumps.MenuItem(f"{check}{name}", callback=self._set_language)
        stt_section["language"] = lang_menu

        settings["stt"] = stt_section

        settings.update([None])

        # ── Sprachausgabe (TTS) ───────────────────────────────────
        tts_section = rumps.MenuItem("🔊 Sprachausgabe")

        # Engine
        for engine_id, label in TTS_ENGINES.items():
            check = "✓ " if engine_id == self.cfg.tts.engine else "  "
            item = rumps.MenuItem(f"{check}{label}", callback=self._set_tts_engine)
            tts_section[engine_id] = item

        tts_section.update([None])

        # Voice selection (engine-specific)
        if self.cfg.tts.engine == "piper":
            voice_menu = rumps.MenuItem(f"Stimme: {self.cfg.tts.piper_voice}")
            for voice_id, label in PIPER_VOICES.items():
                check = "✓ " if voice_id == self.cfg.tts.piper_voice else "  "
                voice_menu[voice_id] = rumps.MenuItem(f"{check}{label}", callback=self._set_piper_voice)
            tts_section["voice"] = voice_menu

        elif self.cfg.tts.engine == "elevenlabs":
            from jarvis.pipeline.tts.elevenlabs_tts import ELEVENLABS_VOICES

            current_el = self.cfg.tts.elevenlabs_voice
            current_label = ELEVENLABS_VOICES.get(current_el, {}).get("label", current_el)
            voice_menu = rumps.MenuItem(f"Stimme: {current_label}")
            for voice_id, info in ELEVENLABS_VOICES.items():
                check = "✓ " if voice_id == current_el else "  "
                voice_menu[voice_id] = rumps.MenuItem(
                    f"{check}{info['label']}", callback=self._set_elevenlabs_voice
                )
            voice_menu["custom"] = rumps.MenuItem(
                "🎤 Eigene Voice-ID...", callback=self._set_elevenlabs_custom_voice
            )
            tts_section["voice"] = voice_menu

        # Speed + mic mute
        tts_section[f"Geschwindigkeit: {self.cfg.tts.rate} wpm"] = rumps.MenuItem(
            f"Geschwindigkeit: {self.cfg.tts.rate} wpm", callback=self._set_tts_rate
        )
        mute_check = "✓ " if self.cfg.tts.mute_mic_during_speech else "  "
        tts_section[f"{mute_check}Mic stumm bei Sprache"] = rumps.MenuItem(
            f"{mute_check}Mic stumm bei Sprache", callback=self._toggle_mic_mute
        )

        settings["tts"] = tts_section

        settings.update([None])

        # ── Agent ─────────────────────────────────────────────────
        agent_section = rumps.MenuItem("🤖 Agent")

        current_label = CLAUDE_MODELS.get(self.cfg.agent.model, self.cfg.agent.model)
        claude_menu = rumps.MenuItem(f"Modell: {current_label}")
        for model_id, label in CLAUDE_MODELS.items():
            check = "✓ " if model_id == self.cfg.agent.model else "  "
            claude_menu[model_id] = rumps.MenuItem(f"{check}{label}", callback=self._set_claude_model)
        agent_section["claude"] = claude_menu

        agent_section[f"Budget: ${self.cfg.agent.max_budget_usd:.2f}"] = rumps.MenuItem(
            f"Budget: ${self.cfg.agent.max_budget_usd:.2f}", callback=self._set_budget
        )
        agent_section[f"Max. Runden: {self.cfg.agent.max_turns}"] = rumps.MenuItem(
            f"Max. Runden: {self.cfg.agent.max_turns}", callback=self._set_max_turns
        )
        cost_check = "✓ " if self.cfg.logging.cost_tracking else "  "
        agent_section[f"{cost_check}Kosten-Tracking"] = rumps.MenuItem(
            f"{cost_check}Kosten-Tracking", callback=self._toggle_cost_tracking
        )

        settings["agent"] = agent_section

        settings.update([None])

        # ── Session ───────────────────────────────────────────────
        session_section = rumps.MenuItem("💬 Session")
        session_section[f"Wake Word: {self.cfg.session.wake_word}"] = rumps.MenuItem(
            f"Wake Word: {self.cfg.session.wake_word}", callback=self._set_wake_word
        )
        session_section[f"Stop Word: {self.cfg.session.stop_word}"] = rumps.MenuItem(
            f"Stop Word: {self.cfg.session.stop_word}", callback=self._set_stop_word
        )
        session_section[f"Exit-Phrase: {self.cfg.session.exit_phrase}"] = rumps.MenuItem(
            f"Exit-Phrase: {self.cfg.session.exit_phrase}", callback=self._set_exit_phrase
        )
        settings["session"] = session_section

        # ── Memory ────────────────────────────────────────────────
        mem_section = rumps.MenuItem("🧠 Memory")
        mem_path = self.cfg.memory.path
        short_path = mem_path.replace(str(Path.home()), "~")
        mem_section[f"Pfad: {short_path}"] = rumps.MenuItem(
            f"Pfad: {short_path}", callback=self._set_memory_path
        )
        files_label = ", ".join(self.cfg.memory.files) if self.cfg.memory.files else "(keine)"
        mem_section[f"Dateien: {files_label}"] = rumps.MenuItem(
            f"Dateien: {files_label}", callback=self._set_memory_files
        )
        settings["memory"] = mem_section

        return settings

    # ── Pipeline ───────────────────────────────────────────────────

    def _restart_pipeline(self) -> None:
        """Stop current pipeline and start a new one with updated config."""
        log.info("Restarting pipeline with new settings...")
        self._cleanup()
        self._pipeline = None
        self._pipeline_started = False
        self._start_pipeline()

    def _start_pipeline(self) -> None:
        """Start VoicePipeline in background thread."""
        if not has_api_key():
            self._update_status("⚠️ API Key fehlt — bitte in Einstellungen setzen")
            self.title = ERROR_ICON
            return

        def run() -> None:
            import os

            from jarvis.agent.core import JarvisAgent
            from jarvis.pipeline.wake.whisper_wake import WhisperWakeEngine

            # Inject API keys from Keychain into environment
            api_key = get_api_key()
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
            dg_key = get_deepgram_key()
            if dg_key:
                os.environ["DEEPGRAM_API_KEY"] = dg_key

            # Select STT engine
            if self.cfg.stt.engine == "deepgram":
                from jarvis.pipeline.stt.deepgram_stt import DeepgramSTTEngine

                stt = DeepgramSTTEngine(stt_config=self.cfg.stt, vad_config=self.cfg.vad)
                log.info("Using Deepgram Nova-3 STT")
            else:
                from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine

                stt = RealtimeSTTEngine(stt_config=self.cfg.stt, vad_config=self.cfg.vad)

            # Select TTS engine
            if self.cfg.tts.engine == "elevenlabs":
                from jarvis.pipeline.tts.elevenlabs_tts import ElevenLabsTTSEngine

                el_key = get_elevenlabs_key() or ""
                tts = ElevenLabsTTSEngine(
                    api_key=el_key,
                    voice=self.cfg.tts.elevenlabs_voice,
                    model=self.cfg.tts.elevenlabs_model,
                )
                log.info(f"Using ElevenLabs TTS ({self.cfg.tts.elevenlabs_voice})")
            elif self.cfg.tts.engine == "piper":
                from jarvis.pipeline.tts.piper import PiperTTSEngine

                tts = PiperTTSEngine(voice=self.cfg.tts.piper_voice, rate=self.cfg.tts.rate)
                log.info(f"Using Piper TTS ({self.cfg.tts.piper_voice})")
            else:
                from jarvis.pipeline.tts.macos_say import MacOSSayEngine

                tts = MacOSSayEngine(rate=self.cfg.tts.rate, voice=self.cfg.tts.voice)
            wake = WhisperWakeEngine(self.cfg.wake_word.variants)
            agent = JarvisAgent(self.cfg)

            self._pipeline = VoicePipeline(
                stt=stt,
                tts=tts,
                wake=wake,
                agent=agent,
                config=self.cfg,
                state_callback=self._on_state_change,
                on_exit=self._quit_from_pipeline,
            )
            try:
                self._restart_attempts = 0
                asyncio.run(self._pipeline.run())
            except Exception as e:
                log.error(f"Pipeline crashed: {e}")
                self.title = ERROR_ICON
                self._restart_attempts += 1
                if self._restart_attempts >= 5:
                    self._update_status("🔴 Dauerfehler — bitte App neu starten")
                    log.error("Pipeline crashed 5 times, giving up.")
                    return
                self._update_status(
                    f"🔴 Fehler — starte neu in 5s... (Versuch {self._restart_attempts}/5)"
                )
                import time

                time.sleep(5)
                self._pipeline_started = False
                self._start_pipeline()

        self._pipeline_thread = threading.Thread(target=run, daemon=True, name="VoicePipeline")
        self._pipeline_thread.start()
        if self.cfg.stt.engine == "deepgram":
            self._update_status("Verbinde mit Deepgram...")
        elif not _is_model_cached(self.cfg.stt.model):
            size = _MODEL_SIZES.get(self.cfg.stt.model, "?")
            self._update_status(f"📥 Lade {self.cfg.stt.model}-Modell herunter (~{size})...")
        else:
            self._update_status(f"Wartet auf '{self.cfg.session.wake_word}'...")

    def _on_state_change(self, state: PipelineState) -> None:
        """Called from pipeline thread — update icon thread-safely."""
        try:
            self.title = STATE_ICONS.get(state, ERROR_ICON)
            labels = {
                PipelineState.IDLE: f"Wartet auf '{self.cfg.session.wake_word}'...",
                PipelineState.LISTENING: "🟢 Lauscht...",
                PipelineState.PROCESSING: "🧠 Denkt...",
                PipelineState.SPEAKING: "🔵 Spricht...",
                PipelineState.PERMISSION_PENDING: "🔐 Wartet auf Genehmigung...",
            }
            self._update_status(labels.get(state, ""))
        except Exception:
            pass  # app not fully ready yet

    def _update_status(self, text: str) -> None:
        if hasattr(self, "_status_item"):
            self._status_item.title = text

    # ── Log Window ─────────────────────────────────────────────────

    def _show_log(self, _) -> None:
        try:
            self._log_window.create()
        except Exception as e:
            log.warning(f"Log window error: {e}")

    def _flush_log(self, _) -> None:
        try:
            self._log_window.flush()
        except Exception:
            pass

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

    def _set_deepgram_key(self, _) -> None:
        response = rumps.Window(
            message="Deepgram API Key eingeben:\n(https://console.deepgram.com)",
            title="🔑 Deepgram API Key",
            secure=True,
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            if set_deepgram_key(response.text.strip()):
                rumps.alert("Deepgram Key gespeichert", "Key wurde sicher im Keychain hinterlegt.")
                self._rebuild_menu_labels()

    def _set_stt_engine(self, sender) -> None:
        for engine_id, label in STT_ENGINES.items():
            if label in sender.title:
                if engine_id == "deepgram" and not has_deepgram_key():
                    rumps.alert(
                        "Deepgram API Key fehlt",
                        "Bitte zuerst einen Deepgram API Key setzen.",
                    )
                    return
                self.cfg.stt.engine = engine_id
                self.cfg.save()
                self._rebuild_menu_labels()
                threading.Thread(target=self._restart_pipeline, daemon=True).start()
                break

    def _set_wake_word(self, _) -> None:
        response = rumps.Window(
            message="Wake Word eingeben:",
            title="Wake Word",
            default_text=self.cfg.session.wake_word,
            ok="Speichern",
            cancel="Abbrechen",
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
            ok="Speichern",
            cancel="Abbrechen",
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
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            self.cfg.session.exit_phrase = response.text.strip().lower()
            self.cfg.save()
            self._rebuild_menu_labels()

    def _set_whisper_model(self, sender) -> None:
        # Find canonical model name by checking which WHISPER_MODELS value is in the title
        for m in WHISPER_MODELS:
            if m in sender.title:
                self.cfg.stt.model = m
                self.cfg.save()
                self._rebuild_menu_labels()
                break

    def _set_language(self, sender) -> None:
        for code, name in LANGUAGES.items():
            if name in sender.title:
                self.cfg.stt.language = code
                self.cfg.save()
                self._rebuild_menu_labels()
                break

    def _set_tts_rate(self, _) -> None:
        response = rumps.Window(
            message="Sprechgeschwindigkeit (100–300 wpm):",
            title="Sprechgeschwindigkeit",
            default_text=str(self.cfg.tts.rate),
            ok="Speichern",
            cancel="Abbrechen",
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
                self._rebuild_menu_labels()
                self._reconfigure_agent()
                break

    def _set_budget(self, _) -> None:
        response = rumps.Window(
            message="Budget-Limit in USD (z.B. 0.50):",
            title="Budget-Limit",
            default_text=str(self.cfg.agent.max_budget_usd),
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked:
            try:
                self.cfg.agent.max_budget_usd = float(response.text.strip())
                self.cfg.save()
                self._rebuild_menu_labels()
                self._reconfigure_agent()
            except ValueError:
                pass

    def _set_max_turns(self, _) -> None:
        response = rumps.Window(
            message="Maximale Gesprächsrunden (1–50):",
            title="Max. Runden",
            default_text=str(self.cfg.agent.max_turns),
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked:
            try:
                turns = int(response.text.strip())
                self.cfg.agent.max_turns = max(1, min(50, turns))
                self.cfg.save()
                self._rebuild_menu_labels()
                self._reconfigure_agent()
            except ValueError:
                pass

    def _reconfigure_agent(self) -> None:
        """Restart the SDK client so the new agent config takes effect."""
        if self._pipeline and self._pipeline.agent:
            threading.Thread(
                target=self._pipeline.agent.reconfigure, daemon=True
            ).start()
            log.info("Agent SDK restarting with new config...")

    def _set_tts_engine(self, sender) -> None:
        for engine_id, label in TTS_ENGINES.items():
            if label in sender.title:
                if engine_id == "elevenlabs" and not has_elevenlabs_key():
                    rumps.alert(
                        "ElevenLabs API Key fehlt",
                        "Bitte zuerst einen ElevenLabs API Key setzen.",
                    )
                    return
                self.cfg.tts.engine = engine_id
                self.cfg.save()
                self._rebuild_menu_labels()
                threading.Thread(target=self._restart_pipeline, daemon=True).start()
                break

    def _set_piper_voice(self, sender) -> None:
        for voice_id, label in PIPER_VOICES.items():
            if label in sender.title:
                self.cfg.tts.piper_voice = voice_id
                self.cfg.save()
                self._rebuild_menu_labels()
                threading.Thread(target=self._restart_pipeline, daemon=True).start()
                break

    def _set_elevenlabs_key(self, _) -> None:
        response = rumps.Window(
            message="ElevenLabs API Key eingeben:\n(https://elevenlabs.io/app/settings/api-keys)",
            title="🔑 ElevenLabs API Key",
            secure=True,
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            if set_elevenlabs_key(response.text.strip()):
                rumps.alert(
                    "ElevenLabs Key gespeichert",
                    "Key wurde sicher im Keychain hinterlegt.",
                )
                self._rebuild_menu_labels()

    def _set_elevenlabs_voice(self, sender) -> None:
        from jarvis.pipeline.tts.elevenlabs_tts import ELEVENLABS_VOICES

        for voice_id, info in ELEVENLABS_VOICES.items():
            if info["label"] in sender.title:
                self.cfg.tts.elevenlabs_voice = voice_id
                self.cfg.save()
                self._rebuild_menu_labels()
                threading.Thread(target=self._restart_pipeline, daemon=True).start()
                break

    def _set_elevenlabs_custom_voice(self, _) -> None:
        response = rumps.Window(
            message="ElevenLabs Voice-ID eingeben:\n(findest du unter Voices → deine Stimme → Voice ID)",
            title="🎤 Eigene Voice-ID",
            default_text=self.cfg.tts.elevenlabs_voice,
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            self.cfg.tts.elevenlabs_voice = response.text.strip()
            self.cfg.save()
            self._rebuild_menu_labels()
            threading.Thread(target=self._restart_pipeline, daemon=True).start()

    def _toggle_mic_mute(self, _) -> None:
        self.cfg.tts.mute_mic_during_speech = not self.cfg.tts.mute_mic_during_speech
        self.cfg.save()
        state = "an" if self.cfg.tts.mute_mic_during_speech else "aus"
        log.info(f"Mic-Stummschaltung bei Sprache: {state}")
        self._rebuild_menu_labels()

    def _toggle_cost_tracking(self, _) -> None:
        self.cfg.logging.cost_tracking = not self.cfg.logging.cost_tracking
        self.cfg.save()
        self._rebuild_menu_labels()

    def _set_memory_path(self, _) -> None:
        response = rumps.Window(
            message="Pfad zum Memory-Ordner (absolut oder mit ~):",
            title="Memory-Pfad",
            default_text=self.cfg.memory.path,
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked and response.text.strip():
            self.cfg.memory.path = response.text.strip()
            self.cfg.save()
            self._rebuild_menu_labels()

    def _set_memory_files(self, _) -> None:
        current = ", ".join(self.cfg.memory.files)
        response = rumps.Window(
            message="Memory-Dateien (kommagetrennt, ohne Pfad):\nHinweis: credentials.md wird nie geladen.",
            title="Memory-Dateien",
            default_text=current,
            ok="Speichern",
            cancel="Abbrechen",
        ).run()
        if response.clicked:
            raw = response.text.strip()
            files = [f.strip() for f in raw.split(",") if f.strip()]
            # Remove credentials.md for security
            files = [f for f in files if f.lower() != "credentials.md"]
            self.cfg.memory.files = files
            self.cfg.save()
            self._rebuild_menu_labels()

    def _rebuild_menu_labels(self) -> None:
        """Rebuild menu to reflect updated config values."""
        try:
            self._build_menu()
        except Exception as e:
            log.warning(f"Menu rebuild failed: {e}")

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
        import sys

        app_path = Path(__file__).parent.parent.parent.parent  # src → jarvis root
        plist.parent.mkdir(parents=True, exist_ok=True)
        Path.home().joinpath(".jarvis", "logs").mkdir(parents=True, exist_ok=True)
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.gambastudio.jarvis</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>jarvis.ui.macos_app</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>{app_path}</string>
    <key>StandardOutPath</key>
    <string>{Path.home() / ".jarvis/logs/jarvis-agent.log"}</string>
    <key>StandardErrorPath</key>
    <string>{Path.home() / ".jarvis/logs/jarvis-agent-err.log"}</string>
</dict>
</plist>
""")
        subprocess.run(["launchctl", "load", str(plist)], capture_output=True)

    # ── Quit ───────────────────────────────────────────────────────

    def _quit_from_pipeline(self) -> None:
        """Called from pipeline thread when exit phrase is spoken."""
        self._cleanup()
        rumps.quit_application()

    def _quit(self, _) -> None:
        self._cleanup()
        rumps.quit_application()

    def _cleanup(self) -> None:
        """Stop pipeline and terminate all child processes."""
        if self._pipeline:
            log.info("Shutting down pipeline...")
            try:
                self._pipeline.stt._running = False
                # RealtimeSTT has _recorder; Deepgram has _connection
                if hasattr(self._pipeline.stt, "_recorder") and self._pipeline.stt._recorder:
                    self._pipeline.stt._recorder.shutdown()
                    self._pipeline.stt._recorder = None
                elif hasattr(self._pipeline.stt, "_connection") and self._pipeline.stt._connection:
                    self._pipeline.stt._connection.finish()
                    self._pipeline.stt._connection = None
            except Exception as e:
                log.warning(f"STT cleanup error: {e}")
            try:
                self._pipeline.agent.close()
            except Exception:
                pass
        # Kill any remaining multiprocessing children
        for child in multiprocessing.active_children():
            log.info(f"Terminating child process {child.pid}")
            child.terminate()
            child.join(timeout=3)
            if child.is_alive():
                child.kill()


def _kill_orphaned_children() -> None:
    """atexit handler — terminate any multiprocessing children that survived."""
    for child in multiprocessing.active_children():
        child.terminate()
        child.join(timeout=2)
        if child.is_alive():
            child.kill()


atexit.register(_kill_orphaned_children)


def main() -> None:
    """Entry point for the macOS Menu Bar App."""
    JarvisMenuBarApp().run()


if __name__ == "__main__":
    main()
