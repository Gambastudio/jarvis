"""Tests for _is_model_cached helper."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def test_is_model_cached_returns_false_when_none(monkeypatch):
    """Returns False when huggingface_hub reports model not cached."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.return_value = None
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("tiny") is False


def test_is_model_cached_returns_true_when_path(monkeypatch):
    """Returns True when huggingface_hub returns a path to cached weights."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.return_value = "/some/path/model.bin"
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("base") is True


def test_is_model_cached_returns_false_on_exception(monkeypatch):
    """Returns False (safe default) if huggingface_hub check raises."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.side_effect = Exception("network error")
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("small") is False


def test_is_model_cached_checks_correct_repo(monkeypatch):
    """Checks the Systran/faster-whisper-{model} HuggingFace repo."""
    mock_hf = MagicMock()
    mock_hf.try_to_load_from_cache.return_value = None
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    _is_model_cached("tiny")

    mock_hf.try_to_load_from_cache.assert_called_once_with(
        "Systran/faster-whisper-tiny", "model.bin"
    )


def test_is_model_cached_returns_false_for_cached_no_exist(monkeypatch):
    """Returns False when huggingface_hub returns _CACHED_NO_EXIST sentinel (not a str path)."""
    mock_hf = MagicMock()
    # _CACHED_NO_EXIST is just a plain object() — simulate it without importing the real sentinel
    mock_hf.try_to_load_from_cache.return_value = object()
    monkeypatch.setitem(sys.modules, "huggingface_hub", mock_hf)

    if "jarvis.ui.macos_app" in sys.modules:
        del sys.modules["jarvis.ui.macos_app"]

    from jarvis.ui.macos_app import _is_model_cached

    assert _is_model_cached("tiny") is False
