# DISPATCH: Reviewer 1

Workspace: `d:\Software GitCode\JARVIS`
Your working directory: `d:\Software GitCode\JARVIS\.agents\reviewer_1`
Mandatory source of truth: `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md`
Project scope: `d:\Software GitCode\JARVIS\PROJECT.md`
Test Readiness: `d:\Software GitCode\JARVIS\TEST_READY.md`

Objective:
Perform comprehensive, independent code and quality review across all Sprint 2 deliverables (R1 to R6):
1. R1: `jarvis/audio/wake_word.py`, `jarvis/core/app.py` — VAD pre-filter gate, 2.5s post-TTS echo mic suppression, SFM/ZCR bounds.
2. R2: `jarvis/tts/manager.py`, `jarvis/tts/fallback.py` — COM CoInitialize/CoUninitialize thread safety.
3. R3: `jarvis/stt/engine.py` — Faster-Whisper background eager preloading and vad_filter=True.
4. R4: `jarvis/ui/overlay.py`, `jarvis/ui/tray.py` — HUD overlay thread safety, System Tray "Status" menu item, Path import fix.
5. R5: `jarvis/hardware/reporter.py`, `jarvis/llm/router.py`, `jarvis/vision/dialog_detector.py` — GPU temp voice reporting, 5 hardware intent routing rules (MISROUTED=0), adversarial bug fixes.
6. Run all acceptance tests, full unit tests, adversarial tests, and routing eval:
   - `pytest tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py tests/unit/test_stt_preload.py tests/unit/test_tray_menu.py tests/unit/test_router_hardware.py -v`
   - `pytest tests/unit/ tests/test_adversarial_*.py -q`
   - `python tests/eval/routing_eval_n150.py`

Evaluate verdict: APPROVE or REQUEST_CHANGES.
Write handoff report to `d:\Software GitCode\JARVIS\.agents\reviewer_1\handoff.md`.
