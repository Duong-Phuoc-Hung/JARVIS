# Milestone 4 Technical Investigation Report: Security Tooling, Packet Capture & Unit Testing Strategy

**Agent**: Explorer 3 (`explorer_m4_3`)  
**Milestone**: Milestone 4 — Hardware Diagnostics, Self-Healing & Security Tooling  
**Scope**: F-23 (Network Scanner), F-24 (Packet Capture), F-25 (Security Risk Reporting), R12 (Biometric Privilege Gate), and Milestone 4 Unit Testing Strategy (`tests/test_hardware_monitor.py`, `tests/test_self_healing.py`, `tests/test_security_scanner.py`).

---

## 1. Executive Summary

This report delivers the comprehensive architectural design, failure mode analysis, privilege gating model, and unit testing strategy for the Security Tooling subsystem and Milestone 4 test infrastructure of the JARVIS AI Desktop Assistant.

All components adhere to the core design principles of JARVIS:
1. **Zero-Hardware & Zero-Cloud Dependency in Tests**: Pure-Python deterministic mocking for subprocesses, Win32 ctypes, psutil, Nmap/TShark binaries, and camera feeds.
2. **Strict Fault Isolation & Graceful Degradation**: External binaries (`nmap`, `tshark`) missing from `%PATH%` return structured diagnostic records (`TOOL_NOT_FOUND`) rather than raising unhandled exceptions or crashing the daemon.
3. **Biometric Security Gating (R12)**: Offensive/intrusive network scans and packet captures strictly require verified owner identity (`is_authenticated=True` & `PrivilegeLevel.ADMIN`) before execution.
4. **Bilingual Vocal Briefings**: Formatted spoken summaries in Vietnamese and English for audio delivery via ElevenLabs / SAPI5.

---

## 2. Security Subsystem Architecture (`jarvis/security/`)

The security subsystem is composed of two modules: `jarvis/security/scanner.py` and `jarvis/security/report.py`.

```
jarvis/security/
├── __init__.py
├── scanner.py          # Nmap & TShark subprocess wrappers with failure isolation
└── report.py           # Risk assessment, severity ranking, Markdown & voice reports, Biometric Gate
```

### 2.1 Network Scanner Wrapper: `jarvis/security/scanner.py` (F-23)

#### 2.1.1 Functional Responsibilities
- **Subnet Discovery**: Fast ping sweep (`nmap -sn <target>`) across local subnets (e.g., `192.168.1.0/24`).
- **Port & Service Auditing**: Port scanning (`nmap -F` or `-p 1-1024,3306,3389,8000,8080`) with service banner version detection (`-sV`).
- **Vulnerability Script Scanning**: Script scanning (`nmap --script vuln` or targeted NSE scripts like `ssl-cert`, `smb-vuln*`, `http-vuln*`).
- **Unprivileged Windows Fallback**: Detection of Windows unprivileged shell context; automatically falls back from raw SYN scan (`-sS`) to TCP connect scan (`-sT`).

#### 2.1.2 Subprocess Management & Binary Resolution
```python
# Binary resolution order
def resolve_nmap_binary() -> Optional[str]:
    # 1. PATH lookup
    path = shutil.which("nmap")
    if path:
        return path
    # 2. Common Windows 64-bit / 32-bit install directories
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Nmap" / "nmap.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Nmap" / "nmap.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None
```

#### 2.1.3 Robust Error Handling & Graceful Degradation
| Scenario | Detection Mechanism | Behavior & Return Value |
|---|---|---|
| Binary Missing | `resolve_nmap_binary() is None` | Returns `ScanReport(status="TOOL_NOT_FOUND", hosts=[], total_hosts=0)` |
| Execution Timeout | `subprocess.TimeoutExpired` | Terminate process tree, return `ScanReport(status="TIMEOUT", duration_s=timeout_s)` |
| Access Denied | `PermissionError` / Exit code != 0 | Log warning, return `ScanReport(status="PERMISSION_DENIED" / "ERROR")` |
| Malformed XML/Stdout | `xml.etree.ElementTree.ParseError` | Fallback to regex stdout parsing or return partial host list |

