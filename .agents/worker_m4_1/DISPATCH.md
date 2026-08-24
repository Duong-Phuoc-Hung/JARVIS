## 2026-08-22T04:34:05Z
You are the Worker for Milestone 4 (Hardware Diagnostics, Self-Healing & Security Tooling).
Working directory: d:/Software GitCode/JARVIS/.agents/worker_m4_1

Read the following documents before starting work:
- Authoritative user request: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md
- Global project architecture: d:/Software GitCode/JARVIS/PROJECT.md
- Milestone 4 Scope: d:/Software GitCode/JARVIS/.agents/sub_orch_m4/SCOPE.md
- Explorer 1 Report (Hardware): d:/Software GitCode/JARVIS/.agents/explorer_m4_1/report.md
- Explorer 2 Report (Self-Healing): d:/Software GitCode/JARVIS/.agents/explorer_m4_2/report.md
- Explorer 3 Report (Security & Tests): d:/Software GitCode/JARVIS/.agents/explorer_m4_3/report.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Exclusive File Write Ownership:
- `jarvis/hardware/monitor.py`
- `jarvis/hardware/reporter.py`
- `jarvis/hardware/__init__.py`
- `jarvis/healing/watchdog.py`
- `jarvis/healing/terminator.py`
- `jarvis/healing/__init__.py`
- `jarvis/security/scanner.py`
- `jarvis/security/report.py`
- `jarvis/security/__init__.py`
- `tests/test_hardware_monitor.py`
- `tests/test_self_healing.py`
- `tests/test_security_scanner.py`

Key Requirements to Implement:
1. `jarvis/hardware/`:
   - `HardwareMonitor` (F-20, F-21): CPU/GPU load & temp, RAM/VRAM, fans via zero-dependency ctypes kernel32 fallbacks and non-elevated PowerShell CIM / WMI / nvidia-smi / psutil if available. S.M.A.R.T. disk health prober, disk partitions, failure prediction status.
   - `HardwareReporter` (F-22): Vocal alerts with cooldown debouncing when thresholds are breached, natural language generation in Vietnamese and English for "tình trạng hệ thống?".
2. `jarvis/healing/`:
   - `ResourceWatchdog` (F-41): RAM > 90% monitoring, CPU saturation, thread heartbeats.
   - `UnresponsiveAppDetector` (F-42): Win32 `IsHungAppWindow()` detection of frozen UI processes via ctypes user32.
   - `AutonomousTerminator` (F-43): OS-critical process whitelist protection (System, csrss.exe, wininit.exe, services.exe, lsass.exe, smss.exe, explorer.exe, dwm.exe, winlogon.exe, svchost.exe, jarvis.exe, python.exe, self-PID), 2-phase safe termination (WM_CLOSE / SIGTERM -> TerminateProcess / SIGKILL), voice healing report ("Hệ thống bị quá tải. Đã xử lý...").
3. `jarvis/security/`:
   - `NetworkScanner` (F-23) & `PacketCapture` (F-24): Nmap & TShark subprocess wrappers, port scanning, vuln scripts, packet capture with durations & filters, graceful degradation on missing binaries without unhandled exceptions.
   - `SecurityReportGenerator` (F-25): Markdown vulnerability assessment, severity categorization (Critical, High, Medium, Low), spoken Vietnamese/English executive summaries.
   - Biometric Privilege Gating (R12): Check `RequesterContext` / `SecurityContext` / `PrivilegeLevel.ADMIN` before performing intrusive network scans or captures.
4. Comprehensive Test Suite:
   - `tests/test_hardware_monitor.py`
   - `tests/test_self_healing.py`
   - `tests/test_security_scanner.py`
   - Test both real and mocked Win32/CIM/Subprocess environments.
   - Ensure all existing tests in `tests/` and new tests pass cleanly with `d:/Software GitCode/JARVIS/.venv/Scripts/pytest`.

When complete, write your full report to `d:/Software GitCode/JARVIS/.agents/worker_m4_1/report.md` and deliver `handoff.md`. Include test execution commands and exact outputs.
