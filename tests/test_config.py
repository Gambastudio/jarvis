"""Tests for configuration loading."""

from jarvis.config import JarvisConfig


def test_default_config():
    """Default config should have sensible values."""
    cfg = JarvisConfig()
    assert cfg.stt.engine == "realtimestt"
    assert cfg.stt.model == "base"
    assert cfg.stt.language == "de"
    assert cfg.tts.engine == "macos-say"
    assert cfg.tts.rate == 200
    assert cfg.session.wake_word == "jarvis"
    assert cfg.session.stop_word == "danke"
    assert cfg.agent.model == "claude-sonnet-4-6"
    assert cfg.agent.max_turns == 20


def test_wake_word_variants():
    """Wake word config should include phonetic variants."""
    cfg = JarvisConfig()
    assert len(cfg.wake_word.variants) > 20
    assert "jarvis" in cfg.wake_word.variants
    assert "dschawis" in cfg.wake_word.variants


def test_get_api_key_missing(monkeypatch):
    """Should raise ValueError when API key is not set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = JarvisConfig()
    try:
        cfg.get_api_key()
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_config_save(tmp_path):
    """save() should write config to YAML file."""
    cfg = JarvisConfig()
    cfg.session.wake_word = "hey jarvis"
    out = tmp_path / "jarvis.yaml"
    cfg.save(out)
    assert out.exists()
    loaded = JarvisConfig.load(out)
    assert loaded.session.wake_word == "hey jarvis"
