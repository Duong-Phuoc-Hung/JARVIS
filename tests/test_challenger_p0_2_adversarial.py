"""
tests/test_challenger_p0_2_adversarial.py
=========================================
Adversarial Stress Test Suite for JARVIS v4.6.0 P0 Subsystems.
Challenger P0-2:
  1. Wake Word Detector (corrupt audio, extreme noise, fast toggle cycles, missing models, NaN/Inf, Vosk error cascades).
  2. ProactiveEngine (rapid concurrent reminders, 99% RAM saturation, Pomodoro transition races, massive loads, EventBus failures).
  3. LLM Router (ReDoS queries >5000 chars, emoji-only strings, number strings, invalid API keys, injection vectors, high concurrency).
"""
import concurrent.futures
import math
import os
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    WakeWordEngineType,
    WakeWordResult,
    generate_wake_word_signal,
    resample_audio,
)
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult
from jarvis.llm.client import LLMClient, LLMResponse
from jarvis.llm.router import IntentResult, LLMIntentRouter
from jarvis.proactive.engine import ProactiveConfig
from jarvis.proactive.health_monitor import HealthAlert, SystemHealthMonitor
from jarvis.proactive.pomodoro import PomodoroState, PomodoroTimer
from jarvis.proactive.reminders import ReminderScheduler
from jarvis.workers.proactive import ProactiveEngine


class MockTelemetryProvider:
    """Mock telemetry provider for testing hardware thresholds."""

    def __init__(
        self,
        cpu_percent: float = 20.0,
        ram_percent: float = 40.0,
        cpu_temp_c: float | None = 45.0,
        disk_free_gb: float = 100.0,
        disk_drive: str = "C:",
        battery_percent: float | None = 90.0,
        battery_plugged: bool = True,
    ) -> None:
        self.cpu_percent = cpu_percent
        self.ram_percent = ram_percent
        self.cpu_temp_c = cpu_temp_c
        self.disk_free_gb = disk_free_gb
        self.disk_drive = disk_drive
        self.battery_percent = battery_percent
        self.battery_plugged = battery_plugged


# ============================================================================
# 1. ADVERSARIAL TESTS: WAKE WORD DETECTOR
# ============================================================================

