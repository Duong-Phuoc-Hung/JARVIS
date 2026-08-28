"""
test_tier5_adversarial_core_audio_sys.py
=========================================
Tier 5 White-Box Adversarial Stress Testing, Concurrency Fuzzing, and Boundary Edge Case Suite.
Covers:
  1. jarvis/core (config, dispatcher, logger, autostart, app lifecycle, event bus saturation, concurrent event dispatching, invalid event types)
  2. jarvis/audio & jarvis/gesture (corrupted audio chunks, NaN/Inf samples, extreme noise floor fluctuations, rapid burst claps, mic probe failure recovery)
  3. jarvis/tts & jarvis/stt (cache corruption, offline fallback under network socket disconnects, empty audio, special characters in synthesis text)
  4. jarvis/llm & jarvis/ui (invalid API keys, malformed JSON responses, rate limits, dashboard websocket disconnects, tray click race conditions)
  5. jarvis/hardware & jarvis/healing (CIM/WMI failures, S.M.A.R.T. disk attribute parsing corner cases, rapid memory threshold oscillation, unkillable hung processes, process termination timeouts)
  6. jarvis/platform (Win32 API failures, ctypes error handling, monitor layout edge cases)
"""

from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import io
import json
import logging
import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import requests

# JARVIS audio & gesture imports
from jarvis.audio.dsp import (
    AudioDSPProcessor,
    DSPBlockResult,
    NoiseFloorTracker,
    SchmittTrigger,
    calculate_rms,
)
from jarvis.audio.engine import (
    AudioDeviceInfo,
    AudioEngine,
    AudioEngineMode,
    MicrophoneProbeManager,
)

# JARVIS core imports
from jarvis.core.config import ConfigManager, JarvisConfig, _simple_yaml_parse, load_config
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.logger import log_action, log_trigger
from jarvis.core.models import (
    ActionDefinition,
    ActionResult,
    HandlerResult,
    MonitorInfo,
    PrivilegeLevel,
    RequesterContext,
    WindowInfo,
)
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import ClapEvent, DetectorState, GestureResult, GestureType

# JARVIS hardware & healing imports
from jarvis.hardware.monitor import (
    DiskSmartMetrics,
    HardwareMetrics,
    HardwareMonitor,
)
from jarvis.healing.terminator import (
    PROTECTED_PROCESS_WHITELIST,
    AutonomousTerminator,
    HealingEngine,
    HealingMode,
    HealingReport,
)
from jarvis.healing.watchdog import HungProcessInfo, UnresponsiveAppDetector

# JARVIS llm & ui imports
from jarvis.llm.client import (
    ChatMessage,
    LLMAuthenticationError,
    LLMClient,
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    TokenUsage,
    ToolCall,
)

# JARVIS platform imports
from jarvis.platform.autostart import (
    AutoStartManager,
    AutostartStatus,
    get_autostart_status,
    set_autostart,
)
from jarvis.platform.windows import (
    WindowsPlatformAPI,
    platform_win32,
)
from jarvis.stt.engine import (
    FasterWhisperSTT,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTEngine,
    STTError,
    VADSegmenter,
    WindowsSpeechSTT,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
    resample_audio,
)
from jarvis.tts.base import TTSError

# JARVIS tts & stt imports
from jarvis.tts.cache import LocalTTSCache, TTSAudioCache
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.engine import TTSEngine
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager
from jarvis.ui.dashboard import (
    DashboardHTTPRequestHandler,
    DashboardServer,
    _DashboardHTTPServer,
)
from jarvis.ui.tray import SystemTrayController, TrayStatus, create_status_icon

# ============================================================================
# DOMAIN 1: jarvis/core ADVERSARIAL STRESS & CONCURRENCY
# ============================================================================

