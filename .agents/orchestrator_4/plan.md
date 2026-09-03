# Plan — Voice Pipeline Upgrade (v4.8.1)

## Objective
Implement and verify all 5 requirements (R1 - R5) from user request:
- R1: Safe Preprocessing Diacritic Normalization in `jarvis/llm/router.py` & sync `tests/eval/stt_intent_eval.py`.
- R2: Baseline evaluation on 90 real WAV audio files (`tests/eval/stt_intent_eval.py --models large-v3 --backend direct`) with ablation metric tracking.
- R3: Selective & Safe Phonetic Drift Aliases with zero misrouting and reaching real audio eval target (CORRECT >= 50%, MISROUTED <= 4.4%).
- R4: Held-Out Generalization Evaluation (`tests/eval/test_voice_generalization_heldout.py`) with >= 25-30 unseen cases, CORRECT >= 85%, MISROUTED == 0.
- R5: Full Test Suite Integrity (`pytest tests/unit/ tests/test_adversarial_*.py -q`), CHANGELOG.md, README.md, clean git commit & push to origin main.

## Orchestration Strategy
Project Pattern:
- Survey Phase: Dispatch 3 Explorers in parallel to inspect:
  - Explorer 1: `jarvis/llm/router.py` and current pattern matching, rule ordering, normalization logic.
  - Explorer 2: `tests/eval/stt_intent_eval.py`, audio dataset (90 WAV files location and metadata), output json format.
  - Explorer 3: Test suite (`tests/unit/`, `tests/test_adversarial_*.py`, held-out test requirements, git status).
- Synthesize findings into `PROJECT.md`.
- Execute Milestones M1 through M5 using Worker, Reviewers, Challengers, and Auditor with strict gate checks.
