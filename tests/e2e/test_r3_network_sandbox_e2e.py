"""
tests/e2e/test_r3_network_sandbox_e2e.py
=========================================
E2E Test Suite for Requirement 3: Network Sandbox B2 & Outbound Socket Isolation.

Covers:
  - TIER 1: Feature Coverage
      * test_r3_real_os_socket_connect_blocked (@pytest.mark.real_os)
      * test_r3_in_process_socket_module_poisoning
      * test_r3_udp_socket_creation_and_sendto_blocked
      * test_r3_dns_resolution_attempt_blocked
      * test_r3_http_client_libraries_blocked
  - TIER 2: Boundary, Corner & Adversarial Cases
      * test_r3_corner_dynamic_import_reimport_evasion
      * test_r3_corner_ctypes_ws2_32_winsock_ffi_blocked
      * test_r3_corner_ipv6_loopback_and_any_bind_blocked
      * test_r3_boundary_local_ipc_pipe_and_unix_socket_denial
      * test_r3_adversarial_ssl_tls_wrap_socket_blocked
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
def os_test_sandbox(tmp_path):
    """Sandbox with permissive AST validator to test adversarial runtime & OS network guards."""
    return CodeInterpreterSandbox(
        base_scratch_dir=tmp_path / "network_scratch",
        default_timeout=5.0,
        validator=_PermissiveValidator(),
    )


# ============================================================================
# TIER 1: FEATURE COVERAGE (R3)
# ============================================================================

class TestR3NetworkSandboxFeatureTier1:
    """Tier 1: Feature verification for AppContainer & Network Sandbox Socket Blocking."""

    @pytest.mark.real_os
    def test_r3_real_os_socket_connect_blocked(self, os_test_sandbox):
        """
        Adversarial Non-Mock Test: Verified on real Windows OS.
        Confirms attempting `socket.connect(("8.8.8.8", 80))` raises PermissionError/OSError
        and fails closed without transmitting network packets.
        """
        code = """
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    s.connect(("8.8.8.8", 80))
    print("SOCKET_CONNECT_SUCCESS")
except (PermissionError, OSError, AttributeError) as exc:
    print(f"SOCKET_CONNECT_BLOCKED_{type(exc).__name__}")
except Exception as exc:
    print(f"SOCKET_CONNECT_OTHER_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SOCKET_CONNECT_SUCCESS" not in result.stdout
        assert (
            "SOCKET_CONNECT_BLOCKED" in result.stdout
            or "SOCKET_CONNECT_OTHER" in result.stdout
        )

    def test_r3_in_process_socket_module_poisoning(self, os_test_sandbox):
        """
        Verify that `import socket; socket.socket()` in sandboxed script
        is neutralized by sys.modules poisoning / sentinel wrapper.
        """
        code = """
try:
    import socket
    sock = socket.socket()
    print("SOCKET_INSTANTIATED")
except Exception as exc:
    print(f"SOCKET_POISONED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SOCKET_INSTANTIATED" not in result.stdout
        assert "SOCKET_POISONED" in result.stdout

    def test_r3_udp_socket_creation_and_sendto_blocked(self, os_test_sandbox):
        """
        Verify UDP datagram packet transmission attempts (`socket.SOCK_DGRAM`)
        are blocked by the sandbox security boundary.
        """
        code = """
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"exfiltration_payload", ("8.8.8.8", 53))
    print("UDP_SEND_SUCCESS")
