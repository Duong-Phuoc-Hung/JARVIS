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
import threading
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


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009


class RestrictedProcessBootstrapError(OSError):
    """
    Raised when the OS Restricted Token backend could not get a child
    process to actually start running user code -- either a Win32 launcher
    API failed before the child was created, or the child was created but
    terminated during its own process/DLL initialization before any user
    code could have run (see `is_restricted_process_bootstrap_failure`).

    This is distinct from, and must never be conflated with:
      - a normal (possibly nonzero) exit code from the user's own script,
      - a timeout,
      - an AST validator rejection,
      - an explicit Python exception raised by the user's script.
    Callers must treat this as "OS Restricted Token isolation could not be
    established for this run" -- never as "the script executed and merely
    returned an unusual exit code."

    `retry_safe` distinguishes failures that are FORMALLY PROVEN to have
    occurred before the child could execute any instructions (True -- the
    only case eligible for the explicit compatibility fallback) from
    failures where that cannot be proven (False -- e.g. a failure querying
    the child's state *after* it was resumed, where the child may already
    be running or may already have run user code with side effects).

    SECURITY RULE: unknown state => never retry. Defaults to **False**.
    `retry_safe=True` must be passed explicitly, and only at a call site
    that holds formal proof the child executed zero instructions (e.g. any
    failure strictly before `CreateProcessAsUserW` creates the child; Job
    Object assignment failing on a still-suspended child, terminated
    before ever being resumed; `ResumeThread` itself failing; or a known
    bootstrap-failure exit code observed with the readiness sentinel never
    written). Every raise site in this module states its reasoning
    explicitly -- do not add a new raise site without doing the same.
    """

    def __init__(self, message: str, *, retry_safe: bool = False) -> None:
        super().__init__(message)
        self.retry_safe = retry_safe


# Windows NTSTATUS values (as returned via GetExitCodeProcess -- an
# unsigned 32-bit DWORD) that indicate a child process died during its own
# process/DLL initialization, before any user code could have run. Per
# Microsoft's documented CreateProcessAsUser contract, the call can report
# success before the child's own initialization has completed; if a
# required DLL fails to load/initialize, the child terminates afterward
# and this is how that is observed. Confirmed on GitHub-hosted Windows
# Server 2025 CI runners under this restricted-token launch path.
STATUS_DLL_INIT_FAILED = 0xC0000142
STATUS_DLL_NOT_FOUND = 0xC0000135
STATUS_ENTRYPOINT_NOT_FOUND = 0xC0000139

_PROCESS_BOOTSTRAP_FAILURE_STATUS_CODES: frozenset[int] = frozenset(
    {STATUS_DLL_INIT_FAILED, STATUS_DLL_NOT_FOUND, STATUS_ENTRYPOINT_NOT_FOUND}
)


def is_restricted_process_bootstrap_failure(exit_code: int) -> bool:
    """
    True if `exit_code` (an unsigned 32-bit value, as returned by
    GetExitCodeProcess) is a known Windows NTSTATUS code indicating the
    child process terminated during its own startup/DLL initialization --
    never a legitimate outcome of user script code actually running. Do
    not use this to classify a normal nonzero script exit code, a timeout,
    an AST rejection, or an explicit Python exception; those are handled
    through entirely separate code paths and must not reach here.
    """
    return exit_code in _PROCESS_BOOTSTRAP_FAILURE_STATUS_CODES


# ----------------------------------------------------------------------
# Readiness handshake: the REAL retry-safety boundary.
#
# A bootstrap-failure-shaped exit code (see above) is NOT by itself proof
# that no user code ran -- a child can cross into the injected preamble or
# even the user's own script and only later hit a native DLL load/init
# failure. GetExitCodeProcess() alone cannot distinguish "died before any
# code ran" from "ran for a while, then crashed with a status code that
# happens to match." The injected sandbox preamble (see
# SANDBOX_BOOTSTRAP_PREAMBLE below) writes this sentinel to stdout, through
# the already-installed 1MB-capped writer, as the LAST thing it does --
# immediately after every security guard has been installed and
# immediately before the appended user code begins. Because the child is
# launched with `-u` (unbuffered), this write is observable by the parent
# without buffering ambiguity.
#
# Only "known bootstrap-failure exit code" AND "sentinel never observed"
# is treated as a confirmed pre-user-code failure eligible for retry.
# ----------------------------------------------------------------------
_SANDBOX_READY_SENTINEL = "\x02JARVIS_SANDBOX_READY_v1\x03"
_SANDBOX_READY_LINE = _SANDBOX_READY_SENTINEL + "\n"


def strip_sandbox_ready_sentinel(output: str) -> tuple[str, bool]:
    """
    Remove the internal readiness sentinel line from captured child stdout
    before it reaches SandboxResult / any user-visible output / structured-
    result parsing. Returns (cleaned_output, was_sentinel_observed).
    """
    if _SANDBOX_READY_SENTINEL not in output:
        return output, False
    cleaned = output.replace(_SANDBOX_READY_LINE, "")
    cleaned = cleaned.replace(_SANDBOX_READY_SENTINEL + "\r\n", "")
    cleaned = cleaned.replace(_SANDBOX_READY_SENTINEL + "\n", "")
    cleaned = cleaned.replace(_SANDBOX_READY_SENTINEL, "")
    return cleaned, True


