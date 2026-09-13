# JARVIS Testing Infrastructure & Architecture Guide

## 1. Overview
The JARVIS testing infrastructure provides deterministic, isolated, and hardware-independent verification across all subsystems of the JARVIS AI Assistant on Windows 11. Designed to enforce strict **Fail-Closed semantics**, **Zero Fabrication**, and **Anti-Ghost Success** policies, the test harness guarantees that all audio capture, hardware control, and communications features execute against real seams without silent fallbacks.

---

## 2. Multi-Tier Test Hierarchy

```
┌────────────────────────────────────────────────────────────────────────┐
│                        JARVIS Quality Gates                            │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Feature Coverage (tests/unit/, tests/e2e/)                     │
│   - Primary behavioral verification (happy paths) for every feature.   │
│   - Direct seam assertions for 16kHz capture, device sync, hotkeys.    │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Boundary & Corner Cases (tests/e2e/)                           │
│   - Extreme parameters, None inputs, hardware disconnection.           │
│   - Rate limit bounds, unauthorized user attempts, playback timeouts.  │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Cross-Component Interactions (tests/e2e/)                      │
│   - Multi-module wiring: Hotkey -> AudioEngine -> STT -> ActionRouter. │
│   - Comms multi-channel fail-closed audit across 4 independent adapters│
├────────────────────────────────────────────────────────────────────────┤
│ Tier 4: Real-World Application Workflows (tests/e2e/)                  │
│   - End-to-end user scenarios: PTT voice turnaround, hardware recovery │
│   - Alert distribution with unconfigured credential protection.        │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 5: Intent & Acoustic Evaluation (tests/eval/)                     │
│   - Multi-condition (clean/noisy) evaluation on >=200 utterances.      │
│   - 4-way outcome classification: CORRECT, MISROUTED, STT_EMPTY,       │
│     ROUTER_ABSTAIN across small and large-v3 models.                   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Feature Inventory to Test Tier Mapping

| Feature ID | Feature Name | Primary Scope | Test Tier | Primary Test File |
|---|---|---|:---:|---|
| **F-01** | 16kHz STT Capture Precedence | `jarvis/core/app.py` | Tier 1, Tier 2 | `tests/e2e/test_beta_v1_acceptance.py`<br>`tests/unit/test_voice_pipeline_fixes.py` |
| **F-02** | Microphone Device Sync | `jarvis/audio/engine.py`<br>`jarvis/core/app.py` | Tier 1, Tier 3 | `tests/e2e/test_beta_v1_acceptance.py`<br>`tests/unit/test_voice_pipeline_fixes.py` |
| **F-03** | Acoustic Settling & Echo Lockout | `jarvis/core/app.py`<br>`jarvis/tts/manager.py` | Tier 1, Tier 4 | `tests/e2e/test_beta_v1_acceptance.py`<br>`tests/unit/test_acoustic_hardening.py` |
| **F-04** | Zero-Crash Hotkeys (PTT) | `jarvis/core/app.py` | Tier 1, Tier 3 | `tests/e2e/test_beta_v1_acceptance.py`<br>`tests/unit/test_voice_pipeline_fixes.py` |
| **F-05** | Hardware Controls Fail-Closed | `jarvis/core/app.py`<br>`jarvis/automation/control.py` | Tier 1, Tier 2 | `tests/e2e/test_beta_v1_acceptance.py`<br>`tests/unit/test_voice_pipeline_fixes.py` |
| **F-06** | Zalo OA Fail-Closed Fix | `jarvis/comms/zalo.py` | Tier 1, Tier 2 | `tests/e2e/test_beta_v1_acceptance.py` |
| **F-07** | Comms `NOT_CONFIGURED` Audit | `jarvis/comms/` (Telegram, Discord, Zalo, IMAP) | Tier 1, Tier 3 | `tests/e2e/test_beta_v1_acceptance.py` |
| **F-08** | STT Evaluator CUDA Fix | `tests/eval/stt_intent_eval.py` | Tier 5 | `tests/eval/stt_intent_eval.py` |
| **F-09** | Independent Audio Dataset | `tests/eval/audio_independent/` | Tier 5 | `tests/eval/independent_test_manifest.py` |
| **F-10** | Multi-Model Benchmark | `tests/eval/` (small vs large-v3) | Tier 5 | `tests/eval/stt_intent_eval.py` |
| **F-11** | 4-Way Outcome Reporting | `tests/eval/stt_intent_eval.py` | Tier 5 | `tests/eval/stt_intent_eval.py` |
| **F-12** | Release Readiness Dashboard | `docs/READINESS_DASHBOARD.md` | Doc Audit | Documentation Inspection |
| **F-13** | Documentation Synchronization | `CHANGELOG.md`, `README.md`, `docs/ROADMAP.md` | Doc Audit | Documentation Inspection |
| **F-14** | E2E & Full Regression | Entire codebase | Tier 4, Tier 5 | Full Pytest Suite |
| **F-15** | Forensic Integrity Audit | Security & Evidence Boundaries | Adversarial | Challenger & Forensic Suites |

---

## 4. Test Architecture & Seam Verification

### 4.1 Audio Subsystem Seams
- **16kHz Capture Precedence**: `JarvisApp.record_audio()` evaluates:
  ```python
  sr = int(sample_rate or self.config.get("stt.sample_rate", 16000))
  ```
  This guarantees that even when `audio.sample_rate` is set to 44100 Hz (system playback rate), STT capture occurs directly at 16000 Hz, avoiding resampler distortions and latency.
- **Device Index Synchronization**: `record_audio()` inspects `self.audio_engine._active_device_index`. If set, it explicitly passes `device=target_device` to both `sounddevice.InputStream` and fallback `sounddevice.rec`.
- **Acoustic Settling Delay & Lockout**: When voice interaction begins, `_start_voice_interaction()` calls `tts_manager.speak(greeting_phrase, wait=True)` followed by `time.sleep(0.15)` (150ms settling guard). In addition, `record_audio()` polls `tts_manager.is_playing` with a 1.0s timeout to prevent self-voice audio contamination.

### 4.2 Hardware Controls Fail-Closed Seams
- `JarvisApp._handle_system_volume()` and `_handle_system_brightness()` verify the return value from `ComputerController`.
- If the hardware endpoint returns `None` (e.g. headless environment, COM failure, or missing driver), the handlers return:
  ```python
  {"status": "failed", "success": False, "error": "VOLUME_SET_FAILED" | "BRIGHTNESS_SET_FAILED", ...}
  ```
  Ghost successes (`{"ok": True}` or `volume: None%`) are strictly disallowed.

### 4.3 Comms Security & Fail-Closed Seams
- **Telegram (`jarvis.comms.telegram.TelegramBotController`)**:
  `send_message` and `send_photo` check for active HTTP client. When unconfigured, they return:
  ```python
  {"ok": False, "error_code": "NOT_CONFIGURED", "description": "..."}
  ```
- **Zalo OA (`jarvis.comms.zalo.ZaloBotController`)**:
  `send_message` and `send_image` check `if not self.config.access_token:`. When unconfigured, they return:
  ```python
  ZaloSendResult(success=False, error="NOT_CONFIGURED")
  ```
- **Discord (`jarvis.comms.discord.DiscordBotController`)**:
  `send_message` checks `if self._http and self.bot_token:`. When unconfigured, it returns:
  ```python
  {"success": False, "error_code": "NOT_CONFIGURED", ...}
  ```
- **Email IMAP (`jarvis.comms.email_imap.IMAPEmailReader`)**:
  `connect()` checks `if not self.host or not self.username or not self.password:`. When unconfigured, it raises:
  ```python
  IMAPNotConfiguredError("... Status: NOT_CONFIGURED")
  ```

---

## 5. Execution Commands

### Run Beta v1 E2E Acceptance Suite
```powershell
pytest tests/e2e/test_beta_v1_acceptance.py -v
```

### Run Voice Pipeline Unit Fixes
```powershell
pytest tests/unit/test_voice_pipeline_fixes.py -v
```

### Run All Unit Tests
```powershell
pytest tests/unit/ -q
```

### Run All E2E Integration Tests
```powershell
pytest tests/e2e/ -q
```

### Run STT Benchmark Evaluation (Dual-Condition, Independent Corpus)
```powershell
python tests/eval/stt_intent_eval.py --models small --backend direct --dataset independent --condition clean
python tests/eval/stt_intent_eval.py --models small --backend direct --dataset independent --condition noisy
```
