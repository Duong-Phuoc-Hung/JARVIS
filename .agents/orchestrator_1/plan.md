# Plan: JARVIS Sprint 2 (v4.7.0) - P1 Accuracy, Acoustic & UX Hardening

## Overview
Implement requirements R1 through R6 according to `ORIGINAL_REQUEST.md` and `docs/ROADMAP.md`:
- R1: DSP Acoustic Hardening (VAD filter, Echo cancellation mute 2.5s, SFM/ZCR thresholds)
- R2: SAPI5 TTS COM Safety (CoInitialize/CoUninitialize on daemon worker thread)
- R3: Faster-Whisper Pre-loading & VAD Trim (Eager background load, vad_filter=True, cold-start latency)
- R4: HUD Overlay Non-blocking & System Tray (Dedicated thread/after callbacks, Status tray item)
- R5: Hardware Voice Reporting (CPU/RAM/GPU voice summary, 5 router rules for system_status)
- R6: Test Suite Integrity, CHANGELOG, Version Bump to 4.7.0, Git Commit & Push

## Workflow & Milestones
- **Survey Phase**: 3 Explorers (including spec mining) to survey codebase structure, test harnesses, existing implementations, and potential integration points.
- **Decomposition**: Finalize `PROJECT.md` with Feature Inventory, Milestones M1-M6, and Interface Contracts.
- **Dual Track Execution**:
  - **E2E Testing Track**: Build comprehensive test harnesses (`tests/unit/test_acoustic_hardening.py`, `test_tts_com_safety.py`, `test_stt_preload.py`, `test_tray_menu.py`, etc.).
  - **Implementation Track**: Implement fixes for M1 to M5 through the Explorer -> Worker -> Reviewer -> Challenger -> Auditor loop.
- **Final Verification**:
  - Run full test suite (`pytest tests/unit/ tests/test_adversarial_*.py -q` -> 0 failures)
  - Run evaluation (`python tests/eval/routing_eval_n150.py` -> SILENT <= 5%, MISROUTED = 0)
  - Forensic integrity audit (CLEAN)
- **Release**: Update `CHANGELOG.md`, bump `__version__ = "4.7.0"` in `jarvis/__init__.py`, git commit & push.
