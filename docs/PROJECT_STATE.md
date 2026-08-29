# JARVIS — PROJECT_STATE.md

> Durable current-state handoff for future sessions.
> Snapshot: 2026-08-30.
> Always verify Git state and current code before relying on this snapshot.

## 0. Windows Sandbox CI Compatibility Fix (in progress, uncommitted)

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
3. **`RestrictedProcessBootstrapError.retry_safe` (Blocker 2 fix).** Defaults `True`, but is only actually `True` where a failure is *formally provable* to have occurred before the child executed any instruction: pre-`CreateProcessAsUserW` failures, Job Object assignment failing on a still-suspended child, or `ResumeThread` itself failing (the thread was never resumed). `WaitForSingleObject`/`GetExitCodeProcess` failing **after** the child was resumed cannot be proven pre-execution, so these raise with `retry_safe=False`. **A generic/unclassified exception is never retry-eligible under any circumstance, regardless of the compat flag** — `execute_python()` only ever falls back for a `RestrictedProcessBootstrapError` with `retry_safe=True`. Replaced the now-corrected test `test_unexpected_launcher_exception_falls_back_when_explicitly_enabled` (previously enforced unsafe behavior) with `test_unexpected_launcher_exception_never_falls_back_even_when_enabled`.
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

## 1. Current state summary

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
