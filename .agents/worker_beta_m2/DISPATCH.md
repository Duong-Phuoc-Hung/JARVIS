## 2026-09-13T10:42:48Z
You are Worker M2 for the JARVIS Beta v1 project.

Your working directory is: d:\Software GitCode\JARVIS\.agents\worker_beta_m2
Your parent is: fcbdbddb-159a-4432-af21-f3ef3e4e8c4e (Project Orchestrator)

Authoritative User Request: d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md (You MUST read this file first).
Scope Document: d:\Software GitCode\JARVIS\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Write Ownership:
- d:\Software GitCode\JARVIS\tests\eval\stt_intent_eval.py
- d:\Software GitCode\JARVIS\tests\eval\generate_independent_audio.py
- d:\Software GitCode\JARVIS\tests\eval\audio_independent\ (directory and files)

Objectives:
1. Fix STT Evaluator CUDA Device Resolution in `tests/eval/stt_intent_eval.py`:
   - At lines 241-248, replace the `import torch` check with:
     ```python
     device = "cuda"
     try:
         import ctranslate2
         if ctranslate2.get_cuda_device_count() == 0:
             device = "cpu"
     except Exception:
         device = "cpu"
     ```
   - Also allow `--audio-dir` or `--manifest` CLI options in `stt_intent_eval.py` so the evaluator can evaluate any audio directory (like `tests/eval/audio_independent/` or `tests/eval/audio/`).

2. Prepare and Generate the Independent Test Dataset (A1, A2):
   - In `tests/eval/independent_test_manifest.py`, there are 210 distinct Vietnamese utterances across 14 intents (15 phrases per intent).
   - Write a script `tests/eval/generate_independent_audio.py` that synthesizes authentic 16kHz mono audio WAV files for these 210 utterances.
   - For audio synthesis:
     * Check if `edge-tts` is available or install it in `.venv` (`pip install edge-tts`) to generate high-quality Vietnamese audio (e.g. `vi-VN-HoaiMyNeural` or `vi-VN-NamMinhNeural`). Alternatively, use Windows SAPI5 or gTTS if available.
   - Dual Acoustic Conditions (A2):
     * Generate `clean` directory: 210 clean WAV files at 16000 Hz mono.
     * Generate `noisy` directory: 210 WAV files with realistic acoustic noise perturbation (e.g. adding environmental/ambient background noise at SNR ~10-15dB, or fan/white noise simulation).
     * Output structure:
       `tests/eval/audio_independent/clean/<intent>/variant_<idx>.wav`
       `tests/eval/audio_independent/noisy/<intent>/variant_<idx>.wav`
     * Ensure exactly 420 audio files are created (210 clean, 210 noisy), satisfying requirement A1 (>=200 independent utterances) and A2 (dual conditions).

3. Verification:
   - Verify audio files exist: `python -c "import os; print(sum(len(f) for _, _, f in os.walk('tests/eval/audio_independent')))"` outputs 420.
   - Verify audio format: 16000 Hz, 1 channel, valid WAV headers.
   - Verify CUDA device detection in `stt_intent_eval.py`: runs with device="cuda" on NVIDIA GPU.

4. Output:
   - Write handoff report with execution logs to `d:\Software GitCode\JARVIS\.agents\worker_beta_m2\handoff.md`.
   - Send message to parent with completion summary.