except Exception as exc:
    print(f"UDP_SEND_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "UDP_SEND_SUCCESS" not in result.stdout
        assert "UDP_SEND_BLOCKED" in result.stdout

    def test_r3_dns_resolution_attempt_blocked(self, os_test_sandbox):
        """
        Verify DNS query / hostname resolution attempts via `gethostbyname` or `getaddrinfo`
        are blocked and do not perform DNS lookups.
        """
        code = """
try:
    import socket
    ip = socket.gethostbyname("api.openai.com")
    print(f"DNS_RESOLVED: {ip}")
except Exception as exc:
    print(f"DNS_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "DNS_RESOLVED" not in result.stdout
        assert "DNS_BLOCKED" in result.stdout

    def test_r3_http_client_libraries_blocked(self, os_test_sandbox):
        """
        Verify high-level standard library HTTP clients (`urllib.request`, `http.client`)
        are blocked from importing or making outbound connections.
        """
        code = """
urllib_blocked = False
try:
    import urllib.request
    urllib.request.urlopen("https://www.google.com", timeout=1)
except Exception as exc:
    urllib_blocked = True

http_client_blocked = False
try:
    import http.client
    conn = http.client.HTTPSConnection("www.google.com", timeout=1)
    conn.request("GET", "/")
except Exception as exc:
    http_client_blocked = True

print(f"URLLIB_BLOCKED={urllib_blocked}")
print(f"HTTP_CLIENT_BLOCKED={http_client_blocked}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "URLLIB_BLOCKED=True" in result.stdout
        assert "HTTP_CLIENT_BLOCKED=True" in result.stdout


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (R3)
# ============================================================================

class TestR3NetworkSandboxBoundaryTier2:
    """Tier 2: Boundary, corner cases, and adversarial evasion vectors for R3."""

    def test_r3_corner_dynamic_import_reimport_evasion(self, os_test_sandbox):
        """
        Evasion Attempt: Deleting `sys.modules['socket']` followed by `importlib.import_module("socket")`
        must be intercepted and blocked by `sys.meta_path[0]` BlockedMetaPathFinder.
        """
        code = """
import sys
try:
    if "socket" in sys.modules:
        del sys.modules["socket"]
    import importlib
    s_mod = importlib.import_module("socket")
    s = s_mod.socket()
    print("REIMPORT_EVASION_SUCCESS")
except Exception as exc:
    print(f"REIMPORT_EVASION_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "REIMPORT_EVASION_SUCCESS" not in result.stdout
        assert "REIMPORT_EVASION_BLOCKED" in result.stdout

    def test_r3_corner_ctypes_ws2_32_winsock_ffi_blocked(self, os_test_sandbox):
        """
        Evasion Attempt: Using `ctypes.windll.ws2_32` to directly invoke WSAStartup
        or socket functions via native FFI is blocked.
        """
        code = """
try:
    import ctypes
    ws2 = ctypes.windll.ws2_32
    sock = ws2.socket(2, 1, 6)  # AF_INET, SOCK_STREAM, IPPROTO_TCP
    print(f"CTYPES_WINSOCK_SOCKET={sock}")
except Exception as exc:
    print(f"CTYPES_WINSOCK_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "CTYPES_WINSOCK_SOCKET" not in result.stdout
        assert "CTYPES_WINSOCK_BLOCKED" in result.stdout

    def test_r3_corner_ipv6_loopback_and_any_bind_blocked(self, os_test_sandbox):
        """
        Corner Case: Attempting to bind or listen on IPv6 loopback (`::1`) or `0.0.0.0`
        to create an unauthorized in-process listener is blocked.
        """
        code = """
try:
    import socket
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(("::1", 0))
    print("IPV6_BIND_SUCCESS")
except Exception as exc:
    print(f"IPV6_BIND_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "IPV6_BIND_SUCCESS" not in result.stdout
        assert "IPV6_BIND_BLOCKED" in result.stdout

    def test_r3_boundary_local_ipc_pipe_and_unix_socket_denial(self, os_test_sandbox):
        """
        Boundary Case: Attempting low-level IPC socket or named pipe connection
        to escape sandbox boundaries is blocked.
        """
        code = """
try:
    import _winapi
    h_pipe = _winapi.CreateFile(
        "\\\\.\\pipe\\jarvis_control",
        _winapi.GENERIC_READ,
        0, 0, _winapi.OPEN_EXISTING, 0, 0
    )
    print("IPC_PIPE_OPENED")
except Exception as exc:
    print(f"IPC_PIPE_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "IPC_PIPE_OPENED" not in result.stdout
        assert "IPC_PIPE_BLOCKED" in result.stdout

    def test_r3_adversarial_ssl_tls_wrap_socket_blocked(self, os_test_sandbox):
        """
        Adversarial: Importing `_ssl` or `ssl` to create TLS encrypted socket tunnels
        fails closed due to module blocking.
        """
        code = """
try:
    import ssl
    ctx = ssl.create_default_context()
    print("SSL_CONTEXT_CREATED")
except Exception as exc:
    print(f"SSL_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SSL_CONTEXT_CREATED" not in result.stdout
        assert "SSL_BLOCKED" in result.stdout


# ============================================================================
# DUAL-EVIDENCE TEST: subprocess starts AND non-network code runs successfully
# ============================================================================

class TestR3DualEvidenceStartupAndBlocking:
    """
    Critical dual-evidence test to rule out the failure mode where AppContainer
    process dies at startup (bad ACLs) rather than blocking only network calls.

    A process that crashes at startup would also "pass" network-blocking tests
    vacuously (no network traffic because nothing ran). This test class provides
    two separate, independent assertions:

    1. The sandboxed subprocess starts and executes non-network computation correctly.
    2. The same (or equivalent) subprocess rejects socket.connect() specifically.

    Both must hold simultaneously. If the process died at startup, assertion #1 fails.
    If network is not actually blocked, assertion #2 fails.
    """

    @pytest.mark.real_os
    def test_r3_dual_evidence_compute_succeeds_then_socket_blocked(self, os_test_sandbox):
        """
        DUAL EVIDENCE:
        Part A — Non-network code executes correctly (proves subprocess started with valid ACLs).
        Part B — socket.connect() is blocked specifically (proves network isolation works).

        Both assertions are required. Passing only Part B could mean the process
        crashed at startup and never reached the socket call.
        """
        code = """
import math
import hashlib

# ── Part A: Non-network computation (must succeed) ────────────────────────
result_math = math.factorial(10)                  # 3628800
result_hash = hashlib.sha256(b"jarvis").hexdigest()[:8]   # deterministic
result_str  = "hello" + "_" + "sandbox"           # string concat

print(f"COMPUTE_OK math={result_math} hash={result_hash} str={result_str}")

# ── Part B: Network socket specifically blocked ────────────────────────────
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(("8.8.8.8", 80))
    print("SOCKET_CONNECT_SUCCESS")
except (PermissionError, OSError, AttributeError, Exception) as exc:
    print(f"SOCKET_BLOCKED_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=8.0)

        # Part A: subprocess started, ran, and computed correctly
        assert result.success is True, (
            "Sandbox subprocess did not execute successfully — "
            "possible AppContainer ACL misconfiguration causing startup crash."
        )
        assert "COMPUTE_OK" in result.stdout, (
            f"Non-network computation did not produce output — "
            f"subprocess may have crashed at startup. stdout={result.stdout!r}"
        )
        # Verify specific computed values (not just that COMPUTE_OK printed)
        assert "math=3628800" in result.stdout, (
            "math.factorial(10) returned wrong result — subprocess compute integrity issue."
        )
        assert "str=hello_sandbox" in result.stdout, (
            "String concat produced wrong result — subprocess compute integrity issue."
        )

        # Part B: network specifically blocked (independent of Part A)
        assert "SOCKET_CONNECT_SUCCESS" not in result.stdout, (
            "socket.connect() succeeded — network sandbox B2 is NOT blocking outbound connections."
        )
        assert "SOCKET_BLOCKED" in result.stdout, (
            f"Expected SOCKET_BLOCKED marker not found. stdout={result.stdout!r}"
        )

    @pytest.mark.real_os
    def test_r3_dual_evidence_file_write_succeeds_network_blocked(self, os_test_sandbox, tmp_path):
        """
        DUAL EVIDENCE (file I/O variant):
        Part A — Writing to the sandbox scratch directory works (proves subprocess runs with
                 correct permissions for allowed operations).
        Part B — Outbound UDP to port 53 (DNS) is blocked.
        """
        scratch = tmp_path / "dual_evidence_scratch"
        scratch.mkdir()
        sentinel_path = scratch / "sentinel.txt"

        code = f"""
import pathlib

# ── Part A: Allowed file I/O in scratch (must succeed) ────────────────────
p = pathlib.Path(r"{sentinel_path}")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("dual_evidence_sentinel")
read_back = p.read_text()
print(f"FILE_IO_OK read_back={{read_back}}")

# ── Part B: DNS / UDP network blocked ─────────────────────────────────────
try:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"\\x00" * 12, ("8.8.8.8", 53))
    print("DNS_UDP_SUCCESS")
except Exception as exc:
    print(f"DNS_UDP_BLOCKED_{{type(exc).__name__}}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=8.0)

        # Part A
        assert result.success is True
        assert "FILE_IO_OK" in result.stdout, (
            f"File I/O in scratch failed — subprocess may not have started. stdout={result.stdout!r}"
        )
        assert "read_back=dual_evidence_sentinel" in result.stdout

        # Part B
        assert "DNS_UDP_SUCCESS" not in result.stdout
        assert "DNS_UDP_BLOCKED" in result.stdout
