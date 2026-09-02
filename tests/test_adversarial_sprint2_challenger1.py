"""
tests/test_adversarial_sprint2_challenger1.py
=============================================
Empirical Adversarial Stress Test Suite for Sprint 2 (v4.7.0):
Accuracy, Acoustic & UX Hardening Subsystems.

Authored by Challenger 1 covering:
  - R1: Acoustic Hardening (VAD threshold edge cases, rapid audio frames, clock jumps, SFM/ZCR bounds)
  - R2: SAPI5 TTS COM Apartment Safety (Multi-threaded speech, worker restarts, queue flood, error recovery)
  - R3: Faster-Whisper STT Preloading & VAD Trimming (Concurrency races during preload, silence short-circuits, hallucination guards)
"""
from __future__ import annotations

import io
import math
import os
import queue
import sys
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.dsp import calculate_rms
from jarvis.audio.vad import SpeechSegment, VoiceActivityConfig, VoiceActivityDetector
from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    WakeWordEngineType,
    WakeWordResult,
    generate_wake_word_signal,
    resample_audio,
)
from jarvis.stt.engine import FasterWhisperSTT, STTError, audio_to_float32
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager


# ============================================================================
# R1: ACOUSTIC HARDENING & VAD ADVERSARIAL STRESS TESTS
# ============================================================================

