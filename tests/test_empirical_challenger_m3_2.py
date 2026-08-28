"""
tests/test_empirical_challenger_m3_2.py
=======================================
Milestone M3 Empirical Challenger 2 Stress Verification Suite.
Validates:
1. High-Concurrency [INTERACTION] Logging Stress (20+ concurrent threads writing to logs/jarvis.log without line tearing or corruption).
2. Randomized Welcome Greetings Pool non-repeating random draw (100+ draws with no adjacent duplicates when pool > 1).
3. Startup Vocal Introduction lifecycle robustness with mocked/uninitialized/throwing TTS (app.start() never crashes).
"""
from __future__ import annotations

import concurrent.futures
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.logger import (
    JarvisLoggerAdapter,
    StructuredFileFormatter,
    get_logger,
    log_action,
    log_interaction,
    log_trigger,
    setup_logging,
    shutdown_logging,
)
from jarvis.tts.manager import WELCOME_PHRASES, TTSManager

# ============================================================================
# 1. HIGH-CONCURRENCY [INTERACTION] LOGGING STRESS & ADVERSARIAL PAYLOADS
# ============================================================================

INTERACTION_LOG_REGEX = re.compile(
    r"^\[INTERACTION\] \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| TRIGGER: (?P<trigger>.*?) \| INPUT: (?P<input>.*?) \| ACTION: (?P<action>.*?) \| RESPONSE: (?P<response>.*?) \| STATUS: (?P<status>success|failed)$"
)


def test_high_concurrency_interaction_logging_stress_30_threads_1500_entries(tmp_path: Path):
    """
    Stress Test: 30 concurrent worker threads rapidly emitting 50 log entries each (total 1,500 entries)
    to a target log file.
    Verifies:
      - Total lines in log file is EXACTLY 1,500.
      - Zero line tearing or file corruption.
      - Every single line strictly conforms to INTERACTION_LOG_REGEX.
      - Zero unhandled thread exceptions.
    """
    log_file = tmp_path / "high_concurrency_stress.log"
    num_threads = 30
    writes_per_thread = 50
    expected_total = num_threads * writes_per_thread

    exceptions: List[Exception] = []

    def _worker(thread_id: int):
        try:
            for seq in range(writes_per_thread):
                trigger_name = f"THREAD_WORKER_{thread_id:02d}"
                input_cmd = f"Lệnh kiểm tra hệ thống #{seq:03d} từ luồng {thread_id}"
                action_name = f"action_worker_{thread_id % 5}"
                resp_text = f"Phản hồi kết quả #{seq:03d} an toàn tuyệt đối"
                status_flag = "success" if (thread_id + seq) % 3 != 0 else "failed"

                line = log_interaction(
                    trigger=trigger_name,
                    input_text=input_cmd,
                    action=action_name,
                    response=resp_text,
                    status=status_flag,
                    log_file=log_file,
                )
                assert line.startswith("[INTERACTION]")
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(_worker, tid) for tid in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0, f"Encountered thread exceptions: {exceptions}"
    assert log_file.exists(), "Target log file was not created!"

    raw_content = log_file.read_text(encoding="utf-8")
    lines = [l for l in raw_content.splitlines() if l.strip()]

    assert len(lines) == expected_total, f"Expected {expected_total} lines, but got {len(lines)}"

    # Validate every single line against strict regex schema
    for idx, line in enumerate(lines):
        match = INTERACTION_LOG_REGEX.match(line)
        assert match is not None, f"Line {idx} failed regex schema: {line!r}"
        assert match.group("status") in ("success", "failed")
        assert "THREAD_WORKER_" in match.group("trigger")


