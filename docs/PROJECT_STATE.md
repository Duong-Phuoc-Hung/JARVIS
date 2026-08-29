# JARVIS — PROJECT_STATE.md

> Durable current-state handoff for future Claude Code sessions.
> Snapshot: 2026-08-29.
> Always verify Git state and current code before relying on this snapshot.

## 1. Current state summary

JARVIS is currently at source version **4.0.1** and has completed a substantial CA/CI, runtime-stability, Windows telemetry, TTS/headless, and PyInstaller release-build stabilization pass.

The v4.0.1 Windows release pipeline has successfully produced and published a standalone Windows artifact.

Current source baseline:
- Package version: `4.0.1`
- Python metadata: `>=3.10`
- Main CI Python: `3.13`
- Release Python: `3.13`
- CLI entry point: `jarvis.__main__:main`
- GUI entry point: `jarvis.__main__:main_tray`
- CI unit baseline: **647 passed**
- Full `tests/` tree is NOT claimed green.

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
