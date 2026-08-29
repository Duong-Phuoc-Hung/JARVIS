"""
tests/integration/test_sandbox_os_boundaries.py
================================================
Real OS-Level Integration Tests for Sandbox Process Isolation and Job Objects.
These tests execute real Python subprocesses (NO MOCKS) on Windows to verify:
  1. Windows Job Object ActiveProcessLimit=1 blocks child/grandchild process spawning.
  2. Zero-Trust Network Denial hook blocks socket/outbound connections.
  3. Environment Scrubbing eliminates all API keys and secrets.
  4. Hard Timeout terminates infinite loop subprocesses.
  5. Memory and Output Flood Protection caps 1MB streams.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

from jarvis.sandbox.interpreter import CodeInterpreterSandbox
from jarvis.sandbox.security import prepare_scrubbed_environment
from jarvis.sandbox.validator import ASTCodeValidator, ValidationResult


class _PermissiveValidator(ASTCodeValidator):
    """Bypasses static AST validation to test OS-level runtime guards directly."""
    def validate_python(self, code: str) -> ValidationResult:
        return ValidationResult(is_safe=True)


@pytest.fixture
def sandbox(tmp_path):
    return CodeInterpreterSandbox(
        base_scratch_dir=tmp_path / "scratch",
        default_timeout=5.0,
    )


@pytest.fixture
def os_test_sandbox(tmp_path):
    """Sandbox with permissive AST validator to test OS-level Job Object & Network guards."""
    return CodeInterpreterSandbox(
        base_scratch_dir=tmp_path / "os_scratch",
        default_timeout=5.0,
        validator=_PermissiveValidator(),
    )


class TestOSLevelProcessIsolation:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object tests require Windows")
    def test_child_process_spawn_blocked_by_job_object(self, os_test_sandbox):
        """
        Verify that Windows kernel enforces ActiveProcessLimit=1 in Job Object,
        preventing any subprocess from spawning grandchild cmd/powershell processes
        even if code bypasses AST static analysis.
        """
        code = """
import subprocess, sys
try:
    p = subprocess.run([sys.executable, "-c", "print('grandchild')"], capture_output=True, text=True)
    print("SPAWN_SUCCESS")
except Exception as exc:
    print(f"SPAWN_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        # Must catch OSError / WinError 1816 (ERROR_NOT_ENOUGH_QUOTA)
        assert "SPAWN_BLOCKED" in result.stdout
        assert "SPAWN_SUCCESS" not in result.stdout

    def test_network_connection_blocked_in_sandbox(self, os_test_sandbox):
        """
        Verify that network socket creation in the sandbox subprocess raises PermissionError
        even if code bypasses AST static analysis.
        """
        code = """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("SOCKET_CREATED")
except PermissionError as exc:
    print(f"NETWORK_BLOCKED: {exc}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "NETWORK_BLOCKED" in result.stdout
        assert "SOCKET_CREATED" not in result.stdout

    def test_environment_scrubbing_eliminates_secrets(self, sandbox, monkeypatch):
        """
        Verify that parent process API keys and secrets are 100% stripped from child subprocess.
        """
        monkeypatch.setenv("GOOGLE_API_KEY", "ai_super_secret_key_12345")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot987654321:token_secret")
        monkeypatch.setenv("DISCORD_TOKEN", "discord_bot_secret_xyz")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")

        code = """
import os
leaked = []
for key in ["GOOGLE_API_KEY", "TELEGRAM_BOT_TOKEN", "DISCORD_TOKEN", "DATABASE_URL"]:
    if os.environ.get(key):
        leaked.append(key)
print(f"LEAKED_KEYS: {leaked}")
"""
        result = sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "LEAKED_KEYS: []" in result.stdout

    def test_hard_timeout_terminates_infinite_loop(self, sandbox):
        """
        Verify that a running loop is terminated when exceeding timeout.
        """
        code = """
import time
while True:
    time.sleep(0.1)
"""
        result = sandbox.execute_python(code, timeout_seconds=1.5)
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in (result.error or "").lower()

    def test_stdout_flood_protection_caps_output(self, sandbox):
        """
        Verify that massive stdout output is truncated to prevent parent memory exhaustion.
        """
        code = """
# Print 2MB of text
print("A" * (2 * 1024 * 1024))
"""
        result = sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        # Output should be capped around 1MB
        assert len(result.stdout) <= (1.2 * 1024 * 1024)
        assert "[TRUNCATED" in result.stdout
