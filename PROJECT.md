# Project: JARVIS Beta v1 Voice Pipeline & Core Integration

## Architecture
JARVIS is a modular AI voice assistant and automation system for Windows 11.
- **Audio Capture & Hardware Synchronization (`jarvis/audio/`, `jarvis/core/app.py`)**: source-rate capture (16 kHz by default) with normalization to a 16 kHz STT/model boundary, microphone device index synchronization with `AudioEngine`, 4-tier acoustic echo suppression & settling guard (2.5s post-TTS echo window frame drop, 150ms settling sleep, active playback lockout, and single-flight execution mutex).
- **Core Controls & Hardware Fail-Closed Semantics (`jarvis/core/app.py`, `jarvis/automation/`)**: Global PTT shortcut (`Ctrl+Shift+L`) dispatching directly to `_start_voice_interaction(trigger_name="HOTKEY_PTT")`; system master volume and screen brightness returning explicit `status: failed`, `success: False`, and specific error codes (`VOLUME_SET_FAILED`, `BRIGHTNESS_SET_FAILED`) when endpoints return `None`.
- **Communications Hub (`jarvis/comms/`)**: Telegram, Zalo, Discord, and IMAP adapters enforcing strict `NOT_CONFIGURED` fail-closed semantics when tokens or credentials are unconfigured, with user whitelisting (HTTP 403) and token-bucket rate limiting (HTTP 429).
- **STT & Intent Routing Evaluation Pipeline (`tests/eval/`)**: Dual-condition acoustic evaluation (`clean` and `noisy`), multi-model direct execution benchmarking (`small` and `large-v3` on CTranslate2 CUDA), and 4-way outcome classification (`CORRECT`, `MISROUTED`, `STT_EMPTY`, `ROUTER_ABSTAIN`) across historical 90-file and independent 420-utterance test corpora.
- **Documentation & Release Artifacts**: Release readiness dashboard, synchronized CHANGELOG, ROADMAP, README, task tracking, and Windows Installer executable (`dist/installer/JARVIS_Setup_v5.1.0.exe`).

## Feature Inventory
| # | Feature | Description | Milestone | Status | Source |
|---|---------|-------------|-----------|:------:|--------|
| F-01 | 16kHz STT Boundary | Preserve capture rate independently of `audio.sample_rate`; normalize to 16kHz before STT/VAD/model | M1 | DONE | Survey (Explorer 1) |
| F-02 | Microphone Device Sync | Synchronize `record_audio()` with `AudioEngine._active_device_index` passed to sounddevice | M1 | DONE | ORIGINAL_REQUEST §R1 (H-02) |
| F-03 | Acoustic Settling & Echo Lockout | 150ms post-TTS settling guard, active playback wait loop, and echo window frame drop | M1 | DONE | ORIGINAL_REQUEST §R1 (H-03) |
| F-04 | Zero-Crash Hotkeys | `Ctrl+Shift+L` PTT hotkey calling `_start_voice_interaction(trigger_name="HOTKEY_PTT")` | M1 | DONE | ORIGINAL_REQUEST §R2 (H-04) |
| F-05 | Hardware Controls Fail-Closed | Master volume & brightness returning `success: False` & error codes on `None` | M1 | DONE | ORIGINAL_REQUEST §R2 (H-08) |
| F-06 | Zalo `send_image()` Fail-Closed Fix | Fix `send_image()` to return `success=False, error="IMAGE_SEND_NOT_IMPLEMENTED"` and strip whitespace tokens | M1 | DONE | Survey / Auditor Beta M1 |
| F-07 | Comms `NOT_CONFIGURED` Audit | Verify Telegram, Discord, Zalo, IMAP fail-closed compliance | M1 | DONE | ORIGINAL_REQUEST §R4 (D-06..D-09) |
| F-08 | STT Evaluator CTranslate2 CUDA Fix | Patch `stt_intent_eval.py:241` to check `ctranslate2.get_cuda_device_count() > 0` instead of `import torch` | M2 | DONE | Survey (Explorer 3) |
| F-09 | Independent Audio Dataset (A1, A2) | Synthesize 420 independent audio utterances across clean and noisy acoustic conditions | M2 | DONE | ORIGINAL_REQUEST §R3 (H-05) |
| F-10 | Multi-Model Benchmark (A3) | Benchmark `small` and `large-v3` Whisper models under direct execution | M3 | PLANNED | ORIGINAL_REQUEST §R3 (H-05) |
| F-11 | 4-Way Outcome Reporting (A4) | Record transparent breakdown of `CORRECT`, `MISROUTED`, `STT_EMPTY`, `ROUTER_ABSTAIN` | M3 | PLANNED | ORIGINAL_REQUEST §R3 (H-05) |
| F-12 | Release Readiness Dashboard | Document `PENDING_CREDENTIALS` (D-06..D-09) and `BLOCKED_ON_CERT` (D-14) in `docs/READINESS_DASHBOARD.md` | M4 | PLANNED | ORIGINAL_REQUEST §R4 |
| F-13 | Documentation Synchronization | Synchronize `CHANGELOG.md`, `task.md`, `README.md`, and `docs/ROADMAP.md` per `AGENTS.md` | M4 | PLANNED | AGENTS.md Invariant |
| F-14 | E2E & Full Regression Verification | Pass 100% of `tests/unit/test_voice_pipeline_fixes.py` (8/8), `test_beta_v1_acceptance.py` (28/28) | M5 | IN_PROGRESS | Acceptance Criteria |
| F-15 | Forensic Integrity & Adversarial Audit | Independent Forensic Auditor and Challenger validation against fabrication and ghost success | M5 | PLANNED | Audit Framework |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|:------:|
| E2E | E2E Acceptance Test Suite | F-14 (`tests/e2e/test_beta_v1_acceptance.py`, `TEST_READY.md`) | none | DONE |
| M1 | Voice Pipeline & Comms Core Hardening | F-01, F-02, F-03, F-04, F-05, F-06, F-07 (H-01 config fix, Zalo fail-closed, comms audit) | none | DONE |
| M2 | Dataset Synthesis & Evaluator CUDA Patch | F-08, F-09 (ctranslate2 CUDA fix, synthesis of 420 audio utterances, clean & noisy) | none | DONE |
| M3 | Multi-Model Benchmark & 4-Way Evaluation | F-10, F-11 (Execute direct benchmark for small & large-v3, generate 4-way evaluation report) | M2 | PLANNED |
| M4 | Readiness Dashboard & Doc Synchronization | F-12, F-13 (Publish READINESS_DASHBOARD.md, update CHANGELOG.md, task.md, README.md, ROADMAP.md) | M1, M3 | PLANNED |
| M5 | Final Regression, Adversarial & Forensic Audit | F-14, F-15 (Run full test suites, Challenger verification, Forensic Auditor verification) | M1, M2, M3, M4 | PLANNED |

