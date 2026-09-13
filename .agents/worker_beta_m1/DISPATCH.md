## 2026-09-13T10:42:38Z
You are Worker M1 for the JARVIS Beta v1 project.

Your working directory is: d:\Software GitCode\JARVIS\.agents\worker_beta_m1
Your parent is: fcbdbddb-159a-4432-af21-f3ef3e4e8c4e (Project Orchestrator)

Authoritative User Request: d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md (You MUST read this file first).
Scope Document: d:\Software GitCode\JARVIS\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Write Ownership (You exclusively own these files for this milestone):
- d:\Software GitCode\JARVIS\jarvis\core\app.py
- d:\Software GitCode\JARVIS\jarvis\comms\zalo.py
- d:\Software GitCode\JARVIS\tests\unit\test_voice_pipeline_fixes.py
- d:\Software GitCode\JARVIS\tests\unit\test_zalo_bot.py

Objectives:
1. Fix H-01 Sample Rate Configuration Precedence in `jarvis/core/app.py`:
   - At line 1738, `record_audio()` currently does:
     `sr = int(sample_rate or self.config.get("audio.sample_rate", 16000))`
   - Because `config/default_config.yaml` defines `audio.sample_rate: 44100`, this evaluates to 44100 in production, causing 44.1kHz capture instead of 16kHz for Whisper STT models.
   - Fix: Decouple STT capture sample rate so it defaults to 16000 unless `stt.sample_rate` or explicit `sample_rate` parameter is given, e.g.:
     `sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))`
   - Verify on runtime: `python -c "from jarvis.core.app import JarvisApp; app = JarvisApp(headless=True); app.initialize(); arr = app.record_audio(duration_s=1.0); print(len(arr))"` outputs 1600 (at 0.1s headless duration, corresponding to 16000 Hz) instead of 4410.
   - Add a test in `tests/unit/test_voice_pipeline_fixes.py` proving that even when `app.config["audio.sample_rate"] == 44100`, `record_audio()` still requests 16000 Hz from sounddevice.

2. Fix Zalo OA `send_image()` Fail-Closed Defect in `jarvis/comms/zalo.py`:
   - At line 340-346, `send_image()` currently returns `ZaloSendResult(success=True, message_id="img_not_implemented")` when unconfigured!
   - Fix: Check `if not self.config.access_token:` (and when not mock), return `ZaloSendResult(success=False, error="NOT_CONFIGURED")`.
   - Add a test in `tests/unit/test_zalo_bot.py` verifying that calling `send_image()` without access_token returns `success=False` and `error="NOT_CONFIGURED"`.

3. Verification:
   - Run `pytest tests/unit/test_voice_pipeline_fixes.py -v` (must pass 100%).
   - Run `pytest tests/unit/test_zalo_bot.py -v` (must pass 100%).
   - Run `pytest tests/test_comms_hub.py -v` (must pass 100%).

4. Output:
   - Write your implementation report and test logs to `d:\Software GitCode\JARVIS\.agents\worker_beta_m1\handoff.md`.
   - Send a message to parent (fcbdbddb-159a-4432-af21-f3ef3e4e8c4e) with your completion summary.
