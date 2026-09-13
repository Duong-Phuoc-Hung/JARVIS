# BRIEFING — 2026-09-13T10:37:30Z

## Mission
Survey and assess the STT and Router evaluation pipeline and empirical data for JARVIS Beta v1 (R3 / H-05 / A1–A4).

## 🔒 My Identity
- Archetype: explorer
- Roles: [investigation, synthesis]
- Working directory: d:\Software GitCode\JARVIS\.agents\explorer_beta_survey_3
- Original parent: fcbdbddb-159a-4432-af21-f3ef3e4e8c4e
- Milestone: Beta v1 STT & Router Evaluation Survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Do NOT modify production source code or test files
- Write findings to survey_stt_eval.md and handoff.md

## Current Parent
- Conversation ID: fcbdbddb-159a-4432-af21-f3ef3e4e8c4e
- Updated: 2026-09-13T10:37:30Z

## Investigation State
- **Explored paths**:
  * `tests/eval/stt_intent_eval.py`
  * `tests/eval/audio/` (clean and noisy)
  * `tests/eval/phrase_manifest.py`
  * `tests/eval/record_test_set.py`
  * `tests/eval/failure_decomposition.py`
  * `tests/eval/test_voice_generalization_heldout.py`
  * `tests/eval/results_p0a/`
  * `tests/eval/results_post_fix/`
  * `docs/eval/`
  * `jarvis/stt/engine.py`
- **Key findings**:
  1. A1 (Dataset Independence): Only 90 WAV files exist in the repository (45 clean, 45 noisy). Zero independent audio files exist. The held-out set in `test_voice_generalization_heldout.py` is text-only (35 cases).
  2. A2 (Dual Acoustic Conditions): Clean and noisy exist for the 90 files via separate physical recordings (different durations/waveforms). No automated noise injection scripts exist.
  3. A3 (Multi-Model Comparison): `stt_intent_eval.py` isolates models via subprocess to release VRAM on GTX 1650 4GB. However, lines 241-248 import `torch` to check CUDA; since `torch` is not installed in `.venv`, it falls back to CPU (~20s vs ~2.5s on GPU).
  4. A4 (4-Way Outcome Reporting): Corrected taxonomy is fully implemented and separates `STT_EMPTY` from `ROUTER_ABSTAIN`. 97.8% of legacy silent failures were router keyword mismatches, not speech recognition drops.
- **Unexplored areas**: None within the survey scope.

## Key Decisions Made
- Documented blockers and actionable remediation steps in `survey_stt_eval.md` and `handoff.md`.

## Artifact Index
- DISPATCH.md — Recorded dispatch message
- BRIEFING.md — Situational awareness
- progress.md — Investigation progress tracker
- survey_stt_eval.md — Detailed survey findings report
- handoff.md — 5-component handoff report
