# CLAUDE.md — JARVIS Project Instructions

> Durable project instructions for Claude Code and coding agents.
> Read this file first, then read `docs/PROJECT_STATE.md` before non-trivial work.

## 0. CURRENT BASELINE — READ THIS FIRST

This section is the single most current "what's true right now" summary. Where it
disagrees with any other paragraph below (including the "Current baseline note" and
"Release-prep note" under §1, which describe an earlier point in time), **this section
wins**. Older v4.3/v4.5 baseline paragraphs elsewhere in this file are historical unless
specifically marked otherwise.

> **Read this before trusting any SHA in this file.** This section — like every session
> before it — has repeatedly recorded "current main" as a fixed commit SHA, only for that
> claim to go stale the instant the *next* change (including a docs-only sync like this
> one) merges and advances `main` past it. That is not a one-time mistake to fix; it is a
> structural property of writing a mutable fact into a static file. **Do not repeat the
> pattern.** Any SHA recorded below is **checkpoint/historical evidence for the PR that
> produced it**, not a durable claim about what `main` points to right now. Before relying
> on "current state" for any non-trivial task: run `git fetch origin --prune`, then
> `git rev-parse origin/main`, and trust that output over anything written here.

- **Documentation state verified through PR #35** (docs-only sync, merge commit
  `399a70cc471bf35d98e1b976f8c895054d4f7524`, post-merge JARVIS CI **#162 SUCCESS** — all
  four jobs green: Syntax Check, Unit Tests, Import Validation, Pipeline Summary). This is
  the **last verified repository checkpoint before this documentation sync** — not a
  permanent "current HEAD" pointer. By the time you read this, `main` may already be ahead
  of it; verify with `git fetch`/`git rev-parse origin/main` as noted above.
- **Current development runtime:** `4.7.0` (`jarvis.__version__`, `jarvis/__init__.py`).
  Unchanged by any of the work below — this is **not** `4.7.1` and no new tag/release was
  cut. Runtime version is itself durable, stable evidence (unlike a commit SHA) — verify it
  directly with `python -c "import jarvis; print(jarvis.__version__)"` if in doubt.
- **Latest formal GitHub Release:** `v4.5.1` (unchanged; tag confirmed present in the
  repository at the PR #35 checkpoint). `v4.0.1` is no longer the latest formal release.
- **Development source/runtime (`4.7.0`) and the latest formal release (`v4.5.1`) are
  different concepts** — `main` has moved well past `v4.5.1` in CHANGELOG/runtime terms
  without a new tag/release having been cut yet. Do not describe `4.7.0` as "released" or
  `v4.5.1` as "the current source version."
- **Completed and merged, as of the PR #35 checkpoint:**
  - **PR #31** (`fix/healing-truthfulness`, merge commit `10d470237b0fe4bc295f02215b4606590d79d17e`) —
    self-healing (`jarvis/healing/terminator.py`) now reports recovery outcomes truthfully.
    See the durable "Healing truthfulness" invariant below.
  - **PR #32** (`fix/wake-word-whisper-ci`, merge commit `aaeeb53f834134bb4490147c238e82e863558caa`) —
    made the Whisper wake-word fallback test (`tests/unit/test_wake_word_p0.py`)
    deterministic across environments with/without `faster-whisper` installed. **Test-only
    change — no production wake-word behavior was modified.** See the durable
    "Optional-dependency test determinism" invariant below.
  - **PR #34** (`fix/dispatch-truthfulness`, feature commit
    `e99c522be808d9160a5b9c57bf9bd8ec11d3dd69`, merge commit
    `ae6d5d8ffd98f4629af951e19820bf047f9c05d7`, post-merge JARVIS CI #160 SUCCESS) —
    **central dispatch truthfulness is RESOLVED**, and the `hardware_status_query`
    compatibility alias is **RESOLVED** (same PR/commit). See the durable "Dispatch
    truthfulness" invariant below for the full contract.
  - **PR #35** (`docs/finalize-dispatch-merge-state`, feature commit
    `a344af1f7b408306d92f781f01a2fc2e5253043d`, merge commit `399a70cc471bf35d98e1b976f8c895054d4f7524`,
    post-merge JARVIS CI #162 SUCCESS) — **documentation-only** finalization of PR #34's
    merged state across all seven docs files; no code/test/config/runtime/version change.
- **`tests/unit/` evidence at the PR #34 checkpoint (`ae6d5d8...`): 1413 passed, 1 skipped,
  50 subtests passed, 0 failed.** (Prior evidence at the PR #32 checkpoint
  (`aaeeb53f8341...`): 1353 passed, 4 skipped, 50 subtests passed, 0 failures — kept here as
  historical lineage, not the current count.) PR #35 was docs-only, so this evidence is
  unchanged by it. Skip counts can vary by environment (which optional dependencies happen
  to be installed) — this is expected, not a regression signal.
- **Central dispatch truthfulness — RESOLVED via PR #34 (checkpoint commit
  `ae6d5d8ffd98f4629af951e19820bf047f9c05d7`).** `jarvis/core/dispatcher.py`'s
  `dispatch_action()`/`dispatch_action_async()` previously wrapped any normally-returning
  handler result as `success=True` unconditionally, ignoring an explicit handler-signaled
  failure (`ActionResult(success=False, ...)`, `{"success": False, ...}`,
  `{"status": "failed"/"error", ...}`); `jarvis/core/app.py`'s `process_text_command()`
  separately never re-derived its own `status_flag` from `action_result.success` after
  dispatch. Both are now fixed on `main` — see the durable "Dispatch truthfulness"
  invariant below and `CHANGELOG.md`'s entry for full detail (root cause, normalization
  contract, sync/async parity, event truthfulness, 57 focused tests, full-suite evidence).
  - **Also resolved on `main` (same PR/commit): `hardware_status_query` compatibility
    alias.** The dispatch-truthfulness fix surfaced a genuine, separate, pre-existing
    router/registration name mismatch: the LLM router (`jarvis/llm/router.py`)
    intentionally routes several hardware/status voice queries (e.g. "Báo cáo tình trạng
    hệ thống") to action name `hardware_status_query` from multiple call sites (system
    prompt examples, Vietnamese/unaccented rule fallback, status regex handling, response
    generation), but `jarvis/core/app.py` had only ever registered a dispatcher action
    named `system_status` — so dispatch correctly returned `ACTION_NOT_FOUND`, previously
    masked by the dispatch-truthfulness bug itself. Per explicit owner direction,
    `jarvis/llm/router.py` was left untouched (changing an intentional, multi-site router
    contract would be a broad change); the narrow fix is a compatibility alias in
    `jarvis/core/app.py::_register_core_actions()` — `hardware_status_query` registered
    against the **same** existing `self._handle_system_status` handler as `system_status`
    (no duplicated logic; `system_status` itself unchanged). Covered by 5 tests in
    `tests/unit/test_dispatch_truthfulness.py::TestHardwareStatusQueryAlias`.
    `tests/unit/test_integration_e2e.py::test_memory_recording_in_process_text_command`
    passes **without that test file ever being modified**.
  - **No remaining known issue from the dispatch-truthfulness task.**
- Full detail: `CHANGELOG.md`'s "Post-v4.7.0 Maintenance" section (PR #31, PR #32, PR #34,
  PR #35); `docs/PROJECT_STATE.md`'s current checkpoint; `docs/TECHNICAL_AUDIT_REPORT.md`'s
  updated audit-status entries.

### Permanent project policy: DOCUMENTATION IS PART OF DEFINITION OF DONE

**Before starting any new task, regardless of what this file says:**
```bash
git fetch origin --prune
git rev-parse origin/main
```
Do not rely on a checkpoint SHA recorded in `CLAUDE.md`/`docs/PROJECT_STATE.md`/
`CHANGELOG.md` as the actual current `main` — treat every recorded SHA in this repository's
documentation as historical evidence for the PR that produced it, never as a live pointer.
This is the fix for a recurring failure mode: a docs-only sync PR records "current main is
SHA X," that PR's own merge commit becomes the new `main`, and the recorded SHA is stale
before the PR is even reviewed. Durable current-state claims in this file (runtime version,
release version, resolved/open status of a fix) do not have this problem — only raw commit
SHAs do — so prefer "resolved via PR #N" / "documentation state verified through PR #N"
phrasing over "current main is `<SHA>`" when writing future updates to this section.

For every future non-trivial task:

**BEFORE editing:**
- Read `CLAUDE.md` (this file).
- Read `README.md`.
- Read `CHANGELOG.md`.
- Read `docs/PROJECT_STATE.md`.
- Read `docs/ROADMAP.md`.
- Read any relevant subsystem/security/audit doc (e.g. `docs/SECURITY_ARCHITECTURE.md`,
  `docs/TECHNICAL_AUDIT_REPORT.md`) for the area being touched.

**AFTER code + tests land:**
- Update `CHANGELOG.md`.
- Update `CLAUDE.md`'s durable decisions/invariants (§1A and this §0 baseline).
- Review and update `README.md`.
- Update `docs/PROJECT_STATE.md`'s current checkpoint.
- Update `docs/ROADMAP.md` / `docs/SECURITY_ARCHITECTURE.md` / `docs/TECHNICAL_AUDIT_REPORT.md`
  when the change is relevant to any of them.
- Search for stale current-state references left behind by the change (version numbers,
  status claims, "not yet fixed" language that is now fixed, etc.).

**A task is NOT complete until documentation synchronization has been reviewed** — this
applies even to fixes that look self-contained (e.g. a single-file bug fix or a test-only
change), because stale docs elsewhere in the repo actively mislead future sessions.

### Durable healing invariant (see PR #31 above)

- **Attempted kill != confirmed kill.** Calling `.terminate()`/`.kill()`
  (`jarvis/healing/terminator.py`) without it raising is never, by itself, proof a process
  actually exited — only a confirmed post-wait/return-code outcome counts as success.
- **Observed RAM recovery != fabricated RAM recovery.** `reclaimed_ram` is only ever the
  actual measured `ram_before - ram_after` delta; it is omitted (not defaulted to a made-up
  number) when RAM cannot be measured, and healing code never mutates a hardware-telemetry
  provider to manufacture a "reclaimed" value.

### Durable optional-dependency test invariant (see PR #32 above)

- Tests must **explicitly control optional-dependency availability** (e.g. patch
  `FASTER_WHISPER_AVAILABLE`/`PORCUPINE_AVAILABLE`/`VOSK_AVAILABLE`-style flags **before**
  constructing the object under test) rather than relying on whatever happens to be
  installed on the developer's or CI runner's machine. A test whose outcome silently
  depends on ambient package availability is non-deterministic across environments even
  though it looks deterministic on any one machine.

### Durable dispatch-truthfulness invariant (PR #34, merged into `main` @ `ae6d5d8ffd98f4629af951e19820bf047f9c05d7`)

- **An action handler's explicit failure must remain failure through the entire chain:**
  handler → `ActionDispatcher` (`jarvis/core/dispatcher.py`) → application response
  (`process_text_command()` in `jarvis/core/app.py`) → memory episode → interaction log →
  events (`action.post_dispatch`). No layer in this chain may upgrade an explicit failure
  into a reported success.
- **The established failure/success contracts, and only these, are recognized** (see
  `jarvis/core/dispatcher.py::_normalize_handler_outcome()`, the single shared
  normalization function used by both `dispatch_action()` and `dispatch_action_async()`):
  an `ActionResult` handler return is authoritative as-is; a dict with an explicit boolean
  `"success"` key is authoritative; a dict with `"status"` literally `"failed"` or
  `"error"` is failure. Nothing else is treated as failure.
- **Generic falsy payload != failure, unless an explicit handler contract says otherwise.**
  `0`, `""`, `[]`, `{}`, `None`, and a bare boolean `False` (no established handler in this
  repository returns a raw `True`/`False` as its entire payload — booleans only ever appear
  nested inside an explicit `"success"` key) all remain ordinary successful data. Custom
  domain-specific status strings that are neither `"failed"` nor `"error"` literally (e.g.
  `"skipped"`, `"tts_unavailable"`, `"overlay_unavailable"`, `"healthy"`) are likewise left
  as success — there is no established repository-wide contract for them, and guessing
  would misclassify genuine successful payloads. Do not add generic falsiness-based failure
  detection (`if not data: failure`) to this normalization; extend the established-contract
  list explicitly instead, only after auditing real handler return conventions.