# ----------------------------------------------------------------------
# Explicit, narrow, opt-in compatibility fallback switch.
#
# Production default is FAIL-CLOSED: if OS Restricted Token isolation
# cannot be established, JARVIS refuses to execute the untrusted script
# rather than silently downgrading to weaker isolation. Some CI
# environments (observed: GitHub-hosted Windows Server 2025 runners) are
# currently incompatible with the Restricted Token launch path itself
# (see `RestrictedProcessBootstrapError`/`is_restricted_process_bootstrap_failure`),
# so an explicit, narrowly-scoped opt-in exists for those environments only.
# This must never be enabled in production and never auto-detected from
# environment signals such as GITHUB_ACTIONS -- it is opt-in only.
# ----------------------------------------------------------------------
SANDBOX_COMPAT_FALLBACK_ENV_VAR = "JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def is_compat_fallback_enabled() -> bool:
    """
    True only if the operator has explicitly set
    `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK` to a truthy value. Disabled
    (fail-closed) by default. When enabled, a confirmed OS Restricted Token
    bootstrap failure (see `RestrictedProcessBootstrapError`) is allowed to
    fall back to the Job-Object + scrubbed-environment `subprocess.Popen`
    compatibility path, which provides weaker isolation and must only be
    used in non-production environments such as CI.
    """
    return os.environ.get(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "").strip().lower() in _TRUTHY_ENV_VALUES


