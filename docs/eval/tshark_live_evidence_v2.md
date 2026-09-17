# Real Runtime Evidence Report: TShark Packet Capture v2 (R11)

**Standard**: `AGENTS.md §2` (Anti-Fabrication Principle) & `AUDIT_FRAMEWORK.md` (Fail-Closed & Runtime Verification)  
**Date of Audit**: 2026-09-17 (Local: 2026-09-18T02:45:00+07:00)  
**Subsystem**: `jarvis.security.scanner.PacketCapture` & `jarvis.security.scanner.resolve_tshark_binary`  
**Host Target**: Windows 11 x64 (25H2 Build 26200), Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz  
**Auditor**: `teamwork_preview_worker_m2_1`  
**Gate Status**: `HARDWARE_BLOCKED (KERNEL_DRIVER_PENDING)`  

---

## 1. Executive Summary

Requirement **R11** mandates an empirical runtime evaluation of the network packet capture subsystem (`PacketCapture`) and direct invocation of the underlying Wireshark / TShark binary on this host machine.

### Key Findings
1. **Binary Installed & Discovered**:
   - `C:\Program Files\Wireshark\tshark.exe` is **present** and operational on disk (Wireshark 4.6.8 installed via Winget).
   - `resolve_tshark_binary()` in `jarvis/security/scanner.py` successfully resolves the binary at `C:\Program Files\Wireshark\tshark.exe`.
   - `tshark.exe --version` exits with code `0`.
2. **Missing Kernel-Mode Driver (`Npcap` / `wpcap.dll`)**:
   - In runtime info reported by TShark itself: `Without: -Npcap`.
   - Directly invoking `tshark -D` or capturing on any local interface (e.g. `eth0` or `1`) exits with code `1` and emits:
     `(unable to load Npcap (wpcap.dll); can't open eth0 to capture) In order to capture packets, Npcap must be installed.`
3. **Fail-Closed & Anti-Fabrication Invariants Preserved**:
   - `PacketCapture.capture_packets()` catches the non-zero exit code (`1`), logs `TShark capture exited with non-zero code 1`, and returns:
     `PacketCaptureResult(status="NO_TSHARK_OUTPUT", packet_count=0, protocols={})`.
   - Exactly zero synthetic packets or fabricated protocols are emitted (`AGENTS.md §2` compliance).
4. **Gate Classification**:
   - Following `AGENTS.md §5` Three-Tier Verdict Discipline, this cannot be marked `PASS runtime` because live packet capture did not succeed on real network traffic.
   - It is truthfully and precisely classified as:
     **`HARDWARE_BLOCKED (KERNEL_DRIVER_PENDING)`**.

---

## 2. Host Context & Environment Evidence

### 2.1 Host System Information
- **Operating System**: 64-bit Windows 11 (25H2), build 26200
- **CPU**: Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz (SSE4.2)
- **Physical Memory**: 16,205 MB RAM
- **TShark Binary Path**: `C:\Program Files\Wireshark\tshark.exe`

