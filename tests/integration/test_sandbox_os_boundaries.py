"""
tests/integration/test_sandbox_os_boundaries.py
================================================
Adversarial (Red-Team) Real OS-Level Integration Tests for Sandbox Process Isolation.
These tests execute real Python subprocesses (NO MOCKS) on Windows to verify:
  1. Windows Job Object ActiveProcessLimit=1 blocks child/grandchild process spawning.
  2. Adversarial socket reload / evasion is blocked at the compiled C-extension layer (_socket).
  3. Adversarial dynamic reflection trying to load ctypes (ws2_32.dll) is blocked.
  4. Adversarial filesystem directory traversal attempting to read .env is blocked.
  5. Adversarial external filesystem write outside sandbox scratch root is blocked.
  6. Environment Scrubbing eliminates all API keys and secrets.
  7. Hard Timeout terminates infinite loop subprocesses.
  8. Memory and Output Flood Protection caps 1MB streams.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

from jarvis.sandbox.interpreter import CodeInterpreterSandbox
from jarvis.sandbox.validator import ASTCodeValidator, ValidationResult


class _PermissiveValidator(ASTCodeValidator):
    """Bypasses static AST validation to test OS & runtime adversarial guards directly."""
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
    """Sandbox with permissive AST validator to test adversarial runtime & OS guards."""
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
        assert "SPAWN_BLOCKED" in result.stdout
        assert "SPAWN_SUCCESS" not in result.stdout

    def test_adversarial_socket_reload_evasion_blocked(self, os_test_sandbox):
        """
        Verify that an adversarial script attempting to reload the socket module
        is blocked by the unlinked/poisoned low-level C-extension _socket module.
        """
        code = """
import importlib
try:
    # Attempting to reload and recreate socket
    sock_mod = importlib.import_module("socket")
    importlib.reload(sock_mod)
    s = sock_mod.socket()
    print("EVASION_SUCCESS")
except Exception as exc:
    print(f"EVASION_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "EVASION_BLOCKED" in result.stdout
        assert "EVASION_SUCCESS" not in result.stdout

    def test_adversarial_dynamic_reflection_ctypes_blocked(self, os_test_sandbox):
        """
        Verify that an adversarial script using dynamic reflection to load ctypes
        and access ws2_32.dll directly is blocked by the poisoned _ctypes module.
        """
        code = """
try:
    # Dynamic reflection to bypass AST and load ctypes
    ct = __import__("c" + "types")
    ws = ct.WinDLL("ws2_32.dll")
    print("CTYPES_LOADED")
except Exception as exc:
    print(f"CTYPES_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "CTYPES_BLOCKED" in result.stdout
        assert "CTYPES_LOADED" not in result.stdout

    def test_adversarial_dotenv_traversal_read_blocked(self, os_test_sandbox, tmp_path):
        """
        Verify that attempting to read .env or traverse parent directories for secrets
        is blocked by the scoped filesystem guard.
        """
        # Create a fake .env in the parent directory
        parent_env = tmp_path / ".env"
        parent_env.write_text("SUPER_SECRET_TOKEN=12345", encoding="utf-8")

        code = """
try:
    with open("../.env", "r") as f:
        content = f.read()
    print("DOTENV_LEAKED")
except Exception as exc:
    print(f"DOTENV_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "DOTENV_BLOCKED" in result.stdout
        assert "DOTENV_LEAKED" not in result.stdout

    def test_adversarial_external_filesystem_write_blocked(self, os_test_sandbox, tmp_path):
        """
        Verify that attempting to write files outside the sandbox scratch root is blocked.
        """
        target_outside_file = tmp_path / "outside_evil.txt"
        target_path_str = str(target_outside_file).replace("\\", "/")

        code = f"""
try:
    with open("{target_path_str}", "w") as f:
        f.write("malicious payload")
    print("EXTERNAL_WRITE_SUCCESS")
except Exception as exc:
    print(f"EXTERNAL_WRITE_BLOCKED: {{type(exc).__name__}}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "EXTERNAL_WRITE_BLOCKED" in result.stdout
        assert "EXTERNAL_WRITE_SUCCESS" not in result.stdout
        assert not target_outside_file.exists()

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
