# Progress: Legacy Test Fix Worker

- **Last visited**: 2026-09-02T13:54:35Z
- **Status**: Starting investigation of 24 failing legacy tests.
- **Tasks**:
  1. [ ] Run `pytest tests/ -q --ignore=tests/e2e` to get exact failure traces.
  2. [ ] Group and analyze root causes of failures.
  3. [ ] Fix root causes in source code or legacy test fixtures/assertions.
  4. [ ] Verify `pytest tests/ -q --ignore=tests/e2e` (0 failures).
  5. [ ] Verify `pytest tests/e2e/test_v460_e2e.py -v` (57 passed).
  6. [ ] Verify `python tests/eval/routing_eval_n150.py` (100% correct).
  7. [ ] Generate `handoff.md` and communicate to parent.
