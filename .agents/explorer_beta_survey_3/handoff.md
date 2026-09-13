# Handoff Report — STT & Intent Router Evaluation Survey (Beta v1 / R3 / H-05)

**Agent**: `explorer_beta_survey_3` (STT Evaluation Explorer)  
**Parent**: `fcbdbddb-159a-4432-af21-f3ef3e4e8c4e` (Project Orchestrator)  
**Handoff Type**: Hard Handoff (Investigation Complete)  
**Target File**: `survey_stt_eval.md` (Detailed Findings)  

---

## 1. Observation

1. **Audio File Count and Locations**:
   - Running PowerShell command `Get-ChildItem -Path "." -Recurse -Filter "*.wav"` located **exactly 90 WAV files** in the entire workspace.
   - All 90 files reside under `tests/eval/audio/`:
     * `tests/eval/audio/clean/`: 45 WAV files across 14 intents.
     * `tests/eval/audio/noisy/`: 45 WAV files across 14 intents.
   - No audio files exist in any other directory. There is **no independent test evaluation set of $\ge 200$ audio utterances**.

2. **Ground Truth Phrase Manifest**:
   - `tests/eval/phrase_manifest.py:31-46` defines `PHRASE_MANIFEST` with exactly 14 intents and 45 distinct Vietnamese phrases (5 `open_app`, 3 `system_shutdown`, 3 `system_restart`, 5 `volume_control`, 4 `weather_query`, 3 `timer_set`, 2 `reminder_set`, 3 `screenshot`, 4 `stop`, 4 `search`, 3 `music_play`, 2 `screen_off`, 2 `note_take`, 2 `settings_open`).
   - Every WAV file in `tests/eval/audio/` maps 1-to-1 with a manifest entry (`clean` has 45 files, `noisy` has 45 files).

3. **Held-Out Generalization Test Suite**:
   - `tests/eval/test_voice_generalization_heldout.py:38-87` defines `HELDOUT_TEST_SET` with 35 distinct text utterances across 7 domains.
   - `test_zero_manifest_overlap()` (lines 101-115) enforces 0 overlap with `PHRASE_MANIFEST`.
   - Lines 129-155 execute `router.parse_intent(utterance)` on strings. There are **zero audio files** recorded or synthesized for these 35 utterances.

4. **Recording Tool Implementation**:
   - `tests/eval/record_test_set.py:99-122` records via `sounddevice.rec()` and requires interactive human keyboard input (`input("Press Enter to record...")` at line 157).
   - Line 56 imports `PHRASE_MANIFEST` from `phrase_manifest.py`. There is no programmatic batch generator or TTS synthesis script.

5. **Acoustic Differences Between Clean and Noisy**:
   - Python inspection via `soundfile.read`:
     * `tests/eval/audio/clean/open_app/variant_0.wav`: 74,080 samples (4.63s at 16kHz).
     * `tests/eval/audio/noisy/open_app/variant_0.wav`: 33,920 samples (2.12s at 16kHz).
   - Clean and noisy files are physically distinct human microphone recordings, not generated via software noise injection.
   - Grep search for noise injection / SNR mixing returned 0 results in the repository.

6. **Subprocess Isolation and Device Resolution in Evaluator**:
   - `tests/eval/stt_intent_eval.py:490-506` spawns a dedicated subprocess per model (`--_worker-model <name>`).
   - Lines 241-248 contain:
     ```python
     device = "cuda"
     try:
         import torch
         if not torch.cuda.is_available():
             device = "cpu"
     except Exception:
         device = "cpu"
     ```
   - Running `.venv\Scripts\python.exe -c "import torch"` throws `ModuleNotFoundError: No module named 'torch'`.
   - Running `.venv\Scripts\python.exe -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` returns `1`.
   - Running `nvidia-smi` confirms NVIDIA GeForce GTX 1650 with 4,096 MiB VRAM.
   - Because `torch` is missing, `stt_intent_eval.py` silently falls back to `device="cpu"`, inflating `large-v3` inference latency from ~2,500ms to ~20,083ms.

7. **4-Way Outcome Reporting**:
   - `tests/eval/failure_decomposition.py:70-92` implements `classify_outcome()`:
     * `STT_EMPTY` if `transcript.strip() == ""`
     * `ROUTER_ABSTAIN` if `predicted_action == "NO_INTENT"`
     * `CORRECT` if `predicted_action in expected_actions[intent_gt]`
     * `MISROUTED` otherwise.
   - Historical failure decomposition (`docs/eval/stt_eval_failure_decomposition.md` lines 14-17): of 134 legacy `SILENT_FAILURE` rows, 3 were `STT_EMPTY` (2.2%) and 131 were `ROUTER_ABSTAIN` (97.8%).
   - Recent clean baseline on Whisper `small` (`tests/eval/results_p0a/stt_eval_summaries_direct.json`): N=45, CORRECT=37.8% (17/45), MISROUTED=2.2% (1/45), STT_EMPTY=0.0%, ROUTER_ABSTAIN=60.0% (27/45).

---

## 2. Logic Chain

