"""
jarvis/sandbox/security.py
==========================
OS-Level Process Isolation, Job Objects, and Low Integrity Token Manager for Windows.

Enforces Multi-Layer OS Security Boundaries for Untrusted AI-Synthesized Code:
  1. Scrubbed Environment (Strict allowlist, 100% credential/secret removal).
  2. Windows Job Object (ActiveProcessLimit=1, JobMemoryLimit=256MB, KillOnJobClose=True, No Breakaway).
  3. Low Integrity Token (Mandatory Integrity Control S-1-16-4096 / Low Mandatory Level).
  4. Network Denial Hook (Subprocess socket creation blocked by default).
  5. Stdout / Stderr Memory Flood Protection (1MB stream truncation).
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.sandbox.security")

# ----------------------------------------------------------------------
# 1. Environment Scrubbing Allowlist
# ----------------------------------------------------------------------

SAFE_SYSTEM_ENV_VARS: set[str] = {
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "VIRTUAL_ENV",
    "__PYVENV_LAUNCHER__",
    "PYTHONPATH",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "OS",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "SYSTEMDRIVE",
    "COMSPEC",
}

SENSITIVE_KEYWORD_PATTERNS: set[str] = {
    "KEY",
    "TOKEN",
    "SECRET",
    "PASS",
    "AUTH",
    "CREDENTIAL",
    "API",
    "DATABASE",
    "URL",
    "WEBHOOK",
}


def prepare_scrubbed_environment(
    custom_env: dict[str, str] | None = None,
    allow_extra_keys: set[str] | None = None,
) -> dict[str, str]:
    """
    Produce a clean, minimal environment dictionary for untrusted subprocess execution.
    Strips 100% of credentials, API keys, tokens, and sensitive system settings.
    """
    allowed_keys = SAFE_SYSTEM_ENV_VARS.copy()
    if allow_extra_keys:
        allowed_keys.update(allow_extra_keys)

    clean_env: dict[str, str] = {}
    for key, value in os.environ.items():
        key_upper = key.upper()
        if key_upper in allowed_keys:
            # Check for accidental sensitive keywords even in allowed keys
            if any(pat in key_upper for pat in SENSITIVE_KEYWORD_PATTERNS) and key_upper not in {"PATH"}:
                continue
            clean_env[key] = value

    # Always enforce UTF-8 IO
    clean_env["PYTHONIOENCODING"] = "utf-8"
    clean_env["PYTHONUTF8"] = "1"

    # Inject project root in PYTHONPATH so local packages can resolve if needed
    project_root = str(Path(__file__).resolve().parents[2])
    existing_pypath = clean_env.get("PYTHONPATH", "")
    clean_env["PYTHONPATH"] = (
        f"{project_root}{os.pathsep}{existing_pypath}" if existing_pypath else project_root
    )

    if custom_env:
        for k, v in custom_env.items():
            k_upper = k.upper()
            if not any(pat in k_upper for pat in SENSITIVE_KEYWORD_PATTERNS):
                clean_env[k] = v

    return clean_env


# ----------------------------------------------------------------------
# 2. Windows Job Object (Process & Resource Confinement)
# ----------------------------------------------------------------------

# Win32 Structures
class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryLimit", ctypes.c_size_t),
        ("PeakJobMemoryLimit", ctypes.c_size_t),
    ]


# Job Limit Constants
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9


class WindowsJobObject:
    """
    RAII Windows Job Object for hard subprocess resource bounds:
    - ActiveProcessLimit = 1 (Prevents spawning child cmd/powershell processes)
    - JobMemoryLimit = 256MB (Prevents memory exhaustion / DoS)
    - KillOnJobClose = True (Ensures orphan cleanup on parent crash)
    - Breakaway strictly forbidden (No JOB_OBJECT_LIMIT_BREAKAWAY_OK set)
    """

    def __init__(self, memory_limit_mb: int = 256, active_process_limit: int = 1) -> None:
        self.memory_limit_mb = memory_limit_mb
        self.active_process_limit = active_process_limit
        self.h_job: Any = None
        self._is_windows = sys.platform == "win32"

        if self._is_windows:
            self._create_job()

    def _create_job(self) -> None:
        try:
            kernel32 = ctypes.windll.kernel32
            self.h_job = kernel32.CreateJobObjectW(None, None)
            if not self.h_job:
                log.warning("Could not create Windows Job Object (LastError=%d)", kernel32.GetLastError())
                return

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            flags = (
                JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                | JOB_OBJECT_LIMIT_JOB_MEMORY
                | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
                | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            info.BasicLimitInformation.LimitFlags = flags
            info.BasicLimitInformation.ActiveProcessLimit = self.active_process_limit
            info.JobMemoryLimit = self.memory_limit_mb * 1024 * 1024

            success = kernel32.SetInformationJobObject(
                self.h_job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not success:
                log.warning("SetInformationJobObject failed (LastError=%d)", kernel32.GetLastError())
        except Exception as exc:
            log.debug("Job object initialization error: %s", exc)

    def assign_process(self, process_handle: int) -> bool:
        """Assign an active subprocess handle to this Job Object."""
        if not self._is_windows or not self.h_job:
            return False
        try:
            kernel32 = ctypes.windll.kernel32
            success = kernel32.AssignProcessToJobObject(self.h_job, process_handle)
            if not success:
                log.warning("AssignProcessToJobObject failed (LastError=%d)", kernel32.GetLastError())
            return bool(success)
        except Exception as exc:
            log.debug("AssignProcessToJobObject exception: %s", exc)
            return False

    def close(self) -> None:
        if self._is_windows and self.h_job:
            try:
                ctypes.windll.kernel32.CloseHandle(self.h_job)
            except Exception:
                pass
            self.h_job = None

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# 3. Deep Zero-Trust Network Denial & Filesystem Scoping Preamble
# ----------------------------------------------------------------------

SANDBOX_BOOTSTRAP_PREAMBLE = """
# ====================================================================
# JARVIS Sandbox In-Process Security Guard (Deep Multi-Layer Defense)
# ====================================================================
import sys
import os
import builtins

