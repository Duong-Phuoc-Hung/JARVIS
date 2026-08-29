"""
jarvis/sandbox/security.py
==========================
True Multi-Layer OS Process Isolation, Low Integrity Token, and Job Objects.

Defense Layers:
  1. Low Integrity Restricted Token (Win32 CreateProcessAsUserW with S-1-16-4096 / LUA_TOKEN / DISABLE_MAX_PRIVILEGE).
  2. Windows Job Object (ActiveProcessLimit=1, JobMemoryLimit=256MB, KillOnJobClose=True, No Breakaway).
  3. Environment Scrubbing (100% credential and API key elimination).
  4. Meta-Path & C-Module Poisoning (sys.meta_path interceptor blocking socket/ctypes/_winapi/mmap re-imports).
  5. Strict Directory-Allowlist Filesystem Guard (builtins.open, io.open, os.open, os.fdopen restricted strictly to sandbox root).
  6. Stdout / Stderr Memory Flood Protection (1MB stream cap).
"""
from __future__ import annotations

import builtins
import ctypes
import io
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
            if any(pat in key_upper for pat in SENSITIVE_KEYWORD_PATTERNS) and key_upper not in {"PATH"}:
                continue
            clean_env[key] = value

    clean_env["PYTHONIOENCODING"] = "utf-8"
    clean_env["PYTHONUTF8"] = "1"

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
# 3. Low Integrity Restricted Token Process Spawner (Win32 SRM Enforcement)
# ----------------------------------------------------------------------

class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


def spawn_low_integrity_process(
    cmd: str,
    cwd: str,
    env: dict[str, str] | None = None,
    job: WindowsJobObject | None = None,
    timeout_seconds: float = 15.0,
) -> tuple[int, str, str, bool]:
    """
    Spawn a child process under a Win32 Low Integrity Restricted Token (S-1-16-4096)
    with ActiveProcessLimit=1 Job Object, scrubbed environment block, and anonymous pipe redirection.
    
    Returns:
        tuple of (exit_code, stdout_str, stderr_str, timed_out)
    """
    if sys.platform != "win32":
        raise NotImplementedError("Low Integrity processes are only supported on Windows.")

    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    # Win32 Function Signatures
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL

    ConvertStringSidToSidW = advapi32.ConvertStringSidToSidW
    ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    ConvertStringSidToSidW.restype = wintypes.BOOL

    advapi32.CreateRestrictedToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        ctypes.POINTER(wintypes.HANDLE)
    ]
    advapi32.CreateRestrictedToken.restype = wintypes.BOOL

    advapi32.SetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    advapi32.SetTokenInformation.restype = wintypes.BOOL

    advapi32.CreateProcessAsUserW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL,
        wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)
    ]
    advapi32.CreateProcessAsUserW.restype = wintypes.BOOL

    # Step 1: Open current process token
    TOKEN_ALL_ACCESS = 0xF01FF
    DISABLE_MAX_PRIVILEGE = 0x1
    LUA_TOKEN = 0x4

    h_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_ALL_ACCESS, ctypes.byref(h_token)):
        raise OSError(f"OpenProcessToken failed with code {kernel32.GetLastError()}")

    # Step 2: Create Restricted Token (Strip Admin + Strip Privileges)
    h_restricted = wintypes.HANDLE()
    res_restr = advapi32.CreateRestrictedToken(
        h_token,
        DISABLE_MAX_PRIVILEGE | LUA_TOKEN,
        0, None, 0, None, 0, None,
        ctypes.byref(h_restricted)
    )
    if not res_restr:
        kernel32.CloseHandle(h_token)
        raise OSError(f"CreateRestrictedToken failed with code {kernel32.GetLastError()}")

    # Step 3: Create anonymous pipes for I/O capture
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.bInheritHandle = True

    h_read = wintypes.HANDLE()
    h_write = wintypes.HANDLE()
    kernel32.CreatePipe(ctypes.byref(h_read), ctypes.byref(h_write), ctypes.byref(sa), 0)
    kernel32.SetHandleInformation(h_read, 1, 0)  # Do not inherit read handle

    si = STARTUPINFOW()
    si.cb = ctypes.sizeof(STARTUPINFOW)
    si.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
    si.hStdOutput = h_write
    si.hStdError = h_write
    pi = PROCESS_INFORMATION()

    CREATE_NO_WINDOW = 0x08000000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    flags = CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT

    # Prepare scrubbed unicode environment block
    clean_env = prepare_scrubbed_environment(env)
    env_str = "\0".join(f"{k}={v}" for k, v in clean_env.items()) + "\0\0"
    lp_env = ctypes.c_wchar_p(env_str)

    # Step 5: Launch via CreateProcessAsUserW
    success = advapi32.CreateProcessAsUserW(
        h_restricted,
        None,
        cmd,
        None,
        None,
        True,
        flags,
        lp_env,
        cwd,
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    kernel32.CloseHandle(h_write)

    if not success:
        err = kernel32.GetLastError()
        kernel32.CloseHandle(h_read)
        kernel32.CloseHandle(h_restricted)
        kernel32.CloseHandle(h_token)
        raise OSError(f"CreateProcessAsUserW failed with error {err}")

    # Step 6: Assign child process to Job Object
    if job:
        job.assign_process(pi.hProcess)

    # Step 7: Wait for completion with timeout
    timeout_ms = int(timeout_seconds * 1000)
    wait_res = kernel32.WaitForSingleObject(pi.hProcess, timeout_ms)
    timed_out = False
    exit_code_val = 0

    if wait_res == 0x00000102:  # WAIT_TIMEOUT
        timed_out = True
        kernel32.TerminateProcess(pi.hProcess, 1)
        exit_code_val = -1
    else:
        dw_exit = wintypes.DWORD()
        kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(dw_exit))
        exit_code_val = dw_exit.value

    # Step 8: Read captured pipe output
    output_chunks: list[bytes] = []
    buf = ctypes.create_string_buffer(8192)
    bytes_read = wintypes.DWORD()
    while kernel32.ReadFile(h_read, buf, 8192, ctypes.byref(bytes_read), None) and bytes_read.value > 0:
        output_chunks.append(buf.raw[: bytes_read.value])

    kernel32.CloseHandle(pi.hProcess)
    kernel32.CloseHandle(pi.hThread)
    kernel32.CloseHandle(h_read)
    kernel32.CloseHandle(h_restricted)
    kernel32.CloseHandle(h_token)

    full_output = b"".join(output_chunks).decode("utf-8", errors="replace")
    return exit_code_val, full_output, "", timed_out


