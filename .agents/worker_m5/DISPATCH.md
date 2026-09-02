## 2026-09-02T07:44:40Z

You are Worker M5 for JARVIS Sprint 2 (v4.7.0).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m5`
Mandatory source of truth: `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md`
Project scope: `d:\Software GitCode\JARVIS\PROJECT.md`
Survey Report: `d:\Software GitCode\JARVIS\.agents\explorer_survey_ui_hardware_eval\handoff.md`

Exclusively owned files:
- `jarvis/hardware/reporter.py`
- `jarvis/hardware/monitor.py`
- `jarvis/llm/router.py`
- `jarvis/vision/dialog_detector.py`

Tasks:
1. R5 (Hardware Voice Reporting & Intent Routing):
   - In `jarvis/hardware/reporter.py`: Update `format_voice_summary()` to format GPU temperature when `metrics.gpu_temp_c is not None` alongside CPU%, CPU temp, RAM%, and storage status.
   - In `jarvis/llm/router.py`: Add support for battery/pin in `_make_hw_intent()`, add regex patterns and static rule mappings for:
     - "cpu mấy phần trăm" -> system_status / hardware_telemetry_check (comp="cpu")
     - "ram còn bao nhiêu" -> system_status / hardware_telemetry_check (comp="ram")
     - "nhiệt độ máy" -> system_status / hardware_telemetry_check (comp="cpu")
     - "pin còn bao nhiêu" -> system_status / hardware_telemetry_check (comp="battery")
     - "tốc độ cpu" -> system_status / hardware_telemetry_check (comp="cpu")
     Ensure MISROUTED = 0 and SILENT = 0 across these queries and `routing_eval_n150.py`.
2. Fix Adversarial Test Suite Issues:
   - `jarvis/vision/dialog_detector.py:122-125`: Check critical/crash before error to preserve severity='critical'.
   - `jarvis/hardware/monitor.py:626`: Allow CRITICAL alerts to bypass warning cooldown.
   - `jarvis/llm/router.py:2152-2158`: Truncate large input strings (>512 chars) before lowercasing/regex search to keep parsing latency <1.0ms for 50KB strings.
3. Build and test verification:
   - Run: `python tests/eval/routing_eval_n150.py`
   - Run: `pytest tests/unit/test_router_hardware.py tests/test_hardware_monitor.py tests/test_adversarial_*.py -v`
   - Ensure all pass with 0 failures.
