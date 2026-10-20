"""
rebuilt/tests/broken/broken_aio_v2.py
====================================
BROKEN VERSION 2: Violates Rule AIO-03.
Only executes 2 retries instead of 5 on transient OS locks.
Target test that MUST FAIL: test_atest_04_retry_loop_on_transient_lock.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("broken.aio_v2")

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
    # BUG: Range is only 1..2 (2 attempts total instead of 5)
    for attempt in range(1, 3):
        try:
            tmp_path.replace(target_path)
            return
        except (PermissionError, OSError) as exc:
            if attempt == 2:
                # Raises too early!
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
        try:
            tmp_path.write_bytes(data)
            _execute_atomic_replace(tmp_path, target_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


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
        try:
            tmp_path.write_text(text, encoding=encoding)
            _execute_atomic_replace(tmp_path, target_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


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
