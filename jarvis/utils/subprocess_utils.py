"""
Subprocess utilities with safe encoding for Vietnamese Windows environments.

Root cause: Windows locale Vietnamese_Vietnam uses getpreferredencoding()='cp1252',
which cannot decode UTF-8 bytes like 0x81 (Vietnamese multi-byte sequences).
Using text=True without explicit encoding defaults to cp1252 -> UnicodeDecodeError.

Fix: Always specify encoding='utf-8', errors='replace' so:
  - Vietnamese output is decoded correctly
  - Non-UTF-8 bytes (e.g. cp437 OEM from cmd.exe) become replacement chars instead of crash
  - Warning is logged when replacement occurs so silent data corruption is detectable
"""
from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

_LOG = logging.getLogger(__name__)

# Suppress CMD/PowerShell window flash on Windows (R2 compliance)
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Replacement character U+FFFD -- written by errors='replace' when bytes can not decode
_REPLACEMENT = "\ufffd"


def run_safe(
    cmd,
    *,
    source: str,
    encoding: str = "utf-8",
    timeout=None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """
    Safe subprocess wrapper with UTF-8 encoding and CREATE_NO_WINDOW on Windows.

    Args:
        cmd: Command to run (list or shell string).
        source: Human-readable label for logging (e.g. 'shell_assistant.exec_cmd').
        encoding: Encoding for decoding output. Default 'utf-8'.
                  Use 'utf-16-le' for PowerShell 5 / wmic commands.
        timeout: Timeout in seconds for the underlying subprocess call.
        **kwargs: Additional keyword arguments forwarded to the subprocess call.

    Returns:
        subprocess.CompletedProcess with decoded stdout/stderr strings.

    Notes:
        - Always sets capture_output=True and text=True unless caller overrides.
        - errors='replace' prevents UnicodeDecodeError — garbled bytes become U+FFFD.
        - Logs a WARNING if replacement characters appear in output.
        - Sets CREATE_NO_WINDOW on Windows to suppress CMD window flash (R2 compliance).
    """
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    # Suppress terminal window on Windows (never override if caller sets creationflags)
    kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)

    # Remove any conflicting encoding/errors the caller may have passed
    kwargs.pop("encoding", None)
    kwargs.pop("errors", None)

    # CREATE_NO_WINDOW (R2 compliance) already injected via kwargs.setdefault above
    result = subprocess.run(
        cmd,
        encoding=encoding,
        errors="replace",
        timeout=timeout,
        **kwargs,
    )

    # Log warning if any bytes were replaced
    stdout_garbled = _REPLACEMENT in (result.stdout or "")
    stderr_garbled = _REPLACEMENT in (result.stderr or "")
    if stdout_garbled or stderr_garbled:
        _LOG.warning(
            "[subprocess:%s] Output contained non-%s bytes (replaced with '?'). "
            "stdout_garbled=%s stderr_garbled=%s cmd=%r",
            source,
            encoding.upper(),
            stdout_garbled,
            stderr_garbled,
            cmd if isinstance(cmd, str) else " ".join(str(x) for x in cmd),
        )

    return result
