# Real Runtime Evidence Report: TShark Packet Capture v2 (R15 / R11)

**Standard**: `AGENTS.md §2` (Anti-Fabrication Principle) & `AUDIT_FRAMEWORK.md` (Fail-Closed & Runtime Verification)  
**Date of Audit**: 2026-09-17 (UTC: 2026-09-17T20:51:05.613357+00:00)  
**Subsystem**: `jarvis.security.scanner.PacketCapture` & `jarvis.security.scanner.resolve_tshark_binary`  
**Host Target**: Windows 11 x64, Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz  
**Auditor**: Worker 1 (`teamwork_preview_worker_m1_infra`)  
**Gate Status**: `HARDWARE_BLOCKED (UAC_REQUIRED)`  

---

## 1. Executive Summary

Requirement **R15** mandates an empirical runtime probe evaluation of the Wireshark / TShark packet capture subsystem and an attempt to verify / install the Npcap kernel driver.

### Key Findings
1. **Wireshark / TShark Binary Discovery**:
   - Location: `C:\Program Files\Wireshark\tshark.exe` is **present** and functional on disk.
   - Invocation `tshark.exe --version` exited with code `0`.
2. **Npcap Driver Absence**:
   - `C:\Windows\System32\drivers\npcap.sys`: **`False`** (File not found).
   - `C:\Windows\System32\wpcap.dll`: **`False`** (File not found).
   - `tshark.exe --version` explicitly reports runtime constraint:
     ```text
     Without:
       -Npcap
     ```
3. **Interface Enumeration Failure**:
   - Executing `tshark.exe -D` exited with code `13` and emitted:
     ```text
     tshark: Unable to load Npcap (wpcap.dll); you will not be able to capture packets.
     In order to capture packets Npcap must be installed. See https://npcap.com/
     ```
4. **PacketCapture Subsystem Execution**:
   - In `jarvis/security/scanner.py`, `PacketCapture.capture_packets()` executed against interface `1`.
   - Exit code: `13`.
   - Status returned: `NO_TSHARK_OUTPUT`.
   - Packet count: `0`.
   - Zero synthetic packets generated.
5. **Winget & UAC Elevation Barrier**:
   - `winget.exe` is available (`version v1.29.360`).
   - While `winget install WiresharkFoundation.Wireshark` was previously completed in userspace, installing the Npcap packet filter driver (`winget install Npcap.Npcap`) requires Windows Administrator UAC interactive elevation to register `npcap.sys` into the Windows kernel driver store (`sc start npcap`).
   - Headless / non-interactive agent execution cannot approve the OS-level UAC elevation prompt.

---

## 2. Verbatim Command Outputs

### 2.1 `tshark.exe --version`
- **Command**: `& "C:\Program Files\Wireshark\tshark.exe" --version`
- **Exit Code**: `0`
- **Output Snippet**:
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

### 2.2 `tshark.exe -D`
- **Command**: `& "C:\Program Files\Wireshark\tshark.exe" -D`
- **Exit Code**: `13`
- **Output**:
```text
1. ciscodump (Cisco remote capture)
2. sshdump (SSH remote capture)
3. udpdump (UDP Listener remote capture)
4. wifidump (Wi-Fi remote capture)
tshark: Unable to load Npcap (wpcap.dll); you will not be able to
capture packets.

In order to capture packets Npcap must be installed. See

        https://npcap.com/

for a downloadable version of Npcap and for instructions on how to
install it.
```

### 2.3 `PacketCapture.capture_packets()` Runtime Result
- **Status**: `NO_TSHARK_OUTPUT`
- **Packet Count**: `0`
- **Duration**: `0.67s`
- **Protocols**: `{}`

---

## 3. Classification & Remediation

- **Three-Tier Verdict**: **`HARDWARE_BLOCKED (UAC_REQUIRED)`** (Cannot be promoted to `PASS runtime` until real packets are captured on a physical NIC).
- **Remediation**:
  1. Open an elevated Administrator PowerShell prompt:
     ```powershell
     Start-Process powershell -Verb runAs
     ```
  2. Execute Npcap installation:
     ```powershell
     winget install Npcap.Npcap --accept-source-agreements --accept-package-agreements
     ```
     Or manually download and install with WinPcap-compatible mode enabled from:
     `https://npcap.com/#download`
  3. Verify `npcap.sys` is running: `Get-Service npcap`
