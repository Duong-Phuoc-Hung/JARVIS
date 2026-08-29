# JARVIS — PROJECT_STATE.md

> Durable current-state handoff for future sessions.
> Snapshot: 2026-08-30.
> Always verify Git state and current code before relying on this snapshot.

## 0. Phase 1 — Wake Word Reliability Hardening (in progress, uncommitted)

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
