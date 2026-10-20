"""
jarvis/utils/atomic_io.py
=========================
Windows Atomic Persistence Layer following AGENTS.md Section 3 and PROJECT.md Contract 3.

Guarantees:
1. Thread serialization via caller-supplied or per-path `_save_lock = threading.Lock()`.
2. Safe data snapshot in RAM under memory lock before disk I/O.
3. Collision-proof temporary file named `.tmp.<thread_id>.<timestamp_ns>` in the same directory.
4. Atomic file replace (`tmp_path.replace(path)`).
5. 5-retry loop for transient `PermissionError` / `WinError 5: Access is denied` / `OSError`
   with exponential backoff (`time.sleep(0.02 * attempt)`).
6. Guaranteed temp file cleanup in `finally:`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("jarvis.utils.atomic_io")

_save_lock = threading.RLock()
_file_locks: dict[str, threading.RLock] = {}
_registry_lock = threading.Lock()


def _get_path_lock(path: Path) -> threading.RLock:
    """Return a shared re-entrant lock for the resolved file path."""
    try:
        resolved = str(path.resolve())
    except Exception:
        resolved = str(path)
    with _registry_lock:
        if resolved not in _file_locks:
            _file_locks[resolved] = threading.RLock()
        return _file_locks[resolved]


def _execute_atomic_replace(tmp_path: Path, target_path: Path) -> None:
    """
    Execute atomic replace with up to 5 retries on Windows transient file locks.
    Exponential backoff: 0.02 * attempt (0.02s, 0.04s, 0.06s, 0.08s).
    """
    for attempt in range(1, 6):
        try:
            tmp_path.replace(target_path)
            return
        except (PermissionError, OSError) as exc:
            if attempt == 5:
                log.error(
                    "Atomic replace failed after 5 attempts on %s (temp=%s): %s",
                    target_path,
                    tmp_path,
                    exc,
                )
                raise
            time.sleep(0.02 * attempt)


def atomic_write_bytes(
    path: Path | str,
    data: bytes,
    lock: threading.Lock | threading.RLock | None = None,
) -> None:
    """
    Atomically writes raw bytes to `path`.
    
    Args:
        path: Destination file path.
        data: Raw bytes to persist.
        lock: Optional external serialization lock. If None, uses path-based lock.
    """
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
    """
    Atomically writes text string to `path`.
    
    Args:
        path: Destination file path.
        text: Text string to persist.
        lock: Optional external serialization lock.
        encoding: Character encoding (default: utf-8).
    """
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
    """
    Atomically serializes and writes JSON data to `path`.
    
    Args:
        path: Destination file path.
        data: Data structure serializable to JSON.
        lock: Optional external serialization lock.
        indent: JSON indentation spaces (default: 2).
        ensure_ascii: Whether to escape non-ASCII characters (default: False).
        default: Custom JSON serializer function for complex objects.
    """
    target_path = Path(path)
    serialized = json.dumps(
        data,
        indent=indent,
        ensure_ascii=ensure_ascii,
        default=default,
    )
    atomic_write_text(target_path, serialized, lock=lock, encoding="utf-8")


__all__ = [
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
    "_save_lock",
]