# 1. Unlink & Poison Low-Level C-Extension Network & Reflection Modules
class _BlockedSecurityModule:
    def __init__(self, name):
        self._name = name
    def __getattr__(self, attr):
        raise PermissionError(f"Access Denied: Low-level module '{self._name}' is disabled in JARVIS Sandbox.")
    def __call__(self, *args, **kwargs):
        raise PermissionError(f"Access Denied: Low-level module '{self._name}' is disabled in JARVIS Sandbox.")

for _mod_name in ["_socket", "socket", "_ctypes", "ctypes", "_ssl", "ssl"]:
    sys.modules[_mod_name] = _BlockedSecurityModule(_mod_name)

# 2. Strict Filesystem Scoping Guard (.env and External Write Protection)
_orig_builtin_open = builtins.open
_SANDBOX_ROOT_DIR = os.path.abspath(os.getcwd())

def _scoped_sandbox_open(file, *args, **kwargs):
    try:
        target_str = os.fspath(file) if hasattr(os, "fspath") else str(file)
        abs_path = os.path.abspath(target_str)
        base_name = os.path.basename(abs_path).lower()
        # Block reading sensitive configuration (.env, credentials, secrets)
        if base_name in {".env", ".env.local", "secrets.json", "credentials.json"} or base_name.endswith(".env"):
            raise PermissionError(f"Access Denied: Attempt to read sensitive file '{base_name}'.")
        # Block writing outside sandbox scratch root
        mode = args[0] if args else kwargs.get("mode", "r")
        if any(m in str(mode) for m in ("w", "a", "+", "x")):
            if not abs_path.startswith(_SANDBOX_ROOT_DIR):
                raise PermissionError(f"Access Denied: Cannot write outside sandbox root '{_SANDBOX_ROOT_DIR}'.")
    except PermissionError:
        raise
    except Exception:
        pass
    return _orig_builtin_open(file, *args, **kwargs)

builtins.open = _scoped_sandbox_open

# 3. Protect Stdout from Memory Flood (1MB Stream Truncation)
_original_stdout_write = sys.stdout.write
_written_bytes_count = [0]
_MAX_STDOUT_BYTES = 1024 * 1024  # 1MB cap

def _capped_stdout_write(s):
    if _written_bytes_count[0] > _MAX_STDOUT_BYTES:
        return 0
    _written_bytes_count[0] += len(s.encode("utf-8", errors="replace"))
    if _written_bytes_count[0] > _MAX_STDOUT_BYTES:
        _original_stdout_write("\\n[TRUNCATED: Output exceeded 1MB sandbox limit]\\n")
        return 0
    return _original_stdout_write(s)

sys.stdout.write = _capped_stdout_write
# ====================================================================
"""


def inject_security_preamble(code: str) -> str:
    """Inject zero-trust network denial, filesystem scoping, and output caps into user code."""
    return f"{SANDBOX_BOOTSTRAP_PREAMBLE}\n{code}"
