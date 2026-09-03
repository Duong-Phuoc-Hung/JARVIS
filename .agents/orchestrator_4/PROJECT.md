# Project: JARVIS Voice Pipeline Upgrade (v4.8.1)

## Architecture
- **Layer 1: Speech-to-Text (STT) & Audio Benchmark Pipeline**:
  - Offline Faster-Whisper transcription on 90 real WAV audio files (`tests/eval/audio/clean/`, `tests/eval/audio/noisy/`).
  - `tests/eval/stt_intent_eval.py` orchestrator and worker modes, evaluating `large-v3` with direct backend.
  - Sync with production router: `predict_intent()` routes through `LLMIntentRouter.parse_intent(transcript, force_llm=False)` with contract mapping of `unknown_intent` -> `"NO_INTENT"`.
- **Layer 2: Intent Routing Engine (`jarvis/llm/router.py`)**:
  - Safe Preprocessing Diacritic Normalization: `strip_vietnamese_diacritics()` strips all 134 Vietnamese vowel tone marks and normalizes `đ/Đ` to `d/D` across both NFC and NFD.
  - Two-Class Word Token Matching in `_match_rule_key()`:
    - Multi-word phrases (`len(words) >= 2`): diacritic folding enabled with word boundary regex verification.
    - Single words (`len(words) == 1`): diacritics strictly preserved, whole-word token match enforced `(?:\b|^)key(?:\b|$)`. Zero homophone collisions (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`).
    - Sub-millisecond performance: one-time stripping of input text and precomputed dictionary tables (`_stripped_rule_keys`, `_rule_word_counts`).
  - Selective & Safe Phonetic Drift Aliases: 15 targeted aliases for Whisper mishearings across `system_power`, `app_open`, `reminder`, `system_volume`, and `memory_save_fact`.
- **Layer 3: Generalization & Anti-Overfitting Suite**:
  - Independent held-out test suite `tests/eval/test_voice_generalization_heldout.py` containing >= 25–30 completely unseen utterances across 7 domains with zero overlap with `PHRASE_MANIFEST`.
- **Layer 4: Verification, Quality Assurance & Release**:
  - Full test suite integrity: `pytest tests/unit/ tests/test_adversarial_*.py -q` (0 failures).
  - Documentation: `CHANGELOG.md` v4.8.1 entry, `README.md` voice recognition section and command table.
  - Release: clean git commit and push to `origin main`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `strip_vietnamese_diacritics` | Strip all tone marks and normalize đ/Đ for both NFC & NFD | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Safe Diacritic Folding in `_match_rule_key` | Enable diacritic folding for multi-word phrases (len(words) >= 2) | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Single-Word Whole-Token Homophone Protection | Strict whole-word token match with diacritics preserved for len(words)==1 | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Sync `tests/eval/stt_intent_eval.py` | Route predict_intent through production router with unknown_intent mapping | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Baseline 90-Audio Real Eval (Step 2) | Run stt_intent_eval with large-v3 direct; CORRECT >= 44.4%, ABSTAIN <= 50.0%, MISROUTED <= 3.3% | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Selective Phonetic Drift Aliases (Step 3) | Add 15 safe aliases for system_power, app_open, reminder, system_volume, memory_save_fact | M3 | ORIGINAL_REQUEST §R3 |
| 7 | Real Audio Target Eval (Step 3) | Run 90 WAV eval: CORRECT >= 50.0%, MISROUTED <= 4.4%; save results to docs/eval/ | M3 | ORIGINAL_REQUEST §R3 |
| 8 | Held-Out Generalization Test Suite | Create test_voice_generalization_heldout.py with >= 25-30 unseen cases; CORRECT >= 85%, MISROUTED == 0 | M4 | ORIGINAL_REQUEST §R4 |
| 9 | Full Test Suite Integrity | Run pytest tests/unit/ and tests/test_adversarial_*.py -> 0 failures | M5 | ORIGINAL_REQUEST §R5 |
| 10 | Documentation & Release Push | Update CHANGELOG.md (v4.8.1), README.md, clean git commit & push to origin main | M5 | ORIGINAL_REQUEST §R5 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Safe Preprocessing Diacritic Normalization | Implement `strip_vietnamese_diacritics`, update `_match_rule_key` with multi-word folding and single-word homophone protection in `jarvis/llm/router.py`, sync `tests/eval/stt_intent_eval.py` | None | DONE |
| M2 | Baseline Evaluation on 90 Real Audio Files | Measure ablation on 90 WAV files: verify CORRECT >= 44.4%, ROUTER_ABSTAIN <= 50.0%, MISROUTED <= 3.3% | M1 | DONE |
| M3 | Selective Phonetic Drift Aliases & Target Eval | Add 15 safe phonetic aliases in `router.py`, run real audio eval reaching CORRECT >= 50.0%, MISROUTED <= 4.4%, save JSON summaries | M1, M2 | DONE |
| M4 | Held-Out Generalization Evaluation | Create `tests/eval/test_voice_generalization_heldout.py` (>= 25-30 unseen utterances, 7 domains, CORRECT >= 85%, MISROUTED == 0, 100% pytest pass) | M1, M3 | DONE |
| M5 | Full Test Suite Integrity, CHANGELOG, README & Git Push | Run all unit and adversarial tests (0 failures), update CHANGELOG.md and README.md, commit and push to origin main | M1, M2, M3, M4 | DONE |

## Interface Contracts
### `jarvis/llm/router.py` ↔ Consumers (`tests/eval/stt_intent_eval.py`, `app.py`)
- `strip_vietnamese_diacritics(text: str) -> str`:
  - Input: arbitrary unicode string (NFC or NFD).
  - Output: lowercase/uppercase preserved ASCII base characters, whitespace and punctuation preserved, all combining diacritical marks removed, `đ/Đ` converted to `d/D`.
- `_match_rule_key(self, key: str, clean_lower: str, clean_lower_stripped: str | None = None) -> bool`:
  - Enforces word count boundary: `len(words) == 1` preserves diacritics and checks regex `(?:\b|^)key(?:\b|$)`.
  - `len(words) >= 2` checks exact match first, then falls back to stripped key in stripped text with word boundary check.
- `parse_intent(self, text: str, force_llm: bool = False) -> IntentResult`:
  - Returns `IntentResult(action_name=...)`. If unhandled, returns `action_name="unknown_intent"`.
- `predict_intent(transcript: str) -> str`:
  - Calls `_ROUTER.parse_intent(transcript, force_llm=False)`.
  - Maps `res.action_name == "unknown_intent"` or `"generic_llm_response"` or empty -> `"NO_INTENT"`.

## Code Layout
- `jarvis/llm/router.py`: Router core, `strip_vietnamese_diacritics`, `_match_rule_key`, rule engine dictionary additions.
- `tests/eval/stt_intent_eval.py`: Evaluation runner, `predict_intent` synchronization.
- `tests/eval/test_voice_generalization_heldout.py`: Independent held-out test suite.
- `docs/eval/stt_eval_results_direct.json`: Direct evaluation trial output.
- `docs/eval/stt_eval_summaries_direct.json`: Direct evaluation summary metrics.
- `CHANGELOG.md`: Release notes.
- `README.md`: System documentation and command catalog.
