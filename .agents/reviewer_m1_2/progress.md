# Progress Tracker - Reviewer M1-2 (Milestone M1: Safe Preprocessing Diacritic Normalization v4.8.1)

- [x] Received dispatch & initialized BRIEFING.md / DISPATCH.md / progress.md
- [/] Review worker handoff (`.agents/worker_m1/handoff.md`) and original requirements
- [ ] Inspect source code changes in `jarvis/llm/router.py` and `tests/eval/stt_intent_eval.py`
- [ ] Integrity check: check for hardcoded test fixtures, facade implementations, or bypasses
- [ ] Adversarially challenge edge cases:
  - Upper/lower case mixes (`Điều Chỉnh ÂM LƯỢNG`, `ĐẶT NHẮC`)
  - Mixed punctuation and special characters (`Điều chỉnh âm lượng!`, `Tìm kiếm Google???`)
  - ReDoS and massive input latency SLAs (< 20.0 ms on 50KB strings)
  - Robustness when `self.llm is None` or `dispatcher` has no actions
  - Unicode NFD/NFC 134+ vowel forms and `đ/Đ`
  - Zero-homophone-collision checks (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`)
- [ ] Execute test suites:
  - `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q`
  - `pytest tests/test_adversarial_m2_llm_router.py -v`
  - `python tests/eval/routing_eval_n150.py`
- [ ] Draft comprehensive handoff report (`.agents/reviewer_m1_2/handoff.md`) with verdict
- [ ] Send final review verdict message to parent

*Last visited: 2026-09-03T15:41:00Z*