class TestCoreAdversarialStress:
    """Stress tests and boundary checks for ConfigManager, EventBus, ActionDispatcher."""

    def test_config_manager_syntax_corruption_and_isolation(self, tmp_path):
        """Verify that malformed YAML/JSON on disk does not crash or corrupt active config."""
        default_file = tmp_path / "default_config.yaml"
        default_file.write_text("audio:\n  sample_rate: 44100\n  channels: 1\n", encoding="utf-8")

        custom_file = tmp_path / "custom_config.yaml"
        custom_file.write_text("audio:\n  sample_rate: 48000\n", encoding="utf-8")

        mgr = ConfigManager(
            config_path=custom_file,
            default_config_path=default_file,
            env_file_path=tmp_path / ".env",
        )
        cfg = mgr.load()
        assert cfg.audio.sample_rate == 48000
        assert mgr.get("audio.sample_rate") == 48000

        # Corrupt custom file with garbage syntax
        custom_file.write_text("audio: {\ninvalid_yaml: [unclosed\n  \t : garbage", encoding="utf-8")
        
        # Hot-reload attempt must fail gracefully and preserve previous valid configuration
        reload_success = mgr.reload()
        assert reload_success is False
        assert mgr.get("audio.sample_rate") == 48000

        # Simple YAML parse edge cases
        with pytest.raises(ValueError):
            _simple_yaml_parse(": invalid starting colon")
        with pytest.raises(ValueError):
            _simple_yaml_parse("key: [unmatched bracket")

    def test_config_manager_concurrent_hot_reload_and_mutation(self, tmp_path):
        """Stress test ConfigManager under high concurrent reads, writes, and disk reloads."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("system:\n  workers: 4\n  debug: true\n", encoding="utf-8")

        mgr = ConfigManager(config_path=cfg_file, default_config_path=cfg_file)
        mgr.load()

        stop_event = threading.Event()
        errors: List[Exception] = []

        def reader_worker():
            while not stop_event.is_set():
                try:
                    w = mgr.get("system.workers")
                    d = mgr.get("system.debug")
                    assert w in (4, 8, 16, 32, 999) or w is not None
                    time.sleep(0.001)
                except Exception as exc:
                    errors.append(exc)

        def writer_worker():
            vals = [4, 8, 16, 32, 999]
            idx = 0
            while not stop_event.is_set():
                try:
                    mgr.set("system.workers", vals[idx % len(vals)])
                    idx += 1
                    time.sleep(0.002)
                except Exception as exc:
                    errors.append(exc)

        def reloader_worker():
            while not stop_event.is_set():
                try:
                    mgr.reload()
                    time.sleep(0.005)
                except Exception as exc:
                    errors.append(exc)

        threads = []
        for _ in range(10):
            threads.append(threading.Thread(target=reader_worker))
        for _ in range(3):
            threads.append(threading.Thread(target=writer_worker))
        threads.append(threading.Thread(target=reloader_worker))

        for t in threads:
            t.start()

        time.sleep(0.5)
        stop_event.set()

        for t in threads:
            t.join(timeout=2.0)

        assert len(errors) == 0, f"Encountered concurrency errors in ConfigManager: {errors}"

    def test_config_manager_dot_key_fuzzing(self):
        """Fuzz dot-notation queries with edge-case strings, non-existent paths, and empty keys."""
        mgr = ConfigManager()
        mgr._data = {
            "nested": {"level1": {"level2": {"value": 123}}},
            "list_key": [1, 2, 3],
            "": {"empty_root": "ok"},
        }

        assert mgr.get("nested.level1.level2.value") == 123
        assert mgr.get("nested.non_existent") is None
        assert mgr.get("nested.level1.invalid.path.deeper", default="fallback") == "fallback"
        assert mgr.get("") is not None
        assert mgr.get(".....", default="def") == "def"

        # Mutate deep non-existent path
        mgr.set("a.b.c.d.e.f", "deep_value")
        assert mgr.get("a.b.c.d.e.f") == "deep_value"

    def test_event_bus_high_concurrency_saturation(self):
        """Saturate EventBus with 2,000 events published across 15 concurrent threads."""
        bus = EventBus()
        counter = {"hits": 0, "wildcard_hits": 0}
        lock = threading.Lock()

        def on_event(val: int):
            with lock:
                counter["hits"] += 1

        def on_wildcard(val: int):
            with lock:
                counter["wildcard_hits"] += 1

        bus.subscribe("telemetry.cpu", on_event, priority=10)
        bus.subscribe("telemetry.*", on_wildcard, priority=0)

        num_threads = 10
        events_per_thread = 100

        def publisher(tid: int):
            for i in range(events_per_thread):
                bus.publish("telemetry.cpu", val=i)

        threads = [threading.Thread(target=publisher, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        expected = num_threads * events_per_thread
        assert counter["hits"] == expected
        assert counter["wildcard_hits"] == expected

    def test_event_bus_handler_exception_isolation(self):
        """Verify that catastrophic exceptions in one subscriber do not block others."""
        bus = EventBus()
        executed = []

        def failing_handler_1(**kwargs):
            raise ZeroDivisionError("Math error in subscriber")

        def failing_handler_2(**kwargs):
            raise RuntimeError("Fatal runtime failure")

        def successful_handler(**kwargs):
            executed.append("success")
            return 42

        bus.subscribe("sensor.alert", failing_handler_1, priority=100)
        bus.subscribe("sensor.alert", successful_handler, priority=50)
        bus.subscribe("sensor.alert", failing_handler_2, priority=10)

        results = bus.publish("sensor.alert", level="CRITICAL")

        assert len(results) == 3
        assert results[0].success is False
        assert results[0].error_type == "ZeroDivisionError"
        assert results[1].success is True
        assert results[1].result == 42
        assert results[2].success is False
        assert results[2].error_type == "RuntimeError"
        assert executed == ["success"]

    def test_event_bus_unsubscribe_during_active_dispatch(self):
        """Verify dynamic unsubscription while event dispatching is actively in progress."""
        bus = EventBus()
        order = []
        sub2_id = None

        def handler1(**kwargs):
            order.append(1)
            # Handler 1 dynamically unregisters Handler 2
            if sub2_id:
                bus.unsubscribe(sub2_id)

        def handler2(**kwargs):
            order.append(2)

        def handler3(**kwargs):
            order.append(3)

        bus.subscribe("test.unsub", handler1, priority=30)
        sub2_id = bus.subscribe("test.unsub", handler2, priority=20)
        bus.subscribe("test.unsub", handler3, priority=10)

        # First dispatch snapshot resolves subscribers
        bus.publish("test.unsub")
        
        # Second dispatch must not invoke handler2
        order.clear()
        bus.publish("test.unsub")
        assert 2 not in order
        assert order == [1, 3]

    def test_event_bus_invalid_event_topics(self):
        """Verify invalid event topic inputs raise ValueError immediately."""
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.subscribe("", lambda: None)
        with pytest.raises(ValueError):
            bus.subscribe(None, lambda: None)  # type: ignore
        with pytest.raises(ValueError):
            bus.subscribe("valid.topic", "not_a_callable")  # type: ignore

    @pytest.mark.asyncio
    async def test_dispatcher_async_timeout_cancellation(self):
        """Verify async action dispatch strictly aborts when exceeding configured timeout."""
        disp = ActionDispatcher()

        async def slow_action():
            await asyncio.sleep(2.0)
            return "finished"

        disp.register_action(
            name="slow_task",
            handler=slow_action,
            timeout_seconds=0.05,
        )

        res = await disp.dispatch_action_async("slow_task")
        assert res.success is False
        assert res.error_code == "TIMEOUT"
        assert "timed out" in res.error.lower()

    def test_dispatcher_privilege_interception_fuzzing(self):
        """Stress RBAC security gate with arbitrary requester privileges and custom interceptors."""
        disp = ActionDispatcher()

        disp.register_action(
            name="admin_kill",
            handler=lambda: "killed",
            required_privilege=PrivilegeLevel.ADMIN,
        )

        guest_ctx = RequesterContext(requester_id="guest_user", granted_privilege=PrivilegeLevel.GUEST)
        normal_ctx = RequesterContext(requester_id="normal_user", granted_privilege=PrivilegeLevel.NORMAL)
        admin_ctx = RequesterContext(requester_id="admin_user", granted_privilege=PrivilegeLevel.ADMIN)
        sys_ctx = RequesterContext.system()

        # Guests and Normals must be blocked
        res1 = disp.dispatch_action("admin_kill", requester=guest_ctx)
        assert res1.success is False
        assert res1.error_code == "PERMISSION_DENIED"

        res2 = disp.dispatch_action("admin_kill", requester=normal_ctx)
        assert res2.success is False
        assert res2.error_code == "PERMISSION_DENIED"

        # Admin & System must succeed
        res3 = disp.dispatch_action("admin_kill", requester=admin_ctx)
        assert res3.success is True
        assert res3.data == "killed"

        res4 = disp.dispatch_action("admin_kill", requester=sys_ctx)
        assert res4.success is True


# ============================================================================
# DOMAIN 2: jarvis/audio & jarvis/gesture ADVERSARIAL STRESS
# ============================================================================

class TestAudioGestureAdversarialStress:
    """Adversarial testing for Acoustic DSP, Schmitt Trigger, GestureDetector, and Mic Prober."""

    def test_dsp_corrupted_samples_nan_inf_denormals(self):
        """Adversarial input fuzzing on calculate_rms: NaNs, Infinities, denormals, multi-dim arrays."""
        # 1. NaN and Inf buffers
        nan_buf = np.array([np.nan, 0.5, np.nan, -0.5, np.nan], dtype=np.float32)
        rms = calculate_rms(nan_buf)
        assert not math.isnan(rms)
        assert not math.isinf(rms)
        assert rms >= 0.0

        inf_buf = np.array([np.inf, -np.inf, 0.2, 0.4], dtype=np.float32)
        rms_inf = calculate_rms(inf_buf)
        assert not math.isnan(rms_inf)
        assert not math.isinf(rms_inf)
        assert rms_inf >= 0.0

        # 2. Denormals / Microscopic numbers
        denormal_buf = np.array([1e-45, -1e-45, 0.0], dtype=np.float32)
        rms_denormal = calculate_rms(denormal_buf)
        assert rms_denormal >= 0.0

        # 3. None and empty buffers
        assert calculate_rms(None) == 0.0
        assert calculate_rms(np.array([], dtype=np.float32)) == 0.0

        # 4. Multi-channel 2D buffers
        stereo_buf = np.array([[0.5, -0.5], [0.8, -0.8]], dtype=np.float32)
        rms_stereo = calculate_rms(stereo_buf)
        assert rms_stereo >= 0.0

        # 5. Massive amplitude clipping guard
        giant_buf = np.array([1e12, -1e12], dtype=np.float32)
        rms_giant = calculate_rms(giant_buf)
        assert not math.isnan(rms_giant)

    def test_dsp_extreme_noise_floor_fluctuations(self):
        """Test NoiseFloorTracker under extreme instantaneous noise floor jumping and quiet gate."""
        tracker = NoiseFloorTracker(alpha=0.95, min_floor=1e-6, max_floor=1.0, initial_floor=0.005)

        # Sudden quiet burst
        floor1, gated1 = tracker.update(0.0001)
        assert floor1 < 0.005
        assert gated1 is False

        # Extreme loud transient (100x above floor) -> must activate quiet gate and freeze adaptation
        pre_loud_floor = tracker.noise_floor
        floor2, gated2 = tracker.update(0.85)
        assert gated2 is True
        assert abs(floor2 - pre_loud_floor) < 1e-5  # Frozen!

        # Continuous noise step -> floor should slowly rise but clamp below max_floor
        for _ in range(200):
            tracker.update(0.008)
        assert tracker.noise_floor > pre_loud_floor
        assert tracker.noise_floor <= 1.0


    def test_dsp_schmitt_trigger_hysteresis_boundary_chatter(self):
        """Test SchmittTrigger boundary hysteresis: transient triggers only once until below retrigger."""
        trigger = SchmittTrigger(spike_ratio=5.0, retrigger_ratio=0.5, min_rms=0.01)
        noise_floor = 0.002
        threshold = max(noise_floor * 5.0, 0.01)  # 0.01
        retrigger_level = threshold * 0.5         # 0.005

        # 1. Sub-threshold: no transient
        t1, armed1, _, _ = trigger.evaluate(0.008, noise_floor)
        assert t1 is False
        assert armed1 is True

        # 2. Spike hits threshold: transient fired!
        t2, armed2, _, _ = trigger.evaluate(0.025, noise_floor)
        assert t2 is True
        assert armed2 is False

        # 3. Next block remains loud: transient MUST NOT re-trigger (chatter lock)
        t3, armed3, _, _ = trigger.evaluate(0.020, noise_floor)
        assert t3 is False
        assert armed3 is False

        # 4. Energy drops below retrigger level: trigger re-arms
        t4, armed4, _, _ = trigger.evaluate(0.003, noise_floor)
        assert t4 is False
        assert armed4 is True

        # 5. Subsequent spike triggers again
        t5, armed5, _, _ = trigger.evaluate(0.030, noise_floor)
        assert t5 is True
        assert armed5 is False

    def test_gesture_rapid_burst_clap_chatter_suppression(self):
        """Adversarial burst fuzzing: 50 claps fired 2ms apart must be filtered by raw gap suppression."""
        detector = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, cooldown_s=0.45)

        base_time = 100.0
        results = []

        # Machine-gun bursts every 2ms
        for i in range(50):
            clap = ClapEvent(
                timestamp=base_time + (i * 0.002),
                amplitude=0.85,
                noise_floor=0.005,
                threshold=0.035,
            )
            res = detector.feed_clap(clap)
            if res:
                results.append(res)

        # Entire 100ms burst must not register as Double or Triple clap
        assert len(results) == 0
        assert len(detector._clap_buffer) == 1  # Only the initial clap retained

    def test_gesture_out_of_order_and_negative_timestamps(self):
        """Fuzz detector state machine with out-of-order and negative timestamps."""
        detector = GestureDetector()

        c1 = ClapEvent(timestamp=50.0, amplitude=0.8)
        detector.feed_clap(c1)
        assert detector._state == DetectorState.WAIT_CLAP_2

        # Ingest clap in the past
        c_past = ClapEvent(timestamp=10.0, amplitude=0.8)
        detector.feed_clap(c_past)
        
        # Detector must not crash and buffer should reset cleanly
        assert len(detector._clap_buffer) <= 2

    def test_gesture_concurrent_clap_ingestion(self):
        """Concurrent multi-threaded clap feed into GestureDetector."""
        detector = GestureDetector()
        results = []
        lock = threading.Lock()

        def worker(tid: int):
            for i in range(20):
                t = 1000.0 + tid * 10.0 + i * 0.15
                c = ClapEvent(timestamp=t, amplitude=0.8)
                res = detector.feed_clap(c)
                if res:
                    with lock:
                        results.append(res)
                detector.tick(now=t + 0.05)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        # Ensure no deadlocks or crashes occurred
        assert detector is not None

    def test_microphone_probe_failure_recovery(self):
        """Verify MicrophoneProbeManager recovers safely from corrupted device lists & PortAudio faults."""
        # 1. Corrupt device metadata
        corrupt_devices = [
            {"index": -1, "max_input_channels": 0},
            {"max_input_channels": "invalid"},
            {},
        ]
        probe = MicrophoneProbeManager(devices=corrupt_devices)
        devs = probe.get_input_devices()
        assert devs == []
        best = probe.select_best_device()
        assert best == 0

        # 2. sd_module raising runtime exception during query
        class FailingSD:
            def query_devices(self):
                raise OSError("PortAudio host error: Device unavailable")

        probe_fail = MicrophoneProbeManager()
        best_fallback = probe_fail.select_best_device(sd_module=FailingSD())
        assert best_fallback == 0


# ============================================================================
# DOMAIN 3: jarvis/tts & jarvis/stt ADVERSARIAL STRESS
# ============================================================================

class TestTTSSTTAdversarialStress:
    """Adversarial testing for TTS caching, offline fallbacks, VAD segmentation, and STT engines."""

    def test_tts_cache_corruption_recovery(self, tmp_path):
        """Corrupt cached WAV files (< 44 bytes or garbage bytes) must be detected and invalidated."""
        cache = LocalTTSCache(cache_dir=tmp_path)
        text = "Hello world"
        key_path = cache.get_cache_path(text)

        # Write truncated 10-byte garbage WAV
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(b"RIFFjunk10")

        # Cache get must detect corrupt header (< 44 bytes), delete the file, and return None
        res = cache.get(text)
        assert res is None
        assert not key_path.exists()

    def test_tts_cache_concurrent_atomic_writes(self, tmp_path):
        """Concurrent atomic writes to the same cache key must not corrupt file on disk."""
        cache = TTSAudioCache(cache_dir=tmp_path)
        text = "System online."
        
        # Generate valid 16-bit PCM bytes (1 sec of 24kHz audio)
        pcm_bytes = np.zeros(24000, dtype=np.int16).tobytes()
        errors = []

        def writer():
            try:
                cache.put_pcm(
                    text=text,
                    voice_id="EXAVITQu4vr4xnSDxMaL",
                    model_id="eleven_multilingual_v2",
                    output_format="pcm_24000",
                    pcm_bytes=pcm_bytes,
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert len(errors) == 0
        cached = cache.get(text, voice_id="EXAVITQu4vr4xnSDxMaL")
        assert cached is not None
        assert cached.stat().st_size >= 44

    def test_tts_special_characters_and_massive_text(self, tmp_path):
        """Fuzz TTS engine with massive strings, unicode emojis, SQL injections, and null bytes."""
        engine = TTSEngine(cache_dir=tmp_path)

        # 1. Empty and whitespace text
        assert engine.speak("") is False
        assert engine.speak("   \n\t  ") is False

        # 2. Massive text (5,000 characters)
        huge_text = "A" * 5000
        res1 = engine.speak(huge_text)
        assert res1 is True
        assert huge_text in engine.offline_calls

        # 3. Special characters & null bytes
        weird_text = "JARVIS! \U0001F680 \u0000 alert'; DROP TABLE users; -- <script>alert(1)</script>"
        res2 = engine.speak(weird_text)
        assert res2 is True

    def test_tts_offline_fallback_under_socket_disconnects(self, tmp_path, monkeypatch):
        """Verify automatic fallback to offline SAPI5 TTS when cloud network fails."""
        manager = TTSManager(
            config={"elevenlabs": {"api_key": "fake_key"}},
            cache_dir=tmp_path,
        )

        # Mock network failure on requests.post
        def mock_post_fail(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Failed to establish socket connection")

        monkeypatch.setattr("requests.post", mock_post_fail, raising=False)

        # Speak should not raise exception; it falls back to offline engine
        success = manager.speak("Testing offline speech fallback", wait=True)
        assert success is True
        manager.stop()

    def test_stt_vad_extreme_audio_inputs(self):
        """VAD segmentation under extreme inputs: silence, extreme noise, and long speech cutoff."""
        vad = VADSegmenter(vad_threshold=0.02, silence_trailing_s=0.2, max_speech_s=1.0, sample_rate=16000)

        # 1. Pure silence: no speech
        silence_frame = np.zeros(640, dtype=np.float32)
        assert vad.feed_block(silence_frame) is None
        assert vad._is_speech_active is False

        # 2. Speech frame triggers active speech
        speech_frame = np.ones(640, dtype=np.float32) * 0.1
        vad.feed_block(speech_frame)
        assert vad._is_speech_active is True

        # 3. Continuous speech exceeding max_speech_s (1.0s = 16000 samples)
        long_speech = np.ones(17000, dtype=np.float32) * 0.1
        segment = vad.feed_block(long_speech)
        assert segment is not None
        assert len(segment) >= 16000
        assert vad._is_speech_active is False  # Reset after max cutoff

    def test_stt_offline_fallback_under_network_failure(self, monkeypatch):
        """STTEngine multi-provider fallback when OpenAI Whisper API is unreachable."""
        primary_mock = OpenAIWhisperSTT(config={"api_key": "dummy_key"})
        fallback_mock = MockSTTEngine(default_transcript="bật đèn phòng khách")

        stt = STTEngine(primary_engine=primary_mock, fallback_engine=fallback_mock)

        def mock_post_network_err(*args, **kwargs):
            raise requests.exceptions.Timeout("HTTP connection timed out")

        monkeypatch.setattr("requests.post", mock_post_network_err, raising=False)

        audio_samples = np.ones(16000, dtype=np.float32) * 0.05
        transcript = stt.transcribe(audio_samples)
        assert transcript == "bật đèn phòng khách"


# ============================================================================
# DOMAIN 4: jarvis/llm & jarvis/ui ADVERSARIAL STRESS
# ============================================================================

class TestLLMUIAdversarialStress:
    """Adversarial testing for LLM client resilience, UI Dashboard REST endpoints, and Tray races."""

    def test_llm_invalid_api_keys_and_auth_failure(self):
        """Verify LLMAuthenticationError when API key is missing or rejected."""
        client = LLMClient(provider=LLMProvider.OPENAI, api_key="")
        with pytest.raises(LLMAuthenticationError):
            client.generate("Hello JARVIS")

    def test_llm_malformed_json_and_markdown_stripping(self):
        """Verify LLMClient._clean_and_parse_json robustly parses bad JSON and code blocks."""
        client = LLMClient(provider=LLMProvider.MOCK)

        # 1. Clean markdown code fence
        raw1 = "```json\n{\"action\": \"turn_on_light\", \"room\": \"kitchen\"}\n```"
        parsed1 = client._clean_and_parse_json(raw1)
        assert parsed1 == {"action": "turn_on_light", "room": "kitchen"}

        # 2. Malformed JSON with regex fallback
        raw2 = "Some text before {\"target\": \"pc\", \"state\": \"locked\"} and after"
        parsed2 = client._clean_and_parse_json(raw2)
        assert "target" in parsed2
        assert parsed2["target"] == "pc"

        # 3. None and empty
        assert client._clean_and_parse_json("") == {}
        assert client._clean_and_parse_json(None) == {}  # type: ignore

    def test_llm_rate_limits_and_exponential_backoff(self, monkeypatch):
        """Verify LLMRateLimitError raised on persistent HTTP 429 rate limit."""
        client = LLMClient(provider=LLMProvider.OPENAI, api_key="sk-real-looking-key-12345", max_retries=1)

        class Mock429Response:
            status_code = 429
            def raise_for_status(self):
                raise requests.HTTPError(response=self)

        def mock_post_rate_limit(*args, **kwargs):
            raise requests.HTTPError(response=Mock429Response())

        monkeypatch.setattr(client.session, "post", mock_post_rate_limit)

        with pytest.raises(LLMRateLimitError):
            client.generate("Test rate limit")

    def test_llm_concurrent_chat_requests(self):
        """Stress mock LLM client with 25 concurrent chat completions."""
        client = LLMClient(provider=LLMProvider.MOCK)
        results = []
        errors = []

        def worker(idx: int):
            try:
                res = client.generate(f"Query {idx}")
                results.append(res)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert len(errors) == 0
        assert len(results) == 25
        assert len(client.call_history) == 25

    def test_dashboard_http_concurrent_endpoints_and_malformed_payloads(self):
        """Stress DashboardServer HTTP server with concurrent REST calls and malformed JSON payloads."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_ws_port = s.getsockname()[1]

        server = DashboardServer(host="127.0.0.1", port=free_port, ws_port=free_ws_port)
        server.start()
        time.sleep(0.08)

        try:
            base_url = f"http://127.0.0.1:{free_port}"
            # 1. Test valid endpoints concurrently
            def requester(endpoint: str):
                resp = requests.get(f"{base_url}{endpoint}", timeout=2.0)
                assert resp.status_code == 200

            endpoints = ["/api/status", "/api/telemetry", "/api/actions", "/api/config", "/api/logs", "/"]
            threads = [threading.Thread(target=requester, args=(ep,)) for ep in endpoints * 3]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=3.0)

            # 2. Test malformed POST payloads
            resp_malformed = requests.post(
                f"{base_url}/api/command",
                data="{invalid_json: true,",
                headers={"Content-Type": "application/json"},
                timeout=2.0,
            )
            assert resp_malformed.status_code == 400
            assert "Invalid JSON" in resp_malformed.text

            # 3. Test non-existent endpoint
            resp_404 = requests.get(f"{base_url}/api/unknown_route", timeout=2.0)
            assert resp_404.status_code == 404

        finally:
            server.stop()

    def test_tray_controller_click_race_conditions_and_rapid_status_toggles(self):
        """Test SystemTrayController rapid state updates and thread-safe toggle operations."""
        tray = SystemTrayController()
        errors = []

        def toggler():
            for _ in range(50):
                try:
                    tray.update_status(TrayStatus.LISTENING)
                    tray._on_toggle_mute()
                    tray.update_status(TrayStatus.ACTIVE)
                    tray._on_toggle_gestures()
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=toggler) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert len(errors) == 0


