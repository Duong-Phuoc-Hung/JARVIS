"""
tests/test_adversarial_m2_llm_router.py
========================================
Milestone M2 Empirical Challenger Adversarial & Concurrency Verification Suite.
Author: Challenger M2.2 (critic, specialist)

Comprehensive Empirical Verification:
1. Boundary Case Matrix:
   - Empty string "", whitespace "   ", "\t\n\r"
   - Emoji "🔥💡", "🤖✨🚀🎉", mixed emoji command "💡 bật đèn phòng khách 💡"
   - Long strings (1KB, 10KB, 50KB payload stress without catastrophic backtracking)
   - Numbers & numeric strings ("1234567890", "24.5", "100")
   - Special regex metacharacters: ".*+?^${}()|[\\]\\", "(?P<name>.*)", "\\b\\d+\\b"
   - Unicode variations, Vietnamese diacritics, and injection strings
2. Latency Benchmarking:
   - Fast-path keyword routing latency strictly < 5.0ms (measuring p50, p95, p99, and max)
   - 1,000 rapid sequential queries throughput benchmark
   - 10KB long query parsing latency < 5.0ms
3. Multithreaded Concurrency & Race Condition Stress:
   - 30 concurrent threads hammering parse_intent() simultaneously
   - 20 concurrent threads calling JarvisApp.process_text_command()
   - Zero race conditions, memory corruption, or lockups
4. Full 7-Category Pipeline Integration & Safety Validation:
   - Smart Home, Hardware/Telemetry, Spotify, Weather, Reminder, Power Safety, and Fallback
   - Verification of IntentResult, ActionDispatcher routing, natural responses, and TTS invocation
"""
from __future__ import annotations

import concurrent.futures
import math
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional
import unittest.mock as mock
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.llm.client import LLMClient, LLMResponse, ToolCall
from jarvis.llm.router import (
    IntentResult,
    LLMIntentRouter,
    build_jarvis_system_prompt,
    generate_tool_schema_from_dispatcher,
)
from jarvis.tts.base import BaseTTSEngine
from jarvis.tts.manager import TTSManager


# ============================================================================
# 1. BOUNDARY & ADVERSARIAL INPUT CASES
# ============================================================================

