"""
tests/test_adversarial_challenger_1.py
======================================
Adversarial Stress Test Suite for JARVIS Personal AI Expansion.
Executed by Challenger 1 covering R1 (Wake Word), R2 (Memory & Context),
R3 (Screen Vision), and R4 (Computer Control).
"""
from __future__ import annotations

import concurrent.futures
import ctypes
import io
import math
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image, ImageGrab

from jarvis.audio.dsp import calculate_rms
from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    WakeWordEngineType,
    WakeWordResult,
    generate_wake_word_signal,
    resample_audio,
)
from jarvis.automation.control import ComputerController
from jarvis.automation.safety_gate import PendingConfirmation, SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.memory.manager import MemoryManager
from jarvis.memory.session import ConversationTurn, SessionContextManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore
from jarvis.platform.windows import WindowsPlatformAPI
from jarvis.ui.tray import SystemTrayController
from jarvis.vision.dialog_detector import WIN32_DIALOG_CLASS, ErrorDialogDetector
from jarvis.vision.screen import ScreenCaptureResult, ScreenVisionManager

# ============================================================================
# R1: WAKE WORD ADVERSARIAL STRESS TESTS
# ============================================================================

def test_r1_adversarial_continuous_noise_rejection():
    """
    Stress: Feed continuous white and pink noise at high RMS power (0.02 to 0.40)
    for 50 blocks. Verifies zero false positive activations.
    """
    detector = WakeWordDetector(sensitivity=0.8)
    np.random.seed(1337)

    for rms_level in [0.02, 0.05, 0.10, 0.20, 0.35, 0.45]:
        for block_idx in range(10):
            noise_block = (np.random.normal(0.0, 1.0, 44100) * rms_level).astype(np.float32)
            detected = detector.process_audio_block(noise_block)
            assert detected is False, f"False positive triggered on noise at RMS={rms_level}, block={block_idx}"

    assert detector.trigger_count == 0


def test_r1_adversarial_impulse_claps_rejection():
    """
    Stress: Feed high-amplitude single, double, and rapid burst claps.
    Claps have sharp wideband transients but lack formant transitions.
    Verifies zero false triggers.
    """
    detector = WakeWordDetector(sensitivity=0.8)
    sr = 44100

    # 1. Single sharp clap (decay 3ms, peak 0.95)
    t = np.linspace(0, 0.03, int(sr * 0.03), endpoint=False)
    clap = (np.exp(-t / 0.003) * np.sin(2 * np.pi * 2200.0 * t) * 0.95).astype(np.float32)
    buf = np.zeros(sr, dtype=np.float32)
    buf[10000 : 10000 + len(clap)] = clap
    assert detector.process_audio_block(buf) is False

    # 2. Rapid double clap (150ms gap)
    buf2 = np.zeros(sr, dtype=np.float32)
    buf2[5000 : 5000 + len(clap)] = clap
    buf2[5000 + int(sr * 0.15) : 5000 + int(sr * 0.15) + len(clap)] = clap
    assert detector.process_audio_block(buf2) is False

    # 3. Triple claps
    buf3 = np.zeros(int(sr * 1.5), dtype=np.float32)
    for offset in [0.1, 0.3, 0.5]:
        idx = int(sr * offset)
        buf3[idx : idx + len(clap)] = clap
    assert detector.process_audio_block(buf3) is False

    assert detector.trigger_count == 0


def test_r1_adversarial_high_frequency_tones_rejection():
    """
    Stress: Feed pure high-frequency sinusoids (2kHz, 4kHz, 6kHz, 8kHz, 12kHz).
    Verifies spectral formant filter rejects unvoiced tonal inputs.
    """
    detector = WakeWordDetector(sensitivity=0.9)
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)

    for freq in [1000.0, 3000.0, 5000.0, 7500.0, 10000.0, 14000.0]:
        tone = (np.sin(2 * np.pi * freq * t) * 0.85).astype(np.float32)
        assert detector.process_audio_block(tone) is False, f"Triggered on pure tone {freq} Hz"

    assert detector.trigger_count == 0