#### 2.1.4 Data Models
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

class VulnerabilitySeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

@dataclass
class Vulnerability:
    id: str                                  # e.g., "CVE-2021-44228", "NMAP-SMB-MS17-010"
    title: str
    severity: VulnerabilitySeverity
    description: str
    port: Optional[int] = None
    remediation: str = ""

@dataclass
class HostScanResult:
    ip: str
    hostname: str
    status: str = "UP"                       # "UP" or "DOWN"
    open_ports: List[int] = field(default_factory=list)
    services: Dict[int, str] = field(default_factory=dict)
    vulnerabilities: List[Vulnerability] = field(default_factory=list)

@dataclass
class ScanReport:
    target: str
    hosts: List[HostScanResult] = field(default_factory=list)
    total_hosts: int = 0
    duration_s: float = 0.0
    status: str = "SUCCESS"                  # "SUCCESS", "TOOL_NOT_FOUND", "TIMEOUT", "PERMISSION_DENIED", "ERROR"
    error_message: Optional[str] = None
```

---

### 2.2 Packet Capture Wrapper: `jarvis/security/scanner.py` (F-24)

#### 2.2.1 Functional Responsibilities
- **Interface Discovery**: Enumerates available capture interfaces (`tshark -D` / `dumpcap -D`).
- **Targeted Capture**: Captures packets with duration limit (`-a duration:N`) or packet count limit (`-c N`).
- **BPF Filtering**: Applies Berkeley Packet Filters (e.g., `-f "tcp port 80 or tcp port 443 or udp port 53"`).
- **PCAP File Persistence**: Writes raw captures to `.pcap` / `.pcapng` files in `logs/captures/`.
- **Statistical Breakdown & Heuristic Anomaly Analysis**:
  - Protocol distribution calculation (`TCP`, `UDP`, `ICMP`, `DNS`, `TLS`, `HTTP`).
  - Anomaly heuristics: Port sweep detection (>50 unique ports/sec), broadcast/multicast storm (>100 pkts/sec), unexpected cleartext credential ports (21, 23).

#### 2.2.2 Subprocess & Error Handling
```python
@dataclass
class PacketCaptureResult:
    interface: str
    packet_count: int
    duration_s: float
    protocols: Dict[str, int] = field(default_factory=dict)
    top_talkers: List[Dict[str, Any]] = field(default_factory=list)
    anomalies_detected: int = 0
    anomalies: List[str] = field(default_factory=list)
    pcap_path: Optional[str] = None
    status: str = "SUCCESS"                  # "SUCCESS", "TOOL_NOT_FOUND", "TIMEOUT", "ERROR"
    error_message: Optional[str] = None
```
- If `tshark.exe` is missing: Gracefully returns `PacketCaptureResult(status="TOOL_NOT_FOUND")`.
- If capture times out: Process is explicitly killed using `proc.kill()` and `proc.wait(timeout=1.0)` to avoid zombie processes.

---

### 2.3 Security Risk Report Generator: `jarvis/security/report.py` (F-25)

#### 2.3.1 Risk Ranking Matrix
Vulnerabilities and open ports are categorized into 4 severity levels:
1. **CRITICAL**:
   - Remote Code Execution (RCE), unauthenticated remote administrative interfaces, critical known CVEs (e.g. MS17-010, Log4j).
   - Telnet (port 23) or unauthenticated remote shell on public/untrusted interfaces.
2. **HIGH**:
   - Exposed databases on subnet (MySQL 3306, PostgreSQL 5432, MongoDB 27017, Redis 6379 with no auth).
   - Cleartext credentials protocols (FTP 21, HTTP Basic Auth without TLS).
   - Exposed RDP (3389) or VNC (5900) without NLA.
3. **MEDIUM**:
   - Web servers on non-standard ports missing TLS, verbose banner leakage exposing outdated software versions.
   - SMBv1 enabled.
4. **LOW / INFO**:
   - Standard secured services (HTTPS 443, SSH 22 with modern ciphers, DNS 53).

#### 2.3.2 Structured Markdown Report Format
The generator compiles findings into `logs/security_reports/security_report_<timestamp>.md`:

```markdown
# JARVIS Security Audit & Risk Report

