# CI baseline evidence — 2026-09-24

The complete raw evidence (console, JUnit, process exit metadata, GitHub metadata/annotation, dependencies, validator RED/GREEN, browser screenshots/negative JSON and reproduction scripts) is preserved in `../ci-baseline-20260924.zip`.

Extract that ZIP into this directory to restore all referenced files when working from a fresh checkout. `summary.json` and `failure-classification.*` remain directly reviewable in Git. Console pass/skip counts and JUnit subtest-inclusive totals are intentionally separate.

Current gates: unit 2723 passed/4 skipped/exit 0; browser 21 passed/exit 0; scoped browser 286 passed/exit 0. Full: 4189 passed/46 failed/41 skipped, native exit -1073740940 after JUnit. Failed-node rerun after build prerequisites: 45 failed/1 passed/exit 1. No full-green or remote-CI-green claim.

`unit-baseline` is the deliberately stopped Temp-permission attempt; its exit -1 is not a suite result. `unit` is the completed in-repo-interpreter diagnostic (14 failures due to sandbox path filtering). Final named runs use Python outside the repository. `browser` is the earlier browser run; `browser-final` is the final browser evidence and screenshots.

Original DOCX assignment has now been read: see `docx-acceptance.md` and `docx-acceptance.json` for verified T-01 criteria and D-01/D-02 remote-CI blockers. The immutable ZIP predates DOCX receipt; this addendum supersedes its DOCX-pending statements only. After extracting the ZIP, restore the tracked README from Git to retain this update. See `../../../docs/eval/ci_baseline_20260924.md` for scope and handoff.
