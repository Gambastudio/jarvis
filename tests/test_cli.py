"""Tests for CLI commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from jarvis.cli import app

runner = CliRunner()


def test_version():
    """version command should print version string."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Jarvis v" in result.output


def test_query_command():
    """query command should call agent.ask() and print the response."""
    with (
        patch("jarvis.config.JarvisConfig") as mock_config_cls,
        patch("jarvis.agent.core.JarvisAgent") as mock_agent_cls,
        patch("jarvis.utils.logging.setup_logging"),
    ):
        mock_agent = MagicMock()
        mock_agent.ask = AsyncMock(return_value="Test response")
        mock_agent.close = AsyncMock()
        mock_agent_cls.return_value = mock_agent
        mock_cfg = MagicMock()
        mock_cfg.logging.level = "INFO"
        mock_config_cls.load.return_value = mock_cfg

        result = runner.invoke(app, ["query", "hello"])
        assert result.exit_code == 0


def test_listen_uses_voice_pipeline():
    """listen command _run_pipeline() must delegate to VoicePipeline, not AudioToTextRecorder."""
    import inspect

    from jarvis.cli import _run_pipeline

    source = inspect.getsource(_run_pipeline)
    assert "VoicePipeline" in source
    assert "AudioToTextRecorder" not in source