**Target**: `192.168.1.0/24`  
**Scan Timestamp**: 2026-08-22 11:30:00 UTC  
**Execution Duration**: 4.25s  
**Overall Risk Status**: ⚠️ HIGH RISK  

---

## 1. Executive Summary
- Total Active Hosts: **3**
- Total Open Ports: **9**
- Detected Vulnerabilities: **2** (0 Critical, 1 High, 1 Medium, 0 Low)

---

## 2. Active Host Matrix
| IP Address | Hostname | Status | Open Ports | Services |
|---|---|---|---|---|
| `192.168.1.1` | router.lan | UP | 80, 443, 53 | HTTP, HTTPS, DNS |
| `192.168.1.15` | desktop.lan | UP | 22, 3389 | SSH, RDP |
| `192.168.1.50` | db-dev.lan | UP | 3306, 8080 | MySQL, HTTP-Alt |

---

## 3. Vulnerability & Risk Assessment
### [HIGH] Exposed MySQL Database on Subnet
- **Host**: `192.168.1.50` (Port 3306)
- **Description**: Database port is accessible across the local subnet without IP whitelisting.
- **Remediation**: Bind MySQL daemon to `127.0.0.1` or configure Windows Firewall rules.

---

## 4. Packet Capture Telemetry
- Interface: `Ethernet0` | Duration: 10.0s | Packets Captured: 240
- Protocol Breakdown: TCP (72%), UDP (21%), ICMP (7%)
- Anomalies: None detected
```

#### 2.3.3 Spoken Executive Summary Generation
The generator produces localized executive summaries for TTS:
- **Vietnamese Summary (`get_voice_summary(lang="vi")`)**:
  - Clean: `"Đã hoàn thành quét bảo mật mạng {target}. Phát hiện {total_hosts} thiết bị đang hoạt động. Trạng thái hệ thống an toàn, không phát hiện lỗ hổng nghiêm trọng."`
  - High/Critical Risk: `"Cảnh báo bảo mật: Đã quét mạng {target}. Phát hiện {total_hosts} thiết bị và {vuln_count} lỗ hổng, bao gồm lỗ hổng mức độ {highest_severity}. Đã lưu báo cáo chi tiết vào file."`
- **English Summary (`get_voice_summary(lang="en")`)**:
  - Clean: `"Security audit completed for network {target}. Found {total_hosts} active devices. All systems secure."`
  - Warning: `"Security Alert: Audit completed for network {target}. Detected {total_hosts} hosts and {vuln_count} vulnerabilities with {highest_severity} risk level. Report saved."`

---

## 3. Biometric Privilege Gating (R12 / `SecurityContext`)

### 3.1 Policy Enforcement Rules
In accordance with **R12** and the JARVIS architecture:
1. All offensive/intrusive network operations (`nmap` subnet discovery, vulnerability audits, raw `tshark` packet captures) are classified as **`PrivilegeLevel.ADMIN`**.
2. An action cannot be executed unless the `RequesterContext` has:
   - `is_authenticated == True` (authenticated via biometric face verification or explicit bypass mode).
   - `granted_privilege >= PrivilegeLevel.ADMIN`.
3. If unauthenticated, the dispatcher or security module immediately rejects the execution:
   - Returns `ActionResult(success=False, error_code="PERMISSION_DENIED")` or raises `PermissionError`.
   - Emits event `security.privilege_denied` on the `EventBus`.

### 3.2 Privilege Gate Implementation Model
```python
from jarvis.core.models import PrivilegeLevel, RequesterContext

