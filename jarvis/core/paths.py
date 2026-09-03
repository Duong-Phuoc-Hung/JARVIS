"""
jarvis/core/paths.py
====================
Centralized path resolution for JARVIS data directories.

All writable files (logs, database, cache, skills, config) must use
get_data_dir() instead of relative paths, which fail when JARVIS is
installed in protected directories like C:\\Program Files\\.

Usage:
    from jarvis.core.paths import get_data_dir, data_path

    db_file  = data_path("memory.db")
    log_file = data_path("logs", "jarvis.log")
    cache    = data_path("cache", "whisper")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_data_dir() -> Path:
    """
    Returns writable per-user data dir for JARVIS.
    Priority: JARVIS_DATA_DIR env > %LOCALAPPDATA%\\JARVIS > ~/.jarvis
    Creates directory on first call.
    """
    override = os.environ.get("JARVIS_DATA_DIR")
    if override:
        d = Path(override)
    elif sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        d = Path(local_app) / "JARVIS" if local_app else Path.home() / ".jarvis"
    else:
        d = Path.home() / ".jarvis"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def data_path(*parts: str) -> Path:
    """
    Returns absolute path under the JARVIS data dir.
    Creates parent dirs automatically.

    Examples:
        data_path("memory.db")           -> %LOCALAPPDATA%/JARVIS/memory.db
        data_path("logs", "jarvis.log")  -> %LOCALAPPDATA%/JARVIS/logs/jarvis.log
        data_path("cache", "whisper")    -> %LOCALAPPDATA%/JARVIS/cache/whisper
    """
    p = get_data_dir().joinpath(*parts)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def logs_dir() -> Path:
    """Returns the logs/ subdirectory, creating it if needed."""
    d = get_data_dir() / "logs"
    d.mkdir(exist_ok=True)
    return d


def cache_dir(subdir: str = "") -> Path:
    """Returns a cache/ subdirectory, creating it if needed."""
    d = get_data_dir() / "cache"
    if subdir:
        d = d / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def hidden_subprocess_flags() -> dict:
    """
    Returns kwargs to prevent console popup windows on Windows.
    Usage: subprocess.run(cmd, **hidden_subprocess_flags())
    """
    if sys.platform == "win32":
        import subprocess
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