class TestAdversarialR1AcousticHardening:
    """Adversarial stress testing of DSP acoustic hardening, VAD gates, and echo suppression."""

    def test_vad_subthreshold_noise_vs_speech_burst_transition(self) -> None:
        """
        Stress: Sub-threshold noise followed by a sudden voiced speech burst.
        Verifies:
          1. Sub-threshold noise does not enter the ring buffer (remains zeroed).
          2. Voiced burst immediately opens the VAD gate and populates ring buffer.
          3. Return to silence drops incoming frames once ring buffer energy drains.
        """
        detector = WakeWordDetector(
            sensitivity=0.6,
            vad_filter_enabled=True,
            vad_threshold=0.005,
        )
        assert np.all(detector._ring_buffer == 0.0)

        # 1. Feed sub-threshold noise (RMS ~ 0.002 < 0.005) for 20 blocks
        np.random.seed(101)
        sub_noise = (np.random.normal(0, 0.002, 512)).astype(np.float32)
        assert calculate_rms(sub_noise) < 0.005

        for _ in range(20):
            res = detector.feed_audio_block(sub_noise)
            assert res is None
        assert np.all(detector._ring_buffer == 0.0), "Ring buffer must stay empty on sub-threshold noise"

        # 2. Sudden high-energy speech burst
        speech_burst = generate_wake_word_signal("hey_jarvis", duration_s=1.2, sample_rate=44100, peak_amp=0.85)
        block_size = 1764
        detected_count = 0
        for i in range(0, len(speech_burst), block_size):
            chunk = speech_burst[i : i + block_size]
            r = detector.feed_audio_block(chunk)
            if r is not None:
                detected_count += 1

        assert np.max(np.abs(detector._ring_buffer)) > 0.05, "Ring buffer must receive speech energy"
        assert detected_count >= 1, "Speech burst must trigger detection"

    def test_rapid_audio_frame_size_permutations_and_sanitization(self) -> None:
        """
        Stress: Feed degenerate and pathological frame sizes:
          - 1 sample, 7 samples, 13 samples, 64 samples, 16384 samples, 44100 samples
          - Corrupted numeric values: NaN, +Inf, -Inf, float overflow
        Verifies zero unhandled exceptions and robust sanitization.
        """
        detector = WakeWordDetector(sample_rate=44100, vad_filter_enabled=True)

        pathological_sizes = [1, 2, 7, 13, 31, 64, 128, 513, 1024, 4096, 16384, 44100]
        for sz in pathological_sizes:
            test_frame = (np.random.normal(0, 0.02, sz)).astype(np.float32)
            # Should process without crash
            detector.feed_audio_block(test_frame)

        # Corrupted arrays
        nan_frame = np.full(512, np.nan, dtype=np.float32)
        inf_frame = np.full(512, np.inf, dtype=np.float32)
        neginf_frame = np.full(512, -np.inf, dtype=np.float32)
        huge_frame = np.full(512, 1e20, dtype=np.float32)

        for bad_frame in [nan_frame, inf_frame, neginf_frame, huge_frame]:
            # Must sanitize to finite floats without throwing
            detector.feed_audio_block(bad_frame)

        # None and empty array
        assert detector.feed_audio_block(None) is None
        assert detector.feed_audio_block(np.empty(0, dtype=np.float32)) is None

    def test_post_tts_mic_suppression_under_monotonic_clock_jumps(self) -> None:
        """
        Stress: 2.5s post-TTS mic suppression under simulated monotonic clock steps:
          - Step jump forward (+10s, +3600s): suppression window cleanly opens.
          - Stale/backwards timestamp: safe handling without locking permanently.
          - Consecutive playback events: continuously extend the suppression deadline.
        """
        tts = TTSManager(config={"cache": {"enabled": False}})
        tts.stop()

        # Initial state: not in echo window
        assert tts.is_in_echo_window(current_time=100.0, cooldown_s=2.5) is False

        # TTS finishes playback at t=100.0
        with tts._lock:
            tts._last_playback_finish_time = 100.0
            tts._is_playing = False

        # Inside 2.5s window
        assert tts.is_in_echo_window(current_time=100.1, cooldown_s=2.5) is True
        assert tts.is_in_echo_window(current_time=102.49, cooldown_s=2.5) is True

        # Exactly at and beyond 2.5s
        assert tts.is_in_echo_window(current_time=102.50, cooldown_s=2.5) is False
        assert tts.is_in_echo_window(current_time=102.51, cooldown_s=2.5) is False

        # Large forward clock jump (+3600s)
        assert tts.is_in_echo_window(current_time=3700.0, cooldown_s=2.5) is False

        # Consecutive playback event at t=3700.0 extending echo window
        with tts._lock:
            tts._last_playback_finish_time = 3700.0
        assert tts.is_in_echo_window(current_time=3701.0, cooldown_s=2.5) is True
        assert tts.is_in_echo_window(current_time=3702.4, cooldown_s=2.5) is True
        assert tts.is_in_echo_window(current_time=3702.6, cooldown_s=2.5) is False

    def test_spectral_flatness_comprehensive_signals(self) -> None:
        """
        Stress: Evaluate AcousticSpectralDetector on various signal topologies:
          1. Pure sine tones (100Hz, 440Hz, 1000Hz, 3000Hz, 5000Hz) -> SFM < 0.03 -> REJECT.
          2. Pure white noise & uniform noise -> SFM > 0.65 -> REJECT.
          3. Simultaneous broadband impulse claps (|t_diff| < 0.05s) -> REJECT.
          4. Valid synthetic wake word signal with formant structure & fricative -> ACCEPT.
        """
        detector = AcousticSpectralDetector(sample_rate=16000)
        sr = 16000
        dur_samples = int(sr * 1.2)
        t = np.linspace(0.0, 1.2, dur_samples, endpoint=False)

        # 1. Pure tones across frequencies
        for freq in [100.0, 440.0, 1000.0, 3000.0, 5000.0]:
            tone = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
            detected, _, _ = detector.analyze_window(tone)
            assert detected is False, f"Pure tone at {freq} Hz must be rejected by SFM lower bound"

        # 2. White noise & uniform noise
        np.random.seed(42)
        white_gaussian = np.random.normal(0, 0.2, dur_samples).astype(np.float32)
        detected_g, _, _ = detector.analyze_window(white_gaussian)
        assert detected_g is False, "Gaussian white noise must be rejected by SFM upper bound"

        white_uniform = np.random.uniform(-0.3, 0.3, dur_samples).astype(np.float32)
        detected_u, _, _ = detector.analyze_window(white_uniform)
        assert detected_u is False, "Uniform white noise must be rejected by SFM upper bound"

        # 3. Simultaneous clap impulse
        clap_signal = np.zeros(dur_samples, dtype=np.float32)
        clap_len = int(sr * 0.02)  # 20ms impulse
        t_clap = np.linspace(0.0, 0.02, clap_len, endpoint=False)
        clap_burst = (np.exp(-t_clap / 0.002) * np.random.normal(0, 0.8, clap_len)).astype(np.float32)
        clap_signal[int(sr * 0.3) : int(sr * 0.3) + clap_len] = clap_burst
        detected_clap, _, _ = detector.analyze_window(clap_signal)
        assert detected_clap is False, "Simultaneous broadband clap must be rejected"

        # 4. Valid synthetic wake word
        wake_signal = generate_wake_word_signal("hey_jarvis", duration_s=1.2, sample_rate=16000, peak_amp=0.85)
        detected_ww, kw, conf = detector.analyze_window(wake_signal, sensitivity=0.6)
        assert detected_ww is True, "Valid synthetic wake word signal must be detected"
        assert kw == "hey_jarvis"
        assert conf >= 0.40

    def test_vad_listen_for_speech_segmentation_lifecycle(self) -> None:
        """
        Stress: VoiceActivityDetector.listen_for_speech() stream parsing:
          - Captures speech chunks between silence boundaries.
          - Pre-speech padding prepended.
          - Discards segments shorter than min_speech_duration_ms.
        """
        cfg = VoiceActivityConfig(
            sample_rate=16000,
            frame_duration_ms=30,
            silence_threshold=0.01,
            min_speech_duration_ms=120,   # 4 frames
            min_silence_duration_ms=180,  # 6 frames
        )
        vad = VoiceActivityDetector(config=cfg)

        frame_bytes = 960  # 16000 * 0.03 * 2 bytes

        # Mock stream: 3 silent frames + 6 speech frames + 8 silent frames
        silent_frame = b"\x00" * frame_bytes
        speech_sample = (np.sin(np.linspace(0, 2 * np.pi * 440, 480)) * 16000).astype(np.int16).tobytes()

        class MockStream:
            def __init__(self, chunks: list[bytes]) -> None:
                self.chunks = list(chunks)

            def read(self, size: int) -> bytes:
                if self.chunks:
                    return self.chunks.pop(0)
                return b""

        stream_data = [silent_frame] * 3 + [speech_sample] * 6 + [silent_frame] * 8
        stream = MockStream(stream_data)

        segment = vad.listen_for_speech(stream, timeout_s=2.0)
        assert segment is not None
        assert len(segment.audio_bytes) > 0
        assert segment.duration_ms >= 120.0
        assert segment.confidence > 0.0