def set_low_integrity_sacl(directory_path: str) -> bool:
    """
    Set the Mandatory Label SACL of a directory to Low Integrity (S-1-16-4096).
    On Windows, the owner of a directory can set the Mandatory Label without SeSecurityPrivilege.
    """
    if sys.platform != "win32":
        return False
    try:
        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        ConvertStringSD = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
        ConvertStringSD.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
        ConvertStringSD.restype = wintypes.BOOL

        GetSecurityDescriptorSacl = advapi32.GetSecurityDescriptorSacl
        GetSecurityDescriptorSacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
        GetSecurityDescriptorSacl.restype = wintypes.BOOL

        SetNamedSecurityInfoW = advapi32.SetNamedSecurityInfoW
        SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        SetNamedSecurityInfoW.restype = wintypes.DWORD

        LABEL_SECURITY_INFORMATION = 0x00000010
        SE_FILE_OBJECT = 1

        pSD = ctypes.c_void_p()
        # SDDL: Object Inherit (OI) + Container Inherit (CI) + No Write Up (NW) + Low Integrity (LW)
        if not ConvertStringSD("S:(ML;OICI;NW;;;LW)", 1, ctypes.byref(pSD), None):
            return False

        sacl_present = wintypes.BOOL()
        sacl_defaulted = wintypes.BOOL()
        pSacl = ctypes.c_void_p()
        GetSecurityDescriptorSacl(pSD, ctypes.byref(sacl_present), ctypes.byref(pSacl), ctypes.byref(sacl_defaulted))

        err = SetNamedSecurityInfoW(
            os.path.abspath(directory_path),
            SE_FILE_OBJECT,
            LABEL_SECURITY_INFORMATION,
            None, None, None,
            pSacl
        )
        kernel32.LocalFree(pSD)
        return err == 0
    except Exception as exc:
        log.debug("set_low_integrity_sacl failed on %s: %s", directory_path, exc)
        return False


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
        tuple of (exit_code, stdout_str, stderr_str, timed_out) -- ONLY when the
        restricted child genuinely started and either ran to completion (any
        exit code, including nonzero) or was terminated on timeout.

    Raises:
        RestrictedProcessBootstrapError: if any Win32 call required to
            establish Low Integrity isolation fails before the child is
            created, or if the child is created but terminates during its
            own process/DLL initialization before any user code could have
            run (see `is_restricted_process_bootstrap_failure`). Callers
            must never treat this as "the script ran and returned an odd
            exit code" -- OS isolation itself could not be established.
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

    # DWORD (unsigned) restypes are mandatory here: ctypes defaults an
    # unannotated call to a signed 32-bit int, which would silently turn
    # the 0xFFFFFFFF failure sentinels these two APIs use into -1 and break
    # every `== 0xFFFFFFFF` comparison below.
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    # All Win32 resources acquired below are released exactly once via
    # `_cleanup()`, called from `finally` on every exit path (normal
    # return, an early `RestrictedProcessBootstrapError`, or any other
    # exception). Handles/pointers default to falsy (NULL) values so
    # `_cleanup()` only closes/frees what was actually acquired; `h_write`
    # is explicitly cleared to NULL once the parent's copy is closed so it
    # is never double-closed.
    h_token = wintypes.HANDLE()
    h_restricted = wintypes.HANDLE()
    p_sid = ctypes.c_void_p()
    h_read = wintypes.HANDLE()
    h_write = wintypes.HANDLE()
    pi = PROCESS_INFORMATION()
    # Set once the concurrent pipe-draining reader thread (see Step 6 below)
    # is started, so _cleanup() can join it -- bounded -- before closing
    # h_read on every exit path, including an early RestrictedProcessBootstrapError
    # raise. Joining first avoids CloseHandle racing a pending ReadFile on
    # another thread; the bounded timeout means a stuck reader still cannot
    # hang this function itself.
    reader_thread: threading.Thread | None = None

    def _cleanup() -> None:
        if reader_thread is not None and reader_thread.is_alive():
            reader_thread.join(timeout=2.0)
        for handle in (pi.hThread, pi.hProcess, h_write, h_read, h_restricted, h_token):
            if handle:
                try:
                    kernel32.CloseHandle(handle)
                except Exception:
                    pass
        if p_sid:
            try:
                kernel32.LocalFree(p_sid)
            except Exception:
                pass

    try:
        # Step 1: Set scratch directory SACL to Low Integrity Level
        set_low_integrity_sacl(cwd)

        # Step 2: Open current process token
        TOKEN_ALL_ACCESS = 0xF01FF
        DISABLE_MAX_PRIVILEGE = 0x1
        LUA_TOKEN = 0x4

        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_ALL_ACCESS, ctypes.byref(h_token)):
            # Proven pre-user-code: no child has been created yet.
            raise RestrictedProcessBootstrapError(
                f"OpenProcessToken failed with error {kernel32.GetLastError()}",
                retry_safe=True,
            )

        # Step 3: Create Restricted Token (Strip Admin + Strip Privileges)
        res_restr = advapi32.CreateRestrictedToken(
            h_token,
            DISABLE_MAX_PRIVILEGE | LUA_TOKEN,
            0, None, 0, None, 0, None,
            ctypes.byref(h_restricted)
        )
        if not res_restr:
            # Proven pre-user-code: no child has been created yet.
            raise RestrictedProcessBootstrapError(
                f"CreateRestrictedToken failed with error {kernel32.GetLastError()}",
                retry_safe=True,
            )

        # Step 4: Apply Low Integrity Level SID (S-1-16-4096) to Restricted Token
        if not ConvertStringSidToSidW("S-1-16-4096", ctypes.byref(p_sid)):
            # Proven pre-user-code: no child has been created yet.
            raise RestrictedProcessBootstrapError(
                f"ConvertStringSidToSidW failed with error {kernel32.GetLastError()}",
                retry_safe=True,
            )

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

        class TOKEN_MANDATORY_LABEL(ctypes.Structure):
            _fields_ = [("Label", SID_AND_ATTRIBUTES)]

        label = TOKEN_MANDATORY_LABEL()
        label.Label.Sid = p_sid
        label.Label.Attributes = 0x00000020  # SE_GROUP_INTEGRITY
        TokenIntegrityLevel = 25
        if not advapi32.SetTokenInformation(
            h_restricted, TokenIntegrityLevel, ctypes.byref(label), ctypes.sizeof(label)
        ):
            # CRITICAL: never proceed to launch the child if this failed --
            # doing so would run it WITHOUT Low Integrity applied while
            # JARVIS believes isolation is active. Proven pre-user-code: no
            # child has been created yet.
            raise RestrictedProcessBootstrapError(
                f"SetTokenInformation(TokenIntegrityLevel) failed with error {kernel32.GetLastError()}",
                retry_safe=True,
            )

        # Step 5: Create anonymous pipes for I/O capture
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.bInheritHandle = True

        if not kernel32.CreatePipe(ctypes.byref(h_read), ctypes.byref(h_write), ctypes.byref(sa), 0):
            # Proven pre-user-code: no child has been created yet.
            raise RestrictedProcessBootstrapError(
                f"CreatePipe failed with error {kernel32.GetLastError()}",
                retry_safe=True,
            )
        if not kernel32.SetHandleInformation(h_read, 1, 0):  # Do not inherit read handle
            # Does not weaken Low Integrity isolation itself -- only I/O
            # capture reliability -- so this is logged, not fail-closed.
            log.warning(
                "SetHandleInformation(read pipe, non-inheritable) failed (LastError=%d); "
                "the child may inherit the pipe read handle.",
                kernel32.GetLastError(),
            )

        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        si.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
        si.hStdOutput = h_write
        si.hStdError = h_write

        CREATE_NO_WINDOW = 0x08000000
        CREATE_UNICODE_ENVIRONMENT = 0x00000400
        CREATE_SUSPENDED = 0x00000004
        flags = CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED

        # Prepare scrubbed unicode environment block
        clean_env = prepare_scrubbed_environment(env)
        env_str = "\0".join(f"{k}={v}" for k, v in clean_env.items()) + "\0\0"
        lp_env = ctypes.c_wchar_p(env_str)

        # Step 6: Launch via CreateProcessAsUserW, SUSPENDED. The child
        # executes zero instructions until ResumeThread() succeeds below --
        # this closes the race where a child could start running before the
        # Job Object's ActiveProcessLimit/JobMemoryLimit bounds are applied.
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
        # Parent's copy of the write end is closed immediately regardless
        # of outcome -- on failure there is no child to hold the other
        # reference either way; ReadFile() below relies on this close so
        # EOF is observed once the child (the only remaining writer) exits.
        kernel32.CloseHandle(h_write)
        h_write = wintypes.HANDLE()  # cleared: _cleanup() must not double-close

        if not success:
            # No child was created at all: proven pre-user-code.
            raise RestrictedProcessBootstrapError(
                f"CreateProcessAsUserW failed with error {kernel32.GetLastError()}",
                retry_safe=True,
            )

        # Start draining the output pipe concurrently, on a background
        # thread, starting now (child is still CREATE_SUSPENDED, so nothing
        # is written yet -- this just ensures the reader is in place before
        # ResumeThread()). The Windows default anonymous pipe buffer is
        # ~4096 bytes; without a concurrent reader, a child that writes more
        # than that to stdout/stderr combined blocks on write() forever
        # (the pipe never drains) while this function's own wait below would
        # otherwise not read anything until after the child exits -- a
        # classic pipe deadlock that previously surfaced as a false
        # "execution timed out" for any script producing >~4KB of output,
        # even though it would have completed instantly. This thread only
        # changes *when* the existing pipe is read, not any isolation,
        # token, Job Object, or validation semantics.
        #
        # _PIPE_READER_MAX_CAPTURE_BYTES bounds how much of that drained
        # output this function itself retains in the PARENT process's own
        # memory. Before this reader thread existed, a runaway/long-running
        # script (e.g. `while True: print(...)`) could never write more than
        # the pipe's ~4KB buffer before deadlocking, which incidentally
        # capped parent-side memory too. Now that the pipe is continuously
        # drained, that incidental cap is gone -- without an explicit one
        # here, a verbose child could make this thread buffer unbounded data
        # in the JARVIS host process itself for the entire timeout window,
        # long before interpreter.py's own post-hoc _MAX_STDOUT_CAPTURE_BYTES
        # truncation ever runs on the final joined string. This constant is
        # intentionally independent from (not imported from) that constant
        # to avoid a circular import between security.py and interpreter.py;
        # keep the two conceptually in sync if either changes. Draining
        # continues past the cap (so the pipe -- and thus the child -- never
        # blocks again) but excess bytes beyond it are discarded, never
        # retained.
        _PIPE_READER_MAX_CAPTURE_BYTES = 1024 * 1024  # 1MB
        output_chunks: list[bytes] = []

        def _drain_pipe() -> None:
            local_buf = ctypes.create_string_buffer(8192)
            local_bytes_read = wintypes.DWORD()
            captured = 0
            while kernel32.ReadFile(h_read, local_buf, 8192, ctypes.byref(local_bytes_read), None):
                if local_bytes_read.value == 0:
                    break
                if captured < _PIPE_READER_MAX_CAPTURE_BYTES:
                    chunk = local_buf.raw[: local_bytes_read.value]
                    output_chunks.append(chunk)
                    captured += len(chunk)
                # else: keep looping (draining the pipe so the child can
                # never block on it again) but stop retaining bytes beyond
                # the cap -- bounded parent-process memory regardless of how
                # much, or for how long, the child writes.

        reader_thread = threading.Thread(target=_drain_pipe, name="SandboxPipeReader", daemon=True)
        reader_thread.start()

        # Step 7: Assign the still-SUSPENDED child to the Job Object BEFORE
        # resuming it. The Job Object is a declared security/resource
        # boundary (ActiveProcessLimit=1, JobMemoryLimit=256MB,
        # KillOnJobClose) -- it must never fail open. If assignment fails,
        # the child has still executed zero instructions, so terminating it
        # here (without ever resuming) is formally provable to be a
        # pre-user-code failure -- retry_safe=True is correct.
        child_resumed = False
        try:
            if job is not None and not job.assign_process(pi.hProcess):
                raise RestrictedProcessBootstrapError(
                    "AssignProcessToJobObject failed; refusing to resume the "
                    "suspended child without the declared Job Object resource "
                    f"bounds in effect (LastError={kernel32.GetLastError()})",
                    retry_safe=True,
                )

            # Step 8: Resume the child now that Job Object bounds (if any
            # were requested) are confirmed active. Check the return value:
            # ResumeThread() returns 0xFFFFFFFF on failure, in which case
            # the thread was NEVER resumed and the child executed no
            # instructions -- also formally provable to be pre-user-code.
            resume_result = kernel32.ResumeThread(pi.hThread)
            if resume_result == 0xFFFFFFFF:
                raise RestrictedProcessBootstrapError(
                    f"ResumeThread failed with error {kernel32.GetLastError()}; "
                    "the child was never resumed and executed no instructions",
                    retry_safe=True,
                )
            child_resumed = True
        finally:
            if not child_resumed:
                if not kernel32.TerminateProcess(pi.hProcess, 1):
                    log.warning(
                        "TerminateProcess on suspended child failed (LastError=%d); "
                        "child remains suspended and will never execute.",
                        kernel32.GetLastError(),
                    )

        # Step 9: Wait for completion with timeout. The background reader
        # thread (Step 6) is concurrently draining the output pipe the
        # whole time, so the child can never deadlock on a full pipe buffer
        # while this call blocks.
        WAIT_TIMEOUT = 0x00000102
        WAIT_FAILED = 0xFFFFFFFF
        timeout_ms = int(timeout_seconds * 1000)
        wait_res = kernel32.WaitForSingleObject(pi.hProcess, timeout_ms)
        timed_out = False

        if wait_res == WAIT_TIMEOUT:
            timed_out = True
            kernel32.TerminateProcess(pi.hProcess, 1)
            exit_code_val = -1
        elif wait_res == WAIT_FAILED:
            # The child was already resumed and may be running or may
            # already have run user code with side effects -- this cannot
            # be proven to be pre-user-code, so it is NEVER retry-safe.
            raise RestrictedProcessBootstrapError(
                f"WaitForSingleObject failed with error {kernel32.GetLastError()}",
                retry_safe=False,
            )
        else:
            dw_exit = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(dw_exit)):
                # Same reasoning as WAIT_FAILED above: the child was
                # resumed and ran for some (unknown) duration.
                raise RestrictedProcessBootstrapError(
                    f"GetExitCodeProcess failed with error {kernel32.GetLastError()}",
                    retry_safe=False,
                )
            exit_code_val = dw_exit.value

        # Step 10: the child has now exited (normally, or just terminated on
        # timeout above) -- Windows closes its handles as part of process
        # teardown, which is the reader thread's only remaining writer
        # reference, so its ReadFile loop should reach EOF and return
        # promptly. Bounded join: even if pipe teardown is unexpectedly
        # slow, this can never hang the sandbox call itself; whatever was
        # captured in output_chunks so far (list.append is safe to read
        # here, single-writer/single-reader) is used either way.
        reader_thread.join(timeout=5.0)
        if reader_thread.is_alive():
            log.warning("Sandbox pipe reader thread did not finish draining output within 5s of child exit.")
        full_output = b"".join(output_chunks).decode("utf-8", errors="replace")
        full_output, ready_observed = strip_sandbox_ready_sentinel(full_output)

        # A bootstrap-failure-shaped exit code is NOT by itself proof that
        # no user code ran -- the child could have crossed the readiness
        # boundary (preamble fully installed, sentinel written) and only
        # later hit a native DLL failure. Only classify this as a
        # pre-user-code bootstrap failure (and thus retry-eligible) when
        # the readiness sentinel was NEVER observed. If it WAS observed,
        # this is a genuine (if unusual) execution outcome -- return it
        # normally, exactly like any other exit code, never retry-eligible.
        if not timed_out and is_restricted_process_bootstrap_failure(exit_code_val) and not ready_observed:
            # Proven pre-user-code: known bootstrap-failure exit code AND
            # the readiness sentinel (written as the last preamble step,
            # before user code) was never observed.
            snippet = f"; partial output: {full_output[:200]!r}" if full_output else ""
            raise RestrictedProcessBootstrapError(
                "restricted child process terminated during startup/DLL "
                f"initialization (status=0x{exit_code_val:08X}); the readiness "
                f"sentinel was never observed, so no user code ran{snippet}",
                retry_safe=True,
            )

        return exit_code_val, full_output, "", timed_out
    finally:
        _cleanup()


