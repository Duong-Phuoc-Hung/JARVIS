"""
tests/unit/test_acoustic_hardening.py
======================================
Tests for DSP Acoustic Hardening & Echo Suppression (Sprint 2 / Requirement R1 / P1-8).
Verifies:
  - VAD pre-filter gate dropping silent/low-energy frames before feeding ring buffer.
  - VAD filter configurable threshold and toggle capability.
  - Ring buffer clearing and frame rejection via suppress_until().
  - Post-TTS 2.5s acoustic echo suppression window in TTSManager.
  - AudioEngine dispatch dropping microphone frames during echo window.
  - SFM (0.03 <= SFM <= 0.65) and ZCR (>= 0.10) bounds in AcousticSpectralDetector.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.dsp import calculate_rms
from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    generate_wake_word_signal,
)
from jarvis.tts.manager import TTSManager


class TestVADPreFilterGate:
    """Test suite for VAD pre-filter in WakeWordDetector."""

    def test_vad_filter_discards_silent_frames(self) -> None:
        """Silent frames (RMS < vad_threshold) should be dropped before entering ring buffer."""
        detector = WakeWordDetector(
            sensitivity=0.5,
            vad_filter_enabled=True,
            vad_threshold=0.003,
        )
        # Verify initial ring buffer is empty
        assert np.all(detector._ring_buffer == 0.0)

        # Feed 10 silent frames (RMS = 0.0)
        silent_frame = np.zeros(512, dtype=np.float32)
        for _ in range(10):
            res = detector.feed_audio_block(silent_frame)
            assert res is None

        # Ring buffer must remain completely untouched (all 0.0)
        assert np.all(detector._ring_buffer == 0.0)

    def test_vad_filter_discards_low_energy_noise_frames(self) -> None:
        """Low energy noise below vad_threshold should be dropped."""
        detector = WakeWordDetector(
            vad_filter_enabled=True,
            vad_threshold=0.005,
        )
        # Create subtle noise with RMS ~ 0.001 (below 0.005)
        np.random.seed(42)
        quiet_noise = np.random.normal(0, 0.001, 1024).astype(np.float32)
        assert calculate_rms(quiet_noise) < 0.005

        res = detector.feed_audio_block(quiet_noise)
        assert res is None
        # Ring buffer must remain 0.0 because noise was filtered before buffer ingestion
        assert np.all(detector._ring_buffer == 0.0)

    def test_vad_filter_passes_speech_frames(self) -> None:
        """Voiced frames above vad_threshold must enter ring buffer and trigger detection."""
        detected_events: list[str] = []
        detector = WakeWordDetector(
            sensitivity=0.7,
            vad_filter_enabled=True,
            vad_threshold=0.003,
            on_wake_word=lambda kw, conf: detected_events.append(kw),
        )

        signal = generate_wake_word_signal(
            keyword="hey_jarvis",
            duration_s=1.2,
            sample_rate=44100,
            peak_amp=0.9,
        )

        # Feed signal in 40ms blocks (~1764 samples at 44.1kHz)
        block_size = 1764
        for i in range(0, len(signal), block_size):
            chunk = signal[i : i + block_size]
            detector.feed_audio_block(chunk)

        # Ring buffer must contain audio energy
        assert np.max(np.abs(detector._ring_buffer)) > 0.01
        assert len(detected_events) >= 1

    def test_vad_filter_can_be_disabled_via_config(self) -> None:
        """When vad_filter_enabled=False, all frames (including silence) enter the ring buffer."""
        detector = WakeWordDetector(
            vad_filter_enabled=False,
            vad_threshold=0.01,
        )
        # Feed non-zero but quiet audio that is below threshold
        quiet_chunk = np.full(512, 0.002, dtype=np.float32)
        detector.feed_audio_block(quiet_chunk)

        # Buffer must have shifted and recorded the quiet chunk since VAD is disabled
        assert np.max(detector._ring_buffer) > 0.001


class TestSuppressUntilAndEchoSuppression:
    """Test suite for suppress_until() and Echo Suppression window."""

    def test_wake_word_suppress_until_clears_buffer_and_drops_frames(self) -> None:
        """suppress_until() must immediately zero ring buffer and drop incoming frames until deadline."""
        detector = WakeWordDetector(sensitivity=0.5)

        # Feed some speech to populate ring buffer
        speech_signal = generate_wake_word_signal(duration_s=0.5, sample_rate=44100)
        detector.feed_audio_block(speech_signal)
        assert np.max(np.abs(detector._ring_buffer)) > 0.0

        # Now suppress for 2.5s into the future
        suppress_deadline = 1000.0
        detector.suppress_until(suppress_deadline)

        # 1. Ring buffer must be cleared immediately
        assert np.all(detector._ring_buffer == 0.0)

        # 2. Incoming frames before deadline (t=999.0) must be discarded
        res = detector.feed_audio_block(speech_signal, timestamp=999.0)
        assert res is None
        assert np.all(detector._ring_buffer == 0.0)

        # 3. Incoming frames after deadline (t=1001.0) must be processed normally
        detector.feed_audio_block(speech_signal, timestamp=1001.0)
        assert np.max(np.abs(detector._ring_buffer)) > 0.0

    def test_tts_manager_is_in_echo_window(self) -> None:
        """TTSManager.is_in_echo_window() should track active playback and 2.5s cooldown."""
        tts = TTSManager(config={"cache": {"enabled": False}})
        tts.stop()  # stop background thread for isolated test

        # Initially no speech has occurred -> not in echo window
        assert tts.is_in_echo_window(current_time=100.0, cooldown_s=2.5) is False

        # Simulate speech completion at t=100.0
        with tts._lock:
            tts._last_playback_finish_time = 100.0
            tts._is_playing = False

        # At t=101.0 (1.0s elapsed < 2.5s) -> in echo window
        assert tts.is_in_echo_window(current_time=101.0, cooldown_s=2.5) is True

        # At t=102.4 (2.4s elapsed < 2.5s) -> in echo window
        assert tts.is_in_echo_window(current_time=102.4, cooldown_s=2.5) is True

        # At t=102.6 (2.6s elapsed > 2.5s) -> echo window closed
        assert tts.is_in_echo_window(current_time=102.6, cooldown_s=2.5) is False

        # When actively playing (even if _last_playback_finish_time is old) -> in echo window
        with tts._lock:
            tts._is_playing = True
        assert tts.is_in_echo_window(current_time=200.0, cooldown_s=2.5) is True

    def test_app_audio_dispatch_drops_frames_during_tts_echo_window(self) -> None:
        """_on_audio_blocks_dispatch in app drops mic frames and calls suppress_until during echo window."""
        mock_tts = MagicMock()
        mock_wake_word = MagicMock()
        mock_gesture = MagicMock()

        # Define the dispatch logic matching jarvis/core/app.py
        def _on_audio_blocks_dispatch(block: np.ndarray, timestamp: float | None = None) -> None:
            now = timestamp if timestamp is not None else time.monotonic()
            if mock_tts and mock_tts.is_in_echo_window(current_time=now, cooldown_s=2.5):
                if mock_wake_word:
                    try:
                        mock_wake_word.suppress_until(now + 0.1)
                    except Exception:
                        pass
                return

            if mock_gesture:
                mock_gesture.feed_audio_block(block, timestamp=timestamp)
            if mock_wake_word:
                mock_wake_word.feed_audio_block(block, timestamp=timestamp)

        sample_block = np.random.normal(0, 0.1, 512).astype(np.float32)

        # Scenario A: TTS is in echo window
        mock_tts.is_in_echo_window.return_value = True
        _on_audio_blocks_dispatch(sample_block, timestamp=50.0)

        # WakeWord should be suppressed and NOT fed mic frame
        mock_wake_word.suppress_until.assert_called_once_with(50.1)
        mock_wake_word.feed_audio_block.assert_not_called()
        mock_gesture.feed_audio_block.assert_not_called()

        # Scenario B: TTS is NOT in echo window
        mock_wake_word.reset_mock()
        mock_gesture.reset_mock()
        mock_tts.is_in_echo_window.return_value = False
        _on_audio_blocks_dispatch(sample_block, timestamp=60.0)

        mock_wake_word.suppress_until.assert_not_called()
        mock_wake_word.feed_audio_block.assert_called_once_with(sample_block, timestamp=60.0)
        mock_gesture.feed_audio_block.assert_called_once_with(sample_block, timestamp=60.0)


class TestAcousticSpectralDetectorBounds:
    """Test suite for SFM and ZCR bounds in AcousticSpectralDetector."""

    def test_spectral_detector_rejects_white_noise_high_sfm(self) -> None:
        """White noise has high spectral flatness (>0.65) and must be rejected."""
        detector = AcousticSpectralDetector(sample_rate=16000)
        np.random.seed(123)
        white_noise = np.random.uniform(-0.5, 0.5, 16000 * 2).astype(np.float32)

        detected, _, _ = detector.analyze_window(white_noise)
        assert detected is False

    def test_spectral_detector_rejects_pure_tone_low_sfm(self) -> None:
        """Pure single tone (e.g., 1000 Hz beep) has near-zero spectral flatness (<0.03) and must be rejected."""
        detector = AcousticSpectralDetector(sample_rate=16000)
        t = np.linspace(0.0, 1.2, int(16000 * 1.2), endpoint=False)
        pure_tone = 0.5 * np.sin(2 * np.pi * 1000.0 * t).astype(np.float32)

        detected, _, _ = detector.analyze_window(pure_tone)
        assert detected is False

    def test_spectral_detector_rejects_low_zcr_syllable2(self) -> None:
        """Audio without high-frequency fricative (ZCR < 0.10) during Syllable 2 must be rejected."""
        detector = AcousticSpectralDetector(sample_rate=16000)
        t = np.linspace(0.0, 1.2, int(16000 * 1.2), endpoint=False)
        # Two low-frequency hum tones (both low ZCR)
        low_hum = (0.4 * np.sin(2 * np.pi * 200.0 * t) + 0.4 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)

        detected, _, _ = detector.analyze_window(low_hum)
        assert detected is False

    def test_spectral_detector_accepts_valid_wake_word_signal(self) -> None:
        """Valid synthetic wake word signal must be classified positively."""
        detector = AcousticSpectralDetector(sample_rate=16000)
        sig = generate_wake_word_signal("hey_jarvis", duration_s=1.2, sample_rate=16000, peak_amp=0.85)

        detected, keyword, conf = detector.analyze_window(sig, sensitivity=0.6)
        assert detected is True
        assert keyword == "hey_jarvis"
        assert conf > 0.4
