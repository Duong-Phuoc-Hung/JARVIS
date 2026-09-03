# DISPATCH — Explorer Survey Eval

You are an Explorer agent investigating JARVIS codebase for Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\`

## Task Assignment
Investigate `tests/eval/stt_intent_eval.py`, audio datasets (90 WAV files location and structure), eval output files in `docs/eval/`, and baseline metrics.
Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).

Specific focus:
1. Examine `tests/eval/stt_intent_eval.py`:
   - How `predict_intent` is implemented currently. Does it use a dictionary scan, raw substring, or import router?
   - How R1 requires syncing `tests/eval/stt_intent_eval.py` so `predict_intent` calls production router with diacritic normalization.
   - CLI arguments: `--models large-v3 --backend direct`. How is `--backend direct` implemented? Does it directly call `FasterWhisperSTT` or what?
2. Inspect the 90 WAV audio files:
   - Where are they stored? (e.g. `tests/data/audio/`, `tests/eval/audio/`, or similar).
   - What are the ground truth transcripts and intent labels? Where is metadata stored?
3. Review existing evaluation results and formats:
   - `docs/eval/stt_eval_results_direct.json`
   - `docs/eval/stt_eval_summaries_direct.json`
   - Check the schema and structure of these JSON files, what metrics are reported (CORRECT, ROUTER_ABSTAIN, MISROUTED, etc.).
   - Baseline numbers mentioned in request: 37.8% baseline -> target >= 44.4% (R2) -> target >= 50% (R3).
4. Write your complete findings to `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\handoff.md` and send a message when done.
