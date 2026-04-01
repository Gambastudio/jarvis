"""Tests for macOS Keychain helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from jarvis.utils.keychain import get_api_key, has_api_key, set_api_key


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
