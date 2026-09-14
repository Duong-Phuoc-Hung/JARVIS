# JARVIS Beta v1 Task Tracking & Verification Checklist

**Project**: JARVIS Voice Assistant Beta v1  
**Milestone**: M4 — Documentation Synchronization & Release Readiness  
**Target Release**: v5.1.3 (Runtime & Package) / v5.1.0 (Installer Artifact)  
**Date**: 2026-09-13  
**Integrity Policy**: `AGENTS.md` (Fail-Closed Default, Anti-Fabrication Principle)  

---

## 1. Acceptance Criteria Checklist

### 1.1 Audio Capture & Hardware Synchronization (H-01, H-02, H-03)
- [x] **16 kHz STT Boundary (H-01 / F-01)**: Capture defaults to 16 kHz and permits explicit/configured source rates. The voice loop preserves the rate with each buffer; a shared helper normalizes to 16 kHz before STT/model inference, while streaming normalizes before VAD without cumulative per-block rounding loss.
  *Evidence*: `tests/unit/test_h01_stt_boundary.py`, `tests/unit/test_voice_pipeline_fixes.py`, `tests/unit/test_adversarial_challenger_m1_sample_rate.py`.
- [x] **Microphone Device Synchronization (H-02 / F-02)**: `record_audio()` synchronizes with `AudioEngine._active_device_index` and passes `device=target_device` to `sounddevice.InputStream` and fallback `sounddevice.rec`.  
  *Evidence*: `jarvis/core/app.py:844`, `tests/unit/test_voice_pipeline_fixes.py::test_h02_record_audio_uses_audio_engine_device` (PASS).
- [x] **Acoustic Settling Delay & Playback Lockout (H-03 / F-03)**: Enforces 150ms settling sleep after TTS greeting and active playback lockout loop in `record_audio()` to prevent microphone self-capture of JARVIS voice output.  
  *Evidence*: `jarvis/core/app.py:817-826`, `tests/unit/test_voice_pipeline_fixes.py::test_h03_record_audio_waits_for_active_tts` (PASS).

### 1.2 Core Controls & Fail-Closed Hardware Handlers (H-04, H-08)
- [x] **Zero-Crash Push-To-Talk Hotkey (H-04 / F-04)**: Global hotkey `Ctrl+Shift+L` connects directly to `_start_voice_interaction(trigger_name="HOTKEY_PTT", greeting_phrase="Vâng, tôi nghe.")` without `AttributeError`.  
  *Evidence*: `jarvis/core/app.py:169`, `tests/unit/test_voice_pipeline_fixes.py::test_h04_hotkey_registration_has_valid_target` (PASS).
- [x] **Master Volume Fail-Closed on None (H-08 / F-05)**: `_handle_system_volume()` returns `{"status": "failed", "success": False, "volume": None, "error": "VOLUME_SET_FAILED"}` when hardware controller returns `None`.  
  *Evidence*: `jarvis/core/app.py:649-656`, `tests/unit/test_voice_pipeline_fixes.py::test_h08_volume_fail_closed_on_none` (PASS).
- [x] **Screen Brightness Fail-Closed on None (H-08 / F-05)**: `_handle_system_brightness()` returns `{"status": "failed", "success": False, "brightness": None, "error": "BRIGHTNESS_SET_FAILED"}` when hardware controller returns `None`.  
  *Evidence*: `jarvis/core/app.py:672-679`, `tests/unit/test_voice_pipeline_fixes.py::test_h08_brightness_fail_closed_on_none` (PASS).

### 1.3 Communications Hub Fail-Closed & Zalo Hardening (F-06, F-07, D-06..D-09)
- [x] **Zalo Token Sanitization & Fail-Closed Image Send (F-06 / D-07)**: Whitespace-only tokens stripped; returns `NOT_CONFIGURED` when unconfigured and `IMAGE_SEND_NOT_IMPLEMENTED` with HTTP 501 when non-mock token provided.  
  *Evidence*: `jarvis/comms/zalo.py:100-112`, `tests/unit/test_zalo_bot.py` (25/25 PASS), `tests/test_adversarial_beta_m1_comms_failclosed.py` (6/6 Zalo tests PASS).
- [x] **Telegram Fail-Closed (D-06)**: `send_message` and `send_photo` return `{"ok": False, "error_code": "NOT_CONFIGURED"}` when token is missing.  
  *Evidence*: `jarvis/comms/telegram.py`, `tests/test_adversarial_beta_m1_comms_failclosed.py::test_telegram_*` (2/2 PASS).
- [x] **Discord Fail-Closed (D-08)**: `send_message`, `send_file`, and `send_embed` return `{"success": False, "error_code": "NOT_CONFIGURED"}` when unconfigured.  
  *Evidence*: `jarvis/comms/discord.py`, `tests/test_adversarial_beta_m1_comms_failclosed.py::test_discord_*` (3/3 PASS).
- [x] **IMAP Email Fail-Closed (D-09)**: `connect()` raises `IMAPNotConfiguredError(NOT_CONFIGURED)` on empty credentials.  
  *Evidence*: `jarvis/comms/email_imap.py`, `tests/test_adversarial_beta_m1_comms_failclosed.py::test_imap_*` (2/2 PASS).

### 1.4 Independent STT & Router Empirical Evaluation (H-05 / A1–A4)
- [x] **Dataset Independence (A1)**: 210 distinct Vietnamese phrases synthesized into 420 audio WAV files, zero overlap with historical 90-file test set.  
  *Evidence*: `tests/eval/audio_independent/`, `tests/eval/independent_test_manifest.py`.
