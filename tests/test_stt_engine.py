"""Tests for RealtimeSTT engine wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from jarvis.pipeline.stt.realtimestt import RealtimeSTTEngine
from jarvis.pipeline.base import STTEngine
from jarvis.config import STTConfig, VADConfig


def test_realtimestt_implements_stt_engine():
    """RealtimeSTTEngine must be a subclass of STTEngine."""
    assert issubclass(RealtimeSTTEngine, STTEngine)


def test_realtimestt_init():
    """Should store config without creating a recorder."""
    engine = RealtimeSTTEngine(
        stt_config=STTConfig(),
        vad_config=VADConfig(),
    )
    assert engine._recorder is None
    assert engine._running is False


def test_mute_without_recorder():
    """mute() should be safe to call without a recorder."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine.mute()  # should not raise


def test_unmute_without_recorder():
    """unmute() should be safe to call without a recorder."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine.unmute()  # should not raise


def test_mute_delegates_to_recorder():
    """mute() should call recorder.set_microphone(False)."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine._recorder = MagicMock()
    engine.mute()
    engine._recorder.set_microphone.assert_called_once_with(False)


def test_unmute_delegates_to_recorder():
    """unmute() should clear queue then re-enable mic."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine._recorder = MagicMock()
    engine.unmute()
    engine._recorder.clear_audio_queue.assert_called_once()
    engine._recorder.set_microphone.assert_called_once_with(True)


@pytest.mark.asyncio
async def test_stop_sets_running_false():
    """stop() should set _running to False and call recorder.stop()."""
    engine = RealtimeSTTEngine(stt_config=STTConfig(), vad_config=VADConfig())
    engine._running = True
    engine._recorder = MagicMock()
    await engine.stop()
    assert engine._running is False
    engine._recorder.stop.assert_called_once()
