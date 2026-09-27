# T-05–T-07 engineering and runtime acceptance — 2026-09-27

Base main: `9d3c5916ee715eff291ed2364beab9b1e9a815b6`. Branch: `codex/t05-t07-runtime-contracts`.
The previous T-02–T-04 and CI-baseline branches are not merged into this branch.
No push or main merge is authorized/performed. Version remains `jarvis.__version__ = 5.2.1` (unreleased fixes).

## Scope and acceptance seams

Read AGENTS.md, AUDIT_FRAMEWORK, READINESS_DASHBOARD, ROADMAP and the external DOCX at
`D:\JAVIS\JARVIS-main\JARVIS-main\docs\JARVIS_Phan_cong_3_thanh_vien_Hoa_Hung_Thai.docx`.
DOCX SHA256: `8ddf67c448c05ced363080e9a55a52a716ad7ed9453353a2deaacf68405616ac`.
User instructions override AGENTS.md's generic push-main instruction. Dashboard gate claims remain historical;
this task does not change its independently reviewed gate statuses.

- T-05: DiscordBotController start/stop/poll_once/handle_message/send_message/send_embed → real ActionDispatcher → SafetyGate.
  Authorized guild/channel/user/admin, inbound command and outbound reply, reconnect/errors/rate limit,
  no dangerous side effect before confirmation. Authenticating a bot with zero guilds is NOT a round-trip.
- T-06: IMAPEmailReader connect/fetch_unread/fetch_and_summarize/disconnect → verified TLS imaplib.
  Unread Unicode MIME, exact sender filter, read-only/PEEK, redacted auth/network/protocol errors,
  explicit reconnect. Reading two emails historically does NOT close the remaining DoD.
- T-07: HomeAssistantClient reads and public writes → ActionDispatcher → exact payload confirmation →
  single allowed entity HTTP request → before/after verification. Restore is another explicit confirmed write.

## Findings and changes

- `jarvis/comms/discord.py`: removed implicit whitelist-to-admin promotion and raw callback/skill-registry
  execution of sensitive commands. `!exec <action> <JSON object>`, macro, screenshot and note action requests
  require an explicit admin and an actual ActionDispatcher. Missing handlers fail, never pretend completion.
  Confirmation stays on the trusted local host; tokens and arbitrary action output are not sent to Discord.
  Transport now uses one HTTP client contract (`request`), exact guild/channel binding, timeout, no redirects,
  HTTP status and actual message ID validation, disabled mentions and content-free bounded delivery records.
  REST polling sends the command response, skips historical messages on initial bootstrap, sorts valid ASCII
  64-bit IDs, serializes polls, deduplicates and applies provider 429 cooldown. Stop timeout retains the worker
  and blocks duplicate restart. Bool from poll_once means continue; inspect last_poll_status for success.
- `jarvis/comms/email_imap.py`: exact parsed single address/domain allowlist replaces substring matching.
  Verified TLS with bounded timeout; negative login/select/search/fetch and disconnects raise redacted
  IMAPTransportError instead of returning an empty successful mailbox. Failed sessions close before retry.
  Read-only EXAMINE and BODY.PEEK[] preserve Seen; Unicode MIME headers/body decoded. Filtering applies to
  fetched messages as well as summaries. Raw body is withheld if sanitizer fails; no raw server/body logs.
- `jarvis/smart_home/home_assistant.py`: removed placeholder credential, added explicit writable entity
  allowlist, single entity/domain/service/parameter validation, redacted HTTP failures, public confirmation
  gate and before/after checks. HTTP success alone is not a verified device state change. Unknown/unavailable
  entity prevents POST; failed post-read yields STATE_NOT_VERIFIED with request_accepted, never automatic retry.
  Legacy mock_http write returns MOCK_WRITE_UNAVAILABLE, not a synthetic success.
- `jarvis/core/app.py`: binds HA client actions to the app's dispatcher and loads
  `smart_home.home_assistant.allowed_entity_ids` (empty by default, no writes).
- `jarvis/planner/safety_interceptor.py`: explicit high-risk classification for macro_play, screenshot, note_add.

## Evidence boundaries and migration notes

HTTP doubles and scripted loopback servers are **engineering evidence (T2)**, not provider runtime acceptance.
IMAP TLS tests use real sockets, certificates, hostname verification and production imaplib, but the server is
scripted; HA HTTP tests use a stateful fixture, not Home Assistant software or physical devices.
Discord HTTP loopback runs real dispatcher/safety and verifies no canary write, but is not discord.com.

