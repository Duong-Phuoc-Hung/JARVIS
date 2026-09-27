# Assignment DOCX acceptance cross-check — 2026-09-24

The user supplied the external DOCX after the initial baseline handoff. It was read successfully, without modifying or copying the original. This addendum supersedes only the earlier **DOCX unavailable / cross-check PENDING** statements. The original evidence ZIP is immutable and still records the state of the initial handoff.

- Source: `D:\JAVIS\JARVIS-main\JARVIS-main\docs\JARVIS_Phan_cong_3_thanh_vien_Hoa_Hung_Thai.docx`
- SHA-256: `8ddf67c448c05ced363080e9a55a52a716ad7ed9453353a2deaacf68405616ac`
- DOCX planning baseline: `75ae962fcafa2a02561dd4e2efd25e598afafe7d` (2026-09-10), not the current test revision.
- Current review HEAD: `26b257551f83167f13be3a8b8cf7a6f987d5ad57`; tested source base: `9d3c5916ee715eff291ed2364beab9b1e9a815b6` with the branch workflow patch.
- All **981** source-manifest file hashes match the working tree. No production, test or workflow changes were made for this follow-up. Existing fresh results therefore remain applicable; no suite was rerun for this documentation-only reconciliation.
- Exact DOCX table rows for D-01, D-02 and T-01, source/evidence hashes and verified JUnit case identities are in [docx-acceptance.json](docx-acceptance.json). References use task IDs and table content, not unverified Word page numbers.

## T-01 — assigned to Thái, P0

Exact required work: “Dựng test browser; validate navigate, click, type, wait selector, timeout, disconnected session bằng browser thật.”

Exact DONE condition: “Có E2E browser flow thật; no-session/disconnect luôn fail; không ghost success.”

Public seams: `BrowserAgent.navigate`, `BrowserActionExecutor.fill_text/click_element/wait_for_selector`, `PlaywrightBrowserDriver`, `CDPBrowserDriver`, and the legacy `BrowserCDPController`/browser skill contracts.

| DOCX criterion | Current test and observable evidence | Result |
|---|---|---|
| Real navigate/click/type/wait-selector flow | `test_real_browser_full_action_and_dom_flow`: real loopback navigation/title, input and click reflected in DOM text `Ada Lovelace`, delayed selector, DOM and 1280×800 screenshot (`browser-artifacts/playwright-action-flow.png`) | PASS runtime |
| CDP action path | `test_real_cdp_attach_navigates_and_interacts`: attaches to real Chromium endpoint, checks driver type and DOM text `CDP verified`; `cdp-action-flow.png` | PASS runtime |
| Timeout fails truthfully | `test_wait_timeout_has_stable_timeout_result` and `test_navigation_timeout_fails_closed`: `success=false`, `TIMEOUT`, `BROWSER_TIMEOUT`; `wait-timeout.json` and `navigation-timeout.json` | PASS fail-closed; PASS runtime |
| Disconnected session fails truthfully | `test_action_after_session_close_reports_disconnected` and `test_real_cdp_disconnect_fails_closed`: stop real session/close owner Chromium, then click returns `success=false`, `DISCONNECTED`, `BROWSER_DISCONNECTED`; `session-close.json`, `cdp-disconnect.json` | PASS fail-closed; PASS runtime |
| No active session | `TestBrowserSkillContract.test_close_without_active_session_is_disconnected`: browser skill with no controller returns `success=false`, `DISCONNECTED`, `BROWSER_NO_ACTIVE_SESSION`. The closed real-session cases above also exercise actions with no live session. The skill case is unit evidence, not a live-process claim. | PASS engineering; PASS fail-closed |
| No ghost click/type through legacy caller | `test_legacy_controller_delegates_to_real_canonical_browser`: real DOM includes `Legacy verified`, screenshot decoded and saved as `legacy-action-flow.png` | PASS runtime |

All seven named E2E cases are present and passed in `browser-final.xml` (the complete run has **21 passed / 0 failed / 0 skipped**, **35.54s**, native **exit 0**). The no-active-session unit case is present and passed in `t01-scoped.xml` (**286 passed / 0 failed / 0 skipped**, **12.11s**, native **exit 0**). The tests and source were inspected alongside their JUnit outcomes; assertions and negative JSON establish observable results rather than treating a successful launch or screenshot alone as proof.

**T-01 DOCX acceptance cross-check complete:** PASS engineering, PASS fail-closed, PASS runtime for the tested loopback Chromium/CDP scope. No external account/device/site was exercised, and no universal browser-compatibility or Product GO claim is made.

## D-01 / D-02 — assigned to Hưng, P0

D-01 requires Syntax, Unit, Import and Pipeline Summary green **on main**. D-02 requires a clean environment and CI pass, including IMAP/TTS/volume/full-unit parity. The original DOCX refers to old CI #200; this task explicitly targets run 35763480258 at 9d3c591, whose invalid `runner.temp` context was proven by the GitHub annotation and actionlint RED/GREEN.

Local dedicated-venv unit results are **2723 passed / 4 skipped / 268 subtests**, **261.12s**, exit **0**; syntax/import and browser checks passed. This host is not the GitHub Windows runner. The local results close neither the hosted-runner parity requirement nor the main Pipeline Summary gate. **D-01 and D-02 remain PENDING remote CI after integration**, not DONE. The task does not authorize pushing or merging main.

Full `tests/` remains **4189 passed / 46 failed / 41 skipped**, **571.15s**, native **exit -1073740940 (0xC0000374)**. After adding build prerequisites, the failed-node rerun was **45 failed / 1 passed**, **42.36s**, exit **1**. Native teardown is unresolved. These are the current recorded runs, not recomputed counts or new test executions.

See [the baseline report](../../../docs/eval/ci_baseline_20260924.md) and [per-node failure inventory](failure-classification.md). Remote CI: PENDING. Full baseline: NOT GREEN. CONDITIONAL GO was not assessed; Product release: NO-GO.

## Replay evidence verification

Run `python -X utf8 reports/evidence/ci-baseline-20260924/verify-docx-acceptance.py` from the repository. Optionally pass the DOCX absolute path as the first argument. The verifier reads raw evidence directly from the immutable ZIP, so extraction is unnecessary. This run verified 3 DOCX rows, 981 source hashes and 8 named JUnit cases: script 0.205557s, process 1.6280681s, exit 0. It does not execute pytest.