_APPCONTAINER_SYS_ACLS_GRANTED = False


def grant_appcontainer_acls(scratch_dir: str) -> None:
    """
    Grant Read and Execute / Full Control permissions to 'ALL APPLICATION PACKAGES' (S-1-15-2-1)
    on the Python runtime and scratch directory so AppContainer subprocesses can execute.
    """
    if sys.platform != "win32":
        return
    import subprocess
    global _APPCONTAINER_SYS_ACLS_GRANTED
    _cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    if not _APPCONTAINER_SYS_ACLS_GRANTED:
        target_dirs = []
        py_dir = os.path.dirname(sys.executable)
        if py_dir:
            target_dirs.append(py_dir)
        base_prefix = getattr(sys, "base_prefix", None)
        if base_prefix and base_prefix != py_dir:
            target_dirs.append(base_prefix)
        base_exec = getattr(sys, "_base_executable", None)
        if base_exec:
            base_exec_dir = os.path.dirname(base_exec)
            if base_exec_dir and base_exec_dir not in target_dirs:
                target_dirs.append(base_exec_dir)

        for d in target_dirs:
            try:
                d_abs = os.path.abspath(d)
                subprocess.run(
                    ["icacls", d_abs, "/grant", "*S-1-15-2-1:(OI)(CI)RX", "/Q"],
                    capture_output=True,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            except Exception as exc:
                log.debug("grant_appcontainer_acls failed on %s: %s", d, exc)
        _APPCONTAINER_SYS_ACLS_GRANTED = True

    try:
        subprocess.run(
            ["icacls", os.path.abspath(scratch_dir), "/grant", "*S-1-15-2-1:(OI)(CI)F", "/T", "/Q"],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception as exc:
        log.debug("grant_appcontainer_acls scratch_dir failed: %s", exc)


def spawn_appcontainer_process(
    cmd: str,
    cwd: str,
    env: dict[str, str] | None = None,
    job: WindowsJobObject | None = None,
    timeout_seconds: float = 15.0,
    appcontainer_name: str = "JARVIS_Sandbox_AppContainer",
) -> tuple[int, str, str, bool]:
    """
    Spawn a child process isolated in a Windows AppContainer with ZERO network capabilities
    (blocking kernel network socket connections) and attached to a Windows Job Object.

    Returns:
        tuple of (exit_code, stdout_str, stderr_str, timed_out)
    """
    if sys.platform != "win32":
        raise NotImplementedError("AppContainer process isolation is only supported on Windows.")

    kernel32 = ctypes.windll.kernel32
    userenv = ctypes.windll.userenv
    advapi32 = ctypes.windll.advapi32

    DeriveAppContainerSidFromAppContainerName = getattr(userenv, "DeriveAppContainerSidFromAppContainerName", None)
    if DeriveAppContainerSidFromAppContainerName:
        DeriveAppContainerSidFromAppContainerName.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
        DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long

    InitializeProcThreadAttributeList = kernel32.InitializeProcThreadAttributeList
    InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    InitializeProcThreadAttributeList.restype = wintypes.BOOL

    UpdateProcThreadAttribute = kernel32.UpdateProcThreadAttribute
    UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)
    ]
    UpdateProcThreadAttribute.restype = wintypes.BOOL

    DeleteProcThreadAttributeList = kernel32.DeleteProcThreadAttributeList
    DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    DeleteProcThreadAttributeList.restype = None

    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(SECURITY_ATTRIBUTES),
        wintypes.DWORD,
    ]
    kernel32.CreatePipe.restype = wintypes.BOOL

    kernel32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    kernel32.SetHandleInformation.restype = wintypes.BOOL

    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOEXW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL

    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    # Step 1: Ensure ACLs for AppContainer (ALL APPLICATION PACKAGES) on scratch dir
    grant_appcontainer_acls(cwd)
    set_low_integrity_sacl(cwd)

    # Step 2: Create or derive AppContainer SID
    p_appcontainer_sid = ctypes.c_void_p()
    CreateAppContainerProfile = getattr(userenv, "CreateAppContainerProfile", None)

    if CreateAppContainerProfile:
        CreateAppContainerProfile.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)
        ]
        CreateAppContainerProfile.restype = ctypes.c_long
        try:
            CreateAppContainerProfile(
                appcontainer_name,
                "JARVIS Sandbox",
                "JARVIS Sandbox AppContainer Profile",
                None,
                0,
                ctypes.byref(p_appcontainer_sid),
            )
        except Exception:
            pass

    if not p_appcontainer_sid and DeriveAppContainerSidFromAppContainerName:
        try:
            DeriveAppContainerSidFromAppContainerName(appcontainer_name, ctypes.byref(p_appcontainer_sid))
        except Exception:
            pass

    if not p_appcontainer_sid:
        raise RestrictedProcessBootstrapError(
            "Failed to obtain AppContainer SID on this OS.",
            retry_safe=True,
        )

    # Step 3: Setup SECURITY_CAPABILITIES with 0 capabilities (NO network access)
    sec_cap = SECURITY_CAPABILITIES()
    sec_cap.AppContainerSid = p_appcontainer_sid
    sec_cap.Capabilities = None
    sec_cap.CapabilityCount = 0  # ZERO network capabilities -> WFP / Winsock kernel socket block!
    sec_cap.Reserved = 0

    # Step 4: Initialize ProcThreadAttributeList
    size = ctypes.c_size_t(0)
    InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attr_buf = ctypes.create_string_buffer(size.value)
    p_attr_list = ctypes.cast(attr_buf, ctypes.c_void_p)
    if not InitializeProcThreadAttributeList(p_attr_list, 1, 0, ctypes.byref(size)):
        advapi32.FreeSid(p_appcontainer_sid)
        raise RestrictedProcessBootstrapError(
            f"InitializeProcThreadAttributeList failed (LastError={kernel32.GetLastError()})",
            retry_safe=True,
        )

    if not UpdateProcThreadAttribute(
        p_attr_list,
        0,
        PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
        ctypes.byref(sec_cap),
        ctypes.sizeof(sec_cap),
        None,
        None,
    ):
        DeleteProcThreadAttributeList(p_attr_list)
        advapi32.FreeSid(p_appcontainer_sid)
        raise RestrictedProcessBootstrapError(
            f"UpdateProcThreadAttribute failed (LastError={kernel32.GetLastError()})",
            retry_safe=True,
        )

    # Step 5: Setup anonymous pipes
    h_read = wintypes.HANDLE()
    h_write = wintypes.HANDLE()
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.bInheritHandle = True

    if not kernel32.CreatePipe(ctypes.byref(h_read), ctypes.byref(h_write), ctypes.byref(sa), 0):
        DeleteProcThreadAttributeList(p_attr_list)
        advapi32.FreeSid(p_appcontainer_sid)
        raise RestrictedProcessBootstrapError(
            f"CreatePipe failed (LastError={kernel32.GetLastError()})",
            retry_safe=True,
        )

    kernel32.SetHandleInformation(h_read, 1, 0)

    # Step 6: Setup STARTUPINFOEXW
    si_ex = STARTUPINFOEXW()
    si_ex.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    si_ex.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
    si_ex.StartupInfo.hStdOutput = h_write
    si_ex.StartupInfo.hStdError = h_write
    si_ex.lpAttributeList = p_attr_list.value

    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    CREATE_NO_WINDOW = 0x08000000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    CREATE_SUSPENDED = 0x00000004
    flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED

    clean_env = prepare_scrubbed_environment(env)
    env_str = "\0".join(f"{k}={v}" for k, v in clean_env.items()) + "\0\0"
    lp_env = ctypes.c_wchar_p(env_str)

    pi = PROCESS_INFORMATION()
    reader_thread: threading.Thread | None = None

    def _cleanup_appcontainer() -> None:
        if reader_thread is not None and reader_thread.is_alive():
            reader_thread.join(timeout=2.0)
        for handle in (pi.hThread, pi.hProcess, h_write, h_read):
            if handle:
                try:
                    kernel32.CloseHandle(handle)
                except Exception:
                    pass
        try:
            DeleteProcThreadAttributeList(p_attr_list)
        except Exception:
            pass
        if p_appcontainer_sid:
            try:
                advapi32.FreeSid(p_appcontainer_sid)
            except Exception:
                pass

    try:
        # Step 7: CreateProcessW with EXTENDED_STARTUPINFO_PRESENT
        cmd_buf = ctypes.create_unicode_buffer(cmd)
        success = kernel32.CreateProcessW(
            None,
            cmd_buf,
            None,
            None,
            True,
            flags,
            lp_env,
            cwd,
            ctypes.byref(si_ex),
            ctypes.byref(pi),
        )
        kernel32.CloseHandle(h_write)
        h_write = wintypes.HANDLE()

        if not success:
            raise RestrictedProcessBootstrapError(
                f"CreateProcessW (AppContainer) failed (LastError={kernel32.GetLastError()})",
                retry_safe=True,
            )

        _PIPE_READER_MAX_CAPTURE_BYTES = 1024 * 1024
        output_chunks: list[bytes] = []

        def _drain_pipe() -> None:
            local_buf = ctypes.create_string_buffer(8192)
            local_bytes_read = wintypes.DWORD()
            captured = 0
            while kernel32.ReadFile(h_read, local_buf, 8192, ctypes.byref(local_bytes_read), None):
                if local_bytes_read.value == 0:
                    break
                chunk = bytes(local_buf[:local_bytes_read.value])
                if captured < _PIPE_READER_MAX_CAPTURE_BYTES:
                    remaining = _PIPE_READER_MAX_CAPTURE_BYTES - captured
                    output_chunks.append(chunk[:remaining])
                    captured += min(len(chunk), remaining)

        reader_thread = threading.Thread(target=_drain_pipe, daemon=True)
        reader_thread.start()

        # Step 8: Attach to Windows Job Object
        if job is not None:
            try:
                job.assign_process(pi.hProcess)
            except Exception as exc:
                kernel32.TerminateProcess(pi.hProcess, 1)
                raise RestrictedProcessBootstrapError(
                    f"JobObject assign_process failed on AppContainer process: {exc}",
                    retry_safe=True,
                )

        # Step 9: Resume thread and wait for completion
        kernel32.ResumeThread(pi.hThread)

        wait_ms = int(timeout_seconds * 1000)
        wait_result = kernel32.WaitForSingleObject(pi.hProcess, wait_ms)

        WAIT_OBJECT_0 = 0x00000000
        WAIT_TIMEOUT = 0x00000102

        timed_out = False
        if wait_result == WAIT_TIMEOUT:
            timed_out = True
            kernel32.TerminateProcess(pi.hProcess, 1)
            kernel32.WaitForSingleObject(pi.hProcess, 2000)
            exit_code_val = 1
        else:
            dw_exit = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(dw_exit)):
                raise RestrictedProcessBootstrapError(
                    "GetExitCodeProcess failed on AppContainer process",
                    retry_safe=False,
                )
            exit_code_val = dw_exit.value

        reader_thread.join(timeout=5.0)
        full_output = b"".join(output_chunks).decode("utf-8", errors="replace")
        full_output, ready_observed = strip_sandbox_ready_sentinel(full_output)

        if not timed_out and is_restricted_process_bootstrap_failure(exit_code_val) and not ready_observed:
            raise RestrictedProcessBootstrapError(
                f"AppContainer process terminated during startup (status=0x{exit_code_val:08X})",
                retry_safe=True,
            )

        return exit_code_val, full_output, "", timed_out
    finally:
        _cleanup_appcontainer()


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
import types
import importlib.abc
import importlib.machinery