### 2.2 Verbatim TShark Version Output
Command executed:
```powershell
& "C:\Program Files\Wireshark\tshark.exe" --version
```
Output (Exit code: `0`):
```text
TShark (Wireshark) 4.6.8 (v4.6.8-0-ge677bf052328).

Copyright 1998-2026 Gerald Combs <gerald@wireshark.org> and contributors.
Licensed under the terms of the GNU General Public License (version 2 or later).
This is free software; see the file named COPYING in the distribution. There is
NO WARRANTY; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Compile-time info:
 Bit width: 64-bit
  Compiler: Microsoft Visual Studio 2026 (VC++ 14.51, build 36244)
      GLib: 2.86.3
 With:
  +brotli                     +MaxMind
  +Gcrypt 1.12.2              +nghttp2 1.65.0
  +GnuTLS 3.8.13 and PKCS#11  +nghttp3 1.8.0
  +Kerberos (MIT)             +PCRE2 10.47 2025-10-21
  +libpcap                    +Snappy 1.1.9
  +libsmi 0.5.0               +xxhash 0.8.3
  +libxml2 2.15.1             +zlib 1.3.1
  +Lua 5.4.6 (UfW patched)    +zlib-ng 2.2.3
  +LZ4 1.10.0                 +Zstandard 1.5.7

Runtime info:
      OS: 64-bit Windows 11 (25H2), build 26200
     CPU: Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz (with SSE4.2)
  Memory: 16205 MB of physical memory
    GLib: 2.86.3
  Locale: LC_TYPE=Vietnamese_Vietnam.utf8
 Plugins: supported, 0 loaded
 With:
  +brotli 1.2.0            +LZ4 1.10.0              +xxhash 803
  +c-ares 1.34.6           +nghttp2 1.65.0          +Zstandard 1.5.7
  +Gcrypt 1.12.2           +nghttp3 1.8.0
  +GnuTLS 3.8.13           +PCRE2 10.47 2025-10-21
 Without:
  -Npcap
```
Notice the explicit runtime diagnostic:
```text
 Without:
  -Npcap
```

---

## 3. Real Execution Attempts & Verbatim Outputs

### 3.1 Interface Enumeration (`tshark -D`)
Command executed:
```powershell
& "C:\Program Files\Wireshark\tshark.exe" -D
```
Exit code: `1`  
Output:
```text
tshark: Unable to load Npcap (wpcap.dll); you will not be able to
capture packets.

In order to capture packets Npcap must be installed. See

        https://npcap.com/

for a downloadable version of Npcap and for instructions on how to
install it.
1. ciscodump (Cisco remote capture)
2. sshdump (SSH remote capture)
3. udpdump (UDP Listener remote capture)
4. wifidump (Wi-Fi remote capture)
```

### 3.2 Capture Attempt on Interface 1 (`tshark -i 1 -a duration:1`)
Command executed:
```powershell
& "C:\Program Files\Wireshark\tshark.exe" -i 1 -a duration:1
```
Exit code: `1`  
Output:
```text
Capturing on 'Cisco remote capture'
tshark: Error from extcap pipe:  ** (ciscodump:10432) 02:41:44.289314 [ciscodump WARNING] C:\gitlab-builds\builds\cyI2ZH7yy\0\wireshark\wireshark\extcap\ciscodump.c:2512 -- real_main(): Missing parameter: --remote-host

0 packets captured
```

### 3.3 Capture Attempt on Interface `eth0` (`tshark -i eth0 -a duration:1`)
Command executed:
```powershell
& "C:\Program Files\Wireshark\tshark.exe" -i eth0 -a duration:1
```
Exit code: `1`  
Output:
```text
Capturing on 'eth0'
tshark: The capture session could not be initiated on capture device "eth0".
(unable to load Npcap (wpcap.dll); can't open eth0 to capture)
In order to capture packets, Npcap must be installed. See

        https://npcap.com/

for a downloadable version of Npcap and for instructions on how to
install it.
0 packets captured
```

---

## 4. Subsystem Wiring & JARVIS Codebase Probe

### 4.1 Invocation with Labs Disabled
When called through `jarvis.security.scanner.PacketCapture` with default configuration:
```powershell
.venv\Scripts\python -c "from jarvis.security.scanner import PacketCapture, resolve_tshark_binary; print('Resolved binary:', resolve_tshark_binary()); pc = PacketCapture(); res = pc.capture_packets(interface='eth0', count=10); print('Result:', res)"
```
Output:
```text
Resolved binary: C:\Program Files\Wireshark\tshark.exe
Blocked execution of Labs feature 'tshark_capture' (capture_packets): Labs flag disabled.
Result: ActionResult(
    action_name='capture_packets',
    success=False,
    status=<ActionStatus.LABS_DISABLED: 'LABS_DISABLED'>,
    code='LABS_FEATURE_DISABLED',
    message="Action 'capture_packets' requires Labs feature 'tshark_capture' to be enabled in configuration.",
    retryable=False,
    data={'feature_name': 'tshark_capture', 'status': 'LABS_DISABLED', 'reason': 'Feature flag not enabled in configuration'}
)
```
Proves Core/Labs gating works cleanly.