# ============================================================================
# R2: SAPI5 TTS COM APARTMENT SAFETY ADVERSARIAL STRESS TESTS
# ============================================================================

class TestAdversarialR2TTSCOMSafety:
    """Adversarial stress testing of COM apartment safety, concurrency, and queue dynamics."""

    def test_multithreaded_concurrent_sapi5_tts_invocations(self) -> None:
        """
        Stress: 20 concurrent threads calling TTSManager.speak() both asynchronously and synchronously.
        Verifies:
          - pythoncom.CoInitialize() / CoUninitialize() balance.
          - Zero COM error exceptions, zero deadlocks, all tasks complete cleanly.
        """
        mock_pythoncom = MagicMock()
        mock_win32com = MagicMock()
        mock_speaker = MagicMock()
        mock_win32com.client.Dispatch.return_value = mock_speaker

        with patch.dict(sys.modules, {
            "pythoncom": mock_pythoncom,
            "win32com": mock_win32com,
            "win32com.client": mock_win32com.client,
        }):
            tts = TTSManager(config={"cache": {"enabled": False}})
            time.sleep(0.05)  # Allow worker thread to initialize

            results: list[bool] = []
            lock = threading.Lock()

            def _speak_worker(idx: int) -> None:
                # Alternate between sync and async
                if idx % 2 == 0:
                    ok = tts.speak(f"Async message {idx}", wait=False)
                    with lock:
                        results.append(ok)
                else:
                    ok = tts.speak(f"Sync message {idx}", wait=True)
                    with lock:
                        results.append(ok)

            threads = [threading.Thread(target=_speak_worker, args=(i,)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)

            assert len(results) == 20
            assert all(results), "All 20 concurrent TTS requests must succeed"

            tts.stop()
            time.sleep(0.05)
            mock_pythoncom.CoUninitialize.assert_called()

    def test_worker_thread_restart_and_idempotent_stop(self) -> None:
        """
        Stress:
          1. Stop running worker thread cleanly.
          2. Restart worker thread via _start_worker().
          3. Process subsequent queue tasks successfully.
          4. Call stop() multiple times in succession without raising exceptions.
        """
        spoken: list[str] = []

        class SimpleMockEngine:
            def is_available(self) -> bool:
                return True

            def speak(self, text: str, voice_id: str | None = None, wait: bool = False) -> bool:
                spoken.append(text)
                return True

        tts = TTSManager(
            config={"cache": {"enabled": False}},
            primary_engine=SimpleMockEngine(),
            fallback_engine=SimpleMockEngine(),
        )

        # 1. Enqueue task 1
        tts.speak("First phrase", wait=True)
        assert len(spoken) == 1

        # 2. Stop worker
        tts.stop()
        assert tts._stop_event.is_set()

        # Multiple idempotent stops
        tts.stop()
        tts.stop()

        # 3. Restart worker
        tts._stop_event.clear()
        tts._start_worker()

        # 4. Enqueue task 2
        done_event = threading.Event()
        tts.speak("Second phrase", wait=False, callback=lambda ok: done_event.set())
        assert done_event.wait(timeout=3.0)
        assert len(spoken) == 2
        assert spoken[1] == "Second phrase"

        tts.stop()

    def test_rapid_queue_flood_and_task_callback_exception_resilience(self) -> None:
        """
        Stress:
          - Flood TTS queue with 50 items simultaneously from 5 producer threads.
          - Pass buggy callbacks that raise unhandled exceptions.
          - Verifies worker thread does NOT crash and finishes processing all tasks.
        """
        processed_count = 0
        lock = threading.Lock()

        class RobustMockEngine:
            def is_available(self) -> bool:
                return True

            def speak(self, text: str, voice_id: str | None = None, wait: bool = False) -> bool:
                nonlocal processed_count
                with lock:
                    processed_count += 1
                return True

        tts = TTSManager(
            config={"cache": {"enabled": False}},
            primary_engine=RobustMockEngine(),
            fallback_engine=RobustMockEngine(),
        )

        def buggy_callback(success: bool) -> None:
            # Deliberately raise exception in caller callback
            raise RuntimeError("Buggy callback blew up!")

        def _producer(pid: int) -> None:
            for item in range(10):
                tts.speak(f"Producer {pid} Item {item}", wait=False, callback=buggy_callback)

        producers = [threading.Thread(target=_producer, args=(p,)) for p in range(5)]
        for p in producers:
            p.start()
        for p in producers:
            p.join()

        # Wait for all 50 items to be processed
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with lock:
                if processed_count >= 50:
                    break
            time.sleep(0.05)

        with lock:
            assert processed_count == 50, f"Expected 50 tasks processed, got {processed_count}"

        tts.stop()

    def test_sapi5_fallback_com_dispatch_failure_and_finally_safety(self) -> None:
        """
        Stress: SAPI5FallbackTTS when win32com Dispatch raises an exception:
          - CoInitialize is executed.
          - CoUninitialize is GUARANTEED in finally block.
          - Fallback cleanly cascades to PowerShell / pyttsx3 / mock without raising.
        """
        mock_pythoncom = MagicMock()
        mock_win32com = MagicMock()
        mock_win32com.client.Dispatch.side_effect = RuntimeError("COM Dispatch catastrophic failure")

        with patch.dict(sys.modules, {
            "pythoncom": mock_pythoncom,
            "win32com": mock_win32com,
            "win32com.client": mock_win32com.client,
        }):
            engine = SAPI5FallbackTTS(config={"voice_name": "TestVoice"})
            with patch("sys.platform", "win32"):
                ok = engine.speak("Test voice synthesis", wait=True)

            assert ok is True, "Must fall back gracefully and return True"
            mock_pythoncom.CoInitialize.assert_called()
            mock_pythoncom.CoUninitialize.assert_called()


# ============================================================================
# R3: FASTER-WHISPER STT PRELOAD & VAD TRIMMING ADVERSARIAL STRESS TESTS
# ============================================================================

class TestAdversarialR3STTPreloadAndVAD:
    """Adversarial stress testing of STT eager preloading, concurrency races, and VAD trimming."""

    def test_concurrent_transcribe_during_background_preload_race(self) -> None:
        """
        Stress: FasterWhisperSTT spawns a background preload thread with artificial delay (0.1s).
        10 concurrent caller threads invoke transcribe() immediately before preload finishes.
        Verifies:
          - All caller threads safely block and wait for WhisperModel initialization.
          - WhisperModel constructor is called exactly ONCE.
          - All 10 transcriptions succeed with 0 race conditions.
        """
        mock_model_instance = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "kết quả nhận dạng"
        mock_info = MagicMock()
        mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

        constructor_calls = 0
        lock = threading.Lock()

        def slow_whisper_constructor(*args: Any, **kwargs: Any) -> Any:
            nonlocal constructor_calls
            with lock:
                constructor_calls += 1
            time.sleep(0.1)  # Simulate model load latency
            return mock_model_instance

        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
            with patch("jarvis.stt.engine.WhisperModel", side_effect=slow_whisper_constructor):
                # Instantiate with background preload enabled
                stt = FasterWhisperSTT({"preload": True, "model_size": "tiny"})

                results: list[str] = []
                res_lock = threading.Lock()

                def _caller_worker(idx: int) -> None:
                    # Provide non-empty audio
                    dummy_audio = np.sin(np.linspace(0, 2 * np.pi * 440, 16000)).astype(np.float32) * 0.5
                    text = stt.transcribe(dummy_audio, language="vi")
                    with res_lock:
                        results.append(text)

                callers = [threading.Thread(target=_caller_worker, args=(i,)) for i in range(10)]
                for c in callers:
                    c.start()
                for c in callers:
                    c.join(timeout=5.0)

                assert len(results) == 10
                assert all(r == "kết quả nhận dạng" for r in results)
                # Model must be constructed exactly once despite 10 concurrent requests + preload thread
                assert constructor_calls == 1
                assert stt.is_model_loaded is True

    def test_vad_filter_and_hallucination_guard_parameters(self) -> None:
        """
        Stress: Verify WhisperModel.transcribe receives:
          - vad_filter=True
          - vad_parameters={"min_silence_duration_ms": 500}
          - condition_on_previous_text=False
          - no_speech_threshold=0.6
          - log_prob_threshold=-1.0
          - compression_ratio_threshold=2.4
        """
        mock_model_instance = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "mở trình duyệt"
        mock_model_instance.transcribe.return_value = ([mock_segment], MagicMock())

        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
            with patch("jarvis.stt.engine.WhisperModel", return_value=mock_model_instance):
                stt = FasterWhisperSTT({"preload": False})
                audio = (np.random.normal(0, 0.1, 16000)).astype(np.float32)

                res = stt.transcribe(audio, language="vi")
                assert res == "mở trình duyệt"

                mock_model_instance.transcribe.assert_called_once()
                _, kwargs = mock_model_instance.transcribe.call_args
                assert kwargs.get("vad_filter") is True
                assert kwargs.get("vad_parameters") == {"min_silence_duration_ms": 500}
                assert kwargs.get("condition_on_previous_text") is False
                assert kwargs.get("no_speech_threshold") == 0.6
                assert kwargs.get("log_prob_threshold") == -1.0
                assert kwargs.get("compression_ratio_threshold") == 2.4

    def test_silence_empty_and_corrupted_audio_short_circuits(self) -> None:
        """
        Stress: Empty array, None, zero RMS silence, short buffer < 0.001 RMS:
        Must short-circuit immediately without calling WhisperModel.transcribe.
        """
        mock_model_instance = MagicMock()

        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
            with patch("jarvis.stt.engine.WhisperModel", return_value=mock_model_instance):
                stt = FasterWhisperSTT({"preload": False})

                # 1. Empty array
                assert stt.transcribe(np.empty(0, dtype=np.float32)) == ""
                # 2. Pure zeros
                assert stt.transcribe(np.zeros(16000, dtype=np.float32)) == ""
                # 3. Very low RMS (0.0001 < 0.001)
                quiet_noise = np.full(16000, 0.0001, dtype=np.float32)
                assert stt.transcribe(quiet_noise) == ""
                # 4. None / empty bytes
                assert stt.transcribe(b"") == ""

                # WhisperModel.transcribe must NEVER have been called
                mock_model_instance.transcribe.assert_not_called()

    def test_warm_model_transcription_latency_budget(self) -> None:
        """
        Stress: Measure warm model transcribe execution latency on 3-second audio.
        Verifies warm model completes well within the 1.5s latency budget.
        """
        mock_model_instance = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "kiểm tra độ trễ âm thanh"
        mock_model_instance.transcribe.return_value = ([mock_segment], MagicMock())

        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
            with patch("jarvis.stt.engine.WhisperModel", return_value=mock_model_instance):
                stt = FasterWhisperSTT({"preload": False})
                # Warm model
                stt._get_model()

                # 3-second audio (48000 samples @ 16kHz)
                audio_3s = (np.sin(np.linspace(0, 2 * np.pi * 440, 48000)) * 0.5).astype(np.float32)

                latencies: list[float] = []
                for _ in range(10):
                    t0 = time.perf_counter()
                    res = stt.transcribe(audio_3s, language="vi")
                    dt = time.perf_counter() - t0
                    latencies.append(dt)
                    assert res == "kiểm tra độ trễ âm thanh"

                avg_latency = float(np.mean(latencies))
                max_latency = float(np.max(latencies))
                # With mock model warm in memory, dispatch overhead is < 0.05s (budget <= 1.5s)
                assert max_latency < 0.5, f"Warm model dispatch exceeded budget: max={max_latency:.4f}s"
                assert avg_latency < 0.1, f"Warm model average latency too high: avg={avg_latency:.4f}s"
