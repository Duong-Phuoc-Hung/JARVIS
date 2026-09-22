"""
tests/test_adversarial_m1_security_remediation.py
=================================================
Empirical Adversarial Challenge Suite for Milestone M1 Security Remediation.

Adversarially challenges and stress-tests:
1. ShellAssistant injection & metacharacter chaining (cmd.exe /c calc, &&, |, ;, $()).
2. SafetyGateInterceptor gating & bypass on shell_exec, vm_stop, sandbox_execute_code.
3. BrowserActionExecutor.download_file path traversal escapes.
4. SafetyGate token replay, consumption, concurrency race conditions, and JarvisApp disambiguation.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.automation.safety_gate import SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.browser.actions import BrowserActionExecutor
from jarvis.browser.models import BrowserConfig
from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.planner.models import TaskNode
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


# ===========================================================================
# 1. ShellAssistant Injection & Command Execution Adversarial Challenges
# ===========================================================================
class TestAdversarialShellAssistantInjection:
    """Stress-tests ShellAssistant against direct injection, metacharacters, and bypasses."""

    @pytest.fixture
    def assistant(self):
        return ShellAssistant()

    def test_direct_cmd_exe_execution_rejected(self, assistant):
        """Verify that direct raw cmd.exe invocation is rejected by the allowlist."""
        res = assistant.execute_natural_command("cmd.exe /c calc")
        assert res.get("success") is False
        assert res.get("exit_code") == -1
        assert "không nằm trong danh mục công cụ được phép thực thi" in res.get("stderr", "")

    def test_direct_calc_rejected(self, assistant):
        """Verify that unauthorized binaries like calc.exe are rejected."""
        res = assistant.execute_natural_command("calc.exe")
        assert res.get("success") is False
        assert "không nằm trong danh mục" in res.get("stderr", "")

    def test_powershell_encoded_command_or_injection(self, assistant):
        """Verify that dangerous destructive commands are gated even if passed via allowed tools."""
        res = assistant.execute_natural_command("powershell -Command Remove-Item -Path C:\\test -Recurse")
        assert res.get("requires_confirmation") is True or res.get("gated") is True

    def test_echo_command_chaining_injection_blocked(self, assistant):
        """
        Adversarial Test: Chaining secondary commands via cmd.exe builtin 'echo' or 'dir'.
        Vulnerability check: On Windows, line 624 wraps 'echo' with ['cmd.exe', '/c', *cmd_tokens].
        If cmd.exe evaluates '&&' or '&', it executes secondary commands without authorization.
        """
        res = assistant.execute_natural_command("echo safe && echo INJECTED_EXECUTION")
        stdout = res.get("stdout", "")
        # A secure implementation must NOT execute the chained command 'echo INJECTED_EXECUTION'.
        assert "INJECTED_EXECUTION" not in stdout, (
            f"VULNERABILITY DETECTED: ShellAssistant executed chained command via cmd.exe /c! stdout: {stdout!r}"
        )

    def test_dir_pipe_injection_blocked(self, assistant):
        """
        Adversarial Test: Piping output from 'dir' into another command on Windows.
        """
        res = assistant.execute_natural_command("dir | whoami")
        stdout = res.get("stdout", "")
        # If piped into whoami, the output will contain user domain/username
        assert "whoami" not in stdout and res.get("exit_code") != 0 or "\\" not in stdout

    def test_port_check_sql_or_shell_injection(self, assistant):
        """Verify that port inspection rejects non-integer/hostile inputs."""
        res = assistant.check_port("80; whoami")
        assert "Không thể kiểm tra port" in res or "rảnh" in res or "PID" in res


# ===========================================================================
# 2. Safety Interceptor Bypass Adversarial Challenges
# ===========================================================================
class TestAdversarialSafetyInterceptorBypass:
    """Stress-tests SafetyGateInterceptor against gating bypasses and parameter tampering."""

    @pytest.fixture
    def interceptor(self):
        return SafetyGateInterceptor(timeout_seconds=5.0)

    def test_shell_exec_requires_affirmative_token(self, interceptor):
        """Verify that shell_exec is classified as high-risk and cannot execute without token."""
        assert interceptor.is_high_risk("shell_exec", {"command": "echo test"}) is True
        token = interceptor.gate("shell_exec", {"command": "echo test"})
        assert token is not None

        # Attempt verify without confirmation
        ok, reason = interceptor.verify(token, "shell_exec", {"command": "echo test"})
        assert ok is False
        assert reason == "NOT_CONFIRMED"

    def test_vm_stop_requires_affirmative_token(self, interceptor):
        """Verify that vm_stop is classified as high-risk and requires confirmation."""
        assert interceptor.is_high_risk("vm_stop", {"vm_name": "prod-db"}) is True
        assert interceptor.is_high_risk("vm.vmware.stop", {"vm_name": "prod-db"}) is True
        assert interceptor.is_high_risk("vm_delete", {"vm_name": "prod-db"}) is True

    def test_sandbox_execute_code_in_high_risk_actions(self, interceptor):
        """
        Adversarial Test: Verify that sandbox_execute_code is unconditionally treated as HIGH_RISK.
        Per M1 requirements and worker claims, sandbox_execute_code must be in HIGH_RISK_ACTIONS.
        """
        # Testing safe-looking code or empty params: must still be high-risk!
        is_risky = interceptor.is_high_risk("sandbox_execute_code", {"code": "print('hello')"})
        assert is_risky is True, (
            "VULNERABILITY DETECTED: 'sandbox_execute_code' was not classified as high-risk! "
            "Arbitrary Python code execution can bypass safety gate when not in HIGH_RISK_ACTIONS."
        )

    def test_sandbox_execute_code_obfuscated_bypass_detected(self, interceptor):
        """
        Adversarial Test: Code execution using obfuscated primitives that avoid naive keyword matching.
        """
        obfuscated_payload = {"code": "__import__('builtins').eval('1 + 1')"}
        assert interceptor.is_high_risk("sandbox_execute_code", obfuscated_payload) is True, (
            "VULNERABILITY DETECTED: Obfuscated code execution in sandbox_execute_code bypassed is_high_risk check!"
        )

    def test_token_payload_tampering_rejected(self, interceptor):
        """Verify that a confirmed token cannot be used for a different payload."""
        token = interceptor.gate("shell_exec", {"command": "dir"})
        interceptor.confirm(token)

        # Attacker tries to use the confirmed token for a destructive command
        ok, reason = interceptor.verify(token, "shell_exec", {"command": "rmdir /s /q C:\\"})
        assert ok is False
        assert reason == "PAYLOAD_MISMATCH"

    def test_token_action_tampering_rejected(self, interceptor):
        """Verify that a confirmed token cannot be substituted for a different action."""
        token = interceptor.gate("home_assistant_turn_on", {"entity_id": "light.living_room"})
        interceptor.confirm(token)

        # Attacker tries to use the light-switch token to shut down system
        ok, reason = interceptor.verify(token, "system_shutdown", {"entity_id": "light.living_room"})
        assert ok is False
        assert reason == "ACTION_MISMATCH"


# ===========================================================================
# 3. Browser Download Path Traversal Adversarial Challenges
# ===========================================================================
class TestAdversarialBrowserDownloadPathTraversal:
    """Stress-tests BrowserActionExecutor.download_file against path traversal escapes."""

    @pytest.fixture
    def executor(self):
        tmp_base = Path(tempfile.gettempdir()) / "jarvis_adv_download_test"
        tmp_base.mkdir(parents=True, exist_ok=True)
        downloads_dir = tmp_base / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        cfg = BrowserConfig(
            downloads_dir=str(downloads_dir),
            session_storage_dir=str(tmp_base / "session"),
        )
        mock_driver = MagicMock()
        mock_driver.config = cfg
        mock_driver.last_error_status = None
        mock_driver.get_cookies.return_value = []
        return BrowserActionExecutor(mock_driver)

    @pytest.mark.parametrize(
        "escape_path",
        [
            "../../evil.bat",
            "..\\..\\evil.bat",
            "../../../Windows/System32/cmd.exe",
            "C:\\Windows\\System32\\calc.exe",
            "C:/Windows/System32/calc.exe",
            "D:\\secret\\passwords.txt",
            "/etc/passwd",
            "/etc/shadow",
            "\\\\localhost\\c$\\evil.bat",
            "..",
            "../",
            "..\\",
        ],
    )
    def test_path_traversal_escapes_blocked(self, executor, escape_path):
        """Verify that path traversal strings in target_path fail closed without writing files."""
        res = executor.download_file("https://example.com/asset.zip", target_path=escape_path)
        assert res.success is False
        assert res.error_message == "The browser download failed." or res.downloaded_file is None

    def test_url_path_traversal_sanitized_when_target_path_omitted(self, executor):
        """Verify that malicious path elements in the download URL itself cannot escape downloads_dir."""
        malicious_url = "https://example.com/../../windows/system32/cmd.exe"
        # When target_path is None, destination is determined by URL basename
        res = executor.download_file(malicious_url, target_path=None)
        # Even if network fails, verify no file outside downloads_dir was created
        downloads_dir = Path(executor.driver.config.downloads_dir).resolve()
        # Ensure no cmd.exe was created outside downloads_dir
        assert not (downloads_dir.parent / "cmd.exe").exists()


# ===========================================================================
# 4. SafetyGate Token Replay, Consumption & Concurrency Race Conditions
# ===========================================================================
class TestAdversarialSafetyGateTokenReplayAndConcurrency:
    """Stress-tests SafetyGate against replay attacks, state mutations, and multi-threaded races."""

    def test_confirm_token_replay_fails(self):
        """Verify that a confirmed token cannot be confirmed a second time."""
        sg = SafetyGate(timeout_seconds=10.0)
        token = sg.request_confirmation("Format Drive")

        assert sg.confirm(token) is True
        # Replay attempt: confirm again
        assert sg.confirm(token) is False, "REPLAY VULNERABILITY: Token was confirmed a second time!"

    def test_consume_token_replay_fails(self):
        """Verify that consume() is strictly one-shot and cannot be consumed twice."""
        sg = SafetyGate(timeout_seconds=10.0)
        token = sg.request_confirmation("Transfer Funds")
        sg.confirm(token)

        assert sg.consume(token) is True
        # Second consume must fail
        assert sg.consume(token) is False, "REPLAY VULNERABILITY: Confirmed token was consumed more than once!"
        # Confirm after consume must also fail
        assert sg.confirm(token) is False

    def test_unconfirmed_token_cannot_be_consumed(self):
        """Verify that a pending (unconfirmed) token cannot be consumed."""
        sg = SafetyGate(timeout_seconds=10.0)
        token = sg.request_confirmation("Pending Action")
        assert sg.consume(token) is False
        assert sg.is_pending(token) is True

    def test_expired_token_cannot_be_confirmed_or_consumed(self):
        """Verify that expired tokens immediately reject confirmation and consumption."""
        sg = SafetyGate(timeout_seconds=0.01)
        token = sg.request_confirmation("Immediate Expiry")
        time.sleep(0.02)

        assert sg.confirm(token) is False
        assert sg.consume(token) is False
        assert sg.is_pending(token) is False

    def test_interceptor_verify_one_shot_consumption(self):
        """Verify that SafetyGateInterceptor.verify() one-shot consumes the token."""
        interceptor = SafetyGateInterceptor()
        token = interceptor.gate("file_delete", {"path": "important.doc"})
        interceptor.confirm(token)

        ok1, reason1 = interceptor.verify(token, "file_delete", {"path": "important.doc"})
        assert ok1 is True
        assert reason1 == "OK"

        # Replay verify()
        ok2, reason2 = interceptor.verify(token, "file_delete", {"path": "important.doc"})
        assert ok2 is False
        assert reason2 == "ALREADY_CONSUMED", f"Expected ALREADY_CONSUMED, got {reason2}"

    def test_concurrent_multithreaded_confirm_race(self):
        """Stress-test concurrent confirm calls across 50 threads; exactly 1 must succeed."""
        sg = SafetyGate(timeout_seconds=10.0)
        token = sg.request_confirmation("Concurrent Action")
        results = []

        def worker():
            res = sg.confirm(token)
            results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = results.count(True)
        failures = results.count(False)
        assert successes == 1, f"RACE CONDITION: {successes} threads succeeded in confirming token!"
        assert failures == 49

    def test_concurrent_multithreaded_consume_race(self):
        """Stress-test concurrent consume calls across 50 threads; exactly 1 must succeed."""
        sg = SafetyGate(timeout_seconds=10.0)
        token = sg.request_confirmation("Concurrent Consume Action")
        sg.confirm(token)
        results = []

        def worker():
            res = sg.consume(token)
            results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = results.count(True)
        failures = results.count(False)
        assert successes == 1, f"RACE CONDITION: {successes} threads succeeded in consuming token!"
        assert failures == 49

    def test_jarvis_app_multi_pending_token_disambiguation(self):
        """Verify that JarvisApp requires explicit token when multiple actions are pending."""
        app = MagicMock(spec=JarvisApp)
        app.safety_gate = SafetyGate(timeout_seconds=30.0)
        app._handle_safety_gate_confirm = JarvisApp._handle_safety_gate_confirm.__get__(app)
        app._handle_safety_gate_reject = JarvisApp._handle_safety_gate_reject.__get__(app)

        t1 = app.safety_gate.request_confirmation("Action 1")
        t2 = app.safety_gate.request_confirmation("Action 2")

        # Ambiguous confirmation (token omitted)
        res_confirm = app._handle_safety_gate_confirm(token=None)
        assert res_confirm["status"] == "failed"
        assert "cung cấp mã token cụ thể" in res_confirm["message"]

        # Ambiguous rejection (token omitted)
        res_reject = app._handle_safety_gate_reject(token=None)
        assert res_reject["status"] == "failed"
        assert "cung cấp mã token cụ thể" in res_reject["message"]

        # Explicit confirmation works
        res_t1 = app._handle_safety_gate_confirm(token=t1)
        assert res_t1["status"] == "success"
        assert app.safety_gate.get_pending(t1).status == "CONFIRMED"
