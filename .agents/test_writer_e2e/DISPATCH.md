## 2026-09-02T07:44:40Z
You are the E2E Test Suite Writer for JARVIS Sprint 2 (v4.7.0).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\test_writer_e2e`
Mandatory source of truth: `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md`
Project scope: `d:\Software GitCode\JARVIS\PROJECT.md`
Spec findings: `d:\Software GitCode\JARVIS\.agents\spec_miner_survey_1\handoff.md`

Your objective is to design and write the complete test suite for Sprint 2 acceptance criteria:
1. `tests/unit/test_acoustic_hardening.py` (>=5 tests):
   - VAD filter frame discard for silent frames
   - VAD speech frame pass-through
   - 2.5s post-TTS microphone suppression (mic blocks dropped during and 2.5s after TTS)
   - Sliding ring buffer clearing on suppression
   - SFM and ZCR thresholds and bounds verification
2. `tests/unit/test_tts_com_safety.py` (>=3 tests):
   - pythoncom.CoInitialize() and CoUninitialize() called in worker thread lifecycle
   - 10 consecutive TTS calls in daemon thread without COM errors
   - SAPI5 fallback error handling and COM uninitialization in finally block
3. `tests/unit/test_stt_preload.py` (>=3 tests):
   - FasterWhisperSTT.__init__() starts model preloading in background thread
   - FasterWhisperSTT.transcribe() configures vad_filter=True and vad_parameters
   - Warm model transcription latency validation
4. `tests/unit/test_tray_menu.py` (>=3 tests):
   - System tray menu contains >=4 items including "Status"
   - "Status" item displays version (v4.7.0), TTS status, STT model readiness, RAM usage
   - Safe Path import in _on_view_logs
5. `tests/unit/test_router_hardware.py` (>=5 tests):
   - 5 hardware query utterances ("cpu mấy phần trăm", "ram còn bao nhiêu", "nhiệt độ máy", "pin còn bao nhiêu", "tốc độ cpu") route to system_status / hardware_telemetry_check with MISROUTED=0
   - format_voice_summary() returns valid Vietnamese string with CPU%, RAM%, GPU temp
6. Create `TEST_INFRA.md` and `TEST_READY.md` at project root (`d:\Software GitCode\JARVIS\`).

Run pytest on the test files to verify they are syntactically sound and valid test structures.
Write your handoff report to `d:\Software GitCode\JARVIS\.agents\test_writer_e2e\handoff.md`.
Maintain `progress.md` in your working directory.
When complete, notify parent orchestrator via send_message.
