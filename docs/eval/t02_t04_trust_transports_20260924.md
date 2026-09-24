# T-02 / T-03 / T-04 — engineering handoff, 2026-09-24

Base: `9d3c5916ee715eff291ed2364beab9b1e9a815b6`, isolated branch `codex/t02-t04-trust-transports`.
Source version remains `jarvis.__version__ = 5.2.1` (unreleased). This task does not merge/push main.
The main checkout was clean at inspection. Earlier CI-baseline work on a different branch is not included.

## Acceptance and evidence boundaries

Read AGENTS.md, AUDIT_FRAMEWORK.md, READINESS_DASHBOARD.md, ROADMAP.md and the external assignment DOCX at
`D:\JAVIS\JARVIS-main\JARVIS-main\docs\JARVIS_Phan_cong_3_thanh_vien_Hoa_Hung_Thai.docx`.
DOCX SHA256: `8ddf67c448c05ced363080e9a55a52a716ad7ed9453353a2deaacf68405616ac`.
T-02 requires separating webpage data from trusted instruction, preventing high-risk actions and passing adversarial regression.
T-03 requires real test-bot send/receive, authorized senders, truthful errors and real round-trip smoke.
T-04 requires real OA outbound/inbound, truthful status/errors and real message evidence; mock IDs are allowed only in explicit test mode.
The user's current requirements add actual loopback E2E, 30-second confirmation expiry, Unicode/Vietnamese spoofing,
Telegram reconnect/deduplication and forged-webhook tests. Historical test counts and old live sends are not current evidence.

Public seams under test: browser results / legacy controller; ReActAgent.run; LLMIntentRouter.parse_intent,
parse_external_content and execute_intent; JarvisApp.process_text_command; ReActTaskEngine.execute_step;
ActionDispatcher.dispatch_action; Telegram send_message/poll_updates/handle_inbound_message/start;
Zalo send_message/handle_webhook/start_webhook and the real `/zalo/webhook` HTTP endpoint.

## T-02 trace and enforcement

1. Canonical BrowserActionResult/ScrapeResult and legacy PageInfo/ElementResult/URL/links carry `UntrustedText` provenance.
   PromptGuard.clean_text retains that marker. Sanitization is supplementary risk reduction, not the authorization decision.
2. A marked browser string cannot enter the app command or router user-instruction channel. App rejection happens before
   stripping text, logging it as a user turn or invoking the planner. Marked new ReAct goals are restricted from their first action.
3. ReAct wraps tool observations and sends **every model-selected action** through its dispatcher.
   After the first observation, an external action scope denies all actions unless the trusted host supplied exact one-use grants.
   All tool observations are treated as data regardless of the tool's name, including custom browser aliases.
4. Router context is untrusted even when serialized to ordinary strings. `parse_external_content(trusted_instruction, data,
   authorized_actions=...)` is the explicit boundary for JSON/IPC content. Only host/UI code supplies grants; model output cannot.
   `execute_intent` installs this scope around dispatch. Planner direct handlers also reject external parameters/scopes.
5. The shared sync/async dispatcher safety gate rejects unauthorized scope/marked action names or parameters **before** checking confirmation
   tokens, permissions or running a handler (`UNTRUSTED_ACTION_BLOCKED`). Ordinary high-risk actions still require the existing
   payload-bound, one-use, 30-second confirmation. Added high-risk aliases cover agent Python/write/send tool names.
6. Existing app voice routing consumes trusted user input, then dispatches; canonical browser handlers return observations.
   The rule-driven DAG planner has no discovered automatic webpage-to-LLM feedback loop. Its custom-handler bypass is now
   checked for external authority too. The separate ReAct model loop is the actual automatic observation feedback path.

