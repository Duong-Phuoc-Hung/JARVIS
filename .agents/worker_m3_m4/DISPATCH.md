## 2026-09-02T07:44:40Z
You are Worker M3 & M4 for JARVIS Sprint 2 (v4.7.0).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m3_m4`
Mandatory source of truth: `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md`
Project scope: `d:\Software GitCode\JARVIS\PROJECT.md`
Survey Reports: `d:\Software GitCode\JARVIS\.agents\explorer_survey_audio_tts\handoff.md`, `d:\Software GitCode\JARVIS\.agents\explorer_survey_ui_hardware_eval\handoff.md`

Exclusively owned files:
- `jarvis/stt/engine.py`
- `jarvis/ui/tray.py`
- `jarvis/ui/overlay.py`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A forensic auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Tasks:
1. R3 (Faster-Whisper Pre-loading & VAD Trimming):
   - In `jarvis/stt/engine.py`: In `FasterWhisperSTT.__init__()`, spawn a background daemon thread to pre-load `WhisperModel`. Ensure thread-safe synchronization in `_get_model()`.
   - In `FasterWhisperSTT.transcribe()`: Pass `vad_filter=True` and `vad_parameters={"min_silence_duration_ms": 500}` to `model.transcribe()`.
2. R4 (HUD Overlay Thread Isolation & System Tray Status):
   - In `jarvis/ui/tray.py`: Add `from pathlib import Path` to resolve NameError in `_on_view_logs`. Add dynamic "Status" menu item displaying: version (`v4.7.0`), TTS status, STT model readiness, and RAM usage. Ensure menu has >=4 items and is callable without crashing.
   - In `jarvis/ui/overlay.py`: Verify thread isolation and `_schedule()` / `root.after(0, fn)` marshaling.
3. Build and test verification:
   - Run: `pytest tests/unit/test_stt_engine.py tests/unit/test_stt_preload.py tests/unit/test_ui_dashboard.py tests/unit/test_tray_menu.py -v`
   - Ensure all pass with 0 failures.

Write handoff report to `d:\Software GitCode\JARVIS\.agents\worker_m3_m4\handoff.md`.
Maintain `progress.md` in your working directory.
When complete, notify parent orchestrator via send_message.