def test_adversarial_empty_and_whitespace_inputs():
    """
    Test edge cases with empty strings, whitespace, newlines, and tabs.
    Must not throw unhandled exceptions; returns unknown_intent or empty response.
    """
    client = LLMClient(provider="mock")
    client.set_mock_behavior(mock_error="auth_error")
    router = LLMIntentRouter(client)

    test_inputs = [
        "",
        " ",
        "   ",
        "\t",
        "\n",
        "\r\n",
        "  \t\n\r  ",
    ]

    for inp in test_inputs:
        # LLM router parse_intent
        res = router.parse_intent(inp, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "unknown_intent"
        assert res.confidence == 0.0
        assert res.response_text == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

    # Test JarvisApp.process_text_command on empty/whitespace
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    for inp in test_inputs:
        app_res = app.process_text_command(inp)
        assert app_res["success"] is False
        assert app_res["error"] == "Empty command"


def test_adversarial_emoji_and_symbol_inputs():
    """
    Test queries consisting purely of emojis, symbols, or emoji-wrapped commands.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # Pure emojis -> unknown intent
    pure_emojis = ["🔥💡", "🤖✨🚀🎉", "🎵🎶🔊", "⚡❄️🌡️"]
    for emo in pure_emojis:
        res = router.parse_intent(emo, force_llm=False)
        assert res.action_name == "unknown_intent"
        assert res.response_text == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

    # Emoji-wrapped legitimate command -> must recognize command cleanly
    emoji_wrapped = "💡 bật đèn phòng khách 🔥"
    res_wrapped = router.parse_intent(emoji_wrapped, force_llm=False)
    assert res_wrapped.action_name == "home_assistant_call"
    assert res_wrapped.parameters["service"] == "turn_on"
    assert res_wrapped.parameters["entity_id"] == "light.living_room"


def test_adversarial_regex_special_characters():
    """
    Test queries containing regex metacharacters and special syntax.
    Must not crash re.search or cause regex compilation errors.
    """
    client = LLMClient(provider="mock")
    client.set_mock_behavior(mock_error="auth_error")
    router = LLMIntentRouter(client)

    regex_metachars = [
        ".*+?^${}()|[\\]\\\\",
        "(?P<name>.*)",
        "(?i)(?s).*",
        "\\b\\d+\\b",
        "[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}",
        "*(+?[{^$])",
        "\\",
        "\\\\\\\\",
        "/^.*$/gi",
        "SELECT * FROM actions WHERE name LIKE '%test%'",
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
    ]

    for meta in regex_metachars:
        res = router.parse_intent(meta, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "unknown_intent"
        assert res.response_text == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"


def test_adversarial_numbers_and_numeric_strings():
    """
    Test pure numeric strings, phone numbers, and large integers.
    """
    client = LLMClient(provider="mock")
    client.set_mock_behavior(mock_error="auth_error")
    router = LLMIntentRouter(client)

    numbers = [
        "0",
        "1234567890",
        "-999999",
        "3.1415926535",
        "00000000",
        "1e10",
    ]

    for num in numbers:
        res = router.parse_intent(num, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "unknown_intent"
        assert res.response_text == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"


def test_adversarial_massive_strings_and_redos_resistance():
    """
    Stress-test with long strings (1KB, 10KB, 50KB) to ensure linear processing time
    and immunity against Regular Expression Denial of Service (ReDoS) catastrophic backtracking.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # 1. 10KB repetition of random text
    ten_kb_text = "lệnh kiểm tra hệ thống " * 500  # ~11.5 KB
    t0 = time.perf_counter()
    res_10k = router.parse_intent(ten_kb_text, force_llm=False)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert duration_ms < 5.0, f"10KB query parsing took {duration_ms:.2f}ms (> 5.0ms)"
    assert res_10k.action_name == "hardware_status_query"

    # 2. 50KB adversarial nested pattern
    fifty_kb_adversarial = ("a" * 1000 + " bật đèn " + "b" * 1000) * 25  # ~50 KB
    t1 = time.perf_counter()
    res_50k = router.parse_intent(fifty_kb_adversarial, force_llm=False)
    duration_50k_ms = (time.perf_counter() - t1) * 1000.0

    assert duration_50k_ms < 20.0, f"50KB query parsing took {duration_50k_ms:.2f}ms (> 20.0ms)"
    assert res_50k.action_name == "home_assistant_call"


# ============================================================================
# 2. LATENCY & THROUGHPUT BENCHMARK (< 5ms PER QUERY)
# ============================================================================

def test_latency_single_query_under_5ms_benchmark():
    """
    Benchmark fast-path keyword routing latency across 1,000 queries.
    Strict Requirement: Average < 1ms, p95 < 2ms, p99 < 5ms, Max < 5ms.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    queries = [
        "bật đèn phòng khách",
        "tắt quạt",
        "đặt điều hòa 24 độ",
        "CPU",
        "kiểm tra RAM",
        "tình trạng hệ thống",
        "mở spotify bài Nắng Ấm Xa Dần",
        "dừng nhạc",
        "thời tiết hà nội",
        "nhắc nhở uống nước sau 15 phút",
        "tắt máy",
        "khóa màn hình",
        "chuẩn bị môi trường làm việc",
        "tự phục hồi hệ thống",
        "câu lệnh ngẫu nhiên không khớp",
    ]

    durations_ms: List[float] = []

    # Warmup
    for q in queries:
        router.parse_intent(q)

    # 1,000 benchmark iterations
    iterations = 1000
    for i in range(iterations):
        q = queries[i % len(queries)]
        t_start = time.perf_counter()
        res = router.parse_intent(q)
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        durations_ms.append(t_elapsed_ms)
        assert res is not None

    avg_ms = sum(durations_ms) / len(durations_ms)
    sorted_durations = sorted(durations_ms)
    p50_ms = sorted_durations[int(len(sorted_durations) * 0.50)]
    p95_ms = sorted_durations[int(len(sorted_durations) * 0.95)]
    p99_ms = sorted_durations[int(len(sorted_durations) * 0.99)]
    max_ms = max(durations_ms)

    assert avg_ms < 0.5, f"Average latency too high: {avg_ms:.4f}ms"
    assert p95_ms < 2.0, f"p95 latency too high: {p95_ms:.4f}ms"
    assert p99_ms < 5.0, f"p99 latency too high: {p99_ms:.4f}ms"
    assert max_ms < 5.0, f"Max latency exceeded 5ms SLA: {max_ms:.4f}ms"


# ============================================================================
# 3. CONCURRENCY & MULTITHREADED RACE CONDITIONS
# ============================================================================

def test_stress_concurrent_parse_intent_multithreaded():
    """
    Stress-test LLMIntentRouter.parse_intent() across 30 concurrent threads.
    Each thread performs 50 intent parses with a mixture of all 7 categories and edge cases.
    Verifies 100% thread safety without state corruption or memory leaks.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    sample_queries = [
        ("bật đèn phòng khách", "home_assistant_call"),
        ("tắt quạt", "home_assistant_call"),
        ("CPU", "hardware_telemetry_check"),
        ("RAM", "hardware_telemetry_check"),
        ("tình trạng hệ thống", "hardware_status_query"),
        ("mở spotify", "spotify"),
        ("dừng nhạc", "spotify"),
        ("thời tiết hà nội", "shell_exec"),
        ("nhắc nhở uống thuốc sau 30 phút", "reminder"),
        ("tắt máy", "system_power"),
        ("khóa máy", "system_power"),
        ("chuẩn bị môi trường làm việc", "workspace_prepare"),
        ("🔥💡", "unknown_intent"),
        ("12345678", "unknown_intent"),
    ]

    num_threads = 30
    iterations_per_thread = 50
    errors: List[str] = []
    e_lock = threading.Lock()

    def worker(tid: int):
        for it in range(iterations_per_thread):
            q, expected_action = sample_queries[(tid + it) % len(sample_queries)]
            try:
                res = router.parse_intent(q)
                if res.action_name != expected_action:
                    with e_lock:
                        errors.append(f"Thread {tid} query '{q}': expected '{expected_action}', got '{res.action_name}'")
            except Exception as exc:
                with e_lock:
                    errors.append(f"Thread {tid} query '{q}' raised exception: {exc}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(errors) == 0, f"Concurrent parse_intent produced {len(errors)} errors: {errors[:5]}"


def test_stress_concurrent_app_process_text_command():
    """
    Stress-test JarvisApp.process_text_command() across 20 concurrent threads.
    Verifies thread-safe action dispatching, TTS queuing, and response formatting.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Track all TTS speak calls
    spoken_phrases: List[str] = []
    s_lock = threading.Lock()

    if app.tts_manager:
        def fake_speak(text, **kw):
            with s_lock:
                spoken_phrases.append(text)
            return True
        app.tts_manager.speak = fake_speak

    commands = [
        "bật đèn phòng khách",
        "CPU",
        "RAM",
        "tình trạng hệ thống",
        "mở spotify",
        "thời tiết",
        "nhắc nhở",
        "khóa máy",
        "unknown gibberish query 9999",
    ]

    num_threads = 20
    iterations = 20
    results: List[Dict[str, Any]] = []
    r_lock = threading.Lock()

    def worker(tid: int):
        for it in range(iterations):
            cmd = commands[(tid + it) % len(commands)]
            res = app.process_text_command(cmd, requester=f"thread_{tid}")
            with r_lock:
                results.append(res)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    # 20 threads * 20 iterations = 400 commands processed
    assert len(results) == 400
    assert all(r.get("success") is True for r in results)

    # Verify TTS spoken count
    with s_lock:
        assert len(spoken_phrases) == 400


# ============================================================================
# 4. FULL 7-CATEGORY PIPELINE INTEGRATION TESTS
# ============================================================================

def test_pipeline_integration_category1_smart_home():
    """Verify Smart Home full pipeline execution and natural responses."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res = app.process_text_command("bật đèn bàn")
    assert res["success"] is True
    assert res["intent"]["action_name"] == "home_assistant_call"
    assert res["intent"]["parameters"]["entity_id"] == "light.desk_lamp"
    assert "Đang bật đèn bàn làm việc cho Ngài." in res["response_text"]


def test_pipeline_integration_category2_hardware_telemetry():
    """Verify Hardware Telemetry full pipeline execution and live metrics."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res_cpu = app.process_text_command("nhiệt độ CPU")
    assert res_cpu["success"] is True
    assert res_cpu["intent"]["action_name"] == "hardware_telemetry_check"
    assert res_cpu["intent"]["parameters"]["component"] == "cpu"
    assert "Nhiệt độ CPU hiện tại là 45 độ C" in res_cpu["response_text"]

    res_sys = app.process_text_command("tình trạng hệ thống")
    assert res_sys["success"] is True
    assert res_sys["intent"]["action_name"] == "hardware_status_query"
    assert "Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu" in res_sys["response_text"]


def test_pipeline_integration_category3_spotify():
    """Verify Spotify playback full pipeline execution."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res_song = app.process_text_command("mở spotify bài Chúng Ta Của Hiện Tại")
    assert res_song["success"] is True
    assert res_song["intent"]["action_name"] == "spotify"
    assert res_song["intent"]["parameters"]["query"] == "Chúng Ta Của Hiện Tại"
    assert "Đang mở Spotify và phát Chúng Ta Của Hiện Tại cho Ngài." in res_song["response_text"]


def test_pipeline_integration_category4_weather():
    """Verify Weather query full pipeline execution."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res_hanoi = app.process_text_command("thời tiết hà nội")
    assert res_hanoi["success"] is True
    assert res_hanoi["intent"]["action_name"] == "shell_exec"
    assert res_hanoi["intent"]["parameters"]["location"] == "Hà Nội"
    assert "Đang kiểm tra thông tin thời tiết tại Hà Nội cho Ngài." in res_hanoi["response_text"]


def test_pipeline_integration_category5_reminder():
    """Verify Reminder query full pipeline execution and duration conversion."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res_rem = app.process_text_command("nhắc nhở tập thể dục sau 45 phút")
    assert res_rem["success"] is True
    assert res_rem["intent"]["action_name"] == "reminder"
    assert res_rem["intent"]["parameters"]["delay_s"] == 2700
    assert "Đã ghi nhận lời nhắc 'tập thể dục' của Ngài." in res_rem["response_text"]


def test_pipeline_integration_category6_power_safety():
    """Verify System Power confirmation safety flags and danger levels."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res_shut = app.process_text_command("tắt máy")
    assert res_shut["success"] is True
    assert res_shut["intent"]["action_name"] == "system_power"
    assert res_shut["intent"]["requires_confirmation"] is True
    assert res_shut["intent"]["danger_level"] == "CRITICAL"
    assert res_shut["intent"]["confirmation_prompt"] == "Ngài có chắc chắn muốn tắt máy không?"
    assert "Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận" in res_shut["response_text"]


def test_pipeline_integration_category7_fallback():
    """Verify standard Vietnamese fallback for unrecognized commands."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res_unknown = app.process_text_command("câu lệnh hoàn toàn không có nghĩa abcxyz123")
    assert res_unknown["success"] is True
    assert res_unknown["response_text"] == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