def test_interaction_logging_adversarial_payloads_under_concurrency(tmp_path: Path):
    """
    Adversarial Stress Test: 20 concurrent threads sending pathological inputs:
      - Raw multiline strings (\\r\\n, \\n, \\r)
      - Vietnamese Unicode diacritics & accented characters
      - Unicode emojis (🚀🔥💡🤖)
      - Quotes, semicolons, brackets, tabs, SQL/Shell injection tokens
      - Empty strings, whitespace-only, None values, boolean flags
    Verifies that all newlines are sanitized into single-line records without line tearing.
    """
    log_file = tmp_path / "adversarial_payloads.log"
    num_threads = 20
    entries_per_thread = 25
    expected_total = num_threads * entries_per_thread

    adversarial_inputs = [
        "Lệnh dòng 1\nLệnh dòng 2\r\nLệnh dòng 3\rDòng 4",
        "  \t\t\n\r  ",
        "'; DROP TABLE logs; --",
        "Tiếng Việt có dấu: Bật đèn phòng khách & kiểm tra nhiệt độ CPU 75°C",
        "🚀 JARVIS Voice Assistant 💡 Ứng dụng đã sẵn sàng 🤖",
        "<xml><tag>nested</tag></xml>",
        '{"command": "spotify_play", "playlist": "Chill & Relax", "volume": 80}',
        "a" * 500,  # Long text
        "",
        None,
    ]

    adversarial_responses = [
        "Phản hồi dòng 1\nPhản hồi dòng 2\n\n\nDòng 3",
        "Đã thực hiện xong lệnh hệ thống: OK",
        "  \t  ",
        "Nhiệt độ CPU hiện tại là 65.4°C, quạt tản nhiệt 1200 RPM",
        "💡 Double clap để hỏi tiếp | Trạng thái: Bình thường",
        "",
        None,
    ]

    exceptions: List[Exception] = []

    def _worker(thread_id: int):
        try:
            for i in range(entries_per_thread):
                inp = adversarial_inputs[(thread_id + i) % len(adversarial_inputs)]
                resp = adversarial_responses[(thread_id + i) % len(adversarial_responses)]
                status = "ok" if i % 2 == 0 else "0"

                entry = log_interaction(
                    trigger=f"ADV_THREAD_{thread_id}",
                    input_text=inp,  # type: ignore
                    action="adversarial_action",
                    response=resp,  # type: ignore
                    status=status,
                    log_file=log_file,
                )
                assert "\n" not in entry
                assert "\r" not in entry
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(_worker, tid) for tid in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == expected_total

    for idx, line in enumerate(lines):
        assert line.startswith("[INTERACTION]")
        assert " | TRIGGER: " in line
        assert " | INPUT: " in line
        assert " | ACTION: " in line
        assert " | RESPONSE: " in line
        assert " | STATUS: " in line
        assert "\n" not in line
        assert "\r" not in line


def test_app_log_interaction_delegation_and_custom_config(tmp_path: Path):
    """Verify JarvisApp.log_interaction() uses configured log file path and writes atomically."""
    custom_log = tmp_path / "custom_app_interactions.log"
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.config.set("logging.file", str(custom_log))
    app.initialize()

    entry = app.log_interaction(
        trigger="TEST_VOICE",
        input_text="Kiểm tra hệ thống",
        action="system_status",
        response="Tất cả dịch vụ đang hoạt động bình thường",
        status="success",
    )

    assert custom_log.exists()
    assert "[INTERACTION]" in entry
    assert "TRIGGER: TEST_VOICE" in entry
    content = custom_log.read_text(encoding="utf-8").strip()
    assert content == entry
    app.stop()


def test_interaction_logging_missing_directory_auto_creation(tmp_path: Path):
    """Verify that logging to a non-existent deeply nested directory creates parents automatically."""
    deep_log = tmp_path / "nested" / "sub1" / "sub2" / "auto_created.log"
    assert not deep_log.parent.exists()

    entry = log_interaction(
        trigger="AUTO_DIR",
        input_text="Deep log path test",
        action="deep_write",
        response="Directory created successfully",
        status="success",
        log_file=deep_log,
    )

    assert deep_log.exists()
    assert deep_log.read_text(encoding="utf-8").strip() == entry


