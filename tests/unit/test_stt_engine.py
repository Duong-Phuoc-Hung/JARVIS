"""
tests/unit/test_stt_engine.py
=============================
Unit tests for JARVIS Speech-to-Text (STT) Subsystem (F-14).
Covers:
  - Audio conversion helpers (audio_to_float32, float32_to_pcm16_wav_bytes, resample_audio)
  - Voice Activity Detection (VADSegmenter) state machine and buffers
  - Multi-provider implementations (OpenAIWhisperSTT, FasterWhisperSTT, WindowsSpeechSTT, MockSTTEngine)
  - Unified STTEngine coordinator, fallback cascade, streaming, and error isolation
"""
from __future__ import annotations

import io
import sys
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.dsp import calculate_rms
from jarvis.core.dispatcher import EventBus
from jarvis.stt.engine import (
    BaseSTTEngine,
    FasterWhisperSTT,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTError,
    STTEngine,
    VADSegmenter,
    WindowsSpeechSTT,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
    resample_audio,
)


# ============================================================================
# 1. AUDIO FORMAT & RESAMPLING CONVERSION TESTS
# ============================================================================

def test_resample_audio_linear_interpolation():
    """Test linear interpolation resampling between sample rates."""
    # 44100 Hz to 16000 Hz
    orig = np.sin(np.linspace(0, 2 * np.pi * 10, 44100, endpoint=False)).astype(np.float32)
    resampled = resample_audio(orig, 44100, 16000)
    assert len(resampled) == 16000
    assert resampled.dtype == np.float32

    # Identity when sample rates match
    same = resample_audio(orig, 44100, 44100)
    assert len(same) == 44100
    np.testing.assert_array_equal(orig, same)

    # Empty array
    empty = resample_audio(np.empty(0, dtype=np.float32), 44100, 16000)
    assert len(empty) == 0


def test_audio_to_float32_various_inputs(tmp_path):
    """Test conversion of various audio input formats to 1D float32 array."""
    # 1. None and empty
    assert len(audio_to_float32(None)) == 0
    assert len(audio_to_float32(np.array([]))) == 0

    # 2. 1D int16 array
    pcm16 = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
    f32_from_int = audio_to_float32(pcm16)
    assert f32_from_int.dtype == np.float32
    assert pytest.approx(f32_from_int[1], abs=0.01) == 0.5
    assert pytest.approx(f32_from_int[2], abs=0.01) == -0.5

    # 3. 2D stereo array -> downmixed to mono
    stereo = np.ones((100, 2), dtype=np.float32) * 0.4
    mono = audio_to_float32(stereo)
    assert mono.ndim == 1
    assert len(mono) == 100
    assert pytest.approx(mono[0]) == 0.4

    # 4. Raw PCM bytes
    raw_bytes = pcm16.tobytes()
    f32_from_bytes = audio_to_float32(raw_bytes)
    assert len(f32_from_bytes) == len(pcm16)

    # 5. In-memory WAV bytes
    wav_buf = float32_to_pcm16_wav_bytes(mono, sample_rate=16000)
    f32_from_wav_bytes = audio_to_float32(wav_buf.getvalue(), sample_rate=16000)
    assert len(f32_from_wav_bytes) == 100

    # 6. WAV file on disk
    file_path = tmp_path / "test_tone.wav"
    with open(file_path, "wb") as f:
        f.write(wav_buf.getvalue())
    f32_from_file = audio_to_float32(str(file_path), sample_rate=16000)
    assert len(f32_from_file) == 100


