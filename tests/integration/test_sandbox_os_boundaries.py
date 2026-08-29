"""
tests/integration/test_sandbox_os_boundaries.py
================================================
Adversarial (Red-Team) Real OS-Level Integration Tests for Sandbox Process Isolation.
These tests execute real Python subprocesses (NO MOCKS) on Windows to verify:
  1. io.open() bypass attempts are caught and blocked.
  2. os.open() / os.fdopen() low-level bypass attempts are caught and blocked.
  3. Arbitrary file read attempts outside sandbox scratch root (Directory Allowlist) are blocked.
  4. del sys.modules + re-import evasion is blocked by sys.meta_path[0] interceptor.
  5. Dynamic reflection ctypes / WinDLL (ws2_32.dll) evasion is blocked.
  6. Windows Job Object ActiveProcessLimit=1 blocks child/grandchild process spawning.
  7. Environment Scrubbing eliminates 100% of API keys and secrets.
  8. Hard Timeout terminates infinite loop subprocesses.
  9. Memory and Output Flood Protection caps 1MB streams.
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
    def test_adversarial_io_open_bypass_blocked(self, os_test_sandbox, tmp_path):
        """
        Verify that attempting to bypass builtins.open via io.open() to read
        files outside the sandbox is blocked by the directory allowlist guard.
        """
        fake_secret = tmp_path / "config_prod.ini"
        fake_secret.write_text("DB_PASSWORD=secret123", encoding="utf-8")
        target_path_str = str(fake_secret).replace("\\", "/")

        code = f"""
import io
try:
    with io.open("{target_path_str}", "r") as f:
        data = f.read()
    print("IO_OPEN_LEAKED")
except Exception as exc:
    print(f"IO_OPEN_BLOCKED: {{type(exc).__name__}}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "IO_OPEN_BLOCKED" in result.stdout
        assert "IO_OPEN_LEAKED" not in result.stdout

    def test_adversarial_os_open_bypass_blocked(self, os_test_sandbox, tmp_path):
        """
        Verify that low-level os.open() file descriptor access outside the sandbox
        is blocked by the directory allowlist guard.
        """
        fake_secret = tmp_path / "app_secrets.json"
        fake_secret.write_text('{{"key": "val"}}', encoding="utf-8")
        target_path_str = str(fake_secret).replace("\\", "/")

        code = f"""
import os
try:
    fd = os.open("{target_path_str}", os.O_RDONLY)
    data = os.read(fd, 1024)
    os.close(fd)
    print("OS_OPEN_LEAKED")
except Exception as exc:
    print(f"OS_OPEN_BLOCKED: {{type(exc).__name__}}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "OS_OPEN_BLOCKED" in result.stdout
        assert "OS_OPEN_LEAKED" not in result.stdout

    def test_adversarial_precached_module_import_blocked(self, os_test_sandbox):
        """
        Verify that even if socket was pre-cached in sys.modules before user code runs,
        the cache poisoning step renders it completely disabled.
        """
        code = """
try:
    import socket
    s = socket.socket()
    print("PRECACHED_SOCKET_SUCCESS")
except Exception as exc:
    print(f"PRECACHED_SOCKET_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "PRECACHED_SOCKET_BLOCKED" in result.stdout
        assert "PRECACHED_SOCKET_SUCCESS" not in result.stdout

    def test_adversarial_import_jarvis_internals_blocked(self, os_test_sandbox):
        """
        Verify that untrusted code cannot import jarvis.sandbox.security to steal
        original unpatched I/O function references.
        """
        code = """
try:
    import jarvis.sandbox.security
    print("JARVIS_IMPORT_SUCCESS")
except Exception as exc:
    print(f"JARVIS_IMPORT_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "JARVIS_IMPORT_BLOCKED" in result.stdout
        assert "JARVIS_IMPORT_SUCCESS" not in result.stdout

    def test_adversarial_del_sys_modules_meta_path_reimport_blocked(self, os_test_sandbox):
        """
        Verify that clearing sys.modules and attempting to re-import socket
        is blocked at the sys.meta_path layer.
        """
        code = """
import sys
try:
    if "socket" in sys.modules: del sys.modules["socket"]
    if "_socket" in sys.modules: del sys.modules["_socket"]
    import socket
    s = socket.socket()
    print("SOCKET_RELOAD_SUCCESS")
except Exception as exc:
    print(f"SOCKET_RELOAD_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SOCKET_RELOAD_BLOCKED" in result.stdout
        assert "SOCKET_RELOAD_SUCCESS" not in result.stdout

    def test_adversarial_dynamic_reflection_ctypes_blocked(self, os_test_sandbox):
        """
        Verify that dynamic reflection attempting to load ctypes / WinDLL (ws2_32.dll)
        is blocked by sys.meta_path and module poisoning.
        """
        code = """
try:
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

    def test_adversarial_arbitrary_read_outside_sandbox_blocked(self, os_test_sandbox, tmp_path):
        """
        Verify that reading ANY file outside the designated sandbox root directory
        (regardless of filename) is blocked by the directory allowlist guard.
        """
        target_outside_file = tmp_path / "user_chat_history.db"
        target_outside_file.write_text("sqlite format 3", encoding="utf-8")
        target_path_str = str(target_outside_file).replace("\\", "/")

        code = f"""
try:
    with open("{target_path_str}", "r") as f:
        content = f.read()
    print("ARBITRARY_READ_SUCCESS")
except Exception as exc:
    print(f"ARBITRARY_READ_BLOCKED: {{type(exc).__name__}}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "ARBITRARY_READ_BLOCKED" in result.stdout
        assert "ARBITRARY_READ_SUCCESS" not in result.stdout

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object tests require Windows")
    def test_child_process_spawn_blocked_by_job_object(self, os_test_sandbox):
        """
        Verify that Windows kernel enforces ActiveProcessLimit=1 in Job Object,
        preventing any subprocess from spawning grandchild cmd/powershell processes.
        """
        code = """
try:
    import subprocess, sys
    p = subprocess.run([sys.executable, "-c", "print('grandchild')"], capture_output=True, text=True)
    print("SPAWN_SUCCESS")
except Exception as exc:
    print(f"SPAWN_BLOCKED: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SPAWN_BLOCKED" in result.stdout
        assert "SPAWN_SUCCESS" not in result.stdout

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
        assert len(result.stdout) <= (1.2 * 1024 * 1024)
        assert "[TRUNCATED" in result.stdout
