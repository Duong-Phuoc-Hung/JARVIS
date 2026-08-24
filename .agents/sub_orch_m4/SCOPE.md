# Scope: Milestone 4 — Hardware Diagnostics, Self-Healing & Security Tooling

## Architecture & Modules
Milestone 4 delivers autonomous diagnostic, recovery, and security capabilities for JARVIS on Windows 11:
1. `jarvis/hardware/monitor.py`:
   - `HardwareMonitor`: CPU/GPU load & temp, RAM/VRAM, fans via PowerShell CIM / WMI / psutil / fallback.
   - S.M.A.R.T. Disk Health Prober: S.M.A.R.T. attributes, disk partitions, temperature, health status.
2. `jarvis/hardware/reporter.py`:
   - `HardwareReporter`: Vocal alerts when thresholds breached, answers Vietnamese/English voice queries ("tình trạng hệ thống?", "nhiệt độ CPU thế nào?"), generates structured status telemetry.
3. `jarvis/healing/watchdog.py`:
   - `ResourceWatchdog`: Continuous monitoring of RAM (>90%), CPU saturation, background task thread health.
   - `UnresponsiveAppDetector`: Win32 `IsHungAppWindow()` API detection of frozen foreground/background processes (Chrome, VMware, IDE, etc.).
4. `jarvis/healing/terminator.py`:
   - `AutonomousTerminator`: Safe termination protocol with OS-critical whitelist (System, csrss.exe, wininit.exe, services.exe, lsass.exe, smss.exe, explorer.exe, dwm.exe), memory reclamation, voice healing report ("Hệ thống bị quá tải. Đã xử lý...").
5. `jarvis/security/scanner.py`:
   - `NetworkScanner`: Nmap subprocess wrapper, port scans, vulnerability script audits, graceful degradation when Nmap binary not found.
   - `PacketCapture`: TShark/Wireshark subprocess wrapper with capture duration, packet filters, PCAP file writing, graceful degradation if tshark not found.
6. `jarvis/security/report.py`:
   - `SecurityReportGenerator`: Markdown report generator, risk ranking (Critical/High/Medium/Low), spoken Vietnamese/English executive briefing.
   - `SecurityContext` / Privilege Enforcement: Biometric gating check (`SecurityContext.is_biometric_authenticated()` / R12 check before running intrusive/security scans).

## Feature Inventory
| # | Feature | Description | Target Module |
|---|---------|-------------|---------------|
| F-20 | Hardware Telemetry Collector | CPU/GPU load, temp, RAM/VRAM, fans via PowerShell CIM/WMI/psutil | `jarvis/hardware/monitor.py` |
| F-21 | S.M.A.R.T. Disk Health Prober | Disk partitions, health status, SMART telemetry | `jarvis/hardware/monitor.py` |
| F-22 | Hardware Voice Alerts & Query | Vocal alerts on threshold breach, TTS queries ("tình trạng hệ thống?") | `jarvis/hardware/reporter.py` |
| F-41 | Process & Resource Watchdog | RAM >90%, CPU saturation detection | `jarvis/healing/watchdog.py` |
| F-42 | Unresponsive App Detector | Win32 `IsHungAppWindow()` detection of frozen apps | `jarvis/healing/watchdog.py` |
| F-43 | Autonomous Healing Protocol | Safe process kill, OS whitelist protection, voice healing report | `jarvis/healing/terminator.py` |
| F-23 | Network Scanner Wrapper | Nmap subprocess wrapper, port/vuln scan, missing-binary fallback | `jarvis/security/scanner.py` |
| F-24 | Packet Capture Wrapper | TShark subprocess wrapper, packet filters, PCAP handling | `jarvis/security/scanner.py` |
| F-25 | Security Risk Report Generator | Markdown vulnerability report, spoken briefing, biometric gate (R12) | `jarvis/security/report.py` |

## Test Plan
- `tests/test_hardware_monitor.py`: Mocked and live hardware queries, CIM/psutil fallbacks, SMART disk checks, reporter alert logic.
- `tests/test_self_healing.py`: Watchdog threshold triggers, `IsHungAppWindow` detection logic, OS whitelist enforcement, safe termination, voice healing logs.
- `tests/test_security_scanner.py`: Biometric authentication gate enforcement, Nmap & TShark subprocess handling with mocks, missing tool fallbacks, markdown & voice report generation.
