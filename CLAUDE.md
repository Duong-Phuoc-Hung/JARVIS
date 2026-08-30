# CLAUDE.md — JARVIS Project Instructions

> Durable project instructions for Claude Code and coding agents.
> Read this file first, then read `docs/PROJECT_STATE.md` before non-trivial work.

## 1. Project identity

JARVIS is a Windows-first autonomous personal AI assistant written in Python.

Core goals:
- Voice-first Windows assistant.
- CLI/voice/Telegram/Zalo/Discord control.
- Autonomous ReAct planning and background workers.
- Browser automation, GUI/computer-use control, self-coding skills, memory/RAG, plugins, notifications, and auto-update.
- Standalone Windows packaging with PyInstaller and GitHub Actions.

Authoritative package metadata:
- Package: `jarvis-assistant`
- Current source version: `4.1.0` (previous stable was `4.0.1`; see note below)
- Current source version: `4.1.0` (previous stable was `4.0.1`; sections below referencing v4.0.1 are historical release record, kept for context — see `docs/PROJECT_STATE.md` for the current baseline)
- Declared Python: `>=3.10`
- Main CI / release Python: `3.13`
- Console entry point: `jarvis = "jarvis.__main__:main"`
- GUI entry point: `jarvis-tray = "jarvis.__main__:main_tray"`

Repository:
- `Duong-Phuoc-Hung/JARVIS`
- Default branch: `main`