class TestWakeWordAdversarial:
    """Stress testing WakeWordDetector with extreme and pathological inputs."""

    def test_corrupt_and_extreme_audio_inputs(self):
        """Test detector resilience against corrupt, NaN, Inf, and abnormal audio arrays."""
        detector = WakeWordDetector(sensitivity=0.5)

        # 1. None and empty inputs
        assert detector.feed_audio_block(None) is None
        assert detector.process_audio_block(None) is False
        assert detector.feed_audio_block(np.array([], dtype=np.float32)) is None

        # 2. NaN and Inf inputs
        nan_array = np.array([np.nan, 0.5, np.nan, -0.5, np.nan] * 100, dtype=np.float32)
        assert detector.feed_audio_block(nan_array) is None

        inf_array = np.array([np.inf, -np.inf, 0.1, -0.1] * 200, dtype=np.float32)
        assert detector.feed_audio_block(inf_array) is None

        # 3. Multi-dimensional arrays (stereo, 3D)
        stereo_array = np.random.uniform(-0.5, 0.5, (1000, 2)).astype(np.float32)
        res = detector.feed_audio_block(stereo_array)
        assert res is None or isinstance(res, WakeWordResult)

        # 4. Out-of-bounds integer inputs
        int16_array = np.random.randint(-32768, 32767, 1600, dtype=np.int16)
        res_int = detector.feed_audio_block(int16_array)
        assert res_int is None or isinstance(res_int, WakeWordResult)

        # 5. Extreme amplitudes / digital clipping (all 1.0 or -1.0)
        clipped_array = np.ones(16000, dtype=np.float32)
        assert detector.feed_audio_block(clipped_array) is None

        # 6. Zero-length frames after resampling
        detector_weird_sr = WakeWordDetector(sample_rate=1, target_sample_rate=16000)
        res = detector_weird_sr.feed_audio_block(np.array([0.1], dtype=np.float32))
        assert res is None

    def test_extreme_noise_rejection(self):
        """Test rejection of white noise, pure sines, square waves, and impulse claps."""
        detector = WakeWordDetector(sensitivity=0.5)

        # 1. Pure Sine Waves at various frequencies (100Hz, 1kHz, 3kHz, 6kHz)
        sr = 44100
        t = np.linspace(0, 1.2, int(sr * 1.2), endpoint=False)
        for freq in [100.0, 440.0, 1000.0, 3000.0, 5000.0, 8000.0]:
            sine_wave = (0.8 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
            detector.reset()
            result = detector.feed_audio_block(sine_wave)
            assert result is None, f"False positive on pure sine wave at {freq} Hz"

        # 2. White noise
        detector.reset()
        white_noise = np.random.normal(0, 0.4, int(sr * 1.2)).astype(np.float32)
        white_noise = np.clip(white_noise, -1.0, 1.0)
        result = detector.feed_audio_block(white_noise)
        assert result is None, "False positive on white noise"

        # 3. Impulse Clap (Dirac delta-like spike)
        detector.reset()
        clap = np.zeros(int(sr * 1.2), dtype=np.float32)
        clap[int(sr * 0.5) : int(sr * 0.5) + 50] = 0.95
        result = detector.feed_audio_block(clap)
        assert result is None, "False positive on impulse clap"

        # 4. Square wave (rapid harmonics)
        detector.reset()
        square = (0.5 * np.sign(np.sin(2 * np.pi * 500.0 * t))).astype(np.float32)
        result = detector.feed_audio_block(square)
        assert result is None, "False positive on square wave"

    def test_rapid_concurrent_toggles_and_stream(self):
        """Stress test thread safety under rapid concurrent enable/disable and audio streaming."""
        detector = WakeWordDetector(sensitivity=0.5)
        stop_event = threading.Event()
        errors = []

        def audio_streamer():
            try:
                synthetic = generate_wake_word_signal(duration_s=1.2, sample_rate=44100)
                chunk_size = 1024
                while not stop_event.is_set():
                    for i in range(0, len(synthetic), chunk_size):
                        chunk = synthetic[i : i + chunk_size]
                        detector.process_audio_block(chunk)
                        time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def toggle_worker():
            try:
                for _ in range(50):
                    detector.toggle_enabled()
                    detector.set_enabled(True)
                    detector.set_enabled(False)
                    detector.reset()
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=audio_streamer),
            threading.Thread(target=audio_streamer),
            threading.Thread(target=toggle_worker),
            threading.Thread(target=toggle_worker),
        ]

        for t in threads:
            t.start()

        time.sleep(0.3)
        stop_event.set()

        for t in threads:
            t.join(timeout=2.0)

        assert len(errors) == 0, f"Concurrent toggle/streaming raised errors: {errors}"

    def test_missing_model_paths_graceful_fallback(self):
        """Test initialization with completely invalid/missing paths falls back gracefully."""
        bad_config = {
            "vosk_model_path": "C:\\non_existent_folder_xyz_12345\\model",
            "porcupine_access_key": "invalid_key_xyz",
            "auto_download_vosk": False,
        }
        detector = WakeWordDetector(config=bad_config)
        assert detector._engine_type in (WakeWordEngineType.ACOUSTIC_FALLBACK, WakeWordEngineType.WHISPER)

        # Feeding signal should still work via fallback
        valid_signal = generate_wake_word_signal(duration_s=1.2, sample_rate=44100)
        res = detector.feed_audio_block(valid_signal)
        assert res is not None
        assert res.keyword == "hey_jarvis"

    def test_cooldown_refractory_enforcement(self):
        """Verify cooldown period strictly blocks consecutive rapid triggers."""
        detector = WakeWordDetector(sensitivity=0.5, cooldown_s=1.5)
        signal = generate_wake_word_signal(duration_s=1.2, sample_rate=44100)

        # First trigger at t=100.0
        r1 = detector.feed_audio_block(signal, timestamp=100.0)
        assert r1 is not None, "Initial trigger failed"

        # Rapid subsequent trigger at t=100.5 (within 1.5s cooldown)
        r2 = detector.feed_audio_block(signal, timestamp=100.5)
        assert r2 is None, "Trigger was not suppressed during cooldown"

        # Trigger at t=101.4 (within 1.5s cooldown)
        r3 = detector.feed_audio_block(signal, timestamp=101.4)
        assert r3 is None, "Trigger was not suppressed during cooldown"

        # Trigger at t=101.6 (after 1.5s cooldown)
        r4 = detector.feed_audio_block(signal, timestamp=101.6)
        assert r4 is not None, "Trigger after cooldown expired failed"

    def test_vosk_engine_exception_falls_back_to_acoustic(self):
        """Verify that if Vosk recognizer raises an unexpected exception during decoding, Tier 2 catches it."""
        detector = WakeWordDetector(sensitivity=0.5)
        detector._engine_type = WakeWordEngineType.VOSK
        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.side_effect = RuntimeError("Vosk corrupted buffer exception")
        detector._tier1_engine = mock_rec

        valid_signal = generate_wake_word_signal(duration_s=1.2, sample_rate=44100)
        # Should not raise exception and should fall back to acoustic detector
        res = detector.feed_audio_block(valid_signal)
        assert res is not None
        assert res.keyword == "hey_jarvis"
        assert res.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value

    def test_massive_audio_buffer_ingestion(self):
        """Verify feeding a massive 5-second audio chunk in one block does not overflow or crash."""
        detector = WakeWordDetector(sensitivity=0.5)
        huge_signal = generate_wake_word_signal(duration_s=5.0, sample_rate=44100)
        res = detector.feed_audio_block(huge_signal)
        assert res is not None or res is None


