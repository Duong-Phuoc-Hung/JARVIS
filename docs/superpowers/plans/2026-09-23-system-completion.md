# JARVIS Current-System Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the current verified blockers, stabilize the test contract, and produce fresh evidence for each release gate without fabricating runtime success.

**Architecture:** First resolve test/spec contradictions at the seam where they occur: healing tests use an explicit simulation contract while production reads telemetry only; audio fixtures reset their own state; packet capture remains Labs-gated. Then add a small shared result/health model and migrate only the dispatcher-facing seam, preserving compatibility for existing handlers.

**Tech Stack:** Python 3.13, pytest, dataclasses/enums, existing dispatcher/router/Windows backends, security scanner, Ruff, XML evidence artifacts, Markdown/DOCX SRS.

**Spec:** `docs/SRS_JARVIS_Current_System_2026-09-23.md`

## Global Constraints

- Never call `set_ram()` from production healing code to fabricate reclamation.
- `READY` is valid only after backend confirmation; fallback is `LIMITED` or `UNAVAILABLE`.
- Labs features remain opt-in and fail-closed when explicit/global configuration disables them.
- Every production behavior change gets a failing test before implementation.
- Full-suite numbers must be rerun after code changes; old counts are not evidence.

## Review Focus

- Healing telemetry must distinguish observed RAM change from test simulation.
- Audio and virtual endpoint state must not leak between tests.
- Packet capture must not bypass Labs or fabricate packet counts.
- Result/Health adapters must preserve existing handler responses.
- Windows runtime evidence must distinguish mock/headless from real device/process output.

---

### Task 1: Reconcile healing telemetry contract

**Files:**
- Modify: `jarvis/healing/terminator.py`
- Test: `tests/test_e2e_scenarios.py`, `tests/unit/test_healing_truthfulness.py`

- [ ] Write a regression test using an explicit test-only telemetry transition hook (not `set_ram`) and assert `reclaimed_ram` is calculated from observed before/after values.
- [ ] Run the regression test and confirm it fails because the current fixture has no transition seam.
- [ ] Add a narrow optional `on_process_terminated(pid, name) -> None` simulation hook consumed only by injected test providers; production providers do not implement it.
- [ ] Run healing truthfulness and E2E healing tests; ensure failed termination never invokes the hook and production paths remain read-only.

### Task 2: Stabilize audio fixture state

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/unit/test_computer_control.py`

- [ ] Add a fixture-level reset assertion for the virtual endpoint mute state before each test.
- [ ] Run the isolated regression and verify it fails when endpoint state leaks.
- [ ] Reset only the test double in fixture setup/teardown; do not unmute real devices from production code.
- [ ] Run the full computer-control module twice and verify deterministic results.

### Task 3: Verify full unit and security gates

**Files:**
- Modify: `docs/eval/runtime_fix_verification_20260923.md`, `CHANGELOG.md`, `docs/ROADMAP.md`
- Test: full `tests/unit`, security subset, scanner and Ruff.

- [ ] Run fresh full unit suite and save JUnit XML.
- [ ] Run security tests and scanner against all `jarvis/` files.
- [ ] Run Ruff on changed files.
- [ ] Record exact counts and remaining failures; do not mark GO while any failure remains.

### Task 4: Introduce shared Result/Health seam

**Files:**
- Create: `jarvis/core/result_model.py`
- Modify: `jarvis/core/dispatcher.py`, `jarvis/core/models.py`
- Test: `tests/unit/test_result_model.py`, dispatcher normalization tests.

- [ ] Write tests for `SUCCESS`, `ERROR`, `TIMEOUT`, `BLOCKED`, `UNAVAILABLE`, `NOT_CONFIGURED` and health statuses.
- [ ] Run tests RED.
- [ ] Implement immutable dataclasses/enums with serialization and compatibility conversion from existing `ActionResult`/dict results.
- [ ] Adapt dispatcher normalization only; do not rewrite every connector in one change.
- [ ] Run dispatcher/core regression tests and verify existing action contracts remain compatible.

### Task 5: Run the 10-workflow Windows matrix

**Files:**
- Create: `docs/eval/workflow_10_windows_runtime_20260923.md`
- Test: `tests/e2e/test_beta_v1_acceptance.py` plus opt-in live runner.

- [ ] Define one evidence row per workflow: command, intent, action, process/window/URL, status, timing and confirmation.
- [ ] Run mock/headless acceptance separately from opt-in live Windows execution.
- [ ] Mark unavailable hardware/dependency as `LIMITED`/`UNAVAILABLE`, never `READY`.
- [ ] Publish pass rate and per-workflow floor.

### Task 6: Voice, discovery and release gates

**Files:**
- Modify: `docs/eval/runtime_fix_verification_20260923.md`, `README.md`, `docs/ROADMAP.md`

- [ ] Run voice onboarding checks with real/absent devices and classify health correctly.
- [ ] Run installed-app catalog probe and cross-machine limitations.
- [ ] Run installer/update/rollback/support-bundle checks where resources exist.
- [ ] Update SRS and release verdict; use `NO-GO` until every gate has runtime evidence.