Real Chromium navigates real loopback HTML carrying Vietnamese, Unicode and forged system/developer payloads in DOM,
scrape, URL, metadata and browser results. The external model boundary is deliberately controlled to emit malicious calls:
it is an adversarial model stub, **not a live cloud LLM**. Browser, router, dispatcher, scope and safety gate are production code.
Assertions verify the victim file remains, the subprocess sentinel is absent, and the loopback exfiltration sink receives zero POSTs.
A positive flow fills and clicks a real form using exact host grants and rejects changed parameters. The confirmation test waits
30.1 seconds on a real clock; a page cannot use a real pending token or revive it after expiry.

This is an application authorization boundary, not OS isolation from hostile Python plugins. `UntrustedText` is not a durable
serialization format: JSON/IPC callers must use the explicit external-data/context seam, never recast page text as trusted user text.
Direct driver/private tool calls and deliberately bypassing host integration are not sandboxed. Multi-step browser actions now need
explicit host grants after observing external data; inferring new write permissions from webpage/model text is intentionally denied.

## T-03 implementation and runtime gate

Telegram validates HTTP status, API `ok` and message IDs; rejects missing credentials, unauthorized senders/chats, malformed
responses, timeout/offline/auth errors and HTTP/API rate limits. Transport exceptions/bodies are not echoed. Replies are sent only
for successful command handling; dispatcher refusal cannot become a successful command. Missing dispatcher and failed OS lock
return explicit failures. `/skills` no longer fabricates a list without a dispatcher.

Polling is serialized, enforces retry-after cooldown, recovers on subsequent requests and records redacted inbound/outbound IDs,
HTTP status, processing outcome and timestamps. Optional token-bound offset persistence uses serialized atomic replacement with
Windows retry; app initialization enables it. Checkpoint failure is fail-closed. Offset is persisted **before** command execution:
this is at-most-once, and a crash can lose an action/reply. It is not exactly-once delivery. One consumer per bot/checkpoint is required;
there is no cross-process leader election. `poll_updates.ok` is the transport outcome; inspect processed statuses and reply_ok too.
The legacy list adapter `poll_once` remains available. Stop can return false while a bounded HTTP request is still finishing.

The owner explicitly confirmed that bot ID, chat ID, sender ID and current token location have not been provided.
Status: **PENDING_CREDENTIALS**. The historical @JARVISAssistantTest_bot name is not current authorization.
No real Telegram request/send was authorized or performed as live acceptance in this task. Controlled API responses test the
engineering contract only. No old message ID or send-only evidence is reused as a current round trip.

Required to resume: explicit test bot username/ID, allowed chat ID and sender ID; a securely provisioned token via an environment
or credential-store entry name (do not paste token into chat); operator availability to send the agreed nonce and safe test command.
Use a dedicated bot without a competing getUpdates consumer/webhook, or explicitly authorize the necessary test configuration.
Verify both outbound acknowledgement and inbound update processing/reply with redacted IDs/status/time before PASS runtime.

## T-04 implementation and runtime gate

OA text sends use `/v3.0/oa/message/cs`, validate HTTP/provider status and a nonempty message ID, refuse recipients outside the
allowlist, disable redirects, enforce rate limits/cooldown and return explicit auth/network/timeout/response errors. Outbound
records exclude token/body/recipient. Explicit `is_mock=True` stays a unit adapter and cannot authenticate the real webhook route.

The webhook checks `X-ZEvent-Signature: mac=<digest>` over SHA256(app_id + exact raw body + timestamp + OA secret), constant-time
comparison, app/OA binding, timestamp freshness, sender whitelist, payload bound and event schema before dispatch. The socket
binds synchronously; failure cannot masquerade as a running listener. Duplicate message events do not rerun commands. Evidence is
redacted, and metrics failures return STATUS_UNAVAILABLE instead of fictional Online/Active status. Listener state is local only;
status output explicitly does not claim a verified server round trip.

The HTTP integration test uses an actual loopback listener and requests, plus synthetic signed fixtures; the outbound OA server
boundary is controlled. This is **not** live Zalo evidence. Replay cache is bounded/in-memory within the freshness window; it does
not survive restart. Events are consumed before side effects; failed replies are not automatically resent on duplicate delivery.
Production TLS/public webhook registration and verified OA authorization remain operator responsibilities.