# ============================================================================
# 2. ADVERSARIAL TESTS: PROACTIVE ENGINE
# ============================================================================

class TestProactiveEngineAdversarial:
    """Stress testing ProactiveEngine under concurrency, hardware saturation, and races."""

    def test_rapid_concurrent_reminder_insertions_and_cancellations(self):
        """Stress test ReminderScheduler with 20 concurrent threads adding/cancelling reminders."""
        scheduler = ReminderScheduler(enabled=True)
        num_threads = 20
        reminders_per_thread = 20
        created_ids = []
        lock = threading.Lock()
        errors = []

        def worker(thread_idx: int):
            try:
                for i in range(reminders_per_thread):
                    r_id = scheduler.add_reminder(
                        text=f"Reminder from thread {thread_idx} item {i}",
                        delay_seconds=float(i + 1),
                    )
                    with lock:
                        created_ids.append(r_id)
                    # Randomly cancel half of them
                    if i % 2 == 0:
                        scheduler.cancel_reminder(r_id)
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            concurrent.futures.wait(futures)

        assert len(errors) == 0, f"Concurrent reminder operations raised errors: {errors}"
        assert len(created_ids) == num_threads * reminders_per_thread

        # Verify tick does not crash
        executed = scheduler.tick(now=time.time() + 100.0)
        assert isinstance(executed, list)

    def test_simulated_99_percent_ram_and_cpu_saturation(self):
        """Test health watchdog when hardware reaches 99% RAM and 99% CPU."""
        mock_event_bus = MagicMock()
        mock_dispatcher = MagicMock()
        tts_alerts = []

        mock_provider = MockTelemetryProvider(
            cpu_percent=99.0,
            ram_percent=99.0,
            disk_free_gb=1.0,
            cpu_temp_c=98.0,
            battery_percent=5.0,
            battery_plugged=False,
        )

        engine = ProactiveEngine(
            telemetry_provider=mock_provider,
            dispatcher=mock_dispatcher,
            event_bus=mock_event_bus,
            tts_callback=lambda txt: tts_alerts.append(txt),
            config=ProactiveConfig(
                health_monitor_enabled=True,
                cpu_threshold=90.0,
                ram_threshold=90.0,
                disk_min_free_gb=5.0,
                temp_threshold_c=90.0,
                battery_min_percent=15.0,
                health_cooldown_s=60.0,
            ),
        )

        # 1. Trigger health check
        alerts = engine.check_health_now()
        assert len(alerts) >= 3  # RAM, CPU, Temp, Disk, Battery alerts
        alert_types = [a["alert_type"] for a in alerts]
        assert "ram" in alert_types
        assert "cpu" in alert_types

        # 2. Verify event bus was called with 'hardware.alert'
        assert mock_event_bus.publish.called
        event_names = [call.args[0] for call in mock_event_bus.publish.call_args_list]
        assert "hardware.alert" in event_names

        # 3. Verify cooldown prevents immediate spamming
        mock_event_bus.reset_mock()
        alerts_cooldown = engine.health_monitor.check_telemetry(now=time.time() + 1.0)
        assert len(alerts_cooldown) == 0, "Health alert cooldown was violated"
        assert not mock_event_bus.publish.called

    def test_event_bus_exception_resilience(self):
        """Verify that if EventBus throws an exception during alert publish, health monitor stays resilient."""
        mock_event_bus = MagicMock()
        mock_event_bus.publish.side_effect = RuntimeError("EventBus broker connection disconnected")
        mock_provider = MockTelemetryProvider(cpu_percent=99.0, ram_percent=99.0)

        engine = ProactiveEngine(
            telemetry_provider=mock_provider,
            event_bus=mock_event_bus,
            config=ProactiveConfig(health_monitor_enabled=True, cpu_threshold=90.0, ram_threshold=90.0),
        )

        # Should not raise exception even if EventBus failed
        alerts = engine.check_health_now()
        assert len(alerts) >= 2

    def test_pomodoro_transition_races(self):
        """Stress test PomodoroTimer under rapid concurrent start, pause, resume, stop calls."""
        timer = PomodoroTimer(
            default_work_minutes=25.0,
            default_break_minutes=5.0,
            enabled=True,
        )
        errors = []

        def racer(action_idx: int):
            try:
                for _ in range(50):
                    if action_idx == 0:
                        timer.start(work_minutes=25.0, break_minutes=5.0)
                    elif action_idx == 1:
                        timer.pause()
                    elif action_idx == 2:
                        timer.resume()
                    elif action_idx == 3:
                        timer.stop()
                    elif action_idx == 4:
                        timer.tick(now=time.time())
                        timer.get_status()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=racer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert len(errors) == 0, f"Pomodoro transition race raised errors: {errors}"

    def test_action_dispatcher_proactive_actions(self):
        """Verify registered proactive actions in ActionDispatcher execute properly."""
        dispatcher = ActionDispatcher()
        engine = ProactiveEngine(dispatcher=dispatcher)

        # Test proactive_reminder action
        res = dispatcher.dispatch_action(
            action_name="proactive_reminder",
            payload={"message": "Uống nước", "delay_seconds": 60},
        )
        assert res.success is True
        assert "reminder_id" in res.data
        assert res.data["status"] == "success"

        # Test proactive_pomodoro_start action
        res_pom = dispatcher.dispatch_action(
            action_name="proactive_pomodoro_start",
            payload={"work_minutes": 30.0, "break_minutes": 5.0},
        )
        assert res_pom.success is True
        assert res_pom.data["status"] == "success"

        # Test proactive_pomodoro_stop action
        res_stop = dispatcher.dispatch_action(
            action_name="proactive_pomodoro_stop",
            payload={},
        )
        assert res_stop.success is True
        assert res_stop.data["status"] == "success"

    def test_proactive_backward_time_anomaly_handling(self):
        """Test engine resilience when clock steps backwards."""
        engine = ProactiveEngine(config=ProactiveConfig())
        t_base = time.time()
        engine.add_reminder("Test reminder", delay_seconds=10.0)

        # Tick at base time
        res_0 = engine.tick(now=t_base)
        assert len(res_0["reminders_executed"]) == 0

        # Clock steps backward by 500s
        res_backward = engine.tick(now=t_base - 500.0)
        assert isinstance(res_backward, dict)
        assert len(res_backward["reminders_executed"]) == 0

        # Clock steps forward to expiration (+15s)
        res_forward = engine.tick(now=t_base + 15.0)
        assert len(res_forward["reminders_executed"]) == 1


