# Installed applications implementation plan

> **For agentic workers:** Execute task-by-task using superpowers:executing-plans; keep the existing uncommitted Windows fixes intact. No commit/push until the repository full-suite gate passes.

**Goal:** Resolve applications installed on the current Windows machine without manual executable paths.
**Architecture:** Local discovery feeds an immutable application catalog. Exact normalized lookup returns one target, ambiguity, or absence. Controller launches only catalog targets; no user text becomes shell code.
**Tech Stack:** Python stdlib, Windows PowerShell Get-StartApps, winreg App Paths.
**Spec:** User-approved design in this conversation: Windows discovery first, no remote devices/HA; truthful launch verification, no arbitrary shell execution.

## Global constraints

- Preserve dirty worktree; no secrets or full inventory in remote reports.
- No false-success: dispatch acknowledgement is not verified window success.
- No fuzzy automatic launch, no scanning all drives, no UAC bypass.
- Stage 1 below is not the whole approved roadmap: disk persistence, portable folder UI, remembered choices, background refresh and all-machine runtime acceptance remain separate deliverables.

## Task 1 — Catalog and discovery

Files: create `jarvis/automation/app_catalog.py`, `tests/unit/test_app_catalog.py`.
Public seam: `InstalledApp(name, target, kind)`, `ApplicationCatalog(provider=None).resolve(name)` returns tuple of exact matches; `refresh()` updates cache, `errors` reports discovery problems.

- [ ] Write tests for Unicode/case normalization, exact matching, ambiguous targets, duplicate identity, dangerous maintenance entries and discovery exceptions.
- [ ] Run `.venv\Scripts\python -m pytest tests/unit/test_app_catalog.py -o addopts='' -q`; observe missing feature failures.
- [ ] Implement bounded Get-StartApps discovery plus HKCU/HKLM App Paths, read-only, fixed commands, process timeout. Cache in memory with lock and TTL.
- [ ] Repeat the test command until green; read-only local smoke check prints counts only.

## Task 2 — Controller and command integration

Files: modify `jarvis/automation/control.py`, `jarvis/llm/router.py`; extend catalog tests.
Consumes `ApplicationCatalog.resolve(name)`; produces `ComputerController.open_installed_app(app_name)` structured failure or verified process result.

- [ ] Write a router→controller test for `mở ứng dụng Example Editor`, ambiguity and unavailable discovery.
- [ ] Run the new cases RED, then register an explicit installed-app command using existing app_open handler without bypassing dispatcher.
- [ ] Launch EXE with an argv list, shell=False; verify process remains alive. Store/Start AppID launch acknowledgement must return unverified, not fabricated success.
- [ ] Run existing app/web/H07 regressions and scoped new suite, write JUnit evidence.

## Task 3 — Evidence and release gate

- [ ] Run full-suite diagnostic; report failures without changing unrelated contracts to force green.
- [ ] Update CHANGELOG.md, README.md, docs/ROADMAP.md with exact counts and limitations.
- [ ] Review changes and run git diff --check. Commit/push only after the full suite is green; otherwise record the blocker.

## Deferred acceptance requirements

Execution checkpoint: Task 1 initial implementation and Task 2 explicit command
delivered with 14 new tests, scoped 90 passed + 25 subtests. Task 3 documentation
and diagnostic run delivered; release gate remains failing. This checkpoint
does not complete deferred requirements or certify all Windows applications.

- Correlate Store/launcher windows, focus existing instances and avoid process-only success claims for UI visibility.
- User choice flow and persistence for ambiguity; portable directory opt-in.
- Startup/background refresh and atomic on-disk cache.
- Cross-machine real launch matrix, not inferred from local discovery or mocks.
