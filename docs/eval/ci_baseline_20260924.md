# CI baseline recovery — 2026-09-24

Base: `9d3c5916ee715eff291ed2364beab9b1e9a815b6` (main was clean).
Branch: `codex/ci-baseline-9d3c591`; dedicated worktree.
Production Python and existing tests are unchanged. Source version remains 5.2.1.

## Acceptance and public seams

- GitHub workflow validation must accept the CI workflow and retain its jobs/dependencies.
- Execute existing CI unit, syntax, import and opt-in Chromium E2E commands on Python 3.13.
- Execute full `tests/` without fail-fast; report failures and skips without upgrading them to success.
- Revalidate T-01 through BrowserAgent/Playwright/CDP plus browser-scoped tests; use only loopback sites.
- No live account/device opt-ins. No main push/merge. Hand off branch, commit, logs, JUnit and screenshots.
- The original assignment DOCX was supplied after the initial handoff and read from its external absolute path. Its D-01/D-02/T-01 rows are now cross-checked in the [DOCX acceptance addendum](../../reports/evidence/ci-baseline-20260924/docx-acceptance.md), with source SHA-256, exact criteria and test/artifact mapping. All 981 source-manifest hashes still match. The document-only follow-up does not constitute a new pytest run.

## Confirmed CI root cause

[Run 35763480258](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/runs/35763480258) at the base SHA completed with failure at the same timestamp it was created, with zero jobs and zero check runs. This alone did not establish the cause.

The run page annotation states: `(Line: 325, Col: 33): Unrecognized named-value: 'runner'. Located at position 1 within expression: runner.temp`.
The original workflow evaluates `${{ runner.temp }}` in `jobs.browser_e2e.env`, which does not support that context. [GitHub context availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability) documents the restriction.

Actionlint 1.7.12 reproduced the same context error (exit 1). Moving the browser-store configuration into a PowerShell step using `$env:RUNNER_TEMP` and `$env:GITHUB_ENV` passes actionlint (exit 0). The install and test steps consume the same isolated browser store.

The unit dependency list also drifted from pyproject: it permitted pytest 9 while the project requires pytest <9, and omitted declared runtime packages. Unit CI now installs `.[browser,dev]` plus the existing elevenlabs dependency and checks pip failure explicitly. This uses the same project dependency source as the browser job. It is separate from the confirmed no-job root cause.

## Environment and experimental controls

See `reports/evidence/ci-baseline-20260924/` for the directly reviewable summary/classification and [the complete evidence ZIP](../../reports/evidence/ci-baseline-20260924.zip) for exact commands, times, exit codes, package versions, raw logs, JUnit and screenshots. On a fresh checkout, extract the ZIP into that evidence directory to use its reproduction scripts.
The local host is Windows with standalone CPython 3.13.15, pytest 8.4.2, and a dedicated venv. This is not a GitHub-hosted Windows Server runner.
Headless/mock audio and the CI compatibility fallback are enabled; fallback does not prove Restricted Token isolation. All external live-test opt-ins are disabled. The existing test-process network guard permits loopback only.

Two local setup findings were isolated:

1. The host shared `pytest-of-MSI` temp directory denied access. The interrupted first attempt is incomplete. Set `PYTEST_DEBUG_TEMPROOT` to a task-private directory; do not report its partial results as a suite verdict.
2. Placing Python under a path containing `JARVIS` causes the existing sandbox path filter to remove stdlib paths, producing `No module named json/csv`. Initial unit run: 2709 passed, 14 failed, 4 skipped, 268 subtests passed / 320.58s / exit 1. The same sandbox group with Python outside the repo: 30 passed, 19 subtests passed / 28.60s / exit 0. No production sandbox changes were made. This is a path-sensitive deployment limitation, not a missing json package and not established flakiness.

## Final results

Results are from base 9d3c591 with the workflow-only patch in this branch. The final commit adds documentation/evidence; production/test source hashes are in source-manifest.json. Historical totals are not current evidence.

| Run | Pass | Fail | Skip | Subtests passed | pytest seconds | Native exit |
|---|---:|---:|---:|---:|---:|---:|
| Unit final | 2723 | 0 | 4 | 268 | 261.12 | 0 |
| Full tests (CI dependencies) | 4189 | 46 | 41 | 268 | 571.15 | -1073740940 |
| Real Chromium/CDP final | 21 | 0 | 0 | 0 | 35.54 | 0 |
| T-01 scoped (12 current browser unit files) | 286 | 0 | 0 | 0 | 12.11 | 0 |
| Wheel after prerequisites | 1 | 0 | 0 | 0 | 8.54 | 0 |
| All 46 failed nodes, after prerequisites | 1 | 45 | 0 | 0 | 42.36 | 1 |

JUnit includes subtest entries; its total is not the count of pytest test functions. Full collection was 4274 items plus 2 collection skips; the console skip total includes those collection skips. See individual *.meta.json for wall-clock seconds, distinct from pytest's elapsed time.

Actionlint original: exit 1 / 0.0816881s; fixed CI plus release workflow: exit 0 / 0.0478398s. Four original CI syntax steps passed (7.7616s combined); the original import-validation step passed (1.3941s). Full collection: 4274 tests / 13.18s / exit 0.

Chromium 153.0.8010.12 (Playwright 1.63.0) executed on loopback. Screenshot and negative-result JSON artifacts cover managed Playwright, real CDP attachment, legacy delegation, timeout and disconnect. T-01 scoped selection is explicitly the 12 current test_browser*.py files; it is not the historical 301-case selection.

