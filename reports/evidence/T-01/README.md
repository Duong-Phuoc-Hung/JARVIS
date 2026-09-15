# T-01 — Browser CDP/Playwright real end-to-end evidence

## Certification result

**DONE — functional T-01 acceptance and repository-wide unit release gate passed.**

The deterministic loopback suite launched real Playwright-managed Chromium, attached to a
separately owned Chromium through `connect_over_cdp`, and exercised the legacy adapter through
the same canonical seam. All 21 real-browser cases passed. The browser-scoped regression suite
passed all 301 cases, including exact-origin header isolation and browser-compatible cookie,
session, PSL/IDNA/IPv6/CHIPS/expiry behavior.

The final full `tests/unit/` gate used the repository's explicit CI test contract,
headless/mock-audio settings, and a writable isolated profile. It passed with 2267 tests,
4 skips, 151 subtests, no failures, and no errors. Runtime version remains 5.1.3.

## Real-browser proof

- `test-results.txt` / `test-results.xml`: final 21/21 real Playwright/CDP E2E artifact run,
  exit 0, 56.91 seconds.
- `artifacts/playwright-action-flow.png`: managed Chromium after real clear-first typing,
  click, delayed-element wait, scroll, DOM read, and screenshot capture.
- `artifacts/cdp-action-flow.png`: independently launched Chromium reached through a real CDP
  endpoint and manipulated through the canonical driver.
- `artifacts/legacy-action-flow.png`: the legacy controller delegated to the canonical real
  browser implementation.
- `artifacts/*.json`: stable, redacted TIMEOUT and DISCONNECTED outcomes.

The website and CDP endpoint were loopback-only. No external credential, private cookie,
email, or session secret was required or retained. Mock cases are unit evidence and are not
counted among the 21 E2E cases.

## Supporting records

- `environment.json`: redacted runtime and dependency inventory.
- `traceability.md`: requirement → code → test → artifact matrix.
- `negative-tests.txt`: fail-closed/security outcomes and stable codes.
- `regression-results.txt`: scoped and repository-wide test-gate results.
- `lint-results.txt` and `compile-results.txt`: final static validation. Task-scoped Ruff is
  green; the 118 pre-existing whole-repository Ruff findings are recorded rather than hidden.
- `evidence-manifest.json`: commands, exit codes, source state, and SHA-256 artifact inventory.
- `.gitattributes`: LF text normalization and binary PNG handling for reproducible hashes.
