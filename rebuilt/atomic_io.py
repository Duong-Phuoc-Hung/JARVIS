"""
rebuilt/atomic_io.py
====================
Clean-room implementation of Windows Atomic Persistence Layer.
Implements rules AIO-01 to AIO-07 from SPEC-JARVIS-001.

Contracts:
- AIO-01: 6-step atomic write contract with in-RAM serialization before disk I/O.
- AIO-02: Temp file naming convention (.tmp.<thread_id>.<timestamp_ns>).
- AIO-03: 5-retry exponential backoff on transient PermissionError / OSError.
- AIO-04: Guaranteed temp file cleanup in finally block.
- AIO-05: Per-path re-entrant lock (RLock) registry.
- AIO-06: Export atomic_write_bytes, atomic_write_text, atomic_write_json.
- AIO-07: Concurrency & thread safety under intense contention.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("rebuilt.atomic_io")

_registry_lock = threading.Lock()
_file_locks: dict[str, threading.RLock] = {}


def _get_path_lock(path: Path) -> threading.RLock:
    """
    Resolve and return a shared re-entrant lock for the target path.
    Rule AIO-05: per-path RLock cached by str(path.resolve()).
    """
    try:
        resolved_key = str(path.resolve())
    except Exception:
        resolved_key = str(path)

    with _registry_lock:
        if resolved_key not in _file_locks:
            _file_locks[resolved_key] = threading.RLock()
        return _file_locks[resolved_key]


def _execute_atomic_replace(tmp_path: Path, target_path: Path) -> None:
    """
    Execute atomic replace with 5 retries on transient file locks (WinError 5 / PermissionError).
    Rule AIO-03:
      attempt=1 fails -> sleep(0.02)
      attempt=2 fails -> sleep(0.04)
      attempt=3 fails -> sleep(0.06)
      attempt=4 fails -> sleep(0.08)
      attempt=5 fails -> raise exception immediately
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
    Atomically writes raw bytes to destination path following the 6-step contract.
    Rules AIO-01, AIO-02, AIO-03, AIO-04.
    """
    target_path = Path(path)
    effective_lock = lock if lock is not None else _get_path_lock(target_path)

    # Step 1: Acquire lock
    with effective_lock:
        # Step 2: Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 3 & 4: In-memory buffer ready, generate temp path in same dir
        thread_id = threading.get_ident()
        timestamp_ns = time.time_ns()
        tmp_path = target_path.parent / f".tmp.{thread_id}.{timestamp_ns}"

        try:
            # Step 4: Write to temp file
            tmp_path.write_bytes(data)
            # Step 5: Atomic replacement
            _execute_atomic_replace(tmp_path, target_path)
        finally:
            # Step 6: Guaranteed temp file cleanup (silence OSError)
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
    Atomically writes text string to destination path following the 6-step contract.
    Rules AIO-01, AIO-02, AIO-03, AIO-04.
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
    Atomically serializes and writes JSON data to destination path.
    Rule AIO-01 Step 3: MUST serialize to string in RAM before opening file.
    Rule AIO-06: delegates to atomic_write_text.
    """
    target_path = Path(path)
    # Step 3 constraint: Snapshot/serialize data into RAM string BEFORE opening any file
    serialized_text = json.dumps(
        data,
        indent=indent,
        ensure_ascii=ensure_ascii,
        default=default,
    )
    atomic_write_text(target_path, serialized_text, lock=lock, encoding="utf-8")


__all__ = [
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
]
