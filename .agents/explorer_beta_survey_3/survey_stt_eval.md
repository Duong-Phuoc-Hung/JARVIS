# JARVIS Beta v1 — STT & Intent Router Evaluation Pipeline Survey (R3 / H-05 / A1–A4)

**Document Status**: Authoritative Explorer Survey Report  
**Author**: STT Evaluation Explorer (`explorer_beta_survey_3`)  
**Parent**: Project Orchestrator (`fcbdbddb-159a-4432-af21-f3ef3e4e8c4e`)  
**Date**: 2026-09-13  
**Integrity Mode**: Benchmark / Fail-Closed  

---

## 1. Executive Summary

This survey provides an empirical, evidence-grounded audit of the speech-to-text (STT) and intent routing evaluation pipeline in JARVIS. It directly investigates Requirement **R3: Multi-Condition Independent STT & Router Evaluation (H-05 / A1–A4)** specified in `ORIGINAL_REQUEST.md`.

### Core Findings Matrix

| Criterion | Requirement (R3 / H-05) | Current Repository Status | Gap / Blocker Identified |
|---|---|---|---|
| **A1: Dataset Independence** | Independent test evaluation set of $\ge 200$ audio utterances distinct from historical 90-file set | 🔴 **NOT YET GENERATED**. Only the historical 90 WAV files exist (`clean`: 45, `noisy`: 45). Zero independent audio files exist. | No audio files exist for held-out evaluation. `test_voice_generalization_heldout.py` has 35 text utterances, but 0 audio recordings. `record_test_set.py` requires manual microphone recording. |
| **A2: Dual Acoustic Conditions** | Both `clean` and `noisy` acoustic environments evaluated | 🟢 **DEFINED & TESTED ON 90-SET**. 45 clean files (quiet room, 30cm) and 45 noisy files (fan/TV background, 60-80cm). | Conditions are separate physical recordings, not software noise injection. No programmatic noise injection scripts exist. |
| **A3: Multi-Model Comparison** | Direct execution benchmark of Whisper `small` vs `large-v3` | 🟡 **FUNCTIONAL BUT CPU-BIASED BY SCRIPT BUG**. Subprocess architecture is sound for VRAM isolation, but `stt_intent_eval.py` forces CPU execution due to missing `torch` check. | `import torch` in `stt_intent_eval.py:243` fails in `.venv` (where only `ctranslate2` is installed), forcing CPU execution (~20s/sample) despite CUDA being fully functional. |
| **A4: 4-Way Outcome Reporting** | Breakdown of `CORRECT`, `MISROUTED`, `STT_EMPTY`, and `ROUTER_ABSTAIN` | 🟢 **VERIFIED IN CODE & EVIDENCE**. Corrected taxonomy in `tests/eval/failure_decomposition.py` and `stt_intent_eval.py` cleanly separates STT empty transcripts from router keyword misses. | Operating point: `small` model achieves ~37.8% CORRECT (P0-A baseline), bounded by 60% ROUTER_ABSTAIN rather than STT failure. |

---

## 2. Dataset Independence Assessment (A1)

### 2.1 File System Inventory of Audio Datasets
A comprehensive scan across the entire workspace for `*.wav` files confirmed **exactly 90 WAV files in total**:
- Root directory: `tests/eval/audio/`
  - `tests/eval/audio/clean/`: 45 WAV files
  - `tests/eval/audio/noisy/`: 45 WAV files
- No files exist in any alternative audio directory (`tests/eval/audio_independent/`, `tests/eval/heldout_audio/`, etc.).

