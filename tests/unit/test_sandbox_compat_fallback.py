"""
tests/unit/test_sandbox_compat_fallback.py
===========================================
Deterministic, mocked regression tests for the sandbox's restricted-token
bootstrap-failure classification and compatibility-fallback policy
(jarvis/sandbox/security.py + jarvis/sandbox/interpreter.py).

Background: on GitHub-hosted Windows Server 2025 CI runners,
CreateProcessAsUserW reports success but the child process terminates
during its own startup/DLL initialization with STATUS_DLL_INIT_FAILED
(0xC0000142) before any user code can run. The prior implementation set
`spawned_via_token = True` merely because the Win32 launcher call
returned, so this was misreported as "the restricted backend executed the
script and returned exit code 3221225794" instead of "OS isolation could
not be established." This file proves the corrected state machine:
production defaults to fail-closed, and a reduced-isolation compatibility
fallback is only ever used with an explicit opt-in
(JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1).

No real admin token or real OS privilege is required for the state-machine
tests: `spawn_low_integrity_process()` is mocked directly at the
interpreter's import site. The one exception (`TestSetTokenInformationFailure`)
mocks every Win32 call it touches and requires only that `ctypes.windll`
exist (Windows), never real token privilege.
"""
from __future__ import annotations

import contextlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from jarvis.sandbox.interpreter import CodeInterpreterSandbox
from jarvis.sandbox.security import (
    _SANDBOX_READY_LINE,
    _SANDBOX_READY_SENTINEL,
    SANDBOX_COMPAT_FALLBACK_ENV_VAR,
    STATUS_DLL_INIT_FAILED,
    RestrictedProcessBootstrapError,
    WindowsJobObject,
    is_compat_fallback_enabled,
    is_restricted_process_bootstrap_failure,
    strip_sandbox_ready_sentinel,
)


@pytest.fixture
def sandbox(tmp_path):
    return CodeInterpreterSandbox(base_scratch_dir=tmp_path / "scratch", default_timeout=5.0)


def _fake_compat_process(stdout: str = "compat ran\n", returncode: int = 0) -> MagicMock:
    """A minimal double for subprocess.Popen sufficient for the legacy compat path."""
    proc = MagicMock()
    proc.pid = 4242
    proc.communicate.return_value = (stdout, "")
    proc.returncode = returncode
    return proc