- [x] **Dual Acoustic Conditions (A2)**: Benchmark evaluated across both `clean` and `noisy` (SNR 10–15 dB) environments.  
  *Evidence*: `docs/eval/independent_benchmark/stt_eval_summaries_direct.json`.
- [x] **Multi-Model Comparison (A3)**: Direct benchmark comparison between Whisper `small` (~710ms latency, ~950MB VRAM) and `large-v3` (~2,732ms latency, ~3,400MB VRAM).  
  *Evidence*: `docs/eval/stt_eval_independent_summary.md §5`.
- [x] **4-Way Outcome Classification (A4)**: Transparent classification into `CORRECT`, `MISROUTED`, `STT_EMPTY`, and `ROUTER_ABSTAIN`:  
  * Clean (N=210): 61.0% CORRECT (128), 3.3% MISROUTED (7), 0.0% STT_EMPTY (0), 35.7% ROUTER_ABSTAIN (75), latency p50 710.8ms.  
  * Noisy (N=210): 53.8% CORRECT (113), 3.3% MISROUTED (7), 0.0% STT_EMPTY (0), 42.9% ROUTER_ABSTAIN (90), latency p50 706.2ms.  
  * Combined (N=420): 57.4% CORRECT (241), 3.3% MISROUTED (14), 0.0% STT_EMPTY (0), 39.3% ROUTER_ABSTAIN (165), latency p50 708.5ms.  
  *Evidence*: `docs/eval/stt_eval_independent_summary.md §2 Table 1`.
- [x] **Oracle Text Intent Routing Accuracy (H-05)**: 99.5% CORRECT (209/210), 0.0% ROUTER_ABSTAIN, 0.5% MISROUTED (1/210) on raw transcripts of 210 independent phrases.  
  *Evidence*: `tests/eval/results_oracle_router_210.json`.

### 1.5 System Durability, Packaging & Blocker Registers
- [x] **Soak Test & Leak Detection (H-09)**: Windows handles slope +0.00/hr (0 handles leaked), thread count stable at 15 threads, memory working set stable at 52.8 MB over continuous execution.  
  *Evidence*: `tests/eval/results_soak_test.json`, `tests/eval/soak_test_runner.py`.
- [x] **Windows Installer Verification (D-12)**: One-click Inno Setup installer compiled at `dist/installer/JARVIS_Setup_v5.1.0.exe` (71.4 MB) with verified SHA-256 hash `E6335E5BF7F704B0FA09E38937BA89CB668939FF9090746B45150ED722031650`.  
  *Evidence*: `dist/installer/JARVIS_Setup_v5.1.0.exe`, `docs/READINESS_DASHBOARD.md §3`.
- [x] **Blockers Register (D-06..D-09, D-14)**: Explicitly labeled `PENDING_CREDENTIALS` (Telegram, Zalo, Discord, IMAP) and `BLOCKED_ON_CERT` (Windows Authenticode code signing) without fabrication.  
  *Evidence*: `docs/READINESS_DASHBOARD.md §6`, `CHANGELOG.md §4`.

---

## 2. Test Execution Verification Matrix

| Test Suite | Command Line | Passed / Total | Status | Evidence File |
|---|---|:---:|:---:|---|
| **E2E Acceptance** | `pytest tests/e2e/test_beta_v1_acceptance.py -v` | 28 / 28 | `PASS` | `TEST_READY.md`, `tests/e2e/test_beta_v1_acceptance.py` |
| **Voice Fixes Seam** | `pytest tests/unit/test_voice_pipeline_fixes.py -v` | 8 / 8 | `PASS` | `tests/unit/test_voice_pipeline_fixes.py` |
| **Zalo Bot Seam** | `pytest tests/unit/test_zalo_bot.py -v` | 25 / 25 | `PASS` | `tests/unit/test_zalo_bot.py` |
| **Comms Fail-Closed** | `pytest tests/test_adversarial_beta_m1_comms_failclosed.py -v` | 18 / 18 | `PASS` | `tests/test_adversarial_beta_m1_comms_failclosed.py` |
| **Full Combined Seams**| `pytest tests/e2e/test_beta_v1_acceptance.py tests/unit/test_voice_pipeline_fixes.py tests/unit/test_zalo_bot.py tests/test_adversarial_beta_m1_comms_failclosed.py -v` | **79 / 79** | `PASS` | All above files |

---

## 3. Documentation Synchronization Status

| Document | Purpose | Target Version | Compliance Status |
|---|---|:---:|:---:|
| `docs/READINESS_DASHBOARD.md` | Master System Readiness Matrix across D-01..D-17 & H-01..H-13, benchmark results, installer hash, blockers | Beta v1 (v5.1.3) | `COMPLETE` |
| `CHANGELOG.md` | Release entry `[5.1.3]` with root causes, technical fixes, empirical benchmark, test counts, blockers | v5.1.3 | `COMPLETE` |
| `task.md` | Authoritative verification checklist matching acceptance criteria with explicit evidence paths | Beta v1 (v5.1.3) | `COMPLETE` |
| `README.md` | System overview, version bump to 5.1.3, verified test counts, installer SHA-256 | v5.1.3 | `COMPLETE` |
| `docs/ROADMAP.md` | Roadmap task status tables: D-01..D-17 (12 DONE, 4 PENDING_CREDENTIALS, 1 BLOCKED_ON_CERT), H-01..H-13 (all DONE) | v5.1.3 | `COMPLETE` |