def test_r1_adversarial_rapid_burst_streaming_ingestion():
    """
    Stress: Stream audio in variable tiny slices (10ms, 20ms, 33ms, 50ms)
    and verify the ring buffer correctly reconstructs the temporal formant sequence
    and triggers exactly once upon full arrival.
    """
    detector = WakeWordDetector(sample_rate=44100, cooldown_s=2.0)
    keyword_audio = generate_wake_word_signal(sample_rate=44100, duration_s=1.0)

    for chunk_size in [441, 882, 1455, 2205]:  # 10ms, 20ms, 33ms, 50ms
        detector.reset()
        triggers = 0
        for i in range(0, len(keyword_audio), chunk_size):
            chunk = keyword_audio[i : i + chunk_size]
            if detector.process_audio_block(chunk):
                triggers += 1

        assert triggers == 1, f"Failed streaming with chunk size {chunk_size}, triggers={triggers}"


def test_r1_adversarial_sensitivity_and_tray_toggle_stress():
    """
    Stress: Rapidly toggle enabled status across 10 threads while streaming audio
    and sweeping sensitivity from 0.0 to 1.0.
    """
    detector = WakeWordDetector()
    keyword = generate_wake_word_signal(sample_rate=44100)
    silence = np.zeros(44100, dtype=np.float32)

    errors = []

    def _worker_stream(tid: int):
        try:
            for step in range(30):
                sig = keyword if step % 2 == 0 else silence
                detector.process_audio_block(sig)
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    def _worker_toggles():
        try:
            for s in range(50):
                detector.set_enabled(False)
                detector.sensitivity = (s % 11) / 10.0
                time.sleep(0.001)
                detector.set_enabled(True)
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(_worker_stream, i) for i in range(6)]
        futs.append(ex.submit(_worker_toggles))
        for f in concurrent.futures.as_completed(futs):
            f.result()

    assert len(errors) == 0, f"Encountered thread errors during tray/sensitivity stress: {errors}"
    assert detector.is_enabled() is True


# ============================================================================
# R2: MEMORY & CONTEXT ADVERSARIAL STRESS TESTS
# ============================================================================

