# tests/test_base_interfaces.py
"""Tests for pipeline base interfaces."""

from jarvis.pipeline.base import STTEngine, TTSEngine, WakeWordEngine


def test_stt_engine_has_callback_interface():
    """STTEngine must define start(on_text), stop(), mute(), unmute()."""
    import inspect
    methods = {name for name, _ in inspect.getmembers(STTEngine, predicate=inspect.isfunction)}
    assert "start" in methods
    assert "stop" in methods
    assert "mute" in methods
    assert "unmute" in methods


def test_stt_engine_start_signature():
    """start() must accept an on_text callback parameter."""
    import inspect
    sig = inspect.signature(STTEngine.start)
    params = list(sig.parameters.keys())
    assert "on_text" in params


def test_stt_engine_no_transcribe():
    """Old transcribe() method should be removed."""
    assert not hasattr(STTEngine, "transcribe")


def test_stt_engine_no_start_stream():
    """Old start_stream() method should be removed."""
    assert not hasattr(STTEngine, "start_stream")