> **v4.1.0 baseline note:** `main` has advanced past the v4.0.1 baseline described in sections 4/7/9/10 below (OS-level kernel sandboxing/security hardening from a separate contributor; see `CHANGELOG.md`'s v4.1.0 entry, `docs/SECURITY_ARCHITECTURE.md`, and `docs/TECHNICAL_AUDIT_REPORT.md` for that work — not reproduced here). Sections 4, 7, 9, and 10 below are **historical v4.0.1 release record**, kept for context; do not read them as describing the current `main`. Always trust `docs/PROJECT_STATE.md` and actual Git state for the current baseline.

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
1. Current source + Git state.
2. `pyproject.toml` and workflow files.
3. Executed tests/build output.
4. `docs/PROJECT_STATE.md`.
5. `CHANGELOG.md`.
6. `README.md`, `PROJECT.md`, `.agents/**` historical handoffs.

Some historical docs are stale.

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

> This section describes the state as of the v4.0.1 release only. `main` has since advanced to v4.1.0 (see the baseline note in section 1) and further. Kept for historical context; not the current baseline.

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

## 5. CI baseline (v4.0.1-era number; see `docs/PROJECT_STATE.md` for current)

Workflow: `.github/workflows/ci.yml`

Environment:
- `windows-latest`
- Python `3.13`
- `JARVIS_HEADLESS=1`
- `JARVIS_MOCK_AUDIO=1`
- `PYTHONIOENCODING=utf-8`

Jobs:
- Syntax Check
- Unit Tests
- Import Validation
- Pipeline Summary

Validated unit baseline:
- `tests/unit/`: **647 passed**
- 46 subtests
- 0 failed

Preferred unit command:

```powershell
python -m pytest tests/unit/ -q --timeout=60 --tb=short
```

Known cosmetic inconsistency:
- CI step is still named `Run 633 tests`.
- Actual current unit baseline is 647.

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
- **Separate, non-security cosmetic defect found but deliberately NOT fixed here**: `strip_sandbox_ready_sentinel()` only matches an LF-terminated sentinel line (`SENTINEL + "\n"`); a CRLF-terminated child stdout (common on Windows) means the exact-match `.replace()` never fires, leaking the raw `\x02JARVIS_SANDBOX_READY_v1\x03` control-byte marker into `SandboxResult.stdout`. Not a security issue (no secret data, just a few marker bytes) and doesn't meet the "makes integration impossible" bar the pipe deadlock did, so `jarvis/sandbox/security.py` was left unmodified for this one; `jarvis/agent/tool_runtime.py::sandbox_result_to_tool_result()` does its own defensive, CRLF-tolerant cleanup on the consumer side instead (see §8.4). If this is ever fixed at the source, make `strip_sandbox_ready_sentinel()` tolerant of both line endings.

### 8.3 Central destructive-action safety layer (`jarvis/core/dispatcher.py`, `jarvis/planner/safety_interceptor.py`, `jarvis/planner/engine.py`)

`ActionDispatcher.dispatch_action()`/`dispatch_action_async()` is the **primary, centralized enforcement point** for destructive/high-risk actions — for both sync and async dispatch, after the existing RBAC/privilege check and before the handler runs. Do not add a parallel, one-off confirmation check elsewhere in a new call path; extend the shared classifier instead.

- **Single authoritative classifier**: `SafetyGateInterceptor.is_high_risk(action_name, parameters, explicit_flag=...)` (generalized from the older `is_high_risk_node(TaskNode)`, now a thin wrapper over it). Checks, in order: explicit flag, `HIGH_RISK_ACTIONS` name set, deterministic `system_power`/`power_action` sub-action recognition (`shutdown`/`restart`/`reboot`/`sleep`/`poweroff`/`hibernate` — **not** `lock`), `delete_`/`remove_`/`drop_`/`truncate_`/`format_`/`destroy_` prefixes, and `DANGEROUS_PATTERNS` regexes scanned over every string found in `parameters`. **This classification is deterministic and never depends on `IntentResult.requires_confirmation`/`confirmation_prompt`** (the LLM router's per-intent flag) — that flag is orphaned data today (computed, never read) and must never become the safety decision itself if it is ever wired up later; at most it may supply UX prompt text.
- **Pending-action binding layer**: `SafetyGateInterceptor.gate(action_name, parameters)` issues a token via the existing `SafetyGate.request_confirmation()` (SafetyGate's own contract is unmodified — `ShellAssistant`'s direct, separate use of `SafetyGate` is unaffected). `SafetyGateInterceptor.verify(token, action_name, parameters)` is the only way to consume a token: it requires the token to be known, unexpired, not rejected, `status == "CONFIRMED"`, and to match the **exact** `action_name` and `parameters` it was issued for — then marks it consumed via an interceptor-local set (own lock), so it can never be reused (replay, cross-action, or modified-payload reuse all fail closed with a distinct `CONFIRMATION_*` reason code).
- **`ActionDispatcher.bypass_security` remains privilege/RBAC-only.** The destructive-action check runs unconditionally in `_evaluate_safety_gate()`, regardless of that flag — do not fold the two together.
- **Planner (`ReActTaskEngine.execute_plan()`)**: high-risk-node interception now applies **regardless of `PlanMode`** — `PlanMode.FULLY_AUTONOMOUS` (the real production default; `_handle_planner_execute_task` never requests `SAFETY_GATE`) only skips gating for nodes the shared classifier does not flag. Parameter interpolation happens before the risk check (not at dispatch time) so a gated token binds to the exact final parameters. `execute_step()` forwards `node.confirmation_token` into `dispatch_action()` so an already-planner-confirmed node isn't re-gated a second time at the dispatcher. Because gating now happens before either the custom-handler (`register_action_handler()`) or dispatcher path is chosen inside `execute_step()`, that (currently production-unused but reachable) bypass path is covered without a separate check.
- **`GUIActor` has no destructive-action logic of its own, deliberately.** Raw click coordinates/keystrokes are not reliably classifiable as destructive — do not add coordinate/keystroke heuristics there. Its two dispatcher-registered callers, `vision_click_ui`/`vision_type_ui`, are gated at that semantic boundary like any other action (their `query`/`text` string payloads are scanned by the same classifier).
- `SelfReflectionEngine.reflect()` treats any error containing `"confirmation"`, `"xác nhận"`, or `"safety_gate_"` (covers `safety_gate_rejected` and `safety_gate_expired`) as `ABORT`, not `RETRY` — a gated/expired/rejected/mismatched action must not trigger a retry storm of fresh confirmation requests.
- The full end-to-end "user says yes → the original action automatically re-executes" voice/UX loop is **not built** — `_handle_safety_gate_confirm()` only flips `SafetyGate` status to CONFIRMED; a caller must explicitly re-invoke `dispatch_action(..., confirmation_token=...)` with the identical action_name/payload. This mirrors a pre-existing, equally-incomplete limitation in `ShellAssistant`'s own gate and was not in scope to fix.

### 8.4 ReActAgent execution hardening (`jarvis/agent/graph.py`, `jarvis/agent/tool_runtime.py`)

Added in the agent-execution-hardening sprint (branch `feat/agent-execution-hardening`), architecturally inspired by OpenInterpreter (current `openinterpreter/openinterpreter` project — substantially rewritten from the historical `OpenInterpreter/open-interpreter` repo referenced in older planning docs; only the general concepts of an explicit agent/execution boundary, sandboxed execution, and bounded/structured tool results were used — no upstream source copied, not vendored, not a runtime dependency). `ReActAgent` is **not wired into `ActionDispatcher`/`app.py`/the planner/the router anywhere in `jarvis/`** — confirmed by grep, before and after this sprint; it is a standalone module with zero production callers today.

- **`_tool_run_python` no longer calls a raw in-process dynamic code evaluation.** It routes through the existing, unmodified `jarvis.sandbox.interpreter.CodeInterpreterSandbox.execute_python()` — full AST validation, isolated scratch dir, OS Restricted Token isolation, timeout/resource bounds all preserved (see §8.2). User code is wrapped with a minimal epilogue (`try: print(result)\nexcept NameError: pass`) to preserve the old "top-level `result` variable becomes the tool output" convention, deliberately without using `locals()`/`globals()`/`vars()` (all rejected by the sandbox's own AST validator — using them would make the epilogue itself fail validation).
- `ReActAgent.__init__` gained an optional `sandbox: CodeInterpreterSandbox | None = None` constructor param (backward compatible, defaults to `None`); `_get_sandbox()` lazily constructs a default (`cleanup_on_exit=True`) only the first time `run_python` is actually invoked, so agents that never call it never create a `workspace/sandbox/` directory. `_tool_run_python(code, timeout_seconds=None, **kw)` gained an optional `timeout_seconds` param, always clamped to `MAX_PYTHON_EXEC_TIMEOUT_SECONDS = 30.0` regardless of what an LLM/heuristic requests.
- **`jarvis/agent/tool_runtime.py` (new module)** — a small, pure, LLM/network/hardware-free structured tool-execution contract: `ToolExecutionResult(success, output, error, metadata)`; `truncate_text()` (deterministic bounded truncation, `DEFAULT_MAX_OBSERVATION_CHARS = 4000` — deliberately much smaller than the sandbox's own internal 1MB stdout cap, which protects the sandbox's pipe, not an LLM's context budget); `normalize_tool_output()` (accepts a `ToolExecutionResult` pass-through, a legacy `{"output": ...}`-shaped dict, or any other value); `sandbox_result_to_tool_result()` (the single place a `SandboxResult` is converted for agent consumption — see the CRLF-sentinel-cleanup note in §8.2); `format_observation()` (final bounded string stored in `ThoughtStep.tool_result`).
- **`ReActAgent._act()` now routes every tool call (not just `run_python`) through `_execute_tool()` + `format_observation()`** — unknown tool names and non-dict (including `None`) `args` fail deterministically without raising; any exception from `tool.fn(**args)` is caught and converted to a failed `ToolExecutionResult`, never escaping to crash the ReAct loop; every tool's output (not just sandboxed Python) is bounded before it can reach agent history/LLM context.
- **Audited, not touched (documented limitation, not a second safety system)**: every built-in agent tool — `write_file`, `read_file`, `browser_open`, `screenshot`, `send_telegram`, `list_dir`, `git_status` — calls straight into `tool.fn(**args)`, completely bypassing `ActionDispatcher`/`SafetyGateInterceptor` (§8.3). `write_file` can overwrite any path the JARVIS process can write to, with no allowlist; `browser_open` can navigate to any URL under agent/LLM control. Wiring the full tool set through `ActionDispatcher` is a materially larger integration than this sprint's scope and was deliberately left undone rather than inventing a parallel, ad-hoc safety mechanism — do the real integration as its own focused task instead of patching around it here. `git_status` uses a fixed `subprocess.run(["git", "status", "--short"], ...)` argv (no interpolated user input, no injection risk) but still bypasses the dispatcher like the others.

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
