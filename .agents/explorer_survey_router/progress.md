# Progress — Explorer Survey Router

Last visited: 2026-09-03T15:12:45Z

## Current Status
Started investigation into Router architecture, diacritic handling, and phonetic drift rules.

## Checklist
- [x] Received dispatch instructions and synchronized DISPATCH.md
- [x] Initialized BRIEFING.md and progress.md
- [x] Investigate `jarvis/llm/router.py`:
  - [x] Rule structure and `_match_rule_key` implementation
  - [x] Check how regex, substring, or exact matching currently works
  - [x] Check if any diacritic stripping or normalization currently exists
- [x] Design specification for `strip_vietnamese_diacritics(text: str) -> str`:
  - [x] Comprehensive Vietnamese character mapping (NFC and NFD)
  - [x] `đ/Đ` -> `d/D`
  - [x] Performance and edge cases
- [x] Safe diacritic folding integration into `_match_rule_key`:
  - [x] Multi-word (`len(words) >= 2`) vs single-word (`len(words) == 1`) rule
  - [x] Token boundary matching / regex boundaries
  - [x] Homophone collision analysis (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`)
  - [x] Verification on required test queries
- [x] Survey R3 Phonetic Drift Aliases:
  - [x] `system_power`, `app_open`, `reminder`, `system_volume`, `memory_save_fact`
  - [x] Rule priority and dictionary placement
  - [x] Collision check with existing tests
- [x] Check `tests/eval/stt_intent_eval.py` usage of router vs raw dictionary
- [x] Compile comprehensive handoff report `handoff.md`
- [x] Message parent agent