### 2.2 Intent & Phrase Manifest Breakdown (`tests/eval/phrase_manifest.py`)
The 90 files originate from 14 distinct intents comprising exactly 45 unique phrases:
1. `open_app`: 5 variants (`"mở chrome"`, `"mở ứng dụng chrome"`, `"mở notepad"`, `"mở spotify"`, `"khởi động chrome"`)
2. `system_shutdown`: 3 variants (`"tắt máy tính"`, `"shutdown máy"`, `"tắt nguồn"`)
3. `system_restart`: 3 variants (`"khởi động lại máy"`, `"restart máy tính"`, `"reboot"`)
4. `volume_control`: 5 variants (`"tăng âm lượng"`, `"giảm âm lượng"`, `"điều chỉnh âm lượng"`, `"tắt tiếng"`, `"mute"`)
5. `weather_query`: 4 variants (`"thời tiết hôm nay"`, `"thời tiết ngày mai"`, `"dự báo thời tiết"`, `"trời hôm nay thế nào"`)
6. `timer_set`: 3 variants (`"hẹn giờ 5 phút"`, `"đặt timer 10 phút"`, `"nhắc tôi sau 15 phút"`)
7. `reminder_set`: 2 variants (`"nhắc nhở lúc 3 giờ"`, `"đặt nhắc lúc 8 giờ sáng"`)
8. `screenshot`: 3 variants (`"chụp màn hình"`, `"chụp ảnh màn hình"`, `"screenshot"`)
9. `stop`: 4 variants (`"dừng lại"`, `"stop"`, `"thôi"`, `"hủy"`)
10. `search`: 4 variants (`"tìm kiếm google"`, `"tìm file word"`, `"search chrome"`, `"tìm kiếm youtube"`)
11. `music_play`: 3 variants (`"mở nhạc"`, `"phát nhạc"`, `"play music"`)
12. `screen_off`: 2 variants (`"tắt màn hình"`, `"turn off monitor"`)
13. `note_take`: 2 variants (`"ghi chú"`, `"tạo ghi chú mới"`)
14. `settings_open`: 2 variants (`"mở cài đặt"`, `"open settings"`)

**Total unique phrases = 45**. Evaluated across 2 acoustic conditions = **90 audio files**.

### 2.3 Status of the Held-Out Test Set (`tests/eval/test_voice_generalization_heldout.py`)
- The file `tests/eval/test_voice_generalization_heldout.py` defines `HELDOUT_TEST_SET` containing **35 unseen test cases** across 7 domains (`weather`, `reminder`, `system`, `search`, `volume`, `notes`, `apps`).
- `test_zero_manifest_overlap()` strictly asserts 0 overlap with the 45 phrases in `PHRASE_MANIFEST`.
- **CRITICAL DISTINCTION**: This held-out test suite is a **pure text routing unit test** (`router.parse_intent(utterance)`). It does **not** evaluate acoustic speech or STT models. There are **zero acoustic recordings (WAV files)** for these 35 held-out utterances.

### 2.4 Existing Scripts to Produce/Record New Audio Data
- `tests/eval/record_test_set.py`:
  - Interactive CLI tool that drives a live microphone recording session.
  - Takes parameters: `--conditions clean noisy`, `--variants 5`, `--resume`.
  - Captures 16kHz mono audio via `sounddevice.rec()`, trims leading/trailing silence via RMS energy, checks duration ($\ge 0.5\text{s}$) and minimum RMS ($> 0.005$).
  - **Limitation**: It imports `INTENT_TEST_SET` from `tests.eval.phrase_manifest` (the fixed 45 phrases). It is **not** an automated generator; it requires a human to sit at a microphone and speak each prompt.
- **Automated Generation Gap**:
  - The repository currently lacks an automated TTS audio generation script to synthesize $\ge 200$ Vietnamese audio utterances.
  - While `jarvis/tts/manager.py` supports SAPI5 and ElevenLabs, SAPI5 defaults to English voices on standard Windows installations, and `ELEVENLABS_API_KEY` is unset.
  - There is no script using `edge-tts` or pre-recorded open datasets (e.g. Vivos/CommonVoice) to batch-generate evaluation WAV files.

---

## 3. Dual Acoustic Conditions Analysis (A2)

### 3.1 Acoustic Condition Definitions
In `tests/eval/record_test_set.py` (lines 58–71), the two conditions are formally defined as:
1. **`clean`**:
   - Environment: Quiet room, background noise sources turned off (fan, TV, street noise).
   - Speaker distance: Normal distance (~30 cm from microphone).
   - Delivery: Clear speech, standard Vietnamese pronunciation. Baseline acoustic clarity.