class SecurityPrivilegeGate:
    """Enforces biometric authorization barrier for sensitive security actions."""

    @staticmethod
    def verify_privilege(context: Optional[RequesterContext], action_name: str = "security_scan") -> bool:
        if context is None:
            return False
        # System internal calls or authenticated Admin contexts are allowed
        if context.requester_id == "system":
            return True
        return bool(context.is_authenticated and context.granted_privilege >= PrivilegeLevel.ADMIN)

    @staticmethod
    def enforce(context: Optional[RequesterContext], action_name: str = "security_scan") -> None:
        if not SecurityPrivilegeGate.verify_privilege(context, action_name):
            raise PermissionError(
                f"Biometric authentication required to execute privileged action '{action_name}'."
            )
```

---

## 4. Comprehensive Unit Testing Strategy for Milestone 4

The Milestone 4 test suite consists of 3 dedicated test modules, supported by fixtures in `tests/conftest.py`:

```
tests/
├── conftest.py                   # MockHardwareProvider, MockWin32Platform, MockCameraFeed, MockHttpServer
├── test_hardware_monitor.py      # F-20, F-21, F-22 (Hardware telemetry, SMART, voice alerts)
├── test_self_healing.py          # F-41, F-42, F-43 (Watchdog, IsHungAppWindow, healing protocol)
└── test_security_scanner.py      # F-23, F-24, F-25, R12 (Nmap, TShark, reports, biometric gate)
```

### 4.1 Test Plan: `tests/test_hardware_monitor.py`

| Test Function | Tier | Target Feature | Mocking Strategy | Acceptance Verification |
|---|---|---|---|---|
| `test_hardware_telemetry_cpu_gpu_ram_collection_tier1` | Tier 1 | F-20 | `MockHardwareProvider` psutil patch | Asserts CPU %, temp, GPU %, temp, RAM %, VRAM GB match provider |
| `test_hardware_smart_disk_health_prober_tier1` | Tier 1 | F-21 | `mock_hardware_provider.smart_drives` | Asserts "PASSED" and transitions to "WARNING" on reallocated sectors |
| `test_hardware_voice_query_tinh_trang_he_thong_tier1` | Tier 1 | F-22 | `monitor.get_voice_summary()` | Asserts Vietnamese keywords: "tình trạng hệ thống", "cpu", "ram" |
| `test_hardware_threshold_alert_trigger_tier1` | Tier 1 | F-22 | CPU temp set to 92.0°C | Asserts alert list contains component "cpu", level "CRITICAL" |
| `test_hardware_missing_gpu_sensor_graceful_handling_tier2` | Tier 2 | F-20 | GPU temp set to `None` | Asserts `metrics.gpu_temp_c is None`, summary generation succeeds without crash |
| `test_hardware_alert_debounce_cooldown_tier2` | Tier 2 | F-22 | Rapid sequential threshold checks | Asserts 1st check triggers alert, 2nd check within cooldown is suppressed |
| `test_hardware_powershell_cim_fallback_tier2` | Tier 2 | F-20 | Mocked subprocess CIM query | Asserts fallback parser extracts CPU load and temperature |

### 4.2 Test Plan: `tests/test_self_healing.py`

| Test Function | Tier | Target Feature | Mocking Strategy | Acceptance Verification |
|---|---|---|---|---|
| `test_healing_watchdog_ram_pressure_detection_tier1` | Tier 1 | F-41 | `mock_hardware_provider.simulate_ram_exhaustion()` | Asserts `is_ram_critical()` returns `True` when RAM >= 90% |
| `test_healing_unresponsive_app_ishungappwindow_probe_tier1` | Tier 1 | F-42 | `mock_win32_platform.add_hung_window()` | Asserts `find_hung_windows()` identifies hung PID and process name |
| `test_healing_autonomous_process_kill_and_reclaim_tier1` | Tier 1 | F-43 | `mock_win32_platform` + RAM drop simulation | Asserts PID added to `killed_pids`, RAM reclaimed < 80%, spoken confirmation returned |
| `test_healing_protected_system_process_whitelist_tier2` | Tier 2 | F-43 | Attempt kill on `explorer.exe`, `jarvis.exe` | Asserts `success=False`, `reason="PROTECTED_PROCESS"`, PID not killed |
| `test_healing_advisory_mode_when_autokill_disabled_tier2` | Tier 2 | F-43 | Engine initialized with `auto_kill=False` | Asserts process NOT killed, warning alert returned |
| `test_healing_hung_window_ctypes_user32_integration_tier2` | Tier 2 | F-42 | Intercepted `user32.IsHungAppWindow` | Asserts ctypes bridge passes HWND integer and returns correct boolean |

### 4.3 Test Plan: `tests/test_security_scanner.py`

| Test Function | Tier | Target Feature | Mocking Strategy | Acceptance Verification |
|---|---|---|---|---|
| `test_security_nmap_subnet_scan_wrapper_tier1` | Tier 1 | F-23 | `monkeypatch` `shutil.which` + mocked stdout | Asserts `status == "SUCCESS"`, `total_hosts >= 2`, open ports parsed |
| `test_security_tshark_packet_capture_wrapper_tier1` | Tier 1 | F-24 | `TSharkCaptureWrapper` mock | Asserts packet count = 100, TCP = 70%, anomalies = 0 |
| `test_security_risk_report_markdown_and_voice_summary_tier1` | Tier 1 | F-25 | `SecurityReportGenerator` + `tmp_path` | Asserts `.md` file created with host table, Vietnamese spoken summary generated |
| `test_security_nmap_binary_not_installed_error_tier2` | Tier 2 | F-23 | `monkeypatch.setattr(shutil, "which", lambda cmd: None)` | Asserts `status == "TOOL_NOT_FOUND"`, `total_hosts == 0`, zero crash |
| `test_security_tshark_binary_not_installed_error_tier2` | Tier 2 | F-24 | Missing binary mock | Asserts `status == "TOOL_NOT_FOUND"`, zero crash |
| `test_security_subprocess_timeout_handling_tier2` | Tier 2 | F-23 | `subprocess.TimeoutExpired` simulation | Asserts `status == "TIMEOUT"`, duration recorded |
| `test_security_biometric_privilege_gating_unauthenticated_tier2` | Tier 2 | R12, F-34 | `RequesterContext(is_authenticated=False)` | Asserts unauthenticated scan attempt is rejected with `PERMISSION_DENIED` |
| `test_security_biometric_privilege_gating_authenticated_tier2` | Tier 2 | R12, F-34 | `RequesterContext.user(authenticated=True)` | Asserts authenticated owner is permitted to scan |

---

## 5. Implementation Guidance for Milestone 4 Workers

1. **File Locations**:
   - Implement `jarvis/security/scanner.py` containing `NetworkScanner` (Nmap) and `PacketCapture` (TShark).
   - Implement `jarvis/security/report.py` containing `SecurityReportGenerator`, `Vulnerability`, and `SecurityPrivilegeGate`.
2. **Action Dispatcher Integration**:
   - Register actions in `ActionDispatcher`:
     - `"security.nmap_scan"` (`PrivilegeLevel.ADMIN`)
     - `"security.packet_capture"` (`PrivilegeLevel.ADMIN`)
     - `"security.generate_report"` (`PrivilegeLevel.NORMAL`)
     - `"security.status_summary"` (`PrivilegeLevel.NORMAL`)
3. **Execution Safety**:
   - All subprocess calls MUST specify explicit `timeout` parameters.
   - Missing binaries (`nmap`, `tshark`) must return diagnostic error dataclasses, NEVER raising unhandled exceptions into the core loop.
