"""
Subprocess utilities with safe encoding for Vietnamese Windows environments.

Root cause: Windows locale Vietnamese_Vietnam uses getpreferredencoding()='cp1252',
which cannot decode UTF-8 bytes like 0x81 (Vietnamese multi-byte sequences).
subprocess.run(..., text=True) without explicit encoding uses cp1252 -> UnicodeDecodeError.

Fix: Always specify encoding='utf-8', errors='replace' so:
  - Vietnamese output is decoded correctly
  - Non-UTF-8 bytes (e.g. cp437 OEM from cmd.exe) become replacement chars instead of crash
  - Warning is logged when replacement occurs so silent data corruption is detectable
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any

_LOG = logging.getLogger(__name__)

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
    subprocess.run wrapper with explicit UTF-8 encoding and replacement error handling.

    Args:
        cmd: Command to run (list or shell string).
        source: Human-readable label for logging (e.g. 'shell_assistant.exec_cmd').
        encoding: Encoding for decoding subprocess output. Default 'utf-8'.
                  Use 'utf-16-le' for PowerShell 5 / wmic commands.
        timeout: Timeout in seconds passed to subprocess.run.
        **kwargs: Additional keyword arguments forwarded to subprocess.run.

    Returns:
        subprocess.CompletedProcess with decoded stdout/stderr strings.

    Notes:
        - Always sets capture_output=True and text=True unless caller overrides.
        - errors='replace' prevents UnicodeDecodeError -- garbled bytes become U+FFFD.
        - Logs a WARNING if replacement characters appear in output.
    """
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)

    # Remove any conflicting encoding/errors the caller may have passed
    kwargs.pop("encoding", None)
    kwargs.pop("errors", None)

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
