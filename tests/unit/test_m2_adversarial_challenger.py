"""
tests/unit/test_m2_adversarial_challenger.py
============================================
Adversarial test suite by Empirical Challenger for Milestone M2.
Probes and stress-tests:
1. HomeAssistantClient:
   - turn_on, turn_off, toggle, set_temperature with missing credentials (NOT_CONFIGURED)
   - turn_on, turn_off, toggle, set_temperature with network errors (CONNECTION_FAILED)
   - Security refusal, HTTP error codes, retryable semantics
2. MobileFileBridge:
   - Rate limit triggers retryable=True and code='RATE_LIMITED'
   - Invalid files return code='VALIDATION_ERROR'
   - Security: Path traversal, oversized files, disallowed extensions
   - Clipboard & Screenshot unconfigured and failure modes
3. VMOrchestrator:
   - start_vm, stop_vm, suspend_vm, snapshot_vm return ActionResult
   - Subprocess returncode != 0 failures
   - Subprocess exceptions and timeouts
   - Hypervisor selection and state transitions
"""
from __future__ import annotations

import os
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.automation.vm import HypervisorType, VMActionResult, VMOrchestrator, VMState
from jarvis.comms.mobile_bridge import MobileFileBridge
from jarvis.comms.rate_limiter import RateLimitConfig
from jarvis.core.models import ActionResult, ActionStatus
from jarvis.smart_home.home_assistant import HomeAssistantClient


# ============================================================================
# 1. HomeAssistantClient Adversarial Probes
# ============================================================================

class TestHomeAssistantAdversarial:
    """Probing HomeAssistantClient under missing credentials, network errors, and malicious inputs."""

    @pytest.mark.parametrize("method_name,args", [
        ("turn_on", ("light.living_room",)),
        ("turn_off", ("light.living_room",)),
        ("toggle", ("light.living_room",)),
        ("set_temperature", ("climate.ac_unit", 23.5)),
    ])
    def test_missing_credentials_returns_not_configured(self, method_name, args):
        """Verify that all mutating methods return ActionResult with NOT_CONFIGURED when token is empty."""
        client = HomeAssistantClient(access_token="", base_url="http://127.0.0.1:8123")
        method = getattr(client, method_name)
        res = method(*args)

        assert isinstance(res, ActionResult), f"{method_name} must return ActionResult"
        assert res.success is False
        assert res.status == ActionStatus.ERROR
        assert res.code == "NOT_CONFIGURED"
        assert res.retryable is False
        assert "token missing" in res.message or "NOT_CONFIGURED" in res.message
        # Test dict emulation
        assert res["success"] is False
        assert res["code"] == "NOT_CONFIGURED"
        assert res.get("code") == "NOT_CONFIGURED"

    @pytest.mark.parametrize("method_name,args", [
        ("turn_on", ("light.living_room",)),
        ("turn_off", ("light.living_room",)),
        ("toggle", ("light.living_room",)),
        ("set_temperature", ("climate.ac_unit", 21.0)),
    ])
    def test_network_errors_return_connection_failed_and_retryable(self, method_name, args):
        """Verify that network errors (URLError, timeout) return CONNECTION_FAILED with retryable=True."""
        client = HomeAssistantClient(access_token="valid_token_123", base_url="http://127.0.0.1:9")
        method = getattr(client, method_name)

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            res = method(*args)

        assert isinstance(res, ActionResult), f"{method_name} must return ActionResult"
        assert res.success is False
        assert res.status == ActionStatus.ERROR
        assert res.code == "CONNECTION_FAILED"
        assert res.retryable is True
        assert "Connection failed" in res.message or "unreachable" in res.message
        assert res["code"] == "CONNECTION_FAILED"
        assert res["retryable"] is True

    def test_http_server_error_500_is_retryable(self):
        """Verify HTTP 500 returns HTTP_500 and is retryable."""
        client = HomeAssistantClient(access_token="valid_token_123", base_url="http://ha.local:8123")
        mock_resp = MagicMock()
        mock_resp.status = 500

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            res = client.turn_on("light.living_room")

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.code == "HTTP_500"
        assert res.retryable is True

    def test_http_client_error_400_is_not_retryable(self):
        """Verify HTTP 400 returns HTTP_400 and is NOT retryable."""
        client = HomeAssistantClient(access_token="valid_token_123", base_url="http://ha.local:8123")
        mock_resp = MagicMock()
        mock_resp.status = 400

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            res = client.turn_on("light.living_room")

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.code == "HTTP_400"
        assert res.retryable is False

    def test_security_refusal_on_restricted_domains_and_injection(self):
        """Verify security-sensitive domains and injection attacks are refused before network dispatch."""
        client = HomeAssistantClient(access_token="valid_token_123")

        # Disallowed domain
        res_lock = client.call_service("lock", "unlock", {"entity_id": "lock.front_door"})
        assert isinstance(res_lock, ActionResult)
        assert res_lock.success is False
        assert res_lock.code == "SECURITY_REFUSAL"
        assert res_lock.retryable is False

        # Command injection attempt
        res_inject = client.turn_on("light.desk; rm -rf /")
        assert isinstance(res_inject, ActionResult)
        assert res_inject.success is False
        assert res_inject.code == "SECURITY_REFUSAL"
        assert res_inject.retryable is False