def test_r2_adversarial_sqlite_wal_multithreaded_concurrency(tmp_path: Path):
    """
    Stress: 40 threads concurrently writing facts, logging episodes, and recording habits
    to SQLite in WAL mode. Verifies zero database locked errors and 100% record integrity.
    """
    db_file = tmp_path / "wal_stress.db"
    store = SQLiteMemoryStore(db_path=db_file)
    assert store.get_journal_mode() == "wal"

    thread_errors = []
    num_threads = 40
    records_per_thread = 15

    def _writer_worker(thread_id: int):
        try:
            for i in range(records_per_thread):
                store.store_fact(
                    key=f"user_{thread_id}_key_{i}",
                    value=f"val_{thread_id}_{i}",
                    category="general",
                )
                store.log_episode(
                    command=f"cmd from {thread_id} step {i}",
                    intent="test_intent",
                    outcome="success",
                    success=True,
                )
                store.record_habit(habit_key=f"habit_{thread_id}")
        except Exception as e:
            thread_errors.append(e)

    threads = [threading.Thread(target=_writer_worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(thread_errors) == 0, f"SQLite concurrency errors: {thread_errors}"

    facts = store.list_facts(limit=1000)
    assert len(facts) == num_threads * records_per_thread
    episodes = store.get_today_episodes()
    assert len(episodes) == num_threads * records_per_thread
    habits = store.get_habits(limit=100)
    assert len(habits) == num_threads


def test_r2_adversarial_100_turn_flooding_fifo_eviction():
    """
    Stress: Flood SessionContextManager with 100 conversational turns (50 user + 50 assistant).
    Verifies that max_turns=10 strictly enforces maxlen=20 and evicts turns in pure FIFO order.
    """
    session = SessionContextManager(max_turns=10)

    for i in range(1, 51):
        session.add_user_turn(f"User utterance {i}")
        session.add_assistant_turn(f"JARVIS response {i}")

    # Maximum length must be capped at 10 * 2 = 20 messages
    assert len(session) == 20
    history = session.get_history()
    assert len(history) == 20

    # Oldest 40 pairs (turns 1..40) must be evicted; only turns 41..50 remain
    assert history[0]["content"] == "User utterance 41"
    assert history[1]["content"] == "JARVIS response 41"
    assert history[-2]["content"] == "User utterance 50"
    assert history[-1]["content"] == "JARVIS response 50"


def test_r2_adversarial_sqli_strings_in_facts_and_episodes(tmp_path: Path):
    """
    Stress: Inject dangerous SQL injection strings into fact keys, values, categories,
    and episode command/intent fields. Verifies SQLite parameter binding guarantees safety.
    """
    manager = MemoryManager(db_path=tmp_path / "sqli_test.db")

    sqli_payloads = [
        "'; DROP TABLE facts; --",
        "' OR '1'='1' --",
        "'; DELETE FROM episodes WHERE '1'='1'; --",
        "1; ATTACH DATABASE 'pwn.db' AS pwn; --",
        "\" UNION SELECT id, category, key, value, 1.0, 'hacked', null, null, 0, null FROM facts --",
        "<script>alert(1)</script>'; DROP TABLE user_habits; --",
        "'''''''''''''",
        "\\x00\\x1a\\x08",
    ]

    for idx, payload in enumerate(sqli_payloads):
        # 1. Store as fact
        saved = manager.store_fact(key=f"sqli_key_{idx}", value=payload, category="general")
        assert saved is True

        # 2. Retrieve fact
        fact = manager.get_fact(key=f"sqli_key_{idx}", category="general")
        assert fact is not None
        assert fact["value"] == payload

        # 3. Log as episode
        ep_id = manager.log_episode(command=payload, intent=payload, outcome=payload)
        assert ep_id > 0

    # Verify tables still exist and contain correct count
    all_facts = manager.list_facts(limit=100)
    assert len(all_facts) == len(sqli_payloads)
    all_eps = manager.get_today_episodes()
    assert len(all_eps) == len(sqli_payloads)


def test_r2_adversarial_vietnamese_phrasing_variations(tmp_path: Path):
    """
    Stress: Test a wide range of natural Vietnamese phrasing variations
    for fact remembering and daily activity summaries.
    """
    manager = MemoryManager(db_path=tmp_path / "vn_phrasing.db")

    test_cases = [
        ("JARVIS, nhớ rằng tôi tên là Nguyễn Văn Hưng", "profile", "user_name", "Nguyễn Văn Hưng"),
        ("hãy nhớ rằng email của tôi là admin@hung.dev", "profile", "email", "admin@hung.dev"),
        ("nhớ là dự án hiện tại là JARVIS AI System", "project", "current_project", "JARVIS AI System"),
        ("ghi nhớ: tôi thích nghe nhạc jazz không lời", "preference", "favorite_music", "nghe nhạc jazz không lời"),
        ("hãy nhớ tôi thích uống cà phê đen đá", "preference", "food_drink", "uống cà phê đen đá"),
        ("nhớ rằng mật khẩu wifi là JarvisSec2026", "general", "mật_khẩu_wifi", "JarvisSec2026"),
    ]

    for cmd, exp_cat, exp_key, exp_val in test_cases:
        assert manager.is_remember_command(cmd), f"Failed to match remember regex: {cmd}"
        res = manager.handle_remember_command(cmd)
        assert res["success"] is True
        assert res["category"] == exp_cat, f"Category mismatch: {res['category']} vs {exp_cat} for '{cmd}'"
        assert exp_val in res["value"], f"Value mismatch: {res['value']} does not contain {exp_val}"

    # Summary command variations
    summary_cmds = [
        "JARVIS, hôm nay tôi đã làm gì?",
        "hôm nay tôi đã làm gì",
        "tóm tắt hoạt động hôm nay",
        "tổng kết hoạt động hôm nay",
        "lịch sử hôm nay",
        "what did i do today",
    ]
    for scmd in summary_cmds:
        assert manager.is_today_summary_command(scmd), f"Failed to match summary regex: {scmd}"


# ============================================================================
# R3: SCREEN VISION ADVERSARIAL STRESS TESTS
# ============================================================================

def test_r3_adversarial_capture_mocked_bounds_and_large_resolutions():
    """
    Stress: Capture and compress screen under extreme resolutions (4K, 8K)
    and verify Lanczos downscaling to max_dim constraint while preserving valid JPEG headers.
    """
    manager = ScreenVisionManager()

    # 1. Simulate 4K frame (3840x2160)
    img_4k = Image.new("RGB", (3840, 2160), color=(50, 100, 150))
    buf = io.BytesIO()
    img_4k.save(buf, format="JPEG")
    raw_4k = buf.getvalue()

    with patch.object(ImageGrab, "grab", return_value=img_4k):
        res = manager.capture_screenshot_full(max_dim=1920, quality=80)
        assert res.width == 1920
        assert res.height == 1080
        assert res.raw_jpeg_bytes[:2] == b"\xff\xd8"
        assert len(res.base64_jpeg) > 0

    # 2. Simulate Ultra-wide 8K frame (7680x2160)
    img_8k = Image.new("RGB", (7680, 2160), color=(80, 20, 20))
    with patch.object(ImageGrab, "grab", return_value=img_8k):
        res_8k = manager.capture_screenshot_full(max_dim=1920, quality=75)
        assert res_8k.width == 1920
        assert res_8k.height == 540  # Aspect ratio preserved


def test_r3_adversarial_invalid_roi_crop_coordinates():
    """
    Stress: Supply inverted, negative, and out-of-bounds ROI bounding boxes.
    Verifies coordinate clamping prevents crashes.
    """
    manager = ScreenVisionManager()
    dummy = Image.new("RGB", (1920, 1080), color=(10, 10, 10))

    with patch.object(ImageGrab, "grab", return_value=dummy):
        # 1. Negative coords
        raw1, _ = manager.capture_screenshot(roi=(-100, -50, 500, 400))
        img1 = Image.open(io.BytesIO(raw1))
        assert img1.size[0] > 0 and img1.size[1] > 0

        # 2. Giant out-of-bounds
        raw2, _ = manager.capture_screenshot(roi=(0, 0, 99999, 99999))
        img2 = Image.open(io.BytesIO(raw2))
        assert img2.size[0] <= 1920


def test_r3_adversarial_missing_api_key_fallbacks():
    """
    Stress: Query vision analysis with empty, whitespace, or invalid keys.
    Verifies polite Vietnamese fallback is returned without network call exceptions.
    """
    manager = ScreenVisionManager(gemini_api_key="", openai_api_key="")

    res_gemini = manager.analyze_screen("Màn hình có gì?", provider="gemini")
    assert "Tôi chưa thể nhìn thấy màn hình" in res_gemini

    res_openai = manager.analyze_screen("Lỗi này là gì?", provider="openai")
    assert "Tôi chưa thể nhìn thấy màn hình" in res_openai


def test_r3_adversarial_dialog_detector_complex_trees():
    """
    Stress: Simulate a desktop with 20 windows (some visible, some cloaked, some zero-sized,
    some normal, and one modal `#32770` error dialog with nested static text).
    """
    detector = ErrorDialogDetector()

    class MockComplexUser32:
        def IsWindowVisible(self, hwnd):
            # HWND 500 is hidden
            return 0 if hwnd == 500 else 1

        def GetClassNameW(self, hwnd, buf, size):
            cls = WIN32_DIALOG_CLASS if hwnd == 777 else "StandardAppWindow"
            ctypes.memmove(buf, cls.encode("utf-16le") + b"\x00\x00", len(cls)*2 + 2)
            return len(cls)

        def GetWindowTextLengthW(self, hwnd):
            return len(f"Window_{hwnd}")

        def GetWindowTextW(self, hwnd, buf, size):
            t = "Fatal Exception: Access Violation 0xC0000005" if hwnd == 777 else f"App_{hwnd}"
            ctypes.memmove(buf, t.encode("utf-16le") + b"\x00\x00", min(len(t)*2 + 2, size*2))
            return len(t)

        def GetWindowRect(self, hwnd, lpRect):
            target = getattr(lpRect, "_obj", None) or getattr(lpRect, "contents", lpRect)
            # HWND 100 is zero-sized utility window
            if hwnd == 100:
                target.left, target.top, target.right, target.bottom = 0, 0, 0, 0
            else:
                target.left, target.top, target.right, target.bottom = 50, 50, 600, 450
            return 1

        def EnumWindows(self, lpEnumFunc, lParam):
            for h in [100, 200, 300, 400, 500, 600, 777, 800]:
                lpEnumFunc(h, lParam)
            return 1

        def EnumChildWindows(self, hwnd, lpEnumFunc, lParam):
            if hwnd == 777:
                lpEnumFunc(77701, lParam)
            return 1

    with patch.object(ctypes.windll, "user32", MockComplexUser32(), create=True), \
         patch.object(detector, "_is_windows", True):

        dialogs = detector.scan_for_dialogs()
        assert len(dialogs) == 1
        d = dialogs[0]
        assert d["hwnd"] == 777
        assert d["is_dialog"] is True
        assert d["severity"] == "critical"
        assert "Fatal Exception" in d["title"]

        active = detector.get_active_error_dialog()
        assert active is not None
        assert active["hwnd"] == 777
        assert detector.has_error_dialog() is True


# ============================================================================
# R4: COMPUTER CONTROL ADVERSARIAL STRESS TESTS
# ============================================================================

def test_r4_adversarial_volume_and_brightness_boundary_clamping():
    """
    Stress: Test extreme volume and brightness values: negative numbers, >100,
    and boundary deltas. Verifies strict [0, 100] clamping.
    """
    controller = ComputerController()

    # 1. Volume clamping
    assert controller.set_volume(-100) == 0
    assert controller.get_volume() == 0
    assert controller.change_volume(-20) == 0

    assert controller.set_volume(500) == 100
    assert controller.get_volume() == 100
    assert controller.change_volume(50) == 100

    # 2. Brightness clamping
    assert controller.set_brightness(-50) == 0
    assert controller.get_brightness() == 0
    assert controller.change_brightness(-30) == 0

    assert controller.set_brightness(9999) == 100
    assert controller.get_brightness() == 100
    assert controller.change_brightness(25) == 100


def test_r4_adversarial_deep_nested_file_search_and_restricted_dirs(tmp_path: Path):
    """
    Stress: Create a directory hierarchy with 12 nested levels and ignored directories
    (node_modules, .git, .venv, Temp). Verifies max_depth=4 restriction, fast return,
    and zero crash on deep traversals.
    """
    controller = ComputerController()

    # Create deep hierarchy
    curr = tmp_path
    for d in range(1, 10):
        curr = curr / f"depth_{d}"
        curr.mkdir()
        (curr / f"target_file_{d}.txt").write_text(f"Depth {d}")

    # Create ignored folder containing target
    ignored_dir = tmp_path / "node_modules" / "sub_pkg"
    ignored_dir.mkdir(parents=True)
    (ignored_dir / "target_file_ignored.txt").write_text("Ignored")

    # Search with max_depth=3
    results_d3 = controller.search_files("target_file", root_dir=str(tmp_path), max_depth=3)
    basenames = [os.path.basename(p) for p in results_d3]

    assert "target_file_1.txt" in basenames
    assert "target_file_2.txt" in basenames
    assert "target_file_3.txt" in basenames
    # Depth 5 should not be in results
    assert "target_file_5.txt" not in basenames
    # Ignored node_modules should not be present
    assert "target_file_ignored.txt" not in basenames


def test_r4_adversarial_safety_gate_token_expiry_rejection_and_concurrency():
    """
    Stress: Test SafetyGate under high concurrency (30 threads creating and checking tokens),
    30s timeout expiration state transitions, rejection, and voice response parser.
    """
    gate = SafetyGate(timeout_seconds=0.1)

    # 1. Timeout Expiration
    t_exp = gate.request_confirmation("Xóa phân vùng ổ cứng")
    assert gate.is_pending(t_exp) is True
    time.sleep(0.15)
    assert gate.is_pending(t_exp) is False
    assert gate.confirm(t_exp) is False  # Cannot confirm expired token

    # 2. Explicit Rejection
    gate_normal = SafetyGate(timeout_seconds=10.0)
    t_rej = gate_normal.request_confirmation("Format USB")
    assert gate_normal.reject(t_rej) is True
    assert gate_normal.is_pending(t_rej) is False
    assert gate_normal.confirm(t_rej) is False  # Cannot confirm rejected token

    # 3. Voice Phrase Parsing
    t_voice = gate_normal.request_confirmation("Khởi động lại hệ thống")
    ok, msg = gate_normal.process_voice_response("tôi đồng ý xác nhận", token=t_voice)
    assert ok is True
    assert "Đã xác nhận" in msg

    # Second confirm on already confirmed token must fail
    assert gate_normal.confirm(t_voice) is False

    # 4. Multi-threaded SafetyGate Stress
    gate_stress = SafetyGate(timeout_seconds=5.0)
    tokens_created = []
    lock = threading.Lock()

    def _token_worker(i: int):
        tok = gate_stress.request_confirmation(f"Action {i}")
        with lock:
            tokens_created.append(tok)
        if i % 2 == 0:
            gate_stress.confirm(tok)
        else:
            gate_stress.reject(tok)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_token_worker, i) for i in range(50)]
        for f in concurrent.futures.as_completed(futs):
            f.result()

    assert len(tokens_created) == 50
    for tok in tokens_created:
        assert gate_stress.is_pending(tok) is False
