# T-01 traceability matrix

| Requirement | Canonical code path | Verification | Evidence | Result |
|---|---|---|---|---|
| One canonical browser layer | `jarvis/browser/driver.py`, `actions.py`, `agent.py`; `cdp_controller.py` delegates to them | legacy delegation unit cases + `test_legacy_controller_delegates_to_real_canonical_browser` | `test-results.xml`, `artifacts/legacy-action-flow.png` | PASS |
| Real Playwright lifecycle | `PlaywrightBrowserDriver.launch/close` with one owner thread and verified cleanup | lifecycle/thread-affinity tests; managed Chromium E2E fixture | `regression-results.txt`, `test-results.xml` | PASS |
| Navigate and observe real URL/title/DOM | `BrowserActionExecutor.navigate/read_page`, `BrowserAgent.navigate/scrape_url` | 503, 403, error-title, redirect, product, full-flow E2E | `test-results.xml` | PASS |
| Real click | `PlaywrightBrowserDriver.click` through `BrowserActionExecutor.click_element` | full-flow, CDP-flow, and legacy-flow E2E | three PNG artifacts | PASS |
| Real type with clear-first | `PlaywrightBrowserDriver.type_text` through `fill_text(clear=True)` | full-flow and CDP E2E assert the resulting DOM text | Playwright/CDP PNG artifacts | PASS |
| Wait for selector | `wait_for_selector` with stable timeout mapping | delayed element succeeds; missing element returns TIMEOUT | `test-results.xml`, `artifacts/wait-timeout.json` | PASS |
| Real scrolling | validated integer distance passed to real page evaluation | full-flow E2E observes changed `scrollY`; injection/invalid-distance unit tests | `test-results.xml`, `regression-results.txt` | PASS |
| Real screenshot | driver bytes are required and decoded as a non-trivial PNG | full-flow, CDP, and legacy E2E | three PNG artifacts | PASS |
| Browser/session disconnect | driver lifecycle state and Playwright/CDP exception mapping | action-after-close and owner-CDP-disconnect E2E | `artifacts/session-close.json`, `artifacts/cdp-disconnect.json` | PASS |
| Real CDP support | `CDPBrowserDriver` uses `connect_over_cdp`; never mutates only a URL cache | attach, navigate, interact, screenshot, then kill owner browser | `test-results.xml`, CDP PNG/JSON artifacts | PASS |
| Truthful fallback and actual driver | `DriverFactory`, HTTP read-only driver, CLI/core/legacy result metadata | fallback, detection, core-handler, CLI-status unit tests | `regression-results.txt` | PASS |
| Stable result contract | `BrowserResultStatus`, normalized `BrowserActionResult`/`ScrapeResult` | result normalization and failure-propagation unit tests | `regression-results.txt`, negative JSON artifacts | PASS |
| Navigation cannot become a successful scrape | agent clears stale evidence and preserves navigation failure | unit regression + 503/error-title real E2E | `test-results.xml`, `regression-results.txt` | PASS |
| Price truthfulness | `PriceComparisonAggregator` accepts only observed finite JSON-LD/DOM offer evidence; unknown fields remain null and missing links remain empty | price-focused cases + real product page E2E | `test-results.xml`, `regression-results.txt` | PASS |
| Session persistence and secret boundaries | atomic replace/retry, exact-origin localStorage, HTTP-safe capture, scoped host/domain cookies, redirect-hop revalidation, safe logs | atomic/concurrency/cookie/origin/redirect/log-redaction tests | `regression-results.txt` | PASS |
| Exact-origin header boundary | CDP Fetch interception authorizes each request/frame and permanently taints cross-origin redirect chains | same-origin/cross-origin redirect, bounce, subresource and iframe real E2E plus unit regressions | `test-results.xml`, `regression-results.txt` | PASS |
| Browser-compatible cookie canonicalization | `cookie_utils.py`, driver adapters and session manager enforce PSL, UTS46 IDNA, IP/path/expiry semantics | cross-adapter cookie security and session atomic suites | `regression-results.txt`, `negative-tests.txt` | PASS |
| CHIPS variant preservation | CDP cookie capture/apply/delete retains partition key and cross-site-ancestor variant | real Chromium round-trip and targeted-expiry regressions | `test-results.xml`, `regression-results.txt` | PASS |
| Failure evidence is redacted | action, agent and core failure paths clear untrusted title/content and redact URL queries | action/workflow/session/core regression cases | `negative-tests.txt`, `regression-results.txt` | PASS |
| CDP detection/config truthfulness | factory requires a real launch/close handshake; `launch(config)` refreshes the endpoint | fake-HTTP-200 rejection and replacement-endpoint regressions | `regression-results.txt` | PASS |
| Legacy persistence compatibility | explicit `user_data_dir` routes through canonical `BrowserSessionManager` | state survives controller recreation | `regression-results.txt` | PASS |
| Health CLI status truthfulness | READY/LIMITED/ERROR map to exit codes 0/2/1 without unconditional success prose | CLI health status regressions | `negative-tests.txt`, `regression-results.txt` | PASS |
| Core and legacy consumers do not ghost-success | `jarvis/core/app.py`, `jarvis/skills/browser_control/__init__.py` | core-handler and legacy truthfulness suites + cross-thread core E2E | `test-results.xml`, `regression-results.txt` | PASS |
| Deterministic local test site | `tests/browser_test_site.py` provides title, input, button, delayed element, scroll, redirect, iframe, headers, cookies, timeout, statuses, and product | 21 opt-in E2E cases | `test-results.txt` | PASS |
| Rate-limit release blocker | `TokenBucketRateLimiter.acquire` | original 10,000-request stress RED; monotonic-in-lock fix passes 10/10 repetitions | `regression-results.txt` | PASS |
| Shell timeout release blocker | `ShellPlugin.exec_command` | original orphan regression RED; recursive descendant cleanup suite GREEN | `regression-results.txt` | PASS |
| Repository full-suite gate | all `tests/unit/` under documented CI test contract | 2267 passed, 4 skipped, 151 subtests passed, exit 0 | `regression-results.txt` | PASS |

`CANCELLED` is part of the stable public status vocabulary but there is no runtime cancellation
API in the current browser seam, so no cancellation execution is claimed or counted as tested.
