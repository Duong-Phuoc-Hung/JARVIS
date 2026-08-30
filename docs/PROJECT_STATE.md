# JARVIS — PROJECT_STATE.md

> Durable current-state handoff for future sessions.
> Snapshot: 2026-08-30.
> Always verify Git state and current code before relying on this snapshot.

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