- **`process_text_command()` derives `status_flag` from `action_result.success`** (not from
  "no Python exception occurred") immediately after dispatch, before response-text
  selection. Failure response-text precedence: `action_result.error` →
  `action_result.data["message"]` (structured failure message) → `action_result.error_code`
  → a neutral truthful fallback (`"Không thể thực hiện lệnh."`) — never a fabricated reason,
  never the success-flavored `"Đã thực hiện lệnh: ..."` fallback for a failed action.
  `CONFIRMATION_REQUIRED` remains failure end-to-end (top-level, memory episode, and
  interaction log all report failure), and a gated high-risk handler never executes.
- **Gesture dispatch consumers** (`_on_gesture_event()`'s `triple_clap`/`clap_pause_clap`/
  generic-pattern loops) must track each dispatched action's real `ActionResult.success`
  and reflect it in the interaction log status — never hardcode `status="success"`
  regardless of outcome. The `double_clap` welcome-sequence branch is a deliberate
  exception: it logs the *launch* of an async background sequence, not per-action outcomes,
  which is a different (and honest) claim — do not "fix" it into the same per-action-outcome
  shape without a dedicated task, since it would require restructuring its threading model.
- **`hardware_status_query` is a registered compatibility alias for `system_status`**
  (`jarvis/core/app.py::_register_core_actions()`, both bound to the same
  `self._handle_system_status` — no duplicated logic), added because `jarvis/llm/router.py`
  intentionally emits `hardware_status_query` as an intent name from several call sites
  while only `system_status` had ever been registered with the dispatcher. This is an
  owner-authorized, narrow, app.py-only compatibility fix — `jarvis/llm/router.py` was
  deliberately left untouched. If a future task ever removes or renames `system_status`,
  update or remove this alias in the same change; do not let them silently diverge.

## 1. Project identity

JARVIS is a Windows-first autonomous personal AI assistant written in Python.

### Original feature concept attribution

