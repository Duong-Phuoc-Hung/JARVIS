# PROTOCOL: ACCEPTANCE GATES CLOSURE (v5.2.1+)
# Verification checklist and automated execution protocol for Phase P3 / Release Go

## 1. Live Voice 50 Cases Protocol (Tiếng Việt)
File: `tools/live_wake_word_acceptance.py` & `scripts/run_voice_acceptance_50.py`
Objective: Test 50 distinct colloquial Vietnamese voice commands across 5 categories:
- System & Audio: 10 queries ("tắt tiếng", "tăng âm lượng", "khóa màn hình", "báo cáo hệ thống"...)
- Application Launch: 10 queries ("mở notepad", "mở chrome", "mở calculator"...)
- Web Intelligence: 10 queries ("thời tiết hôm nay", "tìm kiếm tin tức"...)
- Smart Home / IoT: 10 queries ("bật đèn phòng khách", "tắt điều hòa"...)
- Automation & Media: 10 queries ("chụp màn hình", "phát nhạc"...)

Pass Criteria:
- STT Accuracy >= 95% (>= 48/50 recognized correctly)
- Intent Routing Accuracy >= 96% (>= 48/50 routed to valid action)
- False Alarm Ambient Soak: >= 120s with 0 false-triggers

Execution Command:
```powershell
python tools/live_wake_word_acceptance.py --trials 10 --ambient-seconds 120
python -m pytest tests/unit/test_h05_vietnamese_regression_contract.py tests/unit/test_h07_voice_app_intents.py -v
```

## 2. 10-Workflow Real OS Execution Matrix
File: `scripts/run_10_workflow_real_os.py`
Objective: Validate 10 core autonomous desktop workflows on live Windows kernel:
1. `WF-01`: Desktop System Diagnostic & Metrics Gathering
2. `WF-02`: Multi-Monitor Window Layout & Placement
3. `WF-03`: Clean Text Note Taking & File Persistence
4. `WF-04`: Safe Web Research & Weather Parsing
5. `WF-05`: Controlled Process Termination (Self-Healing)
6. `WF-06`: Browser Navigation & Playwright DOM Extraction
7. `WF-07`: Local App Catalog Lookup & Window Verification
8. `WF-08`: Clipboard Inspection & Sanitized Transform
9. `WF-09`: Smart Home Entity Telemetry Query
10. `WF-10`: Security Scanner Audit & Local Port Verification

Pass Criteria:
- 10/10 workflows return `status="COMPLETED"` with truthful non-mock evidence.
- Zero simulated fallbacks (`simulated: True`).
- All file writes bounded to workspace.

Execution Command:
```powershell
python scripts/run_10_workflow_real_os.py --mode live --report-dir reports/evidence/real_os/
```

## 3. Clean-Machine Deployment & Rollback Gate
File: `scripts/build_installer.py` & `installer/setup.iss`
Objective: Validate installation on pristine Windows VM without Python/Git pre-installed.

Checklist:
- [ ] Build standalone installer: `python scripts/build_installer.py --all`
- [ ] Check output size and Authenticode signature: `dist/installer/JARVIS_Setup_v5.2.1.exe`
- [ ] Run silent installer on clean VM: `JARVIS_Setup_v5.2.1.exe /VERYSILENT /SUPPRESSMSGBOXES`
- [ ] Verify registry autostart key: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\JARVIS`
- [ ] Verify startup health banner: `jarvis --version` outputs `5.2.1`
- [ ] Execute uninstaller: `unins000.exe /VERYSILENT`
- [ ] Verify 100% cleanup of AppData/Local/JARVIS without orphaned processes.
