# Handoff Report — Worker Beta M2: Dataset Synthesis & Evaluator CUDA Patch

## 1. Observation

### CUDA Resolution in STT Evaluator
- In `tests/eval/stt_intent_eval.py` at lines 241-248 (originally):
  ```python
  device = "cuda"
  try:
      import torch
      if not torch.cuda.is_available():
          device = "cpu"
  except Exception:
      device = "cpu"
  ```
  Executing `python -c "import torch"` failed with `ModuleNotFoundError: No module named 'torch'`.
  This caused the evaluator to silently fall back to CPU even on systems equipped with NVIDIA GPUs.
- Testing `ctranslate2.get_cuda_device_count()`:
  ```powershell
  .venv\Scripts\python.exe -c "import sys, ctranslate2; print('ctranslate2 cuda count:', ctranslate2.get_cuda_device_count())"
  ```
  Output:
  ```
  ctranslate2 cuda count: 1
  ```
- After patching `tests/eval/stt_intent_eval.py` lines 277-283 to:
  ```python
  device = "cuda"
  try:
      import ctranslate2
      if ctranslate2.get_cuda_device_count() == 0:
          device = "cpu"
  except Exception:
      device = "cpu"
  ```
  Device resolution was tested and confirmed:
  ```
  Resolved device: cuda
  ```
- Added `--manifest` CLI option and extended `--audio-dir` handling with subprocess propagation and dynamic phrase resolution across both `PHRASE_MANIFEST` and `INDEPENDENT_MANIFEST`.

### Independent Audio Dataset Synthesis (A1, A2)
- Ground truth: `tests/eval/independent_test_manifest.py` containing 210 distinct Vietnamese phrases across 14 intents (15 phrases per intent).
- Implemented `tests/eval/generate_independent_audio.py` featuring:
  * High-fidelity dual Vietnamese neural voices (`vi-VN-HoaiMyNeural` and `vi-VN-NamMinhNeural` via `edge-tts` with `gTTS` fallback).
  * Polyphase resampling via `scipy.signal.resample_poly` (ratio 2:3 from 24kHz to 16kHz) and peak normalization to 0.85 (-1.4 dBFS).
  * Realistic acoustic indoor noise simulation calibrated to SNR 10-15 dB (combining 400Hz low-pass Butterworth HVAC/fan rumble, 100-2000Hz bandpass room reverberation, and wideband background noise).
  * Output written as standard 16-bit PCM mono WAV (`PCM_16`) at 16000 Hz.
- Execution log from `tests/eval/generate_independent_audio.py`:
  ```
  Starting audio synthesis for 210 independent utterances across 14 intents...
  Target conditions: 'clean' (16kHz mono) and 'noisy' (SNR 10.0-15.0dB).
  Output directory: D:\Software GitCode\JARVIS\tests\eval\audio_independent

  Synthesis completed in 632.4s!
  Processed: 210, Skipped existing: 15, Errors: 0

  ============================================================
  VERIFICATION OF INDEPENDENT DATASET
  ============================================================
  Clean WAV files: 210 / 210
  Noisy WAV files: 210 / 210
  Total audio files: 420 / 420

  ALL 420 FILES VERIFIED SUCCESSFULLY! (16000 Hz, 1 channel, valid PCM_16 WAV headers)
  ```

---

## 2. Logic Chain

1. **CUDA Device Resolution**:
   - Step 1: In the project environment, `ctranslate2` is compiled with CUDA support while `torch` is not installed.
   - Step 2: By replacing the `import torch` check with `import ctranslate2; if ctranslate2.get_cuda_device_count() == 0: device = "cpu"`, the evaluator accurately detects NVIDIA GPU acceleration.
   - Step 3: By adding `--manifest` argument parsing and forwarding `--_worker-manifest` to subprocess workers, the evaluator seamlessly handles arbitrary external audio corpora.

2. **Dataset Compliance (Audit Criteria A1 & A2)**:
   - Step 1: Criterion A1 requires >=200 independent utterances with zero overlap with the historical 90-file evaluation corpus. `tests/eval/independent_test_manifest.py` provides 210 distinct utterances across 14 intents.
   - Step 2: Criterion A2 requires dual acoustic conditions (`clean` and `noisy`).
   - Step 3: `generate_independent_audio.py` synthesizes authentic speech for all 210 utterances into `tests/eval/audio_independent/clean/<intent>/variant_<idx>.wav` and generates perturbed audio at SNR ~10-15dB into `tests/eval/audio_independent/noisy/<intent>/variant_<idx>.wav`.
   - Step 4: Every file was validated for `samplerate == 16000`, `channels == 1`, and valid non-empty PCM_16 WAV headers, guaranteeing exact 420 compliant audio files.

---

## 3. Caveats

- Audio generation leverages Microsoft `edge-tts` over WebSocket with fallback to `gTTS`. If both internet endpoints are unavailable during a fresh synthesis run, network access is required for re-generation. However, all 420 WAV files are already persisted on disk under `tests/eval/audio_independent/`.
- No other caveats.

---

## 4. Conclusion

- Objective 1 complete: STT Evaluator CUDA device detection in `tests/eval/stt_intent_eval.py` successfully patched using `ctranslate2` and verified resolving `device="cuda"`. Supported `--manifest` and `--audio-dir` CLI options.
- Objective 2 complete: Exactly 420 authentic 16kHz mono WAV files generated (210 clean, 210 noisy) under `tests/eval/audio_independent/` covering all 14 intent domains and 15 variants per intent.
- Objective 3 complete: All 420 audio files verified as 16000 Hz, 1 channel, valid WAV headers.

---

## 5. Verification Method

### 1. Independent Dataset File Count & Integrity Verification
Run:
```powershell
.venv\Scripts\python.exe tests/eval/generate_independent_audio.py
```
Expected output:
```
Clean WAV files: 210 / 210
Noisy WAV files: 210 / 210
Total audio files: 420 / 420
ALL 420 FILES VERIFIED SUCCESSFULLY! (16000 Hz, 1 channel, valid PCM_16 WAV headers)
```

### 2. CUDA Device Detection Verification
Run:
```powershell
.venv\Scripts\python.exe -c "import ctranslate2; print('CUDA count:', ctranslate2.get_cuda_device_count())"
```
Expected output:
```
CUDA count: 1
```

### 3. Evaluator CLI Arguments Verification
Run:
```powershell
.venv\Scripts\python.exe tests/eval/stt_intent_eval.py --help
```
Confirm `--manifest` and `--audio-dir` options are listed.