## Verdict

Workflow validation: PASS engineering, locally verified. Remote CI after integration: PENDING (no push/PR/run performed by this task).
CI-contract local syntax/import/unit/browser gates: **PASS engineering**. T-01: **PASS engineering**, **PASS fail-closed**, **PASS runtime (loopback Chromium/CDP)** for the available executable seams. Original DOCX cross-check: **complete**, T-01 criteria covered by the recorded evidence. D-01/D-02 remain **PENDING** their required remote CI/main gates.
Full repository baseline: **NOT GREEN** (45 reproducible residual assertions after prerequisite remediation, plus unresolved native shutdown in the full run). Internal pilot **CONDITIONAL GO** is not newly assessed or granted. Product release: **NO-GO**; no **GO** assertion is made.

## Reproduction commands

Run from the task worktree. Keep the Python installation outside paths containing `jarvis` (the existing sandbox filter is path-sensitive). Use a writable private temp root.

```powershell
$python = '../runtime/venv/Scripts/python.exe'
& $python -m pip install '.[browser,dev]' elevenlabs sounddevice pywin32
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD '.baseline-tools/browsers'
& $python -m playwright install chromium
& ./reports/evidence/ci-baseline-20260924/run-tests.ps1 -Name unit-final -TestArgs tests/unit/
& ./reports/evidence/ci-baseline-20260924/run-tests.ps1 -Name full-final -TestArgs tests/
& ./reports/evidence/ci-baseline-20260924/run-tests.ps1 -Name browser-final -TestArgs tests/e2e/test_browser_playwright_e2e.py
$files = @(Get-ChildItem tests/unit/test_browser*.py | ForEach-Object { $_.FullName })
& ./reports/evidence/ci-baseline-20260924/run-tests.ps1 -Name t01-scoped -TestArgs $files
```

The checked-in harness records the command, UTC start, base HEAD, elapsed wall time and native exit code, and emits JUnit plus console output. It explicitly disables external live opt-ins. The full run leaves browser opt-in off; the separate browser run enables it. Do not add counts across overlapping runs.

For full-suite wheel integration, install the build-system prerequisites in the active venv before execution:

```powershell
& $python -m pip install 'setuptools>=72' wheel
& ./reports/evidence/ci-baseline-20260924/run-tests.ps1 -Name wheel-green -TestArgs tests/integration/test_package_version_build.py
$nodes = @(Get-Content reports/evidence/ci-baseline-20260924/failed-nodes.txt)
& ./reports/evidence/ci-baseline-20260924/run-tests.ps1 -Name failures-rerun -TestArgs $nodes
```

The full-suite result below was captured before adding those build prerequisites. The wheel and failed-node reruns were after installation. We did not subtract the repaired wheel test from the recorded full-suite failure count or claim a new full-suite pass. No production Python or test assertion changed between these runs.

## Residual failure ownership

[Per-node classification](../../reports/evidence/ci-baseline-20260924/failure-classification.md) and its JSON enumerate all 46 current failures:

- **1 missing prerequisite resolved:** `setuptools.build_meta` for the existing no-build-isolation wheel test; RED 1 failed/0.99s/exit 1, GREEN 1 passed/8.54s/exit 0.
- **5 confirmed code defects outside workflow/T-01:** zero-area screenshot JPEG exception; explicit zero screen dimensions treated as absent; TTS callback exception kills worker; RSS title retains HTML; whitespace-only welcome pool raises IndexError. These were not patched in this task.
- **24 test-contract/environment mismatches:** e.g. wildcard CORS, missing SafetyGate confirmation, Labs opt-in absent, mock audio bypassing WAV playback, unconfigured Telegram dispatcher, stale CLI/overlay output, and outdated audio mocks. Security gates were not weakened to satisfy these assertions.
- **16 reproduced contract/fixture cases requiring owner review:** routing precedence/long-input expectations, weather pipeline, healing fixture state, gesture/voice flow, startup/logging semantics and Spotify behavior. Their exact assertion/traceback is captured; they are not automatically labeled production bugs or flaky tests.
- **Flaky:** none established among the 45 remaining failed assertions: all 45 failed again in the reduced rerun (45 failed, 1 passed / 42.36s / exit 1). This does not prove the entire suite has no flakes.

The full test process completed its JUnit/pytest summary, then exited **-1073740940 (0xC0000374)**. The final log includes an STT executor-shutdown error. The reduced rerun exited 1 normally. Native teardown cause is **PENDING**; no dump was collected and that log line does not prove causation.

Skip inventory for full tests: 21 opt-in browser cases (separately passed), 6 integration opt-ins, 5 OpenCV fixture skips, 3 matplotlib tests, 1 Vosk test, 3 external network probes blocked/unreachable, and 2 collection skips (biometrics dependency and live infrastructure opt-in). These are not runtime passes. Unit has 3 matplotlib + 1 Vosk skip.

## Integration handoff

The integration agent should review the workflow diff, preserve the existing failure inventory, and create a new remote CI run on its integration/PR revision. The run at 9d3c591 remains a historical failure; local validation does not alter it. No main push/merge or remote run was performed here.

Before claiming a repository-wide green baseline, resolve the product/test-owner items above and investigate the full-process shutdown exit. The original T-01 DOCX criteria have now been checked against current executable evidence (see addendum). D-01/D-02 cannot be marked DONE until the required CI gates pass on the integration/main revision. The immutable ZIP predates DOCX receipt; the addendum supersedes its DOCX-pending statements only.
