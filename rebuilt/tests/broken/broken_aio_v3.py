"""
rebuilt/tests/broken/broken_aio_v3.py
====================================
BROKEN VERSION 3: Violates Rule AIO-01 (Step 3 & Step 5).
Writes non-atomically directly to target file without locking or temporary file replace,
causing race conditions and data corruption under concurrent load.
Target test that MUST FAIL: test_atest_03_concurrent_15_threads_safety.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("broken.aio_v3")


def atomic_write_bytes(
    path: Path | str,
    data: bytes,
    lock: threading.Lock | threading.RLock | None = None,
) -> None:
    # BUG: Non-atomic direct write, ignores locks
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "wb") as f:
        f.write(data)


def atomic_write_text(
    path: Path | str,
    text: str,
    lock: threading.Lock | threading.RLock | None = None,
    encoding: str = "utf-8",
) -> None:
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # BUG: Non-atomic chunk write with simulated interleaving delay
    with open(target_path, "w", encoding=encoding) as f:
        half = len(text) // 2
        f.write(text[:half])
        time.sleep(0.001)
        f.write(text[half:])


def atomic_write_json(
    path: Path | str,
    data: Any,
    lock: threading.Lock | threading.RLock | None = None,
    indent: int = 2,
    ensure_ascii: bool = False,
    default: Callable[[Any], Any] | None = None,
) -> None:
    # BUG: Ignores external serialization locks, writes directly
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        # Deliberately stream partial data without atomicity
        time.sleep(0.0005)
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii, default=default)


__all__ = ["atomic_write_bytes", "atomic_write_text", "atomic_write_json"]
