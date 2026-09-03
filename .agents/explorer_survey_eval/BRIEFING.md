# BRIEFING — 2026-09-03T15:20:00Z

## Mission
Investigate tests/eval/stt_intent_eval.py, predict_intent implementation, 90 real WAV audio files, evaluation parameters, output files in docs/eval/, and baseline metrics for Voice Pipeline Upgrade (v4.8.1).

## 🔒 My Identity
- Archetype: Explorer
- Roles: Read-only investigation, codebase audit, evaluation pipeline survey
- Working directory: d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\
- Original parent: 8def6a90-7f5e-498d-8141-0070b9751330
- Milestone: Voice Pipeline Upgrade (v4.8.1)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement changes in project source code
- Write only to own directory (.agents/explorer_survey_eval/)
- Produce structured 5-component handoff report (handoff.md)
- Send message to parent agent on completion

## Current Parent
- Conversation ID: 8def6a90-7f5e-498d-8141-0070b9751330
- Updated: 2026-09-03T15:20:00Z

## Investigation State
- **Explored paths**:
  - `tests/eval/stt_intent_eval.py`: Full implementation analysis of `predict_intent`, `_build_router`, `run_single_model`, `--backend direct` vs `--backend production`, CLI args.
  - `jarvis/llm/router.py`: Analysis of `parse_intent`, `_match_rule_key`, `rule_engine`, `_sorted_rule_keys`, `_regex_rules`.
  - `tests/eval/audio/`: Verified 90 real WAV files across `clean/` (45) and `noisy/` (45) for 14 intent categories.
  - `tests/eval/phrase_manifest.py`: Source of truth for 45 spoken phrases and variant mappings.
  - `tests/eval/failure_decomposition.py`: Verified `EXPECTED_ACTIONS`, 4-way outcome taxonomy (`CORRECT`, `MISROUTED`, `STT_EMPTY`, `ROUTER_ABSTAIN`), and `classify_outcome()`.
  - `docs/eval/stt_eval_results_direct.json` and `docs/eval/stt_eval_summaries_direct.json`: Audited all 90 trial records and summary metrics.
  - `tests/eval/routing_eval_n150.py`: Cross-referenced text-only routing benchmark.
- **Key findings**:
  - Baseline numbers for `large-v3 --backend direct`: CORRECT = 34/90 (37.8%), MISROUTED = 3/90 (3.3%), ROUTER_ABSTAIN = 53/90 (58.9%), STT_EMPTY = 0/90 (0.0%).
  - `predict_intent` in `stt_intent_eval.py` currently runs a raw dictionary scan `for keyword, result in _ROUTER.rule_engine.items(): if keyword in t: return result.action_name`. It does NOT call `parse_intent`, ignores `_regex_rules`, ignores key length sorting, does not use token matching, and has zero diacritic normalization.
  - The 3 baseline misroutings: 2 are the known open_app/variant_3 "mở spotify" -> "spotify" taxonomy ambiguity; 1 is noisy volume_control/variant_3 where "tắt tiếng" was misheard as "Tắt tính Tắt tính", matching single-word rule `"tắt"` -> `system_power`!
  - 7 trials turn from ROUTER_ABSTAIN to CORRECT via R1 safe diacritic normalization alone (bringing CORRECT to 41/90 = 45.6% >= 44.4%, and ROUTER_ABSTAIN down to 51.1% <= 50%).
  - In syncing `predict_intent` to `_ROUTER.parse_intent()`, `unknown_intent` MUST be translated to `"NO_INTENT"` to prevent `classify_outcome()` from classifying unmatched utterances as `MISROUTED`.
- **Unexplored areas**: None for survey scope.

## Key Decisions Made
- Document findings systematically across the 5 required handoff components (Observation, Logic Chain, Caveats, Conclusion, Verification Method).
- Provide explicit before/after code snippets and mathematical projection for R1, R2, and R3.

## Artifact Index
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\DISPATCH.md` — Assignment instructions
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\progress.md` — Liveness tracker
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\BRIEFING.md` — Persistent memory briefing
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\handoff.md` — Final investigation report
