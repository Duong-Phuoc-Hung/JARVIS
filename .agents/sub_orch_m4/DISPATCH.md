## 2026-08-22T04:28:02Z
You are the Sub-Orchestrator for Milestone 4: Hardware Diagnostics, Self-Healing & Security Tooling.
Your working directory is: d:/Software GitCode/JARVIS/.agents/sub_orch_m4
Project Scope & Global Architecture: d:/Software GitCode/JARVIS/PROJECT.md
E2E Test Infrastructure & Test Ready Specs: d:/Software GitCode/JARVIS/TEST_INFRA.md, d:/Software GitCode/JARVIS/TEST_READY.md
Authoritative User Request: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md
Python virtualenv: d:/Software GitCode/JARVIS/.venv

Your Scope:
Implement Milestone 4 features:
- F-20: Hardware Telemetry Collector (`jarvis/hardware/monitor.py`: CPU/GPU load & temp, RAM/VRAM, fans via PowerShell CIM / WMI / psutil / zero-dependency fallbacks).
- F-21: S.M.A.R.T. Disk Health Prober (`jarvis/hardware/monitor.py`: S.M.A.R.T. attributes, disk partitions).
- F-22: Hardware Voice Alerts & Query (`jarvis/hardware/reporter.py`: vocal alerts when thresholds breached, answers "tình trạng hệ thống?" via TTS).
- F-41: Process & Resource Watchdog (`jarvis/healing/watchdog.py`: RAM > 90% monitoring, CPU saturation).
- F-42: Unresponsive App Detector (`jarvis/healing/watchdog.py`: Win32 `IsHungAppWindow()` detection of frozen Chrome/VMware/apps).
- F-43: Autonomous Healing Protocol (`jarvis/healing/terminator.py`: safe process termination with critical OS whitelist, voice healing report "Hệ thống bị quá tải. Đã xử lý...").
- F-23: Network Scanner Wrapper (`jarvis/security/scanner.py`: Nmap subprocess wrapper, port scans, vuln audits, graceful handling if not in PATH).
- F-24: Packet Capture Wrapper (`jarvis/security/scanner.py`: TShark/Wireshark subprocess wrapper).
- F-25: Security Risk Report Generator (`jarvis/security/report.py`: Markdown vulnerability assessment & spoken briefing).
- Gating: Security tools MUST require biometric privilege check (R12 / `SecurityContext.is_biometric_authenticated()`).
- Tests: `tests/test_hardware_monitor.py`, `tests/test_self_healing.py`, `tests/test_security_scanner.py`.

You must follow the sub-orchestrator procedure:
1. Assess scope, write `SCOPE.md` and `BRIEFING.md` in your working directory.
2. Run iteration loop:
   a. Dispatch Explorer(s) for technical blueprint.
   b. Dispatch Worker with MANDATORY INTEGRITY WARNING to implement code and unit tests.
   c. Dispatch 2 Reviewers independently.
   d. Dispatch 2 Challengers.
   e. Dispatch Forensic Auditor (`teamwork_preview_auditor`).
   f. Gate: Check all pass criteria (Reviewers APPROVE, Challengers confirm, Auditor CLEAN, tests pass).
3. Report final completion with verified test results to parent orchestrator.