### 4.2 Invocation with Labs Enabled
When called with `config={'labs': {'enabled': True, 'features': ['tshark_capture']}}`:
```powershell
.venv\Scripts\python -c "from jarvis.security.scanner import PacketCapture, resolve_tshark_binary; pc = PacketCapture(config={'labs': {'enabled': True, 'features': ['tshark_capture']}}); res = pc.capture_packets(interface='eth0', count=10); print('Result:', res)"
```
Output:
```text
WARNING  jarvis.security.scanner:scanner.py:734 TShark capture exited with non-zero code 1 (stderr: Capturing on 'eth0'
tshark: The capture session could not be initiated on capture device "eth0".
(unable to load Npcap (wpcap.dll); can't open eth0 to capture)
In order to capture packets, Npcap must )
Result: PacketCaptureResult(
    interface='eth0',
    packet_count=0,
    duration_s=0.6939480304718018,
    protocols={},
    top_talkers=[],
    anomalies_detected=0,
    anomalies=[],
    pcap_path=None,
    status='NO_TSHARK_OUTPUT',
    error_message=None
)
```

---

## 5. Unit Test Suite Isolation Fix

### Root Cause
`tests/test_security_scanner.py:178` previously only patched `shutil.which` to return `None`:
```python
monkeypatch.setattr(shutil, "which", lambda cmd: None)
```
Because `resolve_tshark_binary()` also probes `C:\Program Files\Wireshark\tshark.exe`, installing Wireshark broke test isolation: the unit test found the physical binary on disk and attempted live execution, returning `NO_TSHARK_OUTPUT` instead of `TOOL_NOT_FOUND`.

### Fix Applied
Updated `tests/test_security_scanner.py:178`:
```python
monkeypatch.setattr(shutil, "which", lambda cmd: None)
monkeypatch.setattr("jarvis.security.scanner.resolve_tshark_binary", lambda *a, **kw: None)
```

### Verification
- `pytest tests/test_security_scanner.py -v` -> **45 passed in 0.37s** (100% pass)
- `pytest tests/unit/test_packet_capture_truthfulness.py -v` -> **18 passed in 0.44s** (100% pass)

---

## 6. Remediation Steps to Reach `PASS runtime`

To achieve full `PASS runtime` packet capture on Windows:
1. **Npcap Driver Installation**:
   - Download Npcap installer from `https://npcap.com/#download` (e.g. `npcap-1.80.exe`).
   - Run installer with Administrator privileges (interactive UAC confirmation required).
   - Check "Support raw 802.11 traffic" and "Install Npcap in WinPcap API-compatible Mode".
2. **Interface Resolution**:
   - Query available adapter names via `tshark -D`.
   - Select the active network adapter GUID (e.g. `\Device\NPF_{GUID}`) or integer index rather than POSIX `"eth0"`.
3. **Execution**:
   - Run `PacketCapture(config=...).capture_packets(interface="<NPF_GUID>", count=50)`.
   - Verify `packet_count > 0` and `status == "SUCCESS"`.

---

## 7. Audit Verdict

| Gate Requirement | Evaluated Status | Evidence Level | Rationale |
|---|---|---|---|
| **R11: TShark Live Capture** | **`HARDWARE_BLOCKED (KERNEL_DRIVER_PENDING)`** | Real Subprocess Execution (Exit code 1) | TShark executable present at `C:\Program Files\Wireshark\tshark.exe`. Packet capture fail-closed due to uninstalled Npcap driver (`wpcap.dll`). Zero synthetic data generated. |
