# T-01–T-07 integration acceptance — 2026-09-27

Branch: `codex/t01-t07-integration`; base main `9d3c5916ee715eff291ed2364beab9b1e9a815b6`.
Inputs verified by Git: CI `e855da4`, browser/Telegram/Zalo `9e7b977`, Discord/IMAP/HA `eb06735`.
Merge commits preserve all three histories; source version remains 5.2.1, unreleased.
[Draft PR #50](https://github.com/Duong-Phuoc-Hung/JARVIS/pull/50). No main push or merge.

## Requirements and evidence matrix

Read AGENTS.md and AUDIT_FRAMEWORK.md. Original DOCX read at
`D:\JAVIS\JARVIS-main\JARVIS-main\docs\JARVIS_Phan_cong_3_thanh_vien_Hoa_Hung_Thai.docx`;
SHA256 `8ddf67c448c05ced363080e9a55a52a716ad7ed9453353a2deaacf68405616ac`.
Exact task rows: `reports/evidence/T01-T07-integration/docx-requirements.json`.
The following criteria combine those rows with the user's stricter end-to-end gates.

| Task | Acceptance / public seam | Production code | Fresh test / runtime evidence | Verdict / blocker |
|---|---|---|---|---|
| T-01 | Real navigate, click, type, selector wait; timeout, no session, disconnect fail truthfully | browser agent/actions/driver/session, legacy CDP controller | `tests/e2e/test_browser_playwright_e2e.py`; Chromium/CDP process, controlled loopback website, result JSON/screenshots | PASS engineering / PASS fail-closed / PASS runtime: 21 actual browser cases; controlled website |
| T-02 | DOM/scrape/URL/metadata/results cannot authorize shell/delete/send; real browser regression, legitimate actions and 30-second confirmation | external_content, agent graph, router, app, dispatcher, planner engine/interceptor | `tests/e2e/test_browser_authority_e2e.py`; real Chromium and production enforcement, adversarial model responses injected at external model boundary | PASS engineering / PASS fail-closed / PASS runtime: 30 actual browser enforcement cases; no live cloud-model claim |
| T-03 | Authorized bot/chat/sender send + receive roundtrip, safe commands, rate/timeout/reconnect/replay and missing/bad token | TelegramBotController send_message/poll_updates/handle_update/start/stop | `tests/unit/test_telegram_transport_contract.py`; transport doubles only | PASS engineering / PASS fail-closed; runtime PENDING_CREDENTIALS |
| T-04 | Verified OA outbound + inbound, authenticated webhook, message IDs/status/rate/token/network/replay | ZaloBotController send_message/handle_webhook/start_webhook | `tests/unit/test_zalo_transport_contract.py`, `tests/integration/test_zalo_webhook_http.py`; scripted local HTTP only | PASS engineering / PASS fail-closed; runtime PENDING_ZALO_OA_VERIFICATION |
| T-05 | Permitted guild/channel inbound command + outbound reply; start/stop/reconnect/rate/401/403/404; explicit admin and safety gate | DiscordBotController handle_message/send_message/poll_once/start/stop | `tests/unit/test_discord_acceptance_contract.py`, `tests/integration/test_discord_http_contract.py`; scripted local HTTP only | PASS engineering / PASS fail-closed; runtime PENDING_GUILD_CHANNEL_AUTHORIZATION |
| T-06 | Real unread Unicode mailbox via verified TLS, readonly/PEEK, allowlist/injection, reconnect/auth/timeout/disconnect | IMAPEmailReader connect/fetch_unread/fetch_and_summarize/disconnect | `tests/unit/test_imap_acceptance_contract.py`, `tests/integration/test_imap_tls_contract.py`; real TLS sockets to scripted server | PASS engineering / PASS fail-closed; runtime PENDING_MAILBOX_AUTHORIZATION |
| T-07 | Actual entities; confirmed light on/off AND test temperature, before/after/restore; unknown/unauthorized/offline/bad token fail | HomeAssistantClient and app ActionDispatcher bindings | `tests/unit/test_ha_acceptance_contract.py`, `tests/integration/test_ha_http_contract.py`; scripted HTTP state, no HA software/device | PASS engineering / PASS fail-closed; runtime PENDING_HA_INSTANCE_ENTITY |

The owner explicitly reconfirmed in this task that T-03–T-07 resources, credentials and live permissions
have not been provided. No historical credential or send-only result is reused. No live messaging,
mailbox access or Home Assistant write has been performed. No live state requires restoration.
Loopback fixture restoration proves engineering behavior only, not actual provider/device restoration.

## Resource checklist for the operator

Never paste secrets into chat. Configure secrets in the named environment/credential entry and provide
only the entry name, non-secret IDs, authorization scope and allowed test window.

- Telegram: `TELEGRAM_BOT_TOKEN` secret entry; current bot ID/username, `TELEGRAM_CHAT_ID`,
  `TELEGRAM_WHITELIST_USER_IDS`; confirm permitted chat/sender and permission for a nonce send/reply.
  A human must send the agreed nonce from the authorized account for receive evidence.
- Zalo: verified OA ID and app ID, authorized recipient, public HTTPS callback URL, access-token and
  app/OA-secret entries; permission for test outbound and signed inbound webhook. Coordinate callback
  registration and synthetic messages with the OA operator. No deliberate provider flooding for rate tests.
- Discord: bot token entry, guild installation/invitation, guild ID, channel ID, sender whitelist and
  separate admin IDs; authorize read/history/send and message-content access for nonce roundtrip.
- IMAP: test mailbox username, TLS hostname/port, password/app-password entry and exact sender allowlist;
  authorize read-only Unicode/injection fixtures, reconnect, lockout-safe bad-auth and controlled fault tests.
  Verify Seen flags unchanged. No mailbox writes authorized by the current task.
- HA: running test-instance URL, token entry, allowlisted light and climate test entity IDs;
  authorize on/off/set-temperature with bounds, explicit local confirmation and restoration. Snapshot
  original state/temperature, confirm every write/restore, verify post-state; stop if restoration is uncertain.

## Integration and regression findings

Documentation conflicts preserve both histories. `app.py` combines external-text rejection and Telegram
scope/checkpoint wiring with the authoritative HA dispatcher binding. `safety_interceptor.py` retains both
branches' high-risk aliases. Overlapping tests preserve truthful Telegram failures and confirmed HA writes.

Latest completed results appear at the end of this report. Historical reports remain under their own
revision-specific evidence directories; they do not certify this integration head.


### Root causes and bounded repairs

Fresh integration RED: 4332 passed, 45 failed, 20 skipped, 268 subtests; pytest 788.39 s,
process wall 791.837 s, exit 1. These are this integration run's numbers, not the previous branch's.
The historical main reproduction belongs to exact base 9d3c591 and remains separately archived;
its counts are not presented as a new run. `failure-classification.json` enumerates every current RED node.

| Area | Evidence / repair |
|---|---|
| CI parser | Main's workflow uses `runner.temp` where job-level env cannot access runner context. Fresh actionlint reproduces exit 1 at line 325; integrated workflow exit 0. Original GitHub annotation is retained in the CI baseline ZIP. GitHub API recheck confirms 0 jobs on run 35763480258, SHA 9d3c591. Browser store is configured in a runner step via GITHUB_ENV. |
| Router | Oversized commands reached substring routing; workspace punctuation and RAM/disk aliases missed; lock-screen was shadowed by screen-off; system-temperature voice command missed. Minimal rule fixes/rejection retain dispatcher confirmation. |
| TTS | Raising completion callback terminated worker; whitespace-only welcome pool became empty; mock audio treated corrupt WAV as playable. Isolate callback errors, restore the default phrase pool, validate WAV before playback shortcut. |
| Vision / RSS | Explicit zero display dimensions incorrectly selected physical screen; zero-size ROI reached JPEG encoding; feed titles kept markup. Preserve explicit dimensions, normalize the existing minimum ROI policy, clean title HTML. |
| Contract fixtures | Shell/HA tests bypassed newly required confirmation; brightness assumed a physical backend; packet tests omitted explicit labs opt-in and expected fabricated counts; healing asserted invented RAM reclamation; CORS expected a wildcard; UI/CLI used obsolete fields/messages. Fixtures now use explicit adapters, exercise the real confirmation protocol and assert truthful failure or measured state. No production safety gate was relaxed. |
| Voice / lifecycle | Silent PCM cannot stand in for a spoken fixture. Use CapturedAudio with sample rate and a non-silent signal. Await interaction-log completion. Startup-greeting tests disable unrelated proactive briefing. Synthetic gesture audio uses the production sample rate, coherent monotonic epoch, completed TTS queue and real echo cooldown. |
| Order-sensitive clock | Global patch of stdlib time.monotonic was visible to unrelated threads and depleted a finite sequence. A controlled background clock reader reproduces IndexError (1 fail); replacing only runaway_guard's local time reference passes all 36 tests. This proves the interference mechanism; it does not identify the exact background caller in the original full run. |

The CI browser job now also executes T-02 real Chromium regressions and local Zalo/Discord/IMAP/HA
transport contracts (cryptography is an explicit TLS-test dependency). CI still runs `tests/unit/` plus
those named browser/transport files, not the complete `tests/` tree. Full-suite evidence is recorded locally.

All networked transport fixtures are test doubles or controlled loopback HTTP/TLS. Their success does not
close provider acceptance. Existing optional-dependency/live-opt-in skips must not be counted as passes.


### Configuration bindings (not configured in this task)

| Service | Public configuration seam to populate after owner authorization |
|---|---|
| Telegram | Token secret `TELEGRAM_BOT_TOKEN`; `TelegramConfig.whitelist_user_ids` and `whitelist_chat_ids`; app keys `comms.telegram.whitelist_user_ids` / `whitelist_chat_ids`. `TELEGRAM_CHAT_ID` and `TELEGRAM_WHITELIST_USER_IDS` supplied by the operator must be parsed into these config fields by the smoke harness; the app does not automatically consume those ID environment variables. |
| Zalo | `ZaloConfig(access_token, app_id, oa_id, webhook_secret, whitelist_user_ids, host, webhook_port)` and `ZaloBotController(..., dispatcher=authoritative_dispatcher)`. Secret-entry names are chosen by the operator, not assumed env auto-load. Callback must reach the permitted HTTPS endpoint/proxy and preserve exact raw request bytes. |
| Discord | `DiscordConfig(bot_token, guild_id, default_channel_id, whitelist_user_ids, admin_user_ids)`; bind the authoritative dispatcher. Explicit REST polling contract is implemented; this does not certify WebSocket Gateway behavior. |
| IMAP | `IMAPEmailReader(host, port, username, password, priority_senders, timeout)`; use default verified SSL context or owner-approved test CA, never disable certificate validation. |
| HA | `smart_home.home_assistant.url`, `.allowed_entity_ids`, optional `.entities` aliases; token via `HASS_TOKEN` or configured secret injection. App passes its authoritative dispatcher to `HomeAssistantClient`. |

Additional command-boundary RED probes found a Telegram chat-scope check occurring after STT, an STT
exception logged verbatim and converted into a 200 acknowledgement, and Zalo direct skill/fallback paths
returning 200 on unavailable dependencies. Sender authorization was already correct; the new probe distinguishes
sender from chat scope. The fixes precheck chat scope, return TRANSCRIPTION_UNAVAILABLE without raw error data,
route Zalo skills through the dispatcher, and return explicit dependency/LLM errors. Note/screenshot skill aliases
now retain confirmation at the central classifier. Positive calculator/voice and confirmed local canaries remain
tested. No provider account/device is used by these tests.

The second full candidate (artifact name `full-integrated-green`, despite exit 1) recorded 4374 passed,
3 failed, 20 skipped, 268 subtests in 769.24 s, native exit 1. Two old large-input tests still expected
10–50 KB text to authorize an action; they now assert INPUT_TOO_LONG and retain their latency bounds.
The voice test observed the intermediate callback/UI state; the fixture now observes completed log writes and
waits for its own voice worker before teardown. No tests were xfailed or skipped to hide these failures.


### Evidence provenance and interrupted run

- `final-unit`: 2808 passed / 4 skipped / 268 subtests, 249.00 s pytest,
  251.661 s wall, exit 0. This precedes the last single-line LLM success-flag check and
  its added test; do not use it as final hosted-unit evidence.
- `final-full`: deliberately interrupted after its Zalo rate fixture failed; native exit
  4294967295, 169.360 s wall, no completed JUnit or pass total. The failure was separately
  reproduced (`rate-contract-red`: 1 fail), then the fixture was bound to the real dispatcher
  and calculator instead of relying on implicit success without dependencies.
- `llm-status-red`: a populated LLM response with success=False incorrectly returned 200.
  The handler now requires the success flag as well as nonempty content and no error.
- `final-command-contracts`: 45 passed, 3.07 s pytest, 4.279 s wall, exit 0.
- `release-candidate-2-manifest.json` is the source snapshot for `final-full-2` and
  `final-scoped-2`. The earlier candidate manifests and attempted run names are retained for traceability.

Only fully completed runs with native exit 0 may supply a passing verdict. An interrupted run is not a
pytest assertion total, flaky pass, dependency skip or runtime success.


### Remaining non-failing diagnostic

The completed `final-full-2` run reports one RuntimeWarning: coroutine `Server._close` was never awaited,
reported during collection of garbage around `test_startup_intro_custom_configured_phrase` in pytest's stash.
The originating server instance was not traced by this run; do not attribute it to Discord, Zalo or another
transport merely from the warning's class name. This is an unresolved lifecycle diagnostic, not an assertion
failure or evidence of provider runtime. No warning suppression was added. Native process exit is 0.


<!-- current results start -->
## Latest completed validation and verdict

Unit at source commit 6af3509: **2809 pass / 0 fail / 4 skip**, 243.05 s pytest, 245.534 s wall, native exit 0. Full: **4394 pass / 0 fail / 20 skip**, 683.31 s pytest, 686.491 s wall, native exit 0. Scoped T-01–T-07: **164 pass / 0 fail / 0 skip**, 112.44 s pytest, 115.401 s wall, native exit 0.

[Hosted CI](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/runs/36305486023) PASS at `6af3509`; all 5 jobs succeeded.

T-01/T-02: PASS engineering / PASS fail-closed / PASS runtime for controlled real Chromium execution/enforcement. T-03–T-07: PASS engineering / PASS fail-closed / runtime PENDING authorized resources. No live messaging, mailbox access or HA write was performed. Optional/live skips are not passes. No CONDITIONAL GO or GO. Main remains 9d3c591, unchanged.

Exact commands, UTC start, interpreter, native exit and wall time: final-full-2.json and final-scoped-2.json.
JUnit/console/screenshots are in the [evidence archive](../../reports/evidence/t01-t07-integration-20260927.zip).
summary.json lists every skip and per-file scoped counts; 268 subtests are recorded separately from headline passes.
Latest hosted-unit counts come from hosted logs, not local estimates.

The browser is real; its target website is controlled. T-02 injects adversarial responses at the external model seam;
no live cloud-model quality claim is made. T-03–T-07 fixture success never closes provider/device gates.
No provider state requires restoration. Browser sessions and HTTP/TLS fixtures close during teardown;
canaries verify malicious delete/shell/send never occurred. Verdict: **NOT GO**.
<!-- current results end -->

Historical native heap exit 0xC0000374 was not reproduced by the latest completed full run (native exit 0); its historical root cause is not claimed solved by this work.


## Hosted CI on the validated source commit

Run [36305486023](https://github.com/Duong-Phuoc-Hung/JARVIS/actions/runs/36305486023), head
`6af3509af050db158dc4387e6d7ce67c9bec5f73`: Syntax, Import, Unit, Browser/transport and Summary all success.
Hosted unit: **2809 passed / 4 skipped / 268 subtests**, **228.88 s**; hosted browser + local transport:
**69 passed / 0 failed / 0 skipped**, **109.19 s**. `gh run watch --exit-status` returned native exit 0.
Original hosted JUnit, job logs, metadata, screenshot artifact and artifact IDs are retained in the evidence ZIP.
The final evidence/documentation follow-up does not change `jarvis/`, `tests/`, workflow or pyproject from this source
commit. Its own PR check must also finish before handoff. Neither branch CI nor localhost transport success closes
T-03–T-07 provider runtime gates; main has not been updated.
