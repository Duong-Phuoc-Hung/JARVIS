"""
tests/test_rebuilt_atomic_io.py
===============================
Behavioral tests for rebuilt/atomic_io.py.
Verifies rules AIO-01 through AIO-07 (ATEST-01 to ATEST-07).
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure rebuilt module is importable
REBUILT_DIR = Path(__file__).resolve().parent.parent
if str(REBUILT_DIR) not in sys.path:
    sys.path.insert(0, str(REBUILT_DIR))

from atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
)


def test_atest_01_atomic_write_json_basic(tmp_path: Path) -> None:
    """ATEST-01: atomic_write_json creates target file with valid JSON payload."""
    target_file = tmp_path / "data.json"
    payload = {"status": "ok", "count": 42, "items": ["a", "b", "c"]}
    atomic_write_json(target_file, payload)

    assert target_file.exists()
    loaded = json.loads(target_file.read_text(encoding="utf-8"))
    assert loaded == payload


def test_atest_02_no_leftover_temp_files(tmp_path: Path) -> None:
    """ATEST-02: No .tmp.* files remain in directory after successful writes."""
    target_file = tmp_path / "state.json"
    atomic_write_json(target_file, {"version": 1})
    atomic_write_text(tmp_path / "hello.txt", "hello world")
    atomic_write_bytes(tmp_path / "data.bin", b"\x01\x02\x03")

    leftover = list(tmp_path.glob(".tmp.*"))
    assert len(leftover) == 0, f"Leftover temp files detected: {leftover}"


def test_atest_03_concurrent_15_threads_safety(tmp_path: Path) -> None:
    """ATEST-03: 15 concurrent threads writing same file with shared lock: no corruption or WinError 5."""
    target_file = tmp_path / "shared_concurrent.json"
    shared_lock = threading.Lock()
    num_threads = 15
    errors: list[Exception] = []

    def _worker(thread_idx: int) -> None:
        try:
            for iteration in range(5):
                payload = {
                    "thread_idx": thread_idx,
                    "iteration": iteration,
                    "timestamp": time.time_ns(),
                    "payload": f"thread_{thread_idx}_data_{iteration}" * 30,
                }
                atomic_write_json(target_file, payload, lock=shared_lock)
                time.sleep(0.002)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Concurrent writes threw errors: {errors}"
    assert target_file.exists()
    content = json.loads(target_file.read_text(encoding="utf-8"))
    assert "thread_idx" in content
    assert "iteration" in content
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_atest_04_retry_loop_on_transient_lock(tmp_path: Path) -> None:
    """ATEST-04: Transient PermissionError on attempts 1 and 2, succeeds on attempt 3."""
    target_file = tmp_path / "transient.json"
    payload = {"recovered": True}

    original_replace = Path.replace
    call_count = 0

    def mock_replace(self: Path, target: Path) -> Path:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise PermissionError(13, "WinError 5: Access is denied")
        return original_replace(self, target)

    with patch.object(Path, "replace", mock_replace):
        atomic_write_json(target_file, payload)

    assert call_count == 3
    assert target_file.exists()
    assert json.loads(target_file.read_text(encoding="utf-8")) == payload
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_atest_05_exhausted_retries_cleanup(tmp_path: Path) -> None:
    """ATEST-05: Persistent failure raises exception and cleans up temporary file."""
    target_file = tmp_path / "failed.json"

    def mock_replace_always_fail(self: Path, target: Path) -> Path:
        raise PermissionError(13, "Permanent WinError 5")

    with patch.object(Path, "replace", mock_replace_always_fail):
        with pytest.raises(PermissionError):
            atomic_write_json(target_file, {"should": "fail"})

    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_atest_06_atomic_write_bytes(tmp_path: Path) -> None:
    """ATEST-06: atomic_write_bytes preserves exact binary payload."""
    target_file = tmp_path / "binary.bin"
    raw = b"\x00\xFF\xAA\x55\xDE\xAD\xBE\xEF"
    atomic_write_bytes(target_file, raw)

    assert target_file.exists()
    assert target_file.read_bytes() == raw
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_atest_07_atomic_write_text(tmp_path: Path) -> None:
    """ATEST-07: atomic_write_text preserves exact UTF-8 text string."""
    target_file = tmp_path / "document.txt"
    text = "Xin chào Việt Nam! 🇻🇳 Special chars: & < > \" '\n"
    atomic_write_text(target_file, text, encoding="utf-8")

    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == text
    assert len(list(tmp_path.glob(".tmp.*"))) == 0