@contextlib.contextmanager
def _patched_job_assignment_success():
    """
    Patch both OpenProcess() and WindowsJobObject.assign_process() to
    succeed. `_fake_compat_process()` uses a fake, non-real PID, so the
    real OpenProcess()/AssignProcessToJobObject() call chain would
    otherwise genuinely fail on it (correctly triggering the Blocker-3
    fail-closed path) in every test that isn't specifically about that
    behavior -- see TestCompatPopenJobObjectFailClosed for the dedicated
    test that exercises the real failure path.
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32
    with (
        patch.object(kernel32, "OpenProcess", return_value=99999),
        patch.object(WindowsJobObject, "assign_process", return_value=True),
    ):
        yield


# ============================================================================
# Bootstrap-failure exit-code classification (jarvis.sandbox.security)
# ============================================================================

class TestBootstrapFailureClassification:
    def test_recognizes_status_dll_init_failed(self):
        assert is_restricted_process_bootstrap_failure(STATUS_DLL_INIT_FAILED) is True
        # Exact decimal value observed on GitHub-hosted Windows CI.
        assert is_restricted_process_bootstrap_failure(3221225794) is True

    def test_does_not_confuse_normal_exit_codes_timeouts_or_signed_values(self):
        assert is_restricted_process_bootstrap_failure(0) is False
        assert is_restricted_process_bootstrap_failure(1) is False
        assert is_restricted_process_bootstrap_failure(7) is False
        assert is_restricted_process_bootstrap_failure(-1) is False
        assert is_restricted_process_bootstrap_failure(255) is False


class TestRetrySafeDefaultsToFalse:
    """
    SECURITY RULE: unknown state => never retry. retry_safe must default to
    False; True is only ever correct where a call site holds formal proof
    the child executed zero instructions, and must be passed explicitly.
    """

    def test_default_construction_is_not_retry_safe(self):
        assert RestrictedProcessBootstrapError("unspecified failure").retry_safe is False

    def test_explicit_retry_safe_false_is_not_retry_safe(self):
        assert RestrictedProcessBootstrapError("msg", retry_safe=False).retry_safe is False

    def test_explicit_retry_safe_true_is_retry_safe(self):
        assert RestrictedProcessBootstrapError("msg", retry_safe=True).retry_safe is True

    def test_default_constructed_error_never_falls_back_even_when_compat_enabled(self, sandbox, monkeypatch):
        """
        A RestrictedProcessBootstrapError raised WITHOUT an explicit
        retry_safe kwarg (i.e. an unclassified/new failure mode that hasn't
        been formally proven pre-user-code) must fail closed, never
        activate the compatibility fallback -- even with
        JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1 set.
        """
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError("unspecified/new failure mode"),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('should never run')")

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == -1
        assert result.stdout == ""

    def test_only_explicit_retry_safe_true_activates_compat_fallback(self, sandbox, monkeypatch):
        """Direct contrast: retry_safe=False (or unspecified) never activates compat; only True does."""
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError("no explicit retry_safe"),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result_unspecified = sandbox.execute_python("print('a')")
        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result_unspecified.success is False

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError("proven pre-user-code", retry_safe=True),
            ) as mock_spawn2,
            patch(
                "jarvis.sandbox.interpreter.subprocess.Popen",
                return_value=_fake_compat_process(),
            ) as mock_popen2,
            _patched_job_assignment_success(),
        ):
            result_explicit_true = sandbox.execute_python("print('b')")
        mock_spawn2.assert_called_once()
        mock_popen2.assert_called_once()
        assert result_explicit_true.success is True


class TestCompatFallbackEnvVarParsing:
    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "on"])
    def test_truthy_values_enable_compat_fallback(self, monkeypatch, value):
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, value)
        assert is_compat_fallback_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "", "no", "off", "garbage"])
    def test_non_truthy_values_disable_compat_fallback(self, monkeypatch, value):
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, value)
        assert is_compat_fallback_enabled() is False

    def test_unset_defaults_to_disabled(self, monkeypatch):
        monkeypatch.delenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, raising=False)
        assert is_compat_fallback_enabled() is False


# ============================================================================
# A/E. Fail-closed default: restricted backend bootstrap failure, no opt-in
# ============================================================================

class TestFailClosedDefault:
    def test_bootstrap_failure_fails_closed_by_default(self, sandbox, monkeypatch):
        """A. STATUS_DLL_INIT_FAILED + compat fallback disabled => fail closed, legacy Popen NOT called."""
        monkeypatch.delenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, raising=False)

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError(
                    "restricted child process terminated during startup/DLL initialization "
                    f"(status=0x{STATUS_DLL_INIT_FAILED:08X})"
                ),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('should never run')")

        assert mock_spawn.called
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == -1
        assert result.stdout == ""
        assert "isolation" in (result.error or "").lower()
        # No secrets/internal details leaked into the refusal message.
        assert "GOOGLE_API_KEY" not in (result.error or "")

    def test_unexpected_launcher_exception_also_fails_closed_by_default(self, sandbox, monkeypatch):
        """E. A non-RestrictedProcessBootstrapError launcher failure is treated identically."""
        monkeypatch.delenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, raising=False)

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RuntimeError("simulated unexpected ctypes failure"),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('should never run')")

        assert mock_spawn.called
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == -1


# ============================================================================
# B/E. Explicit opt-in compatibility fallback
# ============================================================================

class TestCompatFallbackExplicitOptIn:
    def test_bootstrap_failure_falls_back_when_explicitly_enabled(self, sandbox, monkeypatch):
        """
        B. STATUS_DLL_INIT_FAILED, CONFIRMED pre-user-code (retry_safe=True,
        the readiness sentinel was never observed) + compat fallback
        explicitly enabled => legacy Job-Object path used.
        """
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError(
                    f"status=0x{STATUS_DLL_INIT_FAILED:08X}; readiness sentinel never observed",
                    retry_safe=True,
                ),
            ),
            patch(
                "jarvis.sandbox.interpreter.subprocess.Popen",
                return_value=_fake_compat_process(),
            ) as mock_popen,
            _patched_job_assignment_success(),
        ):
            result = sandbox.execute_python("print('compat ran')")

        mock_popen.assert_called_once()
        assert result.success is True
        assert result.exit_code == 0
        assert "compat ran" in result.stdout

    def test_unexpected_launcher_exception_never_falls_back_even_when_enabled(self, sandbox, monkeypatch):
        """
        E (corrected). An unclassified/generic launcher exception is NOT
        formally proven to have occurred before user code could run (it
        could have happened after the child was resumed, possibly after
        side effects). It must NEVER trigger the compatibility fallback,
        even when JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1 is set.
        """
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RuntimeError("simulated unexpected ctypes failure"),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('should never run')")

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == -1
        assert result.stdout == ""


# ============================================================================
# C. Genuine execution with a normal nonzero exit code: NO compat retry
# ============================================================================

class TestNormalExecutionOutcomesAreNeverRetried:
    def test_normal_nonzero_exit_code_is_not_retried(self, sandbox, monkeypatch):
        """C. Restricted backend genuinely ran the script; its own nonzero exit is final."""
        monkeypatch.delenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, raising=False)

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                return_value=(7, "partial output", "", False),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("import sys; sys.exit(7)")

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == 7
        assert result.stdout == "partial output"

    def test_normal_nonzero_exit_code_is_not_retried_even_with_compat_enabled(self, sandbox, monkeypatch):
        """C (continued). A genuine execution outcome is final even when the opt-in flag is set."""
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                return_value=(7, "partial output", "", False),
            ),
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("import sys; sys.exit(7)")

        mock_popen.assert_not_called()
        assert result.exit_code == 7

    def test_timeout_is_not_retried_and_keeps_timeout_semantics(self, sandbox, monkeypatch):
        """D. Restricted backend timeout is final -- NO compat retry, -1/timed_out semantics preserved."""
        monkeypatch.delenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, raising=False)

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                return_value=(-1, "", "", True),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("while True: pass", timeout_seconds=1.0)

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in (result.error or "").lower()


# ============================================================================
# F/G. Environment scrubbing remains intact in the compatibility path
# ============================================================================

class TestEnvironmentScrubbingInCompatFallback:
    def test_no_secrets_leak_into_compat_fallback_environment(self, sandbox, monkeypatch):
        """F/G. The compat fallback reuses the same scrubbed env; no secrets, still functional."""
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")
        monkeypatch.setenv("GOOGLE_API_KEY", "super_secret_should_not_leak")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "also_super_secret")

        captured_env: dict[str, str] = {}

        def _fake_popen(cmd_list, cwd, env, **kwargs):
            captured_env.update(env)
            return _fake_compat_process()

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError("simulated", retry_safe=True),
            ),
            patch("jarvis.sandbox.interpreter.subprocess.Popen", side_effect=_fake_popen),
            _patched_job_assignment_success(),
        ):
            result = sandbox.execute_python("print('compat ran')")

        assert result.success is True
        assert "GOOGLE_API_KEY" not in captured_env
        assert "TELEGRAM_BOT_TOKEN" not in captured_env
        # Scrubbing removes secrets, not the whole environment.
        assert "PYTHONPATH" in captured_env


# ============================================================================
# Blocker 2: a generic/unclassified failure is NEVER retry-eligible, even
# when RestrictedProcessBootstrapError itself is raised with
# retry_safe=False (e.g. WaitForSingleObject/GetExitCodeProcess failing
# AFTER the child was resumed -- not formally provable as pre-user-code).
# ============================================================================

class TestRetrySafeFalseNeverRetries:
    def test_retry_unsafe_bootstrap_error_never_falls_back_even_when_enabled(self, sandbox, monkeypatch):
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError(
                    "WaitForSingleObject failed with error 6; the child was already resumed",
                    retry_safe=False,
                ),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('should never run')")

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == -1
        assert result.stdout == ""

    def test_retry_unsafe_bootstrap_error_fails_closed_by_default_too(self, sandbox, monkeypatch):
        monkeypatch.delenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, raising=False)

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError(
                    "GetExitCodeProcess failed with error 6", retry_safe=False
                ),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('should never run')")

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False


# ============================================================================
# Blocker 1: the readiness sentinel is the real retry-safety boundary --
# an NTSTATUS-shaped exit code alone is NOT proof that no user code ran.
# ============================================================================

class TestReadySentinelStripping:
    """Pure-function tests for strip_sandbox_ready_sentinel() -- no Win32 involved."""

    def test_sentinel_absent_returns_unchanged_output_and_false(self):
        output, observed = strip_sandbox_ready_sentinel("hello world\n")
        assert output == "hello world\n"
        assert observed is False

    def test_sentinel_present_is_stripped_and_reports_true(self):
        raw = f"some preamble noise\n{_SANDBOX_READY_LINE}user output here\n"
        cleaned, observed = strip_sandbox_ready_sentinel(raw)
        assert observed is True
        assert _SANDBOX_READY_SENTINEL not in cleaned
        assert cleaned == "some preamble noise\nuser output here\n"

    def test_sentinel_only_no_other_output(self):
        cleaned, observed = strip_sandbox_ready_sentinel(_SANDBOX_READY_LINE)
        assert observed is True
        assert cleaned == ""


class TestReadinessBoundaryAtInterpreterLevel:
    """
    execute_python() must respect whatever classification
    spawn_low_integrity_process() already made internally via the
    readiness sentinel -- it never re-derives retry-safety itself.
    """

    def test_status_code_without_ready_sentinel_is_retry_eligible(self, sandbox, monkeypatch):
        """
        known STATUS_* + READY NOT observed => raised as
        RestrictedProcessBootstrapError(retry_safe=True) internally =>
        eligible for the explicit compatibility fallback.
        """
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError(
                    f"status=0x{STATUS_DLL_INIT_FAILED:08X}; readiness sentinel never observed",
                    retry_safe=True,
                ),
            ),
            patch(
                "jarvis.sandbox.interpreter.subprocess.Popen",
                return_value=_fake_compat_process(),
            ) as mock_popen,
            _patched_job_assignment_success(),
        ):
            result = sandbox.execute_python("print('compat ran')")

        mock_popen.assert_called_once()
        assert result.success is True

    def test_status_code_with_ready_sentinel_observed_never_retries(self, sandbox, monkeypatch):
        """
        Simulated child that emits READY and THEN exits with
        STATUS_DLL_INIT_FAILED: spawn_low_integrity_process() observed the
        sentinel internally, so it does NOT raise -- it returns the
        genuine (if unusual) exit code normally, exactly like any other
        execution outcome. Compat fallback enabled or not, the Popen
        fallback path MUST NOT be called.
        """
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                return_value=(STATUS_DLL_INIT_FAILED, "user output before the crash\n", "", False),
            ) as mock_spawn,
            patch("jarvis.sandbox.interpreter.subprocess.Popen") as mock_popen,
        ):
            result = sandbox.execute_python("print('user output before the crash')")

        mock_spawn.assert_called_once()
        mock_popen.assert_not_called()
        assert result.success is False
        assert result.exit_code == STATUS_DLL_INIT_FAILED
        assert "user output before the crash" in result.stdout


# ============================================================================
# Blocker 3: the restricted child is created SUSPENDED and must only be
# resumed after the Job Object (a declared security/resource boundary) has
# been confirmed assigned. Job assignment/ResumeThread must never fail
# open. Every Win32 call is mocked; no real OS privilege is required.
# ============================================================================

@pytest.mark.skipif(sys.platform != "win32", reason="Requires ctypes.windll (Win32 API surface)")
class TestJobObjectFailClosed:
    def test_job_assignment_failure_terminates_suspended_child_and_never_resumes(self, tmp_path):
        import ctypes

        from jarvis.sandbox.security import spawn_low_integrity_process

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        fake_job = MagicMock(spec=WindowsJobObject)
        fake_job.assign_process.return_value = False  # Job assignment FAILS

        with (
            patch.object(advapi32, "OpenProcessToken", return_value=1),
            patch.object(advapi32, "CreateRestrictedToken", return_value=1),
            patch.object(advapi32, "SetTokenInformation", return_value=1),
            patch.object(advapi32, "CreateProcessAsUserW", return_value=1),
            patch.object(kernel32, "ResumeThread") as mock_resume,
            patch.object(kernel32, "TerminateProcess", return_value=1) as mock_terminate,
        ):
            with pytest.raises(RestrictedProcessBootstrapError, match="AssignProcessToJobObject") as exc_info:
                spawn_low_integrity_process(
                    cmd="doesnotmatter", cwd=str(tmp_path), job=fake_job, timeout_seconds=1.0
                )

        assert exc_info.value.retry_safe is True  # child never executed a single instruction
        fake_job.assign_process.assert_called_once()
        mock_resume.assert_not_called()
        mock_terminate.assert_called_once()

    def test_job_assignment_success_resumes_exactly_once_and_proceeds(self, tmp_path):
        import ctypes

        from jarvis.sandbox.security import spawn_low_integrity_process

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        fake_job = MagicMock(spec=WindowsJobObject)
        fake_job.assign_process.return_value = True  # Job assignment SUCCEEDS

        with (
            patch.object(advapi32, "OpenProcessToken", return_value=1),
            patch.object(advapi32, "CreateRestrictedToken", return_value=1),
            patch.object(advapi32, "SetTokenInformation", return_value=1),
            patch.object(advapi32, "CreateProcessAsUserW", return_value=1),
            patch.object(kernel32, "ResumeThread", return_value=1) as mock_resume,
            patch.object(kernel32, "WaitForSingleObject", return_value=0) as mock_wait,  # WAIT_OBJECT_0
            patch.object(kernel32, "GetExitCodeProcess", return_value=1),
            patch.object(kernel32, "ReadFile", return_value=0),  # immediate EOF, no output
            patch.object(kernel32, "TerminateProcess") as mock_terminate,
        ):
            exit_code, stdout, stderr, timed_out = spawn_low_integrity_process(
                cmd="doesnotmatter", cwd=str(tmp_path), job=fake_job, timeout_seconds=1.0
            )

        fake_job.assign_process.assert_called_once()
        mock_resume.assert_called_once()
        mock_wait.assert_called_once()
        mock_terminate.assert_not_called()
        assert exit_code == 0
        assert timed_out is False

    def test_resume_thread_failure_terminates_child_and_raises_retry_safe(self, tmp_path):
        import ctypes

        from jarvis.sandbox.security import spawn_low_integrity_process

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        fake_job = MagicMock(spec=WindowsJobObject)
        fake_job.assign_process.return_value = True

        with (
            patch.object(advapi32, "OpenProcessToken", return_value=1),
            patch.object(advapi32, "CreateRestrictedToken", return_value=1),
            patch.object(advapi32, "SetTokenInformation", return_value=1),
            patch.object(advapi32, "CreateProcessAsUserW", return_value=1),
            patch.object(kernel32, "ResumeThread", return_value=0xFFFFFFFF) as mock_resume,  # FAILS
            patch.object(kernel32, "TerminateProcess", return_value=1) as mock_terminate,
        ):
            with pytest.raises(RestrictedProcessBootstrapError, match="ResumeThread") as exc_info:
                spawn_low_integrity_process(
                    cmd="doesnotmatter", cwd=str(tmp_path), job=fake_job, timeout_seconds=1.0
                )

        # ResumeThread failing means the thread was NEVER resumed -- the
        # child executed zero instructions, which is formally provable to
        # be pre-user-code, so this specific failure IS retry-eligible.
        assert exc_info.value.retry_safe is True
        mock_resume.assert_called_once()
        mock_terminate.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires ctypes.windll (Win32 API surface)")
class TestCompatPopenJobObjectFailClosed:
    """
    Blocker 3 (compat path): the legacy subprocess.Popen fallback must not
    silently claim "Job-Object + scrubbed environment" isolation when Job
    Object assignment actually fails -- it must kill/refuse the process.
    """

    def test_compat_popen_killed_when_job_assignment_fails(self, sandbox, monkeypatch):
        monkeypatch.setenv(SANDBOX_COMPAT_FALLBACK_ENV_VAR, "1")

        fake_process = MagicMock()
        fake_process.pid = 4242
        fake_process.communicate.return_value = ("should not be used\n", "")
        fake_process.returncode = 0

        import ctypes

        kernel32 = ctypes.windll.kernel32

        with (
            patch(
                "jarvis.sandbox.interpreter.spawn_low_integrity_process",
                side_effect=RestrictedProcessBootstrapError("simulated", retry_safe=True),
            ),
            patch("jarvis.sandbox.interpreter.subprocess.Popen", return_value=fake_process),
            patch.object(kernel32, "OpenProcess", return_value=0),  # simulate failure -> h_proc falsy
        ):
            result = sandbox.execute_python("print('should not run')")

        fake_process.kill.assert_called_once()
        assert result.success is False
        assert result.exit_code == -1
        assert "job object" in (result.error or "").lower()
        assert result.stdout == ""


# ============================================================================
# Goal 8: critical unchecked Win32 return value fix (SetTokenInformation)
# ============================================================================

@pytest.mark.skipif(sys.platform != "win32", reason="Requires ctypes.windll (Win32 API surface)")
class TestSetTokenInformationFailure:
    def test_set_token_information_failure_raises_before_launch(self, tmp_path):
        """
        DO NOT claim Low Integrity isolation succeeded if
        SetTokenInformation(TokenIntegrityLevel) failed. Every Win32 call up
        to and including the failure point is mocked, so this requires no
        real OS token privilege.
        """
        import ctypes

        from jarvis.sandbox.security import spawn_low_integrity_process

        advapi32 = ctypes.windll.advapi32
        with (
            patch.object(advapi32, "OpenProcessToken", return_value=1),
            patch.object(advapi32, "CreateRestrictedToken", return_value=1),
            patch.object(advapi32, "SetTokenInformation", return_value=0),  # FAILS
            patch.object(advapi32, "CreateProcessAsUserW") as mock_create_process,
        ):
            with pytest.raises(RestrictedProcessBootstrapError, match="SetTokenInformation"):
                spawn_low_integrity_process(cmd="doesnotmatter", cwd=str(tmp_path), timeout_seconds=1.0)

        mock_create_process.assert_not_called()
