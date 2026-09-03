# BRIEFING — 2026-09-03T15:12:35Z

## Mission
Investigate `jarvis/llm/router.py`, safe Vietnamese diacritic stripping, homophone collision prevention, and phonetic drift rule expansion for Voice Pipeline Upgrade (v4.8.1).

## 🔒 My Identity
- Archetype: Explorer
- Roles: Read-only investigation, codebase analysis, synthesis, architectural design report
- Working directory: d:\Software GitCode\JARVIS\.agents\explorer_survey_router
- Original parent: 8def6a90-7f5e-498d-8141-0070b9751330
- Milestone: Voice Pipeline Upgrade (v4.8.1)

## 🔒 Key Constraints
- Read-only investigation — do NOT modify codebase source files directly
- Write all findings, designs, and reports to `.agents/explorer_survey_router/`
- Send message to parent upon completion

## Current Parent
- Conversation ID: 8def6a90-7f5e-498d-8141-0070b9751330
- Updated: not yet

## Investigation State
- **Explored paths**: `jarvis/llm/router.py`, `tests/eval/stt_intent_eval.py`, `tests/eval/routing_eval_n150.py`, `tests/eval/failure_decomposition.py`, `tests/eval/phrase_manifest.py`, `tests/unit/test_router_p0.py`, `tests/test_adversarial_m1_intent_router.py`, `jarvis/__init__.py`.
- **Key findings**:
  1. `_match_rule_key` at lines 1803-1820 relies on character length `len(key) <= 4` and raw `key in clean_lower` substring checks without diacritic normalization, failing accented queries against unaccented keys (e.g. `"Điều chỉnh âm lượng"`) and vice versa.
  2. `strip_vietnamese_diacritics` specification designed using `unicodedata.normalize('NFD', ...)` + explicit `đ/Đ -> d/D` + combining marks regex `[\u0300-\u036f]`. Handles all 134 vowel-tone combinations across NFC and NFD.
  3. Single-word rules (`len(words) == 1`) strictly preserve diacritics and enforce whole-word token boundaries, eliminating homophone collisions (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`). Multi-word rules (`len(words) >= 2`) safely apply diacritic folding.
  4. R3 phonetic drift aliases identified and mapped cleanly to `system_power`, `app_open`, `reminder`, `system_volume`, and `memory_save_fact`. Length-descending sort guarantees priority without colliding with existing tests.
  5. `tests/eval/stt_intent_eval.py` currently iterates raw `rule_engine.items()` with unordered substring search; ready to synchronize with production router call `parse_intent(transcript, force_llm=False)`.
- **Unexplored areas**: None within router survey scope. Ready for handoff to implementer.

## Key Decisions Made
- Architecture for `strip_vietnamese_diacritics` verified against full Vietnamese Unicode alphabet.
- `_match_rule_key` optimized with precomputed stripped keys, word counts, and one-time stripping per query.
- Guard against `self.llm is None` before Tier 2 to eliminate exception handling overhead during offline eval runs.

## Artifact Index
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\DISPATCH.md` — Assignment instructions
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\BRIEFING.md` — Working memory & state
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\progress.md` — Heartbeat & execution progress
- `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\handoff.md` — Comprehensive Handoff Report

