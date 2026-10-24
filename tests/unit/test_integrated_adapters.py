"""
tests/unit/test_integrated_adapters.py
======================================
Unit Test Suite for Universal Model Adapters:
  1. ArgonEnhancedWhisper (CTranslate2 Whisper + DM-HSS + CGDS Medusa).
  2. ArgonConstrainedSLMAgent (Action-Tree + Win32 Oracle + Edge SLM).
  3. ArgonKokoroFullDuplexController (Kokoro/Piper TTS + FullDuplex ducking).
"""
import numpy as np
import pytest

from jarvis.audio.fullduplex import BargeInDecision
from jarvis.audio.integrated_full_duplex import ArgonKokoroFullDuplexController
from jarvis.planner.integrated_slm_agent import ArgonConstrainedSLMAgent, SLMResolutionOutput
from jarvis.stt.integrated_whisper import ArgonEnhancedWhisper, TranscriptionOutput


class MockWhisperModel:
    """Mock Faster-Whisper model for testing adapter integration without downloading weights."""

    def transcribe(self, audio, **kwargs):
        class Segment:
            text = "mở trình duyệt chrome"

        return [Segment()], None


def test_argon_enhanced_whisper_integration():
    """Validates ArgonEnhancedWhisper processing flow with mock base model."""
    mock_base = MockWhisperModel()
    enhanced_whisper = ArgonEnhancedWhisper(
        whisper_model_instance=mock_base,
        enable_ps_hcf=True,
        enable_dm_hss=True,
        enable_medusa=True,
        enable_cgds=True,
    )

    # 16kHz sine wave audio frame (100ms)
    fs = 16000
    t = np.linspace(0, 0.1, int(fs * 0.1), endpoint=False)
    audio = (0.2 * np.sin(2 * np.pi * 200.0 * t)).astype(np.float32)

    output = enhanced_whisper.transcribe_streaming_buffer(audio, language="vi")

    assert isinstance(output, TranscriptionOutput)
    assert output.text == "mở trình duyệt chrome"
    assert output.language == "vi"
    assert output.filter_mode in ("comb", "spectral_subtraction", "bypass")


def test_argon_constrained_slm_agent_reflex_resolution():
    """Validates that candidate commands matching Action Tree are resolved with Oracle vetting."""
    agent = ArgonConstrainedSLMAgent(confidence_threshold=0.50)

    # Standard volume mute command
    output = agent.resolve_and_verify(
        user_utterance="tắt tiếng máy tính",
        active_window_title="YouTube - Google Chrome",
        nlu_priors={"system_volume": 0.85},
    )

    assert isinstance(output, SLMResolutionOutput)
    assert output.status in ("RESOLVED_LOCAL_REFLEX", "RESOLVED_SLM_FALLBACK", "UNRESOLVED")
    assert output.oracle_passed is True


def test_argon_constrained_slm_agent_fallback():
    """Validates fallback to SLM callable when local reflex does not match."""
    agent = ArgonConstrainedSLMAgent(confidence_threshold=0.99)

    def dummy_slm(text, window):
        return {
            "action_name": "custom_llm_action",
            "parameters": {"query": text},
            "confidence": 0.85,
        }

    output = agent.resolve_and_verify(
        user_utterance="viết bài thơ về mùa thu hà nội",
        slm_fallback_callable=dummy_slm,
    )

    assert output.status == "RESOLVED_SLM_FALLBACK"
    assert output.action_name == "custom_llm_action"
    assert output.source == "external_slm"


def test_argon_kokoro_full_duplex_controller():
    """Validates ArgonKokoroFullDuplexController enqueuing and barge-in feeding."""
    recorded_chunks = []

    def mock_sink(chunk):
        recorded_chunks.append(chunk)

    controller = ArgonKokoroFullDuplexController(
        playback_sink_fn=mock_sink,
    )

    # Set controller in playback state to test full-duplex mic barge-in
    controller.audio_controller.on_playback_started("test_speech")
    assert controller.audio_controller.is_tts_playing is True

    # Feed ambient frame (typing noise during playback)
    d_amb = controller.feed_mic_frame(np.zeros(512, dtype=np.float32), is_voice_detected=False)
    assert d_amb == BargeInDecision.IGNORE_AMBIENT
    assert controller.audio_controller.ducking_gain == 1.0

    # Feed hard barge-in ("dừng lại" command)
    d_hard = controller.feed_mic_frame(
        np.ones(512, dtype=np.float32) * 0.05,
        is_voice_detected=True,
        transcript="dừng lại",
    )
    assert d_hard == BargeInDecision.HARD_BARGE_IN
    assert controller.audio_controller.is_tts_playing is False
    assert controller.audio_controller.ducking_gain == 0.125