# ============================================================================
# 2. MobileFileBridge Adversarial Probes
# ============================================================================

class TestMobileFileBridgeAdversarial:
    """Probing MobileFileBridge rate limiting, validation, and attack vectors."""

    def test_rate_limit_burst_exhaustion_triggers_retryable_and_429(self, tmp_path):
        """Verify rate limit exhaustion returns retryable=True, code='RATE_LIMITED', status=429."""
        bridge = MobileFileBridge(
            save_directory=str(tmp_path / "downloads"),
            rate_limit_config=RateLimitConfig(requests_per_minute=1, burst_limit=1),
        )
        meta = {"user_id": "attacker_user_1"}

        # 1st request succeeds
        res1 = bridge.receive_file(b"legit data", "doc.txt", metadata=meta)
        assert res1.success is True
        assert res1.status == ActionStatus.SUCCESS

        # 2nd request is throttled
        res2 = bridge.receive_file(b"spam data", "doc2.txt", metadata=meta)
        assert isinstance(res2, ActionResult)
        assert res2.success is False
        assert res2.status == ActionStatus.ERROR
        assert res2.code == "RATE_LIMITED"
        assert res2.retryable is True
        assert res2.data["status"] == 429
        assert res2.data["retry_after_s"] > 0
        assert res2["retryable"] is True
        assert res2["status"] == 429

    @pytest.mark.parametrize("filename,content", [
        ("malware.exe", b"MZ..."),
        ("exploit.bat", b"@echo off"),
        ("script.vbs", b"WScript.Echo"),
        ("payload.py", b"import os"),
        ("trojan.dll", b"MZ..."),
    ])
    def test_invalid_file_extensions_return_validation_error(self, tmp_path, filename, content):
        """Verify disallowed file extensions return VALIDATION_ERROR with retryable=False."""
        bridge = MobileFileBridge(save_directory=str(tmp_path / "downloads"))
        res = bridge.receive_file(content, filename)

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.status == ActionStatus.ERROR
        assert res.code == "VALIDATION_ERROR"
        assert res.retryable is False
        assert "không được hỗ trợ" in res.message or "định dạng" in res.message
        assert res["status"] == 400

    def test_oversized_file_returns_validation_error(self, tmp_path):
        """Verify file exceeding size limit is rejected with VALIDATION_ERROR."""
        bridge = MobileFileBridge(
            save_directory=str(tmp_path / "downloads"),
            max_file_size_mb=1,
        )
        oversized_data = b"X" * (2 * 1024 * 1024)  # 2MB > 1MB limit
        res = bridge.receive_file(oversized_data, "large.txt")

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.code == "VALIDATION_ERROR"
        assert res.retryable is False
        assert "vượt quá giới hạn" in res.message

    def test_path_traversal_sanitization(self, tmp_path):
        """Verify filename with path traversal is sanitized and kept inside save directory."""
        download_dir = tmp_path / "downloads"
        bridge = MobileFileBridge(save_directory=str(download_dir))

        traversal_filename = "../../../etc/passwd.txt"
        res = bridge.receive_file(b"safe content", traversal_filename)

        assert res.success is True
        saved_path = Path(res.data["saved_path"])
        # Must reside safely inside download_dir
        assert saved_path.is_relative_to(download_dir)
        assert ".." not in saved_path.name

    def test_clipboard_empty_returns_error(self, tmp_path):
        """Verify empty clipboard returns EMPTY_CLIPBOARD with retryable=False."""
        bridge = MobileFileBridge(save_directory=str(tmp_path / "downloads"))
        with patch.object(bridge, "_get_clipboard_text", return_value=""):
            res = bridge.send_clipboard_to_mobile()

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.code == "EMPTY_CLIPBOARD"
        assert res.retryable is False

    def test_screenshot_capture_failure(self, tmp_path):
        """Verify failed screen capture returns CAPTURE_FAILED."""
        bridge = MobileFileBridge(save_directory=str(tmp_path / "downloads"))
        with patch.object(bridge, "_capture_screenshot", return_value=None):
            res = bridge.send_screenshot_to_mobile()

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.code == "CAPTURE_FAILED"
        assert res.retryable is False


# ============================================================================
# 3. VMOrchestrator Adversarial Probes
# ============================================================================