def test_float32_to_pcm16_wav_bytes():
    """Verify WAV container structure generated from float32 array."""
    samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    wav_io = float32_to_pcm16_wav_bytes(samples, sample_rate=16000)

    assert isinstance(wav_io, io.BytesIO)
    wav_bytes = wav_io.getvalue()
    assert wav_bytes.startswith(b"RIFF")

    with wave.open(wav_io, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == len(samples)


# ============================================================================
# 2. VAD SEGMENTER STATE MACHINE TESTS
# ============================================================================

def test_vad_segmenter_silence_detection(audio_synthesizer):
    """Test VAD is_speech detection on pure silence vs speech noise."""
    vad = VADSegmenter(vad_threshold=0.015, sample_rate=16000)

    silence = audio_synthesizer.generate_silence(0.1, sample_rate=16000)
    noise = audio_synthesizer.generate_noise(0.1, rms=0.05, sample_rate=16000)

    assert vad.is_speech(silence) is False
    assert vad.is_speech(noise) is True
    assert vad.is_speech(None) is False
    assert vad.is_speech(np.empty(0)) is False


def test_vad_segmenter_pre_buffer_and_utterance_completion(audio_synthesizer):
    """
    Test VAD state machine capturing pre-speech ring buffer and concluding
    utterance after trailing silence cutoff.
    """
    vad = VADSegmenter(
        vad_threshold=0.015,
        sample_rate=16000,
        silence_trailing_s=0.1,  # 100ms for fast test
        pre_speech_s=0.05,       # 50ms pre-speech
        min_speech_s=0.05,
    )

    frame_len = int(16000 * 0.02)  # 20ms frames
    silence_frame = audio_synthesizer.generate_silence(0.02, sample_rate=16000)
    voice_frame = audio_synthesizer.generate_noise(0.02, rms=0.04, sample_rate=16000)

    # 1. Feed 3 silence frames (pre-buffer accumulation)
    for _ in range(3):
        res = vad.feed_block(silence_frame)
        assert res is None

    # 2. Feed 5 voice frames (speech active)
    for _ in range(5):
        res = vad.feed_block(voice_frame)
        assert res is None

    # 3. Feed trailing silence until completion (6 frames = 120ms > 100ms)
    completed_segment = None
    for _ in range(6):
        res = vad.feed_block(silence_frame)
        if res is not None:
            completed_segment = res
            break

    assert completed_segment is not None
    assert isinstance(completed_segment, np.ndarray)
    assert len(completed_segment) > 0


def test_vad_segmenter_max_speech_hard_cutoff(audio_synthesizer):
    """Test VAD auto-cuts utterance when exceeding max_speech_s."""
    vad = VADSegmenter(
        vad_threshold=0.01,
        sample_rate=16000,
        max_speech_s=0.2,  # 200ms hard cutoff
        silence_trailing_s=1.0,
    )

    voice_frame = audio_synthesizer.generate_noise(0.05, rms=0.05, sample_rate=16000)

    # Feed voice frames exceeding 200ms
    completed = None
    for _ in range(6):
        res = vad.feed_block(voice_frame)
        if res is not None:
            completed = res
            break
        time.sleep(0.05)

    assert completed is not None


# ============================================================================
# 3. MULTI-PROVIDER STT TESTS
# ============================================================================

def test_mock_stt_engine_behavior(audio_synthesizer):
    """Test deterministic MockSTTEngine returns transcripts and tracks calls."""
    mock_stt = MockSTTEngine(default_transcript="kiểm tra nhiệt độ cpu")
    assert mock_stt.engine_name == "mock"
    assert mock_stt.is_available() is True
    assert "vi" in mock_stt.supported_languages

    # Silence returns ""
    silence = audio_synthesizer.generate_silence(0.3)
    assert mock_stt.transcribe(silence) == ""

    # Voice returns default transcript
    voice = audio_synthesizer.generate_noise(0.3, rms=0.03)
    text = mock_stt.transcribe(voice, language="vi")
    assert text == "kiểm tra nhiệt độ cpu"
    assert len(mock_stt.call_history) == 1


def test_openai_whisper_stt_mock_http(audio_synthesizer):
    """Test OpenAIWhisperSTT intercepts via mock_http."""
    engine = OpenAIWhisperSTT({"api_key": "test_openai_key"})
    assert engine.engine_name == "openai_whisper_api"
    assert engine.is_available() is True

    voice = audio_synthesizer.generate_noise(0.2, rms=0.03)

    # With mock_http object
    mock_http = MagicMock()
    mock_http.handle_whisper_transcription.return_value = "quét mạng nội bộ"
    res = engine.transcribe(voice, language="vi", mock_http=mock_http)
    assert res == "quét mạng nội bộ"
    mock_http.handle_whisper_transcription.assert_called_once()


def test_openai_whisper_stt_missing_key_raises_error(audio_synthesizer):
    """Test OpenAIWhisperSTT raises STTError when API key is missing."""
    engine = OpenAIWhisperSTT({"api_key": ""})
    assert engine.is_available() is False

    voice = audio_synthesizer.generate_noise(0.2, rms=0.03)
    with pytest.raises(STTError, match="API key missing"):
        engine.transcribe(voice)


def test_faster_whisper_and_windows_speech_providers():
    """Test FasterWhisperSTT and WindowsSpeechSTT properties."""
    fw = FasterWhisperSTT({"model_size": "tiny"})
    assert fw.engine_name == "faster_whisper"

    ws = WindowsSpeechSTT({"timeout_s": 2.0})
    assert ws.engine_name == "windows_speech"
    if sys.platform == "win32":
        assert ws.is_available() is True
    else:
        assert ws.is_available() is False


# ============================================================================
# 4. UNIFIED STTENGINE COORDINATOR & RESILIENCE TESTS
# ============================================================================

def test_stt_engine_auto_resolution():
    """Test STTEngine automatic provider resolution."""
    stt = STTEngine(provider="mock")
    assert isinstance(stt.primary_engine, MockSTTEngine)

    stt_auto = STTEngine(provider="auto")
    assert stt_auto.primary_engine is not None


def test_stt_engine_fallback_on_primary_failure(audio_synthesizer):
    """Test STTEngine catches primary engine failure and cascades to fallback."""
    failing_primary = MagicMock(spec=BaseSTTEngine)
    failing_primary.is_available.return_value = True
    failing_primary.engine_name = "failing_primary"
    failing_primary.transcribe.side_effect = RuntimeError("Cloud API 500 Outage")

    fallback = MockSTTEngine(default_transcript="fallback transcription successful")

    bus = EventBus()
    events = []
    bus.subscribe("stt.transcribed", lambda **ev: events.append(ev))

    coordinator = STTEngine(
        primary_engine=failing_primary,
        fallback_engine=fallback,
        event_bus=bus,
    )

    voice = audio_synthesizer.generate_noise(0.3, rms=0.03)
    result = coordinator.transcribe(voice)

    assert result == "fallback transcription successful"
    assert len(events) == 1
    assert events[0]["text"] == "fallback transcription successful"
    assert events[0]["engine"] == "mock"


def test_stt_engine_streaming_transcription(audio_synthesizer):
    """Test STTEngine.transcribe_stream consuming generator frames."""
    coordinator = STTEngine(provider="mock")

    def audio_stream_generator():
        # Pre-speech silence
        yield audio_synthesizer.generate_silence(0.04, sample_rate=16000)
        # Utterance
        yield audio_synthesizer.generate_noise(0.2, rms=0.04, sample_rate=16000)
        # Trailing silence
        yield audio_synthesizer.generate_silence(0.9, sample_rate=16000)

    result = coordinator.transcribe_stream(audio_stream_generator())
    assert "bật đèn phòng khách" in result


def test_stt_engine_feed_audio_block(audio_synthesizer):
    """Test STTEngine.feed_audio_block incremental frames."""
    coordinator = STTEngine(provider="mock")

    silence = audio_synthesizer.generate_silence(0.04, sample_rate=16000)
    voice = audio_synthesizer.generate_noise(0.2, rms=0.04, sample_rate=16000)
    trail = audio_synthesizer.generate_silence(0.9, sample_rate=16000)

    assert coordinator.feed_audio_block(silence) is None
    assert coordinator.feed_audio_block(voice) is None
    res = coordinator.feed_audio_block(trail)
    assert res == "bật đèn phòng khách"