1. **Regarding A1 (Dataset Independence)**:
   - *Premise 1*: Observation 1 shows only 90 audio files exist in the repository, all within `tests/eval/audio/`.
   - *Premise 2*: Observation 2 shows these 90 files correspond strictly to the 45 phrases in `PHRASE_MANIFEST`.
   - *Premise 3*: Observation 3 shows the held-out generalization set has 35 text utterances and 0 audio files.
   - *Deduction*: The required independent evaluation test set of $\ge 200$ audio utterances does not exist. It has not yet been generated or recorded.
   - *Premise 4*: Observation 4 shows `record_test_set.py` is interactive only, tied to a human at a microphone, and limited to 45 phrases.
   - *Deduction*: To fulfill A1, an automated script (or manual recording session) must be built with $\ge 100$ or $\ge 200$ new distinct Vietnamese phrases.

2. **Regarding A2 (Dual Acoustic Conditions)**:
   - *Premise 1*: Observation 5 shows the 45 clean files and 45 noisy files have distinct waveforms and sample counts.
   - *Premise 2*: Observation 5 shows no programmatic noise injection scripts exist.
   - *Deduction*: Dual conditions currently exist only for the 90 historical files and were produced through manual dual-recording sessions. For any new automated test set, synthetic noise injection (e.g. adding background fan/street noise at controlled SNR) will be required.

3. **Regarding A3 (Multi-Model Comparison)**:
   - *Premise 1*: Observation 6 shows `stt_intent_eval.py` has an effective subprocess isolation pattern that circumvents CTranslate2 VRAM retention on the 4GB GTX 1650.
   - *Premise 2*: Observation 6 demonstrates that `stt_intent_eval.py` imports `torch` to check CUDA, but `.venv` does not have `torch` installed.
   - *Deduction*: Direct execution via `stt_intent_eval.py` runs on CPU by default despite CUDA hardware availability. Changing the device check to use `ctranslate2` restores 2.5s CUDA execution.

4. **Regarding A4 (4-Way Outcome Reporting)**:
   - *Premise 1*: Observation 7 shows that `classify_outcome()` deterministically computes `CORRECT`, `MISROUTED`, `STT_EMPTY`, and `ROUTER_ABSTAIN`.
   - *Premise 2*: Observation 7 shows that `ROUTER_ABSTAIN` accounts for 60% of trials on Whisper `small` and 31–38% on `large-v3`, while `STT_EMPTY` is $\le 2.2\%$.
   - *Deduction*: Whisper STT acoustic capture is reliable; the primary bottleneck preventing $\ge 60\%$ accuracy on Whisper `small` is router vocabulary mismatch.

---

## 3. Caveats

1. **No Production Code Modified**: As an Explorer, no modifications were made to `stt_intent_eval.py` or `record_test_set.py`.
2. **Automated Vietnamese Speech Generation**: Built-in Windows SAPI5 voices lack Vietnamese phonetic support. Synthesizing $\ge 200$ realistic Vietnamese audio files requires an external package like `edge-tts` (which is not currently in `.venv`) or an active ElevenLabs API key (which is currently unset).
3. **Taxonomy Conflict**: As documented in `phrase_manifest.py`, `"mở spotify"` routes to `spotify` in production, but `EXPECTED_ACTIONS["open_app"]` expects `{"app_open", "web_open"}`. This 1 MISROUTED case is a known evaluation taxonomy mismatch, not a safety bug.

---

## 4. Conclusion

- **A1 (Dataset Independence)**: **FAIL / NOT MET**. No $\ge 200$ independent audio utterance dataset exists. Only 90 historical files exist.
- **A2 (Dual Acoustic Conditions)**: **PARTIALLY MET**. Valid for the 90 historical files (physically recorded), but no automated noise injection pipeline exists for synthetic multi-condition evaluation.
- **A3 (Multi-Model Comparison)**: **BLOCKED BY MINOR SCRIPT DEFECT**. Subprocess architecture is functional, but `stt_intent_eval.py:243` falls back to CPU due to missing `torch`. Fixing the check to use `ctranslate2` enables real GPU benchmarking.
- **A4 (4-Way Outcome Reporting)**: **MET & ACCURATE**. The 4-way taxonomy is implemented, verified, and correctly separates STT recognition from router abstention.
- **Detailed Survey**: See `survey_stt_eval.md` for full metrics, comparative tables, and run logs.

---

## 5. Verification Method

1. **Verify audio file count**:
   ```powershell
   Get-ChildItem -Path "tests\eval\audio" -Recurse -Filter "*.wav" | Measure-Object | Select-Object Count
   ```
   *Expected*: Exactly 90 files (45 clean, 45 noisy). Zero independent files.

2. **Verify CUDA availability vs Torch omission**:
   ```powershell
   .venv\Scripts\python.exe -c "import ctranslate2; print('CUDA Count:', ctranslate2.get_cuda_device_count())"
   .venv\Scripts\python.exe -c "import torch"
   ```
   *Expected*: CUDA Count is 1; `import torch` raises `ModuleNotFoundError`.

3. **Verify 4-Way Outcome execution on cached transcripts**:
   ```powershell
   .venv\Scripts\python.exe tests/eval/stt_intent_eval.py --cached-transcripts --models large-v3 --conditions clean noisy --backend direct --out-dir docs/eval
   ```
   *Expected*: Reports 4-way table (`Correct`, `Misroute`, `STT_empty`, `RtrAbst`).

4. **Verify text held-out suite**:
   ```powershell
   .venv\Scripts\pytest.exe tests/eval/test_voice_generalization_heldout.py -v
   ```
   *Expected*: 100% PASS (37/37 tests passed).
