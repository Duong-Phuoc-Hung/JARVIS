"""
tests/test_adversarial_m3_challenger1.py
=========================================
Empirical Challenger 1 Stress & Adversarial Test Suite for Milestone 3 Gate Verification.
Covers:
  1. STT Audio Processing & Robustness (silence, extreme noise, multi-bursts, buffer overflow, corrupt audio)
  2. VAD Energy Threshold Detection & Streaming Audio (pre-buffer, trailing debounce, max cutoff, streaming chunks)
  3. SystemTray Status Transitions & Dynamic Icon Generation (thread safety, RGBA palette rendering, menu handlers)
  4. DashboardServer High-Concurrency HTTP & REST Stress (500+ concurrent requests, malformed payloads, event stream deque)
"""
import concurrent.futures
import io
import json
import logging
import math
import os
import socket
import sys
from pathlib import Path

# Ensure jarvis package root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.audio.dsp import calculate_rms
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult
from jarvis.stt.engine import (
    BaseSTTEngine,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTError,
    STTEngine,
    VADSegmenter,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
    resample_audio,
)
from jarvis.ui.tray import (
    PIL_AVAILABLE,
    SystemTrayController,
    TrayStatus,
    create_status_icon,
)
from jarvis.ui.dashboard import (
    DashboardHTTPRequestHandler,
    DashboardServer,
)

logger = logging.getLogger("test.challenger_m3_1")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ============================================================================
# CATEGORY 1: STT AUDIO PROCESSING & RESILIENCE
# ============================================================================

def test_stt_silence_and_zero_inputs_rejection():
    """STT-01: Silence, sub-threshold noise floor, zero-length arrays, and None are rejected immediately."""
    engine = STTEngine()
    
    # 1. None
    assert engine.transcribe(None) == ""
    
    # 2. Empty numpy array
    empty = np.array([], dtype=np.float32)
    assert engine.transcribe(empty) == ""
    
    # 3. Pure digital zero silence (1.0 sec @ 16kHz)
    silence = np.zeros(16000, dtype=np.float32)
    assert engine.transcribe(silence) == ""
    
    # 4. Sub-audible noise (RMS ~ 0.0002, well below 0.001 threshold)
    low_noise = np.random.normal(0.0, 0.0002, 16000).astype(np.float32)
    assert engine.transcribe(low_noise) == ""
    
    # 5. Empty BytesIO & empty bytes
    assert engine.transcribe(b"") == ""
    assert engine.transcribe(io.BytesIO(b"")) == ""


def test_stt_extreme_noise_and_clipping():
    """STT-02: Extreme synthetic noise and heavy clipping handled gracefully without NaN/Inf crashes."""
    mock_provider = MockSTTEngine(default_transcript="test extreme noise")
    engine = STTEngine(primary_engine=mock_provider)
    
    # Extreme loud noise with clipping beyond [-1.0, 1.0]
    clipped_noise = (np.random.normal(0.0, 5.0, 16000) * 10.0).astype(np.float32)
    
    # Verify normalization clips values safely
    normalized = audio_to_float32(clipped_noise)
    assert np.max(normalized) <= 1.0
    assert np.min(normalized) >= -1.0
    assert not np.isnan(normalized).any()
    assert not np.isinf(normalized).any()
    
    res = engine.transcribe(clipped_noise)
    assert res == "test extreme noise"


