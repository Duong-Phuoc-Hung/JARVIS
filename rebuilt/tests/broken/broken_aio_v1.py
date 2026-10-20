"""
rebuilt/tests/broken/broken_aio_v1.py
====================================
BROKEN VERSION 1: Violates Rule AIO-04.
Deliberately omits temp file cleanup in finally block, leaking .tmp files on disk.
Target test that MUST FAIL: test_atest_02_no_leftover_temp_files.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("broken.aio_v1")

_registry_lock = threading.Lock()
_file_locks: dict[str, threading.RLock] = {}


def _get_path_lock(path: Path) -> threading.RLock:
    try:
        resolved_key = str(path.resolve())
    except Exception:
        resolved_key = str(path)
    with _registry_lock:
        if resolved_key not in _file_locks:
            _file_locks[resolved_key] = threading.RLock()
        return _file_locks[resolved_key]


def _execute_atomic_replace(tmp_path: Path, target_path: Path) -> None:
    for attempt in range(1, 6):
        try:
            tmp_path.replace(target_path)
            return
        except (PermissionError, OSError) as exc:
            if attempt == 5:
                raise
            time.sleep(0.02 * attempt)


def atomic_write_bytes(
    path: Path | str,
    data: bytes,
    lock: threading.Lock | threading.RLock | None = None,
) -> None:
    target_path = Path(path)
    effective_lock = lock if lock is not None else _get_path_lock(target_path)
    with effective_lock:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        thread_id = threading.get_ident()
        timestamp_ns = time.time_ns()
        tmp_path = target_path.parent / f".tmp.{thread_id}.{timestamp_ns}"
        # BUG: Deliberately create extra leaked temp file and never clean up
        leaked_tmp = target_path.parent / f".tmp.leaked.{timestamp_ns}"
        leaked_tmp.write_bytes(b"leaked")
        tmp_path.write_bytes(data)
        _execute_atomic_replace(tmp_path, target_path)
        # BUG: No finally block to unlink tmp_path or leaked_tmp!


def atomic_write_text(
    path: Path | str,
    text: str,
    lock: threading.Lock | threading.RLock | None = None,
    encoding: str = "utf-8",
) -> None:
    target_path = Path(path)
    effective_lock = lock if lock is not None else _get_path_lock(target_path)
    with effective_lock:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        thread_id = threading.get_ident()
        timestamp_ns = time.time_ns()
        tmp_path = target_path.parent / f".tmp.{thread_id}.{timestamp_ns}"
        leaked_tmp = target_path.parent / f".tmp.leaked.{timestamp_ns}"
        leaked_tmp.write_text("leaked")
        tmp_path.write_text(text, encoding=encoding)
        _execute_atomic_replace(tmp_path, target_path)
        # BUG: No cleanup in finally!


def atomic_write_json(
    path: Path | str,
    data: Any,
    lock: threading.Lock | threading.RLock | None = None,
    indent: int = 2,
    ensure_ascii: bool = False,
    default: Callable[[Any], Any] | None = None,
) -> None:
    target_path = Path(path)
    serialized_text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, default=default)
    atomic_write_text(target_path, serialized_text, lock=lock, encoding="utf-8")


__all__ = ["atomic_write_bytes", "atomic_write_text", "atomic_write_json"]
