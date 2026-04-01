"""Configuration loading and management."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".jarvis"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "jarvis.yaml"


@dataclass
class WakeWordConfig:
    engine: str = "whisper-wake"
    variants: list[str] = field(
        default_factory=lambda: [
            "jarvis",
            "dschawis",
            "jervis",
            "jarwis",
            "schavis",
            "chavez",
            "jogges",
            "jarves",
            "jarfis",
            "jarvice",
            "charvis",
            "tschawis",
            "ja bis",
            "ja, bis",
            "job ist",
            "ciao bis",
            "ciao, bis",
            "javis",
            "jarbis",
            "tschabis",
            "schawis",
            "dscharvis",
            "dschavis",
            "travis",
            "bis monat",
        ]
    )


@dataclass
class STTConfig:
    engine: str = "realtimestt"
    model: str = "base"
    language: str = "de"
    compute_type: str = "int8"
    initial_prompt: str = "Jarvis"


@dataclass
class TTSConfig:
    engine: str = "macos-say"
    rate: int = 200
    voice: str | None = None
    piper_voice: str = "de_DE-thorsten-high"


@dataclass
class VADConfig:
    sensitivity: float = 0.4
    post_speech_silence: float = 0.8
    min_recording_length: float = 0.2


@dataclass
class SessionConfig:
    wake_word: str = "jarvis"
    stop_word: str = "danke"
    exit_phrase: str = "jarvis beenden"
    max_history: int = 16


@dataclass
class AgentConfig:
    api_key_env: str = "ANTHROPIC_API_KEY"
    model: str = "claude-sonnet-4-6"
    max_turns: int = 20
    max_budget_usd: float = 0.50
    permission_mode: str = "acceptEdits"
    thinking: dict[str, Any] = field(default_factory=lambda: {"type": "adaptive"})


@dataclass
class AudioConfig:
    input_device: str = "default"
    output_device: str = "default"
    sample_rate: int = 16000


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "~/.jarvis/logs/jarvis.log"
    cost_tracking: bool = True


@dataclass
class JarvisConfig:
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> JarvisConfig:
        """Load config from YAML file, falling back to defaults."""
        config = cls()
        search_paths = [
            path,
            Path.cwd() / "jarvis.yaml",
            DEFAULT_CONFIG_FILE,
        ]
        for p in search_paths:
            if p and p.exists():
                config = cls._from_yaml(p)
                break
        return config

    @classmethod
    def _from_yaml(cls, path: Path) -> JarvisConfig:
        """Parse YAML config file into JarvisConfig."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        config = cls()
        if "wake_word" in data:
            config.wake_word = WakeWordConfig(**data["wake_word"])
        if "stt" in data:
            config.stt = STTConfig(**data["stt"])
        if "tts" in data:
            config.tts = TTSConfig(**data["tts"])
        if "vad" in data:
            config.vad = VADConfig(**data["vad"])
        if "session" in data:
            config.session = SessionConfig(**data["session"])
        if "agent" in data:
            config.agent = AgentConfig(**data["agent"])
        if "audio" in data:
            config.audio = AudioConfig(**data["audio"])
        if "logging" in data:
            config.logging = LoggingConfig(**data["logging"])
        if "mcp_servers" in data:
            config.mcp_servers = data["mcp_servers"]
        if "allowed_tools" in data:
            config.allowed_tools = data["allowed_tools"]
        if "disallowed_tools" in data:
            config.disallowed_tools = data["disallowed_tools"]
        return config

    @classmethod
    def from_legacy_json(cls, path: Path) -> JarvisConfig:
        """Import config from Jarvis4Gamba config.json format."""
        with open(path) as f:
            data = json.load(f)
        config = cls()
        if "llm_model" in data:
            config.agent.model = data["llm_model"]
        if "whisper_model" in data:
            config.stt.model = data["whisper_model"]
        if "wake_word" in data:
            config.session.wake_word = data["wake_word"]
        if "stop_word" in data:
            config.session.stop_word = data["stop_word"]
        if "speech_rate" in data:
            config.tts.rate = data["speech_rate"]
        if "language" in data:
            config.stt.language = data["language"]
        if "max_tokens" in data:
            config.agent.max_turns = min(data["max_tokens"] // 10, 20)
        if "system_prompt" in data:
            pass  # System prompt now lives in CLAUDE.md
        return config

    def save(self, path: Path | None = None) -> None:
        """Write current config to YAML file."""
        target = path or DEFAULT_CONFIG_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "wake_word": {"engine": self.wake_word.engine, "variants": self.wake_word.variants},
            "stt": {
                "engine": self.stt.engine,
                "model": self.stt.model,
                "language": self.stt.language,
                "compute_type": self.stt.compute_type,
                "initial_prompt": self.stt.initial_prompt,
            },
            "tts": {
                "engine": self.tts.engine,
                "rate": self.tts.rate,
                "voice": self.tts.voice,
                "piper_voice": self.tts.piper_voice,
            },
            "vad": {
                "sensitivity": self.vad.sensitivity,
                "post_speech_silence": self.vad.post_speech_silence,
                "min_recording_length": self.vad.min_recording_length,
            },
            "session": {
                "wake_word": self.session.wake_word,
                "stop_word": self.session.stop_word,
                "exit_phrase": self.session.exit_phrase,
                "max_history": self.session.max_history,
            },
            "agent": {
                "api_key_env": self.agent.api_key_env,
                "model": self.agent.model,
                "max_turns": self.agent.max_turns,
                "max_budget_usd": self.agent.max_budget_usd,
                "permission_mode": self.agent.permission_mode,
            },
            "audio": {
                "input_device": self.audio.input_device,
                "output_device": self.audio.output_device,
                "sample_rate": self.audio.sample_rate,
            },
            "logging": {
                "level": self.logging.level,
                "file": self.logging.file,
                "cost_tracking": self.logging.cost_tracking,
            },
        }
        with open(target, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def get_api_key(self) -> str:
        """Resolve API key from environment variable."""
        key = os.getenv(self.agent.api_key_env, "")
        if not key:
            raise ValueError(
                f"API key not found. Set {self.agent.api_key_env} environment variable."
            )
        return key
