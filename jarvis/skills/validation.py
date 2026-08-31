"""
jarvis/skills/validation.py
=============================
Small, dependency-free validation/coercion helpers for skill manifests.

Deliberately NOT a JSON Schema framework: these are plain deterministic
type-coercion and identifier-safety checks used by SkillMetadata.from_dict()
and SkillRegistry so that a malformed or type-wrong manifest field can never
crash discovery or propagate an unsafe value into filesystem path
construction. Unknown/invalid fields fall back to safe, well-typed defaults
rather than raising -- discovery must fail closed per-skill, not globally.
"""
from __future__ import annotations

import re
from typing import Any

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")
_MAX_IDENTIFIER_LEN = 128


def is_safe_skill_identifier(name: Any) -> bool:
    """
    True if `name` is safe to use as a skill registry key AND as a
    filesystem path component (directory/file name) derived from
    untrusted manifest content. Rejects path separators, `..` traversal,
    null bytes, empty/overlong strings, and anything not matching a
    conservative identifier pattern.
    """
    if not isinstance(name, str) or not name:
        return False
    if len(name) > _MAX_IDENTIFIER_LEN:
        return False
    if ".." in name or "/" in name or "\\" in name or "\x00" in name:
        return False
    return bool(_SAFE_IDENTIFIER_RE.match(name))


def is_safe_entrypoint_identifier(name: Any) -> bool:
    """True if `name` is safe to use as a getattr() lookup for a skill's entrypoint function."""
    return isinstance(name, str) and bool(name) and name.isidentifier() and not name.startswith("_")


def coerce_str(value: Any, default: str) -> str:
    """Return `value` if it is a str, else `default`."""
    return value if isinstance(value, str) else default


def coerce_dict(value: Any) -> dict[str, Any]:
    """Return `value` if it is a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def coerce_optional_dict(value: Any) -> dict[str, Any] | None:
    """Return `value` if it is a dict, else None (covers both missing and wrong-typed input)."""
    return value if isinstance(value, dict) else None


def coerce_str_list(value: Any) -> list[str]:
    """Return the subset of `value` that are strings, if `value` is a list; else an empty list."""
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def coerce_float(value: Any, default: float) -> float:
    """Return `value` as a float if it is a real number (not bool), else `default`."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def coerce_int(value: Any, default: int) -> int:
    """Return `value` if it is an int (not bool), else `default`."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