2. **`noisy`**:
   - Environment: Background noise active (fan or TV running at moderate volume).
   - Speaker distance: Further distance (60–80 cm from microphone) or slightly softer voice.
   - Delivery: Simulates realistic living-room / workspace interference.

### 3.2 Generation Method: Physical Recordings vs Synthetic Noise
- **Physical Verification**: Audio files in `tests/eval/audio/clean` and `tests/eval/audio/noisy` have different sample lengths and waveforms (e.g. `clean/open_app/variant_0.wav` is 74,080 samples / 4.63s, whereas `noisy/open_app/variant_0.wav` is 33,920 samples / 2.12s).
- **Finding**: Dual conditions in the current dataset were created via **two distinct physical recording passes**, not via programmatic noise injection (additive white Gaussian noise, street babble, or SNR scaling).
- **Implication**: If $\ge 200$ independent audio files are created artificially from clean recordings, an SNR noise injection utility (e.g., adding room impulse responses or fan noise at +10dB, +5dB SNR) would need to be implemented.

---

## 4. Multi-Model Comparison (A3)

### 4.1 Execution Architecture & VRAM Isolation
- Evaluator script: `tests/eval/stt_intent_eval.py`
- Models supported: `small` and `large-v3`
- Subprocess Isolation:
  - `stt_intent_eval.py` lines 490–506 spawn a dedicated subprocess for each model (`--_worker-model <name> --_worker-out <path>`).
  - **Reason**: On Windows with NVIDIA GTX 1650 (4,096 MiB VRAM), `ctranslate2` / PyTorch memory allocators do not reliably return VRAM to the OS upon object deletion. Spawning a new subprocess guarantees that VRAM is 100% released before the next model is loaded.
  - This design successfully prevents CUDA Out-Of-Memory (OOM) crashes when switching from `small` to `large-v3`.

### 4.2 Comparison of Evaluation Backends

| Dimension | Direct Backend (`--backend direct`) | Production Backend (`--backend production`) |
|---|---|---|
| **Class Surface** | Raw `faster_whisper.WhisperModel` | `jarvis.stt.engine.FasterWhisperSTT` |
| **Beam Size** | `beam_size = 3` (retains comparability with historical latency benchmarks) | `beam_size = 5` (production default) |
| **Audio Input** | Path string directly to `WhisperModel.transcribe()` | `audio_to_float32()` conversion, mono-channel mix |
| **RMS Pre-Gate** | None (evaluates all audio files) | `calculate_rms(arr) < 0.001` returns `""` immediately |
| **Hallucination Gate**| None | Discards low RMS ($<0.005$) segments with $>3$ words |
| **Confidence Output**| Supported: $\text{confidence} = \exp(\text{mean}(\text{avg\_logprob}))$ | Unsupported (`None`): `FasterWhisperSTT` returns string only |
| **Threshold Curve** | Generates 0.3–0.9 threshold sweep | Empty `{}` |

### 4.3 Script Bug Discovery: CPU Fallback in `stt_intent_eval.py`
During the audit, a significant execution barrier was uncovered in `tests/eval/stt_intent_eval.py` lines 241–248:
```python
device = "cuda"
try:
    import torch
    if not torch.cuda.is_available():
        device = "cpu"
except Exception:
    device = "cpu"
```
- **Evidence**: The project's `.venv` environment contains `ctranslate2 4.8.1`, `faster-whisper 1.2.1`, and `nvidia-cublas-cu12 12.9.2.10`. However, `torch` is **not installed** in `.venv`.
- **Result**: `import torch` raises `ModuleNotFoundError`. The `except Exception:` block catches this and unconditionally sets `device = "cpu"`.
- **Impact**:
  - Direct execution via `stt_intent_eval.py` inadvertently runs models on the **CPU**, resulting in `large-v3` p50 latency of **~20,083 ms** (20 seconds/utterance) instead of **~2,565 ms** on CUDA!
  - `ctranslate2.get_cuda_device_count()` reports `1` and CUDA acceleration is fully functional (as demonstrated by `FasterWhisperSTT._resolve_device()`), but `stt_intent_eval.py` bypassed it due to the `torch` check.