def test_logger_adapter_log_interaction_integration(tmp_path: Path):
    """Verify JarvisLoggerAdapter exposes log_interaction helper matching specification."""
    adapter_log = tmp_path / "adapter_test.log"
    logger = get_logger("jarvis.test_adapter")

    entry = logger.log_interaction(
        trigger="ADAPTER",
        input_text="Adapter invocation",
        action="adapter_action",
        response="Adapter response",
        status="success",
        log_file=adapter_log,
    )

    assert adapter_log.exists()
    assert entry in adapter_log.read_text(encoding="utf-8")


# ============================================================================
# 2. WELCOME POOL NON-REPEATING RANDOM SELECTION & STRESS
# ============================================================================

def test_welcome_pool_non_repeating_100_consecutive_draws_default_pool():
    """
    Verify across 200 consecutive draws from default WELCOME_PHRASES (pool of 5 phrases):
      - No two adjacent draws are identical (selected[i] != selected[i+1] for all i).
      - Every drawn phrase is a member of WELCOME_PHRASES.
      - Full coverage: all phrases in the pool are drawn over 200 trials.
    """
    mgr = TTSManager(config={})
    assert len(WELCOME_PHRASES) >= 4

    draws: List[str] = []
    total_draws = 200

    for _ in range(total_draws):
        phrase = mgr.get_welcome_phrase()
        draws.append(phrase)
        assert phrase in WELCOME_PHRASES

    # Critical Assertion: No two adjacent draws are identical
    for i in range(len(draws) - 1):
        assert draws[i] != draws[i + 1], f"Adjacent duplicate detected at draw {i}: {draws[i]!r}"

    # Verify coverage across all phrases in pool
    unique_drawn = set(draws)
    assert len(unique_drawn) == len(WELCOME_PHRASES), "Not all phrases in the pool were selected!"
    mgr.stop()


def test_welcome_pool_non_repeating_minimal_two_phrase_pool():
    """
    Adversarial test on minimal pool with exactly 2 phrases:
    Must strictly alternate (A, B, A, B, A, B...) for 100 consecutive draws with 100% adherence.
    """
    config = {
        "welcome": {
            "phrases": ["Phrase Alpha", "Phrase Beta"]
        }
    }
    mgr = TTSManager(config=config)
    draws = [mgr.get_welcome_phrase() for _ in range(100)]

    for i in range(len(draws) - 1):
        assert draws[i] != draws[i + 1], f"Adjacent duplicate in 2-item pool at index {i}"
        assert (draws[i], draws[i + 1]) in [("Phrase Alpha", "Phrase Beta"), ("Phrase Beta", "Phrase Alpha")]

    mgr.stop()


def test_welcome_pool_single_phrase_stability():
    """
    Boundary test on pool with exactly 1 phrase:
    Must safely return the single phrase on every call without infinite loops or errors.
    """
    config = {
        "welcome": {
            "phrases": ["Single Unique Greeting"]
        }
    }
    mgr = TTSManager(config=config)
    for _ in range(50):
        phrase = mgr.get_welcome_phrase()
        assert phrase == "Single Unique Greeting"

    mgr.stop()


def test_welcome_pool_empty_and_whitespace_fallback():
    """
    Edge case: Empty phrases list or whitespace-only phrases fall back gracefully to default WELCOME_PHRASES.
    """
    config_empty = {"welcome": {"phrases": ["   ", "", "\t\n"]}}
    mgr = TTSManager(config=config_empty)
    phrase = mgr.get_welcome_phrase()
    assert phrase in WELCOME_PHRASES
    mgr.stop()


def test_welcome_phrase_explicit_override_precedence():
    """Verify explicit_phrase argument immediately overrides configuration without mutating pool state."""
    config = {"welcome": {"phrases": ["Phrase A", "Phrase B"]}}
    mgr = TTSManager(config=config)

    override = mgr.get_welcome_phrase(explicit_phrase="Explicit Stark Greeting")
    assert override == "Explicit Stark Greeting"

    # Subsequent normal call still pulls from configured pool
    next_phrase = mgr.get_welcome_phrase()
    assert next_phrase in ["Phrase A", "Phrase B"]
    mgr.stop()


