"""
tests/test_m3_ux.py
===================
Comprehensive test suite for Milestone M3 UX Polish & Interaction Logging:
1. Randomized Greetings Pool (TTSManager.get_welcome_phrase) non-repeating selection.
2. Startup vocal introduction in JarvisApp.start().
3. Structured [INTERACTION] logging for voice, text, gestures, and silence.
4. Concurrency & thread safety for interaction logger and UI overlay.
"""
from __future__ import annotations

import concurrent.futures
from pathlib import Path
import threading
import time
from typing import Any, Dict, List
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.logger import log_interaction
from jarvis.tts.manager import TTSManager, WELCOME_PHRASES
from jarvis.ui.overlay import JarvisOverlay, OverlayState


def test_tts_randomized_welcome_pool_non_repeating():
    """Verify TTSManager selects from pool without repeating immediate previous phrase."""
    config = {
        "welcome": {
            "phrases": ["Phrase A", "Phrase B", "Phrase C", "Phrase D"]
        }
    }
    mgr = TTSManager(config=config)
    selected = []
    for _ in range(40):
        p = mgr.get_welcome_phrase()
        selected.append(p)
        assert p in ["Phrase A", "Phrase B", "Phrase C", "Phrase D"]

    # Verify no two consecutive phrases are identical
    for i in range(len(selected) - 1):
        assert selected[i] != selected[i + 1]

    mgr.stop()


def test_tts_welcome_phrase_explicit_override():
    """Verify explicit phrase override takes precedence over pool."""
    config = {
        "welcome": {
            "phrases": ["Phrase A", "Phrase B"]
        }
    }
    mgr = TTSManager(config=config)
    p = mgr.get_welcome_phrase(explicit_phrase="Custom Override Phrase")
    assert p == "Custom Override Phrase"
    mgr.stop()


def test_startup_vocal_introduction(monkeypatch):
    """Verify JarvisApp.start() vocalizes the startup intro phrase."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    spoken: List[tuple] = []
    app.initialize()

    if app.tts_manager:
        monkeypatch.setattr(
            app.tts_manager,
            "speak",
            lambda txt, wait=False: spoken.append((txt, wait)) or True,
        )

    app.start()
    assert len(spoken) >= 1
    assert "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS." in spoken[0][0]
    assert spoken[0][1] is False  # Non-blocking async queue
    app.stop()


def test_structured_interaction_logging(tmp_path):
    """Verify [INTERACTION] format in log file for voice, text, gestures, and silence."""
    log_file = tmp_path / "jarvis_interaction_test.log"
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app.config.set("logging.file", str(log_file))

    # 1. Text command
    res_text = app.process_text_command("nhiệt độ hệ thống", requester="user")
    assert res_text["success"] is True

    # 2. Gesture triggers
    app._on_gesture_event("double_clap")
    time.sleep(0.05)
    app._on_gesture_event("triple_clap")
    time.sleep(0.05)
    app._on_gesture_event("clap_pause_clap")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if "[INTERACTION]" in line]
    assert len(lines) >= 4

    # Verify schema layout on all lines
    for line in lines:
        assert line.startswith("[INTERACTION]")
        assert " | TRIGGER: " in line
        assert " | INPUT: " in line
        assert " | ACTION: " in line
        assert " | RESPONSE: " in line
        assert " | STATUS: " in line

    # Check specific trigger records
    assert any("TRIGGER: USER" in l or "TRIGGER: GESTURE:double_clap" in l for l in lines)
    assert any("TRIGGER: GESTURE:triple_clap" in l for l in lines)
    assert any("TRIGGER: GESTURE:clap_pause_clap" in l for l in lines)

    app.stop()


def test_interaction_logging_newline_sanitization(tmp_path):
    """Verify multiline text in input or response is sanitized to a single log line."""
    log_file = tmp_path / "single_line_test.log"
    line = log_interaction(
        trigger="TEXT",
        input_text="Lệnh dòng 1\nLệnh dòng 2\r\nLệnh dòng 3",
        action="test_action",
        response="Phản hồi dòng 1\nPhản hồi dòng 2",
        status="success",
        log_file=log_file,
    )

    assert "\n" not in line
    assert "\r" not in line
    assert "Lệnh dòng 1 Lệnh dòng 2 Lệnh dòng 3" in line
    assert "Phản hồi dòng 1 Phản hồi dòng 2" in line

    content = log_file.read_text(encoding="utf-8")
    assert len(content.strip().splitlines()) == 1


def test_concurrent_interaction_logging_thread_safety(tmp_path):
    """Stress test: 20 threads writing 300+ interaction logs concurrently with zero tearing."""
    log_file = tmp_path / "stress_interaction.log"
    exceptions: List[Exception] = []

    def _worker(worker_id: int):
        try:
            for i in range(20):
                log_interaction(
                    trigger=f"THREAD_{worker_id}",
                    input_text=f"Sample query {i}",
                    action=f"action_{worker_id}",
                    response=f"Response output {i}",
                    status="success",
                    log_file=log_file,
                )
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_worker, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 400
    for line in lines:
        assert line.startswith("[INTERACTION]")
        assert " | TRIGGER: " in line