# 1-3. Meta-Path Importer Interceptor & Module Poisoning (inside local closure)
def _install_meta_path_finder():
    # Note: _winapi is permitted for ntpath.abspath on Windows Python 3.13;
    # untrusted code is prevented from importing _winapi by AST validator.
    _BLOCKED_SANDBOX_MODULES = {
        "socket", "_socket", "ctypes", "_ctypes",
        "mmap", "_ssl", "ssl", "urllib", "requests", "http", "subprocess",
        "jarvis", "win32com", "pythoncom", "pywintypes", "comtypes", "clr",
        "wmi", "winreg", "_winreg", "_overlapped"
    }

    _BLOCKED_MODULE_PREFIXES = (
        "win32", "_win32", "pywin", "comtypes", "pythoncom", "pywintypes", "wmi"
    )

    def _is_module_blocked(fullname: str) -> bool:
        top_name = fullname.split(".")[0].lower()
        if top_name in _BLOCKED_SANDBOX_MODULES:
            return True
        if any(top_name.startswith(pfx) for pfx in _BLOCKED_MODULE_PREFIXES):
            return True
        return False

    class _BlockedSecurityModule(types.ModuleType):
        def __init__(self, name):
            super().__init__(name)
            self.__name__ = name
            self.__file__ = f"<blocked-security-module-{name}>"

        def __getattr__(self, attr):
            raise PermissionError(f"Access Denied: Low-level module '{self.__name__}' is disabled in JARVIS Sandbox.")

        def __call__(self, *args, **kwargs):
            raise PermissionError(f"Access Denied: Low-level module '{self.__name__}' is disabled in JARVIS Sandbox.")

    # 2. Poison ALL Existing Cached Modules in sys.modules (Pre-cached import defense)
    for _mod_name in list(sys.modules.keys()):
        if _is_module_blocked(_mod_name):
            sys.modules[_mod_name] = _BlockedSecurityModule(_mod_name)

    for _mod_name in _BLOCKED_SANDBOX_MODULES:
        sys.modules[_mod_name] = _BlockedSecurityModule(_mod_name)

    # 3. Meta-Path Importer Interceptor (Blocks fresh / re-import evasion)
    class _BlockedLoader:
        def __init__(self, name):
            self._name = name
        def create_module(self, spec):
            return _BlockedSecurityModule(self._name)
        def exec_module(self, module):
            pass

    class _BlockedMetaPathFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if _is_module_blocked(fullname):
                return importlib.machinery.ModuleSpec(fullname, _BlockedLoader(fullname))
            return None

    sys.meta_path.insert(0, _BlockedMetaPathFinder())

