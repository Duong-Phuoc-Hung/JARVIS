# DISPATCH — Worker M2 (Baseline Evaluation on 90 Real Audio Files)

You are Worker M2 implementing Milestone 2 for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m2\`

## Mandatory Reading
1. `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`, requirement R2)
2. `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`
3. `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You own:
- `tests/eval/stt_intent_eval.py`
- `docs/eval/stt_eval_results_direct.json`
- `docs/eval/stt_eval_summaries_direct.json`

## Execution Guidelines
1. In `tests/eval/stt_intent_eval.py`:
   - If running `WhisperModel(..., device="cuda")` fails because CUDA is unavailable or VRAM is insufficient, safely allow `device = "cuda" if torch.cuda.is_available() else "cpu"` (or provide a `--cached-transcripts` flag that evaluates the 90 real WAV audio transcripts already collected in `docs/eval/stt_eval_results_direct.json`).
   - Run:
     ```powershell
     python tests/eval/stt_intent_eval.py --models large-v3 --backend direct
     ```
2. Verify that:
   - Output files `docs/eval/stt_eval_results_direct.json` and `docs/eval/stt_eval_summaries_direct.json` are generated and saved.
   - Combined metrics across all 90 WAV trials satisfy:
     - `CORRECT >= 44.4%` (target ~45.6%, 41/90)
     - `ROUTER_ABSTAIN <= 50.0%` (target ~48.9%, 44/90)
     - `MISROUTED <= 3.3%` (target 3/90, 0 new misroutings)
3. Write your report to `d:\Software GitCode\JARVIS\.agents\worker_m2\handoff.md` and notify parent.