The owner explicitly confirmed that verified OA/recipient/callback/token/secret are unavailable for this task.
Status: **PENDING_ZALO_OA_VERIFICATION**; real API sends are not authorized.

Required to resume: verified test OA ID and app ID, explicitly allowed test recipient, access-token and OA-secret credential entry
names, an authorized public HTTPS webhook endpoint routed to this listener, and a human able to send the test inbound message.
Do not confuse the OA secret used in the documented MAC with an arbitrary HMAC secret. Real Zalo send+receive evidence must
include server message IDs, status, timestamps and handler result, with secrets and personal message text omitted.

Protocol references: [Telegram Bot API](https://core.telegram.org/bots/api),
[Zalo OA webhook signature](https://stc-developers.zdn.vn/docs/v2/official-account/webhook/tin-nhan/su-kien-official-account-gui-tin-nhan-cho-nguoi-dung?lang=vi&ts=1786320000079),
[Zalo OA v3 message endpoint](https://stc-developers.zdn.vn/docs/v2/official-account/tin-nhan/tin-tu-van/gui-tin-tu-van-trich-dan?lang=vi&ts=1783296000075).

## Reproduction and artifacts

All raw command arrays, base HEAD, UTC start, wall time and native process exit codes are in
`reports/evidence/T02-T04/<run>.json`; pytest summaries are in `.txt`, test-level evidence in JUnit `.xml`.
Base HEAD alone does not identify the uncommitted patch: `source-manifest.json` fingerprints the final source/test bytes.
Early RED/GREEN artifacts refer to intermediate working trees and must not be cited as final-revision certification.
The audit runner is archived as `run_pytest.py`; its absolute paths describe this host and must be changed on another machine.
Test Python is the reused Python 3.13.15 venv from the CI baseline worktree; Chromium is Playwright-managed revision 1243.
This was not a clean-machine dependency install. The wrapper selects headless/mock audio, sandbox compatibility opt-in,
dummy Google key, disables live network/infra/IMAP opt-in suites, and enables the real loopback browser suite.
Run metadata provides the complete pytest command; addopts is cleared, timeout=120s, JUnit enabled.
Full tests include the browser E2E opt-in here, in addition to the standalone browser run.

The RED sequence includes valid reproductions for ReAct tool authority, raw browser text, serialized context, legacy URL,
fresh agent goals, app entry point, planner direct handlers, Telegram API failures/replay/checkpoint/dispatcher/lifecycle,
Zalo MAC/message-ID/webhook/error redaction, and unavailable status/capabilities. There were also test-harness errors:
one wrong browser test filename (exit 4), an initial missing router constructor argument, and a loopback fixture missing
Content-Type. Those are explicitly not product-failure evidence. A unit regression caught circular-payload recursion and was fixed. Another regression expected the old fictional
Zalo Online/Active wording; that assertion now requires measured metrics and explicit NOT_LISTENING/NOT_VERIFIED instead.
Direct DOM-to-dispatcher action-name escalation was also reproduced and blocked, independently of payload checks.

Two historical Telegram assertions also conflicted with the current fail-closed contract. They are in scope: the explicit photo
mock now receives a dummy test token, and `/exec` without a dispatcher must return 503/DISPATCHER_UNAVAILABLE without echoing
the attempted command. Both failures are preserved in prior full logs, and the corrected Telegram subset passed (5 tests).
No production code changed after the final unit/browser runs; these last corrections only changed two legacy test files.
The evidence runner's console encoding was also made UTF-8 after Windows cp1252 failed while printing a completed full log;
the raw log, JUnit and native pytest exit code had already been saved and were not lost.

## Final measured results and verdict

| Run | Pass | Fail | Skip | pytest seconds | Wall seconds | Native exit |
|---|---:|---:|---:|---:|---:|---:|
| `unit-final-acceptance` | 2751 | 0 | 4 | 222.23 | 224.84 | 0 |
| `browser-acceptance` | 51 | 0 | 0 | 99.51 | 100.92 | 0 |
| `full-handoff` | 4278 | 45 | 20 | 700.10 | 703.47 | 1 |

Unit and full runs also report **268 passed subtests**, separately from the passed-test counts above. Browser acceptance is
**30 T-02 cases + 21 existing browser cases**; all 51 also pass in the final full run. These are fresh local results, not old counts.
The production code and unit/browser test files did not change after their final runs; the last two edits were legacy Telegram
fixtures/assertions, followed by the complete `full-handoff` run. Final source/test bytes match `source-manifest.json`.

Additional measured regressions: transports-final 68 passed / 0 failed (7.14s, wall 8.53s, exit 0; earlier patch stage),
compatibility-and-flake-rerun 31 passed (9.80s, wall 13.30s, exit 0), legacy-comms-contracts-green 5 passed / 28 deselected
(1.71s, wall 2.91s, exit 0), and handoff-order-rerun 2 passed (2.43s, wall 4.55s, exit 0). None is live Bot/OA evidence.

Final full-suite failures: **43 reproduced base failures** (5 confirmed code defects, 22 test-contract mismatches,
16 contracts requiring owner review) plus **2 shared-process/order-dependent failures**. The two latter cases passed isolated
rerun; one exhausts a finite global monotonic mock, the other captures a background PowerShell SMART-health poll in the global
Popen mock. Their root cause remains open. Earlier runs also exposed transient voice latency/silence and triple-clap failures;
those were retained in artifacts, not silently discarded. The full suite remains **FAIL** despite successful targeted reruns.

The 5 confirmed defects concern zero-area vision ROI, TTS callback exceptions, zero screen dimensions, HTML in RSS titles,
and an empty filtered welcome-phrase pool. These areas were not changed here. Remaining shell/labs/voice/route assertions need
separate owners; do not remove fail-closed gates to make them green. See the exhaustive
[final failure list](../../reports/evidence/T02-T04/full-handoff-failures.md) and JSON with current assertion messages.
Two historical Telegram failures were **in scope and fixed**, rather than classified away as baseline debt.
No new missing package caused the final failures; runtime resources behind opt-in suites remain unverified. All 20 skip reasons
are recorded in `skip-reasons.json` and JUnit.

Static checks: 20 changed Python files parse successfully. Ruff exits **1** with 8 warnings (6 I001, 1 B023, 1 E401),
all matching warnings in the corresponding base source; no new warning is attributed to this patch. `git diff --cached --check` passes for code/docs. The all-files check reports trailing whitespace in
raw pytest console/JUnit evidence; those artifacts are deliberately preserved rather than rewritten.
Do not call the whole-repository lint/CI gate green. GitHub-hosted CI was not run on this branch; the separate CI-baseline
workflow repair (`codex/ci-baseline-9d3c591`, commits `26b2575` / `e855da4`) is not included here.

| Scope | Engineering | Fail-closed | Runtime | Pilot / release |
|---|---|---|---|---|
| T-02 audited browser-to-action seams | PASS engineering | PASS fail-closed | PASS runtime **for real loopback enforcement**, with adversarial external-model stub | No global CONDITIONAL GO or GO |
| T-03 Telegram transport | PASS engineering (scoped) | PASS fail-closed | **PENDING_CREDENTIALS**, owner confirmed | Not DONE; no CONDITIONAL GO/GO |
| T-04 Zalo OA transport | PASS engineering (scoped) | PASS fail-closed | **PENDING_ZALO_OA_VERIFICATION**, owner confirmed | Not DONE; no CONDITIONAL GO/GO |
| Whole repository / hosted CI | Full regression FAIL | No global certification | Hosted CI NOT_RUN | **NO-GO** |

Handoff: isolated branch `codex/t02-t04-trust-transports`; commit identifier is provided with the handoff response.
CHANGELOG, README and ROADMAP are committed together with code/tests/evidence. The main checkout remains untouched.
`.task-tools/` contains local scratch profiles/temp files and is intentionally excluded from the commit; reproducible runner,
commands, results and comparisons are archived in `reports/evidence/T02-T04/`.