def test_welcome_pool_high_concurrency_thread_safety():
    """
    Stress test: 50 concurrent worker threads requesting welcome phrases simultaneously.
    Verifies thread safety under TTSManager._lock with zero exceptions or race corruptions.
    """
    config = {
        "welcome": {
            "phrases": [f"Custom Phrase {i}" for i in range(10)]
        }
    }
    mgr = TTSManager(config=config)
    results: List[str] = []
    exceptions: List[Exception] = []
    lock = threading.Lock()

    def _worker():
        try:
            for _ in range(20):
                p = mgr.get_welcome_phrase()
                with lock:
                    results.append(p)
        except Exception as e:
            with lock:
                exceptions.append(e)

    threads = [threading.Thread(target=_worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(exceptions) == 0
    assert len(results) == 1000
    for p in results:
        assert p.startswith("Custom Phrase ")

    mgr.stop()


def test_speak_welcome_async_daemon_thread(monkeypatch):
    """Verify speak_welcome() launches in a background daemon thread with configured delay."""
    spoken: List[str] = []
    mgr = TTSManager(config={})
    monkeypatch.setattr(mgr, "speak", lambda txt, wait=False: spoken.append(txt) or True)

    mgr.speak_welcome(delay_s=0.01)
    time.sleep(0.08)

    assert len(spoken) == 1
    assert spoken[0] in WELCOME_PHRASES
    mgr.stop()


# ============================================================================
# 3. STARTUP INTRO WITH MOCKED / UNINITIALIZED / THROWING TTS (app.start())
# ============================================================================

def test_startup_intro_with_uninitialized_tts_manager():
    """
    Adversarial test: app.tts_manager is None (uninitialized or failed to create).
    app.start() must execute completely without throwing AttributeError or crashing.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app.tts_manager = None  # Force uninitialized TTS

    # app.start() must NOT crash
    try:
        app.start()
        assert app.tts_manager is None
    finally:
        app.stop()


def test_startup_intro_with_throwing_tts_manager():
    """
    Adversarial test: app.tts_manager.speak raises an unhandled hardware/network exception.
    app.start() must catch the exception, log warning, and safely proceed without crashing.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    mock_tts = MagicMock()
    mock_tts.speak.side_effect = RuntimeError("Fatal hardware disconnect on audio output device!")
    app.tts_manager = mock_tts

    try:
        app.start()
        assert mock_tts.speak.called
    finally:
        app.stop()


def test_startup_intro_with_mocked_tts_queues_expected_phrase(monkeypatch):
    """
    Verify app.start() queues the canonical startup greeting:
    'Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.' asynchronously (wait=False).
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    spoken_calls: List[tuple] = []
    if app.tts_manager:
        monkeypatch.setattr(
            app.tts_manager,
            "speak",
            lambda text, wait=False: spoken_calls.append((text, wait)) or True,
        )

    try:
        app.start()
        assert len(spoken_calls) == 1
        phrase, wait_flag = spoken_calls[0]
        assert phrase == "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."
        assert wait_flag is False  # Must be non-blocking async
    finally:
        app.stop()


def test_startup_intro_custom_configured_phrase(monkeypatch):
    """Verify custom startup phrase in config (tts.welcome.startup_phrase) is respected."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.config.set("tts.welcome.startup_phrase", "Chào buổi sáng sếp. JARVIS trực tuyến.")
    app.initialize()

    spoken_calls: List[tuple] = []
    if app.tts_manager:
        monkeypatch.setattr(
            app.tts_manager,
            "speak",
            lambda text, wait=False: spoken_calls.append((text, wait)) or True,
        )

    try:
        app.start()
        assert len(spoken_calls) == 1
        assert spoken_calls[0][0] == "Chào buổi sáng sếp. JARVIS trực tuyến."
    finally:
        app.stop()


def test_app_lifecycle_resilience_all_subsystems_failing():
    """
    Adversarial test: All background subsystems (audio, dashboard, tray, overlay, TTS) fail or are None.
    app.start() and app.stop() handle all failures gracefully without unhandled exceptions.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    app.audio_engine = None
    app.dashboard_server = None
    app.overlay = None
    app.tray_controller = None
    app.tts_manager = None

    try:
        app.start()
    finally:
        app.stop()