Legacy tests were revised at the HTTP boundary: they previously assumed unconfigured sends retained raw
message content, raw callbacks could execute commands, whitelist users were admins, SELECT errors meant
empty mailbox, and mocked HA methods returned success without executing the authoritative transport.
The revised cases cover malformed/Unicode/oversized IDs, duplicate and concurrent polls, start/stop and
stop timeout, retries/reset/401/403/404, unauthorized commands, real confirmation, before/after and restoration.
No failures are hidden with xfail or new skip markers. The TLS fixture explicitly requires cryptography.

Security limits: sender From allowlisting is **not** sender authentication (SPF/DKIM/DMARC is not verified).
Email is returned as untrusted data and this reader has no automatic LLM/router/dispatcher execution path.
PromptGuard is risk reduction, not an authorization boundary. Any future summarizer must pass data through
an explicit untrusted-context seam; raw email must never be promoted to user instructions.
Discord is REST polling, not WebSocket Gateway/Discord application slash interactions. A new controller
skips offline history, and in-memory cursor is at-most-once during its lifetime; a reply failure is not retried
because repeating a command could repeat a side effect. Only one controller per configured channel is supported.
Home Assistant supports explicit light/switch/fan on/off and climate temperature writes (5–35 °C),
not domain-wide/area writes, toggle, camera/lock/security domains or arbitrary services. Immediate post-read
may report STATE_NOT_VERIFIED for asynchronous devices; inspect state before deciding to retry/restore.

## Live blockers and required operator inputs

No live Discord, mailbox or HA write was performed. Current environment presence-only probe and Docker
probe are in `reports/evidence/T05-T07/`; no credential values were collected in evidence.
Docker engine probe exited 1 with missing `dockerDesktopLinuxEngine` named pipe. No container was created.

- T-05 runtime: **PENDING_GUILD_CHANNEL_AUTHORIZATION**. Need authorized invitation/install, guild/channel IDs,
  sender/admin IDs and secure credential location. Bot authentication/zero guild historical evidence is insufficient.
- T-06 runtime: **PENDING_MAILBOX_AUTHORIZATION**. Need authorized test mailbox, TLS host/port, sender allowlist,
  credential location and permission for controlled Unicode/injection unread fixtures and fault cases.
- T-07 runtime: **PENDING_HA_INSTANCE_ENTITY**. Need running test HA, URL, secure token location, safe entity IDs
  and explicit permission for write/restore. Docker on this host is currently unavailable.

Questions were sent to the user for these exact inputs; none are inferred from historical credentials.
Do not paste tokens/passwords into chat or commit .env/credential dumps.

## Runtime completion protocol (pending resources)

1. Record revision, UTC time, resource IDs (redacted/shareable form), config presence and allowed scope.
2. Discord: install bot in the permitted guild/channel with needed read/send/history permissions and message
   content access. Start controller, send a fresh safe nonce command from allowed account, capture inbound ID,
   command status, outbound HTTP status/reply ID/time. Repeat with forbidden sender/non-admin dangerous command,
   verify no action side effect; verify local confirmation, cancel/expiry, stop/restart and controlled errors.
   Do not deliberately flood Discord to trigger 429; use transport tests for fault injection unless separately authorized.
3. IMAP: provision only synthetic unread Unicode/plain/HTML and injection messages. Record counts, opaque IDs,
   UTF-8 assertions and Seen flags before/after (never subjects/body/password). Fetch twice with disconnect/reconnect;
   test invalid auth and faults only against the designated test server/account with lockout-safe permission.
4. HA: snapshot selected entity state and only necessary brightness/temperature. Read entities, request action
   through the public dispatcher, confirm locally, record HTTP outcome and actual state after. Restore the exact
   tested setting with a new confirmation and verify again. If state becomes uncertain or restoration fails,
   stop and require operator intervention. Do not run these steps on production household entities.

## Reproducibility and results

Fresh local validation, with the CI environment flags recorded in `run_pytest.py`:

| Run | Pass | Fail | Skip | Subtests pass | Pytest seconds | Wall seconds | Native exit |
|---|---:|---:|---:|---:|---:|---:|---:|
| Final unit (`unit-final`) | 2764 | 0 | 4 | 268 | 287.81 | 291.365 | 0 |
| Final scoped acceptance/regression (`scoped-final`) | 254 | 0 | 0 | 31 | 21.82 | 24.843 | 0 |
| Final full (`full-final`) | 4264 | 46 | 20 | 268 | 721.77 | 724.935 | 1 |
| Real socket loopback transports (`transports-loopback`) | 9 | 0 | 0 | 0 | 5.68 | 7.079 | 0 |
| Selected failures on pristine base (`baseline-rerun`) | 1 | 45 | 0 | 0 | 42.15 | 45.848 | 1 |
| Isolated triple-clap/current (`order-rerun`) | 1 | 0 | 0 | 0 | 1.93 | 3.313 | 0 |
| Isolated triple-clap/base (`baseline-order-rerun`) | 1 | 0 | 0 | 0 | 1.95 | 3.235 | 0 |

Counts from separate runs overlap and must not be summed. Exact commands, UTC starts, wall times and native
exit codes are in [run-inventory.json](../../reports/evidence/T05-T07/run-inventory.json); each named run has
raw `.txt`, JUnit `.xml` and runner `.json` artifacts. All initial RED and intermediate failed runs are retained.
Final lint on changed Python files exits 0 (`lint-handoff.json`).

Full regression remains **FAIL**. 45 final failures reproduce on a fresh archive of base `9d3c591`, using the
same interpreter and CI flags; they are outside this task (routing, UI/audio, plugins/security contract drift,
Telegram, host integration and other existing cases). See `baseline-classification.md` and
`full-final-classification.json` for every case and assertion. The remaining failure is
`TestGesturePassiveTriggerGuardWiring.test_repeated_triple_clap_triggers_are_bounded`: its globally patched
`time.monotonic` exhausts a seven-value list (`IndexError`). It passes in final unit and isolated current/base
runs. This is a **suspected order/concurrency-sensitive test**, not a proven fixed failure; the caller consuming
the extra time value and causal ownership remain unresolved. No assertion or test was disabled to hide it.
The earlier concurrent-gesture stress candidate passes the final full run and the selected base rerun.

The first broad run (`full-current`) had 4241 pass/66 fail/20 skip, 691.20 pytest seconds and native exit
**3221226356 (0xC0000374)** at/after teardown. Retained as a real abnormal process exit; cause unresolved.
The final full run terminates normally with exit 1. Revised task contracts account for the subsequently fixed
scoped failures; outside-task failures remain visible. No hosted GitHub Actions rerun was performed here:
**hosted CI NOT_RUN; local full suite FAIL**. This handoff does not supersede the separate CI-baseline branch.

The 20 final skips and exact reasons are in `full-final-skips.json`. Four unit skips concern missing
optional dependencies (three matplotlib cases, one vosk case). Of the other 16, five report unavailable
OpenCV, six require the full-pipeline opt-in flag, three report unreachable public network endpoints, and
two are module-level collection skips (biometrics and live infrastructure). A skipped live gate is not runtime evidence.

Reproducibility: runner metadata HEAD is the clean base while tests ran on uncommitted task changes.
`source-manifest-final.json` records source at final-full start; `source-manifest-handoff.json` records final
source bytes. Six files received import-only ordering cleanup after full started; AST excluding imports is
unchanged (`import-only-cleanup.json`). Final unit and scoped runs occurred after that cleanup. No functional
code changed after final full started. `source-drift-check.json` verifies final source against the handoff
manifest. Adapt host-specific Python/browser paths in the runner when reproducing elsewhere.

## Handoff verdict

T-05, T-06 and T-07: **PASS engineering** and **PASS fail-closed** for the documented scoped contracts.
Provider **PASS runtime is not established**: all three remain PENDING under the exact blockers above.
No task is runtime DONE; neither CONDITIONAL GO nor GO is issued. Full-suite failures and the unproven
order-sensitive case prevent a clean whole-repository acceptance claim.

Integrate `codex/t05-t07-runtime-contracts` through review, never direct main push. The final chat handoff
provides the commit ID; `handoff-files.txt` enumerates the commit paths. Resolve shared documentation and
`safety_interceptor.py` changes with the T-02–T-04/CI branches without dropping their security fixes, then
rerun combined regression. No external account/channel/device resources were used by this work.

## Primary protocol references

- [Discord Message API](https://docs.discord.com/developers/resources/message): channel messages and created message identifiers.
- [Python imaplib](https://docs.python.org/3/library/imaplib.html): TLS, timeouts and readonly mailbox selection.
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/): state reads and service calls.