---

## 5. 4-Way Outcome Reporting (A4)

### 5.1 Outcome Taxonomy & Classification Logic
Implemented in `tests/eval/failure_decomposition.py` and utilized in `stt_intent_eval.py`:
- `CORRECT`: `predicted_action in EXPECTED_ACTIONS[intent_gt]`
- `MISROUTED`: `predicted_action != "NO_INTENT"` and not in `EXPECTED_ACTIONS[intent_gt]` (safety risk: executes wrong action).
- `STT_EMPTY`: `transcript.strip() == ""` (acoustic recognition complete failure).
- `ROUTER_ABSTAIN`: `transcript.strip() != ""` and `predicted_action == "NO_INTENT"` (STT transcribed text, but the router found no matching rule or keyword).

### 5.2 Historical Taxonomy Correction
The historical evaluation collapsed `STT_EMPTY` and `ROUTER_ABSTAIN` into a single metric: `SILENT_FAILURE`. This created the misconception that Whisper failed to transcribe audio 70–80% of the time.
Failure decomposition on the historical 180 evaluation trials proved:
- Total legacy `SILENT_FAILURE` rows: **134**
- True `STT_EMPTY`: **3 (2.2%)**
- True `ROUTER_ABSTAIN`: **131 (97.8%)**

This proves that **transcription acoustic capture is largely functional**, but **intent routing keyword alignment was the primary failure point**.

---

## 6. Review of Empirical Results & Historical Runs

### 6.1 Summary Comparison of Evaluation Datasets

| Dataset / Run | Model | Condition | Backend | N | CORRECT | MISROUTED | STT_EMPTY | ROUTER_ABSTAIN | Latency p50 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| **P0-A Run (2026-09-13)**<br>`tests/eval/results_p0a/` | `small` | clean | direct | 45 | 17 (37.8%) | 1 (2.2%) | 0 (0.0%) | 27 (60.0%) | 3,907 ms |
| **Post-Fix Run**<br>`tests/eval/results_post_fix/` | `large-v3` | clean | production | 45 | 26 (57.8%) | 3 (6.7%) | 0 (0.0%) | 16 (35.6%) | 20,348 ms (CPU) |
| **Post-Fix Run**<br>`tests/eval/results_post_fix/` | `large-v3` | noisy | production | 45 | 26 (57.8%) | 3 (6.7%) | 0 (0.0%) | 16 (35.6%) | 20,083 ms (CPU) |
| **Direct Post-Fix**<br>`docs/eval/stt_eval_results_direct.json` | `large-v3` | clean | direct | 45 | 30 (66.7%) | 1 (2.2%) | 0 (0.0%) | 14 (31.1%) | 2,733 ms (CUDA) |
| **Direct Post-Fix**<br>`docs/eval/stt_eval_results_direct.json` | `large-v3` | noisy | direct | 45 | 27 (60.0%) | 1 (2.2%) | 0 (0.0%) | 17 (37.8%) | 2,565 ms (CUDA) |
| **Historical Baseline**<br>`docs/eval/stt_eval_results.json` | `small` | clean | direct | 45 | 7 (15.6%) | 1 (2.2%) | 1 (2.2%) | 36 (80.0%) | 853 ms |
| **Historical Baseline**<br>`docs/eval/stt_eval_results.json` | `large-v3` | clean | direct | 45 | 13 (28.9%) | 1 (2.2%) | 0 (0.0%) | 31 (68.9%) | 2,799 ms |