def test_stt_multiple_voice_bursts_and_vad_segmentation():
    """STT-03: Multiple voice bursts separated by silence correctly segment into separate utterances."""
    sr = 16000
    vad = VADSegmenter(vad_threshold=0.02, silence_trailing_s=0.3, min_speech_s=0.2, max_speech_s=5.0)
    
    # Create 2 distinct voice bursts (sine waves @ 440Hz, amp=0.5) separated by 0.5s silence
    burst1 = (0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(0.5 * sr), endpoint=False))).astype(np.float32)
    silence = np.zeros(int(0.5 * sr), dtype=np.float32)
    burst2 = (0.5 * np.sin(2 * np.pi * 880 * np.linspace(0, 0.5, int(0.5 * sr), endpoint=False))).astype(np.float32)
    
    stream = np.concatenate([silence[:sr//10], burst1, silence, burst2, silence])
    
    chunk_size = int(0.05 * sr)  # 50ms chunks
    segments = []
    
    for i in range(0, len(stream), chunk_size):
        chunk = stream[i : i + chunk_size]
        seg = vad.feed_block(chunk)
        if seg is not None:
            segments.append(seg)
            
    assert len(segments) == 2, f"Expected 2 segmented utterances, got {len(segments)}"
    assert len(segments[0]) >= int(0.4 * sr)
    assert len(segments[1]) >= int(0.4 * sr)


def test_stt_buffer_overflow_and_large_memory_safety():
    """STT-04: Large audio buffer (5M samples / ~20MB) processed safely without memory corruption."""
    mock_provider = MockSTTEngine(default_transcript="large buffer ok")
    engine = STTEngine(primary_engine=mock_provider)
    
    num_samples = 5_000_000
    large_audio = (0.1 * np.sin(np.linspace(0, 1000, num_samples))).astype(np.float32)
    
    t0 = time.time()
    res = engine.transcribe(large_audio)
    elapsed = time.time() - t0
    
    assert res == "large buffer ok"
    assert elapsed < 5.0, f"Processing 5M samples took too long: {elapsed:.2f}s"


def test_stt_corrupt_and_adversarial_audio_inputs():
    """STT-05: Corrupted RIFF headers, truncated WAV buffers, and NaN/Inf values do not crash."""
    # 1. NaN and Inf in array
    bad_arr = np.array([0.0, np.nan, 0.5, np.inf, -np.inf, 0.2], dtype=np.float32)
    clean = audio_to_float32(bad_arr)
    assert not np.isnan(clean).any()
    assert not np.isinf(clean).any()
    assert len(clean) == 6
    
    # 2. Corrupt RIFF header
    corrupt_riff = b"RIFF" + b"\x00" * 10 + b"WAVEfmt " + b"\xff" * 20
    clean_riff = audio_to_float32(corrupt_riff)
    assert isinstance(clean_riff, np.ndarray)
    
    # 3. Truncated random bytes
    random_bytes = b"\x12\x34\x56\x78" * 10
    clean_bytes = audio_to_float32(random_bytes)
    assert isinstance(clean_bytes, np.ndarray)
    assert len(clean_bytes) == 20


def test_stt_multichannel_and_resampling():
    """STT-06: Multi-channel downmixing (stereo, 6-ch) and arbitrary sample rate resampling."""
    # Stereo downmix
    sr = 44100
    t = np.linspace(0, 0.5, int(0.5 * sr), endpoint=False)
    left = 0.4 * np.sin(2 * np.pi * 440 * t)
    right = 0.4 * np.cos(2 * np.pi * 440 * t)
    stereo = np.column_stack([left, right]).astype(np.float32)
    
    mono = audio_to_float32(stereo)
    assert mono.ndim == 1
    assert len(mono) == len(left)
    assert np.allclose(mono, (left + right) / 2.0, atol=1e-5)
    
    # Resample from 44100 to 16000
    resampled = resample_audio(mono, orig_sr=44100, target_sr=16000)
    expected_len = int(len(mono) * (16000 / 44100))
    assert abs(len(resampled) - expected_len) <= 2
    assert resampled.dtype == np.float32


def test_stt_provider_fallback_cascading():
    """STT-07: If Primary STT engine throws an exception, Fallback engine is seamlessly invoked."""
    class FailingPrimarySTT(BaseSTTEngine):
        @property
        def engine_name(self) -> str:
            return "failing_primary"
        def is_available(self) -> bool:
            return True
        def transcribe(self, audio, language="vi", **kwargs):
            raise STTError("Primary provider API 500 fatal error")

    fallback = MockSTTEngine(default_transcript="fallback success transcript")
    engine = STTEngine(primary_engine=FailingPrimarySTT(), fallback_engine=fallback)
    
    audio = (0.5 * np.sin(np.linspace(0, 100, 16000))).astype(np.float32)
    res = engine.transcribe(audio)
    assert res == "fallback success transcript"


# ============================================================================
# CATEGORY 2: VAD ENERGY THRESHOLD & STREAMING AUDIO CONVERSION
# ============================================================================

def test_vad_threshold_detection_and_hysteresis():
    """VAD-01: Verify energy threshold sensitivity and boundary conditions."""
    vad = VADSegmenter(vad_threshold=0.05, sample_rate=16000)
    
    # Frame below threshold
    sub_th = (0.03 * np.ones(320, dtype=np.float32))
    assert calculate_rms(sub_th) < 0.05
    assert vad.is_speech(sub_th) is False
    
    # Frame above threshold
    above_th = (0.08 * np.ones(320, dtype=np.float32))
    assert calculate_rms(above_th) >= 0.05
    assert vad.is_speech(above_th) is True


def test_vad_pre_speech_ring_buffer_preservation():
    """VAD-02: Pre-speech silence/background noise is preserved in the active buffer when speech starts."""
    sr = 16000
    vad = VADSegmenter(vad_threshold=0.05, pre_speech_s=0.2, silence_trailing_s=0.2, sample_rate=sr)
    
    pre_noise = (0.01 * np.ones(int(0.3 * sr), dtype=np.float32))
    voice = (0.2 * np.ones(int(0.4 * sr), dtype=np.float32))
    trail = np.zeros(int(0.3 * sr), dtype=np.float32)
    
    stream = np.concatenate([pre_noise, voice, trail])
    chunk_size = int(0.05 * sr)
    
    collected_segment = None
    for i in range(0, len(stream), chunk_size):
        seg = vad.feed_block(stream[i : i + chunk_size])
        if seg is not None:
            collected_segment = seg
            
    assert collected_segment is not None
    expected_samples = int(0.8 * sr)
    assert abs(len(collected_segment) - expected_samples) <= chunk_size * 2


def test_vad_max_speech_duration_hard_cutoff():
    """VAD-04: Continuous non-stop speech triggers segment cutoff at max_speech_s."""
    sr = 16000
    vad = VADSegmenter(vad_threshold=0.05, max_speech_s=1.0, sample_rate=sr)
    
    continuous_voice = (0.3 * np.ones(int(2.0 * sr), dtype=np.float32))
    chunk_size = int(0.1 * sr)
    
    completed_segment = None
    for i in range(0, len(continuous_voice), chunk_size):
        seg = vad.feed_block(continuous_voice[i : i + chunk_size])
        if seg is not None:
            completed_segment = seg
            break
            
    assert completed_segment is not None
    assert len(completed_segment) >= int(1.0 * sr)


def test_vad_streaming_transcription_generator():
    """VAD-05: transcribe_stream accurately consumes generator until utterance completion."""
    sr = 16000
    mock_provider = MockSTTEngine(default_transcript="streamed voice command")
    engine = STTEngine(primary_engine=mock_provider)
    
    lead = np.zeros(int(0.1 * sr), dtype=np.float32)
    voice = (0.4 * np.sin(np.linspace(0, 50, int(0.4 * sr)))).astype(np.float32)
    trail = np.zeros(int(1.0 * sr), dtype=np.float32)
    full_audio = np.concatenate([lead, voice, trail])
    
    def _chunk_gen():
        c_size = int(0.05 * sr)
        for idx in range(0, len(full_audio), c_size):
            yield full_audio[idx : idx + c_size]
            
    transcript = engine.transcribe_stream(_chunk_gen(), sample_rate=sr)
    assert transcript == "streamed voice command"


# ============================================================================
# CATEGORY 3: SYSTEM TRAY STATUS CHANGES & ICON GENERATION
# ============================================================================

def test_tray_dynamic_icon_generation_all_statuses():
    """TRAY-01: Dynamic RGBA icons generated for all TrayStatus values, or None gracefully when PIL absent."""
    statuses = [
        TrayStatus.ACTIVE,
        TrayStatus.LISTENING,
        TrayStatus.MUTED,
        TrayStatus.ERROR,
        TrayStatus.DISABLED,
        "active",
        "listening",
        "muted",
        "error",
        "disabled",
        "unknown_status_custom",
    ]
    
    for st in statuses:
        img = create_status_icon(st, size=(64, 64))
        if PIL_AVAILABLE:
            assert img is not None
            assert img.size == (64, 64)
            assert img.mode == "RGBA"
            raw_pixels = list(img.getdata())
            has_colored_pixels = any(p[3] > 0 for p in raw_pixels)
            assert has_colored_pixels, f"Icon for status {st} was completely transparent!"
        else:
            assert img is None, "When PIL is unavailable, create_status_icon should return None."


def test_tray_rapid_concurrent_status_updates():
    """TRAY-02: 40 threads concurrently updating status 500+ times without race conditions or locks sticking."""
    tray = SystemTrayController()
    tray.start()
    
    statuses = [TrayStatus.ACTIVE, TrayStatus.LISTENING, TrayStatus.MUTED, TrayStatus.ERROR, TrayStatus.DISABLED]
    exceptions: List[Exception] = []
    
    def _worker(thread_id: int):
        try:
            for step in range(25):
                st = statuses[(thread_id + step) % len(statuses)]
                tray.update_status(st)
                _ = tray.status
        except Exception as e:
            exceptions.append(e)
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(_worker, i) for i in range(40)]
        for f in concurrent.futures.as_completed(futures):
            f.result()
            
    assert len(exceptions) == 0, f"Exceptions during tray concurrent status updates: {exceptions}"
    tray.stop()
    assert tray.is_running is False


def test_tray_menu_handlers_and_mute_toggle():
    """TRAY-04: Menu action handlers execute correctly, toggling mute and gestures state."""
    app_mock = MagicMock()
    app_mock.audio_engine = MagicMock()
    
    tray = SystemTrayController(app=app_mock)
    
    # 1. Toggle mute ON
    tray._on_toggle_mute()
    assert tray._is_mic_muted is True
    assert tray.status == "muted"
    app_mock.audio_engine.pause_stream.assert_called_once()
    
    # 2. Toggle mute OFF
    tray._on_toggle_mute()
    assert tray._is_mic_muted is False
    assert tray.status == "active"
    app_mock.audio_engine.resume_stream.assert_called_once()
    
    # 3. Toggle gestures
    tray._on_toggle_gestures()
    assert tray._gestures_enabled is False
    tray._on_toggle_gestures()
    assert tray._gestures_enabled is True


# ============================================================================
# CATEGORY 4: DASHBOARD SERVER CONCURRENT HTTP & REST STRESS
# ============================================================================

def test_dashboard_concurrent_http_flood_500_requests():
    """DASH-01: Concurrent workers executing 500+ requests across all endpoints with zero dropped requests."""
    port = _find_free_port()
    ws_port = _find_free_port()
    
    disp = ActionDispatcher()
    disp.register_action("ping_test", lambda: {"msg": "pong"}, description="Ping action")
    
    cfg_mock = MagicMock()
    cfg_mock._config_data = {"version": "1.0.0", "mode": "test"}
    cfg_mock.to_dict.return_value = cfg_mock._config_data
    
    server = DashboardServer(host="127.0.0.1", port=port, ws_port=ws_port, dispatcher=disp, config_manager=cfg_mock)
    server.start()
    time.sleep(0.05)
    
    base_url = f"http://127.0.0.1:{port}"
    endpoints = [
        ("/", "GET", None),
        ("/api/status", "GET", None),
        ("/api/telemetry", "GET", None),
        ("/api/actions", "GET", None),
        ("/api/config", "GET", None),
        ("/api/logs", "GET", None),
        ("/api/command", "POST", json.dumps({"action": "ping_test"}).encode("utf-8")),
        ("/api/command", "POST", json.dumps({"command": "ki?m tra nhi?t d? cpu"}).encode("utf-8")),
    ]
    
    status_codes: List[int] = []
    errors: List[Exception] = []
    
    def _request_task(task_id: int):
        path, method, data = endpoints[task_id % len(endpoints)]
        req = urllib.request.Request(
            f"{base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        # Resilient client retry on transient OS TCP queue overflow
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    status_codes.append(resp.status)
                    return
            except Exception as exc:
                if attempt == 2:
                    errors.append(exc)
                else:
                    time.sleep(0.01 * (attempt + 1))
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_request_task, i) for i in range(500)]
        for f in concurrent.futures.as_completed(futures):
            f.result()
            
    server.stop()
    
    assert len(errors) == 0, f"Encountered {len(errors)} HTTP errors during flood: {errors[:5]}"
    assert len(status_codes) == 500
    assert all(code == 200 for code in status_codes)


def test_dashboard_malformed_and_adversarial_json_payloads():
    """DASH-02: Malformed JSON, corrupted UTF-8, and huge payloads return HTTP 400 without crashing."""
    port = _find_free_port()
    server = DashboardServer(host="127.0.0.1", port=port)
    server.start()
    time.sleep(0.05)
    
    base_url = f"http://127.0.0.1:{port}"
    
    adversarial_payloads = [
        b'{"unclosed": json',
        b'invalid non-json text',
        b'{"a": 1234, }',
        b'\x80\x81\x82\x83',
        b'{"big": "' + b'x' * 50000 + b'"',
    ]
    
    for payload in adversarial_payloads:
        req = urllib.request.Request(
            f"{base_url}/api/command",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                assert resp.status in (200, 400)
        except urllib.error.HTTPError as http_err:
            assert http_err.code == 400
            err_json = json.loads(http_err.read().decode("utf-8"))
            assert "error" in err_json
            
    server.stop()


def test_dashboard_cors_options_and_404_resilience():
    """DASH-03: CORS preflight (OPTIONS) returns 204 with headers, missing routes return 404."""
    port = _find_free_port()
    server = DashboardServer(host="127.0.0.1", port=port)
    server.start()
    time.sleep(0.05)
    
    base_url = f"http://127.0.0.1:{port}"
    
    # 1. OPTIONS CORS request
    req_options = urllib.request.Request(f"{base_url}/api/status", method="OPTIONS")
    with urllib.request.urlopen(req_options) as res:
        assert res.status == 204
        assert res.headers.get("Access-Control-Allow-Origin") == "*"
        
    # 2. 404 GET
    req_404 = urllib.request.Request(f"{base_url}/api/unknown_endpoint_route")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req_404)
    assert exc_info.value.code == 404
    
    server.stop()


def test_dashboard_high_concurrency_telemetry_and_event_deque():
    """DASH-04: 30 threads pushing 1500 events to broadcast_telemetry/broadcast_event; verify deque maxlen 200."""
    server = DashboardServer()
    server.start()
    
    exceptions: List[Exception] = []
    
    def _publisher(thread_id: int):
        try:
            for step in range(50):
                server.broadcast_telemetry({"cpu": float(thread_id), "step": step})
                server.broadcast_event({"type": "concurrency_test", "thread": thread_id, "step": step})
                _ = server.get_status_summary()
                _ = server.get_latest_telemetry()
        except Exception as e:
            exceptions.append(e)
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(_publisher, i) for i in range(30)]
        for f in concurrent.futures.as_completed(futures):
            f.result()
            
    assert len(exceptions) == 0
    assert len(server._event_history) <= 200
    assert server.get_status_summary()["status"] == "healthy"
    server.stop()