The following original JARVIS feature concepts were designed by
**Huynh Minh Hoa ([@hoahuynh19a-crypto](https://github.com/hoahuynh19a-crypto))**:

- Voice-first assistant architecture.
- Wake-word activation.
- Speech-to-text and text-to-speech interaction.
- Local AI / Cloud AI routing.
- Hardware diagnostics and window management.
- Internal-network InfoSec auditing.
- Workflow automation.
- Data analysis.
- IoT / Home Assistant integration.
- Biometric face authentication.
- Gesture control.
- Multi-channel communications.
- Self-healing system monitoring.
- Destructive-action safety guardrails and internal-network-only InfoSec scope.

This attribution applies **only to the original feature concepts above**.
Later extensions, implementation details, security hardening, testing,
benchmarking, maintenance work, and additional features are not included in
this attribution. Implementation authorship remains tracked through Git
commits and pull requests. Repository ownership and repository URLs must not
be interpreted as authorship of these feature concepts.
Core goals:
- Voice-first Windows assistant.
- CLI/voice/Telegram/Zalo/Discord control.
- Autonomous ReAct planning and background workers.
- Browser automation, GUI/computer-use control, self-coding skills, memory/RAG, plugins, notifications, and auto-update.
- Standalone Windows packaging with PyInstaller and GitHub Actions.

Authoritative package metadata:
- Package: `jarvis-assistant`
- Package/runtime version: single-sourced from `jarvis.__version__` (a plain string literal in `jarvis/__init__.py`, **currently `"4.7.0"`** as of `main` @ `aaeeb53f834134bb4490147c238e82e863558caa` — see §0 CURRENT BASELINE above for the authoritative current state). `pyproject.toml` declares `dynamic = ["version"]` and resolves it via `[tool.setuptools.dynamic] version = {attr = "jarvis.__version__"}` — there is no second hardcoded version literal in `pyproject.toml`. See "Version metadata" in §1A below for the full classification (package vs. runtime vs. config vs. formal-release vs. CHANGELOG-milestone version). Do not bump this value without explicit release/versioning intent from the user.
- **HISTORICAL v4.5.1 RELEASE-PREP SNAPSHOT (as of 2026-09-02, branch `release/v4.5.1`, before it merged) — not current, kept for record only:** at that point in time, `jarvis.__version__` had just been bumped from `4.4.0` to `4.5.1` as explicit, user-directed release prep for the intended v4.5.1 formal release; the tag/GitHub Release did not exist yet at that moment, and `v4.0.1` was still the latest published release at that moment. **None of that is current anymore**: the `v4.5.1` tag and GitHub Release were subsequently created and published (confirmed present in the repository and confirmed an ancestor of current `main` — see §0), and `main`'s runtime has since advanced to `4.7.0` via v4.6.0/v4.7.0 and the post-v4.7.0 maintenance PRs. Do not read "currently 4.5.1" or "tag/GitHub Release not yet created" anywhere in the historical paragraphs below (§1's "Current baseline note"/"Release-prep note", and similar phrasing in `docs/PROJECT_STATE.md`) as describing anything later than that 2026-09-02 release-prep moment.
- Declared Python: `>=3.10`
- Main CI / release Python: `3.13`
- Console entry point: `jarvis = "jarvis.__main__:main"`
- GUI entry point: `jarvis-tray = "jarvis.__main__:main_tray"`

Repository:
- `Duong-Phuoc-Hung/JARVIS`
- Default branch: `main`

> **Historical — superseded by §0 CURRENT BASELINE above.** The two notes immediately
> below describe `main` and the `v4.5.1` release-prep branch as they stood on 2026-09-02
> *before* the `v4.5.1` tag/GitHub Release were actually created and before `main` advanced
> through v4.6.0/v4.7.0 and PRs #31/#32. In particular, do not trust the "tag/GitHub Release
> not yet created" language below — `v4.5.1` has since been tagged and is now the latest
> formal release per §0. Kept verbatim for historical detail; not rewritten.
>
> **Current baseline note (updated 2026-09-02, after `eval/stt-real-mic-baseline-correction` merged `origin/main` a second time, up to commit `857d729`):** `main`'s `CHANGELOG.md` development history now reaches **v4.5.0** — but `jarvis.__version__` is still `4.4.0`; **v4.5.0 did NOT bump the runtime version** (confirmed: no `### Version` bump note in its CHANGELOG entry, and `jarvis/__init__.py` is unchanged since v4.4.0). This makes v4.4.0 the exception, not the rule: v4.4.0 was the first (and so far only) milestone where the CHANGELOG heading and `jarvis.__version__` moved together (`4.1.0 → 4.4.0`, commit `4bebc42`); v4.5.0 reverts to the normal pattern (every other milestone since v4.0.1 is a dev-history label that does not move the runtime version). **Always check `jarvis/__init__.py` directly — never infer the runtime version from the latest CHANGELOG heading.**
>
> v4.5.0 (commits `89e4c7d`→`29e8ade`→`1b1c847`→`442ed0f`→`857d729`) added: an E9 acoustic-echo-feedback-loop fix (`jarvis/core/app.py` — a wake-word-triggered `unknown_intent` no longer speaks "Xin lỗi", so the mic can't re-hear its own TTS and re-trigger); SecretsManager wired into 6 more production modules (`jarvis/core/app.py`, `stt/engine.py`, `vision/screen.py`, `web/weather.py`, `agent/graph.py`, `workers/notification_hub.py`); a new N=152 text-only Tier-1 routing eval (`tests/eval/routing_eval_n150.py`, Wilson-CI — separate evidence from the acoustic STT eval, see §"STT" below, do not conflate); an emoji-detection regex extended to BMP ranges; a full test-suite cleanup (~44 failures → 0, across router/subprocess/emoji/async/cv2-optional-dep/psutil/ReDoS-timing fixes, `psutil>=5.9` and `asyncio_mode = "auto"` added to `pyproject.toml`); `jarvis/utils/subprocess_utils.py`'s `run_safe()` gained `CREATE_NO_WINDOW` by default; and a new `scripts/system_diagnostic.ps1` environment-check script. It sits on top of v4.4.0 (three production bug fixes — `parse_intent(None)` crash, `WakeWordDetector` pure-tone false positive, 23 `subprocess.run(text=True)` call sites missing `encoding=` — plus Tier-1 rule_engine expansion and a now-superseded STT-eval phrase categorization change), which itself sits on v4.3.2-era and v4.3.1-era work (real-microphone STT evaluation, sandbox/security hardening, `PromptGuard`, comms rate limiting, email IMAP hardening, Secrets Manager). This paragraph describes `main`, which is unaffected by the release-prep note immediately below it — `main` itself is still at `jarvis.__version__ = "4.4.0"` until the v4.5.1 release-prep branch is merged back. `config/default_config.yaml`'s `system.version` (`1.0.0`) remains a separate, currently-unused field (see §1A), unaffected. Sections 4, 7, 9, and 10 below are **historical v4.0.1 release record**, kept for context; do not read them as describing the current `main`. Always trust `docs/PROJECT_STATE.md` and actual Git state for the current baseline.
>
> **Release-prep note (2026-09-02, branch `release/v4.5.1`, based on `main` @ `6666cd1` — PR #23 merged, post-merge CI #135 green):** PR #23 (the STT real-microphone baseline correction referenced throughout this file) is **merged**, not in progress — merge commit `6666cd15c25db4f372afcaa0b0628dee9dc5731d`. This branch bumps `jarvis.__version__` to **`4.5.1`** as explicit, user-directed release prep: **v4.5.1 is the intended next formal GitHub Release/tag**, packaging the v4.4.0/v4.5.0 CHANGELOG-milestone work above plus PR #23's STT correction into one official checkpoint. **The tag and GitHub Release have deliberately not been created yet** — until they are, `v4.0.1` remains the actual latest formal release; do not describe `v4.5.1` as published. `CHANGELOG.md` now has a `v4.5.1` section above `v4.5.0` describing exactly what ships. See `docs/PROJECT_STATE.md` §0 for the full release-prep checkpoint.

## 1A. Durable current-baseline invariants (keep current across sessions)

Durable invariants verified through the v4.3.2 checkpoint commit `6012487` (branch `docs/v4.3.2-maintenance-checkpoint`, PR #21), based on merged main `1ad5b6d` (v4.3.2-era `CHANGELOG.md` state) — first established at commit `a370633` (v4.3.1-era) and kept current through the ProactiveConfig, version-metadata, and Night Shift maintenance workstreams. Treat `6012487`/`1ad5b6d` as the state as of this writing, not as a permanently-current SHA — once PR #21 merges, `main` moves past both; always confirm via actual Git state. Full rationale and file:line citations live in the referenced subsections below — update both together if either changes.

**Safety** (see §8.3):
- LLM output alone never authorizes destructive/high-risk action execution — `SafetyGateInterceptor.is_high_risk()` is a deterministic classifier (name sets, regexes, prefix matching), never an LLM decision.
- Confirmation tokens are bound to the exact `action_name` + `parameters` they were issued for, and are one-shot-consumed (replay/mismatch fails closed with a distinct `CONFIRMATION_*` reason).
- `ActionDispatcher.bypass_security` is privilege/RBAC-only — it never bypasses the destructive-action safety gate.

**Sandbox** (see §8.2):
- `CodeInterpreterSandbox.execute_python()`'s primary, and only, production Windows execution path is `spawn_low_integrity_process()`: OS Restricted Token + Low Integrity SID + Windows Job Object (assigned before the suspended child is resumed) + scrubbed environment + AST-validated/module-restricted preamble + bounded stdout/stderr capture.
- The readiness sentinel is the retry-safety boundary: an unclassified or unproven-pre-execution bootstrap failure fails closed (never retried); only a formally-provable pre-user-code failure is retry-eligible.
- The weaker compatibility fallback path requires an explicit opt-in env var and is never auto-detected from CI environment signals.
- `spawn_appcontainer_process()` (zero-network AppContainer) is real and real-OS-tested, but is **not** currently `execute_python()`'s backend — do not imply production Python execution has AppContainer network isolation.

**Prompt / comms security**:
- `PromptGuard` sanitizes untrusted content before it reaches an LLM prompt; live callers include browser (`cdp_controller.py`, `scraper.py`), `email_imap.py`, and `skills/screen_context`.
- Telegram/Discord/Zalo/Mobile Bridge each fail-close on an empty user/sender allowlist and each enforce `TokenBucketRateLimiter.acquire()` per inbound message; `email_imap.py` layers sender allowlist + subject-injection regex filter + fail-close HTML strip + `PromptGuard` + a hard body-length cap, but has no rate limiter of its own.
- The secrets manager (`jarvis/security/secrets.py`) wraps Windows Credential Manager via `keyring`; reads fall back to env vars, but writes fail closed (never silently persist plaintext) when keyring is unavailable.

**STT**:
- `FasterWhisperSTT.transcribe()` applies 4 hallucination guards (`condition_on_previous_text=False`, `no_speech_threshold=0.6`, `log_prob_threshold=-1.0`, `compression_ratio_threshold=2.4`) plus an RMS/length post-filter.
- The real-microphone eval dataset (`tests/eval/audio/`, `docs/eval/stt_eval_results.json`/`stt_eval_summaries.json`) is the preferred evidence for recognition quality — keep it distinct from (a) the real-CUDA-hardware-but-synthetic-audio throughput benchmark in `docs/benchmark_results.md` §1, and (b) the explicitly `[MOCK]`-tagged historical adapter figures in that doc's §2. Never cite (a) or (b) as a claim about speech-recognition accuracy — only the real-microphone eval measures that. Misrouting holds flat at ~2.2% across models/conditions and drops to 0% above a confidence threshold — see `docs/PROJECT_STATE.md` section 0 for the current numbers.
- **Corrected 2026-09-02 (`docs/eval/stt_eval_failure_decomposition.md`, branch `eval/stt-real-mic-baseline-correction`): the historical 66–82% "silent_failure_rate" is an end-to-end abstention rate, not a pure recognition-failure rate.** The historical 3-way taxonomy's `SILENT_FAILURE` bucket collapsed two distinct outcomes: `STT_EMPTY` (transcript truly empty) and `ROUTER_ABSTAIN` (transcript non-empty, but the Tier-1 rule-engine found no keyword match). Of the 134 historical `SILENT_FAILURE` rows across the full 180-row real-microphone dataset (90 recordings × `small`/`large-v3`), only **3** were `STT_EMPTY` — the other **131** were `ROUTER_ABSTAIN`. Do not describe this rate as measuring "STT recognition failure" alone; it is dominated by non-empty transcripts that didn't match a keyword, which is consistent with either poor transcription quality or an overly strict Tier-1 matcher — the decomposition alone does not distinguish those two causes (see AUDIT_METHODOLOGY.md's causal-attribution rule). `tests/eval/failure_decomposition.py::classify_outcome()` is the single source for this corrected 4-way taxonomy (`CORRECT`/`MISROUTED`/`STT_EMPTY`/`ROUTER_ABSTAIN`); `tests/eval/stt_intent_eval.py` now uses it directly for new eval runs, and also gained an explicit `--backend {direct,production}` flag (`production` calls `FasterWhisperSTT.transcribe()` itself, not a reimplementation) plus a single-sourced phrase manifest (`tests/eval/phrase_manifest.py`) fixing a real drift where the evaluator's own phrase list had gone stale/ASCII-only relative to what `tests/eval/record_test_set.py` actually recorded. No production threshold, router behavior, or historical committed evidence file was changed by this correction.
- **`tests/eval/routing_eval_n150.py`** (added by `main`'s v4.5.0 work, distinct from the acoustic STT eval above) is a **text-only** Tier-1 `rule_engine` routing-accuracy eval (N=152 utterances, no audio, no STT model, Wilson-95%-CI reported) — it answers "given a correctly-transcribed sentence, does the router pick the right action?", not "does the real mic→STT→router pipeline work end to end?". Do not cite its numbers as acoustic/STT evidence, and do not conflate its CORRECT/MISROUTED/SILENT_FAILURE labels with the 4-way `CORRECT`/`MISROUTED`/`STT_EMPTY`/`ROUTER_ABSTAIN` taxonomy above — they're two different evals answering two different questions.
- **Known cross-eval ambiguity, documented not resolved**: all 4 historical `MISROUTED` rows in `docs/eval/stt_eval_results.json` are the same case — `intent_gt="open_app"`, `phrase="variant_3"` ("mở spotify") — which the Tier-1 router routes to `action_name="spotify"`. `tests/eval/failure_decomposition.py::EXPECTED_ACTIONS["open_app"]` deliberately still excludes `"spotify"`, so these 4 rows stay `MISROUTED` rather than being silently reclassified `CORRECT` to match `main`'s own (separate, text-eval-only) taxonomy fix that moved this phrase to `music_play`. See the merge-note comments in `tests/eval/stt_intent_eval.py` (near `BACKENDS`) and `tests/eval/failure_decomposition.py` (at `EXPECTED_ACTIONS`) for the full reasoning — changing this would alter historical evidence without new acoustic data.

**Skills** (see §8.7):
- `SkillRegistry.invoke_skill()` no longer rewrites packaged `metadata.json` on every invocation — telemetry persists to a separate atomic `SkillTelemetryStore`, not the manifest.
- Two skill-manifest schema families ("jarvis_builtin_system" vs "JARVIS Core Team") still coexist unmigrated; `jarvis/skills/synthesizer.py` still writes fresh manifests via the telemetry-including `to_dict()` rather than `to_manifest_dict()` — a known, not-yet-fixed inconsistency, out of scope unless a task specifically targets it.

**Proactive config**:
- `ProactiveConfig.from_dict()` (`jarvis/proactive/engine.py`) must keep sourcing its fallback values from a fresh `cls()`/`ProactiveConfig()` instance (see the `_defaults = cls()` pattern in `from_dict()`), never from duplicated numeric constants. Hardcoding fallback numbers a second time is exactly how the health-monitor thresholds (`health_interval_s`/`cpu_threshold`/`ram_threshold`/`disk_min_free_gb`/`temp_threshold_c`/`battery_min_percent`/`health_cooldown_s`) previously drifted out of sync with the dataclass defaults — fixed; do not reintroduce a second source of truth for these values.

**Version metadata** (six distinct concepts — do not conflate them; see `tests/unit/test_version_metadata.py`, `tests/unit/test_build_installer_version.py`, `tests/unit/test_ui_dashboard.py`, and `tests/integration/test_package_version_build.py` for the locking regression coverage):
1. **Package/distribution version** (what `pyproject.toml`/wheel metadata report) — `dynamic = ["version"]` in `[project]`, resolved via `[tool.setuptools.dynamic] version = {attr = "jarvis.__version__"}`. No literal `version = "..."` may reappear in `[project]`.
2. **Runtime version** (`jarvis.__version__`) — the single canonical numeric literal, a plain top-level string assignment in `jarvis/__init__.py`. **Keep it a literal, not an import** — `jarvis/workers/auto_updater.py::get_current_version()` and `scripts/health_check_report.py::get_version()` both locate it by scanning that file's raw source text for a `"__version__ ="` line, not by importing `jarvis`; moving it behind `from jarvis._version import __version__` (or similar) would silently break both. Direct consumers: `jarvis/cli.py` (`--version` flag and health-check banner), `jarvis/ui/dashboard.py` (both the embedded HTML display and the `/api/status` `"version"` field — imported as `from jarvis import __version__ as _jarvis_version`; the HTML is substituted via a literal `.replace("{{JARVIS_VERSION}}", _jarvis_version)`, deliberately **not** `.format()`/an f-string, since the document is full of literal CSS/JS `{ }` braces that must not be touched), `scripts/build_installer.py::_get_canonical_version()` (a lightweight raw-text reader mirroring the auto-updater/health-check pattern — deliberately does not `import jarvis`, to avoid needing jarvis's runtime dependencies installed just for a build-tool script), and `tests/test_cli.py`/`tests/unit/test_version_metadata.py`.
3. **Config `system.version`** (`config/default_config.yaml`) — confirmed by repo-wide audit (2026-09-01) to have **zero production consumers**; `jarvis/core/config.py` has no special handling for it and no other `jarvis/` module reads the dot-notation key `"system.version"`. Kept only for backward compatibility with any config file that already sets it; explicitly **not** required to equal `jarvis.__version__`, and not to be reinterpreted as a config-schema-version field without real evidence of that semantic (none currently exists). Regression coverage is behavioral (`ConfigManager.get()`/`.set()` round-trip + independence from `jarvis.__version__`), not a brittle "no file may ever contain this exact text" source-text scan.
4. **Formal release version** — Git tags / GitHub Releases. Latest formal release is `v4.0.1`. `.github/workflows/release.yml` derives its own version string purely from the pushed tag name (`github.ref_name`, stripped of the leading `v`) — independent of `pyproject.toml`/`jarvis.__version__` — used only for the release archive filename and release notes text, not injected back into the package.
5. **CHANGELOG development-milestone headings** (e.g. "v4.3.1") — development-history labels only, not formal releases. Do not describe a CHANGELOG milestone as "the latest release."
6. **README display** — must keep these distinct: source/runtime version, latest formal release, and CHANGELOG development-history state are shown as three separate labeled pieces of information, not one ambiguous "version" badge.
7. **Windows Inno Setup installer** (`installer/setup.iss`) — `AppVersion` (which drives `[Setup] AppVersion`, `OutputBaseFilename`/installer filename, and the `[Registry]` `Version` value) has **no hardcoded fallback**; `setup.iss` requires it via `#ifndef AppVersion` / `#error` and it must be supplied externally as an ISCC preprocessor define. `scripts/build_installer.py::build_installer()` supplies it automatically (`ISCC.exe /DAppVersion=<jarvis.__version__> setup.iss`) via `_get_canonical_version()`. A manual `ISCC.exe setup.iss` invocation with no `/DAppVersion=` now fails clearly instead of silently building with a stale literal.

No file in the repository declares a second hardcoded numeric package/application-version literal outside the single canonical `jarvis.__version__` source — the historical `installer/setup.iss` `#define AppVersion "4.1.0"` and `jarvis/ui/dashboard.py`'s hardcoded `"version": "1.0.0"` were both confirmed real application-version displays (not independent schema/protocol/component versions) and fixed to derive from `jarvis.__version__`, per items 2 and 7 above.

**Night Shift** (`jarvis/workers/night_shift.py`; see `docs/night_shift_audit.md` for the full corrected audit, `tests/unit/test_night_planner.py` for the locking regression tests):
- `NightShiftTask.scheduled_time` defaults to `"23:00"`; `NightShiftWorker.add_task()` accepts any caller-supplied `"HH:MM"` string; `_schedule_task()` schedules for that time today (or tomorrow if it has already passed) with **no time-of-day range check anywhere in the code** — there is no 02:00–05:00 (or any other) enforced execution window. Do not describe Night Shift as running in a fixed overnight window without checking this file first.
- `NightShiftTask.report_time` (default `"07:00"`) is **stored task metadata only** — confirmed by repo-wide grep, it is never read by `_schedule_task()` or anywhere else in the module. Do not describe it as controlling when the report is sent.
- Step types are a mix of real and placeholder behavior — do not describe all step types as equally implemented:
  - Real, sandboxed: `calculate`/`compute` and `analyze`/`analysis`/`code`/`script` route through `CodeInterpreterSandbox.execute_python()` (same Restricted-Token/Low-Integrity backend documented in §8.2 — not AppContainer).
  - Real, but *not* sandboxed: `save_file` writes directly from the host JARVIS process via plain `Path.write_text()` — the sandbox's directory-allowlisting preamble does not apply to it.
  - Placeholder (canned confirmation string, no real external work): `web_search` (no search API call, no `PromptGuard` — the module doesn't import either), `notify` (no comms-channel delivery), the per-step `generate_report` type (no synthesis — the real Markdown report comes from the separate `NightShiftWorker.generate_report(task)` method, called once at the end of `execute_task()`), and any other/unrecognized step type.
- `_send_morning_report()`'s previous Telegram-delivery docstring ("Send report via Telegram if configured") was stale and has been corrected (2026-09-01) — both the docstring and the implementation now describe local Markdown persistence only. **No Telegram/comms delivery is implemented today.** Do not describe report delivery as reaching Telegram or any other channel.

## 2. Startup procedure for every new Claude Code session

Before editing:

1. Read this file.
2. Read `docs/PROJECT_STATE.md`.
3. Inspect actual Git state:
   - `git status`
   - `git branch --show-current`
   - `git log --oneline -5`
   - `git tag --points-at HEAD`
4. Read relevant source and tests.
5. Do not trust documentation over current code/tests when they disagree.

Source-of-truth priority:
1. Current source + Git state (`git log`, `git status`, actual code).
2. Executed/externally-verified CI or test evidence for the exact commit in question (e.g. a GitHub Actions run number tied to a specific SHA).
3. `docs/PROJECT_STATE.md`'s current-checkpoint section (see its own internal "Section 0" convention — only the top checkpoint is current; everything below it is preserved historical record, not a description of `main` today).
4. `CHANGELOG.md`.
5. `pyproject.toml`, workflow files, `README.md`, `PROJECT.md`, `.agents/**` — useful for structure/config, but test-count strings in particular are known to drift and should not be trusted as current-state evidence over 1-4 above. (`pyproject.toml`'s version is no longer a separate literal to drift — see "Version metadata" in §1A.)

Some historical docs are stale. `jarvis.__version__`/`pyproject.toml` do not automatically track `CHANGELOG.md`'s development-milestone headings (currently `v4.7.0`, plus a "Post-v4.7.0 Maintenance" section that does not bump the runtime version — see §0 CURRENT BASELINE) or the latest formal GitHub Release (currently `v4.5.1`, published — see §0) — these are three distinct concepts, not one drifting number; see "Version metadata" in §1A. (Historically, `v4.5.1` was itself a deliberate exception where the package/runtime version and the intended formal-release tag were made to converge by explicit user intent, the same way `v4.4.0` had before it — that release has since actually been tagged and published, which is why it is now the current latest formal release; this convergence pattern does not change the general rule that the three concepts normally drift independently.) Do not silently "bump" any of them as a side effect of an unrelated task; only change version strings when the user gives explicit release/versioning intent.

## 3. Git safety rules

This repository is shared. Avoid direct pushes to `main`.

Normal workflow:
1. Update `main`.
2. Create focused feature/fix branch.
3. Make minimal coherent change.
4. Validate.
5. Review `git diff`.
6. Commit locally.
7. Push feature branch.
8. Open PR to `main`.
9. Merge only after CI green.
10. Pull `main`.

Do not:
- force-push shared `main`;
- rewrite published history without explicit approval;
- use GitHub Revert unless the intent is truly to remove that change;
- move/recreate a published release tag casually;
- commit generated build output or local diagnostic reports.

Generated artifacts that stay untracked:
- `/build/`
- `/dist/`
- `*.spec`
- local `reports/` diagnostics unless explicitly required.

For work after v4.0.1, prefer a new semantic version (`v4.0.2`, `v4.1.0`, etc.) instead of moving the already-published `v4.0.1`.

## 4. Historical v4.0.1 Git/release baseline

> This section describes the state as of the v4.0.1 release only. `main` has since advanced through v4.1.0 to the current v4.4.0 (see the baseline note in section 1) and further. Kept for historical context; not the current baseline.

Snapshot: 2026-08-29.

At snapshot time:
- Current `main`: `971404945cbc1f9631549a7268befe7ff079946c`
  - `Update CHANGELOG.md`
- Previous docs commit: `6369b22` (`Update README.md`)
- Release/build-fix merge: `b88accac75941e1debbe8739dc08fe7f8b69ee20`
  - PR #6: `Fix PyInstaller Windows release build`
- Annotated tag `v4.0.1` points to `b88acca...`.
- GitHub Release `JARVIS v4.0.1` is published successfully.
- Windows asset exists: `JARVIS_v4.0.1_windows_x64.zip`.
- Release workflow run #4 completed successfully.

`main` is ahead of the v4.0.1 tag by documentation-only commits. This is expected. Do not retag v4.0.1 just to include docs.

## 5. CI baseline

**Newest checkpoint CI baseline** — commit `6012487441dc03bdb78aa8d5538adf32e7547c08` (the v4.3.2 documentation checkpoint commit, PR #21), GitHub Actions CI run #121, externally verified: **conclusion `success`**, all four jobs passed (Syntax Check, Unit Tests, Import Validation, Pipeline Summary). Exact collected/passed/skipped/failed counts for run #121 were not independently pulled from that run's logs — do not invent them.

**Pre-checkpoint merged-main baseline** — commit `1ad5b6d246d86ad2cb3af40840b13dd576041815` (v4.3.2-era, merge of PR #20, the base this checkpoint branched from), GitHub Actions CI run #120, externally verified: **conclusion `success`**, all four jobs passed. Exact counts for run #120 likewise not pulled from its logs. The most recent **locally**-verified full `tests/unit/` evidence (from the Night Shift reality-sync work merged in PR #20, run on that branch before merge into `1ad5b6d` — labeled LOCAL, not either CI run's own count): 1008 collected, 1008 passed, 0 failed.

**Historical baseline (a370633-era, superseded — kept for context only, do not cite as current):** CI run #108: 993 collected, 990 passed, 3 skipped, 0 failed, all four jobs green.

Workflow: `.github/workflows/ci.yml`

Environment:
- `windows-latest`
- Python `3.13`
- `JARVIS_HEADLESS=1`
- `JARVIS_MOCK_AUDIO=1`
- `PYTHONIOENCODING=utf-8`
- Unit Tests job only: `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1` (explicit, narrow opt-in for a known GitHub-hosted-runner Restricted Token bootstrap incompatibility — see §8.2. Does not validate Low Integrity isolation end-to-end on that runner; production code never reads this from CI auto-detection.)

Jobs:
- Syntax Check
- Unit Tests
- Import Validation
- Pipeline Summary

Preferred unit command:

```powershell
python -m pytest tests/unit/ -q --timeout=60 --tb=short
```

Known cosmetic inconsistency (still present, non-blocking):
- CI step is still named `Run 633 tests`.
- Actual current collected count is well above 633 (see the current/historical baselines above), not 633.

**Historical baseline (v4.0.1-era, superseded — kept for context only, do not cite as current):**
- `tests/unit/`: 647 passed, 46 subtests, 0 failed.

Do not claim the entire `tests/` tree is green. Broader adversarial/challenger, biometrics and e2e suites have pre-existing failures and/or optional dependency requirements such as `cv2`.

## 6. Static-analysis baseline

Established clean baseline:
- Ruff clean for `jarvis/` + `tests/`.
- `scripts/build_installer.py` clean.
- audited runtime mypy issues fixed.
- changed modules validated with `py_compile`.

Do not assume `ruff .` is globally clean.
Known pre-existing unrelated script issues existed in:
- `build_exe.py`
- `create_shortcuts.py`
- `health_check_report.py`

Suggested checks:

```powershell
ruff check jarvis tests scripts/build_installer.py
mypy jarvis
python -m pytest tests/unit/ -q --timeout=60 --tb=short
```

## 7. Packaging and release rules

Release workflow:
- `.github/workflows/release.yml`
- Trigger: tags matching `v*.*.*`
- Python `3.13`
- Tests before build
- PyInstaller creates `dist/JARVIS.exe`

Real app entry point:
- `jarvis/__main__.py`

Never create a fake root `main.py` merely for PyInstaller.

Release build command:

```powershell
python scripts/build_installer.py --exe-only --skip-tests
```

The repaired build must preserve:
- real `jarvis/__main__.py` entry point;
- generated/re-generated spec so stale specs cannot retain old paths;
- repository-rooted paths;
- optional/missing data directories handled safely;
- `tkinter` NOT excluded because JARVIS UI imports it;
- verify `dist/JARVIS.exe` actually exists and is non-empty;
- `/build/`, `/dist/`, `*.spec` remain ignored.

v4.0.1 local proof:
- `dist/JARVIS.exe` built successfully.
- `79,431,668` bytes (~75.8 MB).
- smoke-launched for 5 seconds with headless/mock-audio settings.
- GitHub release build later succeeded.

Known non-blocking build warning:
- `Hidden import "tzdata" not found`

Known release-description cosmetic issue:
- `.github/workflows/release.yml` still hardcodes `Tests: 633 passed`.
- Fix prose/dynamic count in future; do not rebuild/re-tag v4.0.1 solely for this.

## 8. Architecture map

Major areas:

- `jarvis/__main__.py` — module/packaging entry point.
- `jarvis/cli.py` — CLI lifecycle and health-check entry.
- `jarvis/core/` — application wiring/lifecycle/plugins/dispatch.
- `jarvis/agent/` — ReAct agent graph.
- `jarvis/planner/` — DAG planning, reflection, safety.
- `jarvis/workers/` — background workers, night shift, notifications, updater.
- `jarvis/sandbox/` — constrained Python/PowerShell execution.
- `jarvis/skills/` — skills, registry, synthesis, RAG, browser/updater skills.
- `jarvis/browser/` — browser/CDP/Playwright-oriented automation and fallbacks.
- `jarvis/vision/` — computer-use grounding and visual verification.
- `jarvis/automation/` — GUI actor and Windows desktop automation.
- `jarvis/ui/` — always-on overlay/HUD.
- `jarvis/memory/` — SQLite + vector/RAG memory.
- `jarvis/comms/` — Telegram, Discord, Zalo, mobile bridge.
- `jarvis/audio/`, `jarvis/stt/`, `jarvis/tts/` — audio, STT, TTS.
- `jarvis/plugins/` — plugin loader/SDK.
- `jarvis/platform/` — Windows platform integration/autostart.
- `tests/unit/` — authoritative CI unit suite.
- `tests/e2e/` and broader suites — useful but not the same green baseline.
- `scripts/build_installer.py` — supported Windows executable build path.
- `installer/setup.iss` — Inno Setup path when available.

Historical design docs:
- `PROJECT.md`
- `ORIGINAL_REQUEST.md`
- `.agents/**`

Use them for context, not as current truth.

### 8.1 Wake word backend architecture (`jarvis/audio/wake_word.py`)

`WakeWordDetector` is a two-tier cascade: an optional Tier 1 local engine (Vosk, OpenWakeWord, or Porcupine — first one available/configured wins, checked in that order in `_init_tier1()`), falling back to the zero-dependency `AcousticSpectralDetector` (Tier 2) whenever Tier 1 is absent, unavailable, initialization-failed, or permanently degraded. This cascade only runs at all while the detector itself is enabled — a disabled `WakeWordDetector` short-circuits in `feed_audio_block()` and performs no detection through either tier.

Porcupine lifecycle/runtime contract (verified against the upstream `pvporcupine` Python API staged locally at `.references/porcupine/binding/python/` and not committed — see `docs/PROJECT_STATE.md`). The staged upstream's own `setup.py` identifies it as `pvporcupine==4.0.3`; the `pyproject.toml` optional dependency constraint (`>=4.0.3,<5`) is pinned to match that audited major version exactly — do not widen it to include 3.x without independently re-auditing that API surface first:
- `pvporcupine.create(access_key=..., keywords=[...], sensitivities=[...])` returns an engine exposing `.sample_rate`, `.frame_length`, `.process(pcm)`, `.delete()`. Treat `.sample_rate`/`.frame_length` as authoritative — do not assume they equal `target_sample_rate` (16000) even though that is true in practice today.
- `.process()` requires **exactly** `frame_length` int16 PCM samples per call (`ValueError` otherwise) and returns the matched keyword index (`>= 0`) or `-1` for no match. It advances native engine state on every call, so every complete frame must be processed in order — never skipped.
- JARVIS audio callbacks do not align to Porcupine's frame size, so `feed_audio_block()` buffers PCM through the internal `_PorcupineFrameBuffer` helper (drains every complete frame each call, carries over the remainder) rather than assuming one callback == one frame. Verified against the actual production `AudioEngine` default (`sample_rate=44100`, `block_ms=40` → 1764 raw samples/callback → exactly 640 resampled samples/callback at `target_sample_rate=16000`).
- **Cooldown suppresses event emission, not Porcupine's audio consumption.** Porcupine is a streaming engine and must keep receiving every complete frame during the post-detection cooldown window, or its native state / the frame buffer would desync from live audio. `feed_audio_block()` always runs the Porcupine branch first, then applies the cooldown gate to decide whether to emit a `WakeWordResult`/callback. Vosk and Tier 2 keep the older behavior of being skipped entirely during cooldown — do not change that without a similar streaming-continuity justification.
- **A `porcupine.process()` runtime failure permanently degrades this detector for the rest of its lifecycle** — not just for that one block. It releases the native engine exactly once, clears the pending frame buffer, and flips `_engine_type` to `ACOUSTIC_FALLBACK`, so a known-bad native engine is never invoked again on a later callback. Tier 2 keeps working normally afterward. Do not revert this to a per-block-only fallback; a native failure that repeats on every callback is the failure mode this specifically prevents.
- Partial initialization (e.g. `pvporcupine.create()` succeeds but reading `frame_length`/`sample_rate` or constructing the frame-buffer adapter fails) releases the just-created native engine inline before falling back — `_init_tier1()` only attaches the engine/buffer to `self` after every setup step has fully succeeded, so a half-built Porcupine backend is never left both attached and un-tracked.
- `porcupine.delete()` must be called exactly once to release native resources; `WakeWordDetector._release_porcupine_native()` is the single shared helper both `shutdown()` and the runtime-failure degradation path call, so this logic cannot diverge between the two. It is idempotent (safe to call repeatedly, after a partial/failed init, or after a runtime degradation) and protected by the detector's own `RLock` — the same lock `feed_audio_block()` holds while calling `porcupine.process()`, so `delete()` can never run concurrently with an in-flight `process()` call even under multi-threaded shutdown. `jarvis/core/app.py`'s `stop()` calls `wake_word_detector.shutdown()` **after** `audio_engine.stop_stream()` (which joins the audio worker thread) — preserve that ordering if `stop()` is ever restructured; correctness does not strictly depend on the join completing in time (the shared lock covers that), but keep the ordering anyway.
- `set_enabled()` and `toggle_enabled()` share one transition helper (`_reset_stream_state_locked()`) so they cannot diverge: on an actual enabled-state change, the ring buffer and any pending partial Porcupine frame are cleared, so caller-owned PCM from before an arbitrarily long disabled gap is never concatenated with caller-owned PCM from after it. `_last_trigger_time` (the cooldown timer) is deliberately **not** reset on enable/disable — cooldown is a real-time debounce independent of the toggle, so rapid disable/enable must not bypass it. This does **not** reset the native Porcupine engine's own internal state — no reset API is used or exists in the audited upstream contract short of full reinitialization, which is intentionally out of scope; whatever detection history the native engine keeps internally may still span the disabled interval. This narrow, JARVIS-owned-buffers-only guarantee is deliberate, not a known gap — do not describe it as clearing "all" state spanning the toggle.

Policy:
- `pvporcupine` is an **optional** dependency (`pyproject.toml` `[project.optional-dependencies].wakeword`, pinned `>=4.0.3,<5`). Normal startup, and CI, must work with it absent and without a real Picovoice access key (`PORCUPINE_ACCESS_KEY` env or `config["porcupine_access_key"]`); missing either just yields the Tier 2 fallback.
- `WakeWordDetector.toggle_enabled()` (thread-safe, returns the resulting `enabled` bool) exists alongside `set_enabled()`/`is_enabled()`/the `enabled` property — `jarvis/core/app.py`'s global hotkey toggle callback depends on `toggle_enabled()` specifically; do not remove it without updating that caller.
- Wake-word tests must never require real microphone hardware or a real Picovoice access key — mock `PORCUPINE_AVAILABLE`/`pvporcupine`/`VOSK_AVAILABLE`/`OPENWAKEWORD_AVAILABLE` and use deterministic PCM (zeros/constants), not `generate_wake_word_signal()`'s random content, whenever a mock — not genuine acoustic analysis — is what determines the test's outcome. Real-microphone / spoken "Hey JARVIS" / real-AccessKey end-to-end validation is **intentionally deferred** until explicitly requested in a future task — its absence is not a Phase 1 defect.
- OpenWakeWord has the same "initialized but never processed" shape of defect as Porcupine had (confirmed by code inspection: `feed_audio_block()` only branches on `WakeWordEngineType.VOSK`), but its API is materially different (stateful internal buffering, `predict()` returns a dict of per-model scores rather than a single index, default-model loading behavior needs verification) and was **not fixed** — see `docs/PROJECT_STATE.md` for the follow-up.
### 8.2 Sandbox process isolation & CI compatibility policy (`jarvis/sandbox/security.py`, `jarvis/sandbox/interpreter.py`)

`CodeInterpreterSandbox.execute_python()` launches untrusted code under a Win32 **OS Restricted Token** (`CreateRestrictedToken` + `CreateProcessAsUserW`, Low Integrity SID `S-1-16-4096`) plus a Windows Job Object (`ActiveProcessLimit=1`, `JobMemoryLimit=256MB`) via `spawn_low_integrity_process()`. This is the primary OS-kernel security boundary — do not weaken it casually.

- **A successful `CreateProcessAsUserW` call does not mean the child is ready** — the call can report success before the child's own process/DLL initialization completes. **An NTSTATUS-shaped exit code (`is_restricted_process_bootstrap_failure()`: `STATUS_DLL_INIT_FAILED`/`STATUS_DLL_NOT_FOUND`/`STATUS_ENTRYPOINT_NOT_FOUND`) is by itself NOT proof that no user code ran** — the child could have crossed into the preamble or user code and only later hit a native DLL failure. The real retry-safety boundary is the **readiness handshake**: the injected preamble writes an internal sentinel to stdout (`strip_sandbox_ready_sentinel()`) as the very last thing it does, after every security guard is installed and before user code begins. Only "known STATUS_* code AND sentinel never observed" is raised as `RestrictedProcessBootstrapError`; "known STATUS_* code AND sentinel observed" is returned as a genuine (if unusual) execution outcome and is never retry-eligible. The sentinel is stripped from output before it reaches `SandboxResult` or structured-result parsing, on both the restricted-token and compatibility paths.
- **`RestrictedProcessBootstrapError` carries a `retry_safe` attribute** (default `False` — "unknown state => never retry") — `True` only where a failure is *formally provable* to have occurred before the child executed any instructions (pre-`CreateProcessAsUserW` failures; Job Object assignment failing on a still-suspended child; `ResumeThread` itself failing). `WaitForSingleObject`/`GetExitCodeProcess` failing **after** the child was resumed cannot be proven pre-execution, so those raise with `retry_safe=False`. **Any generic/unclassified exception is never retry-eligible regardless of `retry_safe` or the compat flag** — only a `RestrictedProcessBootstrapError` with `retry_safe=True` is ever eligible for the compatibility fallback.
- **Production default is fail-closed.** If `spawn_low_integrity_process()` raises, `execute_python()` returns a refused `SandboxResult(success=False, exit_code=-1)` — it does **not** silently retry with weaker isolation. This is a deliberate security property; do not "fix" a CI red build by removing it.
- **Compatibility fallback is explicit opt-in only**: `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1` (env var; see `SANDBOX_COMPAT_FALLBACK_ENV_VAR`/`is_compat_fallback_enabled()`). Only when set, AND only for a `RestrictedProcessBootstrapError` with `retry_safe=True`, does it fall back to the legacy Job-Object + scrubbed-environment `subprocess.Popen` path (weaker isolation — no Low Integrity token). Never auto-detected from environment signals like `GITHUB_ACTIONS`; a warning is always logged when it activates. `.github/workflows/ci.yml`'s **Unit Tests job only** sets this — this does **not** validate Low Integrity isolation end-to-end on that runner.
- **The restricted child is created `CREATE_SUSPENDED`** and is only assigned to the Job Object — then `ResumeThread`'d — while still suspended, closing the race where a child could run before the Job Object's bounds are in effect. Job Object assignment failing on a suspended child terminates it (never `ResumeThread`s) and fails closed; `ResumeThread`'s return value is checked (`0xFFFFFFFF` = failure — note `WaitForSingleObject`/`ResumeThread` need explicit `restype = wintypes.DWORD`, or ctypes' signed-int default silently breaks this exact comparison). The compatibility Popen path also fails closed (kills the process) if its own post-hoc Job Object assignment fails — it has no `CREATE_SUSPENDED` equivalent, so a brief unavoidable race window is a known, documented, weaker property of that explicit-opt-in path only.
- `SetTokenInformation(TokenIntegrityLevel)`'s return value is checked — if it fails, the child is never launched. All Win32 handles/SID allocations in `spawn_low_integrity_process()` are released exactly once via a single `finally`-backed cleanup on every exit path, including all of the above.
- `execute_powershell()` does not use this restricted-token path at all (plain `subprocess.run`) — this policy is specific to `execute_python()`.
- **Output pipe is drained concurrently by a background reader thread, not read only after the wait (fixed during the agent-execution-hardening sprint — confirmed, reproducible bug, not hypothetical).** `spawn_low_integrity_process()` previously called `WaitForSingleObject(pi.hProcess, timeout_ms)` to wait for the *entire* child process to finish before ever calling `ReadFile` on the output pipe. Windows' default anonymous pipe buffer is ~4096 bytes; once a child's cumulative unread stdout+stderr exceeded that, its `write()`/`print()` blocked forever (pipe full, nobody draining) while the parent was itself stuck in `WaitForSingleObject` waiting for a process that could never finish — a classic pipe deadlock, resolved only by hitting the caller's own timeout and then misreporting the run as "timed out" instead of "succeeded with output." Empirically bisected to exactly 4096 bytes (4000 succeeds instantly, 4096 hangs for the full timeout, up to 25s tested). **Fix**: a daemon `threading.Thread` starts draining `h_read` via a `ReadFile` loop immediately after `CreateProcessAsUserW` succeeds (while the child is still `CREATE_SUSPENDED`, before `ResumeThread`), so the pipe is never left undrained at any point the child could be writing to it. `WaitForSingleObject`/timeout/`GetExitCodeProcess` handling is **completely unchanged** — the thread only changes *when* the pipe is read, not any isolation/token/Job-Object/`retry_safe` semantics. After the child exits (normally or via `TerminateProcess` on timeout), `reader_thread.join(timeout=5.0)` bounds the wait for drainage to finish; `_cleanup()` (the shared `finally` handler covering every exit path, including early `RestrictedProcessBootstrapError` raises) also joins the reader thread (bounded 2.0s) before closing `h_read`, avoiding a `CloseHandle` race against a pending `ReadFile` on another thread. Verified: 100–50000 byte outputs now all complete in ~0.13–0.14s; regression test `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_large_stdout_does_not_deadlock` (20000 bytes). All existing sandbox tests (`test_skill_synthesis.py`, `test_adversarial_r1_r2_r5_stress.py`, `test_hud_telemetry_and_memory.py`, `test_sandbox_compat_fallback.py`, `tests/integration/test_sandbox_os_boundaries.py`) re-run clean after this change.
- **`_drain_pipe()`'s accumulation is capped at `_PIPE_READER_MAX_CAPTURE_BYTES = 1024 * 1024` (found and fixed in a follow-up pre-commit security review of the fix above).** The deadlock fix removed the *only* thing that previously bounded parent-process memory during pipe capture — the deadlock itself, which silently capped a runaway script to ~4KB before it blocked. Without an explicit cap, a long-running/verbose script (e.g. `while True: print(...)`) could make the reader thread retain unbounded data in the **JARVIS host process's own memory** for the entire timeout window (up to `MAX_PYTHON_EXEC_TIMEOUT_SECONDS=30.0` via the agent, or longer via direct `execute_python()` calls), long before `interpreter.py`'s own post-hoc `_MAX_STDOUT_CAPTURE_BYTES` truncation ever ran on the final joined string — a real resource-exhaustion regression distinct from the Job Object's `JobMemoryLimit` (which bounds the *child's* memory, not the parent's). Fix: once `captured >= _PIPE_READER_MAX_CAPTURE_BYTES`, `_drain_pipe()` keeps calling `ReadFile` in a loop (so the pipe — and thus the child — can never block again) but stops appending further bytes to `output_chunks`, discarding the excess. This constant is intentionally **not** imported from `interpreter.py`'s `_MAX_STDOUT_CAPTURE_BYTES` (would create a circular import, since `interpreter.py` imports from `security.py`) — keep the two conceptually in sync if either changes. Verified: a `while True: print('x'*100000)` loop against a 1.5s timeout still returns within bounded wall-clock time (no indefinite hang) with `len(stdout) < 2MB`, versus unbounded growth before this cap. Regression test: `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_runaway_output_does_not_grow_unbounded`.
- Also added in the same review pass: `tests/unit/test_skill_synthesis.py::TestCodeInterpreterSandbox::test_sandbox_mixed_stdout_stderr_heavy_output_does_not_deadlock`, closing a coverage gap — no prior test exercised heavy/interleaved writes to `stderr` specifically through the real sandboxed subprocess. **Correction (found via GitHub Actions CI #75, backend-specific, not universal)**: stdout and stderr share one pipe (`hStdOutput == hStdError`) only on the primary OS Restricted Token path. On the explicit-opt-in compatibility fallback path (`JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1`, used by CI when it hits the known `0xC0000142` Restricted Token bootstrap failure — see the item above this one), `subprocess.Popen` captures stdout and stderr **separately**. The test was corrected to assert only the semantic contract that holds across both paths (success, no deadlock, both payloads present somewhere in `stdout + stderr` combined) rather than assuming they are always merged into `stdout`.
- **`strip_sandbox_ready_sentinel()` handles LF, CRLF, and raw (no-line-ending) sentinel forms.** Verified directly against current source (`jarvis/sandbox/security.py::strip_sandbox_ready_sentinel()`): it strips the LF-terminated line, then explicitly also strips a CRLF-terminated form and a bare sentinel with no trailing newline. This is **not** a known limitation — a prior version of this document described an LF-only defect that no longer matches the code; do not reintroduce that claim without re-reading the function first. `jarvis/agent/tool_runtime.py::sandbox_result_to_tool_result()` still does its own defensive cleanup on the consumer side (see §8.6), which remains harmless/redundant given the source-side fix.
- **`spawn_appcontainer_process()` exists and is real, but is NOT the production `execute_python()` backend.** `jarvis/sandbox/security.py` implements a second, independent isolation primitive — a Windows AppContainer launch path with `SECURITY_CAPABILITIES`/`CapabilityCount=0` (zero network capabilities), verified in real-OS tests (the "AppContainer B2" dual-evidence test: compute succeeds, `socket.connect()` is kernel-blocked). However, `jarvis/sandbox/interpreter.py::CodeInterpreterSandbox.execute_python()` only imports and calls `spawn_low_integrity_process()` (the Restricted Token path documented above) — `spawn_appcontainer_process()` has zero callers outside `tests/integration/test_sandbox_os_boundaries.py` and `tests/e2e/test_r3_network_sandbox_e2e.py`. Do not describe production Python execution as having AppContainer network isolation; it does not, today. Wiring AppContainer in as (or alongside) the production backend is an open, unstarted follow-up — see `docs/PROJECT_STATE.md`.

### 8.3 Central destructive-action safety layer (`jarvis/core/dispatcher.py`, `jarvis/planner/safety_interceptor.py`, `jarvis/planner/engine.py`)

`ActionDispatcher.dispatch_action()`/`dispatch_action_async()` is the **primary, centralized enforcement point** for destructive/high-risk actions — for both sync and async dispatch, after the existing RBAC/privilege check and before the handler runs. Do not add a parallel, one-off confirmation check elsewhere in a new call path; extend the shared classifier instead.

- **Single authoritative classifier**: `SafetyGateInterceptor.is_high_risk(action_name, parameters, explicit_flag=...)` (generalized from the older `is_high_risk_node(TaskNode)`, now a thin wrapper over it). Checks, in order: explicit flag, `HIGH_RISK_ACTIONS` name set, deterministic `system_power`/`power_action` sub-action recognition (`shutdown`/`restart`/`reboot`/`sleep`/`poweroff`/`hibernate` — **not** `lock`), `delete_`/`remove_`/`drop_`/`truncate_`/`format_`/`destroy_` prefixes, and `DANGEROUS_PATTERNS` regexes scanned over every string found in `parameters`. **This classification is deterministic and never depends on `IntentResult.requires_confirmation`/`confirmation_prompt`** (the LLM router's per-intent flag) — that flag is orphaned data today (computed, never read) and must never become the safety decision itself if it is ever wired up later; at most it may supply UX prompt text.
- **Pending-action binding layer**: `SafetyGateInterceptor.gate(action_name, parameters)` issues a token via the existing `SafetyGate.request_confirmation()` (SafetyGate's own contract is unmodified — `ShellAssistant`'s direct, separate use of `SafetyGate` is unaffected). `SafetyGateInterceptor.verify(token, action_name, parameters)` is the only way to consume a token: it requires the token to be known, unexpired, not rejected, `status == "CONFIRMED"`, and to match the **exact** `action_name` and `parameters` it was issued for — then marks it consumed via an interceptor-local set (own lock), so it can never be reused (replay, cross-action, or modified-payload reuse all fail closed with a distinct `CONFIRMATION_*` reason code).
- **`ActionDispatcher.bypass_security` remains privilege/RBAC-only.** The destructive-action check runs unconditionally in `_evaluate_safety_gate()`, regardless of that flag — do not fold the two together.
- **Planner (`ReActTaskEngine.execute_plan()`)**: high-risk-node interception now applies **regardless of `PlanMode`** — `PlanMode.FULLY_AUTONOMOUS` (the real production default; `_handle_planner_execute_task` never requests `SAFETY_GATE`) only skips gating for nodes the shared classifier does not flag. Parameter interpolation happens before the risk check (not at dispatch time) so a gated token binds to the exact final parameters. `execute_step()` forwards `node.confirmation_token` into `dispatch_action()` so an already-planner-confirmed node isn't re-gated a second time at the dispatcher. Because gating now happens before either the custom-handler (`register_action_handler()`) or dispatcher path is chosen inside `execute_step()`, that (currently production-unused but reachable) bypass path is covered without a separate check.
- **`GUIActor` has no destructive-action logic of its own, deliberately.** Raw click coordinates/keystrokes are not reliably classifiable as destructive — do not add coordinate/keystroke heuristics there. Its two dispatcher-registered callers, `vision_click_ui`/`vision_type_ui`, are gated at that semantic boundary like any other action (their `query`/`text` string payloads are scanned by the same classifier).
- `SelfReflectionEngine.reflect()` treats any error containing `"confirmation"`, `"xác nhận"`, or `"safety_gate_"` (covers `safety_gate_rejected` and `safety_gate_expired`) as `ABORT`, not `RETRY` — a gated/expired/rejected/mismatched action must not trigger a retry storm of fresh confirmation requests.
- The full end-to-end "user says yes → the original action automatically re-executes" voice/UX loop is **not built** — `_handle_safety_gate_confirm()` only flips `SafetyGate` status to CONFIRMED; a caller must explicitly re-invoke `dispatch_action(..., confirmation_token=...)` with the identical action_name/payload. This mirrors a pre-existing, equally-incomplete limitation in `ShellAssistant`'s own gate and was not in scope to fix.

### 8.4 Biometrics embedding validation & storage integrity (`jarvis/vision/biometrics.py`)

`ageitgey/face_recognition` (MIT) was consulted as an **API/architecture reference only** for this subsystem's 128D-embedding / Euclidean-distance / `tolerance` conventions (`face_locations()`/`face_encodings()`/`face_distance()`/`compare_faces()`, one encoding per detected face, upstream default `tolerance=0.6`). No upstream source was copied, `face_recognition`/`dlib`/`cv2` remain fully optional (soft-imported, absent from `pyproject.toml` entirely, never required for tests or CI), and no biometric images/model files/real face data exist anywhere in this repo — all test embeddings are synthetic deterministic 128D arrays. See `docs/PROJECT_STATE.md` for the full audit trail.

- **Single embedding-validation boundary**: `_validate_embedding()` (module-private) is the only path any embedding — enrolled, candidate, camera-provided, or loaded from disk — is trusted through. It requires exactly 128 dimensions, numeric, all-finite (no NaN/±Infinity) values, returns a fresh `float64` copy (never aliases/mutates the caller's array), and never raises — malformed input yields `None` so every call site fails closed deterministically. Do not add a second, parallel validation path; extend this helper instead.
- **Face-count ambiguity is fail-closed everywhere.** `enroll_face()`, `verify_frame()`, and `process_surveillance_frame()` all require **exactly one** detected face; zero or more than one is rejected/treated as unverified. A multi-face surveillance frame reports a distinct `"ambiguous_faces"` status (not `"owner_verified"`, not `"intruder_locked"`) and deliberately does **not** trigger the lock-workstation/Telegram side effects — the frame's content is genuinely unknown, not confirmed to be a non-owner, and inventing a new lock-triggering policy for that case was out of scope. Do not silently take `encodings[0]` from an unchecked multi-element list anywhere in this file.
- **`FaceEmbeddingStorage` writes atomically** (temp file + `os.replace()`) and `save()`/`add_face()` return `bool`. A failed `add_face()` **rolls back the in-memory `enrolled_faces` dict** to its pre-call state — memory can never claim an enrollment succeeded when persistence actually failed. On load, a JSON-parse failure or a non-dict root still wipes the store to `{}` (a pre-existing, test-locked contract — do not change), but an individual corrupt entry inside an otherwise-valid JSON dict is now skipped while the rest of the store loads normally.
- **`BiometricsEngine` keys labeled embeddings by label** (`_labeled_embeddings: dict[str, np.ndarray]`, separate from the unlabeled `camera.owner_encoding` entry) instead of a flat list — re-enrolling an existing label deterministically **replaces** its embedding rather than accumulating a stale duplicate that would still match after re-enrollment. The public `enrolled_embeddings` list attribute is preserved as a read-only `@property` computed from both structures, for compatibility; nothing outside this file reads it directly (verified by grep) so this is safe to keep evolving internally.
- **Tolerance is validated, not trusted.** `_validate_tolerance()` rejects NaN/Infinity/negative/non-numeric/boolean/absurdly-large values (`MAX_SANE_TOLERANCE = 10.0`, a sanity ceiling on the *configuration knob*, not a claim about real embedding distance ranges) and falls back to `DEFAULT_TOLERANCE = 0.60` with a logged error — a bad config value can never silently broaden authentication. The match boundary itself remains **strict `<`** (distance exactly equal to tolerance is not a match) — this is locked in by a pre-existing adversarial test (`tests/test_adversarial_m5_2.py::test_adversarial_biometrics_boundary_distances`); do not change it to `<=`.
- Do **not** treat any of this as a security guarantee: no liveness detection, no anti-spoofing, tolerance 0.6 is a library default not an identity guarantee, and Windows support for `face_recognition`/`dlib` itself was never validated in this pass (out of scope by explicit instruction — no dlib packaging work was attempted).
- `BiometricPrivilegeGate` was **not modified** — the hardening pass only tightens `verify_frame()`'s fail-closed semantics (strictly harder to authenticate, never easier), so no separate authorization redesign was needed there.

### 8.5 Hand-gesture pipeline & Data Analysis Service facade (`jarvis/gesture/hand_*.py`, `jarvis/data/analysis_service.py`)

Added in a time-boxed reference-integration sprint (branch `feat/gesture-data-reference-hardening`). Both are additive, isolated subsystems — **not wired into `ActionDispatcher`, `app.py`, the planner, or the LLM router** in this phase; they only emit structured results/callbacks.

**Hand-gesture pipeline** — a second, independent gesture subsystem alongside the pre-existing *acoustic* clap detector (`jarvis/gesture/detector.py`, `jarvis/gesture/models.py` — unmodified, still the only subsystem wired to anything). No shared types between the two: acoustic uses `GestureType`/`GestureResult`; hand tracking uses `HandGestureType`/`HandGestureResult`, deliberately named to avoid confusion.

- `jarvis/gesture/hand_models.py` — `HandLandmarks`/`HandLandmarkPoint` are `frozen=True` dataclasses; `HandLandmarks` enforces exactly 21 points (`NUM_HAND_LANDMARKS`) at construction, raising `ValueError` otherwise. `HandGestureType`: `OPEN_PALM`, `FIST`, `SWIPE_LEFT`, `SWIPE_RIGHT`, `UNKNOWN`.
- `jarvis/gesture/hand_preprocess.py` — pure, deterministic functions with **no MediaPipe/OpenCV/camera dependency at all**, so they're directly unit-testable: `normalize_landmarks()` (translate wrist to origin, scale by max wrist-to-landmark planar distance — scale/position invariant), `classify_static_shape()` (OPEN_PALM/FIST via a wrist-relative digit-extension-ratio heuristic — a from-scratch geometric heuristic, **not** a port of any trained classifier from the `kinivi/hand-gesture-recognition-mediapipe` reference consulted for architecture only), `classify_dynamic_gesture()` (SWIPE_LEFT/SWIPE_RIGHT from net horizontal displacement over a short point-history window).
- `jarvis/gesture/hand_tracker.py`'s `HandGestureTracker` — thread-safe (own `RLock`), confidence threshold, temporal stabilization/debounce for static shapes (`stabilization_frames` identical consecutive classifications required — swipes bypass this since displacement across several frames already implies temporal consistency), post-emission cooldown (`cooldown_s`). `ingest_landmarks()` is the deterministic entry point used both internally by the optional real-camera loop and directly by tests — it never imports cv2/mediapipe. `cv2`/`mediapipe` are lazily imported at module load behind `CV2_AVAILABLE`/`MEDIAPIPE_AVAILABLE` flags (same graceful-degradation pattern as Porcupine in `jarvis/audio/wake_word.py` — see §8.1); missing either, or a webcam that won't open, sets `HandTrackerState.UNAVAILABLE` and returns `False` from `start()`, never raises. `start()`/`_capture_loop()`/`stop()`/`shutdown()` exist for real hardware use but are **not exercised by unit tests** (no webcam requirement) and have not been validated against a real camera/MediaPipe install.
- `pyproject.toml` optional extra `gestures = ["opencv-python>=4.8,<5", "mediapipe>=0.10,<1"]` — **intentionally excluded from the `all` aggregate** (mediapipe's Python 3.13 wheel support is not reliably verified; do not add it to `all` without re-auditing that first).
- No direct OS actions are performed anywhere in this subsystem; it only emits `HandGestureResult` via callbacks (`add_callback()`/`on_gesture`).

**Data Analysis Service facade** — `jarvis/data/analysis_service.py`'s `DataAnalysisService` is a thin, deterministic wrapper over the pre-existing `DataAnalyticsEngine`/`MonteCarloEngine` in `jarvis/data/stats.py` (**unmodified**), adding structured request/result models (`DataAnalysisRequest`, `DataAnalysisResult`, `AnalysisOperation`) and two safety properties `stats.py` itself doesn't have:

- **Bounded file handling**: `_check_file_bounds()` checks file existence and size against `max_file_size_bytes` (default 50MB) *before* delegating to `engine.load_csv()`/`load_xlsx()`, raising `FileTooLargeError` on an oversized file rather than reading it unbounded into memory. Unsupported file extensions raise `UnsupportedOperationError` before any parse attempt.
- **Chart specification/rendering**: `ChartSpec`/`ChartSeries` are plain, deterministic dataclasses describing a chart — fully testable with no plotting library installed. `render_chart()` lazily imports `matplotlib` with the `Agg` backend (headless-safe) only inside the render call; if matplotlib is absent or rendering fails, it returns `ChartRenderResult(rendered=False, error=...)` rather than raising. `pyproject.toml` optional extra `charts = ["matplotlib>=3.7,<4"]` **is** included in the `all` aggregate (low install risk, broad wheel support including Python 3.13) — unlike the `gestures` extra above.
- **Deliberately independent of `jarvis/llm/router.py`.** `execute()` only maps an already-structured `DataAnalysisRequest` to one of the fixed `AnalysisOperation` values (`DESCRIBE`/`CORRELATION`/`ANOMALY`/`TREND`/`MONTE_CARLO`/`CHART`) — no natural-language parsing, no `eval()`/`exec()`, no shell command generation, no LLM-generated code execution anywhere in this module. Mapping natural language onto these operations is an explicitly out-of-scope future phase.
- Architectural inspiration only came from `Sinaptik-AI/pandas-ai`'s separation of data loading / data model / analysis-agent / execution-sandbox layers — no PandasAI source, models, or enterprise code was copied, and PandasAI is not a runtime dependency anywhere in JARVIS.

### 8.6 ReActAgent execution hardening (`jarvis/agent/graph.py`, `jarvis/agent/tool_runtime.py`)

Added in the agent-execution-hardening sprint (branch `feat/agent-execution-hardening`), architecturally inspired by OpenInterpreter (current `openinterpreter/openinterpreter` project — substantially rewritten from the historical `OpenInterpreter/open-interpreter` repo referenced in older planning docs; only the general concepts of an explicit agent/execution boundary, sandboxed execution, and bounded/structured tool results were used — no upstream source copied, not vendored, not a runtime dependency). `ReActAgent` is **not wired into `ActionDispatcher`/`app.py`/the planner/the router anywhere in `jarvis/`** — confirmed by grep, before and after this sprint; it is a standalone module with zero production callers today.

- **`_tool_run_python` no longer calls a raw in-process dynamic code evaluation.** It routes through the existing, unmodified `jarvis.sandbox.interpreter.CodeInterpreterSandbox.execute_python()` — full AST validation, isolated scratch dir, OS Restricted Token isolation, timeout/resource bounds all preserved (see §8.2). User code is wrapped with a minimal epilogue (`try: print(result)\nexcept NameError: pass`) to preserve the old "top-level `result` variable becomes the tool output" convention, deliberately without using `locals()`/`globals()`/`vars()` (all rejected by the sandbox's own AST validator — using them would make the epilogue itself fail validation).
- `ReActAgent.__init__` gained an optional `sandbox: CodeInterpreterSandbox | None = None` constructor param (backward compatible, defaults to `None`); `_get_sandbox()` lazily constructs a default (`cleanup_on_exit=True`) only the first time `run_python` is actually invoked, so agents that never call it never create a `workspace/sandbox/` directory. `_tool_run_python(code, timeout_seconds=None, **kw)` gained an optional `timeout_seconds` param, always clamped to `MAX_PYTHON_EXEC_TIMEOUT_SECONDS = 30.0` regardless of what an LLM/heuristic requests.
- **`jarvis/agent/tool_runtime.py` (new module)** — a small, pure, LLM/network/hardware-free structured tool-execution contract: `ToolExecutionResult(success, output, error, metadata)`; `truncate_text()` (deterministic bounded truncation, `DEFAULT_MAX_OBSERVATION_CHARS = 4000` — deliberately much smaller than the sandbox's own internal 1MB stdout cap, which protects the sandbox's pipe, not an LLM's context budget); `normalize_tool_output()` (accepts a `ToolExecutionResult` pass-through, a legacy `{"output": ...}`-shaped dict, or any other value); `sandbox_result_to_tool_result()` (the single place a `SandboxResult` is converted for agent consumption — see the CRLF-sentinel-cleanup note in §8.2); `format_observation()` (final bounded string stored in `ThoughtStep.tool_result`).
- **`ReActAgent._act()` now routes every tool call (not just `run_python`) through `_execute_tool()` + `format_observation()`** — unknown tool names and non-dict (including `None`) `args` fail deterministically without raising; any exception from `tool.fn(**args)` is caught and converted to a failed `ToolExecutionResult`, never escaping to crash the ReAct loop; every tool's output (not just sandboxed Python) is bounded before it can reach agent history/LLM context.
- **Audited, not touched (documented limitation, not a second safety system)**: every built-in agent tool — `write_file`, `read_file`, `browser_open`, `screenshot`, `send_telegram`, `list_dir`, `git_status` — calls straight into `tool.fn(**args)`, completely bypassing `ActionDispatcher`/`SafetyGateInterceptor` (§8.3). `write_file` can overwrite any path the JARVIS process can write to, with no allowlist; `browser_open` can navigate to any URL under agent/LLM control. Wiring the full tool set through `ActionDispatcher` is a materially larger integration than this sprint's scope and was deliberately left undone rather than inventing a parallel, ad-hoc safety mechanism — do the real integration as its own focused task instead of patching around it here. `git_status` uses a fixed `subprocess.run(["git", "status", "--short"], ...)` argv (no interpolated user input, no injection risk) but still bypasses the dispatcher like the others.

### 8.7 Skill manifest / runtime telemetry separation (`jarvis/skills/models.py`, `jarvis/skills/registry.py`, `jarvis/skills/telemetry.py`, `jarvis/skills/validation.py`)

Added in the skill/plugin-hardening sprint (branch `feat/skill-plugin-hardening`), architecturally inspired by leon-ai/leon's 2.0 Developer Preview (`develop` branch) capability hierarchy (Skills → Actions → Tools → Functions) and its separation of static capability definition from runtime state — concepts only, no Leon source copied, not vendored, not a dependency. This is a partial, selective adaptation; the JARVIS skill system does **not** now implement Leon's architecture.

- **Confirmed, pre-existing bug fixed**: `SkillMetadata.to_dict()`/`.from_dict()` both silently dropped `category` and `author` despite the dataclass declaring both — every "jarvis_builtin_system"-family packaged `metadata.json` (app_launcher, briefing, calculator, clipboard, file_manager, git_assistant, note_taker, pomodoro, system_control) already lacked these keys as a direct consequence. `from_dict()` is now rewritten around deterministic coercion helpers in `jarvis/skills/validation.py` (`coerce_str`/`coerce_dict`/`coerce_optional_dict`/`coerce_str_list`/`coerce_float`/`coerce_int`): a field missing from an old manifest falls back to the dataclass default (backward compatible); a field present with the **wrong type** (e.g. `"tags": "not-a-list"`) *also* falls back to the default rather than propagating onto a typed attribute — a single malformed field can never crash discovery or produce a type-inconsistent `SkillMetadata`. `to_dict()` now emits `category`/`author`.
- **Two manifest schemas coexist on disk, deliberately left as-is**: the "jarvis_builtin_system" family (9 skills, matches `SkillMetadata.to_dict()`'s shape) and a separate "JARVIS Core Team" family (auto_updater, browser_control, macro_recorder, night_planner, rag_search, screen_context, skill_synthesizer, smart_home_discovery, sound_board — the other contributor's recent work, using `display_name`/`author`/`actions`, no telemetry fields at all). `from_dict()` must and does read both without crashing; this sprint does **not** unify or migrate either family's files.
- **Confirmed root cause of tracked `metadata.json` mutation, fixed**: `SkillRegistry.invoke_skill()` used to call `_persist_skill_metadata()` (now removed — nothing else called it) after *every* invocation, rewriting the entire packaged `<skill>/metadata.json` with fresh invocation_count/success_count/failure_count/total_latency_ms. This was not only a test artifact (`tests/unit/test_builtin_skills.py`'s fixture points `skills_dir` directly at `Path("jarvis/skills").resolve()`) — **real production usage rewrote its own installed package too**: `jarvis/core/app.py:373` constructs `SkillRegistry(skills_dir=skills_dir, ...)` with `skills_dir` defaulting to the string `"jarvis/skills"` (resolves to the packaged tree unless overridden by config), and `jarvis/comms/discord.py`/`jarvis/comms/zalo.py` construct `SkillRegistry()` with no arguments at all (same default). Fixed by introducing `jarvis/skills/telemetry.py::SkillTelemetryStore` — a separate, atomic-write (temp file + `os.replace()`), corruption-tolerant, thread-safe (`threading.Lock`) JSON store, located via `jarvis.core.paths.data_path()` (existing convention, **not modified**). `SkillRegistry.__init__` gained an optional `telemetry_store: SkillTelemetryStore | None = None` param (fully backward compatible — no caller needed to change). The default store path is **scoped by a hash of `skills_dir`**: the real packaged tree always resolves to the same persistent file across process restarts, while every test's fresh `tempfile.TemporaryDirectory()` gets a brand-new, never-colliding telemetry file automatically — this was load-bearing for test determinism (without it, `tests/unit/test_skill_synthesis.py::test_skill_invocation_and_telemetry`'s exact-count assertions would flake across repeated local runs by inheriting stale counts from a shared global store).
- **`SkillMetadata` in-memory telemetry fields and `get_metrics()` are unchanged** — `record_invocation()` still mutates the in-memory dataclass every call, exactly as before, for this process's lifetime. Only *where telemetry is durably persisted* changed, per the explicit compatibility requirement to keep the public API intact.
- **Telemetry is never silently discarded across the migration**: `SkillTelemetryStore.record_invocation(..., seed=...)` only uses `seed` the first time the store has no entry for a skill, bootstrapping from that skill's current in-memory counters (which may already reflect old counts baked into a legacy packaged `metadata.json`) instead of starting at zero — so switching a skill onto the new store is numerically continuous, never a visible reset. `SkillRegistry._hydrate_telemetry()` overlays the store's counters onto freshly-parsed static metadata at discovery time (when the store has an entry); if it has none yet, the metadata's own (possibly legacy) values are left untouched.
- **Skill-identifier safety** (`jarvis/skills/validation.py::is_safe_skill_identifier()`): a skill's declared `metadata.name` is untrusted content (it comes from a JSON file the skill's own directory owns) that used to flow unchecked into filesystem path construction (`register_skill()`'s `self.skills_dir / name`; the old `_persist_skill_metadata()`'s `f"{name}.json"`). `SkillRegistry._sanitize_declared_name()` runs **before** `SkillMetadata.from_dict()` and substitutes the filesystem-derived (guaranteed-safe) directory/file name directly into the raw parsed dict whenever the declared `"name"` is missing, the wrong type, or an unsafe string — the skill still loads, only the untrusted name is replaced, and it always falls back to *its own* correct name, never a shared placeholder (see the "wrong-typed name" fix below). `_enforce_safe_skill_name()` remains as a second, defense-in-depth check after construction. `register_skill()` independently refuses (returns `False`, logs) to register a skill whose name isn't safe, before ever constructing a path from it. `is_safe_entrypoint_identifier()` similarly gates the `getattr(module, entrypoint_function)` lookup in `_import_skill_module()`.
- **Confirmed and fixed in a follow-up pre-commit review: a wrong-TYPED `name` (not just an unsafe string) could silently collide two unrelated skills under one shared, incorrect identity.** `SkillMetadata.from_dict()` coerces a non-string `name` (e.g. `"name": 12345`) to the fixed placeholder `"unnamed_skill"` — a string that itself *passes* `is_safe_skill_identifier()`, so the post-construction override never fired, and TWO different skills with equally wrong-typed names would both resolve to the identical `"unnamed_skill"` key (the second silently dropped by duplicate-resolution, `"stealing"` the first skill's intended identity in effect). Fixed by `_sanitize_declared_name()` running on the raw dict before `from_dict()` ever sees it, so an invalid name (wrong type OR unsafe string) always resolves to *this skill's own* directory/file name, never a generic shared placeholder.
- **Malformed-JSON-per-skill behavior, stated precisely**: syntactically invalid JSON does **not** cause a skill to be skipped from discovery — it still loads, using fallback metadata derived from its directory/file name (pre-existing behavior, unchanged, now covered by a regression test). This is distinct from a **field-level** type error in an otherwise-valid manifest (e.g. `"tags": "not-a-list"`), which is coerced to that field's safe default rather than causing a crash. Neither case causes a skill to be rejected/skipped or aborts discovery of other skills — do not describe either as "manifests are rejected."
- **Manifest vs. telemetry separation, now also applied to newly-written manifests** (follow-up review): `SkillMetadata.to_dict()` is unchanged and still includes telemetry fields (used by `SkillDefinition.to_dict()` and dashboard/API introspection, which legitimately want current stats). New `to_manifest_dict()` excludes all six telemetry fields; `register_skill(save_to_disk=True)` now writes new packaged `metadata.json` files with `to_manifest_dict()`, so a freshly-registered skill's manifest never bakes in telemetry (even zero-valued). `jarvis/skills/synthesizer.py` (out of scope this sprint) still uses `to_dict()` for its own metadata.json write — manifest/telemetry separation is therefore not 100% complete at every write site, only at the one this sprint owns (`registry.py`).
- **In-memory concurrency race found and fixed** (follow-up review): `invoke_skill()`'s seed-capture + `skill_def.metadata.record_invocation()` (a non-atomic `+= 1` on a dataclass attribute shared across every caller invoking the same skill) previously ran with no lock, risking lost updates to `get_metrics()`'s in-memory counters under concurrent invocation of the same skill. Now wrapped in the registry's existing `self._lock` (RLock); the on-disk `self.telemetry.record_invocation()` call is intentionally left outside that lock since `SkillTelemetryStore` has its own independent lock and always increments from whatever is currently on disk (never from a stale `seed`, which only ever bootstraps a skill's very first store entry) — the two locks never need to be unified for correctness. Regression test: 40 concurrent `invoke_skill()` calls (half success/half failure) assert `invocation_count == success_count + failure_count` holds in both `get_metrics()` and the telemetry store.
- **`_write_all_locked()` also catches `TypeError`/`ValueError`** around `json.dumps()`, not just `OSError` (follow-up review) — defense-in-depth in case a non-JSON-serializable value ever ends up in the telemetry dict; not currently reachable given the codebase always casts telemetry values to `int`/`float` explicitly, but a JSON encode failure must never propagate out and interrupt a skill invocation.
- **Discovery is now deterministic**: `discover_skills()` sorts both the subdirectory scan and the standalone-`.py`-file scan by name before processing (previously relied on `Path.iterdir()`/`glob()`'s unordered results). If two different skills declare the same `metadata.name` independently of their directory names, the one processed first in sorted order wins; the later duplicate is skipped with a logged warning, never a silent overwrite. Verified for both directory-vs-directory and directory-vs-standalone-file collisions. **Not addressed, pre-existing, out of scope**: `discover_skills()` never removes an entry from `self._skills` for a skill whose directory has since been deleted from disk — a subsequent `discover_skills()` call does not reconcile stale entries. Do not describe discovery as "fully reconciled"; only its ordering and duplicate-resolution are guaranteed deterministic.
- **Direct `invoke_skill()` is intentional, coexisting design — not a bypass that was "fixed."** Traced every production caller: `jarvis/core/app.py`, `jarvis/comms/discord.py`, `jarvis/comms/zalo.py`, `jarvis/ui/dashboard.py`, and `ActionDispatcher` registration itself (`_create_dispatcher_handler()` calls `invoke_skill()` internally). Both the direct-invocation path (trusted internal callers) and the ActionDispatcher-routed path coexist by design. No second safety gate was added; direct invocation is not treated as unsafe.
- **No new dependency.** Validation in `jarvis/skills/validation.py` is plain Python type/identifier checks — deliberately not a JSON Schema framework.

## 9. Important v4.0.1 fixes already completed

Do not rediscover/revert these without evidence of regression.

### Build/dependencies
- Fixed corrupted `requirements.txt` line.
- Fixed PEP 517 backend to `setuptools.build_meta`.

### Telegram / intent routing
- Fixed nonexistent `TelegramController` references and wrong `send_message` signature.
- Fixed nonexistent `IntentRouter` references in agent/Zalo paths.

### Windows integration
- Implemented missing autostart APIs.
- Fixed Windows volume-control constant/source usage.

### Core/plugin/skills
- Repaired stale API/signature mismatches in `jarvis/core/app.py`.
- Fixed plugin `stop_all()` shadowing and registration bool behavior.
- Fixed Discord/Zalo `SkillMetadata` dataclass access.
- Fixed morning briefing crypto-price lookup.

### Vision/UI
- Fixed visual verifier fallback/result construction.
- Added missing overlay `show()` used by `toggle()`.

### Battery telemetry
- Invalid battery percentages return unavailable instead of bogus values.
- Unknown Windows sentinels `-1` and `255` are handled safely.
- Explicit unsigned byte behavior avoids Python 3.11/3.12 `ctypes.wintypes.BYTE` differences.
- Charging state is preserved when percentage is unknown.

### TTS/headless CI
- `JARVIS_MOCK_AUDIO=1` bypasses physical playback while preserving synthesis/cache validation.

### Release build
- PyInstaller uses the real entry point.
- stale spec reuse eliminated.
- missing `assets/` handled safely.
- `tkinter` kept in package.

## 10. PR/release incident history

v4.0.1 stabilization:
- PR #1 — CA/CI and runtime fixes.
- PR #2 — battery telemetry release fix.
- PR #3 — Windows battery sentinel + Python 3.13 release parity.
- PR #4 — accidental revert of PR #3.
- PR #5 — restored PR #3 changes.
- PR #6 — repaired PyInstaller Windows release build.

Important associated commits:
- `281e5ab` — runtime fixes from strict audit.
- `03fcc1a` — Ruff test lint cleanup.
- `75a4dac` — build backend fix.
- `7060592` — changelog docs.
- `9b1a6a6` — mock-audio TTS playback fix.
- `aaddba0` — first battery telemetry validation.
- `b050862` — related changelog update.
- `270b271` — Windows battery sentinel fix.
- `428bc59` — release Python 3.13 parity.
- `c660b9a` — v4.0.1 release notes.
- `b8820a3` — reapplied accidentally reverted release fixes.
- `18f770d` — repaired PyInstaller Windows release build.
- `b88acca` — PR #6 merge / release commit.

## 11. Documentation consistency rules

Current docs are not fully synchronized.

At snapshot time:
- `pyproject.toml` correctly says `4.0.1`.
- `CHANGELOG.md` has Vietnamese v4.0.1 notes and `647 passed`.
- `README.md` still contains stale top-level values including:
  - `tests-633 passed`
  - `version-4.0.0`
  - some v4.0.0 install/config examples
- `.github/workflows/ci.yml` has stale step text `Run 633 tests`.
- `.github/workflows/release.yml` has stale release prose `Tests: 633 passed`.
- `PROJECT.md` contains older 921+/951 test claims and should not be treated as the current CI baseline.

When updating version/test counts, search the repo for stale hardcoded values.
Do not rewrite historical changelog entries simply because older releases had different counts.

## 12. Environment and secrets

Never commit:
- `.env`
- API keys
- Telegram/Zalo/Discord tokens
- credentials
- logs containing secrets

When adding optional dependencies:
- keep imports graceful where practical;
- put them in the correct `pyproject.toml` optional group;
- avoid unexpectedly forcing hardware/heavy deps into CI.

## 13. Working style for future features/fixes

For each task:
1. Define concrete acceptance criteria.
2. Inspect relevant subsystem and tests.
3. Reuse existing abstractions.
4. Preserve Windows/headless behavior.
5. Add focused regression tests for real bugs.
6. Prefer mocks/injection for hardware/network behavior.
7. Avoid broad exception swallowing when narrower handling is possible.
8. Do not silence Ruff/mypy instead of fixing runtime behavior.
9. Run targeted tests, then `tests/unit/`.
10. For packaging changes, perform an actual PyInstaller build if practical.
11. Verify outputs exist before claiming success.
12. Update `docs/PROJECT_STATE.md` when project state materially changes.

## 14. Session handoff rule

Before ending a major Claude Code session, update `docs/PROJECT_STATE.md` with:
- branch/commit state;
- completed work;
- test/build evidence;
- new known limitations;
- remaining tasks;
- decisions future agents should not re-investigate.

Keep `CLAUDE.md` durable.
Put transient SHAs, current feature status, and TODOs in `docs/PROJECT_STATE.md`.