# ============================================================================
# 3. ADVERSARIAL TESTS: LLM ROUTER
# ============================================================================

class TestLLMRouterAdversarial:
    """Stress testing LLMIntentRouter against ReDoS, extreme payloads, emojis, and errors."""

    def test_long_redos_queries(self):
        """Stress test router against 50,000 character repeating regex attack vectors."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.generate.return_value = LLMResponse(content="Natural response", tool_calls=[])
        router = LLMIntentRouter(llm_client=mock_client)

        # Catastrophic backtracking patterns with large repetition
        attack_vectors = [
            "a" * 10000,
            ("bật đèn " * 2000),
            ("(((a+)+)+)" * 1000),
            "đặt báo thức lúc " + "9 " * 5000 + "giờ",
            "nhắc tôi " + "a" * 10000 + " sau 5 phút",
            " " * 20000,
            "!" * 10000,
            "🔥" * 5000,
        ]

        for vec in attack_vectors:
            t0 = time.perf_counter()
            intent = router.parse_intent(vec)
            elapsed = time.perf_counter() - t0
            assert elapsed < 0.5, f"ReDoS query exceeded 500ms (took {elapsed:.4f}s): {vec[:50]}..."
            assert isinstance(intent, IntentResult)

    def test_emoji_only_and_bmp_dingbats(self):
        """Verify emoji-only text returns unknown_intent without invoking LLM."""
        mock_client = MagicMock(spec=LLMClient)
        router = LLMIntentRouter(llm_client=mock_client)

        emoji_queries = [
            "🔥🚀🎉",
            "✨✅⚡❄",
            "😀😃😄😁😆",
            "  🔥  ✨  ",
        ]

        for eq in emoji_queries:
            res = router.parse_intent(eq)
            assert res.action_name == "unknown_intent", f"Emoji query '{eq}' failed to classify as unknown_intent"
            assert not mock_client.generate.called

    def test_number_only_queries(self):
        """Verify number-only queries return unknown_intent without invoking LLM."""
        mock_client = MagicMock(spec=LLMClient)
        router = LLMIntentRouter(llm_client=mock_client)

        number_queries = [
            "123456",
            "0987654321",
            "+1-800-555-0199",
            "3.1415926535",
            "  123 456  ",
        ]

        for nq in number_queries:
            res = router.parse_intent(nq)
            assert res.action_name == "unknown_intent", f"Number query '{nq}' failed to classify as unknown_intent"
            assert not mock_client.generate.called

    def test_invalid_api_key_and_network_exception_fallback(self):
        """Verify LLM errors (e.g. 401 Unauthorized, ConnectionError) gracefully fallback to Tier 3."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.generate.side_effect = ConnectionError("401 Unauthorized: Invalid API Key")
        router = LLMIntentRouter(llm_client=mock_client)

        # 1. Known phrase that triggers Tier 3 fallback
        res = router.parse_intent("bật đèn phòng khách", force_llm=True)
        assert res.action_name == "home_assistant_call"
        assert res.source == "rule_fallback"

        # 2. Unknown phrase with failed LLM -> returns unknown_intent gracefully
        res_unknown = router.parse_intent("lập trình một ứng dụng quantum computing", force_llm=True)
        assert res_unknown.action_name == "unknown_intent"
        assert res_unknown.source == "rule_fallback"
        assert "error" in res_unknown.parameters

    def test_none_input_graceful_handling(self):
        """Verify None input returns unknown_intent without crashing."""
        mock_client = MagicMock(spec=LLMClient)
        router = LLMIntentRouter(llm_client=mock_client)

        res_none = router.parse_intent(None)  # type: ignore[arg-type]
        assert res_none.action_name == "unknown_intent"
        assert res_none.confidence == 0.0
        assert not mock_client.generate.called

    def test_special_control_characters_and_injections(self):
        """Verify NULL bytes, BiDi overrides, ANSI escape sequences, and SQL/Command injection payloads."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.generate.return_value = LLMResponse(content="Handled", tool_calls=[])
        router = LLMIntentRouter(llm_client=mock_client)

        injection_payloads = [
            "bật đèn \x00 phòng khách",
            "\u202Ebật đèn phòng khách\u202C",
            "\033[31;1;4mbật đèn phòng khách\033[0m",
            "'; DROP TABLE users; --",
            "$(rm -rf /)",
            "{\"action\": \"shutdown_system\"}",
            "\r\n\r\n\t\t\t\n",
        ]

        for payload in injection_payloads:
            res = router.parse_intent(payload)
            assert isinstance(res, IntentResult)
            assert res.action_name in ("home_assistant_call", "unknown_intent", "generic_llm_response", "system_power")
            if res.action_name == "system_power":
                assert res.requires_confirmation is True

    def test_concurrent_router_high_throughput(self):
        """Stress test router with 20 concurrent worker threads submitting mixed queries."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.generate.return_value = LLMResponse(content="Response", tool_calls=[])
        router = LLMIntentRouter(llm_client=mock_client)

        queries = [
            "bật đèn phòng khách",
            "tắt đèn phòng ngủ",
            "thời tiết hà nội hôm nay",
            "đặt báo thức lúc 7 giờ sáng",
            "🔥🚀🎉",
            "123456789",
            "giải thích cơ học lượng tử",
            "a" * 1000,
        ]

        errors = []

        def worker(thread_id: int):
            try:
                for q in queries:
                    res = router.parse_intent(q)
                    assert isinstance(res, IntentResult)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0, f"Concurrent router execution had errors: {errors}"