class TestVMOrchestratorAdversarial:
    """Probing VMOrchestrator under subprocess failure, timeouts, and state tracking."""

    @pytest.mark.parametrize("method_name,args,expected_action", [
        ("start_vm", ("Ubuntu-Server",), "vm.vmware.start"),
        ("stop_vm", ("Ubuntu-Server",), "vm.vmware.stop"),
        ("suspend_vm", ("Ubuntu-Server",), "vm.vmware.suspend"),
        ("snapshot_vm", ("Ubuntu-Server", "checkpoint-1"), "vm.vmware.snapshot"),
    ])
    def test_dry_run_all_methods_return_action_result(self, method_name, args, expected_action):
        """Verify all VM operations return ActionResult under dry_run mode."""
        vm_orch = VMOrchestrator(dry_run=True)
        method = getattr(vm_orch, method_name)
        res = method(*args)

        assert isinstance(res, ActionResult)
        assert res.action_name == expected_action
        assert res.success is True
        assert res.status == ActionStatus.SUCCESS
        assert res.code == "OK"
        assert res.retryable is False
        assert res["hypervisor"] == "vmware"

    def test_live_vm_start_subprocess_failure(self):
        """Verify non-zero subprocess returncode generates ActionResult failure with proper code."""
        vm_orch = VMOrchestrator(dry_run=False, vmrun_path="fake_vmrun.exe")

        # Mock shutil.which so it doesn't skip to dry_run
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "Error: Cannot open VM config file"

        with patch("shutil.which", return_value="C:\\fake\\fake_vmrun.exe"), \
             patch("subprocess.run", return_value=mock_proc):
            res = vm_orch.start_vm("BrokenVM", hypervisor="vmware")

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.status == ActionStatus.ERROR
        assert res.code == "VM_START_FAILED"
        assert res.retryable is False
        assert "Cannot open VM" in res.message
        assert res["return_code"] == 1
        assert res["state"] == VMState.STOPPED.value

    def test_live_vm_stop_subprocess_failure(self):
        """Verify stop_vm failure generates proper ActionResult."""
        vm_orch = VMOrchestrator(dry_run=False, vboxmanage_path="fake_vbox.exe")

        mock_proc = MagicMock()
        mock_proc.returncode = 2
        mock_proc.stdout = ""
        mock_proc.stderr = "VBoxManage: error: Machine not found"

        with patch("shutil.which", return_value="C:\\fake\\fake_vbox.exe"), \
             patch("subprocess.run", return_value=mock_proc):
            res = vm_orch.stop_vm("NonExistentVM", hypervisor="virtualbox")

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.status == ActionStatus.ERROR
        assert res.code == "VM_STOP_FAILED"
        assert res.retryable is False
        assert "Machine not found" in res.message
        assert res["return_code"] == 2

    def test_live_vm_start_subprocess_exception(self):
        """Verify subprocess timeout or OS exception returns VM_EXCEPTION."""
        vm_orch = VMOrchestrator(dry_run=False, vmrun_path="fake_vmrun.exe")

        with patch("shutil.which", return_value="C:\\fake\\fake_vmrun.exe"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="vmrun", timeout=30)):
            res = vm_orch.start_vm("TimeoutVM", hypervisor="vmware")

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.status == ActionStatus.ERROR
        assert res.code == "VM_EXCEPTION"
        assert res.retryable is False
        assert "timed out" in res.message.lower()
        assert res["state"] == VMState.UNKNOWN.value


# ============================================================================
# 4. ActionResult Bidirectional Contract & Subscripting Stress Test
# ============================================================================

class TestActionResultContractAdversarial:
    """Stress testing ActionResult edge cases."""

    def test_status_normalization_string_and_enum(self):
        """Verify that string statuses are converted/harmonized to ActionStatus enum."""
        res1 = ActionResult(status="error", success=False)
        assert res1.status == ActionStatus.ERROR

        res2 = ActionResult(status="RATE_LIMITED", success=False)
        assert res2.status == ActionStatus.RATE_LIMITED

    def test_inconsistent_success_status_harmonization(self):
        """If success=False but status=SUCCESS, __post_init__ harmonizes to status=ERROR."""
        res = ActionResult(success=False, status=ActionStatus.SUCCESS)
        assert res.status == ActionStatus.ERROR
        assert res.success is False

    def test_dict_subscripting_key_error_on_missing_key(self):
        """Subscripting a non-existent key must raise KeyError."""
        res = ActionResult(action_name="test", data={"known_key": 123})
        with pytest.raises(KeyError):
            _ = res["unknown_key"]

    def test_to_dict_preserves_all_contract_fields(self):
        """Ensure to_dict contains all 4 standard fields and matches dataclass state."""
        res = ActionResult(
            action_name="contract_test",
            status=ActionStatus.RATE_LIMITED,
            code="TOO_MANY_REQUESTS",
            message="Please wait 10 seconds",
            retryable=True,
            data={"limit": 100},
        )
        d = res.to_dict()
        assert d["status"] == "RATE_LIMITED"
        assert d["code"] == "TOO_MANY_REQUESTS"
        assert d["message"] == "Please wait 10 seconds"
        assert d["retryable"] is True
        assert d["success"] is False
        assert d["data"] == {"limit": 100}