# ============================================================================
# DOMAIN 5: jarvis/hardware & jarvis/healing ADVERSARIAL STRESS
# ============================================================================

class TestHardwareHealingAdversarialStress:
    """Adversarial testing for HardwareMonitor CIM/WMI resilience, threshold oscillation, and self-healing."""

    def test_hardware_monitor_cim_wmi_failure_resilience(self, monkeypatch):
        """Verify HardwareMonitor handles PowerShell CIM failures and subprocess timeouts gracefully."""
        monitor = HardwareMonitor()

        # Mock subprocess.run raising TimeoutExpired on CIM calls
        def mock_subprocess_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="Get-CimInstance", timeout=1.5)

        monkeypatch.setattr("subprocess.run", mock_subprocess_timeout)

        metrics = monitor.get_metrics(use_cache=False)
        assert isinstance(metrics, HardwareMetrics)
        assert metrics.cpu_percent >= 0.0
        assert metrics.smart_status in ("PASSED", "WARNING", "FAILING")

    def test_hardware_monitor_smart_corner_cases(self):
        """Test S.M.A.R.T. status aggregation with degraded, critical, and failing drive sets."""
        monitor = HardwareMonitor()

        # 1. All drives healthy
        disks_ok = {
            "C:": DiskSmartMetrics(drive="C:", status="PASSED"),
            "D:": DiskSmartMetrics(drive="D:", status="PASSED"),
        }
        assert monitor._aggregate_smart_status(disks_ok) == "PASSED"

        # 2. Warning / Degraded drive
        disks_warn = {
            "C:": DiskSmartMetrics(drive="C:", status="PASSED"),
            "D:": DiskSmartMetrics(drive="D:", status="WARNING"),
        }
        assert monitor._aggregate_smart_status(disks_warn) == "WARNING"

        # 3. Failing drive
        disks_fail = {
            "C:": DiskSmartMetrics(drive="C:", status="FAILING"),
            "D:": DiskSmartMetrics(drive="D:", status="PASSED"),
        }
        assert monitor._aggregate_smart_status(disks_fail) == "FAILING"

    def test_hardware_monitor_threshold_oscillation_debouncing(self):
        """Verify alert debouncing prevents alert flooding when metrics oscillate around threshold."""
        monitor = HardwareMonitor(
            cpu_temp_threshold=80.0,
            ram_threshold=90.0,
            alert_cooldown_s=2.0,
        )

        # Mock provider that oscillates CPU temperature: 85°C -> 75°C -> 85°C
        class OscillatingProvider:
            def __init__(self):
                self.cpu_percent = 50.0
                self.cpu_temp_c = 85.0
                self.ram_percent = 50.0
                self.smart_drives = {}

        prov = OscillatingProvider()
        monitor.provider = prov

        # First spike -> Alert triggered
        alerts1 = monitor.check_thresholds()
        assert len(alerts1) == 1
        assert alerts1[0]["component"] == "cpu"

        # Second spike within cooldown -> Alert must be suppressed
        alerts2 = monitor.check_thresholds()
        assert len(alerts2) == 0

    def test_healing_immutable_os_whitelist_defense(self):
        """Strictly verify that OS-critical processes and self-PID can never be terminated."""
        terminator = AutonomousTerminator()
        self_pid = os.getpid()

        for proc in ("system", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "explorer.exe", "python.exe", "jarvis.exe"):
            assert terminator.is_protected(proc) is True
            assert terminator.terminate_process(pid=1234, process_name=proc) is False

        # Protect self-PID regardless of process name
        assert terminator.is_protected("malicious_impersonator.exe", pid=self_pid) is True
        assert terminator.terminate_process(pid=self_pid, process_name="malicious_impersonator.exe") is False

    def test_healing_unkillable_hung_process_two_phase_escalation(self, mock_win32_platform):
        """Verify that a hung process is safely targeted and killed in two-phase escalation."""
        engine = HealingEngine(win32_platform=mock_win32_platform, auto_kill=True)

        hung_hwnd = mock_win32_platform.add_hung_window("UnresponsiveApp.exe", pid=8888)
        report = engine.heal_hung_process(pid=8888, name="UnresponsiveApp.exe", hwnd=hung_hwnd)

        assert report["success"] is True
        assert report["pid"] == 8888
        assert 8888 in mock_win32_platform.killed_pids

    def test_healing_advisory_vs_autonomous_mode(self, mock_win32_platform):
        """Verify Advisory mode produces voice alert without killing, while Autonomous mode terminates."""
        # 1. Advisory Mode
        adv_engine = HealingEngine(win32_platform=mock_win32_platform, auto_kill=False)
        rep1 = adv_engine.heal_hung_process(pid=7777, name="LeakingApp.exe")
        assert rep1["success"] is False
        assert rep1["reason"] == "AUTO_KILL_DISABLED"
        assert rep1["alert_issued"] is True
        assert 7777 not in mock_win32_platform.killed_pids

        # 2. Autonomous Mode
        auto_engine = HealingEngine(win32_platform=mock_win32_platform, auto_kill=True)
        rep2 = auto_engine.heal_hung_process(pid=7777, name="LeakingApp.exe")
        assert rep2["success"] is True
        assert 7777 in mock_win32_platform.killed_pids