## Interface Contracts
### Audio Recording Sample Rate Contract (`jarvis/core/app.py`, `config/default_config.yaml`)
- `record_audio(duration_s=None, sample_rate=None, *, return_capture=False)` captures at the explicit rate, otherwise `stt.sample_rate`, otherwise 16000 (including a configured `None`). Invalid rates raise `ValueError` before device access. `audio.sample_rate` is unchanged.
- The default return remains a source-rate ndarray for compatibility. `return_capture=True` returns `CapturedAudio(samples, source_sample_rate)`; the production voice loop uses this form so a config reload cannot relabel a captured buffer. Device selection still follows `AudioEngine._active_device_index`.
- `prepare_stt_audio` normalizes/downmixes to mono float32, then resamples once to 16000 when required. WAV/file headers are authoritative; raw ndarray/PCM uses explicit `source_sample_rate`. Legacy raw input without that argument is assumed already 16000. Invalid explicit source rates (including `None`) fail closed.
- Coordinator, tiered and direct providers consume source metadata at their boundary. They pass plain 16-kHz arrays onward without forwarding source metadata to model APIs. Already-16k input bypasses resampling.
- `transcribe_stream(sample_rate=...)` and `feed_audio_block(..., sample_rate=...)` normalize before the 16-kHz VAD. Continuous linear interpolation retains fractional sample accounting across blocks; changing an incremental stream's rate requires `reset_stream(new_rate)`. Upsampling may delay an output sample until the next input block supplies its interpolation neighbor.
- Resampling uses existing NumPy linear interpolation, with no new DSP dependency. This validates rate/duration semantics, not anti-alias quality, WER or physical device compatibility.

### Zalo OA Fail-Closed Contract (`jarvis/comms/zalo.py`)
- `ZaloBotController.send_image(user_id, image_path, caption) -> ZaloSendResult`:
  Sanitizes `token = (self.config.access_token or "").strip()`.
  If `not token`: returns `ZaloSendResult(success=False, error="NOT_CONFIGURED")`.
  If `is_mock=False` and token is provided: returns `ZaloSendResult(success=False, error="IMAGE_SEND_NOT_IMPLEMENTED")`.

### STT Evaluator CUDA Contract (`tests/eval/stt_intent_eval.py`)
- Resolves device using:
  ```python
  device = "cuda"
  try:
      import ctranslate2
      if ctranslate2.get_cuda_device_count() == 0:
          device = "cpu"
  except Exception:
      device = "cpu"
  ```
- CLI flags supported: `--audio-dir` and `--manifest`.

### Evaluation Corpus Contract (`tests/eval/audio_independent/`, `tests/eval/independent_test_manifest.py`)
- 210 distinct Vietnamese phrases across 14 intents.
- Exactly 420 WAV files generated (210 clean, 210 noisy).
- 4-way outcome classification: `CORRECT`, `MISROUTED`, `STT_EMPTY`, `ROUTER_ABSTAIN`.

## Code Layout
- `jarvis/core/app.py`: `record_audio` sample rate resolution, hotkey registration, system volume and brightness fail-closed handlers.
- `jarvis/comms/zalo.py`: Zalo OA adapter, fail-closed `send_image`, whitespace token sanitization.
- `jarvis/comms/telegram.py`, `discord.py`, `email_imap.py`: Fail-closed comms adapters.
- `tests/eval/stt_intent_eval.py`: Benchmark evaluation harness, CUDA device resolution, 4-way outcome reporter.
- `tests/eval/independent_test_manifest.py`: 210 independent phrases ground truth.
- `tests/eval/audio_independent/`: 420 independent audio files (210 clean, 210 noisy).
- `tests/unit/test_voice_pipeline_fixes.py`: Seam-level regression tests for H-01, H-02, H-03, H-04, H-08.
- `tests/e2e/test_beta_v1_acceptance.py`: E2E Acceptance Test Suite across Tiers 1–4 (28 tests).
- `TEST_READY.md`: Acceptance test suite status signal.
- `docs/READINESS_DASHBOARD.md`: Centralized tracking of feature tiers, credentials blockers, and cert blockers.
- `CHANGELOG.md`: Synchronized release notes.
- `task.md`: Task tracking list.
- `README.md`: Root system overview.
- `docs/ROADMAP.md`: Master roadmap tracker.