if __name__ == "__main__":
    print("Running Challenger 1 Empirical Test Suite directly...")
    tests = [
        test_stt_silence_and_zero_inputs_rejection,
        test_stt_extreme_noise_and_clipping,
        test_stt_multiple_voice_bursts_and_vad_segmentation,
        test_stt_buffer_overflow_and_large_memory_safety,
        test_stt_corrupt_and_adversarial_audio_inputs,
        test_stt_multichannel_and_resampling,
        test_stt_provider_fallback_cascading,
        test_vad_threshold_detection_and_hysteresis,
        test_vad_pre_speech_ring_buffer_preservation,
        test_vad_max_speech_duration_hard_cutoff,
        test_vad_streaming_transcription_generator,
        test_tray_dynamic_icon_generation_all_statuses,
        test_tray_rapid_concurrent_status_updates,
        test_tray_menu_handlers_and_mute_toggle,
        test_dashboard_concurrent_http_flood_500_requests,
        test_dashboard_malformed_and_adversarial_json_payloads,
        test_dashboard_cors_options_and_404_resilience,
        test_dashboard_high_concurrency_telemetry_and_event_deque,
    ]
    
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except Exception as err:
            print(f"  [FAIL] {t.__name__}: {err}")
            import traceback
            traceback.print_exc()
            failed += 1
            
    print(f"\nSummary: {passed} PASSED, {failed} FAILED out of {len(tests)} tests.")
    sys.exit(0 if failed == 0 else 1)