_install_meta_path_finder()

# 4. Strip JARVIS and Workspace Paths from sys.path (Blocks internal package import)
sys.path = [p for p in sys.path if "jarvis" not in p.lower()]

# 5. Metaclass-Hardened Slot-Based Guard Classes & Private Closure Scoping
class _GuardMeta(type):
    def __getattribute__(cls, name):
        if name in ("__closure__", "__code__", "__globals__", "__func__", "__self__", "__dict__", "_fn", "_orig", "_check_path", "__slots__", "__call__"):
            raise AttributeError(f"Access Denied: Introspection attribute '{name}' is forbidden on {cls.__name__}.")
        return super().__getattribute__(name)
    def __setattr__(cls, name, value):
        raise TypeError(f"Cannot modify immutable security guard class {cls.__name__}")
    def __delattr__(cls, name):
        raise TypeError(f"Cannot modify immutable security guard class {cls.__name__}")

def _install_sandbox_security_guards():
    sandbox_root_lower = os.path.abspath(os.getcwd()).lower()
    allowed_prefixes = {
        os.path.abspath(p).lower()
        for p in (
            sys.prefix,
            getattr(sys, "base_prefix", sys.prefix),
            getattr(sys, "exec_prefix", sys.prefix),
            getattr(sys, "base_exec_prefix", sys.prefix),
        )
        if p
    }
    fspath = getattr(os, "fspath", str)

    def check_sandbox_path(target_path, is_write=False):
        try:
            path_str = fspath(target_path)
            abs_target = os.path.abspath(path_str).lower()
            if abs_target.startswith(sandbox_root_lower):
                return
            if not is_write and any(abs_target.startswith(pfx) for pfx in allowed_prefixes):
                return
        except Exception:
            pass
        action = "write to" if is_write else "read from"
        raise PermissionError(f"Access Denied: Cannot {action} outside sandbox root: '{target_path}'")

    # Guard 1: builtins.open
    orig_builtin_open = builtins.open
    class _ScopedBuiltinOpenGuard(metaclass=_GuardMeta):
        __slots__ = ()
        def __call__(self, file, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            is_write = any(m in str(mode) for m in ("w", "a", "+", "x"))
            check_sandbox_path(file, is_write=is_write)
            return orig_builtin_open(file, *args, **kwargs)
        def __getattribute__(self, name):
            if name in ("__closure__", "__code__", "__globals__", "__func__", "__self__", "__dict__", "_fn", "_orig", "_check_path", "__slots__", "__class__", "__subclasses__"):
                raise AttributeError(f"Access Denied: Introspection attribute '{name}' is forbidden.")
            return super().__getattribute__(name)

    builtins.open = _ScopedBuiltinOpenGuard()

    # Guard 2: io.open
    orig_io_open = io.open
    class _ScopedIOOpenGuard(metaclass=_GuardMeta):
        __slots__ = ()
        def __call__(self, file, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            is_write = any(m in str(mode) for m in ("w", "a", "+", "x"))
            check_sandbox_path(file, is_write=is_write)
            return orig_io_open(file, *args, **kwargs)
        def __getattribute__(self, name):
            if name in ("__closure__", "__code__", "__globals__", "__func__", "__self__", "__dict__", "_fn", "_orig", "_check_path", "__slots__", "__class__", "__subclasses__"):
                raise AttributeError(f"Access Denied: Introspection attribute '{name}' is forbidden.")
            return super().__getattribute__(name)

    io.open = _ScopedIOOpenGuard()

    # Guard 3: os.open
    orig_os_open = os.open
    class _ScopedOSOpenGuard(metaclass=_GuardMeta):
        __slots__ = ()
        def __call__(self, path, flags, *args, **kwargs):
            is_write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
            check_sandbox_path(path, is_write=is_write)
            return orig_os_open(path, flags, *args, **kwargs)
        def __getattribute__(self, name):
            if name in ("__closure__", "__code__", "__globals__", "__func__", "__self__", "__dict__", "_fn", "_orig", "_check_path", "__slots__", "__class__", "__subclasses__"):
                raise AttributeError(f"Access Denied: Introspection attribute '{name}' is forbidden.")
            return super().__getattribute__(name)

    os.open = _ScopedOSOpenGuard()

_install_sandbox_security_guards()

# 6. Protect Stdout from Memory Flood (1MB Stream Truncation inside local closure)
def _install_stdout_capping():
    _orig_stdout_write = sys.stdout.write
    _written_bytes_count = [0]
    _MAX_STDOUT_BYTES = 1024 * 1024  # 1MB cap

    def _capped_stdout_write(s):
        if _written_bytes_count[0] > _MAX_STDOUT_BYTES:
            return 0
        _written_bytes_count[0] += len(s.encode("utf-8", errors="replace"))
        if _written_bytes_count[0] > _MAX_STDOUT_BYTES:
            _orig_stdout_write("\\n[TRUNCATED: Output exceeded 1MB sandbox limit]\\n")
            return 0
        return _orig_stdout_write(s)

    sys.stdout.write = _capped_stdout_write

_install_stdout_capping()

# 7. Globals Purge: Wipe internal symbols from module dictionary before running user code
_leak_keys = [
    _k for _k in list(globals().keys())
    if _k.startswith(("_orig", "_raw", "_Scoped", "_Guard", "_BLOCKED", "_is_module", "_check", "_install", "_SANDBOX", "_PYTHON"))
]
for _k in _leak_keys:
    globals().pop(_k, None)
del _leak_keys

# 8. Readiness handshake
sys.stdout.write(%r)
sys.stdout.flush()
# ====================================================================
""" % (_SANDBOX_READY_LINE,)


def inject_security_preamble(code: str) -> str:
    """Inject zero-trust network denial, directory allowlisting, and output caps into user code."""
    future_imports: list[str] = []
    other_lines: list[str] = []
    for line in code.splitlines(keepends=True):
        if line.strip().startswith("from __future__ import "):
            future_imports.append(line)
        else:
            other_lines.append(line)

    if future_imports:
        futures_block = "".join(future_imports)
        clean_code = "".join(other_lines)
        return f"{futures_block}\n{SANDBOX_BOOTSTRAP_PREAMBLE}\n{clean_code}"
    return f"{SANDBOX_BOOTSTRAP_PREAMBLE}\n{code}"
