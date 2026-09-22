"""
jarvis/security/path_guard.py
=============================
Path Traversal Defense & Canonical Path Containment Validator (SEC-004).
Safely validates and resolves target file paths within designated workspace
or allowed directory roots, defending against directory climbing, null bytes,
and URL-encoded traversal patterns (%2e%2e%2f, %2e%2e\\).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import urllib.parse


def validate_safe_path(
    target_path: str | Path | None,
    base_dir: str | Path | None = None,
    allow_absolute: bool = False,
) -> tuple[bool, str, Path | None]:
    """
    Validates that target_path does not escape base_dir boundaries.

    Fails closed:
    - Rejects empty, whitespace-only, or None paths;
    - Rejects null bytes (\\x00);
    - Decodes URL-encoded traversal (%2e%2e, %2f, %5c);
    - Detects dot-dot sequence directory climbing (../ or ..\\);
    - Confirms canonical resolved path is contained within base_dir via is_relative_to().

    Returns:
        (is_safe, reason_or_code, resolved_path_or_none)
    """
    if target_path is None:
        return False, "PATH_EMPTY", None

    raw_path_str = str(target_path).strip()
    if not raw_path_str:
        return False, "PATH_EMPTY", None

    # 1. Null-byte rejection
    if "\x00" in raw_path_str:
        return False, "INVALID_CHARACTERS", None

    # 2. URL-decoding traversal patterns
    unquoted = urllib.parse.unquote(raw_path_str)
    if "\x00" in unquoted:
        return False, "INVALID_CHARACTERS", None

    # 3. Explicit base directory resolution
    if base_dir is None:
        base_dir = Path.cwd()
    base_path = Path(base_dir).resolve()

    # 4. Resolve candidate path and verify containment
    try:
        p = Path(unquoted)
        if p.is_absolute():
            resolved = p.resolve()
            if not allow_absolute:
                if resolved != base_path and not resolved.is_relative_to(base_path):
                    return False, "PATH_TRAVERSAL_DETECTED", None
        else:
            resolved = (base_path / p).resolve()
            if resolved != base_path and not resolved.is_relative_to(base_path):
                return False, "PATH_TRAVERSAL_DETECTED", None
        return True, "OK", resolved
    except (ValueError, RuntimeError, OSError):
        return False, "PATH_TRAVERSAL_DETECTED", None
