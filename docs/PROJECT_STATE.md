# JARVIS — PROJECT_STATE.md

> **Original feature concept attribution:** The original JARVIS concepts for
> voice-first interaction, wake-word activation, STT/TTS, Local/Cloud AI
> routing, hardware diagnostics and window management, internal-network
> InfoSec auditing, workflow automation, data analysis, IoT/Home Assistant,
> biometric face authentication, gesture control, multi-channel
> communications, self-healing, and destructive-action safety guardrails were
> designed by **Huynh Minh Hoa
> ([@hoahuynh19a-crypto](https://github.com/hoahuynh19a-crypto))**.
>
> This is feature-origin attribution only. It does not claim authorship of
> PROJECT_STATE.md as a whole and does not include later extensions,
> implementation details, testing, security hardening, benchmarking, or
> maintenance work; those remain attributable through Git history and pull
> requests.
> Durable current-state handoff for future sessions.
> Snapshot: 2026-09-01.
> Always verify Git state and current code before relying on this snapshot.

## 0. Current Checkpoint — J.A.R.V.I.S. Terminal Control Center, implemented/committed/pushed, PR pending (2026-09-03) — READ THIS FIRST

This section supersedes the checkpoint immediately below it (now demoted to `0-PREV5`, kept
as historical record — not rewritten; further checkpoints cascade as `0-PREV6`, etc.). As
always: **do not treat any SHA recorded here as a permanent "current main" pointer** — run
`git fetch origin --prune && git rev-parse origin/main` before trusting it.

**State:**
- Branch: `feat/terminal-control-center`, based on `main` @
  `80b47a57c70dad39ec9f783d128e610d11e17f79` (merge of PR #36, `docs/sync-post-pr35-state`,
  unchanged by this work — `origin/main` has not advanced past it as of this checkpoint).
  **This branch's changes are implemented, committed, and pushed** — feature commit
  `81c649aba7d3ed34950925eb5cd4e1c85237f1f7` (`feat(ui): add terminal control center`),
  confirmed as both `HEAD` and `origin/feat/terminal-control-center`. **A pull request has
  NOT yet been opened, and the feature is NOT merged into `main`** — `main` itself remains at
  `80b47a5...` and has no `jarvis menu` command until a PR is opened, reviewed, and merged.
  Treat `81c649a` as branch/checkpoint evidence only, never as a permanent pointer — the
  branch may advance with further commits before a PR is opened.
- runtime: `4.7.0` (`jarvis.__version__`, unchanged by this work — not a version bump, not a
  new release).
- formal release: `v4.5.1` (unchanged).

**J.A.R.V.I.S. Terminal Control Center — implemented, committed, and pushed on
`feat/terminal-control-center`; PR pending; not merged.** A new hierarchical, interactive
Terminal/PowerShell UI (`python -m jarvis menu` / `jarvis menu`), covering all nine product
areas as a thin presentation/routing layer with no duplicated business logic. Full
architecture contract, truthfulness findings, and the durable invariant future sessions must
preserve are recorded in `CLAUDE.md`'s "Durable Terminal Control Center invariant" section
and `CHANGELOG.md`'s matching entry — not repeated verbatim here.

**New files** (25 code files as of the final architecture verification pass below, across all
three sessions on this branch):
- `jarvis/ui/terminal/{app,console,context,logo,models,navigator,report,session,theme}.py`
  (`authority.py` was added during the hardening pass and then removed during final
  verification — see below; it does not exist in the current tree)
- `jarvis/ui/terminal/modules/{hardware,infosec,workflow,data,smart_home,biometrics,gesture,comms,healing}.py`
- `tests/unit/test_terminal_{navigator,console,session_report,app,modules}.py`
  (`test_terminal_authority.py` was added, then removed as obsolete along with `authority.py`
  — see below; 98 net new `tests/unit/` tests across all three sessions)
- `jarvis/cli.py`: +7 lines (one `menu` subparser, one 2-line lazy-import routing branch) —
  **no other CLI command's behavior changed**.
- `tests/test_cli.py`: +21 lines (3 new tests: `menu` subcommand parsing, `--version` exits 0,
  `menu` routes to `run_terminal_menu()` without constructing `JarvisApp`).

**Pre-commit hardening pass (same day, same branch)** found and attempted to fix a real
authorization bypass, then a **third, final architecture-verification pass (same day)** found
that the hardening pass's own fix was itself wrong and corrected it. Recorded here as it
actually happened, including the false start, since a future session should not repeat it:

1. **Side-effect authorization bypass, found in the hardening pass.** Smart Home control and
   Self-Healing termination were calling `HomeAssistantClient`/`HealingEngine` methods
   directly after only the terminal's own Y/N prompt — bypassing real authorization entirely,
   since no dispatcher action for either operation existed anywhere in the codebase to route
   through instead.
2. **First attempted fix (hardening pass), later found to be wrong.** A new module,
   `jarvis/ui/terminal/authority.py::TerminalAuthority`, constructed a standalone
   `ActionDispatcher` + `SafetyGateInterceptor` — the real production classes — and registered
   `smart_home_turn_on`/`turn_off`/`toggle`/`set_temperature`/`os_kill_process` against that
   *private instance*. This looked "dispatcher-routed" but was in fact a second, disconnected
   security universe: those five action names exist nowhere in the canonical
   `jarvis/core/app.py` dispatcher (confirmed by exhaustive grep), so there was nothing
   authoritative for this private dispatcher to actually be routing into.
3. **Correction (final verification pass).** `authority.py` and its 12 tests
   (`tests/unit/test_terminal_authority.py`) were removed entirely. Per-operation replacement,
   following the rule "reuse an existing authoritative path, else reuse an existing
   backend-native safety contract, else report the action truthfully unavailable — never
   invent a new dispatcher":
   - **Self-Healing** now calls `HealingEngine.heal_hung_process()` **directly**. Safe because
     that method already checks `is_protected(name, pid)` against
     `PROTECTED_PROCESS_WHITELIST` **internally**, unconditionally, regardless of caller — a
     genuine, pre-existing backend-native authoritative contract, not something added for this
     UI. Verified with a real `HealingEngine`, targeting our own interpreter's PID with the
     protected name `"python.exe"`: confirmed refusal (`PROTECTED_PROCESS`) with no OS-level
     termination attempt.
   - **Smart Home control** (Turn On/Off/Toggle/Set Temperature) has neither a
     backend-native safety contract (`HomeAssistantClient` is a bare REST wrapper) nor a
     canonical dispatcher action to reuse. These four actions are now marked unavailable in
     the menu and report `LIMITED` truthfully — **they no longer call the real
     `HomeAssistantClient` methods at all**, a real behavior downgrade from both the original
     (unauthenticated-direct-call) and hardening-pass (private-dispatcher) versions, and the
     correct choice given no safe authoritative path currently exists.
4. **A false premise from the hardening pass is also corrected.** That pass believed
   `HealingEngine.heal_hung_process()` returned a `HealingReport` dataclass (needing a
   `.to_dict()` conversion before dispatcher registration). Re-reading the actual current
   source during final verification shows this was **wrong**: the method returns a plain
   `dict` literal in every branch; `HealingReport` is defined/exported but never instantiated
   by that method in production code (only by unrelated test files). The `.to_dict()` wrapper
   this false premise produced was never exercised against the real method — only against a
   self-constructed test fake matching the same wrong assumption — and has been removed along
   with the rest of `authority.py`.
5. **`[A]` visibility rule corrected** (hardening pass, unaffected by the correction above)
   from `>=1` to `>=2` eligible actions (`MenuScreen.batch_visible()`). Concretely changes
   real behavior: InfoSec's `[A]` is hidden until a scan target is validated; Data Analysis's
   `[A]` is hidden until a dataset is selected. `batch_eligible()` (used to actually run `[A]`)
   is unchanged.
6. **Package architecture reviewed, kept as-is** (hardening pass) — every `modules/*.py` file
   classified as clean menu-definition + thin-backend-adapter ("A+B"), no rendering code, no
   reimplemented business logic. `modules/` directory name and per-file organization kept
   unchanged.

Zero backend/security production files were touched across any of these passes (`jarvis/
security/`, `jarvis/comms/`, `jarvis/healing/`, `jarvis/smart_home/`,
`jarvis/core/dispatcher.py`, `jarvis/planner/safety_interceptor.py`,
`jarvis/automation/safety_gate.py` all confirmed zero diff throughout).

**Two real, pre-existing truthfulness gaps were discovered during this work and are recorded
as open findings, not fixed** (out of scope per explicit task instruction) — see
`docs/TECHNICAL_AUDIT_REPORT.md` §7 for the full citation-backed detail:
1. `jarvis/security/scanner.py::PacketCapture.capture_packets()` fabricates a fixed
   70/20/10 TCP/UDP/ICMP protocol-distribution split regardless of whether the underlying
   `tshark` capture actually succeeded (both its success and exception paths call the same
   unconditional synthesis helper, `_build_capture_result()`, and both report
   `status="SUCCESS"`).
2. `jarvis/comms/telegram.py`'s `send_message()`/`send_photo()` return a synthetic
   `{"ok": True, ...}` whenever no real HTTP client is wired (always true for a bare
   `TelegramBotController()`); `jarvis/comms/discord.py`'s `send_message()`/`send_embed()`
   report `{"success": True, ...}` even when the real underlying HTTP POST raises, and
   `send_file()` never attempts a network call at all yet still reports success.

The Terminal UI's InfoSec > Packet Capture and Communications Hub > Telegram/Discord > Send
* screens never call these methods — they always report `LIMITED`/truthfully-explained
non-evidence instead of fabricated data, per the explicit "don't make an existing
truthfulness gap worse" instruction. **Fixing the underlying `PacketCapture`/`telegram.py`/
`discord.py` transport truthfulness is separate, future, unstarted work** — do not assume the
Terminal UI's workaround also fixed the underlying module; it did not.

**Validation evidence (local, initial implementation pass):**
```text
New tests: 86 in tests/unit/ (test_terminal_navigator.py 10, test_terminal_console.py 12,
  test_terminal_session_report.py 16, test_terminal_app.py 27, test_terminal_modules.py 21)
  + 3 in tests/test_cli.py = 89 new tests total, all passing.
tests/unit/ (full suite, local): 1499 passed, 1 skipped, 50 subtests passed, 0 failed.
  (1413 baseline + 86 new tests/unit/ tests = 1499, exact match -- confirms no regression
  and no double-counting.)
ruff check jarvis/ui/terminal jarvis/cli.py <new test files>: clean (2 trivial issues
  auto-fixed: an unsorted import block, one f-string without a placeholder).
python -m py_compile: clean for every new/changed file.
git diff --check: no whitespace errors.
```

**Validation evidence (local, hardening pass, same day -- superseded in part by the
correction below, kept for the historical record of what was actually run):**
```text
22 new tests added: 12 in tests/unit/test_terminal_authority.py (new file, since removed) +
  6 in test_terminal_app.py ([A] visibility at 0/1/2/3+ eligible, concrete changing-live-value
  [R] proof, [R] never invokes a handler) + 4 in test_terminal_modules.py (InfoSec/Data
  batch_visible() before/after target or dataset selection) -- all passing at the time.
tests/unit/ (full suite, local, AT THAT TIME): 1521 passed, 1 skipped, 50 subtests passed,
  0 failed. This count included the 12 authority.py tests later removed -- see the updated
  count in the final-verification validation block below; 1521 is not the current count.
tests/test_cli.py + test_dispatch_truthfulness.py + test_action_dispatcher_safety.py +
  test_app_integration.py (81 tests, dispatcher/safety-gate regression check): all passing.
ruff check (changed/new files): clean (1 more trivial auto-fixed import-sort issue).
python -m compileall jarvis: clean (whole package, not just the new files).
git diff --check: no whitespace errors.
```

**Validation evidence (local, final architecture-verification pass, same day -- current)**:
```text
Removed: jarvis/ui/terminal/authority.py, tests/unit/test_terminal_authority.py (12 tests).
Changed: jarvis/ui/terminal/modules/healing.py, jarvis/ui/terminal/modules/smart_home.py,
  tests/unit/test_terminal_modules.py (net 2 tests: one replaced to assert unavailability
  instead of confirmation-required for Smart Home control; one new test using a REAL
  HealingEngine + a real protected process name ("python.exe") to prove the backend-native
  protected-process contract is what's actually relied upon, not a mock).
python -m compileall jarvis/ui/terminal: clean.
Targeted regression (179 tests -- not the full suite, per explicit instruction not to
  over-rerun unless materially justified): tests/unit/test_terminal_{navigator,console,
  session_report,app,modules}.py + tests/test_cli.py + test_dispatch_truthfulness.py +
  test_action_dispatcher_safety.py + test_app_integration.py -- 179 passed, 4 subtests
  passed, 0 failed.
ruff check jarvis/ui/terminal tests/unit/test_terminal_modules.py: clean.
git diff --check: no whitespace errors.
tests/unit/ (full suite, local, run once more for documentation accuracy):
  1511 passed, 1 skipped, 50 subtests passed, 0 failed.
  (1413 baseline + 98 net new tests/unit/ tests -- exact match; this is the current,
  authoritative count -- 1521/1499 above are historical, from earlier states of this branch.)
```
**Local environment caveat** (see also the "0-PREV5" checkpoint's own STT/test-environment
notes below, unaffected by this work): this session's local interpreter is Python 3.14.6;
CI pins 3.13. `pytest-asyncio`/`pytest-env` are not installed in this local venv
(`PytestConfigWarning: Unknown config option: asyncio_mode`/`env` at collection time), so this
full-suite run is not a perfect substitute for actual CI — but it collected and ran the
complete `tests/unit/` tree with 0 failures, which is still meaningful, real evidence, not a
fabricated pass. The branch is now pushed (`feat/terminal-control-center`, feature commit
`81c649aba7d3ed34950925eb5cd4e1c85237f1f7`); whether GitHub Actions CI has actually run
against that pushed commit, and its result, has not been independently checked in this
documentation pass — verify on GitHub Actions before treating CI as green for this branch.

**Manual validation performed** (see `CHANGELOG.md`'s matching entry for the exact scenarios):
`python -m jarvis menu` run for real via both an interactive terminal and a piped-stdin
subprocess; navigation/breadcrumb/[A]-batch (against real `HardwareMonitor` data)/[S]-save
(a real file written under `%LOCALAPPDATA%/JARVIS/reports/cli/` and verified to exist)/[J]
confirm-cancel/InfoSec target validation (one real RFC1918 accept, one real public-IP reject)
were all exercised against real backends. No destructive action, real Nmap/TShark invocation,
real message send, real biometric enrollment, camera/microphone access, or process
termination was performed.

**Additional manual validation, hardening pass (historical -- exercised the since-removed
`TerminalAuthority` architecture)**: the Smart Home Turn On flow was exercised twice more
through the real `TerminalApp` at that time -- once with Home Assistant disabled by config
(correct `OFFLINE` short-circuit, zero network activity), and once with it enabled but
pointed at `http://127.0.0.1:1` (a safe, local, guaranteed-unreachable port) with a fake
token, proving the (then-existing) `TerminalAuthority` gate→confirm→execute chain ran against
the real `ActionDispatcher`/`SafetyGateInterceptor`/`SafetyGate`/`HomeAssistantClient` classes
end-to-end. This validated that `TerminalAuthority`'s *mechanics* worked correctly -- it did
not, and could not, validate whether constructing a private dispatcher was architecturally
sound in the first place; that question was only asked and answered in the final-verification
pass above, which found it was not, and removed it. **Current behavior**: Smart Home control
no longer calls `HomeAssistantClient` at all (reports `LIMITED`, see above) -- this historical
smoke test no longer describes what the code does today, kept here only as a record of what
was actually run at the time. Self-Healing was verified in the final-verification pass with a
real `HealingEngine` and a real protected process name (`"python.exe"`, safe -- rejected
before any OS-level interaction); no real process was ever terminated in any pass, per the
explicit no-real_os-process-operations constraint.

**No remaining known issue from this task within its stated scope.** The two comms/packet-
capture truthfulness gaps above are pre-existing and explicitly out of scope; they are not
"remaining issues from this task," they are follow-up work this task discovered and worked
around without fixing.

---

## 0-PREV5. Prior Checkpoint — Documentation State Verified Through PR #35 — historical,
superseded by the `0` checkpoint above

This is the single authoritative "what's true right now" section. **Do not treat any SHA
recorded in this section, or anywhere in this file, as a permanent "current main" pointer.**
Every checkpoint in this file's history (see the note immediately below) has recorded an
exact commit as "current main," only for that claim to go stale the moment the *next*
change — including the very docs-only sync that recorded it — merged and advanced `main`
past it. A SHA below is **checkpoint/historical evidence for the PR that produced it**,
never a live pointer. **Before relying on "current state" for any real task, run:**
```bash
git fetch origin --prune
git rev-parse origin/main
```
and trust that output over this file.

This section supersedes the checkpoint immediately below it (now demoted to `0-PREV`,
kept as historical record — not rewritten; further checkpoints cascade as `0-PREV2`,
`0-PREV3`, `0-PREV4`).

**State:**
- **Documentation synchronized and verified through PR #35** (`docs/finalize-dispatch-merge-state`,
  feature commit `a344af1f7b408306d92f781f01a2fc2e5253043d`, merge commit
  `399a70cc471bf35d98e1b976f8c895054d4f7524`) — **documentation-only**: no code, test,
  config, runtime, or version behavior changed. Post-merge **JARVIS CI #162: SUCCESS** —
  all four jobs green (Syntax Check, Unit Tests, Import Validation, Pipeline Summary).
- **PR #34 production work remains RESOLVED** (`fix/dispatch-truthfulness`, feature commit
  `e99c522be808d9160a5b9c57bf9bd8ec11d3dd69`, merge commit
  `ae6d5d8ffd98f4629af951e19820bf047f9c05d7`, post-merge JARVIS CI #160 SUCCESS): central
  dispatch truthfulness and the `hardware_status_query` compatibility alias both shipped in
  that PR and both remain resolved — PR #35 only synchronized documentation to reflect
  that merged state, it did not touch the fix itself.
- runtime: `4.7.0` (`jarvis.__version__`, unchanged through PR #34 and PR #35 — not
  `4.7.1`, no new tag/release).
- formal release: `v4.5.1` (unchanged).

**Central dispatch truthfulness — RESOLVED (via PR #34).** **`hardware_status_query`
compatibility alias — RESOLVED (via PR #34).** Full implementation detail, return-convention
audit, normalization contract, and validation evidence are preserved verbatim in the
`0-PREV` checkpoint immediately below (all of it still accurate). **No remaining known
issue from the dispatch-truthfulness task.**

**Future sessions:** this checkpoint, like every one before it, will itself become
historical the moment `main` advances again — including via this checkpoint's own merge.
Verify live Git state (`git fetch` + `git rev-parse origin/main`) before treating any
recorded SHA here as current; treat the runtime version, release version, and
resolved/open status of specific fixes (not raw commit SHAs) as this section's durable
content.

---

## 0-PREV. Prior Checkpoint — PR #34 merged state (2026-09-03) — historical, superseded
by the `0` checkpoint above (this checkpoint's own "current main" wording below was
accurate at PR #34's merge time but is superseded now that PR #35 has merged on top of it
— kept verbatim as historical record, not rewritten)

**State (as of the PR #34 merge, before PR #35):**
- `main`: `ae6d5d8ffd98f4629af951e19820bf047f9c05d7` — merge of **PR #34**
  (`fix/dispatch-truthfulness`, feature commit `e99c522be808d9160a5b9c57bf9bd8ec11d3dd69`).
  **This PR is MERGED.** `main` now carries both the central-dispatch-truthfulness fix and
  the `hardware_status_query` compatibility alias described in the `0-PREV2` checkpoint
  below — that checkpoint's "NOT committed and NOT merged" language described a real,
  earlier point in time (2026-09-03, before this merge) and is not being rewritten, but it
  no longer describes current state; the `0` checkpoint above does.
- **Post-merge CI: JARVIS CI #160, conclusion SUCCESS** — all four jobs green: Syntax
  Check, Import Validation, Unit Tests, Pipeline Summary.
- runtime: `4.7.0` (`jarvis.__version__`, unchanged by this merge — not `4.7.1`, no new
  tag/release).
- formal release: `v4.5.1` (unchanged).

**Central dispatch truthfulness — RESOLVED ON `main`.** **`hardware_status_query`
compatibility alias — RESOLVED ON `main`.** Both shipped together in PR #34. Full
implementation detail, return-convention audit, normalization contract, and validation
evidence are preserved verbatim in the `0-PREV2` checkpoint immediately below (all of it
still accurate — only the commit/merge/CI status has changed, which this section records).
**No remaining known issue from the dispatch-truthfulness task.**

---

## 0-PREV2. Prior Checkpoint — PR #34 pre-merge state (2026-09-03) — historical,
superseded by the `0-PREV` checkpoint above (PR #34 has since merged — see above; this
section's own "NOT committed/NOT merged" language below describes an earlier point on
2026-09-03, before that merge, and is kept verbatim as historical record)

**State (as of 2026-09-03, before PR #34 merged):**
- Branch: `fix/dispatch-truthfulness`, based on `main` @
  `1f89bfffcc9eda8cc976642535c40d838b456d88` (merge of PR #33, `docs/sync-v4.7-maintenance`).
  **This branch's changes are implemented and validated but NOT committed and NOT merged**
  — `main` itself is still at `1f89bff...` and still has the original dispatch-truthfulness
  bug until this branch is committed, pushed, reviewed, and merged.
- runtime: `4.7.0` (`jarvis.__version__`, unchanged by this work).
- formal release: `v4.5.1` (unchanged).

**Central dispatch truthfulness — IMPLEMENTED AND VALIDATED (uncommitted), root cause
confirmed and fixed.** `jarvis/core/dispatcher.py`'s `dispatch_action()`/
`dispatch_action_async()` previously wrapped any normally-returning handler result as
`success=True` unconditionally — an explicit handler failure (`ActionResult(success=False)`,
`{"success": False}`, `{"status": "failed"/"error"}`) was silently turned into dispatcher
success. `jarvis/core/app.py`'s `process_text_command()` separately initialized
`status_flag = "success"` and never re-derived it from `action_result.success` after
dispatch, so a failed action could still produce a top-level `{"success": True}`, a
`status="success"` interaction-log entry, a `success=True` memory episode, and the
success-flavored fallback text `"Đã thực hiện lệnh: ..."`.

**Return-convention audit (evidence, not guesswork):**
- `ActionResult` handler returns: no current production handler does this, but it is the
  dataclass's own official contract (`jarvis/core/models.py`) and is supported.
- `{"success": bool, ...}`: the dominant established contract — `jarvis/automation/control.py`,
  `jarvis/comms/mobile_bridge.py`/`discord.py`, `jarvis/smart_home/home_assistant.py`,
  `jarvis/ui/dashboard.py`, `jarvis/workers/night_shift.py`/`auto_updater.py`,
  `jarvis/plugins/spotify.py`.
- `{"status": "failed"/"error", ...}`: the dominant contract inside `jarvis/core/app.py`'s
  own ~60 dispatcher-registered `_handle_*` methods, and `jarvis/plugins/spotify.py`.
- **Bare boolean `False`/`True` as a handler's entire payload has no established contract
  anywhere in the repository** (confirmed by grep across every dispatcher-registered
  handler) — booleans only ever appear nested inside an explicit `"success"` key. Decision:
  a bare `False` remains ordinary successful data, per the "no generic falsiness" rule.
- Many custom `"status"` strings (`"welcome_spoken"`, `"tts_unavailable"`,
  `"overlay_unavailable"`, `"healthy"`, `"skipped"`, `"started"`, `"ok"`) do **not** match
  `"failed"`/`"error"` literally and are correctly left as success — inventing a broader
  failure rule for them would misclassify real successful payloads (e.g.
  `_handle_tts_welcome()` returning `{"status": "tts_unavailable"}` when TTS is off, which
  is not an error condition worth failing the whole dispatch over).

**Fix implemented:**
- New shared pure function `jarvis/core/dispatcher.py::_normalize_handler_outcome(raw)` →
  `(success, data, error, error_code)`, used identically by both `dispatch_action()` (sync)
  and `dispatch_action_async()` — no sync/async divergence.
- `action.post_dispatch`'s `success=` event parameter now reflects the real normalized
  outcome (previously hardcoded `True`) — a failed normalized result never emits a
  `success=True` event. No new event type was added; existing `action.pre_dispatch`/
  `action.failed` (exception path) architecture is untouched.
- `process_text_command()` now sets `status_flag = "success" if action_result.success else "failed"`
  immediately after dispatch, before response-text selection. Failure response-text
  precedence: `action_result.error` → `action_result.data["message"]` → `action_result.error_code`
  → neutral fallback `"Không thể thực hiện lệnh."` — never a fabricated reason, never the
  success-flavored `"Đã thực hiện lệnh: ..."` fallback for a failed action.
  `CONFIRMATION_REQUIRED` remains failure end-to-end (verified: gated handler never runs).
- `_on_gesture_event()`'s `triple_clap`/`clap_pause_clap`/generic-pattern loops (previously
  discarding each `ActionResult` and unconditionally logging `status="success"`) now track
  real per-action success and log `status="failed"` truthfully when any action fails. The
  `double_clap` welcome-sequence branch was deliberately left unchanged — it logs the
  *launch* of an async background sequence, a genuinely different claim from per-action
  outcome, and correcting it would need a threading-model restructure out of this task's
  narrow scope.
- Safety preserved unchanged: `SafetyGateInterceptor`, RBAC/privilege checks,
  `ACTION_NOT_FOUND`, and all `CONFIRMATION_*` semantics were not touched.

**`hardware_status_query` compatibility alias — owner-authorized, RESOLVED (same branch,
2026-09-03).** The dispatch-truthfulness fix above surfaced a genuine, separate,
pre-existing bug: `jarvis/llm/router.py` intentionally routes several hardware/status voice
queries (e.g. "Báo cáo tình trạng hệ thống") to action name `hardware_status_query` from
multiple call sites (system prompt examples, Vietnamese/unaccented rule fallback, status
regex handling, response-generation compatibility logic), but `jarvis/core/app.py` had only
ever registered a dispatcher action named `system_status` — so dispatch correctly returned
`ACTION_NOT_FOUND`, a failure previously masked by the dispatch-truthfulness bug itself
(the dispatcher used to report `success=True` regardless). Owner decision: leave
`jarvis/llm/router.py` untouched (an intentional, multi-site router contract; changing it
would be a broad change) and fix the narrow registration gap instead. Fix
(`jarvis/core/app.py::_register_core_actions()`): register `hardware_status_query` against
the **same** existing `self._handle_system_status` handler already used by `system_status`
— no duplicated implementation logic, `system_status` itself unchanged. Covered by 5 new
tests (`tests/unit/test_dispatch_truthfulness.py::TestHardwareStatusQueryAlias`): both
action names exist after core registration, both resolve to the identical underlying
function (`.handler.__func__` identity), `hardware_status_query` no longer returns
`ACTION_NOT_FOUND`, and both names dispatch to the same behavior/result shape.
`tests/unit/test_integration_e2e.py::test_memory_recording_in_process_text_command` now
passes **without that test file being modified**, per explicit owner instruction.

**Final validation evidence (after both fixes, this checkpoint):**
```text
tests/unit/test_dispatch_truthfulness.py (57 tests, +4 alias tests):   57 passed
tests/unit/test_action_dispatcher_safety.py (unchanged):               15 passed
tests/unit/test_app_integration.py (unchanged):                         1 passed
tests/unit/test_integration_e2e.py::test_memory_recording_in_process_text_command
    (NOT modified — now passes via the alias registration):            1 passed
tests/unit/ (full suite):        1413 passed, 1 skipped, 50 subtests passed, 0 FAILED
```
`jarvis.__version__` unchanged at `4.7.0` — not described as a separate version/release.
Files touched: `jarvis/core/dispatcher.py`, `jarvis/core/app.py` (both authorized production
files), plus the authorized test file `tests/unit/test_dispatch_truthfulness.py`. No other
production file was modified — in particular, `jarvis/llm/router.py` and
`tests/unit/test_integration_e2e.py` remain untouched, per explicit owner direction.

**No remaining known issues from this task.** The full unit suite is green (0 failures).
This branch's changes are still uncommitted — see "State" above.

---

## 0-PREV3. Prior Checkpoint (2026-09-02) — historical, superseded by the `0-PREV2`
checkpoint below (itself now superseded by the `0` checkpoint at the top of this file)

This is the single authoritative "what's true right now" section, superseding the
`2026-09-01` checkpoint immediately below it (now demoted to `0-PREV2`, kept as historical
record — not rewritten).

**State:**
- `main`: `aaeeb53f834134bb4490147c238e82e863558caa` (merge of PR #32, `fix/wake-word-whisper-ci`).
- runtime: `4.7.0` (`jarvis.__version__`, unchanged by either PR below).
- formal release: `v4.5.1` (latest tagged/published GitHub Release; tag confirmed present
  and confirmed an ancestor of the `main` commit above — the `0-PREV` checkpoint's
  "tag/GitHub Release have deliberately not been created yet" language for `v4.5.1` is now
  stale; the tag was created after that checkpoint was written. `v4.0.1` is no longer the
  latest formal release).
- CHANGELOG development history reaches `v4.7.0` ("Sprint 2 Acoustic & UX Hardening
  Release"), plus a `main`-only "Post-v4.7.0 Maintenance" section (not a version bump)
  covering the two PRs below.

**PR #31 — `fix(healing): report recovery outcomes truthfully` — MERGED, RESOLVED.**
Feature commit `e24a366d98a38a53f3467e2b8ee17e1d4e44c63e`, merge commit
`10d470237b0fe4bc295f02215b4606590d79d17e`. `jarvis/healing/terminator.py`
(`AutonomousTerminator.terminate_process()`, `HealingEngine.heal_hung_process()`,
`HealingEngine._read_ram_percent()`) now guarantees:
- Attempted process termination (`.terminate()`/`.kill()` called without raising) is
  **never** by itself treated as successful termination — only a confirmed post-wait
  outcome (`psutil.NoSuchProcess`, a successful `.wait()`, or a nonzero Win32
  `TerminateProcess()` return code) counts as success.
- Healing success requires a confirmed termination outcome; a mocked/injected test backend
  is trusted only via an explicit `terminate_process()` callable's actual boolean return —
  never via the mere presence of a `killed_pids`-style bookkeeping attribute.
- False, exception-raising, or unconfirmed termination remains a reported failure.
- `report["reason"] == "TERMINATION_FAILED"` is set truthfully whenever termination could
  not be confirmed or raised an exception.
- No fabricated reclaimed RAM: the old `max(40.0, ram_percent - 25.0)` synthetic formula is
  gone. `reclaimed_ram` is only ever an observed `ram_before - ram_after` delta (floored at
  0.0) and is omitted from the report entirely when RAM cannot be measured.
- No production `hardware.set_ram()`-style fake telemetry mutation — `_read_ram_percent()`
  only reads.
- Unavailable RAM (no hardware provider, no `psutil`) stays reported as unavailable — never
  defaulted to an invented number.
- "Hệ thống bị quá tải" ("system overloaded") wording is only prepended when RAM was
  actually measured before termination AND is at/above the configured `ram_threshold` —
  never asserted unconditionally.
- "Success"/"đã xử lý" wording only appears after termination has been confirmed.
- psutil/Win32 termination results are verified (their actual return values/exceptions
  inspected), never assumed.
- Mixed recovery (multiple processes in one healing pass) preserves truthful per-process
  outcomes — one process's success/failure never leaks onto another's report.

Validation evidence (from the merged PR): `tests/unit/test_healing_truthfulness.py` — 20
passed; `tests/test_self_healing.py` (legacy) — 7 passed; feature-branch full unit
evidence — 1135 passed, 50 subtests passed; independent safe smoke — PASS. No real existing
process was intentionally terminated during validation.

**PR #32 — `fix(test): make whisper wake-word fallback deterministic` — MERGED, RESOLVED,
TEST-ONLY.** Feature commit `c70c79384744e1756bc893125cd967c69f2276d8`, merge commit /
current `main` `aaeeb53f834134bb4490147c238e82e863558caa`. Root cause: `WakeWordDetector`
only selects the `WHISPER` engine when `FASTER_WHISPER_AVAILABLE` is true
(`jarvis/audio/wake_word.py`); the prior version of `tests/unit/test_wake_word_p0.py`
injected a mocked Whisper model **after** detector construction without forcing that
optional-dependency-availability flag deterministically, so in an environment without
`faster-whisper` installed the detector would already have selected `ACOUSTIC_FALLBACK`
before the mock could exercise the Whisper path — an environment-dependent, non-deterministic
test outcome, not a production defect. Fix (test file only): the test now explicitly patches
`FASTER_WHISPER_AVAILABLE=True`, constructs the detector inside that patch, and asserts
`engine == WHISPER`; the `MagicMock` model injection is unchanged. **No production
wake-word behavior changed; no heavy dependency added to CI.**

Validation evidence: focused test — 1 passed; wake-word P0 (`test_wake_word_p0.py`) — 19
passed, 1 skipped; wake-word + acoustic hardening combined — 64 passed; feature-branch full
unit evidence — 1356 passed, 1 skipped, 50 subtests passed. **Post-merge `main` CI: GREEN.**

**Latest verified unit evidence on `main` (post-PR #32):**
```text
1353 passed
4 skipped
50 subtests passed
0 failures
0 errors
```
Skip counts can and do vary by environment (which optional dependencies — e.g.
`faster-whisper`, `cv2`, `mediapipe` — happen to be installed on the machine running the
suite); a different skip count than this snapshot is not by itself evidence of a regression.

**CENTRAL DISPATCH TRUTHFULNESS WAS OPEN AS OF THIS CHECKPOINT.** Known issue, not fixed by
PR #31 or PR #32: `ActionDispatcher` / `process_text_command` (`jarvis/core/app.py`) may
still incorrectly propagate an explicit failed action outcome as a reported success. **This
is now superseded — see the `0` checkpoint above**: it was implemented and validated on
branch `fix/dispatch-truthfulness` on 2026-09-03 (not yet committed/merged as of that
checkpoint). Do not read this paragraph as describing the current state; kept verbatim as
historical record of what was true at this checkpoint's own snapshot time.

---

## 0-PREV4. Prior Checkpoint (2026-09-01) — historical, superseded by the 2026-09-02
checkpoint above

This section is the single authoritative "what's true right now" section. Everything below it —
`0-PRE`, `0-PRE2`, `0-PRE3`, `0A`, `0B`, `0C`, `0D`, and the older `## 1` onward sections —
is a **historical, point-in-time snapshot** captured while each piece of work was still
in progress. Their "in progress, uncommitted, not pushed, no PR opened" language describes
the state **at the moment that section was written**, not the current repository state.
Do not read any "in progress, uncommitted" statement below this checkpoint as describing
`main` today — all of that work has since merged. Detailed historical records, findings,
and validation numbers in those sections are preserved as-is and are not being rewritten;
use this checkpoint, plus actual `git log`/`git status`, as the source of truth for current
state. This checkpoint supersedes the prior `5f9f6da` checkpoint below (its own validation
numbers are preserved as historical record further down, not rewritten).

**v4.3.2 checkpoint lineage** (deliberately phrased as lineage, not a single "Current main" SHA —
that framing goes stale the moment the checkpoint PR itself merges):
- pre-checkpoint merged `main`: `1ad5b6d246d86ad2cb3af40840b13dd576041815` ("Merge pull request
  #20 from Huynh-Minh-Hoa/docs/night-shift-runtime-reality") — the last `main` commit before the
  v4.3.2 documentation checkpoint was authored.
- v4.3.2 documentation checkpoint commit: `6012487441dc03bdb78aa8d5538adf32e7547c08` (PR #21) —
  once this PR merges, `main` moves to (or past) this commit; always confirm via `git log`/
  `git rev-parse origin/main` rather than trusting either SHA above as permanently "current."

**Updated 2026-09-02** (branch `eval/stt-real-mic-baseline-correction` merged `origin/main`
a second time, now up to commit `857d729`): `CHANGELOG.md` development history now reaches
**v4.5.0** — a maintenance milestone, **not** a formal release/tag (latest formal GitHub
Release remains `v4.0.1`). **`jarvis.__version__`/`pyproject.toml` is still `4.4.0` — v4.5.0
did NOT bump it** (no `### Version` note in its CHANGELOG entry; confirmed directly against
`jarvis/__init__.py`). v4.4.0 remains the one exception where a CHANGELOG heading and the
runtime version moved together (`4.1.0 → 4.4.0`, commit `4bebc42`) — v4.5.0 reverts to the
normal pattern of every other milestone since v4.0.1 (dev-history label only). Always check
`jarvis/__init__.py` directly; never infer the runtime version from the latest heading.
v4.4.0 fixed a `parse_intent(None)` crash, a `WakeWordDetector` pure-tone false positive, 23
`subprocess.run(text=True)` call sites missing `encoding=`, expanded Tier-1 `rule_engine`
coverage, and adjusted the (now-superseded — see the STT eval section below) STT eval's old
phrase categorization. v4.5.0 (commits `89e4c7d`→`29e8ade`→`1b1c847`→`442ed0f`→`857d729`,
all now merged) added: an E9 acoustic-echo-feedback-loop fix in `jarvis/core/app.py`;
SecretsManager wired into 6 more production modules; a new N=152 text-only routing eval
(`tests/eval/routing_eval_n150.py`); an emoji-detection regex extended to BMP ranges; a full
test-suite cleanup (~44 failures → 0); `CREATE_NO_WINDOW` added by default to
`jarvis/utils/subprocess_utils.py::run_safe()`; and a new `scripts/system_diagnostic.ps1`.
See CLAUDE.md's "Current baseline note" (§1) for the full breakdown.

**Updated 2026-09-02 — v4.5.1 release prep (branch `release/v4.5.1`, based on `main` @
`6666cd1`):** `eval/stt-real-mic-baseline-correction` (referenced throughout the paragraph
above and elsewhere in this file) is no longer an active branch — it merged cleanly via
**PR #23**, merge commit `6666cd15c25db4f372afcaa0b0628dee9dc5731d`, and post-merge GitHub
Actions **CI #135** was verified **green (success)**. `main` before this release-prep work
started: `6666cd15c25db4f372afcaa0b0628dee9dc5731d` (identical to the PR #23 merge commit —
no other commits landed on `main` in between). This release-prep branch, `release/v4.5.1`,
bumps `jarvis.__version__` to **`4.5.1`** and adds a new `v4.5.1` CHANGELOG section above
`v4.5.0` — **v4.5.1 is the intended next official GitHub Release/tag**, packaging the
v4.4.0/v4.5.0 CHANGELOG-milestone work described above plus PR #23's STT baseline
correction into one release checkpoint. **The `v4.5.1` tag and GitHub Release have
deliberately not been created yet** (separate follow-up action, explicitly out of scope for
this release-prep commit) — until they exist, `v4.0.1` remains the actual latest formal
release. Do not describe `v4.5.1` as published, and do not create the tag/release as a side
effect of any other task without the user's explicit go-ahead. Full unit-suite evidence for
this release-prep commit (`tests/unit/`, pytest's own terminal counts): **1085 collected,
1085 passed, 0 failed, 0 skipped** (plus 50 subtests passed, unchanged from PR #23's own
final evidence) — `python -c "import jarvis; print(jarvis.__version__)"` prints `4.5.1`.

**Post-`d62cb61` evolution merged onto `main`:**

- **v4.2.0 — Security Hardening & Stability (7 workstreams):** `__globals__` class-level
  sandbox-escape patch; Night Shift daemon sandbox-isolation audit (`docs/night_shift_audit.md`);
  AppContainer B2 implementation + real-OS dual-evidence testing (zero-network-capability
  AppContainer, kernel-level socket blocking verified — see "Architecture reality" below for
  its actual production-wiring status, which is more limited than "implemented" alone implies);
  `PromptGuard` prompt-injection defense (`jarvis/security/prompt_guard.py`); per-user
  `TokenBucketRateLimiter` comms rate limiting across Telegram/Zalo/Discord/Mobile Bridge;
  Discord functional tests + Watchdog chaos-test (MTTR); STT/benchmark test infrastructure
  (`docs/benchmark_results.md`, `scripts/benchmark_stt_cuda.py`).
- **v4.2.1:** Faster-Whisper hallucination-mitigation guards (`jarvis/stt/engine.py`) and the
  STT intent-misrouting evaluation framework (`tests/eval/stt_intent_eval.py`).
- **v4.3.0:** AppContainer B2 real-OS dual-evidence confirmation; email IMAP 5-layer security
  hardening (`jarvis/comms/email_imap.py`); Windows Credential Manager/`keyring`-backed Secrets
  Manager (`jarvis/security/secrets.py`).
- **v4.3.1:** committed the real-microphone STT evaluation dataset — **90 real
  microphone recordings** (45 clean + 45 noisy) under `tests/eval/audio/`, each evaluated
  against both `small` and `large-v3` faster-whisper models, plus the resulting evaluation
  results/summaries in `docs/eval/`. 90 recordings, not 90 model-runs or 180 recordings — see
  the STT reality note below for exactly how the 90-recording dataset and the 180-row raw
  results file relate.
- **v4.3.2 (current) — Maintenance & Runtime Reality Sync:** three merged maintenance
  workstreams, consolidated under one CHANGELOG milestone (see `CHANGELOG.md`'s "v4.3.2" section
  for full detail): (1) `ProactiveConfig.from_dict()`'s health-monitor fallback defaults now
  single-sourced from the dataclass itself, fixing silent drift toward obsolete thresholds on
  partial config dicts; (2) package/runtime/installer/dashboard version-metadata single-source
  semantics — `pyproject.toml` dynamically derives its version from `jarvis.__version__`,
  `installer/setup.iss` no longer owns a duplicate `AppVersion` literal, and
  `jarvis/ui/dashboard.py` no longer displays a stale hardcoded `1.0.0`; (3) Night Shift
  scheduler/reporting documentation reality sync — `docs/night_shift_audit.md` corrected to
  match actual code (no enforced 02:00–05:00 window, `report_time` unused, `web_search`/`notify`
  are placeholders, report delivery is local-file-only), plus a docstring-only correction in
  `jarvis/workers/night_shift.py` (no runtime logic changed). Follow-ups #1–#3 below are now DONE;
  see this checkpoint's "Immediate follow-ups" section for exact evidence per workstream.

**Newest checkpoint CI evidence — GitHub Actions CI run #121, PR #21, for commit `6012487`
(the v4.3.2 documentation checkpoint commit itself; externally verified — conclusion `success`,
all four jobs passed: Syntax Check, Unit Tests, Import Validation, Pipeline Summary). The exact
collected/passed/skipped/failed counts for run #121 itself were not independently pulled from
that run's logs this session — not invented here.**

**Pre-checkpoint merged-main CI evidence — GitHub Actions CI run #120, for commit `1ad5b6d`
(externally verified — conclusion `success`, all four jobs passed: Syntax Check, Unit Tests,
Import Validation, Pipeline Summary). Exact counts for run #120 itself likewise not pulled from
its logs.** The most recent **locally**-verified full `tests/unit/` evidence (from the Night
Shift reality-sync branch, run before merge into `1ad5b6d` — labeled LOCAL, distinct from either
CI run's own count):
```text
1008 collected
1008 passed
0 skipped
0 failed
```

**Historical CI baseline (a370633-era, superseded — kept for context only, do not cite as
current):** GitHub Actions CI run #108, for commit `a370633`:
```text
993 collected
990 passed
3 skipped
0 failed
```
All four CI jobs passed: Syntax Check, Unit Tests, Import Validation, Pipeline Summary.

**Architecture reality — sandbox execution backend (do not blur these two statements):**
- **Production** `CodeInterpreterSandbox.execute_python()` (`jarvis/sandbox/interpreter.py`)
  calls `spawn_low_integrity_process()` only: Windows OS Restricted Token + Low Integrity SID
  (`S-1-16-4096`) + Windows Job Object (`ActiveProcessLimit`/`JobMemoryLimit`, assigned to the
  still-suspended child before `ResumeThread`) + scrubbed environment + AST-validated/module-
  restricted preamble + bounded (1MB-capped, two layers) stdout/stderr capture + a readiness-
  sentinel retry-safety boundary. This is the real, current production isolation boundary.
- **AppContainer** (`spawn_appcontainer_process()` in `jarvis/sandbox/security.py`) is a
  separate, real, non-trivial implementation — a zero-network-capability
  (`SECURITY_CAPABILITIES`/`CapabilityCount=0`) AppContainer launch path, confirmed working via
  real-OS dual-evidence testing (compute succeeds; `socket.connect()` is kernel-blocked with
  `PermissionError`/`OSError`) in `tests/integration/test_sandbox_os_boundaries.py` and
  `tests/e2e/test_r3_network_sandbox_e2e.py`. It is **implemented and tested, but has no caller
  in `jarvis/sandbox/interpreter.py` or anywhere else in production code** —
  `execute_python()` does not use it. Do not describe current production Python execution as
  having AppContainer network isolation; it does not, today.
- Confirmed by direct source read of `jarvis/sandbox/security.py::strip_sandbox_ready_sentinel()`:
  it explicitly strips the LF-terminated, CRLF-terminated, and bare (no-line-ending) forms of
  the readiness sentinel. This is **not** a current limitation — a stale "LF-only" claim from an
  earlier snapshot of this project no longer matches the code and must not be reintroduced
  without re-reading the function first.

**STT reality — three distinct kinds of evidence, do not conflate:**
- **(A) Real-microphone acoustic evaluation** — the dataset is **90 real microphone
  recordings total** (45 clean + 45 noisy conditions). Each of those 90 recordings was
  evaluated against **two** faster-whisper models (`small` and `large-v3`), so the raw
  per-trial results file (`docs/eval/stt_eval_results.json`) contains **180 model-evaluation
  rows** — 180 rows does **not** mean 180 recordings; it means 90 recordings × 2 models.
  `docs/eval/stt_eval_summaries.json` holds the aggregated rates per model/condition. This is
  the only data source that speaks to actual recognition/intent-routing quality.
  - `small` (int8): clean 15.6% correct / 2.2% misrouted / 82.2% silent-failure, median latency
    ~853ms; noisy 17.8% correct / 2.2% misrouted / 80.0% silent-failure, ~780ms.
  - `large-v3` (int8_float16): clean 28.9% correct / 2.2% misrouted / 68.9% silent-failure,
    ~2.8s; noisy 31.1% correct / 2.2% misrouted / 66.7% silent-failure, ~2.8s.
  - The dominant current problem is **high end-to-end abstention rate**, not broad
    unsafe-action misrouting — misrouting sits flat at ~2.2% across every model/condition
    (that single case among the 90 recordings was arguably correct JARVIS behavior anyway),
    dropping to 0.0% above a per-model/condition confidence threshold (~0.5–0.7).
  - **Corrected 2026-09-02, branch `eval/stt-real-mic-baseline-correction`
    (`docs/eval/stt_eval_failure_decomposition.md`/`.json`): the "silent-failure" figures
    quoted above are an end-to-end abstention rate (`STT_EMPTY` + `ROUTER_ABSTAIN`), not a
    pure STT recognition-failure rate.** Re-deriving each of the 180 historical rows'
    outcome directly from its own `(transcript, predicted_intent, intent_gt)` fields via the
    new `classify_outcome()` (`tests/eval/failure_decomposition.py`) shows the 134 legacy
    `SILENT_FAILURE` rows split into only **3 `STT_EMPTY`** (transcript truly empty) vs.
    **131 `ROUTER_ABSTAIN`** (STT produced non-empty — often garbled — text that the Tier-1
    rule-engine simply didn't match). Per AUDIT_METHODOLOGY.md's causal-attribution rule,
    this decomposition alone does **not** establish whether the dominant cause is poor
    transcription quality or an overly strict keyword matcher — both are consistent with
    "non-empty but wrong" transcripts. **The auxiliary token-similarity metric WAS computed**
    for all 180 historical rows (`tests/eval/failure_decomposition.py::compute_text_similarity_stats()`,
    built on `tests/eval/text_normalize.py::token_similarity()`, deliberately never used to
    determine intent outcome — see `docs/eval/stt_eval_failure_decomposition.md`'s "auxiliary"
    section for the full per-model/condition/outcome breakdown): overall mean similarity is
    only ~0.17 (median 0.0), and `ROUTER_ABSTAIN` rows specifically average ~0.115 — i.e. most
    non-empty transcripts, including the large majority of `ROUTER_ABSTAIN` rows, are also
    substantially textually wrong, not merely differently-phrased-but-accurate. This is real
    evidence against the naive "only 3/180 are STT_EMPTY, so transcription must be mostly fine"
    inference. It does **not**, by itself, conclusively separate the two candidate causes —
    a low similarity score cannot distinguish "STT acoustically mis-heard the words" from "STT
    heard something close but the Tier-1 rule-engine's fixed keyword list wouldn't have matched
    it anyway," and a manual per-row causal review (reading each garbled transcript against its
    audio and judging which failure mode applies) was **not** performed as part of this
    correction — that remains the one way to fully resolve the two candidate causes. No
    production STT threshold
    (`no_speech_threshold`/`log_prob_threshold`/`compression_ratio_threshold`/beam_size),
    router behavior, or historical committed evidence file was changed — this was a
    re-classification pass over existing evidence, not new acoustic evidence, and does not
    by itself earn Tier 1 status for STT recognition quality. Also fixed in the same pass:
    `tests/eval/stt_intent_eval.py` carried a stale ASCII/unaccented phrase list that had
    drifted from what `tests/eval/record_test_set.py` actually recorded (one entry,
    `open_app` variant 4, had drifted in content, not just accenting — recorded prompt was
    "khởi động chrome", evaluator's stale copy claimed "launch spotify"); both scripts now
    import a single-sourced `tests/eval/phrase_manifest.py`. The evaluator also gained an
    explicit `--backend {direct,production}` flag — `production` calls
    `jarvis.stt.engine.FasterWhisperSTT.transcribe()` directly (no reimplementation of its
    filtering) so a real production-path rerun is possible without conflating it with the
    historical raw-`WhisperModel` direct backend (`beam_size=3`, no RMS pre-gate, no
    post-filter — see `docs/eval/stt_eval_failure_decomposition.md`'s Phase 4 table for the
    full enumerated diff). A real CUDA production-backend rerun (Phase 8) was **not**
    executed this session: CUDA hardware is present (`nvidia-smi` succeeds) but
    `faster-whisper`/`ctranslate2` are not installed in any available interpreter and no
    project venv with them was found — reported as not-executed rather than faked, per
    AUDIT_METHODOLOGY.md. Branch `eval/stt-real-mic-baseline-correction` (now merged into
    `main` via **PR #23**, merge commit `6666cd15c25db4f372afcaa0b0628dee9dc5731d`, no
    longer an active branch) landed the STT eval baseline correction across **two** pushed
    commits, each independently reviewed — do not describe either one in isolation as the
    final state; the merge commit above is what actually reached `main`. Full
    `tests/unit/` counts below are pytest's own terminal "collected"/pass-fail summary, NOT
    the JUnit XML `tests` attribute — see the dedicated correction note immediately below
    this list for why those differ.

    - **Base** commit `2b73a49` (same commit as `main` at the time of this work): **1008
      collected, 1008 passed, 0 failed, 0 skipped** locally (matches GitHub Actions CI run
      #126's 1008 collected exactly; CI's own pass/skip split, 1005 passed/3 skipped, is a
      known local-vs-CI-runner divergence already documented earlier in this file for prior
      checkpoints — not specific to this change).
    - **First commit, `42098d6`** ("eval(stt): separate recognition and routing failures" —
      introduced the core CORRECT/MISROUTED/STT_EMPTY/ROUTER_ABSTAIN decomposition, the
      single-sourced phrase manifest, the auxiliary text-similarity metric, and the
      `--backend {direct,production}` evaluator refactor): **1064 collected, 1064 passed,
      0 failed, 0 skipped** (plus 50 subtests passed, unchanged from base). Net **+56** versus
      base, in `tests/unit/test_stt_eval_failure_decomposition.py`.
    - **Second commit, `29da633`** ("eval(stt): harden baseline evidence reproducibility" —
      fixed 5 issues an independent review found in `42098d6`: stale test-count prose,
      an auxiliary-metric contradiction, a machine-specific hardcoded default in the report
      generator, an ambiguous `"silent"` key in new evaluator output, and a
      host-path-dependent historical-row lookup; added 21 more tests, including a new file
      `tests/unit/test_stt_intent_eval_threshold_curve.py`) — **current branch head**:
      **1085 collected, 1085 passed, 0 failed, 0 skipped** (plus the same 50 subtests,
      unchanged). Net **+77** versus base (56 from the first commit + 21 from the second).
      Running just the two dedicated STT-eval test files
      (`test_stt_eval_failure_decomposition.py` + `test_stt_intent_eval_threshold_curve.py`)
      in isolation: **77 passed**, 0 failed.

    **Note on the +46/+56 discrepancy inside `42098d6` itself**: the originally pushed
    commit `42098d6`'s own commit message and the first draft of this section's prose said
    "46 new tests"/"1054 collected" — accurate for the test file's content partway through
    that same working session, before 10 more tests (`TestComputeTextSimilarityStats`, plus
    two `TestRenderMarkdownReport` cases) were added later in the *same* commit to lock in
    the auxiliary text-similarity metric (§ auxiliary text-quality note below) before it was
    ever pushed. The commit message itself is not rewritten (the commit is public/pushed) —
    but the actual file has always had all 56 tests since `42098d6`, and 56/1064 are the
    correct historical numbers **for that one commit**; they are no longer the current branch
    totals now that `29da633` is on top of it (see the 77/1085 current numbers above). Do not
    cite 46/1054 as evidence for anything.

    **Correction (found via independent GitHub Actions CI #126 verification against this
    exact base commit, 2026-09-02): an earlier draft of this evidence conflated pytest's own
    "collected items" count with the JUnit XML `<testsuite tests="...">` attribute, which are
    NOT the same number in this repository.** `pytest-subtests` (`pyproject.toml`, declared
    dependency) emits one additional `<testcase>` entry per `subtests.test()` invocation in
    JUnit XML on top of the entries for the enclosing regular tests — it does **not** add to
    pytest's own "collected N items" count or its terminal "N passed" line, which count only
    top-level collected test items. At base commit `2b73a49`, pytest's terminal summary reads
    "1008 passed, **50 subtests** passed" (collected = 1008) while the JUnit XML `tests`
    attribute for the same run reports 1058 = 1008 + 50 — the JUnit total is inflated by
    exactly the 50 pre-existing subtests, unrelated to this branch. At the first commit
    (`42098d6`), pytest's terminal summary read "1064 passed, 50 subtests passed" (collected =
    1064) while the JUnit `tests` attribute would report 1114 = 1064 + 50; at the current
    branch head (`29da633`), pytest's terminal summary reads "1085 passed, 50 subtests
    passed" (collected = 1085) while the JUnit `tests` attribute would report 1135 = 1085 +
    50 — both inflated by exactly the same 50 pre-existing subtests, which this branch never
    changed. Earlier drafts of this document cited JUnit totals (1058/1104, then a stale
    intermediate 1054 pytest count, then briefly called `42098d6`'s own 1064 the branch's
    "final" number even after `29da633` was pushed on top of it) as if they were the current
    pytest collected/passed counts; the correct, authoritative numbers for the current branch
    head are the ones in the bulleted list above, obtained via direct `subprocess.run()` capture of
    pytest's own terminal output (not the JUnit XML file, and not piped through a shell
    `tail`/`tr`, both of which independently proved unreliable for capturing pytest's final
    `\r`-terminated summary line in this Windows Git-Bash environment — see this branch's own
    git history for that investigation) — and critically, invoked with pytest's own
    single `-q` from `pyproject.toml`'s `addopts` only, never a redundant second `-q` on the
    CLI (double `-q` silently suppresses the terminal summary line entirely, which was the
    proximate cause of the earlier missing-summary confusion).
  - **(A-merge-note, 2026-09-02)** After merging `origin/main`, two things need to stay
    distinct: `tests/eval/routing_eval_n150.py` (N=152, text-only Tier-1 `rule_engine`
    routing accuracy, no STT/audio involved — a different eval answering a different
    question than the acoustic eval above) must never be cited as acoustic/STT evidence; and
    the historical 4 `MISROUTED` rows above are all `intent_gt="open_app"`/`phrase="variant_3"`
    ("mở spotify", routed by Tier-1 to `action_name="spotify"`) — `main`'s own v4.4.0 CHANGELOG
    entry independently found and fixed this same ambiguity in its own (separate, now-superseded)
    phrase categorization, but `EXPECTED_ACTIONS["open_app"]` here deliberately still excludes
    `"spotify"` so these 4 historical rows are not silently reclassified `CORRECT`. See
    `tests/eval/stt_intent_eval.py` and `tests/eval/failure_decomposition.py`'s merge-note
    comments for the full reasoning.
- **(B) Real CUDA throughput benchmark, synthetic (non-speech) input** (`docs/benchmark_results.md`
  §1): genuine GPU latency measurement on real hardware (GTX 1650 Max-Q), but the input is a
  synthesized sine-wave signal, not recorded speech — it measures pipeline throughput (RTF), not
  recognition accuracy. Do not cite it as an accuracy claim.
- **(C) Historical mock/adapter figures** (`docs/benchmark_results.md` §2): explicitly tagged
  `[MOCK — đo trên adapter, không phản ánh model thật]` with an audit warning banner,
  structurally separated from (B). Do not cite as real model latency.

**Immediate follow-ups (confirmed during orientation, not yet actioned — each is its own future
task, not bundled into a documentation-only sync):**
1. **DONE (2026-09-01, branch `fix/proactive-config-defaults`):** `ProactiveConfig.from_dict()`
   (`jarvis/proactive/engine.py`) contained stale fallback defaults (5.0/90.0/85.0/10.0/85.0/20.0/60.0)
   that no longer matched the raised dataclass-field defaults (30.0/92.0/92.0/5.0/92.0/15.0/600.0) —
   only manifested when a partial config dict supplied some but not all health-monitor threshold
   keys. Fixed by sourcing every fallback from a fresh `cls()`/`ProactiveConfig()` instance
   (`_defaults = cls()`) inside `from_dict()` instead of duplicating numeric constants, so future
   dataclass-default tuning cannot drift out of sync again. 4 new regression tests added to
   `tests/unit/test_proactive_engine.py`
   (`test_proactive_config_empty_and_none_match_dataclass_defaults`,
   `test_proactive_config_partial_nested_health_uses_current_defaults`,
   `test_proactive_config_partial_flat_health_uses_current_defaults`,
   `test_proactive_config_nested_health_overrides_flat_value`); one pre-existing test
   (`test_proactive_engine_unified_tick`) had its mock RAM fixture bumped from 92.0 to 95.0 since
   it had implicitly depended on the old stale `ram_threshold` fallback to trigger its assertion.
   Evidence this session: `tests/unit/test_proactive_engine.py` — 49 passed; full `tests/unit/` —
   997 collected, 997 passed, 0 failed; `ruff check`/`py_compile`/`git diff --check` all clean.
   See `CHANGELOG.md`'s "ProactiveConfig Fallback-Default Fix" entry for full detail.
2. **DONE (2026-09-01, branch `chore/version-metadata-semantics`) — semantics clarified and
   single-sourced; no version number was bumped.** Classification, confirmed against actual code
   (not assumed): (A) package/distribution version — `pyproject.toml` now declares
   `dynamic = ["version"]`, resolved via `[tool.setuptools.dynamic] version = {attr = "jarvis.__version__"}`
   (no more duplicate literal); (B) runtime version — `jarvis.__version__`, the one canonical
   `"4.1.0"` literal, kept as a plain top-level string assignment in `jarvis/__init__.py`
   specifically because `jarvis/workers/auto_updater.py::get_current_version()` and
   `scripts/health_check_report.py::get_version()` both locate it by scanning that file's raw
   source text (confirmed by reading both — moving it behind an import, e.g. the
   `jarvis/_version.py` pattern originally suggested for this task, would have silently broken
   both); (C) `config/default_config.yaml`'s `system.version` (`"1.0.0"`) — confirmed by
   repo-wide audit to have zero production consumers (`jarvis/core/config.py` has no "version"
   handling at all, and no other `jarvis/` module reads the dot-notation key `"system.version"`);
   documented as non-authoritative in a YAML comment, value and key left unchanged, no schema
   semantics invented; (D) formal release version — Git tags/GitHub Releases, latest `v4.0.1`,
   independent of (A)/(B) — `.github/workflows/release.yml` derives its own version purely from
   the pushed tag name, not touched; (E) CHANGELOG milestone headings (v4.1.x–v4.3.1) — dev-history
   labels, not formal releases, not rewritten; (F) README — the single ambiguous "Version" badge
   was split into three explicit labeled pieces (source version 4.1.0 / latest release v4.0.1 /
   CHANGELOG dev-history state), and the stale "633+ passed" test badge was reworded to avoid
   re-staling. New tests: `tests/unit/test_version_metadata.py` (5 tests) and
   `tests/integration/test_package_version_build.py` (1 test, real wheel build — not part of the
   `tests/unit/` fast baseline, run explicitly).

   **Follow-up correction (same day, same branch, commit amended in place — review found the
   installer/dashboard duplicates flagged below were real, non-passive, user-visible/build-affecting
   duplicates, not merely cosmetic, so they were fixed rather than left out of scope):**
   `installer/setup.iss`'s `#define AppVersion "4.1.0"` actually **drove** `[Setup] AppVersion`,
   the installer output filename (`OutputBaseFilename=JARVIS_Setup_v{#AppVersion}`), and the
   `[Registry]` `Version` value — not passive documentation. Fixed: `setup.iss` no longer declares
   any `#define AppVersion "..."` literal; it now requires the value externally
   (`#ifndef AppVersion` / `#error`, with a clear message) and `scripts/build_installer.py` gained
   `_get_canonical_version()` (a lightweight raw-text reader mirroring the existing
   `auto_updater.py`/`health_check_report.py` pattern — deliberately does not `import jarvis`) and
   now invokes `ISCC.exe /DAppVersion=<version> setup.iss`. Similarly, `jarvis/ui/dashboard.py`'s
   hardcoded `"Windows AI Assistant Engine v1.0.0"` (embedded HTML) and `"version": "1.0.0"`
   (`/api/status` field) were confirmed to be genuine application-version displays with no evidence
   of an independent schema/protocol/component-version meaning — both now derive from
   `jarvis.__version__` (imported once as `_jarvis_version`; the HTML substitution uses a literal
   `.replace("{{JARVIS_VERSION}}", _jarvis_version)`, not `.format()`/an f-string, since the
   document contains many literal CSS/JS `{ }` braces that must not be touched). Also revisited:
   `tests/unit/test_version_metadata.py`'s `system.version` source-scan test (a brittle "no future
   file may ever contain this exact text" textual assertion) was replaced with
   `test_config_manager_system_version_is_generic_inert_data`, which tests observable
   `ConfigManager.get()`/`.set()` round-trip behavior and independence from `jarvis.__version__`
   instead; the `pyproject.toml`-duplicate-literal test was kept unchanged (not weakened).
   New tests this follow-up: `tests/unit/test_build_installer_version.py` (3 tests, mocks the
   `ISCC.exe` subprocess boundary — Inno Setup is never required to run these) and 2 new tests in
   `tests/unit/test_ui_dashboard.py` (HTML/API version-display coverage). Evidence at this point
   (superseded by the CI follow-up below — do not cite as final):
   `tests/unit/test_version_metadata.py` + `test_build_installer_version.py` +
   `test_ui_dashboard.py` + `tests/test_cli.py` — 21 passed;
   `tests/integration/test_package_version_build.py` — 1 passed; full `tests/unit/` — 1007
   collected, 1007 passed, 0 failed (1002 + 5 new: 3 installer + 2 dashboard, net 0 change from the
   system.version test replacement); `ruff check`/`py_compile`/`git diff --check` all clean; a
   second real wheel build + clean temp venv install re-confirmed `jarvis.__version__` and
   `importlib.metadata.version("jarvis-assistant")` both report `4.1.0`, matching.

   **CI follow-up (commit `dbb0b53`, a normal follow-up commit — not an amend, since the branch
   was already public and PR #19 already open at this point) — this is the FINAL merged Version
   Metadata evidence, superseding both blocks above.** PR #19's first GitHub Actions run (CI #114)
   failed at test collection: `tests/unit/test_version_metadata.py` had a module-level
   `import yaml`, but the CI Unit Tests job intentionally does not install PyYAML, producing
   `ModuleNotFoundError: No module named 'yaml'` and failing Pipeline Summary as a downstream
   consequence. Root cause confirmed by reading the actual CI job's install list, not assumed. Fix
   (`dbb0b53`, `tests/unit/test_version_metadata.py` only — no dependency added, no production
   code touched): removed `import yaml`; the `system.version`-presence test and the
   `test_config_manager_system_version_is_generic_inert_data` test above were consolidated into
   one test (`test_system_version_config_key_present_and_independent`) that reads the config via
   `ConfigManager().load()` — which already has its own built-in fallback parser for when PyYAML
   isn't installed — instead of calling `yaml.safe_load()` directly. Net effect: 5 → **4** tests in
   `tests/unit/test_version_metadata.py`. Verified in a temporary venv containing CI's actual
   package list (confirmed via that venv's `importlib.util.find_spec("yaml") is None`): both
   `tests/unit/test_version_metadata.py --collect-only` and the full `tests/unit/ --collect-only`
   succeeded with zero errors. **Final merged evidence**:
   `tests/unit/test_version_metadata.py` + `test_build_installer_version.py` +
   `test_ui_dashboard.py` + `tests/test_cli.py` — **20 passed** (was 21);
   `tests/integration/test_package_version_build.py` — 1 passed; full `tests/unit/` — **1006
   collected, 1006 passed, 0 failed** (was 1007 — the exact 5→4 reduction, nothing else changed);
   `ruff check`/`py_compile`/`git diff --check` clean. PR #19's CI (run against the corrected
   commit) passed. **1006 is PR #19's own final merged baseline — it is not the same number as
   this checkpoint's current `main` baseline (1008), which is 1006 plus the 2 further tests Night
   Shift (PR #20) added afterward; do not conflate the two.**

   Evidence from the original pass in this same item (superseded, kept for context only): full
   `tests/unit/` — 1002 collected, 1002 passed, 0 failed; `ruff check`/`py_compile`/`git diff --check`
   all clean; real wheel built via `pip wheel . --no-deps --no-build-isolation` installed into a
   clean temp venv confirmed `jarvis.__version__` and `importlib.metadata.version("jarvis-assistant")`
   both report `4.1.0`, matching. (Note:
   `python -m build` could not be used directly from the repo root — a pre-existing, unrelated,
   tracked `build.py` file at the repo root, the real PyInstaller packaging entrypoint, shadows
   PyPA's `build` package for `-m build` invocations from that directory; not fixed here, out of
   scope. The task's own prescribed `pip wheel` fallback was used instead and works correctly.)
   See `CHANGELOG.md`'s "Version Metadata Semantics & Single-Source Consistency" entry and
   CLAUDE.md's "Version metadata" invariants in §1A for full detail.
3. **DONE (2026-09-01, branch `docs/night-shift-runtime-reality`) — audit doc aligned with
   actual scheduler/reporting behavior; no production behavior/runtime logic changed** (source
   docstrings in `jarvis/workers/night_shift.py` were corrected — see below — but no code path,
   import, or logic changed; full unit-suite count is identical before and after). Confirmed
   against source (not assumed): `NightShiftTask.scheduled_time` defaults to `"23:00"`;
   `add_task()` accepts any caller-supplied `"HH:MM"`; `_schedule_task()` has no time-of-day range
   check anywhere — there is no enforced 02:00–05:00 (or any other) window. `NightShiftTask.report_time`
   (default `"07:00"`) is confirmed **stored task metadata only** — never read by `_schedule_task()`
   or anywhere else in the module (repo-wide grep, 3 total occurrences, all definition/plumbing,
   zero reads). Two further inaccuracies found beyond the original follow-up's scope and corrected
   in the same pass: (a) `docs/night_shift_audit.md` described `[web_search]` as querying real
   search APIs through `PromptGuard.sanitize()` and `[notify]` as posting to comms channels — both
   are currently placeholders returning a canned confirmation string with no network/PromptGuard/comms
   call (`night_shift.py` imports neither `PromptGuard` nor any network module); (b)
   `_send_morning_report()` previously had a stale Telegram-delivery docstring; that docstring was
   corrected in this task (now: "Persist the completed task report to the local JARVIS logs
   directory."). Runtime behavior remains local Markdown persistence only — no comms delivery is
   implemented today. The `[calculate]`/`[compute]`/`[analyze]`/`[analysis]`/`[code]`/`[script]`
   step types and the underlying 6-layer `CodeInterpreterSandbox` defense framework were
   independently re-verified accurate and left unchanged (still the Restricted-Token/Low-Integrity
   backend documented elsewhere in this file — not AppContainer). `docs/night_shift_audit.md`
   corrected in place (all 4 sections required by
   `tests/e2e/test_r2_night_shift_e2e.py::test_r2_audit_documentation_structure_and_verdict`
   preserved verbatim); `CHANGELOG.md`'s historical v4.2.0/R2 entry received a minimal footnote
   annotation rather than a rewrite; `CLAUDE.md` gained a "Night Shift" durable-invariant entry in
   §1A. 2 new regression tests added to `tests/unit/test_night_planner.py`:
   `test_schedule_task_ignores_report_time` and `test_send_morning_report_writes_file_only`.
   **Final validation evidence**, current as of the latest follow-up commit (which fixed
   "docstring still claims Telegram"-style wording that had been left describing the now-corrected
   `_send_morning_report()` docstring in present tense across `CLAUDE.md`/`CHANGELOG.md`/this
   entry/the audit doc/the new test's own docstring): `tests/unit/test_night_planner.py` — 22
   passed; `tests/e2e/test_r2_night_shift_e2e.py` — 10 passed; full `tests/unit/` — 1008 collected,
   1008 passed, 0 failed; `ruff check` — clean; `py_compile` — clean; `git diff --check` — clean;
   `git diff origin/main...HEAD --check` — clean.
4. Evaluate STT accuracy/latency improvements using the now-committed real-microphone dataset
   (`tests/eval/audio/`) rather than any synthetic proxy. **Baseline-correction prerequisite
   DONE** (see the "STT reality" correction above, branch `eval/stt-real-mic-baseline-correction`)
   — the historical evaluator's SILENT_FAILURE/ROUTER_ABSTAIN conflation, phrase-manifest
   drift, and evaluator-vs-production-path differences are now documented and the evaluator
   supports a real `--backend production` path; actual threshold/architecture tuning using
   this corrected baseline is still open and deliberately out of scope for that branch.
5. Decide whether `spawn_appcontainer_process()` should become (or be added alongside) the
   production `execute_python()` backend, after a dedicated compatibility/security validation
   pass — it is not a drop-in replacement without that evaluation.
6. Reassess other isolated/unwired systems separately, each on its own merits — do not wire any
   of them into production casually or as a side effect of another task:
   `jarvis/agent/graph.py::ReActAgent` (zero production callers), OpenWakeWord's known-unfixed
   "initialized but never processed" defect, `jarvis/plugins/loader.py` (generic plugin SDK,
   unused — `app.py` uses a separate hardcoded plugin list), `jarvis/automation/vm.py::VMOrchestrator`
   (no caller anywhere), the hand-gesture pipeline (`jarvis/gesture/hand_*.py`), and the Data
   Analysis Service facade (`jarvis/data/analysis_service.py`).

CHANGELOG historical benchmark prose (e.g. the v4.2.0/R7 entry's RTF figures) may be superseded
by newer empirical documents (`docs/benchmark_results.md`); this checkpoint does not rewrite
historical `CHANGELOG.md` entries — that file is out of scope for documentation-only syncs.

**Merged since the earlier `e4bcd6d` baseline — all now on `main`, all closed, 0 open PRs:**
- PR #11 — Gesture/Data Reference-Hardening (corresponds to section `0-PRE` below)
- PR #12 — Agent Execution Hardening (corresponds to section `0-PRE2` below)
- PR #13 — Skill/Plugin Manifest & Telemetry Hardening (corresponds to section `0-PRE3` below)

(Sections `0A`–`0D` — Wake Word Phase 1, Sandbox CI Compatibility Fix, Central Safety-Layer
Hardening, and Biometrics Hardening — were merged earlier, via PR #8, #9, #10, and #14
respectively, and were already historical before the prior checkpoint was added.)

**Validation on the prior checkpoint's merge point (`5f9f6da`), preserved as historical record:**

Local:
```text
907 collected
907 passed
0 skipped
0 failed
```

GitHub Actions CI (run #88):
```text
907 collected
904 passed
3 skipped
0 failed
```
All 4 CI jobs passed. The 3-skipped/0-skipped difference between CI and local is a
CI-environment-specific characteristic (consistent with the same pattern noted for earlier
merges in the sections below) and is not a discrepancy requiring investigation here.

**Historical note on `feat/ai-routing-hardening`:** this branch name was previously used for
deferred Phase 3 (AI-routing) work. It is **not** part of current shared `main`, and no remote
branch by this name is treated as active project state by this checkpoint. Any surviving branch
with this name on an individual developer's local machine is **machine-local state, not shared
repository truth** — `docs/PROJECT_STATE.md` records shared project state, not any one
developer's local Git checkout. Do not describe a local branch's presence or absence on any
particular machine as part of current `main`/shared state either way. If a branch by this name
is ever resumed, it must be audited fresh against whatever `main` looks like at that time, the
same as every sprint below did against `e4bcd6d`.

---

## 0-PRE. Gesture/Data Reference-Integration Sprint (in progress, uncommitted)

Snapshot: 2026-08-31. Branch `feat/gesture-data-reference-hardening`, based on `main` at `e4bcd6d015dec2796e0f50e88b5c9f69b58bb1f7`. Time-boxed (~3 hours). Local working-tree change, **not committed, not pushed, no PR opened**.

### Scope and constraints

- Explicit NO-TOUCH list honored, verified untouched: `jarvis/llm/router.py`, `jarvis/core/app.py`, `jarvis/comms/mobile_bridge.py`, `jarvis/proactive/**`, `jarvis/hardware/**`, `jarvis/stt/**`, `jarvis/audio/**`, `jarvis/automation/**`, `jarvis/security/scanner.py`, `jarvis/vision/biometrics.py`, `installer/**`, `scripts/build_installer.py`. No hard dependency forced touching any of these — both features were buildable as fully isolated additions.
- No wiring into `ActionDispatcher`, `app.py`, planner, or router this sprint — both new subsystems only emit structured results/callbacks.
- Pre-existing baseline CI failures (mobile_bridge, proactive health-monitor) were **not** chased or modified, per instruction.

### Upstream references consulted (architecture/API only — no source/models/datasets copied)

- `kinivi/hand-gesture-recognition-mediapipe` — informed the general pipeline shape (21-point MediaPipe landmarks → normalization → static-shape classification + point-history for dynamic gestures). The actual static-shape classifier implemented is a from-scratch, transparent geometric heuristic (wrist-relative digit-extension distance ratios) — not a port of that repo's trained keypoint/point-history classifier models or code.
- `Sinaptik-AI/pandas-ai` — informed only the layering idea (data loading → dataframe/data model → analysis/agent layer → execution/sandbox boundary). No PandasAI source, enterprise code, or models were imported; PandasAI is not a runtime dependency anywhere in `pyproject.toml`.

### 1. Hand-gesture pipeline (new, additive)

Files added:
- [jarvis/gesture/hand_models.py](../jarvis/gesture/hand_models.py) — `HandLandmarkIndex` (IntEnum, MediaPipe 21-point topology), `HandLandmarkPoint`/`HandLandmarks` (frozen dataclasses, `HandLandmarks` enforces exactly 21 points), `HandGestureType` (`OPEN_PALM`/`FIST`/`SWIPE_LEFT`/`SWIPE_RIGHT`/`UNKNOWN`), `HandGestureBackend`, `HandTrackerState`, `HandGestureResult`.
- [jarvis/gesture/hand_preprocess.py](../jarvis/gesture/hand_preprocess.py) — pure deterministic functions, zero optional-dependency imports: `normalize_landmarks()`, `landmarks_to_feature_vector()`, `classify_static_shape()`, `classify_dynamic_gesture()`.
- [jarvis/gesture/hand_tracker.py](../jarvis/gesture/hand_tracker.py) — `HandGestureTracker` (thread-safe lifecycle, confidence threshold, static-shape debounce/stabilization, post-emission cooldown), lazy `cv2`/`mediapipe` imports (`CV2_AVAILABLE`/`MEDIAPIPE_AVAILABLE`), `get_available_backend()`, optional real-camera `start()`/`_capture_loop()`/`stop()`/`shutdown()` (not exercised against real hardware this session).
- [jarvis/gesture/__init__.py](../jarvis/gesture/__init__.py) — additive exports only; existing acoustic exports (`GestureDetector`, `GestureType`, `GestureResult`, etc.) unchanged, [jarvis/gesture/detector.py](../jarvis/gesture/detector.py) and [jarvis/gesture/models.py](../jarvis/gesture/models.py) **not modified**.
- [tests/unit/test_hand_gesture.py](../tests/unit/test_hand_gesture.py) — new, 24 tests, fully deterministic (synthetic landmark fixtures, no MediaPipe/OpenCV/webcam).

`pyproject.toml`: new optional extra `gestures = ["opencv-python>=4.8,<5", "mediapipe>=0.10,<1"]`, deliberately **not** added to the `all` aggregate (mediapipe's Python 3.13 wheel availability was not independently verified this session — see CLAUDE.md §8.5). Added `cv2`/`mediapipe.*` to `[[tool.mypy.overrides]]`.

### 2. Data Analysis Service facade (new, additive)

Files added:
- [jarvis/data/analysis_service.py](../jarvis/data/analysis_service.py) — `DataAnalysisService` facade over the existing, unmodified `DataAnalyticsEngine`/`MonteCarloEngine` in [jarvis/data/stats.py](../jarvis/data/stats.py). Structured models: `AnalysisOperation`, `DataAnalysisRequest`, `DataAnalysisResult`, `ChartSpec`/`ChartSeries`/`ChartRenderResult`. Operations: `describe`, `correlation`, `detect_anomalies`, `trend`, `monte_carlo`, `build_chart_spec`/`render_chart`, and a single `execute()` structured dispatcher. Bounded file loading via `_check_file_bounds()` (`max_file_size_bytes`, default 50MB) raising `FileTooLargeError`; unsupported file extensions raise `UnsupportedOperationError`.
- [jarvis/data/__init__.py](../jarvis/data/__init__.py) — additive exports only; existing `DataAnalyticsEngine`/`MonteCarloEngine`/document-exporter exports unchanged.
- [tests/unit/test_data_analysis_service.py](../tests/unit/test_data_analysis_service.py) — new, 22 tests: CSV fixture-based describe/correlation/anomaly/trend, seeded-deterministic Monte Carlo, file-size-bound rejection, unsupported extension, chart rendering both with and without matplotlib (via `monkeypatch`-simulated `ImportError`), `execute()` dispatch, and a source-scan assertion against `eval`/`exec`/`subprocess`/`os.system` appearing in the module.

`pyproject.toml`: new optional extra `charts = ["matplotlib>=3.7,<4"]`, **included** in the `all` aggregate (matplotlib has broad, low-risk wheel support including Python 3.13; the dev environment already had 3.11.1 installed and both the "matplotlib present" and "matplotlib absent" code paths in `render_chart()` were actually exercised). Added `matplotlib.*` to `[[tool.mypy.overrides]]`.

### Validation actually executed (this session, local)

```text
tests/unit/test_hand_gesture.py             — 24 passed
tests/unit/test_data_analysis_service.py    — 22 passed
tests/unit/test_gesture_detector.py         — 8 passed (acoustic detector regression check)

ruff check jarvis/gesture jarvis/data tests/unit/test_hand_gesture.py \
  tests/unit/test_data_analysis_service.py pyproject.toml   — All checks passed!
mypy jarvis/gesture jarvis/data                             — Success: no issues found in 11 source files
mypy jarvis (full)                                          — 29 pre-existing errors in 9 unrelated files
                                                                (night_shift.py, macro_recorder, auto_updater.py,
                                                                smart_home/discovery.py, mobile_bridge.py, tray.py,
                                                                gui_actor.py, cli.py — none touched this sprint);
                                                                one new hand_tracker.py error was found and fixed
                                                                (explicit HandGestureType/float annotations added
                                                                to resolve a mypy narrowing false-positive)
py_compile (all changed files)                               — exit 0
git diff --check                                             — exit 0

tests/unit/ full run (pre-review-pass) — 782 collected, 773 passed, 9 failed
```

9 failures are the **documented, pre-existing, unrelated baseline failures** in NO-TOUCH areas: 8 in `tests/unit/test_mobile_bridge.py` (`TestReceiveFile`/`TestTransferHistory`, `AttributeError: 'NoneType' object has no attribute 'exists'` inside `jarvis/comms/mobile_bridge.py`) and 1 in `tests/unit/test_proactive_engine.py::test_health_monitor_multiple_simultaneous_breaches`. 782 − 736 (pre-sprint baseline collected count) = 46, exactly matching the 24 + 22 new tests added — **zero regressions introduced by this sprint**.

**Post-merge correction (added when merging `main` into this branch)**: the "9 known pre-existing failures" figure above (and every other reference to it in this section) reflects the state of `main` at `e4bcd6d` — the exact base commit this sprint branched from, **before** a separate, independent branch (`fix/ci-baseline`) fixed both root causes and merged into `main`: `jarvis/comms/mobile_bridge.py`'s dangling `_TRANSFER_LOG: Path | None` (now resolved via a lazy `_get_transfer_log_path()` using `jarvis.core.paths.data_path()`), and `tests/unit/test_proactive_engine.py::test_health_monitor_multiple_simultaneous_breaches` (now asserts against the monitor's live threshold attributes instead of stale hardcoded values). This is a **historical record of what this sprint observed at the time it ran** — it is not being rewritten.

**Actual post-merge validation** (run this session, after resolving the `CHANGELOG.md`/`CLAUDE.md` merge conflicts from `main` into `feat/gesture-data-reference-hardening`):
```text
python -m pytest tests/unit/test_hand_gesture.py tests/unit/test_data_analysis_service.py \
  tests/unit/test_gesture_detector.py tests/unit/test_mobile_bridge.py \
  tests/unit/test_proactive_engine.py tests/unit/test_biometrics_hardening.py -q --timeout=120
0 failed (49+25+8+27+15+39 = 163 collected across these 6 files, all passed)

python -m pytest tests/unit/ -q --timeout=120 --tb=short
837 collected, 837 passed, 0 failed
```
837 = 736 (original `e4bcd6d` baseline) + 49 (biometrics hardening, PR #14) + 27 (`test_hand_gesture.py`) + 25 (`test_data_analysis_service.py`) = 736 + 49 + 52 = 837, exactly as predicted before running. The 9 previously-known failures are genuinely gone (fixed by `fix/ci-baseline` on `main`), not skipped or masked. **Zero regressions from the merge.**

### Pre-commit review pass (same session, before any commit) — 4 real bugs found and fixed

A dedicated correctness/lifecycle/resource-safety review of the diff (no new features) found and fixed 4 real, testable defects, all still inside the sprint's own new files — no NO-TOUCH file was touched:

1. **`jarvis/data/analysis_service.py::render_chart()` leaked the matplotlib figure on any rendering error.** `plt.close(fig)` only ran on the success path; an exception raised after `plt.subplots()` (e.g. a `ChartSpec` with mismatched series `x`/`y` lengths) returned `rendered=False` without ever closing the already-created figure — a real, repeatable resource leak across repeated failed renders. Fixed with a `try/finally` that always closes the figure once created, on every path.
2. **`jarvis/data/analysis_service.py::execute()` misreported chart-render failures as success.** For `AnalysisOperation.CHART` it always returned `DataAnalysisResult(success=True, ...)` regardless of `render_result.rendered` — a caller trusting the uniform `success` contract (the entire point of this facade) would see a failed/matplotlib-less render as successful. Fixed: `success=render_result.rendered`, `error=render_result.error`.
3. **`jarvis/gesture/hand_tracker.py::_capture_loop()` didn't recover from a worker exception.** If `cap.read()`/`hands.process()` raised, the thread logged and returned, but `self._state` stayed `RUNNING`, camera/MediaPipe resources were never released, and `self._capture_thread` was never cleared — so a later `start()` call saw `state == RUNNING` and no-op'd, leaving the tracker permanently, silently dead while still reporting itself as running. Fixed: the exception handler now releases resources via the existing `_release_backend_locked()`, clears `_capture_thread`, and drops state to `HandTrackerState.UNAVAILABLE` so a later `start()` genuinely restarts.
4. **`jarvis/gesture/hand_tracker.py::start()` didn't clear stale classification buffers on (re)start.** `_point_history`/`_recent_static`/`_last_emit_time` from before a `stop()` survived into the next `start()`, so a landmark from long before a restart could combine with the first post-restart frame into a spurious gesture. Fixed: `start()` now clears all three right before spinning up the capture thread.

All 4 fixes are covered by new, deterministic, mocked-backend regression tests (no real camera/MediaPipe/matplotlib-required-to-be-absent): `test_render_chart_error_path_does_not_leak_figure`, `test_execute_chart_success_reflects_actual_render_outcome`, `test_execute_chart_failure_is_not_reported_as_success`, `test_capture_loop_exception_releases_resources_and_updates_state`, `test_start_after_worker_exception_actually_restarts` (a real background-thread crash → self-heal → real restart end-to-end check), `test_start_clears_stale_classification_state_from_before_restart`. These closed a real test-coverage gap — the original 46 tests never exercised `execute()` with `AnalysisOperation.CHART`, nor any `HandGestureTracker` lifecycle path with a mocked (rather than absent) backend.

```text
tests/unit/test_hand_gesture.py             — 27 passed (24 + 3 new)
tests/unit/test_data_analysis_service.py    — 25 passed (22 + 3 new)
tests/unit/test_gesture_detector.py         — 8 passed (acoustic detector regression check, unaffected)

ruff check jarvis/gesture jarvis/data tests/unit/test_hand_gesture.py \
  tests/unit/test_data_analysis_service.py pyproject.toml   — All checks passed!
mypy jarvis/gesture jarvis/data                             — Success: no issues found in 11 source files
py_compile (all changed files)                               — exit 0
git diff --check                                             — exit 0

tests/unit/ full run (post-review-pass) — 788 collected, 779 passed, 9 failed (same 9 pre-existing baseline failures; zero new regressions from the fixes)
```

Non-blocking findings noted during the review but **not** fixed (kept out of scope — none is a correctness/safety defect):
- `_check_file_bounds()` doesn't call `is_file()`, so a directory path falls through to a slightly-confusing `UnsupportedOperationError: Unsupported file type: ''` rather than a clearer "not a file" message.
- `render_chart()`'s `except ImportError` around the matplotlib import doesn't also catch a (very unlikely) exception from `matplotlib.use()` itself, which would then propagate out despite the docstring's "never raises" claim.
- `matplotlib.use("Agg", force=True)` is called on every `render_chart()` call; harmless today since no other JARVIS code uses matplotlib, but would forcibly switch backends for any future in-process matplotlib user.
- Swipe direction (`SWIPE_LEFT`/`SWIPE_RIGHT`) is computed directly from raw image-space x, which assumes an un-mirrored camera frame; a typical "selfie-view" mirrored webcam feed would invert perceived direction. Documented as an x-increases-rightward assumption in the docstring, but the mirroring caveat itself isn't called out. Real-camera validation (already a known follow-up) would surface and settle this.

### Known limitations / confirmed follow-ups

- Hand-gesture pipeline is not wired into `ActionDispatcher`/`app.py`/planner/router — by design, out of scope this sprint.
- `HandGestureTracker.start()`/`_capture_loop()` (real webcam + MediaPipe) now has mocked-backend regression coverage for crash-recovery and restart-buffer-clearing, but is still **not validated against real hardware/a real MediaPipe install** this session.
- `DataAnalysisService` has no natural-language-to-operation mapping yet (explicitly deferred to a future Phase 3).
- The 9 pre-existing unrelated baseline failures (mobile_bridge, proactive health-monitor) remain unfixed **on this branch**, per explicit instruction not to chase them here — but see the post-merge correction note above: they were fixed independently on `main` by `fix/ci-baseline` and are already present once `main` is merged into this branch.
- The 4 non-blocking findings listed above remain open (deliberately not fixed this pass).
- Not committed, not pushed, no PR opened, no CI run for this branch yet.

### Recommended next task

Commit this sprint's additive changes (including the review-pass fixes) on `feat/gesture-data-reference-hardening`, push, and open a PR. Follow-ups explicitly out of scope here: real-webcam/MediaPipe validation for the hand-gesture tracker; a Phase 3 natural-language → `DataAnalysisRequest` mapping layer; the 4 non-blocking findings above (separate, unrelated tasks). ~~Independently fixing the pre-existing mobile_bridge/proactive baseline failures~~ — **already done**, on `main` via the separate `fix/ci-baseline` branch, prior to merging `main` into this branch.

---

## 0-PRE2. Agent Execution Hardening — OpenInterpreter Reference Sprint (in progress, uncommitted)

Snapshot: 2026-08-31. Branch `feat/agent-execution-hardening`, based on `main` at `e4bcd6d015dec2796e0f50e88b5c9f69b58bb1f7`. Local working-tree change, **not committed, not pushed, no PR opened, no CI run**. Primary target: `jarvis/agent/**`.

### Scope and constraints

- NO-TOUCH list honored, verified untouched: `jarvis/llm/router.py`, `jarvis/core/app.py`, `jarvis/comms/mobile_bridge.py`, `jarvis/proactive/**`, `jarvis/hardware/**`, `jarvis/stt/**`, `jarvis/audio/**`, `jarvis/automation/**`, `jarvis/security/scanner.py`, `jarvis/vision/biometrics.py`, `installer/**`, `scripts/build_installer.py`.
- `ReActAgent` remains completely unwired — grepped the whole `jarvis/` tree before and after this sprint: it is imported nowhere outside `jarvis/agent/**` and its own tests. Zero production blast radius today; the findings below matter for whenever it *is* wired in.
- One deliberate, user-approved exception to "do not touch `jarvis/sandbox/**`": a proven, reproducible pipe-deadlock defect in `jarvis/sandbox/security.py` was found and fixed — see below. This was not a unilateral decision; the user was asked explicitly before any sandbox file was touched.

### Upstream reference consulted (architecture only — no source copied, not vendored, not a dependency)

- **OpenInterpreter** — current project is `openinterpreter/openinterpreter`, substantially rewritten from the historical `OpenInterpreter/open-interpreter` repo named in older planning docs. Only architectural concepts were used: explicit agent-harness/execution boundary, sandboxed code execution, permission/approval boundaries, bounded execution, structured execution results, portable/isolated tools. No OpenInterpreter code was read into any JARVIS file; `pyproject.toml` was not touched (no new dependency of any kind this sprint).

### Confirmed findings (audited before any edit, exactly as suspected)

1. **`jarvis/agent/graph.py::ReActAgent._tool_run_python` called Python's builtin `exec()` directly**, in-process, with only `ast.parse()` for a syntax check (not a safety check) — full access to the JARVIS process's own globals/environment, no timeout, no resource bound, no isolation. JARVIS already had `jarvis.sandbox.interpreter.CodeInterpreterSandbox.execute_python()` (AST safety validation, isolated scratch dir, OS Restricted Token isolation, Windows Job Object, timeout, structured `SandboxResult`) — `_tool_run_python` used none of it.
2. **Every built-in agent tool (`write_file`, `read_file`, `browser_open`, `screenshot`, `send_telegram`, `list_dir`, `git_status`, and the old `run_python`) bypasses `ActionDispatcher.dispatch_action()`/`SafetyGateInterceptor` entirely** — `ReActAgent._act()` calls `tool.fn(**args)` directly. No RBAC, no risk classification, no safety-gate anywhere in the agent's tool-calling path. `git_status` uses `subprocess.run(["git", "status", "--short"], ...)` with a fixed argv (no injection risk from user input) but still bypasses the dispatcher like everything else.

### Fix 1 (required): route Python execution through the existing sandbox

- `_tool_run_python` now calls `CodeInterpreterSandbox.execute_python()` instead of `exec()`. `jarvis/sandbox/interpreter.py` itself was **not modified** for this fix.
- User code is wrapped with `try: print(result)\nexcept NameError: pass` to preserve the old "top-level `result` becomes tool output" convention, without using any AST-forbidden introspection call (`locals()`/`globals()`/`vars()` are all rejected by the sandbox's validator — using them would break the epilogue's own validation).
- `ReActAgent.__init__` gained an optional `sandbox: CodeInterpreterSandbox | None = None` param (backward compatible); `_get_sandbox()` lazily constructs a default (`cleanup_on_exit=True`) only when `run_python` is actually first called.
- `_tool_run_python(code, timeout_seconds=None, **kw)` gained an optional `timeout_seconds`, always clamped to `MAX_PYTHON_EXEC_TIMEOUT_SECONDS = 30.0`.

### Unplanned, serious finding: pipe deadlock in `jarvis/sandbox/security.py` (found, confirmed, fixed with explicit user approval)

While integration-testing Fix 1 against realistic output sizes (not a hypothetical check), `CodeInterpreterSandbox.execute_python()` was found to **hang for the entire timeout** on any script producing more than **exactly 4096 bytes** of combined stdout+stderr — bisected precisely (4000 bytes: instant; 4096 bytes: hangs the full timeout, verified up to 25s). Root cause, confirmed by reading `spawn_low_integrity_process()`: it called `WaitForSingleObject()` to wait for the *entire* child process to exit **before** ever calling `ReadFile` on the output pipe (the old Step 10 read loop ran only after the wait). Windows' default anonymous pipe buffer is ~4096 bytes; once the child's unread output exceeded that, its `write()`/`print()` blocked forever (pipe full, nobody draining) while the parent was itself blocked in `WaitForSingleObject` — a textbook pipe deadlock, broken only by the caller's own timeout, which then **misreported the run as "timed out" instead of "succeeded with output."**

This is not an edge case: any moderately verbose script (printing a JSON blob, a file listing, etc.) — exactly the kind of thing agent-generated Python commonly does — would trigger it. It also directly undermined this sprint's own required outcome ("huge stdout is bounded before entering agent history") since a real large-output run couldn't even complete to be bounded.

Per the task's own instruction ("do NOT modify `jarvis/sandbox/**` unless a proven defect... makes the agent integration impossible"), this was **not fixed unilaterally** — the user was asked explicitly (fix now vs. document-only) and chose to fix it.

**Fix applied** (`jarvis/sandbox/security.py::spawn_low_integrity_process()`, `import threading` added):
- A daemon `threading.Thread` starts draining `h_read` via a `ReadFile` loop immediately after `CreateProcessAsUserW` succeeds (while the child is still `CREATE_SUSPENDED`, before `ResumeThread`) — the pipe is never left undrained while the child could be writing.
- `WaitForSingleObject`/timeout handling/`GetExitCodeProcess` are **completely unchanged** — only *when* the pipe is read changed, not any Restricted Token/Job Object/`retry_safe`/AST-validation semantics.
- After the child exits (normally, or via `TerminateProcess` on timeout), `reader_thread.join(timeout=5.0)` bounds the wait for drainage; whatever was captured in `output_chunks` by then is used regardless.
- `_cleanup()` (the shared `finally` on every exit path, including early `RestrictedProcessBootstrapError` raises) also joins the reader thread (bounded 2.0s) before closing `h_read`, avoiding a `CloseHandle`-vs-pending-`ReadFile` race across threads.
- Verified: 100–50000 byte outputs all now complete in ~0.13–0.14s, `success=True`, correct data — versus hanging the full timeout before the fix for anything ≥4096 bytes.
- New regression test: `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_large_stdout_does_not_deadlock` (20000 bytes, 5.0s timeout, asserts success).
- All existing sandbox tests re-run clean after the fix: `test_skill_synthesis.py` (21), `test_adversarial_r1_r2_r5_stress.py`, `test_hud_telemetry_and_memory.py`, `test_sandbox_compat_fallback.py` (40), and `tests/integration/test_sandbox_os_boundaries.py` (15) — all pass, zero regressions.
- **Separate, non-security cosmetic defect found but deliberately NOT fixed**: `strip_sandbox_ready_sentinel()` only strips an LF-terminated sentinel line; a CRLF-terminated child stdout (common on Windows) leaks the raw `\x02JARVIS_SANDBOX_READY_v1\x03` marker bytes through. Not a security issue and doesn't meet the "makes integration impossible" bar, so left unfixed at the source; `jarvis/agent/tool_runtime.py` does its own defensive, CRLF-tolerant cleanup on the consumer side instead.

### Follow-up pre-commit security review — 1 more real issue found and fixed, 1 test gap closed

A dedicated line-by-line security review of the diff (no new features) found the pipe-drain fix above had introduced its own resource-safety regression, and closed a test-coverage gap:

- **`_drain_pipe()` had no cap on retained memory.** The deadlock fix removed the *only* thing that previously bounded parent-process (JARVIS host) memory during pipe capture — the deadlock itself, which silently capped a runaway script to ~4KB before it blocked. Without an explicit cap, `while True: print(...)` could make the reader thread buffer unbounded data in the JARVIS process for the entire timeout window, long before `interpreter.py`'s post-hoc `_MAX_STDOUT_CAPTURE_BYTES` truncation ever ran. Fixed: `_drain_pipe()` now stops appending to `output_chunks` once `_PIPE_READER_MAX_CAPTURE_BYTES = 1024 * 1024` (1MB) is reached, while continuing to call `ReadFile` in a loop so the pipe — and the child — never blocks again; excess bytes are simply discarded. Independent constant from `interpreter.py`'s (avoids a circular import); keep the two conceptually in sync if either changes. New regression test: `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_runaway_output_does_not_grow_unbounded` (a genuinely unbounded print loop against a 1.5s timeout; asserts bounded wall-clock time and `len(stdout) < 2MB`).
- **Test gap closed**: no existing test exercised heavy or interleaved writes to `stderr` specifically through the real sandboxed subprocess. Added `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_mixed_stdout_stderr_heavy_output_does_not_deadlock`.
- **Correction (found via GitHub Actions CI #75)**: the test as originally written asserted heavy stderr content landed in `result.stdout`, on the assumption that stdout/stderr are always merged into one pipe (`hStdOutput == hStdError`). That merge is true only on the primary OS Restricted Token path. GitHub's runners currently hit the known `0xC0000142` Restricted Token bootstrap failure (see above) and fall back to the explicit-opt-in compatibility path, where `subprocess.Popen` captures stdout and stderr **separately** — so the assertion was backend-specific and failed there. Fixed by asserting only the semantic contract that holds across both paths: `result.success is True`, no timeout/deadlock, and both heavy payloads present somewhere in `result.stdout + result.stderr` combined.
- Re-validated after this fix: all sandbox/agent test files re-run clean (`test_skill_synthesis.py` now 23 tests, `test_react_agent.py` 38, `test_agent_tool_runtime.py` 25, plus `test_adversarial_r1_r2_r5_stress.py`, `test_hud_telemetry_and_memory.py`, `test_sandbox_compat_fallback.py`, `test_react_planner.py`, `test_browser_agent.py`, `tests/integration/test_sandbox_os_boundaries.py`); `ruff`/`mypy`/`py_compile`/`git diff --check` all clean; full `tests/unit/` — 781 collected, 772 passed, same 9 pre-existing unrelated failures, zero new regressions.
- No other finding from this review pass rose to blocking severity. Confirmed unchanged: Restricted Token creation, integrity level, `CreateProcessAsUserW` args, Job Object assignment/kill-on-close, environment scrubbing, AST validation, compatibility fallback policy, security preamble — the entire diff to `security.py` across both passes is confined to *when*/*how much* of the pipe is read, never any isolation/authorization semantic. `_tool_write_file`/`_tool_read_file`/etc. remain byte-for-byte unchanged — no second/ad-hoc safety mechanism was introduced anywhere.

### Fix 2: structured tool-execution contract (new module, `jarvis/sandbox/**` untouched)

- [jarvis/agent/tool_runtime.py](../jarvis/agent/tool_runtime.py) (new) — `ToolExecutionResult(success, output, error, metadata)`; `truncate_text()` (deterministic bound, `DEFAULT_MAX_OBSERVATION_CHARS=4000`, deliberately much smaller than the sandbox's own 1MB stdout cap which protects its pipe, not an LLM context budget); `normalize_tool_output()`; `sandbox_result_to_tool_result()` (the one place a `SandboxResult` becomes agent-facing, including the CRLF-sentinel defensive cleanup above); `format_observation()`.
- `ReActAgent._act()` now routes **every** tool call through `_execute_tool()` + `format_observation()`, not just `run_python`: unknown tool names and non-dict (including `None`) args fail deterministically without raising; any tool exception is caught and converted, never escaping to crash the ReAct loop; every tool's output is bounded before it can reach `ThoughtStep.tool_result`/agent history.

### Audited and deliberately NOT fixed (documented, not patched with a second safety system)

All built-in agent tools — `write_file`, `read_file`, `browser_open`, `screenshot`, `send_telegram`, `list_dir`, `git_status` — still call straight into `tool.fn(**args)`, completely bypassing `ActionDispatcher`/`SafetyGateInterceptor` (CLAUDE.md §8.3). `write_file` can overwrite any path the process can write to (no allowlist); `browser_open` can navigate anywhere under LLM/agent control. Wiring the full tool set through `ActionDispatcher` is a materially larger integration than this sprint's scope; per explicit instruction, no ad-hoc parallel safety mechanism was invented to patch around it — this is left for a dedicated future integration task. Current production risk is zero since `ReActAgent` has no callers yet.

### Files changed

- [jarvis/agent/graph.py](../jarvis/agent/graph.py) — `_tool_run_python()` rewritten to use the sandbox; `_act()`/new `_execute_tool()` use the structured tool-execution contract; `ReActAgent.__init__`/`_get_sandbox()` gained the optional `sandbox` param and lazy construction.
- [jarvis/agent/tool_runtime.py](../jarvis/agent/tool_runtime.py) — new file (see Fix 2).
- [jarvis/sandbox/security.py](../jarvis/sandbox/security.py) — `spawn_low_integrity_process()` pipe-deadlock fix (see above); `import threading` added. No other function in this file touched.
- [tests/unit/test_react_agent.py](../tests/unit/test_react_agent.py) — 17 new tests added; all 21 pre-existing tests unmodified and still passing.
- [tests/unit/test_agent_tool_runtime.py](../tests/unit/test_agent_tool_runtime.py) — new file, 25 tests.
- [tests/unit/test_skill_synthesis.py](../tests/unit/test_skill_synthesis.py) — 3 new regression tests added (pipe-deadlock fix, memory-bound fix, mixed stdout/stderr coverage — see follow-up review section below); all pre-existing tests unmodified.

No other tracked file is part of this change set.

### Validation actually executed (this session, local)

```text
tests/unit/test_react_agent.py             — 38 passed (21 pre-existing + 17 new)
tests/unit/test_agent_tool_runtime.py      — 25 passed (new file)
tests/unit/test_skill_synthesis.py         — 21 passed (20 pre-existing + 1 new)
tests/unit/test_adversarial_r1_r2_r5_stress.py, test_hud_telemetry_and_memory.py,
  test_sandbox_compat_fallback.py, test_react_planner.py, test_browser_agent.py — all pass
tests/integration/test_sandbox_os_boundaries.py — all 15 pass (post pipe-fix regression check)

ruff check jarvis/agent tests/unit/test_react_agent.py tests/unit/test_agent_tool_runtime.py \
  tests/unit/test_skill_synthesis.py jarvis/sandbox/security.py           — All checks passed!
mypy jarvis/agent/graph.py jarvis/agent/tool_runtime.py jarvis/agent/__init__.py \
  jarvis/sandbox/security.py --follow-imports=silent                     — Success: no issues found in 4 source files
py_compile (all changed files)                                            — exit 0
git diff --check                                                         — exit 0

tests/unit/ full run — 779 collected, 770 passed, 9 failed
```

9 failures are the **documented, pre-existing, unrelated baseline failures** in NO-TOUCH areas (identical set seen on this same `e4bcd6d` baseline in an earlier, separate reference-integration sprint on a different branch): 8 in `tests/unit/test_mobile_bridge.py` and 1 in `tests/unit/test_proactive_engine.py::test_health_monitor_multiple_simultaneous_breaches`. 779 − 736 (confirmed `e4bcd6d` baseline collected count) = 43, exactly matching 17 + 25 + 1 new tests. **Zero regressions introduced by this sprint.**

### Known limitations / confirmed follow-ups

- All built-in agent tools bypass `ActionDispatcher`/`SafetyGateInterceptor` (see "Audited and deliberately NOT fixed" above) — recommended as a dedicated future integration, not a quick patch.
- `ReActAgent` is still not wired into `app.py`/dispatcher/router/planner anywhere — out of scope, no Phase 3 LLM routing started, per explicit instruction.
- The CRLF-vs-LF sentinel-stripping cosmetic defect in `strip_sandbox_ready_sentinel()` remains unfixed at the source (see above); only defensively worked around on the agent-consumer side.
- CI has not been run for this branch; not committed, not pushed, no PR opened.
- The 9 pre-existing unrelated baseline failures (mobile_bridge, proactive health-monitor) remain unfixed, per explicit instruction not to chase them.

**Post-main-sync correction (added when merging `main` into `feat/agent-execution-hardening`)**: the "779 collected, 770 passed, 9 failed" figure above (and "781 collected, 772 passed" after the follow-up security review) reflects `main` at `e4bcd6d` — the exact base this sprint branched from — **before** `main` merged PR #15 (`fix/ci-baseline`, which fixed both root causes of those 9 failures), PR #14 (Biometrics Hardening, +49 tests), and PR #11 (Gesture/Data Reference-Hardening, +52 tests). This is a **historical record of what this sprint observed at the time it ran** — it is not being rewritten. GitHub Actions CI history for reference: CI run #75 surfaced the stdout/stderr-separate-pipes backend difference on the compatibility-fallback path (see the pipe-deadlock fix section above); CI run #76 confirmed the corrected assertion passed. PR #11's own GitHub Actions CI (post Biometrics+Gesture/Data merge, pre-Agent) reported 837 collected, 834 passed, 3 skipped, 0 failed — the 3 skips are CI-environment-specific and were not reproduced locally (0 skipped locally, see below).

**Actual post-main-sync validation** (run this session, after resolving the `CHANGELOG.md`/`CLAUDE.md`/`docs/PROJECT_STATE.md` merge conflicts from `main` into `feat/agent-execution-hardening`):
```text
python -m pytest tests/unit/test_react_agent.py tests/unit/test_agent_tool_runtime.py \
  tests/unit/test_skill_synthesis.py tests/unit/test_sandbox_compat_fallback.py \
  tests/unit/test_biometrics_hardening.py tests/unit/test_hand_gesture.py \
  tests/unit/test_data_analysis_service.py tests/unit/test_mobile_bridge.py \
  tests/unit/test_proactive_engine.py -q --timeout=120
0 failed (25+49+25+27+15+39+38+40+23 = 281 collected across these 9 files, all passed)

python -m pytest tests/unit/ -q --timeout=120 --tb=short
882 collected, 882 passed, 0 skipped, 0 failed
```
882 = 837 (merged-main baseline, already confirmed locally after the Biometrics + Gesture/Data merge) + 45 new tests this sprint adds (17 `test_react_agent.py` + 25 `test_agent_tool_runtime.py` [new file] + 3 `test_skill_synthesis.py` regression tests) = 837 + 45 = 882, exactly as predicted before running. The 9 previously-known failures are genuinely gone (fixed by `fix/ci-baseline` on `main`), not skipped or masked — confirmed by an actual local run, not assumed. **Zero regressions from the merge.**

### Recommended next task

Commit this sprint's changes on `feat/agent-execution-hardening`, push, open a PR — the sandbox pipe-deadlock fix in particular should get real CI/Windows-runner validation given how central `jarvis/sandbox/security.py` is (PR #9). Follow-ups explicitly out of scope here: wiring `ReActAgent`'s built-in tools through `ActionDispatcher`/`SafetyGateInterceptor`; fixing `strip_sandbox_ready_sentinel()`'s CRLF handling at the source; any Phase 3 LLM-routing/agent-wiring work; independently fixing the pre-existing mobile_bridge/proactive baseline failures.

---

## 0-PRE3. Skill/Plugin Manifest & Telemetry Hardening — Leon 2.0 Reference Sprint (in progress, uncommitted)

Snapshot: 2026-08-31. Branch `feat/skill-plugin-hardening`, based on `main` at `e4bcd6d015dec2796e0f50e88b5c9f69b58bb1f7`. Local working-tree change, **not committed, not pushed, no PR opened, no CI run**. Primary target: `jarvis/skills/models.py`, `jarvis/skills/registry.py`.

### Scope and constraints

- NO-TOUCH list honored, verified untouched: `jarvis/llm/router.py`, `jarvis/core/app.py`, `jarvis/agent/**`, `jarvis/sandbox/**`, `jarvis/comms/**`, `jarvis/proactive/**`, `jarvis/hardware/**`, `jarvis/stt/**`, `jarvis/audio/**`, `jarvis/automation/**`, `jarvis/security/**`, `jarvis/vision/**`, `installer/**`, `scripts/build_installer.py`.
- Also untouched (no hard dependency required it): `jarvis/skills/synthesizer.py`, every individual skill implementation directory, and every existing `jarvis/skills/*/metadata.json` file. The other contributor's recent individual-skill and metadata changes are preserved exactly.
- No second safety gate invented; `ActionDispatcher` itself not modified, only consumed via its existing public API.

### Upstream reference consulted (architecture only — no source copied, not vendored, not a dependency)

- **leon-ai/leon**, 2.0 Developer Preview on `develop` (not older Leon docs/tutorials). Concepts used: the Skills → Actions → Tools → Functions capability hierarchy, separation of static capability definition from runtime execution state, deterministic native execution, tool boundaries, discoverability/registry design, validate-before-load, explicit capability metadata, separation of static definitions from runtime context/telemetry. No Leon TypeScript source was read into any JARVIS file; this is a partial, selective adaptation of concepts, not a reimplementation of Leon's architecture; `pyproject.toml` was not touched (no new dependency).

### Confirmed findings (audited before any edit, exactly as suspected)

1. **`SkillMetadata.to_dict()`/`.from_dict()` both silently dropped `category` and `author`** — confirmed by reading the source (neither key appears in either method) and by inspecting every packaged `metadata.json`: all 9 "jarvis_builtin_system"-family files (app_launcher, briefing, calculator, clipboard, file_manager, git_assistant, note_taker, pomodoro, system_control) already lack these keys, proving the bug has been live since those files were first written. A separate, newer "JARVIS Core Team"-family of 8 skills (auto_updater, browser_control, macro_recorder, night_planner, rag_search, screen_context, skill_synthesizer, smart_home_discovery, sound_board — the other contributor's recent work) uses an entirely different manifest shape (`display_name`/`author`/`actions`, no telemetry fields); `from_dict()` was silently discarding their real `"author": "JARVIS Core Team"` value in favor of the dataclass default.
2. **`invoke_skill()` called `_persist_skill_metadata()` after every invocation**, rewriting the entire packaged `<skill>/metadata.json` with fresh runtime counters. Confirmed as the exact root cause of `tests/unit/` mutating tracked metadata files: `tests/unit/test_builtin_skills.py`'s fixture constructs `SkillRegistry(skills_dir=Path("jarvis/skills").resolve())` and every test method calls `invoke_skill()` on a real built-in skill. **Not just a test artifact** — `jarvis/core/app.py:373` (`skills_dir` defaults to the string `"jarvis/skills"`, resolving to the packaged tree unless overridden by config) and `jarvis/comms/discord.py`/`jarvis/comms/zalo.py` (`SkillRegistry()` with no arguments, same default) mean real end-user JARVIS usage — Telegram/Discord/voice/CLI skill invocation — has been rewriting its own installed package's metadata.json files on every real invocation too.
3. **Direct `invoke_skill()` is intentional, coexisting design, confirmed by tracing every production caller — not a bypass to "fix."** Callers: `jarvis/core/app.py:1302`, 5 call sites in `jarvis/comms/discord.py`, `jarvis/comms/zalo.py`, `jarvis/ui/dashboard.py:714`, and `SkillRegistry._create_dispatcher_handler()` itself (the `ActionDispatcher` adapter calls `invoke_skill()` internally). All are trusted, internal JARVIS-owned callers invoking a known skill by name — none is LLM-routed or untrusted-input-driven skill *selection*. Both the direct path and the `ActionDispatcher`-routed path (`skill_<name>` actions) coexist by design and both remain fully functional.
4. Malformed-JSON-per-skill discovery was already fail-closed **in the sense that the skill still loads with fallback metadata rather than being skipped or crashing discovery** (caught, logged, falls back to a directory/file-derived default `SkillMetadata`) before this sprint — confirmed by reading the code and by a new regression test, not a new behavior. Precisely: neither syntactically-invalid JSON nor a field-level type error in otherwise-valid JSON (see below) ever causes a skill to be rejected/skipped from discovery — both degrade to safe defaults for that field/manifest. What was **not** validated before: a syntactically-valid manifest with wrong field types (e.g. `"tags": "not-a-list"`), which could silently produce a type-inconsistent `SkillMetadata` that crashes later in unrelated code (e.g. `", ".join(tags)` in `synthesizer.py`'s markdown generation).
5. **No skill-identifier safety validation existed anywhere.** `register_skill()`'s `skill_dir = self.skills_dir / name` and the old `_persist_skill_metadata()`'s `f"{name}.json"` both trusted `metadata.name` (untrusted content from a JSON file the skill's own directory owns) with zero sanitization — a manifest declaring `"name": "../../evil"` would have caused a path escape in either call site.
6. Discovery order was **not** deterministic (`Path.iterdir()`/`glob()` order is filesystem-dependent), and two different skill directories declaring the same `metadata.name` (independent of their own directory names) would silently overwrite each other depending on that unordered iteration.

### A. Manifest/telemetry separation (new module, `jarvis/skills/**` outside the two target files untouched except new files)

- [jarvis/skills/telemetry.py](../jarvis/skills/telemetry.py) (new) — `SkillTelemetryStore`: thread-safe (`threading.Lock`), atomic writes (temp file + `os.replace()`), corruption-tolerant (`load_all()`/`get()` never raise, log and return empty/None on a corrupt file), located via `jarvis.core.paths.data_path()` (existing, **unmodified**) by default. `default_telemetry_path_for(skills_dir)` scopes the default path by a SHA-256 hash of the resolved `skills_dir` — the real packaged tree always resolves to the same persistent file across restarts; every test's fresh temp directory gets an automatically unique, never-colliding file. `record_invocation(skill_name, success, latency_ms, seed=None)` — `seed` bootstraps a skill's counters from its current in-memory values the first time the store has no entry for it, so migrating onto the new store is numerically continuous (never a visible reset of historical counts).
- [jarvis/skills/registry.py](../jarvis/skills/registry.py) — `SkillRegistry.__init__` gained an optional `telemetry_store: SkillTelemetryStore | None = None` param (backward compatible; no existing caller needed to change). `invoke_skill()` no longer calls `_persist_skill_metadata()` (removed entirely — nothing else called it); it now calls `self.telemetry.record_invocation(...)` after computing a `seed` from the skill's current in-memory counters. In-memory `SkillMetadata.record_invocation()` (and thus `get_metrics()`/`success_rate`/`avg_latency_ms`) is unchanged — only where telemetry is durably persisted changed. New `_hydrate_telemetry()` overlays the store's counters onto freshly-parsed static metadata at discovery time when the store has an entry; if not, the metadata's own (possibly legacy) values are left untouched.

### B. Metadata round-trip fidelity fix

- [jarvis/skills/models.py](../jarvis/skills/models.py) — `to_dict()` now emits `category`/`author`. `from_dict()` rewritten around deterministic coercion helpers (see below): missing fields fall back to dataclass defaults (backward compatible with old manifests); fields present with the **wrong type** also fall back to defaults rather than propagating onto a typed attribute (fixes finding #4 above) — a single malformed field can never crash discovery.

### C. Deterministic manifest validation (new module, no JSON Schema framework, no new dependency)

- [jarvis/skills/validation.py](../jarvis/skills/validation.py) (new) — `is_safe_skill_identifier()` (rejects path separators, `..`, null bytes, empty/overlong strings; used to override an unsafe declared `metadata.name` with the filesystem-derived safe name at discovery time, and to make `register_skill()` refuse an unsafe name before constructing any path from it); `is_safe_entrypoint_identifier()` (gates the `getattr(module, entrypoint_function)` lookup in `_import_skill_module()`); `coerce_str`/`coerce_dict`/`coerce_optional_dict`/`coerce_str_list`/`coerce_float`/`coerce_int` (plain deterministic type coercion with safe fallback defaults, used throughout `SkillMetadata.from_dict()`).

### D. Discovery determinism

- `discover_skills()` now sorts both the subdirectory scan and the standalone-`.py`-file scan by name before processing. Duplicate `metadata.name` collisions (independent of directory name) resolve deterministically: the first-processed (sorted order) skill wins, later duplicates are skipped with a logged warning — never a silent overwrite. Verified for both directory-vs-directory and directory-vs-standalone-file collisions. Malformed-JSON-per-skill behavior confirmed unchanged (was already correct — see finding #4's precise wording) and now covered by a regression test. **Not addressed, pre-existing, out of scope**: a skill whose directory is deleted from disk between two `discover_skills()` calls is never removed from `self._skills` — do not describe discovery as "fully reconciled," only its ordering/duplicate-resolution are guaranteed.

### Follow-up pre-commit review — 4 real issues found and fixed, 6 tests added

A dedicated line-by-line review of the diff (no new features) found and fixed the following, all still inside this sprint's own files:

1. **A wrong-TYPED `name` (not just an unsafe string) could silently collide two unrelated skills under one shared, incorrect identity.** `SkillMetadata.from_dict()` coerced a non-string `name` (e.g. `"name": 12345`) to the fixed placeholder `"unnamed_skill"` — a string that itself *passes* `is_safe_skill_identifier()`, so the post-construction `_enforce_safe_skill_name()` override never fired. Two different skills with equally wrong-typed names would both resolve to the identical `"unnamed_skill"` key. Fixed with a new `SkillRegistry._sanitize_declared_name()` that runs on the raw parsed dict **before** `from_dict()` ever sees it, substituting the filesystem-derived safe name whenever the declared `"name"` is missing, wrong-typed, or an unsafe string — an invalid name now always resolves to *this skill's own* correct identity, never a generic shared placeholder. Regression tests: one skill with a wrong-typed name resolves to its own directory name; two independently-wrong-typed skills resolve to two distinct names, never colliding.
2. **Manifest/telemetry separation was incomplete at the `register_skill()` write site.** `SkillMetadata.to_dict()` (unchanged, still includes all 6 telemetry fields, used by `SkillDefinition.to_dict()`/dashboard introspection) was also being used to write brand-new packaged `metadata.json` files in `register_skill(save_to_disk=True)` — baking in telemetry fields (typically zero, but not conceptually separated) into every newly-created manifest. Fixed by adding `SkillMetadata.to_manifest_dict()` (excludes all 6 telemetry fields) and switching `register_skill()`'s disk write to use it. `jarvis/skills/synthesizer.py` (out of scope this sprint, not modified) still uses `to_dict()` for its own metadata.json write — this separation is therefore complete only at the one write site this sprint owns.
3. **In-memory concurrency race in `invoke_skill()`.** The seed-capture + `skill_def.metadata.record_invocation()` sequence (a non-atomic `+= 1` on a dataclass attribute shared across every caller invoking the same skill) ran with no lock — concurrent invocations of the same skill could lose updates to `get_metrics()`'s in-memory counters (a classic lost-update race), even though the separate on-disk `SkillTelemetryStore` was already correctly locked. This was a **pre-existing** race (the original `skill_def.metadata.record_invocation()` call was never locked either), newly exposed by this review's explicit concurrency verification, not introduced by this sprint's earlier changes. Fixed by wrapping the seed-capture and in-memory increment in the registry's existing `self._lock` (RLock); the on-disk telemetry write is intentionally left outside that lock since `SkillTelemetryStore` has its own independent lock and always increments from whatever is currently on disk (never from a stale `seed`, which only bootstraps a skill's very first store entry) — the two locks never need to be unified for correctness. Regression test: 40 concurrent `invoke_skill()` calls (half success / half failure) assert `invocation_count == success_count + failure_count` in both `get_metrics()` and the telemetry store.
4. **`_write_all_locked()` only caught `OSError` around `json.dumps()`.** Widened to also catch `TypeError`/`ValueError` — defense-in-depth for a hypothetical non-JSON-serializable value (not currently reachable, since all telemetry values are explicitly cast to `int`/`float`), so a JSON encode failure can never propagate out and interrupt a skill invocation.

Also closed two test-coverage gaps identified during the review (no code change, pre-existing behavior verified): directory-vs-standalone-file duplicate-name resolution, and `to_manifest_dict()`'s exact field exclusion in isolation.

### Files changed

- [jarvis/skills/models.py](../jarvis/skills/models.py) — `to_dict()`/`from_dict()` fixed (see B); `to_manifest_dict()` added (see follow-up review #2).
- [jarvis/skills/registry.py](../jarvis/skills/registry.py) — telemetry store integration, `_persist_skill_metadata()` removed, `_sanitize_declared_name()`/`_enforce_safe_skill_name()`/`_hydrate_telemetry()` added, `discover_skills()` made deterministic, `_import_skill_module()`/`register_skill()` gained identifier-safety checks (see A/C/D), `register_skill()` uses `to_manifest_dict()`, `invoke_skill()`'s telemetry update now lock-guarded (see follow-up review #1/#2/#3).
- [jarvis/skills/telemetry.py](../jarvis/skills/telemetry.py) — new file (see A); `_write_all_locked()` widened exception handling (see follow-up review #4).
- [jarvis/skills/validation.py](../jarvis/skills/validation.py) — new file (see C).
- [tests/unit/test_skill_registry_hardening.py](../tests/unit/test_skill_registry_hardening.py) — new file, 25 tests (19 original + 6 from the follow-up review).

No other tracked file is part of this change set. `jarvis/skills/synthesizer.py`, individual skill directories, and existing `metadata.json` files are unmodified.

### Validation actually executed (this session, local — includes the follow-up review pass)

```text
tests/unit/test_skill_registry_hardening.py    — 25 passed (new file)
tests/unit/test_plugin_sdk.py                  — 11 passed (unrelated jarvis/plugins/** SDK, unaffected)
tests/unit/test_plugins_m2.py                  — 3 passed (unrelated, unaffected)
tests/unit/test_builtin_skills.py              — 14 passed (skills_dir points at the real jarvis/skills/ tree)
tests/unit/test_skill_synthesis.py             — 20 passed
tests/unit/test_skill_synthesizer.py           — 13 passed
tests/unit/test_adversarial_r1_r2_r5_stress.py — 14 passed (includes a 20-thread concurrent invoke_skill() stress test)

ruff check jarvis/skills/models.py jarvis/skills/registry.py jarvis/skills/telemetry.py \
  jarvis/skills/validation.py tests/unit/test_skill_registry_hardening.py     — All checks passed!
mypy jarvis/skills/models.py jarvis/skills/registry.py jarvis/skills/telemetry.py \
  jarvis/skills/validation.py --follow-imports=silent                        — Success: no issues found in 4 source files
py_compile (all changed files)                                               — exit 0
git diff --check                                                             — exit 0

tests/unit/ full run (post-review) — 761 collected, 752 passed, 9 failed
```

9 failures are the **documented, pre-existing, unrelated baseline failures** in NO-TOUCH areas (identical set seen on this same `e4bcd6d` baseline across every earlier reference-integration sprint this cycle): 8 in `tests/unit/test_mobile_bridge.py` and 1 in `tests/unit/test_proactive_engine.py::test_health_monitor_multiple_simultaneous_breaches`. 761 − 736 (confirmed `e4bcd6d` baseline collected count) = 25, exactly matching the total new tests across both the original sprint and this review pass. **Zero regressions introduced.**

**Critical regression check for this sprint specifically**: `git status --short` and `git diff -- jarvis/skills/*/metadata.json` were run **before and after** the focused test run and the full `tests/unit/` run, both in the original implementation pass and again in this follow-up review pass (761 tests, including the new 40-thread concurrent-invocation test). Every check returned **empty** — no tracked `metadata.json` file was touched, including by tests that discover/invoke skills directly against the real `jarvis/skills/` tree (`test_builtin_skills.py`, and a dedicated test in `test_skill_registry_hardening.py` that explicitly asserts this). This was the sprint's core goal and remains verified after the additional fixes.

### Known limitations / confirmed follow-ups

- The two coexisting manifest schema "families" (`jarvis_builtin_system` and `JARVIS Core Team`) are not unified — `from_dict()` reads both without crashing, but no migration was performed, per explicit instruction not to rewrite every metadata.json this sprint. Unknown fields specific to the "JARVIS Core Team" shape (`display_name`, `actions`, `hotkey`) are silently ignored by `from_dict()` (never read, never crash) — this is no-crash tolerance, not schema compatibility; those fields are not modeled by `SkillMetadata` and are not preserved through a `SkillMetadata` round-trip.
- Manifest/telemetry separation is complete at `register_skill()` (this sprint's write site) but not at `synthesizer.py`'s own metadata.json write, which still uses `to_dict()` (out of scope, not modified).
- `discover_skills()` does not remove stale entries for skills deleted from disk between calls — pre-existing, out of scope.
- `is_safe_entrypoint_identifier()` gates `getattr(module, entrypoint_function)`, but in current production usage `entrypoint_function` is almost always the literal default `"execute"` — this check is primarily defense-in-depth for the less-used `SkillDefinition.from_dict()` path.
- `reload_skill()` still always `exec_module()`s a fresh module with no explicit teardown of the previous module object — pre-existing behavior, out of scope for this sprint.
- CI has not been run for this branch; not committed, not pushed, no PR opened.
- The 9 pre-existing unrelated baseline failures (mobile_bridge, proactive health-monitor) remain unfixed, per explicit instruction not to chase them.

**Post-main-sync correction (added when merging `main` into `feat/skill-plugin-hardening`)**: the "761 collected, 752 passed, 9 failed" figure above reflects `main` at `e4bcd6d` — the exact base this sprint branched from — **before** `main` merged PR #15 (`fix/ci-baseline`, which fixed both root causes of those 9 failures), PR #14 (Biometrics Hardening, +49 tests), PR #11 (Gesture/Data Reference-Hardening, +52 tests), and PR #12 (Agent Execution Hardening, +45 tests). This is a **historical record of what this sprint observed at the time it ran** — it is not being rewritten. Current merged-`main` local baseline before this Skill merge was **882 collected, 882 passed, 0 failed**; GitHub PR #12's own CI reported 882 collected, 879 passed, 3 skipped, 0 failed (the 3 skips are CI-environment-specific and were not reproduced locally).

**Actual post-main-sync validation** (run this session, after resolving the `CHANGELOG.md`/`CLAUDE.md`/`docs/PROJECT_STATE.md` merge conflicts from `main` into `feat/skill-plugin-hardening`):
```text
python -m pytest tests/unit/test_skill_registry_hardening.py tests/unit/test_plugin_sdk.py \
  tests/unit/test_plugins_m2.py tests/unit/test_builtin_skills.py tests/unit/test_skill_synthesis.py \
  tests/unit/test_skill_synthesizer.py tests/unit/test_adversarial_r1_r2_r5_stress.py \
  tests/unit/test_mobile_bridge.py tests/unit/test_proactive_engine.py -q --timeout=120
0 failed (all collected tests across these 9 files passed)

git status --short && git diff -- jarvis/skills/*/metadata.json
(both empty — no tracked metadata.json touched by the focused run, before or after)

python -m pytest tests/unit/ -q --timeout=120 --tb=short
907 collected, 907 passed, 0 skipped, 0 failed
```
907 = 882 (merged-`main` baseline, already confirmed locally after Biometrics + Gesture/Data + Agent) + 25 new tests this sprint adds (`tests/unit/test_skill_registry_hardening.py`) = 882 + 25 = 907, exactly as predicted before running. The 9 previously-known failures are genuinely gone (fixed by `fix/ci-baseline` on `main`), not skipped or masked — confirmed by an actual local run, not assumed. `git diff -- jarvis/skills/*/metadata.json` was re-checked after the full `tests/unit/` run too and remained empty, confirming the manifest/telemetry separation fix still holds on the merged baseline. **Zero regressions from the merge.**

### Recommended next task

Commit this sprint's changes (including the follow-up review fixes) on `feat/skill-plugin-hardening`, push, open a PR. Follow-ups explicitly out of scope here: unifying the two manifest schema families; migrating/rewriting existing packaged `metadata.json` files; updating `synthesizer.py` to use `to_manifest_dict()`; reconciling stale `discover_skills()` entries; any Phase 3 LLM-routing work; independently fixing the pre-existing mobile_bridge/proactive baseline failures.

---

## 0A. Phase 1 — Wake Word Reliability Hardening (in progress, uncommitted)

Snapshot: 2026-08-30. Four review rounds in the same overall effort: initial implementation, a dependency/API-surface correction pass, a correctness/determinism correction pass, and — after `main` advanced substantially — a **v4.1.0 sync + further correctness pass** (this one). Local working-tree change, **not committed, not pushed, no PR opened**. This section describes the final, verified state after all four rounds.

### v4.1.0 synchronization

- This branch (`feat/porcupine-wakeword-hardening`) was fast-forwarded onto the new `origin/main` baseline: **HEAD is now `2455fb6` — v4.1.0 "OS-Level Kernel Isolation & Master Technical Audit Hardening"** (source version `4.1.0` in `pyproject.toml`), contributed separately from this Phase 1 work. This v4.1.0 work (Windows MIC/Job Object OS-kernel sandboxing, closure/globals introspection hardening, Zalo webhook HMAC hardening, mobile-bridge upload allowlisting, an STT buffer fix, hardware benchmarking, `docs/SECURITY_ARCHITECTURE.md`, `docs/TECHNICAL_AUDIT_REPORT.md`) is **entirely outside Phase 1's wake-word scope** and was **preserved as-is, not reverted or rewritten** — verified by diffing only the 7 Phase 1 files (`CHANGELOG.md`, `CLAUDE.md`, `docs/PROJECT_STATE.md`, `jarvis/audio/wake_word.py`, `jarvis/core/app.py`, `pyproject.toml`, `tests/unit/test_wake_word.py`) against HEAD and confirming no other tracked file changed.
- The previously-approved Phase 1 working-tree changes (Porcupine processing, cooldown streaming, permanent degradation, partial-init cleanup, shutdown lifecycle, `toggle_enabled()`, disable/enable buffer clearing) were reapplied on top of this new baseline and re-audited; they needed no rewrite for v4.1.0 compatibility (see "Fixes implemented" below — items 1-9 are unchanged from the prior round; this round added item 10, the int16 stereo fix, plus determinism fixes).
- `CHANGELOG.md`'s merge conflict (from the sync) was resolved by keeping the new v4.1.0 section intact; a fresh Phase 1 "Chưa phát hành" section was reintroduced **above** it (pure insertion — the v4.1.0 section was not edited, reordered, or deleted).
- All validation in this document was **re-run after the sync**, against the actual v4.1.0-based `tests/unit/` baseline (see Validation results below) — not against the stale pre-4.1.0 numbers from earlier rounds.

### Scope

- Phase: Phase 1 of the JARVIS Ultimate InfoSec v2.0 integration roadmap — Wake Word reliability hardening.
- Branch: `feat/porcupine-wakeword-hardening`.
- Subsystem changed: `jarvis/audio/wake_word.py` (Tier 1 Porcupine backend), plus a small lifecycle hookup in `jarvis/core/app.py`.
- Upstream reference used: `.references/porcupine/binding/python/_porcupine.py` and `_factory.py` (Picovoice Porcupine official Python binding), consulted locally as an API-contract reference only. Package version **`pvporcupine==4.0.3`** per that same checkout's `binding/python/setup.py` line 69 — this is the exact version the implementation and the `pyproject.toml` dependency range were audited against. It is **not committed** — ignored via `.git/info/exclude` (`.references/`), confirmed with `git check-ignore -v .references/porcupine` and `git status` showing it untracked/absent. No upstream source was copied into `jarvis/`; only the documented public API contract (`create()` factory, `.process()`, `.frame_length`, `.sample_rate`, `.delete()`) was adapted. Upstream file headers are Picovoice/Apache-style license notices — irrelevant to JARVIS's own license since no upstream code was copied.

### Defect independently confirmed

- Prior claim ("Porcupine initializes but `feed_audio_block()` only has a real Tier 1 path for Vosk") was verified true by direct code reading, not assumed. In the pre-fix `feed_audio_block()`, the Tier 1 branch was `if self._engine_type == WakeWordEngineType.VOSK and self._tier1_engine:` with no `elif` for `PORCUPINE` — so a successfully initialized Porcupine engine was constructed and stored but never called; every block silently fell through to the Tier 2 `AcousticSpectralDetector`.
- The same shape of defect was independently confirmed for `WakeWordEngineType.OPENWAKEWORD` (same missing branch) — see "OpenWakeWord finding" below.
- A separate, related defect was found during the same audit and fixed in this phase: `jarvis/core/app.py`'s global hotkey callback calls `self.wake_word_detector.toggle_enabled()`, which did not exist on `WakeWordDetector` (only `set_enabled()`/`is_enabled()`/the `enabled` property did) — would have raised `AttributeError` if that hotkey path were ever exercised.

### Root cause

`feed_audio_block()`'s Tier 1 dispatch only had a single hardcoded `if` for Vosk; it was never extended when Porcupine/OpenWakeWord init paths were added to `_init_tier1()`.

### Fixes implemented (final state)

1. **Real Porcupine processing.** `feed_audio_block()` now actually calls into Porcupine via `_process_porcupine_tier()`, which resamples to `porcupine.sample_rate` (reusing `resample_audio()`; reuses the already-computed 16kHz array when `porcupine.sample_rate == target_sample_rate`, the common case), converts to clipped int16 PCM, and feeds it through `_PorcupineFrameBuffer` — a helper that buffers PCM across calls and drains every complete `frame_length` frame in order (never skipping one, even when an earlier/middle frame in the same block already detected a keyword), carrying over any partial remainder. Verified end-to-end against the real production `AudioEngine` default path: `sample_rate=44100`, `block_ms=40` → exactly 1764 raw samples/callback → exactly 640 resampled samples/callback — a dedicated test feeds this exact production block size over several consecutive callbacks and asserts every call into the mocked `process()` receives exactly `frame_length` samples, never a malformed one.
2. **Cooldown suppresses emission, not Porcupine's audio consumption.** `feed_audio_block()` always runs the Porcupine branch first (so the engine keeps streaming through the post-detection cooldown window and never desyncs from live audio), then applies the cooldown gate to decide whether to emit a `WakeWordResult`/callback. Vosk and Tier 2 keep the prior behavior of being skipped entirely during cooldown (unchanged, per explicit instruction). A dedicated test drives a mocked Porcupine through a detection, three more complete frames fed *during* cooldown (asserting `process()` call count grows by exactly 3 and no second callback fires), then a detection past cooldown.
3. **Runtime failures permanently degrade the backend.** A `porcupine.process()` exception now releases the native engine exactly once, clears the pending frame buffer, and flips `_engine_type` to `ACOUSTIC_FALLBACK` for the rest of this detector's lifecycle — the failed engine is never invoked again on a later callback (this replaces an earlier, superseded "fall back for this one block only, keep retrying" behavior, which risked the same native failure repeating on every subsequent callback). Tier 2 keeps working normally afterward. Implemented via `_degrade_porcupine_to_acoustic_fallback()`.
4. **Partial-init leak fixed.** `_init_tier1()` builds the native engine and its `_PorcupineFrameBuffer` in local variables first, and only attaches them to `self` once both steps have fully succeeded. If `pvporcupine.create()` succeeds but a later step fails (e.g. reading `.frame_length`/`.sample_rate`, or constructing the adapter), the just-created native engine is deleted inline before falling back to `ACOUSTIC_FALLBACK` — previously it could have been assigned to `self._tier1_engine` before the failure, silently leaking a native handle that `shutdown()`'s `engine_type == PORCUPINE` guard would never see (because `_init_tier1()` had already returned `ACOUSTIC_FALLBACK`).
5. **Shared release helper.** `_release_porcupine_native()` is the single locked, idempotent helper that both `shutdown()` and the runtime-failure degradation path call, so `porcupine.delete()` lifecycle logic cannot diverge between the two call sites and can never double-delete.
6. **Shutdown lifecycle.** `WakeWordDetector.shutdown()` calls `porcupine.delete()` exactly once via the shared helper; idempotent; safe after partial/failed init or after a runtime degradation. Protected by the detector's own `RLock` — the same lock `feed_audio_block()` holds while calling `porcupine.process()`, so `delete()` can never run concurrently with an in-flight `process()` call. `jarvis/core/app.py`'s `stop()` calls `wake_word_detector.shutdown()` **after** `audio_engine.stop_stream()` (which joins the audio worker thread) — confirmed this ordering was already correct in the very first pass and needed no change; the shared-lock guarantee also means correctness does not strictly depend on that join completing in time. Verified with a test that uses an explicit `threading.Event()` to prove `shutdown()` genuinely blocks while `process()` is in-flight (no `time.sleep()` timing assumptions).
7. **`reset()`** also clears the Porcupine frame buffer's pending partial frame; verified `reset()` after `shutdown()` never dereferences the deleted engine/buffer.
8. **Disable/enable clears JARVIS-owned streaming buffers only (precise, narrow claim).** `set_enabled()` and `toggle_enabled()` now share one transition helper, `_reset_stream_state_locked()`, so they cannot diverge: on an actual enabled-state change, the ring buffer and any pending partial Porcupine frame are cleared, so **caller-owned PCM** from before an arbitrarily long disabled gap is never concatenated with caller-owned PCM from after it. This does **not** reset the native Porcupine engine's own internal state — no reset API is used or exists in the audited upstream contract short of full reinitialization (intentionally out of scope); whatever detection history the native engine keeps internally may still span the disabled interval. This is the deliberate, narrow lifecycle guarantee being made — do not describe it as "audio can never be connected in any way" across a toggle. Feeding audio while disabled still never reaches Porcupine at all (unchanged, pre-existing early-return). `_last_trigger_time` (the cooldown timer) is deliberately **not** reset on enable/disable — documented and tested as a chosen semantic: cooldown is a real-time debounce independent of the toggle, so rapid disable/enable must not be usable to bypass it.
9. **`toggle_enabled()` added**, thread-safe, returns the resulting `enabled` bool, fixing the confirmed `AttributeError` risk described above. `set_enabled()`, `is_enabled()`, and the `enabled` property are otherwise unchanged.
10. **int16 stereo normalization ordering fixed (found and fixed this round).** In `feed_audio_block()`, the format-conversion block used to run `np.mean(arr, axis=1)` (multi-channel downmix) *before* checking `np.issubdtype(arr.dtype, np.integer)`. For an int16 stereo array, `np.mean()` promotes the result to `float64`, which made the integer check false and silently skipped the `/32768.0` normalization branch — stereo int16 PCM was interpreted at raw amplitude scale (~[-32768, 32767]) instead of `[-1.0, 1.0]`. Fixed by normalizing integer PCM to `[-1.0, 1.0]` *before* the channel downmix; float32 mono, float stereo, and int16 mono behavior are all unchanged by the reordering (verified by two new exact-value regression tests: `test_wake_word_int16_mono_normalization_exact`, `test_wake_word_int16_stereo_normalization_exact`). `AudioEngine` was not touched.
11. No changes to `AudioEngine`, `VAD`, full-duplex, or `Faster-Whisper` STT, gesture detection, LLM routing, security modules, or the installer/release pipeline.

### Files/modules affected

- `jarvis/audio/wake_word.py` — `_PorcupineFrameBuffer` (new), `WakeWordDetector._init_tier1()`, `._reset_stream_state_locked()` (new), `.set_enabled()`, `.toggle_enabled()` (new), `.reset()`, `._release_porcupine_native()` (new), `.shutdown()`, `._degrade_porcupine_to_acoustic_fallback()` (new), `._process_porcupine_tier()` (new), `.feed_audio_block()` (int16-stereo-normalization-order fix this round).
- `jarvis/core/app.py` — `stop()` calls `self.wake_word_detector.shutdown()` (guarded, exception-isolated) after `audio_engine.stop_stream()`; the pre-existing `toggle_enabled()` call in the hotkey callback now has a real method to call.
- `tests/unit/test_wake_word.py` — **53 wake-word tests total**: 23 pre-existing at the v4.1.0 baseline + 30 added by Phase 1. The 30 Phase-1-added tests are mocked/state-machine tests and are deterministic (no real backend package, no random content where a mock determines the outcome). The 23 pre-existing tests are not all mocked — several genuinely exercise `AcousticSpectralDetector` against synthetic acoustic signal generated by `generate_wake_word_signal()`, which is a real (if synthetic) classification path, not a mock. This round added the int16 mono/stereo tests and hardened several of the newly-added generic-state tests to force `VOSK_AVAILABLE`/`OPENWAKEWORD_AVAILABLE`/`PORCUPINE_AVAILABLE` to `False` and replace random `generate_wake_word_signal()` content with deterministic PCM wherever a mock (not genuine acoustic analysis) determines the test outcome.
- `pyproject.toml` — new `wakeword` optional dependency group.

No other tracked file is part of the Phase 1 change set. `git diff --name-only` against HEAD confirms exactly these 7 files; anything else appearing in `git status` (see Known limitations) is unrelated test-run side effects, not Phase 1 changes.

### Dependency changes

- Added `[project.optional-dependencies].wakeword = ["pvporcupine>=4.0.3,<5"]` to `pyproject.toml`, matching the exact audited upstream major version (see Scope above), and included `wakeword` in the `all` extras aggregate.
- `pvporcupine` remains fully optional: not in base `dependencies`, not required for normal startup, not required in CI, no real Picovoice access key needed anywhere in tests (all Porcupine tests patch `PORCUPINE_AVAILABLE`/`pvporcupine` with mocks). Only the API *contract* was audited this session — actual `pip install pvporcupine==4.0.3` / real import was not exercised (see Known limitations).

### OpenWakeWord finding (not implemented — out of scope for Phase 1)

- Confirmed via code inspection: same "initialized but never processed" defect shape (`feed_audio_block()` only checks `WakeWordEngineType.VOSK`).
- Verified upstream `Model.predict()` contract (openWakeWord, via public source — no local `.references/` copy was staged for it, unlike Porcupine): accepts a NumPy int16/16kHz array of **arbitrary length** (library does its own internal chunk accumulation), and returns a **dict of per-model/per-class float scores in [0, 1]**, not a single boolean/index. `Model` keeps its own stateful prediction/feature buffers across calls and exposes its own `reset()`.
- **Not fixed in this phase, by explicit instruction.** The API shape is materially different from Porcupine's (dict-of-scores + library-internal buffering vs. index + caller-owned frame buffering), would need its own threshold/score-key calibration and verification of default-model-loading behavior (risk of implicit network access / non-determinism if `openwakeword.Model()` with no args triggers a model download — unverified), and no vetted local reference was staged for it this session. No OpenWakeWord models were downloaded, no new OpenWakeWord dependency was added, no OpenWakeWord code was touched. Documented as a **confirmed follow-up issue**.

### Validation results (re-run this round, on HEAD `2455fb6` / v4.1.0 + Phase 1 working tree)

Targeted:
```text
python -m pytest tests/unit/test_wake_word.py --timeout=60 --tb=short -v
53 passed in 0.94s
```

Full `tests/unit/`:
```text
python -m pytest tests/unit/ --timeout=60 --tb=short
681 passed, 46 subtests passed in 97.09s (0:01:37)
0 failed
```
**Actual v4.1.0 baseline (HEAD, before Phase 1), computed exactly:** `git show HEAD:tests/unit/test_wake_word.py` has 23 `test_` functions; the current working tree has 53; no other test file is touched by Phase 1 (confirmed via `git diff --stat`). So the v4.1.0-only `tests/unit/` baseline is **681 − 30 = 651 passed**, and Phase 1 adds exactly **+30** wake-word tests this round, with zero regressions elsewhere. (Do not reuse the older, now-superseded counts 647/664/670/675 from earlier rounds before the v4.1.0 sync — 651 is the correct current baseline to diff against.)

Static analysis:
```text
ruff check jarvis tests scripts/build_installer.py
Found 3 errors (I001 x2, E401 x1), 3 fixable with --fix
  - tests/integration/test_sandbox_os_boundaries.py:16 (import sort)
  - tests/unit/test_zalo_bot.py:50 (import sort + multiple-imports-on-one-line)

mypy jarvis
Success: no issues found in 157 source files
```
The 3 Ruff findings are **pre-existing in the v4.1.0 baseline** (both files belong to the other contributor's security work — commits `d1c3f82` and `d3b2595` — neither touched by Phase 1). Confirmed by scoping Ruff to exactly the Phase 1 files:
```text
ruff check jarvis/audio/wake_word.py jarvis/core/app.py tests/unit/test_wake_word.py pyproject.toml
All checks passed!
```
Not fixed here — out of scope (unrelated security-module test files; "no broad unrelated refactor").

`py_compile` (all changed files):
```text
python -m py_compile jarvis/audio/wake_word.py jarvis/core/app.py tests/unit/test_wake_word.py
exit 0
```

`git diff --check`:
```text
git diff --check
exit 0 (no output — no whitespace/conflict-marker issues)
```

Headless/mock-audio smoke/import validation (`JARVIS_HEADLESS=1 JARVIS_MOCK_AUDIO=1`, no microphone or real access key involved):
```text
WakeWordDetector() constructs with no native backend -> engine_type=acoustic_fallback
toggle_enabled() flips True<->False correctly
shutdown() is a safe no-op with no native backend, idempotent
jarvis.core.app imports cleanly with the updated shutdown() call wired in
```

### Known limitations / confirmed follow-ups

- OpenWakeWord has the same class of defect as Porcupine had; intentionally not fixed this phase (see above). Recommended as the next focused task, ideally after staging a local `.references/openwakeword` checkout the same way Porcupine's was staged for this phase.
- This phase has not run in CI. CI has not been triggered; no commit, push, or PR exists yet for this work.
- The 3 pre-existing Ruff findings in `tests/integration/test_sandbox_os_boundaries.py` and `tests/unit/test_zalo_bot.py` (v4.1.0 baseline, unrelated to wake word) are not a Phase 1 blocker but are noted here since `ruff check jarvis tests scripts/build_installer.py` as a whole no longer reports clean.
- **Real microphone / spoken "Hey JARVIS" / real Picovoice AccessKey end-to-end validation remains intentionally deferred**, per explicit instruction — this is not an unresolved defect, missing implementation, or failed Phase 1 requirement. Phase 1 validation relied entirely on deterministic mocks, headless operation, unit/lifecycle tests, static analysis, and import/smoke tests, none of which require physical hardware. Real-hardware validation, and with it the first real-world confirmation that `pvporcupine>=4.0.3,<5` actually installs/imports correctly (only its API *contract* was audited, not an actual `pip install`), remains for a future task the user explicitly requests.
- Unrelated, pre-existing working-tree noise observed again this round (not caused by any Phase 1 code change): running `tests/unit/` repeatedly mutates 9 tracked `jarvis/skills/*/metadata.json` files (runtime invocation-count/timestamp telemetry written by the skill registry on load). Per this round's explicit instruction, no attempt was made to revert them (previous attempts were blocked by the sandbox's destructive-action guard anyway); the user will restore them manually before commit.

### Upstream Porcupine behavior intentionally NOT adopted

- Multi-keyword support (`keyword_paths`/multiple simultaneous keywords with per-index disambiguation) — JARVIS's existing `_init_tier1()` already hardcodes a single `keywords=["jarvis"]`; this phase preserved that and canonicalizes any detected index to the existing `"hey_jarvis"` keyword string (matching the convention already used by the Vosk/Tier 2 paths), rather than introducing per-keyword name plumbing.
- Device/GPU selection (`device` parameter on `pvporcupine.create()`) — left at upstream default; JARVIS's config surface for Porcupine is intentionally minimal (`porcupine_access_key`, `sensitivities` derived from the existing `sensitivity` field only).
- `pvporcupine.available_devices()` / hardware enumeration — not exposed; out of scope for a reliability fix.
- No native Porcupine "reset" API was invented for the disable/enable buffer-clearing fix — upstream exposes no such call short of full reinitialization, so only JARVIS-owned caller-side buffers are cleared on a transition (see Fixes implemented, item 8).

### Recommended next task

Fix the confirmed OpenWakeWord "initialized but never processed" defect as its own focused phase, after staging a local OpenWakeWord reference (mirroring how `.references/porcupine` was staged here) and verifying default-model-loading/network behavior is safe for headless CI. Real-microphone/real-AccessKey Porcupine validation remains a separate, explicitly-deferred follow-up whenever the user wants it exercised.

---

## 0B. Windows Sandbox CI Compatibility Fix (in progress, uncommitted)

Snapshot: 2026-08-30. Branch `fix/sandbox-windows-ci-compat`, based on `origin/main` v4.1.0, commit `2455fb6`. Local working-tree change, **not committed, not pushed, no PR opened**. Separate and independent from the Wake Word Phase 1 branch (`feat/porcupine-wakeword-hardening`) — does not touch `jarvis/audio/wake_word.py`, Porcupine, or PR #8. This snapshot reflects a **second review pass** that fixed three security blockers found in the first pass (readiness boundary, generic-exception retry, Job Object fail-open) — see "Fixes implemented" below for the corrected final state.

### Root cause (bisected, verified against commit history)

- Known-good: `3039bb4` ("multi-layer OS process isolation and Job Object bounds") and `dfa2eaf` ("deep adversarial defense") — GitHub Actions runs #38/#39 both SUCCESS. At this point the sandbox used Windows Job Object + the previously-working `subprocess.Popen` execution path.
- First bad commit: `adab40d` ("resolve all 4 sandbox bypasses with true OS Restricted Tokens...") — GitHub Actions run #40 FAILURE. This commit replaced the working `subprocess.Popen` path with `CreateRestrictedToken` + `CreateProcessAsUserW` (`jarvis/sandbox/security.py` +294/-?? per `git show --stat adab40d`). Confirmed via `git log --oneline dfa2eaf..adab40d`.
- Exactly 6 `tests/unit/` tests began failing at run #40 and remained failing through v4.1.0/PR #8 (all real-execution tests through `CodeInterpreterSandbox.execute_python()`, no mocks):
  1. `tests/unit/test_adversarial_r1_r2_r5_stress.py::TestAdversarialR2SandboxSecurity::test_sandbox_timeout_and_resource_bounds_enforcement`
  2. `tests/unit/test_hud_telemetry_and_memory.py::TestJarvisAppAutonomousIntegration::test_app_sandbox_action_dispatch`
  3. `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_artifact_capture_image_and_excel`
  4. `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_extra_files_provisioning`
  5. `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_python_execution_data_processing`
  6. `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_timeout_termination`
- Observed GitHub CI failure signature: exit code `3221225794` decimal (`0xC0000142` — `STATUS_DLL_INIT_FAILED`). Timeout tests expect `-1` but receive this value because the restricted child dies during its own process/DLL initialization before test code can run **in the observed cases**; normal sandbox scripts also show empty stdout / `success=False`. **Important correction from the first pass**: this NTSTATUS code alone is not formal proof that no user code ran in general — see the readiness-handshake fix below, which is the actual safety boundary now used.
- **Exact defect**: Microsoft's `CreateProcessAsUser` contract explicitly permits the call to report success before the child's own initialization completes. The prior `jarvis/sandbox/interpreter.py` set `spawned_via_token = True` unconditionally once `spawn_low_integrity_process()` returned without raising — so a child that died immediately with `STATUS_DLL_INIT_FAILED` was misreported as "the restricted backend executed the script and returned an unusual exit code," not as "OS isolation could not be established." Later MIC/SACL work is NOT the origin of this regression — CI was already red starting at `adab40d`, before that later work landed.

### Fixes implemented (final state, after the second security review pass)

1. **Bootstrap-failure classification** (`jarvis/sandbox/security.py`): `STATUS_DLL_INIT_FAILED = 0xC0000142` (+ `STATUS_DLL_NOT_FOUND`, `STATUS_ENTRYPOINT_NOT_FOUND`), `is_restricted_process_bootstrap_failure(exit_code)`, and `RestrictedProcessBootstrapError(OSError)` — distinct from a normal (even nonzero) script exit code, a timeout, an AST rejection, or an explicit Python exception.
2. **Readiness handshake — the real retry-safety boundary (Blocker 1 fix).** An NTSTATUS-shaped exit code alone is NOT proof no user code ran (the child could have crossed into the preamble or user code and only later hit a native DLL failure). The injected preamble (`SANDBOX_BOOTSTRAP_PREAMBLE`) now writes an internal sentinel to stdout, through the already-capped writer, as the last thing it does — after every security guard is installed, before appended user code begins. Observable without buffering ambiguity because the child runs with `-u`. `strip_sandbox_ready_sentinel()` strips it from output before `SandboxResult`/structured-result parsing, on both the restricted-token and compatibility paths. Classification: STATUS_* + sentinel **never observed** → `RestrictedProcessBootstrapError` (retry-eligible); STATUS_* + sentinel **observed** → returned normally as a genuine execution outcome, never retried.
3. **`RestrictedProcessBootstrapError.retry_safe` (Blocker 2 fix).** Defaults `False` ("unknown state => never retry"), and is set to `True` only where a failure is *formally provable* to have occurred before the child executed any instruction: pre-`CreateProcessAsUserW` failures, Job Object assignment failing on a still-suspended child, or `ResumeThread` itself failing (the thread was never resumed). `WaitForSingleObject`/`GetExitCodeProcess` failing **after** the child was resumed cannot be proven pre-execution, so these raise with `retry_safe=False`. **A generic/unclassified exception is never retry-eligible under any circumstance, regardless of the compat flag** — `execute_python()` only ever falls back for a `RestrictedProcessBootstrapError` with `retry_safe=True`. Replaced the now-corrected test `test_unexpected_launcher_exception_falls_back_when_explicitly_enabled` (previously enforced unsafe behavior) with `test_unexpected_launcher_exception_never_falls_back_even_when_enabled`.
4. **`CREATE_SUSPENDED` + Job Object assigned before resume (Blocker 3 fix).** The restricted child is created with `CREATE_SUSPENDED` (executes zero instructions). It is assigned to the Job Object **while still suspended**; only on confirmed success is `ResumeThread` called. If Job Object assignment fails, the suspended child is `TerminateProcess`'d and `ResumeThread` is **never** called — this closes the prior race where a child could run before Job Object bounds applied, and is formally provable to be pre-execution (`retry_safe=True`). `ResumeThread`'s return value is checked (`0xFFFFFFFF` = failure). **A real bug found and fixed while implementing this**: `WaitForSingleObject` and `ResumeThread` lacked explicit `restype`, so ctypes' signed-`int` default silently turned their `0xFFFFFFFF` failure sentinels into `-1`, breaking every `== 0xFFFFFFFF` comparison; both now declare `restype = wintypes.DWORD`.
5. **Compatibility Popen path also fails closed on Job Object failure.** If the post-hoc `AssignProcessToJobObject` fails there, the process is killed immediately rather than silently continuing as if "Job-Object + scrubbed environment" isolation were active. Documented, narrow exception: unlike the restricted-token path, `subprocess.Popen` has no `CREATE_SUSPENDED` equivalent, so an unavoidable brief race window exists between process creation and this check — a known, weaker property of this explicit-opt-in, non-production-only path.
6. **Fail-closed by default** (`execute_python()`): any non-retry-eligible outcome returns `SandboxResult(success=False, exit_code=-1)` with a clear, non-sensitive refusal message, never silently executing with weaker isolation.
7. **Explicit, narrow compatibility opt-in**: `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK` (`SANDBOX_COMPAT_FALLBACK_ENV_VAR`/`is_compat_fallback_enabled()`). Only when set AND the failure is a `retry_safe=True` `RestrictedProcessBootstrapError` does execution fall back to the legacy Job-Object + scrubbed-environment `subprocess.Popen` path. Disabled by default; never auto-detected from `GITHUB_ACTIONS`; a warning is logged whenever it activates.
8. **Previously-unchecked Win32 return values audited and fixed**: `ConvertStringSidToSidW`, `CreatePipe`, `WaitForSingleObject` (`WAIT_FAILED`), `GetExitCodeProcess`, `ResumeThread`, `AssignProcessToJobObject` (now fail-closed, not just logged, in the restricted-token path — see item 4). Most critically, **`SetTokenInformation(TokenIntegrityLevel)`'s return value is checked** — if it fails, the child is never launched. `SetHandleInformation` failure is logged only (doesn't affect the isolation guarantee).
9. **Resource cleanup re-verified after the `CREATE_SUSPENDED` changes**: all Win32 handles (token, restricted token, process, thread, pipe) and the allocated SID pointer (`LocalFree`) are still released exactly once via a single `finally`-backed `_cleanup()` covering every exit path, including the new suspend/assign/resume/terminate paths. No double-close.
10. **No security hardening removed**: Windows Job Object, `ActiveProcessLimit`, memory limit, environment scrubbing, `sys.meta_path`/`sys.modules` blocking, filesystem allowlist, COM/win32 blocking, Low Integrity SACL code, `TokenIntegrityLevel` code, introspection protections, stdout cap, and all Zalo/mobile security work are unchanged. This remains a compatibility/error-classification repair, not a rollback of v4.1.0 security.
11. **CI**: `.github/workflows/ci.yml`'s `test` (Unit Tests) job only sets `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK: "1"` at job level. No other job or release/package workflow sets it.

### Files changed

- `jarvis/sandbox/security.py` — readiness sentinel + `strip_sandbox_ready_sentinel()`, `RestrictedProcessBootstrapError.retry_safe`, `CREATE_SUSPENDED`/Job-before-resume/`ResumeThread`-checked launch sequence, `WaitForSingleObject`/`ResumeThread` `restype` fix, bootstrap-failure classification, compat-fallback env-var helper, single-`finally` cleanup re-verified.
- `jarvis/sandbox/interpreter.py` — `execute_python()`'s subprocess-execution block restructured around `retry_safe`-gated fail-closed/compat-fallback policy; sentinel stripped on both paths; compat Popen path fails closed on Job Object assignment failure; imports updated.
- `.github/workflows/ci.yml` — `test` job job-level `env: JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK: "1"`, documented inline.
- `tests/unit/test_sandbox_compat_fallback.py` — **new file**, 40 deterministic mocked regression tests collected (30 test functions; 2 are `@pytest.mark.parametrize`d into 12 total cases) (not an "expected" file per the task's file list, but necessary: adding mocks into the existing real-execution sandbox test files would have contaminated their purpose).

No other tracked file is part of this change set. `jarvis/audio/wake_word.py`, `tests/unit/test_wake_word.py`, the Porcupine dependency, and unrelated Zalo/mobile/STT source were not touched.

### Validation results (this session, local Windows, after the security review pass)

Targeted (6 historically-failing tests):
```text
6 passed in 5.13s
```
(Expected: local Windows does not reproduce GitHub's `STATUS_DLL_INIT_FAILED`, so these pass both before and after this fix locally — the fix's effect is only observable on GitHub-hosted CI.)

Sandbox-focused files together:
```text
python -m pytest tests/unit/test_skill_synthesis.py tests/unit/test_adversarial_r1_r2_r5_stress.py \
  tests/unit/test_hud_telemetry_and_memory.py tests/unit/test_sandbox_compat_fallback.py \
  --timeout=120 --tb=short
100 passed, 46 subtests passed in 15.38s
```

Full `tests/unit/`:
```text
691 passed, 46 subtests passed in 92.46s (0:01:32)
0 failed
```
The actual v4.1.0 baseline (this branch, before this fix) is **651 passed** (not 647 — that figure in some older docs was already stale; 651 was independently confirmed against this same `2455fb6` commit on another branch). 691 − 651 = exactly the 40 new tests in `test_sandbox_compat_fallback.py`; no regressions.

Static analysis:
```text
ruff check jarvis/sandbox tests/unit/test_sandbox_compat_fallback.py
All checks passed!

mypy jarvis
Success: no issues found in 157 source files
```

`py_compile jarvis/sandbox/security.py jarvis/sandbox/interpreter.py`: exit 0.
`git diff --check`: exit 0 (one benign CRLF-normalization warning on the new test file, not an error).

### Known limitations / confirmed follow-ups

- **CI has not been run for this fix.** The real GitHub-hosted Windows Server `STATUS_DLL_INIT_FAILED` behavior was diagnosed from the forensic bisection facts and historical CI logs, not reproduced locally (expected — local Windows works fine with the Restricted Token path). Final confirmation that the compat fallback actually resolves the 6 CI failures requires a real GitHub Actions run after review/push.
- Enabling `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1` in CI's Unit Tests job means those specific test runs exercise the Job-Object + scrubbed-`Popen` path, not Low Integrity Restricted Token isolation end-to-end. This is documented, not claimed as equivalent validation.
- Root cause of *why* GitHub-hosted Windows Server 2025 specifically fails `CreateProcessAsUserW`-launched children with `STATUS_DLL_INIT_FAILED` (a missing/incompatible DLL under that restricted token context on that specific runner image) was not further investigated — out of scope; the classification/fail-closed/opt-in-fallback policy is correct regardless of the underlying platform-specific cause.
- The compatibility Popen path's Job Object assignment has an unavoidable brief race window (no `CREATE_SUSPENDED` equivalent for plain `subprocess.Popen`) — documented as a known, narrow, weaker property of that explicit-opt-in, non-production path only; not present in the primary Restricted Token path.
- `jarvis/skills/*/metadata.json` telemetry files mutated by running `tests/unit/` this session were restored (`git checkout --`) per explicit instruction; not part of this change set.

### Recommended next task

Push this branch and open a PR to observe the real GitHub Actions Windows Server behavior with `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1` active in the Unit Tests job, confirming the 6 previously-failing tests go green in that environment specifically (not just locally). If GitHub's runner image issue is later understood/fixed upstream, consider removing the CI opt-in and validating Restricted Token isolation directly in CI again.

---

## 0C. Central Safety-Layer Hardening (Phase 2, in progress, uncommitted)

Snapshot: 2026-08-30. Branch `feat/safety-layer-hardening`, based on `main` **after** both PR #8 (Wake Word Phase 1) and PR #9 (Sandbox CI Compatibility Fix) were merged — `git log` confirms `main` HEAD `35713b9` (merge of PR #8) with `8c7e530` (merge of PR #9) as an ancestor. Local working-tree change, **not committed, not pushed, no PR opened**. Independent of both merged PRs — does not touch `jarvis/sandbox/*` or `jarvis/audio/wake_word.py`.

### Audit performed first (per explicit instruction, before any implementation)

Traced the actual, current safety architecture by reading code, not assuming from docs:

- `SafetyGate` ([jarvis/automation/safety_gate.py](../jarvis/automation/safety_gate.py)) — generic two-phase token confirmation primitive (30s TTL, voice/text affirmative/negative phrase matching). Solid, reusable; **left unmodified** this phase.
- `SafetyGateInterceptor` ([jarvis/planner/safety_interceptor.py](../jarvis/planner/safety_interceptor.py)) — risk classifier (`HIGH_RISK_ACTIONS`, prefix matching, `DANGEROUS_PATTERNS` regexes) wrapping `SafetyGate`, used by `ReActTaskEngine.execute_plan()` — but **only** when called with `mode=PlanMode.SAFETY_GATE`. Traced `execute_plan()`'s only real production caller, `JarvisApp._handle_planner_execute_task()` → invoked at `app.py`'s intent-routing block with no `mode` argument → always defaults to `PlanMode.FULLY_AUTONOMOUS` → the interceptor's `is_high_risk_node()` check was **dead in production**.
- `ShellAssistant.is_destructive()` ([jarvis/automation/shell_assistant.py](../jarvis/automation/shell_assistant.py)) — its own, separate destructive-command regex/keyword gate, wired to the same shared `SafetyGate` instance but with duplicated, divergent classification logic from `SafetyGateInterceptor.DANGEROUS_PATTERNS`.
- `IntentResult.requires_confirmation`/`confirmation_prompt` ([jarvis/llm/router.py](../jarvis/llm/router.py)) — a **third**, independent risk flag the LLM router computes for `system_power` (shutdown/restart/sleep) intents, with a ready Vietnamese confirmation prompt. Grepped the entire `jarvis/` tree for `requires_confirmation`: **read nowhere outside `router.py` itself.** Also confirmed `"system_power"` was not registered as a dispatcher action anywhere — so today this intent fails with `ACTION_NOT_FOUND` rather than executing unconfirmed; still a real, latent gap (would become live the moment a real handler is registered), closed here.
- `ActionDispatcher.dispatch_action()`/`dispatch_action_async()` ([jarvis/core/dispatcher.py](../jarvis/core/dispatcher.py)) — the actual funnel for intent-routed voice/text commands, skills, Telegram, plugins, and (via `vision_click_ui`/`vision_type_ui`) `GUIActor`. Had **only** RBAC privilege interception; zero destructive-action awareness.
- `GUIActor` ([jarvis/automation/gui_actor.py](../jarvis/automation/gui_actor.py)) — accepts a real, shared `SafetyGate` instance at construction (`app.py` wires `safety_gate=self.safety_gate`) but a full grep of the file showed it is **never called** — dead wiring giving false confidence. Traced its only two callers, `_handle_vision_click_ui`/`_handle_vision_type_ui`, and confirmed both are registered `ActionDispatcher` actions with no other (non-dispatcher) call site — meaning the dispatcher-level fix protects this path automatically, with no change to `gui_actor.py` needed or made.
- Traced `ReActTaskEngine.execute_step()` precisely, per instruction: it has two real paths — `self._action_handlers` (populated via `register_action_handler()`/`custom_action_handlers`, **bypasses `ActionDispatcher` entirely**) and `self.dispatcher.dispatch_action(..., requester="planner")`. Grepped the whole tree: `register_action_handler`/`custom_action_handlers` is **never populated in production** (only in tests) — so today, every real planner node execution already reaches `ActionDispatcher`. The bypass path is real and reachable, though, so it is still covered (see "Fixes implemented" below), not left open just because production doesn't currently exercise it.

### Fixes implemented

1. **Single authoritative classifier** (`jarvis/planner/safety_interceptor.py`): `SafetyGateInterceptor.is_high_risk(action_name, parameters, explicit_flag=False)` generalizes the prior `is_high_risk_node(TaskNode)` (now a one-line wrapper over it, guaranteeing the two can never diverge). Adds deterministic `system_power`/`power_action` recognition (`SYSTEM_POWER_ACTION_NAMES`/`SYSTEM_POWER_DESTRUCTIVE_SUBACTIONS`: `shutdown`/`restart`/`reboot`/`poweroff`/`power_off`/`sleep`/`hibernate`, explicitly excluding `lock`) — matched against the actual `action_name="system_power"`, `parameters={"action": ...}` shape the real `LLMIntentRouter` emits (verified by reading `router.py`), never against `IntentResult.requires_confirmation`.
2. **Pending-action binding layer** (`jarvis/planner/safety_interceptor.py`, `SafetyGate` itself untouched): `gate(action_name, parameters)` issues a token via the existing `SafetyGate.request_confirmation()`, storing `{"action_name", "parameters"}`. `verify(token, action_name, parameters)` — under an interceptor-owned `RLock` — requires the token to be known, not already consumed, not expired, not rejected, `status == "CONFIRMED"`, and an **exact** match on both `action_name` and `parameters`; only then marks it consumed in an interceptor-local `_consumed_tokens` set. `intercept_node()` (the pre-existing planner-facing method) was left behavior-unchanged but already stored the same `{"action_name", "parameters"}` shape (plus `step_id`), so tokens it issues are `verify()`-compatible without any change to it.
3. **`ActionDispatcher` primary enforcement point** (`jarvis/core/dispatcher.py`): new `_evaluate_safety_gate(action_name, payload, confirmation_token, context)` helper, called from both `dispatch_action()` and `dispatch_action_async()` after the existing privilege check and before handler execution. Not risky → `None` (unchanged behavior). Risky + no/invalid token → failed `ActionResult` (`error_code="CONFIRMATION_REQUIRED"` or `"CONFIRMATION_<reason>"`, token included in `data`), handler never runs. Risky + `verify()`-passing token → proceeds to execute. New constructor param `safety_interceptor` (lazily imports and default-constructs `SafetyGateInterceptor()` if omitted, to avoid a circular import with `jarvis.planner` at module scope and to keep bare `ActionDispatcher()` protected by default in tests); new `set_safety_interceptor()` setter. **Explicitly verified this check is not gated by `self.bypass_security`** — that flag's effect is unchanged (RBAC/privilege only).
4. **Planner (`jarvis/planner/engine.py`)**: `execute_plan()`'s high-risk interception condition dropped its `mode == PlanMode.SAFETY_GATE` guard — it now applies to any `is_high_risk_node()`-classified node regardless of `PlanMode` (closes the dead-in-production gap; `FULLY_AUTONOMOUS` still skips gating for non-high-risk nodes, so low-risk autonomy is unaffected). Parameter interpolation (`dag.interpolate_node_params(node)`) was hoisted from immediately-before-dispatch to immediately-before-the-risk-check, in the same loop pass, so a gated token's stored `parameters` are byte-identical to what is later dispatched (no interpolation-timing mismatch against the new exact-match `verify()`). `execute_step()` now passes `confirmation_token=node.confirmation_token` into `dispatcher.dispatch_action()`, so a node the planner poll-loop already gated and confirmed is not re-gated a second, redundant time at the dispatcher (the dispatcher's own `verify()` still independently re-validates it — defense in depth, not a skip).
5. **`GUIActor`: no code changes.** Confirmed (see audit above) its only two callers are dispatcher-registered actions; gating happens at that semantic boundary via the shared classifier scanning `query`/`text` string payloads against the existing `DANGEROUS_PATTERNS` — no new coordinate/keystroke heuristic was added, per explicit instruction to stay conservative here.
6. **`SelfReflectionEngine`** (`jarvis/planner/reflection.py`): Case D (`ABORT`, not `RETRY`) now also matches `"confirmation"`, `"xác nhận"`, and the `"safety_gate_"` prefix (previously only the exact string `"safety_gate_rejected"` — `"safety_gate_expired"` fell through to blind `RETRY` before this change, a small pre-existing gap fixed incidentally). Prevents a gated/expired/rejected/mismatched high-risk action from causing a retry storm of fresh confirmation requests.
7. **`jarvis/core/app.py`**: one line added — `self.dispatcher.set_safety_interceptor(self.safety_interceptor)` right after `self.safety_interceptor` is constructed — so the planner, the dispatcher, and (transitively, via `vision_click_ui`/`vision_type_ui`) `GUIActor` all resolve confirmation tokens against one shared `SafetyGate` instance. No other change to `app.py`; `_handle_planner_execute_task`'s existing `mode` string logic and the intent-routing dispatch call were **not** changed — they did not need to be, since gating is now enforced deterministically regardless of what mode string is passed.

### Files changed

- `jarvis/planner/safety_interceptor.py` — `is_high_risk()` (new, generalized), `SYSTEM_POWER_ACTION_NAMES`/`SYSTEM_POWER_DESTRUCTIVE_SUBACTIONS`, `gate()`/`verify()` (new binding layer), `_consumed_tokens`/`_verify_lock`.
- `jarvis/core/dispatcher.py` — `_evaluate_safety_gate()` (new), `safety_interceptor` constructor param + `set_safety_interceptor()`, `confirmation_token` param on both `dispatch_action()`/`dispatch_action_async()`.
- `jarvis/planner/engine.py` — `execute_plan()`'s interception condition and interpolation timing restructured; `execute_step()` forwards `confirmation_token`.
- `jarvis/planner/reflection.py` — Case D match list extended.
- `jarvis/core/app.py` — one line wiring `set_safety_interceptor()`.
- `tests/unit/test_action_dispatcher_safety.py` — **new file**, 15 deterministic regression tests.

No other tracked file is part of this change set. `jarvis/sandbox/*` and `jarvis/audio/wake_word.py` were not touched.

### Validation results (this session, local Windows)

Targeted (new file):
```text
python -m pytest tests/unit/test_action_dispatcher_safety.py -v --timeout=60 --tb=short
15 passed, 4 subtests passed in 0.73s
```

Planner + ShellAssistant (existing tests most likely to regress from this change):
```text
python -m pytest tests/unit/test_react_planner.py tests/unit/test_shell_assistant.py -v --timeout=60 --tb=short
56 passed in 1.25s
```

All other test files independently confirmed to exercise `ActionDispatcher` (`test_adversarial_r1_r2_r5_stress.py`, `test_app_integration.py`, `test_background_workers.py`, `test_gesture_detector.py`, `test_hud_telemetry_and_memory.py`, `test_llm_engine.py`, `test_plugins_m2.py`, `test_skill_synthesis.py`, `test_ui_dashboard.py`): exit code 0, no failures.

Full `tests/unit/`:
```text
python -m pytest tests/unit/ -q --timeout=120 --tb=short
exit 0, no failures
```
Exact collected count (`pytest --collect-only -q`, summed per-file — this repo's pytest config does not print a final grand-total summary line, confirmed pre-existing in earlier sessions too): **736**. This branch's baseline, after PR #8 (+30) and PR #9 (+40) on top of the earlier 651, is 651+30+40 = **721**; 736 − 721 = exactly the 15 new tests in `test_action_dispatcher_safety.py`. No regressions.

Static analysis:
```text
ruff check jarvis/planner/safety_interceptor.py jarvis/core/dispatcher.py jarvis/planner/engine.py jarvis/planner/reflection.py jarvis/core/app.py tests/unit/test_action_dispatcher_safety.py
All checks passed!

ruff check jarvis tests scripts/build_installer.py
Found 3 errors -- all in tests/integration/test_sandbox_os_boundaries.py and tests/unit/test_zalo_bot.py, both PRE-EXISTING on the merged main baseline (unrelated to this change; already documented in section 0B above).

mypy jarvis
Success: no issues found in 157 source files
```
`py_compile` on all 5 changed source files + the new test file: exit 0.
`git diff --check`: exit 0.

### Known limitations / confirmed follow-ups

- **The full "user says yes → original action automatically re-executes" voice/UX loop is not built.** `_handle_safety_gate_confirm()` only flips `SafetyGate` status to `CONFIRMED`; nothing in `app.py` today automatically re-dispatches the original gated action with the resulting token. A caller (including the existing voice/text command pipeline) must explicitly call `dispatch_action(action_name, payload, confirmation_token=token)` again with the identical action_name/payload. This mirrors a pre-existing, equally-incomplete limitation already present in `ShellAssistant.execute_natural_command()`'s own gate (documented in this same file's git history) — not a regression introduced here, and not requested in scope for Phase 2.
- `IntentResult.requires_confirmation`/`confirmation_prompt` remains unread anywhere in `jarvis/`. It is no longer a safety gap (the deterministic classifier now recognizes `system_power` independently), but it is still orphaned data; wiring it in as a nicer confirmation-prompt hint (not as a security decision) would be a reasonable, small future task, not required.
- CI has not been run for this branch yet.
- `jarvis/skills/*/metadata.json` telemetry files mutated by running `tests/unit/` this session were restored (`git checkout --`) before finishing; not part of this change set.

### Recommended next task

Push this branch and open a PR into `main`. Once CI is green, consider (separately, not required) wiring `_handle_safety_gate_confirm()` to actually re-dispatch the originally-gated action, and/or surfacing `IntentResult.confirmation_prompt` as the gate's description text for a nicer spoken confirmation prompt.

---

## 0D. Biometrics Hardening: Embedding Validation, Storage Atomicity & Face-Count Ambiguity (in progress, uncommitted)

Snapshot: 2026-08-31. Branch `feat/biometrics-hardening`, based on `main`/HEAD at commit `e4bcd6d015dec2796e0f50e88b5c9f69b58bb1f7` (branch had **zero divergence** from `main` when this task started — confirmed via `git merge-base` returning the same SHA and an empty `git diff main...HEAD --stat`). Local working-tree change, **not committed, not pushed, no PR opened**. Independent of sections 0A/0B/0C — does not touch `jarvis/sandbox/*`, `jarvis/audio/wake_word.py`, `jarvis/planner/*`, `jarvis/core/dispatcher.py`, or `jarvis/core/app.py`.

### Reference used

`ageitgey/face_recognition` (MIT) was consulted as an **API/architecture reference only**: `face_locations()`/`face_encodings()`/`face_distance()`/`compare_faces()`, 128-dimensional embeddings, Euclidean distance, `tolerance` semantics (lower = stricter; upstream default `0.6` — a library default, not a security guarantee), one encoding per detected face. No upstream source was copied, no upstream repo was vendored, `face_recognition`/`dlib`/`cv2` were **not** added as a mandatory dependency (confirmed: neither appears anywhere in `pyproject.toml`, before or after this change — they are, and remain, soft-imported optionals with no declared dependency group), no model files or binary artifacts were added, and no Windows `dlib` packaging work was attempted (explicitly out of scope).

### Audit performed first (per explicit instruction, before any implementation)

Read `jarvis/vision/biometrics.py`, `jarvis/vision/__init__.py`, every test importing `BiometricsEngine`/`FaceEmbeddingStorage`/`BiometricPrivilegeGate` (`tests/test_biometrics.py`, `tests/test_adversarial_m5_2.py`, `tests/test_tier5_adversarial_sec_iot_comms_data.py`, `tests/test_e2e_scenarios.py`), `pyproject.toml` (dependency context only), and `jarvis/core/paths.py` (read-only, to understand writable-data conventions — **not modified**). Confirmed by direct code reading, not assumption:

- `enroll_face()`/`verify_frame()`/`process_surveillance_frame()` all took `encodings[0]` unconditionally with no face-count check — a multi-face frame (e.g. owner + a stranger in view) could be misclassified non-deterministically depending on extraction order.
- No embedding validation existed anywhere: a wrong-dimension, NaN/Infinity-containing, or non-numeric embedding could reach `np.linalg.norm(enrolled - cand)` uncaught, either crashing the caller or (if shapes happened to broadcast) producing a silently-trusted bogus distance.
- `FaceEmbeddingStorage.save()` wrote directly (non-atomic) — a crash mid-write could corrupt/truncate the store.
- `FaceEmbeddingStorage.add_face()`/`BiometricsEngine.enroll_face()` never surfaced a disk-write failure to the caller — a failed save still left in-process memory believing the enrollment succeeded.
- Re-enrolling the same label left a **stale duplicate embedding** in the old flat in-memory `enrolled_embeddings` list (storage on disk correctly overwrote by label, but the engine's in-memory matching list did not track by label at all) — both the old and new embedding would still match after re-enrollment.
- No label validation (type, emptiness, control characters, length) and no `tolerance` validation (negative/NaN/Infinity/string/absurdly-large values could silently broaden authentication) existed.
- The camera-mock extraction branch (`self.camera.get_face_encodings()`) was not wrapped in try/except, unlike the `face_recognition` branch — a throwing mock/backend could crash the caller uncaught.
- Confirmed via `tests/test_adversarial_m5_2.py::test_adversarial_biometrics_boundary_distances` that the existing tolerance boundary is **strict `<`** (distance exactly equal to tolerance = no match) — this is a locked contract, preserved bit-for-bit.
- Confirmed via grep that no code outside `jarvis/vision/biometrics.py` reads the `enrolled_embeddings`/`enrolled_faces` attributes directly, and that `cv2`/`face_recognition` appear nowhere in `pyproject.toml` (not even as an optional group) — both are simply soft-imported with `ImportError → None`.

### Fixes implemented (`jarvis/vision/biometrics.py` only)

1. **Single embedding-validation boundary** — `_validate_embedding()` (module-private): exactly 128 dims, numeric, all-finite, returns a fresh `float64` copy (never mutates the caller's array), never raises (returns `None` on anything malformed). A cheap pre-check on `len()` avoids materializing pathologically large arrays before shape validation. Reused at every embedding entry point: storage load, `add_face()`, and every extraction call site in `enroll_face()`/`verify_frame()`/`process_surveillance_frame()`.
2. **`_validate_label()`** — non-empty string after `strip()`, ≤128 chars, no control characters. Still used purely as a dict/JSON key, never as a filesystem path (unchanged — this was never a real risk in the existing design).
3. **`_validate_tolerance()`** — rejects NaN/Infinity/negative/non-numeric/bool/values above `MAX_SANE_TOLERANCE = 10.0` (a sanity ceiling on the configuration knob, not a claim about real embedding distance ranges), falls back to `DEFAULT_TOLERANCE = 0.60` with a logged error. Applied in `BiometricsEngine.__init__`.
4. **`FaceEmbeddingStorage._load()` hardened** — whole-file JSON parse failure or non-dict root still wipes the store to `{}` (preserves the existing test-locked contract exactly), but each entry inside an otherwise-valid dict is now validated independently (`_validate_label` + `_validate_embedding`); corrupt individual entries are skipped and logged while valid entries load normally.
5. **Atomic `save()`** — temp file + `os.replace()`; returns `bool`. A write/replace failure leaves the previously-saved file on disk completely untouched and cleans up the temp file.
6. **`add_face()` returns `bool` and rolls back on failed persistence** — validates label/embedding first, then only commits to the in-memory `enrolled_faces` dict if `save()` succeeded; on failure, restores the pre-call value (or removes the key if it was new) so memory can never claim a persisted success that didn't happen. Added `get_labeled_embeddings() -> dict[str, np.ndarray]` (new method; the old `get_embeddings() -> list[np.ndarray]` is unchanged/still present for compatibility, though nothing outside this file called it).
7. **`BiometricsEngine` now keys labeled embeddings by label** (`_labeled_embeddings: dict[str, np.ndarray]`), separate from `_unlabeled_embeddings` (the `camera.owner_encoding` case, which has no label to key on). Re-enrolling an existing label now deterministically **replaces** rather than accumulating a stale duplicate. `enrolled_embeddings` is preserved as a read-only `@property` (flat list, computed from both structures) for compatibility — confirmed via grep that nothing outside this file reads it directly.
8. **`enroll_face()`** — deterministically rejects 0 or >1 detected faces (requires exactly 1), validates label and embedding, and only updates `_labeled_embeddings` after `storage.add_face()` confirms persistence succeeded (rollback-safe).
9. **`verify_frame()`** — `bypass_mode` and the None/empty/dark-frame (`np.mean < 5.0`) checks are preserved exactly. Now fails closed deterministically on 0 or >1 faces, a malformed candidate embedding, or zero enrolled embeddings. Tolerance boundary remains strict `<`, bit-for-bit unchanged.
10. **`process_surveillance_frame()`** — a multi-face frame now returns a distinct `{"status": "ambiguous_faces", "locked": False, "distance": None}` and a malformed-embedding frame returns `{"status": "invalid_face_data", "locked": False, "distance": None}`; neither is ever classified as `"owner_verified"`. **Deliberate scope decision**: neither ambiguous state triggers the lock-workstation/Telegram side effects (unlike a genuine `"intruder_locked"` no-match) — the frame's content is genuinely unknown rather than confirmed non-owner, and inventing a new lock-triggering policy for that case was judged out of scope for this sprint (see explicit "do not expand into surveillance orchestration" instruction). The zero-enrolled-embeddings sentinel distance changed from the old magic `1.0` to `None` (no existing test asserted a specific value for that path — confirmed by grep before making the change).
11. **`_extract_encodings()`** — the camera-mock branch is now wrapped in try/except like the `face_recognition` branch; a throwing backend/mock returns `[]` instead of crashing the caller.
12. **`BiometricPrivilegeGate` was not modified** — audited for regressions only; since `verify_frame()` only became strictly harder to pass (never easier), no separate authorization change was needed there.
13. `jarvis/vision/__init__.py` **unchanged** — all three exported names (`BiometricsEngine`, `BiometricPrivilegeGate`, `FaceEmbeddingStorage`) keep identical public signatures (`verify_frame()`/`enroll_face()` still return `bool`; `process_surveillance_frame()` still returns a `dict` with a `"status"` key). `jarvis/core/paths.py` was read but not modified — `FaceEmbeddingStorage`'s inline `%LOCALAPPDATA%` resolution logic was left exactly as-is (migrating it to `jarvis.core.paths.data_path()` was judged out of scope for an embedding/storage-integrity hardening sprint).

### Files changed

- `jarvis/vision/biometrics.py` — see above.
- `tests/unit/test_biometrics_hardening.py` — **new file**, 49 deterministic tests, synthetic 128D arrays only (no real biometric data, no photos, no model files). Originally created at `tests/test_biometrics_hardening.py` (outside `tests/unit/`, so it would not have run in CI, which only runs `tests/unit/`); moved to its final `tests/unit/` location before commit `dcbe797` — no duplicate file remains at the old path.

No other tracked file is part of this change set (confirmed via `git status` — see Known limitations for one unrelated pre-existing telemetry side effect).

### Validation results (this session, local Windows)

Targeted (new file, at its final `tests/unit/` location):
```text
python -m pytest tests/unit/test_biometrics_hardening.py -v --timeout=60 --tb=short
49 passed in 0.45s
```

Existing biometrics-touching test files, compared bit-for-bit against baseline via `git stash`:
```text
python -m pytest tests/test_biometrics.py tests/test_adversarial_m5_2.py \
  tests/test_tier5_adversarial_sec_iot_comms_data.py tests/test_e2e_scenarios.py \
  -v --timeout=60 --tb=short
3 failed, 45 passed, 9 errors
```
All 12 failures/errors reproduced identically on the pre-change baseline (`git stash` + rerun): 6 `ModuleNotFoundError: No module named 'cv2'` in `test_biometrics.py` (the `mock_camera_feed` fixture does `monkeypatch.setattr("cv2.VideoCapture", ...)`, which imports the target module first regardless of `raising=False` — `cv2` is genuinely not installed in this environment), 3 identical in `test_e2e_scenarios.py`, plus 2 pre-existing nmap/tshark CLI-capture bugs and 1 pre-existing `DiscordBotController.summarize_channel` `AttributeError` in `test_tier5_...` — all unrelated to biometrics or to this change. **Zero regressions.**

Full `tests/unit/` (rerun after moving the test file into `tests/unit/`, with collection counts verified against a `git stash` baseline):
```text
python -m pytest tests/unit/ --collect-only -q --timeout=120
python -m pytest tests/unit/ -q --timeout=120 --tb=short
```
- Baseline collection (`git stash`, file not yet present in `tests/unit/`): **736**.
- Feature-branch collection (`tests/unit/test_biometrics_hardening.py` present): **785**.
- Delta: **+49** — exactly the number of new biometrics-hardening tests, confirming the file is now collected by the same command CI runs.
- All 49 biometrics-hardening tests: **passed**.
- Exactly the documented pre-existing baseline of 9 failures: 8 in `tests/unit/test_mobile_bridge.py` + 1 in `tests/unit/test_proactive_engine.py::test_health_monitor_multiple_simultaneous_breaches` — confirmed identical before/after via `git stash`. **Zero new failures.** (This repo's pytest config prints no final grand-total summary line — confirmed pre-existing, consistent with section 0C's note.)
- **Post-merge correction (added when merging `main` into `feat/gesture-data-reference-hardening`, which pulled this section in unmodified from `main`)**: the "9 known pre-existing failures" above reflects `main` at `e4bcd6d`, the exact base this branch never diverged from — **before** the separate `fix/ci-baseline` branch fixed both root causes (`jarvis/comms/mobile_bridge.py`'s dangling transfer-log path; the stale hardcoded thresholds in the proactive-engine test) and merged into `main`. This is a historical record of what this branch observed at the time; it is not being rewritten. **Actual post-merge validation** (see section 0-PRE above for the full command/output): `tests/unit/` now collects **837** and all **837 pass, 0 failed** — the 9 failures are genuinely fixed, confirmed by an actual test run, not assumed.
- **Correction**: an earlier draft of this section stated "no test in `tests/unit/` touches `jarvis/vision/biometrics.py`". That was only true while the new test file still lived at `tests/test_biometrics_hardening.py` (outside `tests/unit/`, so it would not have run in CI). The file was moved to `tests/unit/test_biometrics_hardening.py` before commit `dcbe797`, so as of this snapshot **49 tests inside `tests/unit/` do exercise `jarvis/vision/biometrics.py`**, and CI (which runs `python -m pytest tests/unit/`) now covers them.

Static analysis:
```text
ruff check jarvis/vision/biometrics.py tests/unit/test_biometrics_hardening.py
All checks passed!

mypy jarvis
```
`jarvis/vision/biometrics.py` has zero mypy errors. Repo-wide `ruff check jarvis tests scripts/build_installer.py` (9 errors) and `mypy jarvis` (28 errors, 8 files) were confirmed **identical to baseline** via `git stash` — none of the flagged files are touched by this change (`tests/unit/test_zalo_bot.py` import-sort, plus `night_shift.py`/`macro_recorder`/`auto_updater.py`/`smart_home/discovery.py`/`mobile_bridge.py`/`tray.py`/`gui_actor.py`/`cli.py` for mypy).

`py_compile jarvis/vision/biometrics.py tests/unit/test_biometrics_hardening.py`: exit 0. `git diff --check`: exit 0.

**Note on test file location**: the test file was originally authored at `tests/test_biometrics_hardening.py`, outside `tests/unit/` — since CI runs only `python -m pytest tests/unit/`, those 49 tests would not have executed in CI at that location. It was moved to `tests/unit/test_biometrics_hardening.py` before commit `dcbe797` (plain filesystem move — the file was untracked at the time, no `git mv` needed, no duplicate left behind). CI has still not been run for this branch; the numbers above are local-run results, not a CI claim.

### Known limitations / explicitly not claimed

- No claim of spoofing resistance, liveness detection, or anti-spoofing. Tolerance `0.6` is a library default, not an identity guarantee. Windows support for `face_recognition`/`dlib` was not validated (no install/packaging attempted — explicitly out of scope).
- `jarvis/skills/*/metadata.json` (9 files) were mutated by running the test suite this session (skill-registry invocation-count/timestamp telemetry, same pre-existing side effect documented in section 0A/0C). Restoring them via `git checkout --` was **blocked by the tool's own safety classifier** (a discard-uncommitted-work-style command) this session — unlike prior sessions, it was not possible to restore them programmatically here. They remain uncommitted/unrestored; the user should run `git checkout -- jarvis/skills/*/metadata.json` manually before committing if desired.
- CI has not been run for this branch. Not committed, not pushed, no PR opened.
- `FaceEmbeddingStorage`'s AppData path-resolution logic duplicates (rather than reuses) `jarvis/core/paths.py`'s conventions; left unchanged as out-of-scope for this sprint.
- The `_labeled_embeddings`/`_unlabeled_embeddings` split and the `enrolled_embeddings` property are an internal representation change; verified via grep that nothing outside `biometrics.py` reads `enrolled_embeddings` directly, so this is not considered a breaking change, but any future external caller should be aware it is now a computed property, not a plain list attribute.

### Recommended next task

Push this branch and open a PR into `main` once the user reviews the diff. CI has not been exercised for this change. No other biometrics work (e.g. liveness detection, OS-level camera permission hardening, actual `face_recognition`/`dlib` Windows packaging) was in scope and none is recommended as an immediate follow-up beyond what the user explicitly requests next.

---

## 1. Current state summary

> **Historical note**: despite the section title, this is an **older v4.0.1-era snapshot**
> (predates even the v4.1.0 sync referenced in section `0A`), kept for historical continuity.
> For the actual current state of `main`, see **section `0` — Current Checkpoint** at the top
> of this file. This section's figures (662 passed, v4.0.1 tag, etc.) are not being rewritten.

JARVIS is currently at source version **4.1.0** and has completed a 13-round deep Adversarial Technical Audit, establishing true OS Kernel-level sandboxing (Windows MIC + Job Object) and empirical hardware benchmarking.

Current source baseline:
- Package version: `4.1.0`
- Python metadata: `>=3.10`
- Main CI Python: `3.13`
- Release Python: `3.13`
- CLI entry point: `jarvis.__main__:main`
- GUI entry point: `jarvis.__main__:main_tray`
- Validated baseline: **662 passed** (647 unit tests + 15 adversarial integration tests)
- Primary Security Boundaries: OS Kernel MIC (`TokenIntegrityLevel = LOW`) & Windows Job Object (`ActiveProcessLimit = 1`)
- Documentation Standards: [`docs/TECHNICAL_AUDIT_REPORT.md`](docs/TECHNICAL_AUDIT_REPORT.md) & [`docs/SECURITY_ARCHITECTURE.md`](docs/SECURITY_ARCHITECTURE.md)

Repository:
- `Duong-Phuoc-Hung/JARVIS`
- default branch: `main`

## 2. Current Git snapshot

Current `main` when this file was prepared:

```text
971404945cbc1f9631549a7268befe7ff079946c  Update CHANGELOG.md
6369b22...                              Update README.md
b88accac75941e1debbe8739dc08fe7f8b69ee20  Merge PR #6 - Fix PyInstaller Windows release build
18f770d...                              fix: repair PyInstaller Windows release build
```

Published annotated tag:

```text
v4.0.1
  -> b88accac75941e1debbe8739dc08fe7f8b69ee20
```

`main` is ahead of the v4.0.1 release commit by documentation edits.
That is acceptable. Do not move the already-published tag just to include documentation-only changes.

Before future work:

```powershell
git status
git branch --show-current
git log --oneline -5
git fetch origin
```

## 3. v4.0.1 release status

Release status: **SUCCESS / PUBLISHED**

GitHub Actions:
- workflow: `JARVIS Release — Build & Publish`
- successful release run: run #4
- release source commit: `b88acca...`

Published release:
- `JARVIS v4.0.1`
- not draft
- not prerelease

Important Windows release asset:
- `JARVIS_v4.0.1_windows_x64.zip`
- GitHub asset size observed: `75,759,045` bytes

The release successfully passed:
- dependency installation;
- unit tests before build;
- PyInstaller build;
- archive creation;
- artifact upload;
- GitHub Release publication.

The release body still has stale cosmetic prose referring to `633 passed`.
Do not re-run/re-tag solely for this text issue.

## 4. CI state

Workflow:
- `.github/workflows/ci.yml`

Jobs:
1. Syntax Check
2. Unit Tests
3. Import Validation
4. Pipeline Summary

Environment:
```text
windows-latest
Python 3.13
JARVIS_HEADLESS=1
JARVIS_MOCK_AUDIO=1
PYTHONIOENCODING=utf-8
```

Validated unit baseline:
```text
tests/unit/: 647 passed
46 subtests
0 failed
```

Preferred local validation:

```powershell
python -m pytest tests/unit/ -q --timeout=60 --tb=short
```

Known stale CI label:
```text
Run 633 tests
```

This is only display text. Actual suite currently has 647 passing unit tests.

Important scope:
The v4.0.1 changelog explicitly does NOT claim the entire `tests/` tree is green.
Non-CI test sets may have pre-existing failures from:
- optional dependencies not installed in CI, such as `cv2`;
- unfinished or never-implemented capabilities;
- adversarial/challenger stress tests;
- biometrics;
- e2e scenarios.

Future agents must distinguish:

```text
CI baseline == tests/unit/
```

from:

```text
all tests under tests/
```

## 5. Static-analysis state

The stabilization pass established:
- Ruff clean for `jarvis/` + `tests/`.
- `scripts/build_installer.py` clean.
- mypy issues in audited runtime code fixed.
- changed modules validated with `py_compile`.

Known unrelated full-repo issues existed in:
- `build_exe.py`
- `create_shortcuts.py`
- `health_check_report.py`

Those were treated as pre-existing/out-of-scope during the PyInstaller fix.

Do not claim `ruff .` is globally clean unless re-run and it actually passes.

## 6. Packaging / PyInstaller state

### Original release failure

The release workflow reached PyInstaller and failed:

```text
ERROR: script '.../JARVIS/main.py' not found
```

Root cause:
`scripts/build_installer.py` generated a spec with:

```python
Analysis(["main.py"], ...)
```

but the repository has no supported root-level `main.py`.

Actual application entry point:
```text
jarvis/__main__.py
```

Matching package metadata:

```toml
[project.scripts]
jarvis = "jarvis.__main__:main"
```

### Additional latent packaging problems discovered and fixed

1. Generated spec could reference missing `assets/` unconditionally.
2. `JARVIS.spec` was generated only if absent, allowing stale wrong specs to be reused.
3. `tkinter` was excluded even though `jarvis.ui.overlay` and `jarvis.skills.clipboard` import it at module level. A produced executable could crash on startup.

### Current repaired behavior

`scripts/build_installer.py` now:
- uses real `jarvis/__main__.py`;
- regenerates spec so stale entry points do not persist;
- uses robust repository-rooted paths;
- conditionally handles optional data paths;
- keeps `tkinter`;
- builds `dist/JARVIS.exe`.

Actual local proof:

```text
dist/JARVIS.exe exists
79,431,668 bytes (~75.8 MB)
```

Executable was smoke-launched with:

```text
JARVIS_HEADLESS=1
JARVIS_MOCK_AUDIO=1
```

and stayed running for 5 seconds without startup crash.

Release build command:

```powershell
python scripts/build_installer.py --exe-only --skip-tests
```

Generated artifacts intentionally ignored:

```text
/build/
/dist/
*.spec
```

Non-blocking build warning observed:

```text
Hidden import "tzdata" not found
```

## 7. v4.0.1 stabilization fixes completed

### 7.1 Build and dependencies

Completed:
- repaired corrupted `requirements.txt` content that could break `pip install -r requirements.txt`;
- repaired invalid build backend to:

```toml
build-backend = "setuptools.build_meta"
```

### 7.2 Telegram integration

Files involved:
- `jarvis/agent/graph.py`
- `jarvis/workers/notification_hub.py`

Fixed:
- references to nonexistent `TelegramController`;
- wrong `send_message` calling convention/signature.

### 7.3 LLM intent routing

Files involved:
- `jarvis/agent/graph.py`
- `jarvis/comms/zalo.py`

Fixed:
- references to nonexistent `IntentRouter`.

### 7.4 Windows autostart

File:
- `jarvis/platform/windows.py`

Implemented APIs used by CLI:
- `set_autostart`
- `get_autostart_status`

### 7.5 Windows volume control

File:
- `jarvis/automation/control.py`

Fixed incorrect source/usage of `CLSCTX_ALL` that affected volume get/set/mute.

### 7.6 Core app API mismatches

File:
- `jarvis/core/app.py`

Fixed stale/incorrect API and signatures including:
- wrong enum member;
- missing required argument;
- stale skill-synthesis call;
- stale form-fill call;
- duplicate/redundant lookups.

### 7.7 Plugin registration

File:
- `jarvis/core/plugin.py`

Fixed:
- duplicate `stop_all()` definition shadowing another;
- `register_plugin()` returning `None` instead of stable bool in some paths.

### 7.8 Discord/Zalo skill listing

Files:
- `jarvis/comms/discord.py`
- `jarvis/comms/zalo.py`

Fixed `SkillMetadata` dataclass being accessed like a dictionary.

### 7.9 Morning briefing crypto lookup

Area:
- `jarvis/skills/briefing`

Fixed call to a nonexistent crypto-price method.

### 7.10 Visual verifier

File:
- `jarvis/vision/visual_verifier.py`

Fixed result construction from unresolved `None` image bytes; uses computed fallback values.

### 7.11 Always-on overlay

File:
- `jarvis/ui/overlay.py`

Added missing `show()` method used by `toggle()`.

### 7.12 Battery telemetry — first layer

File:
- `jarvis/ui/overlay.py`

`_safe_probe_battery()` now:
- validates percentage range;
- treats invalid sentinel percentage as unavailable (`None`);
- preserves AC/charging state.

Regression coverage added for:
- valid battery percentage;
- invalid sentinel;
- no battery.

### 7.13 Battery telemetry — Windows/Python version-independent fix

Second release failure revealed:
- Python 3.11 `ctypes.wintypes.BYTE` behaved as signed `c_byte`;
- Python 3.12+ behavior is unsigned;
- Windows `GetSystemPowerStatus` unknown percentage is `0xFF` / `255`;
- under signed representation this can appear as `-1`.

Final fix:
- explicit unsigned byte semantics for `BatteryLifePercent`;
- validate `0 <= percentage <= 100`;
- treat both `-1` and `255` as unknown;
- shared validation across WinAPI and psutil paths;
- preserve charging state.

Focused regression tests covered valid `0`, `42`, `100`; invalid `-1`, `101`, `255`; and mocked WinAPI behavior.

### 7.14 TTS mock/headless playback

Original GitHub runner problem:
cached WAV playback still attempted physical audio despite:

```text
JARVIS_MOCK_AUDIO=1
```

Fixed:
- mock mode bypasses physical playback;
- synthesis/cache validation remains.

This removed CI dependence on real audio hardware.

## 8. Important release/PR history

The stabilization/release sequence matters because one accidental revert created confusing history.

### PR #1
Broad CA/CI audit + runtime fixes.

Notable commits:
- `281e5ab` — runtime fixes from strict audit
- `03fcc1a` — Ruff test lint fixes
- `75a4dac` — build backend fix
- `7060592` — changelog docs
- `9b1a6a6` — mock-audio TTS playback fix

PR #1 merged; main CI passed.

### First release failure
Failure:
```text
test_safe_probe_functions
battery = -1
assert 0 <= bat <= 100
```

Initial telemetry validation:
- branch `fix-release-battery-telemetry`
- `aaddba0`
- `b050862`
- PR #2 merged

### Second release failure
Same visible test failed again.
Deeper cause: WinAPI signed/unsigned sentinel behavior across Python versions.

Final sentinel/release-parity work:
- `270b271` — Windows battery sentinel fix
- `428bc59` — release Python 3.13 parity
- `c660b9a` — v4.0.1 release notes
- branch `fix-release-battery-sentinel-py313`
- PR #3 merged

### Accidental revert
PR #4:
```text
Revert "Fix release battery sentinel py313"
```
accidentally removed PR #3 fixes from `main`.

### Restore
Branch:
```text
restore-release-fixes
```

Commit:
```text
b8820a3 Reapply "Fix release battery sentinel py313"
```

PR #5 restored fixes.
Merge:
```text
7a9bdd1
```

### PyInstaller failure
After tests passed, release failed at:

```text
Build JARVIS.exe
ERROR: script '.../main.py' not found
```

Branch:
```text
fix-pyinstaller-release-build
```

Commit:
```text
18f770d fix: repair PyInstaller Windows release build
```

PR #6 merged:
```text
b88acca
```

`v4.0.1` was then pointed to `b88acca`, and release workflow run #4 succeeded.

## 9. Architecture and feature inventory

Historical `PROJECT.md` describes a broad autonomous architecture. Current code areas include:

### Application/core
- `jarvis/__main__.py`
- `jarvis/cli.py`
- `jarvis/core/`

### Agent/planning
- `jarvis/agent/`
- `jarvis/planner/`

Purpose:
- ReAct behavior;
- task DAG/planning;
- self-reflection/safety/workflow coordination.

### Background workers
- `jarvis/workers/`

Includes:
- night shift;
- notification hub;
- auto updater;
- background task lifecycle.

### Self-coding / sandbox / skills
- `jarvis/sandbox/`
- `jarvis/skills/`

Includes:
- constrained execution;
- skill registry;
- skill synthesis;
- RAG/search;
- browser/updater and other built-ins.

### Browser automation
- `jarvis/browser/`

Historically described as Playwright/CDP/HTTP/mock multi-tier behavior.

### Computer-use / vision
- `jarvis/vision/`
- `jarvis/automation/gui_actor.py`

Includes:
- coordinate grounding;
- visual verification;
- GUI interaction.

### Windows/desktop automation
- `jarvis/automation/`
- `jarvis/platform/`

Includes:
- OS control;
- volume;
- autostart;
- desktop interaction.

### UI
- `jarvis/ui/overlay.py`

Always-on HUD/overlay.

### Memory
- `jarvis/memory/`

Includes:
- SQLite state/history;
- semantic/vector/RAG memory.

### Communications
- `jarvis/comms/`

Channels:
- Telegram
- Zalo
- Discord
- mobile bridge

### Audio / speech
- `jarvis/audio/`
- `jarvis/stt/`
- `jarvis/tts/`

Includes:
- VAD/full duplex/audio effects;
- speech-to-text;
- TTS/cache/playback.

### Plugins
- `jarvis/plugins/`

External plugin loading/SDK.

### Build/release
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `scripts/build_installer.py`
- `installer/setup.iss`
- `pyproject.toml`

## 10. Historical milestone documentation caution

`PROJECT.md` says M1-M6 are DONE and includes older test expectations such as:

```text
921+ baseline
>=951 total
```

Do NOT treat that as current test truth.

Current verified CI unit truth:

```text
647 passed in tests/unit/
```

`PROJECT.md` is useful for architecture/interface intent, but each interface must be verified against current implementation.

`.agents/**` also contains old auditor handoffs/briefings/progress. Use only for historical context.

## 11. Current documentation inconsistencies / housekeeping TODO

These are known current inconsistencies, not runtime blockers.

### README.md

Current README still includes stale top badges:

```text
tests-633 passed
version-4.0.0
```

It also contains some v4.0.0 install/config strings.

Desired current presentation:

```text
tests-647 passed
version-4.0.1
```

Do not blindly replace every historical `4.0.0`:
- historical release notes stay historical;
- update only current-version badges/examples/current docs.

### CI workflow

`.github/workflows/ci.yml` currently has:

```text
Run 633 tests
```

Better future design:
- rename generically to `Run unit tests`.

### Release workflow

`.github/workflows/release.yml` release body hardcodes:

```text
Tests: 633 passed
```

Better:
- derive test count from JUnit output, or
- use generic wording such as `Unit test suite passed`.

### Published release v4.0.1

Release page was created with stale display prose for test count.
Artifact itself is valid.
Editing release prose does not require moving tag or rebuilding.

### PROJECT.md

Contains older test-count/milestone claims.
If treated as historical design, leave historical context.
If converted to live architecture docs, reconcile deliberately.

## 12. README / CHANGELOG state

`CHANGELOG.md` now has a Vietnamese v4.0.1 section covering:
- build/dependency fixes;
- runtime fixes;
- battery fixes;
- TTS mock fix;
- Ruff/mypy cleanup;
- `647 passed`;
- Python 3.13 CI/release parity.

`README.md` was edited after release merge, but some top-level version/test badges remain stale as above.

## 13. Current pyproject.toml truth

Important fields:

```toml
[build-system]
requires = ["setuptools>=72", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "jarvis-assistant"
version = "4.0.1"
requires-python = ">=3.10"

[project.scripts]
jarvis = "jarvis.__main__:main"

[project.gui-scripts]
jarvis-tray = "jarvis.__main__:main_tray"
```

Dependency families include:
- Google Generative AI
- dotenv
- numpy
- Pillow
- requests
- psutil
- pyperclip
- pystray
- keyboard
- python-telegram-bot

Optional groups:
- `audio`
- `windows`
- `offline`
- `browser`
- `notifications`
- `dev`
- `all`

Ruff targets Python 3.10 compatibility.
mypy is non-strict and ignores missing optional imports.

## 14. Release workflow truth

`.github/workflows/release.yml`:
- triggers on `v*.*.*`;
- `contents: write`;
- Windows runner;
- Python 3.13;
- headless/mock-audio env;
- installs dependencies;
- runs unit tests;
- runs:

```powershell
python scripts/build_installer.py --exe-only --skip-tests
```

- obtains `dist/JARVIS.exe`;
- creates:
  `JARVIS_v<version>_windows_x64.zip`;
- uploads artifact;
- publishes GitHub Release through `softprops/action-gh-release`.

Prerelease tags containing `alpha`, `beta`, or `rc` are marked prerelease.

## 15. Known non-blocking / deferred concerns

1. Full non-CI test tree is not green.
2. Optional dependencies may be absent by environment.
3. Some utility scripts have old lint/static issues.
4. README/workflow hardcoded test/version prose needs cleanup.
5. `PROJECT.md` historical test counts conflict with current CI truth.
6. Inno Setup installer path was not the critical proof in the successful PyInstaller-only local test; standalone `.exe` path is proven.
7. Release executable is currently unsigned unless future code-signing is added.
8. Optional browser/vision/audio packages should not be treated as core failures unless the feature requires them.

## 16. Recommended next development workflow

For a new feature:

```powershell
git switch main
git pull origin main
git switch -c feature/<short-name>
```

Then in a fresh Claude Code session:

```text
Read CLAUDE.md and docs/PROJECT_STATE.md first.
Inspect the current repository state and relevant implementation.
Do not modify code until you can explain the existing architecture and the acceptance criteria.
```

During implementation:
1. Add/modify focused unit tests.
2. Run targeted tests.
3. Run `tests/unit/`.
4. Run Ruff/mypy/py_compile for touched code.
5. If build/runtime changes, exercise actual runtime/build path.
6. Review diff.
7. Commit on feature branch.
8. Push and PR to main.
9. Wait for CI.
10. Merge.
11. Pull main.
12. Update this file if state materially changed.

## 17. Handoff template for future sessions

At the end of each major feature/fix, update these fields:

```md
### Latest work
- Branch:
- Commits:
- PR:
- Main merge SHA:

### What changed
- ...

### Validation
- Targeted tests:
- tests/unit:
- Ruff:
- mypy:
- py_compile:
- Runtime/build proof:

### Known limitations
- ...

### Next recommended task
- ...
```

This file is durable cross-session memory.
Verbose terminal logs, repeated debugging attempts, and superseded hypotheses should stay out.