### 6.2 Key Empirical Takeaways
1. **Diacritic Normalization Impact**: Moving from historical baseline to v4.8.1 raised `large-v3` clean accuracy from 28.9% to 66.7% and noisy accuracy from 31.1% to 60.0%.
2. **Small Model Gap**: Whisper `small` achieves only **37.8% CORRECT** on clean audio, with **60.0% ROUTER_ABSTAIN**. The small model frequently introduces minor acoustic/spelling deviations that the exact keyword router rejects.
3. **Safety Profile**: `MISROUTED` remains low across all runs ($\le 2.2\%$ in direct backend, $6.7\%$ in production backend). The lone misroute in direct backend is `open_app/variant_3` (`"mở spotify"` $\to$ `spotify`, where the evaluator strictly expected `app_open`/`web_open`).

---

## 7. Execution Commands & Pipeline Runbook

### 7.1 Exact Execution Commands

1. **Full Dual-Model, Dual-Condition Direct Evaluation (Historical 90 Files)**:
   ```powershell
   .venv\Scripts\python.exe tests/eval/stt_intent_eval.py --models small large-v3 --conditions clean noisy --backend direct --out-dir docs/eval
   ```
2. **Production Backend Evaluation**:
   ```powershell
   .venv\Scripts\python.exe tests/eval/stt_intent_eval.py --models small large-v3 --conditions clean noisy --backend production --out-dir tests/eval/results_post_fix
   ```
3. **Instant Cached-Transcripts Re-Evaluation** (tests router rule changes without re-running STT audio inference):
   ```powershell
   .venv\Scripts\python.exe tests/eval/stt_intent_eval.py --cached-transcripts --models small large-v3 --conditions clean noisy --backend direct --out-dir docs/eval
   ```
4. **Text Generalization Held-Out Test Suite**:
   ```powershell
   .venv\Scripts\pytest.exe tests/eval/test_voice_generalization_heldout.py -v
   ```
5. **Interactive Microphone Recording of Audio**:
   ```powershell
   .venv\Scripts\python.exe tests/eval/record_test_set.py --conditions clean noisy --variants 5
   ```

---

## 8. Identified Barriers & Blockers (Root Cause Analysis)

### Blocker 1: Absence of the $\ge 200$ Independent Audio Dataset (A1)
- **Root Cause**: No audio recordings exist outside `tests/eval/audio/` (N=90). The held-out dataset `test_voice_generalization_heldout.py` (N=35) was implemented purely as a text-matching test.
- **Remediation**:
  1. Author an expanded phrase manifest with $\ge 100$ unseen Vietnamese utterances across all 14 intents.
  2. Implement an automated audio generation script (using edge-tts or offline synthesizer) to create 100 clean WAV files and 100 noisy WAV files (or 200 distinct files), saving them to an independent directory (e.g. `tests/eval/audio_independent/`).

### Blocker 2: Device Detection Bug Forcing CPU Inference (A3)
- **Root Cause**: `stt_intent_eval.py:241-248` imports `torch` to check for CUDA. `torch` is not in `.venv`, so it falls back to `device="cpu"`, causing a $8\times$ latency penalty (~20s vs ~2.5s per utterance).
- **Remediation**: Replace `torch.cuda.is_available()` with `ctranslate2.get_cuda_device_count() > 0` or reuse `FasterWhisperSTT._resolve_device("cuda")`.

### Blocker 3: Lack of Automated Audio Generation Tooling
- **Root Cause**: `record_test_set.py` is entirely interactive and microphone-dependent. Generating 200 utterances manually requires hours of human speech recording.
- **Remediation**: Provide a programmatic speech generation script (e.g. `scripts/generate_independent_eval_audio.py`) leveraging Microsoft Edge TTS (`vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural`) with audio post-processing to inject background noise for the noisy condition.

### Blocker 4: Evaluator Taxonomy Ambiguity ("mở spotify")
- **Root Cause**: `"mở spotify"` in `open_app` is routed to action `"spotify"`, which is considered a misroute because `EXPECTED_ACTIONS["open_app"]` only permits `{"app_open", "web_open"}`.
- **Remediation**: Acknowledge this documented taxonomy edge case in all compliance reporting as a benign taxonomy conflict rather than a safety failure.