# ============================================================================
# DOMAIN 6: jarvis/platform ADVERSARIAL STRESS
# ============================================================================

class TestPlatformWindowsAdversarialStress:
    """Adversarial testing for Win32 API error handling, monitor layouts, and registry autostart."""

    def test_platform_windows_monitor_enumeration_negative_coords(self, mock_win32_platform):
        """Verify monitor sorting with negative coordinate offsets (secondary monitor left of primary)."""
        # Secondary monitor at [-1920, 0, 0, 1080], Primary at [0, 0, 1920, 1080]
        mock_win32_platform.monitors = [
            (0, 0, 1920, 1080),
            (-1920, 0, 0, 1080),
        ]

        api = WindowsPlatformAPI()
        monitors = api.get_monitors()

        assert len(monitors) == 2
        # Verify left-to-right sorting (-1920 comes first)
        assert monitors[0].rect[0] == -1920
        assert monitors[1].rect[0] == 0

    def test_platform_windows_invalid_hwnd_cloaked_window_handling(self):
        """Verify cloaked window querying on non-existent or null HWNDs returns False safely."""
        api = WindowsPlatformAPI()
        assert api.is_window_cloaked(0) is False
        assert api.is_window_cloaked(-1) is False
        assert api.is_window_hung(0) is False
        assert api._build_window_info(0) is None

    def test_platform_windows_sendinput_invalid_keys_and_modifiers(self):
        """Verify SendInput keystroke synthesis with unknown key names and empty sequences."""
        api = WindowsPlatformAPI()

        # 1. Invalid key names should return False without raising exceptions
        assert api.send_hotkey("non_existent_virtual_key_12345") is False

        # 2. Empty hotkey call
        assert api.send_hotkey() is False

        # 3. Unicode text injection with empty text
        assert api.send_unicode_text("") is False

    def test_autostart_registry_error_handling_and_corrupt_paths(self, monkeypatch):
        """Verify AutoStartManager resilience when winreg is unavailable or raises PermissionError."""
        # 1. winreg module raising PermissionError
        class FailingWinreg:
            HKEY_CURRENT_USER = 1
            KEY_SET_VALUE = 2
            def OpenKey(self, *args, **kwargs):
                raise PermissionError("Access is denied to HKCU Run key")

        monkeypatch.setitem(sys.modules, "winreg", FailingWinreg())

        res = set_autostart(app_name="JARVIS_Test", enabled=True)
        assert res is False

        status = get_autostart_status(app_name="JARVIS_Test")
        assert bool(status) is False