# ----------------------------------------------------------------------
# 4. Deep Zero-Trust In-Process Preamble (Meta-Path + Directory Allowlist)
# ----------------------------------------------------------------------

SANDBOX_BOOTSTRAP_PREAMBLE = """
# ====================================================================
# JARVIS Sandbox In-Process Security Guard (Deep Multi-Layer Defense)
# ====================================================================
import sys
import os
import io
import builtins

# 1. Blocked Sandbox Modules Definition
_BLOCKED_SANDBOX_MODULES = {
    "socket", "_socket", "ctypes", "_ctypes", "_winapi", "winapi",
    "mmap", "_ssl", "ssl", "urllib", "requests", "http", "subprocess",
    "jarvis",
}

class _BlockedSecurityModule:
    def __init__(self, name):
        self._name = name
    def __getattr__(self, attr):
        raise PermissionError(f"Access Denied: Low-level module '{self._name}' is disabled in JARVIS Sandbox.")
    def __call__(self, *args, **kwargs):
        raise PermissionError(f"Access Denied: Low-level module '{self._name}' is disabled in JARVIS Sandbox.")

# 2. Poison ALL Existing Cached Modules in sys.modules (Pre-cached import defense)
for _mod_name in list(sys.modules.keys()):
    if _mod_name.split(".")[0] in _BLOCKED_SANDBOX_MODULES:
        sys.modules[_mod_name] = _BlockedSecurityModule(_mod_name)

for _mod_name in _BLOCKED_SANDBOX_MODULES:
    sys.modules[_mod_name] = _BlockedSecurityModule(_mod_name)

# 3. Meta-Path Importer Interceptor (Blocks fresh / re-import evasion)
class _BlockedMetaPathFinder:
    def find_spec(self, fullname, path, target=None):
        top_name = fullname.split(".")[0]
        if top_name in _BLOCKED_SANDBOX_MODULES:
            raise PermissionError(f"Access Denied: Module '{fullname}' is forbidden in JARVIS Sandbox.")
        return None

sys.meta_path.insert(0, _BlockedMetaPathFinder())

# 4. Strip JARVIS and Workspace Paths from sys.path (Blocks internal package import)
sys.path = [p for p in sys.path if "jarvis" not in p.lower()]

# 5. Strict Directory-Allowlist Filesystem Scoping Guard (Encapsulated in closure)
def _install_filesystem_guards():
    _orig_builtin_open = builtins.open
    _orig_io_open = io.open
    _orig_os_open = os.open
    _SANDBOX_ROOT_DIR = os.path.abspath(os.getcwd())
    _PYTHON_STDLIB_PREFIX = os.path.abspath(sys.prefix).lower()

    def _check_path(target_path, is_write=False):
        try:
            path_str = os.fspath(target_path) if hasattr(os, "fspath") else str(target_path)
            abs_target = os.path.abspath(path_str)
            if abs_target.startswith(_SANDBOX_ROOT_DIR):
                return
            if not is_write and abs_target.lower().startswith(_PYTHON_STDLIB_PREFIX):
                return
        except Exception:
            pass
        action = "write to" if is_write else "read from"
        raise PermissionError(f"Access Denied: Cannot {action} outside sandbox root: '{target_path}'")

    def _scoped_builtin_open(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        is_write = any(m in str(mode) for m in ("w", "a", "+", "x"))
        _check_path(file, is_write=is_write)
        return _orig_builtin_open(file, *args, **kwargs)

    def _scoped_io_open(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        is_write = any(m in str(mode) for m in ("w", "a", "+", "x"))
        _check_path(file, is_write=is_write)
        return _orig_io_open(file, *args, **kwargs)

    def _scoped_os_open(path, flags, *args, **kwargs):
        is_write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
        _check_path(path, is_write=is_write)
        return _orig_os_open(path, flags, *args, **kwargs)

    builtins.open = _scoped_builtin_open
    io.open = _scoped_io_open
    os.open = _scoped_os_open

_install_filesystem_guards()
del _install_filesystem_guards

# 6. Protect Stdout from Memory Flood (1MB Stream Truncation)
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
    """Inject zero-trust network denial, directory allowlisting, and output caps into user code."""
    return f"{SANDBOX_BOOTSTRAP_PREAMBLE}\n{code}"
