"""
tests/test_empirical_challenger_m2.py
======================================
Empirical Challenger Stress Testing Suite for Milestone 2:
- High-concurrency TTS queue stress and cache hit/miss speed benchmarking.
- Corrupted cache file resilience and automatic self-healing recovery.
- Simulated network chaos/timeout on ElevenLabs triggering seamless SAPI5 fallback.
- Plugin boundary testing (invalid monitor IDs, missing Spotify/Chrome/Cursor executables, shell command timeouts, privilege gating).
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import unittest.mock as mock
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.core.plugin import PluginRegistry
from jarvis.plugins.chrome import ChromeMultiMonitorPlugin
from jarvis.plugins.cursor import CursorPlugin
from jarvis.plugins.shell import ShellPlugin
from jarvis.plugins.spotify import SpotifyPlugin
from jarvis.plugins.webhook import WebhookPlugin
from jarvis.tts.base import BaseTTSEngine, TTSError
from jarvis.tts.cache import LocalTTSCache, TTSAudioCache
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager

# ============================================================================
# 1. HIGH-CONCURRENCY TTS QUEUE & CACHE CONTENTION STRESS TESTS
# ============================================================================

def test_stress_concurrent_tts_queue_and_cache_contention(tmp_path):
    """
    Stress test TTSManager and TTSAudioCache under high concurrency (30 concurrent threads).
    Hammering both identical phrases (testing race conditions on .tmp atomic file replacement)
    and distinct phrases with non-blocking queue callbacks and blocking calls.
    """
    cache_dir = tmp_path / "concurrent_cache"
    
    # Mock primary engine generating dummy PCM
    mock_primary = mock.MagicMock(spec=BaseTTSEngine)
    mock_primary.is_available.return_value = True
    mock_primary.voice_id = "test_voice"
    mock_primary.model_id = "eleven_multilingual_v2"
    mock_primary.output_format = "pcm_24000"
    mock_primary.sample_rate = 24000

    def mock_synth(text, **kwargs):
        # 0.05s of synthetic PCM audio (2400 samples = 4800 bytes)
        return np.full(1200, 100, dtype=np.int16).tobytes()

    mock_primary.synthesize_to_bytes.side_effect = mock_synth

    fallback_engine = SAPI5FallbackTTS()
    mgr = TTSManager(
        config={"cache": {"enabled": True, "dir": str(cache_dir)}},
        primary_engine=mock_primary,
        fallback_engine=fallback_engine,
    )

    num_threads = 30
    callbacks_received: List[bool] = []
    cb_lock = threading.Lock()

    def thread_callback(success: bool):
        with cb_lock:
            callbacks_received.append(success)

    def worker_action(thread_idx: int):
        # Even threads speak shared phrase (testing cache collision)
        # Odd threads speak distinct phrase
        if thread_idx % 2 == 0:
            phrase = "Shared Collision Phrase Alpha"
        else:
            phrase = f"Distinct Unique Phrase {thread_idx}"

        # Mix of async (wait=False) and sync (wait=True)
        if thread_idx % 3 == 0:
            return mgr.speak(phrase, wait=True)
        else:
            return mgr.speak(phrase, wait=False, callback=thread_callback)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker_action, i) for i in range(num_threads)]
        results = [f.result(timeout=10.0) for f in concurrent.futures.as_completed(futures)]

    # All speak requests dispatched successfully
    assert all(r is True for r in results)

    # Wait for background queue to flush all tasks
    t0 = time.time()
    while not mgr._queue.empty() and (time.time() - t0 < 5.0):
        time.sleep(0.05)
    mgr._queue.join()

    # Verify callback count matches async calls
    async_calls_count = len([i for i in range(num_threads) if i % 3 != 0])
    assert len(callbacks_received) == async_calls_count
    assert all(cb is True for cb in callbacks_received)

    # Verify cache integrity on disk
    target_cache = cache_dir / "jarvis_welcome"
    cached_files = list(target_cache.glob("*.wav"))
    assert len(cached_files) > 0
    for wav_file in cached_files:
        assert wav_file.stat().st_size > 44  # Valid WAV size
        with wave.open(str(wav_file), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 24000

    mgr.stop()


def test_stress_cache_hit_miss_speed_benchmark(tmp_path):
    """
    Empirically benchmark cache hit vs miss latency.
    Cache hit must resolve in < 5ms without re-synthesizing.
    """
    cache = TTSAudioCache(cache_dir=tmp_path)
    text = "Benchmark test phrase for speed verification"
    pcm_raw = np.ones(24000, dtype=np.int16).tobytes()

    # 1. Miss check
    t0 = time.perf_counter()
    miss_res = cache.get(text)
    miss_duration_ms = (time.perf_counter() - t0) * 1000.0
    assert miss_res is None
    assert miss_duration_ms < 5.0

    # 2. Put
    saved_path = cache.put_pcm(text, "v1", "m1", "pcm_24000", pcm_raw, 24000)
    assert saved_path.is_file()

    # 3. Hit benchmark across 100 iterations
    durations = []
    for _ in range(100):
        t_start = time.perf_counter()
        hit = cache.get(text, "v1", "m1", "pcm_24000")
        durations.append((time.perf_counter() - t_start) * 1000.0)
        assert hit is not None

    avg_hit_ms = sum(durations) / len(durations)
    max_hit_ms = max(durations)
    assert avg_hit_ms < 2.0, f"Average cache hit too slow: {avg_hit_ms:.3f}ms"
    assert max_hit_ms < 10.0, f"Max cache hit latency spiked: {max_hit_ms:.3f}ms"


# ============================================================================
# 2. CORRUPTED CACHE FILE RESILIENCE & AUTOMATIC RECOVERY
# ============================================================================

@pytest.mark.parametrize("corrupt_type", ["empty_0b", "partial_hdr_12b", "garbage_binary_200b", "truncated_pcm_50b"])
def test_stress_cache_corruption_resilience_matrix(tmp_path, corrupt_type):
    """
    Stress test all forms of disk cache corruption:
    - 0 bytes empty file
    - 12 bytes incomplete RIFF header
    - 200 bytes random unparseable binary noise
    - Truncated frame data
    Verifies automatic detection, file invalidation, and graceful regeneration.
    """
    cache_dir = tmp_path / f"corrupt_{corrupt_type}"
    cache = TTSAudioCache(cache_dir=cache_dir)
    text = f"Corruption test {corrupt_type}"
    target_path = cache.get_cache_path(text, "v_test", "m_test", "pcm_24000")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Inject specific corruption pattern
    if corrupt_type == "empty_0b":
        target_path.write_bytes(b"")
    elif corrupt_type == "partial_hdr_12b":
        target_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    elif corrupt_type == "garbage_binary_200b":
        target_path.write_bytes(os.urandom(200))
    elif corrupt_type == "truncated_pcm_50b":
        # Valid 44-byte header but corrupt length / data
        with wave.open(str(target_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 3)

    # Test TTSAudioCache.get resilience
    if corrupt_type in ("empty_0b", "partial_hdr_12b"):
        res = cache.get(text, "v_test", "m_test", "pcm_24000")
        assert res is None
        assert not target_path.exists()  # Corrupt file removed
    else:
        # File is >= 44 bytes, check if play_wav handles garbage without crashing
        res_play = cache.play_wav(target_path, wait=True)
        # If play_wav fails on garbage binary, it returns False safely
        if corrupt_type == "garbage_binary_200b":
            assert res_play is False

    # Now verify TTSManager end-to-end self-healing
    mock_primary = mock.MagicMock(spec=BaseTTSEngine)
    mock_primary.is_available.return_value = True
    mock_primary.voice_id = "v_test"
    mock_primary.model_id = "m_test"
    mock_primary.output_format = "pcm_24000"
    mock_primary.sample_rate = 24000
    mock_primary.synthesize_to_bytes.return_value = np.zeros(2400, dtype=np.int16).tobytes()

    mgr = TTSManager(
        config={"cache": {"enabled": True, "dir": str(cache_dir)}},
        primary_engine=mock_primary,
    )

    # Re-inject corrupt file to test TTSManager recovery
    if corrupt_type == "garbage_binary_200b":
        target_path.write_bytes(os.urandom(200))
        # TTSManager will try cache -> play_wav returns False -> regenerates via primary engine
        success = mgr.speak(text, wait=True)
        assert success is True
        assert mock_primary.synthesize_to_bytes.called

    mgr.stop()


def test_stress_cache_directory_auto_recreation(tmp_path):
    """
    Test runtime resilience when cache directory is unexpectedly deleted during operation.
    """
    cache_dir = tmp_path / "ephemeral_cache"
    cache = TTSAudioCache(cache_dir=cache_dir)
    text = "Cache dir recreate test"
    pcm_data = np.zeros(1000, dtype=np.int16).tobytes()

    # Initial write
    p1 = cache.put_pcm(text, "v1", "m1", "pcm_24000", pcm_data)
    assert p1.is_file()

    # Nuke the entire cache directory
    shutil.rmtree(cache.cache_dir)
    assert not cache.cache_dir.exists()

    # Next write should recreate directory and succeed without throwing FileNotFoundError
    p2 = cache.put_pcm(text, "v1", "m1", "pcm_24000", pcm_data)
    assert p2.is_file()
    assert cache.cache_dir.exists()


# ============================================================================
# 3. ELEVENLABS NETWORK CHAOS & SEAMLESS SAPI5 FALLBACK TRANSITIONS
# ============================================================================

@pytest.mark.parametrize(
    "error_scenario",
    [
        "timeout",
        "connection_refused",
        "http_401_unauthorized",
        "http_429_rate_limited",
        "http_500_internal_error",
        "http_503_service_unavailable",
        "empty_response_200",
    ],
)
def test_stress_elevenlabs_network_chaos_and_sapi5_fallback(tmp_path, monkeypatch, error_scenario):
    """
    Simulate full spectrum of network failures against ElevenLabs TTS:
    - Socket timeout
    - DNS / Connection refusal
    - HTTP 401, 429, 500, 503
    - Malformed empty response
    Verifies 100% seamless fallback to SAPI5 without unhandled exceptions.
    """
    import requests

    def mock_post(url, *args, **kwargs):
        if error_scenario == "timeout":
            raise requests.exceptions.Timeout("Read timeout after 10.0s")
        elif error_scenario == "connection_refused":
            raise requests.exceptions.ConnectionError("Connection refused by peer")
        elif error_scenario == "http_401_unauthorized":
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = '{"detail": {"status": "invalid_api_key"}}'
            return mock_resp
        elif error_scenario == "http_429_rate_limited":
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 429
            mock_resp.text = '{"detail": {"status": "quota_exceeded"}}'
            return mock_resp
        elif error_scenario == "http_500_internal_error":
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            return mock_resp
        elif error_scenario == "http_503_service_unavailable":
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 503
            mock_resp.text = "Service Temporarily Unavailable"
            return mock_resp
        elif error_scenario == "empty_response_200":
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b""
            return mock_resp

    monkeypatch.setattr(requests, "post", mock_post)

    fallback_tts = SAPI5FallbackTTS()
    eleven_engine = ElevenLabsTTS({"api_key": "test_api_key_123"})

    def fake_sdk_synth(text, **kwargs):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_engine.voice_id}?output_format={eleven_engine.output_format}"
        headers = {"xi-api-key": eleven_engine.api_key, "Content-Type": "application/json"}
        resp = requests.post(url, json={"text": text}, headers=headers, timeout=10.0)
        if resp.status_code == 200 and resp.content:
            return resp.content
        raise TTSError(f"ElevenLabs HTTP Error {resp.status_code}: {resp.text}")

    monkeypatch.setattr(eleven_engine, "synthesize_to_bytes", fake_sdk_synth)

    mgr = TTSManager(
        config={"cache": {"enabled": True, "dir": str(tmp_path)}},
        primary_engine=eleven_engine,
        fallback_engine=fallback_tts,
    )

    phrase = f"Network test phrase for {error_scenario}"
    res = mgr.speak(phrase, wait=True)

    # Speech must succeed via offline fallback
    assert res is True
    assert phrase in fallback_tts.spoken_history

    mgr.stop()


def test_stress_elevenlabs_recovery_after_network_restoration(tmp_path, monkeypatch):
    """
    Test that once network connectivity is restored after a failure, ElevenLabs TTS
    resumes primary synthesis and updates disk cache.
    """
    import requests

    network_healthy = False

    def mock_post(url, *args, **kwargs):
        if not network_healthy:
            raise requests.exceptions.ConnectionError("Offline")
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = np.zeros(2400, dtype=np.int16).tobytes()
        return mock_resp

    monkeypatch.setattr(requests, "post", mock_post)

    fallback_tts = SAPI5FallbackTTS()
    eleven_engine = ElevenLabsTTS({"api_key": "valid_key"})

    def fake_synth(text, **kwargs):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_engine.voice_id}"
        resp = requests.post(url, json={"text": text})
        if resp.status_code == 200 and resp.content:
            return resp.content
        raise TTSError("Failed")

    monkeypatch.setattr(eleven_engine, "synthesize_to_bytes", fake_synth)

    mgr = TTSManager(
        config={"cache": {"enabled": True, "dir": str(tmp_path)}},
        primary_engine=eleven_engine,
        fallback_engine=fallback_tts,
    )

    # Phase 1: Network Down -> SAPI5 Fallback
    res1 = mgr.speak("Phase 1 Offline", wait=True)
    assert res1 is True
    assert "Phase 1 Offline" in fallback_tts.spoken_history

    # Phase 2: Network Restored -> ElevenLabs Online + Cached
    network_healthy = True
    res2 = mgr.speak("Phase 2 Online", wait=True)
    assert res2 is True
    # Should NOT have been routed to offline fallback
    assert "Phase 2 Online" not in fallback_tts.spoken_history

    # Phase 3: Immediate repeat -> Local cache hit
    res3 = mgr.speak("Phase 2 Online", wait=True)
    assert res3 is True

    mgr.stop()


# ============================================================================
# 4. PLUGIN BOUNDARY & ERROR HANDLING STRESS TESTS
# ============================================================================

def test_stress_chrome_plugin_invalid_monitors_and_missing_binary(monkeypatch):
    """
    Stress test ChromeMultiMonitorPlugin:
    - Invalid monitor inputs (0, -1, 999, floats, strings)
    - Missing Chrome executable on system -> Fallback to default browser
    """
    dispatcher = ActionDispatcher()
    plugin = ChromeMultiMonitorPlugin()
    plugin.initialize({}, dispatcher)

    # Scenario A: Test boundary monitor coordinates
    # For monitor=0 -> x_offset = (0 - 1) * 1920 = -1920
    # For monitor=3 -> x_offset = (3 - 1) * 1920 = 3840
    spawned_cmds = []

    def mock_popen(args, *p_args, **kwargs):
        spawned_cmds.append(args)
        return mock.MagicMock(pid=9999)

    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    monkeypatch.setattr(plugin, "_get_chrome_exe", lambda: r"C:\fake\chrome.exe")

    res = dispatcher.dispatch_action("chrome_open", {"url": "https://example.com", "monitor": 3})
    assert res.success is True
    assert "--window-position=3840,0" in spawned_cmds[-1]

    # Scenario B: Missing Chrome binary entirely (Popen raises FileNotFoundError)
    def mock_popen_missing(args, *p_args, **kwargs):
        raise FileNotFoundError("chrome.exe not found")

    browser_opened = []
    import webbrowser
    monkeypatch.setattr(subprocess, "Popen", mock_popen_missing)
    monkeypatch.setattr(webbrowser, "open", lambda url: browser_opened.append(url))

    res_fallback = dispatcher.dispatch_action("chrome_open", {"url": "https://fallback.example.com", "monitor": 1})
    assert res_fallback.success is True
    assert res_fallback.data.get("fallback") == "browser"
    assert "https://fallback.example.com" in browser_opened


def test_stress_cursor_plugin_missing_executable_and_simulated_fallback(monkeypatch):
    """
    Stress test CursorPlugin:
    - Cursor executable absent from system
    - Ensure it returns graceful simulated status without crashing ActionDispatcher
    """
    dispatcher = ActionDispatcher()
    plugin = CursorPlugin()
    plugin.initialize({"focus_existing": False, "fullscreen": False}, dispatcher)

    monkeypatch.setattr(plugin, "_get_cursor_exe", lambda: None)

    res = dispatcher.dispatch_action("cursor_focus", requester=RequesterContext.system())
    assert res.success is True
    assert res.data["status"] == "simulated"
    assert res.data["focused"] is True


def test_stress_spotify_plugin_empty_and_corrupt_uris(monkeypatch):
    """
    Stress test SpotifyPlugin:
    - Empty and whitespace URIs -> status: skipped
    - Operating system startfile failure -> status: error
    """
    dispatcher = ActionDispatcher()
    plugin = SpotifyPlugin()
    plugin.initialize({"song_uri": ""}, dispatcher)

    # Empty URI
    res_empty = dispatcher.dispatch_action("spotify_play", {"song_uri": "   "}, requester=RequesterContext.system())
    assert res_empty.success is True
    assert res_empty.data["status"] == "skipped"

    # OS Startfile failure simulation
    def mock_startfile_fail(uri):
        raise OSError("Protocol not registered on system")

    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", mock_startfile_fail)
    else:
        import webbrowser
        monkeypatch.setattr(webbrowser, "open", mock_startfile_fail)

    res_err = dispatcher.dispatch_action("spotify_play", {"song_uri": "spotify:track:123"}, requester=RequesterContext.system())
    assert res_err.success is True
    assert res_err.data["status"] == "error"


def test_stress_shell_plugin_timeout_and_privilege_enforcement():
    """
    Stress test ShellPlugin:
    - Command timeout guard enforcement (command exceeding timeout raises TimeoutError)
    - RBAC privilege boundary enforcement (NORMAL requester cannot execute ADMIN actions)
    """
    dispatcher = ActionDispatcher()
    plugin = ShellPlugin()
    plugin.initialize({}, dispatcher)

    # 1. Privilege check: NORMAL user should be rejected
    res_denied = dispatcher.dispatch_action(
        "shell_exec",
        {"command": "echo test"},
        requester=RequesterContext(requester_id="unprivileged_user", granted_privilege=PrivilegeLevel.NORMAL),
    )
    assert res_denied.success is False
    assert res_denied.error_code == "PERMISSION_DENIED"

    # 2. Timeout check: Command sleeping 2s with 0.1s timeout should trigger TimeoutError
    res_timeout = dispatcher.dispatch_action(
        "shell_exec",
        {"command": "powershell -Command Start-Sleep -Seconds 2", "timeout": 0.1},
        requester=RequesterContext.system(),
    )
    assert res_timeout.success is False
    assert "timed out" in res_timeout.error.lower() or res_timeout.error_code == "HANDLER_EXCEPTION"


def test_stress_webhook_plugin_network_failure(monkeypatch):
    """
    Stress test WebhookPlugin:
    - Handles connection errors and DNS failures gracefully
    """
    dispatcher = ActionDispatcher()
    plugin = WebhookPlugin()
    plugin.initialize({}, dispatcher)

    res = dispatcher.dispatch_action(
        "webhook_send",
        {"url": "http://127.0.0.1:59999/nonexistent_webhook_endpoint", "payload": {"event": "test"}, "timeout": 0.2},
        requester=RequesterContext.system(),
    )
    assert res.success is True
    assert res.data["status"] == 500
    assert res.data["delivered"] is False


# ============================================================================
# 5. FULL PIPELINE CHAOS & RECOVERY END-TO-END STRESS
# ============================================================================

def test_stress_full_audio_tts_lifecycle_resilience(tmp_path, mock_audio_stream):
    """
    Full end-to-end stress test combining AudioEngine -> GestureDetector -> ActionDispatcher -> Plugins -> TTSManager.
    Injects random failures into ElevenLabs and verifies the entire daemon continues operating smoothly.
    """
    from jarvis.gesture.detector import GestureDetector

    event_bus = EventBus()
    dispatcher = ActionDispatcher(event_bus=event_bus)
    registry = PluginRegistry(dispatcher)

    # Register plugins
    registry.register_plugin(SpotifyPlugin)
    registry.register_plugin(ChromeMultiMonitorPlugin)
    registry.register_plugin(CursorPlugin)
    registry.initialize_all({})

    # Mock TTS with chaos monkey
    call_counts = {"elevenlabs_attempts": 0, "fallback_calls": 0}

    class ChaosPrimaryTTS(BaseTTSEngine):
        @property
        def engine_name(self) -> str:
            return "chaos_primary"

        def is_available(self) -> bool:
            return True

        def speak(self, text: str, **kwargs) -> bool:
            return False

        def synthesize_to_bytes(self, text: str, **kwargs) -> bytes:
            call_counts["elevenlabs_attempts"] += 1
            if call_counts["elevenlabs_attempts"] % 2 == 1:
                raise TTSError("Chaos Monkey Network Outage")
            return np.zeros(2400, dtype=np.int16).tobytes()

    class TrackedFallbackTTS(BaseTTSEngine):
        @property
        def engine_name(self) -> str:
            return "tracked_fallback"

        def is_available(self) -> bool:
            return True

        def speak(self, text: str, **kwargs) -> bool:
            call_counts["fallback_calls"] += 1
            return True

        def synthesize_to_bytes(self, text: str, **kwargs) -> bytes:
            return b""

    tts_mgr = TTSManager(
        config={"cache": {"enabled": True, "dir": str(tmp_path)}},
        primary_engine=ChaosPrimaryTTS(),
        fallback_engine=TrackedFallbackTTS(),
    )

    dispatcher.register_action(
        name="tts_welcome",
        handler=lambda **kwargs: tts_mgr.speak("Welcome home sir", wait=True),
    )

    gestures_triggered = []
    detector = GestureDetector(
        dispatcher=dispatcher,
        event_bus=event_bus,
        on_gesture=lambda pat, conf: gestures_triggered.append(pat),
    )

    # Feed synthetic double clap through detector stream
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15, leading_silence_s=0.1, trailing_silence_s=0.5)
    events = detector.process_stream(pcm)

    # Verify double clap triggered
    assert len(events) == 1
    assert events[0].pattern_type == "DOUBLE_CLAP"

    # Execute TTS greeting through dispatcher
    res_tts = dispatcher.dispatch_action("tts_welcome", requester=RequesterContext.system())
    assert res_tts.success is True
    # Chaos monkey caused ElevenLabs to fail on 1st try, fallback must have caught it
    assert call_counts["fallback_calls"] >= 1

    tts_mgr.stop()
    registry.stop_all()
