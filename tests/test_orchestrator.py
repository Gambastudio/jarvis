"""Tests for the VoicePipeline orchestrator state machine."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.config import JarvisConfig
from jarvis.pipeline.orchestrator import PipelineState, VoicePipeline


@pytest.fixture
def mock_components():
    """Create mock STT, TTS, Wake, and Agent components."""
    stt = MagicMock()
    stt.mute = MagicMock()
    stt.unmute = MagicMock()
    stt.start = AsyncMock()
    stt.stop = AsyncMock()

    tts = MagicMock()
    tts.speak = AsyncMock()
    tts.stop = AsyncMock()

    wake = MagicMock()
    wake.check_transcription = MagicMock(return_value=None)

    agent = MagicMock()
    agent.ask = AsyncMock(return_value="Test response")
    agent.reset_session = AsyncMock()
    agent.close = AsyncMock()

    config = JarvisConfig()

    return stt, tts, wake, agent, config


def test_initial_state(mock_components):
    """Pipeline should start in IDLE state."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    assert pipeline.state == PipelineState.IDLE


def test_idle_ignores_non_wake_word(mock_components):
    """In IDLE state, non-wake-word text should be ignored."""
    stt, tts, wake, agent, config = mock_components
    wake.check_transcription.return_value = None
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("random text")
    assert pipeline.state == PipelineState.IDLE
    agent.ask.assert_not_called()


def test_idle_wake_word_no_command(mock_components):
    """Wake word without command should transition to LISTENING and say 'Ja?'."""
    stt, tts, wake, agent, config = mock_components
    wake.check_transcription.return_value = ""  # empty = wake word only
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("Jarvis")
    assert pipeline.state == PipelineState.LISTENING
    tts.speak.assert_called()


def test_idle_wake_word_with_command(mock_components):
    """Wake word with command should process immediately."""
    stt, tts, wake, agent, config = mock_components
    wake.check_transcription.return_value = "wie ist das wetter"
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("Jarvis wie ist das wetter")
    agent.ask.assert_called_once_with("wie ist das wetter")
    tts.speak.assert_called()
    assert pipeline.state == PipelineState.LISTENING


def test_listening_stop_word(mock_components):
    """Stop word in LISTENING state should transition to IDLE."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    pipeline._on_transcription("danke")
    assert pipeline.state == PipelineState.IDLE
    agent.reset_session.assert_called_once()


def test_listening_command(mock_components):
    """Regular text in LISTENING state should be processed."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    pipeline._on_transcription("was ist Python")
    agent.ask.assert_called_once_with("was ist Python")
    tts.speak.assert_called()


def test_listening_exit_phrase(mock_components):
    """Exit phrase should raise SystemExit."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    with pytest.raises(SystemExit):
        pipeline._on_transcription("jarvis beenden")


def test_speak_mutes_and_unmutes(mock_components):
    """_speak() should mute before TTS and unmute after."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.LISTENING
    asyncio.run(pipeline._speak("hello"))
    stt.mute.assert_called_once()
    tts.speak.assert_called_once_with("hello")
    stt.unmute.assert_called_once()


def test_empty_text_ignored(mock_components):
    """Empty or very short text should be ignored."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline._on_transcription("")
    pipeline._on_transcription("a")
    pipeline._on_transcription("  ")
    agent.ask.assert_not_called()
    wake.check_transcription.assert_not_called()


def test_speaking_state_ignores_input(mock_components):
    """Input during SPEAKING state should be ignored."""
    stt, tts, wake, agent, config = mock_components
    pipeline = VoicePipeline(stt=stt, tts=tts, wake=wake, agent=agent, config=config)
    pipeline.state = PipelineState.SPEAKING
    pipeline._on_transcription("some text")
    agent.ask.assert_not_called()
    wake.check_transcription.assert_not_called()


def test_state_callback_called_on_transition(mock_components):
    """state_callback should be called whenever state changes."""
    stt, tts, wake, agent, config = mock_components
    states_seen = []
    pipeline = VoicePipeline(
        stt=stt,
        tts=tts,
        wake=wake,
        agent=agent,
        config=config,
        state_callback=lambda s: states_seen.append(s),
    )
    wake.check_transcription.return_value = ""
    pipeline._on_transcription("Jarvis")
    assert PipelineState.LISTENING in states_seen
