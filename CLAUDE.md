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
- Current source version: `4.0.1`
- Declared Python: `>=3.10`
- Main CI / release Python: `3.13`
- Console entry point: `jarvis = "jarvis.__main__:main"`
- GUI entry point: `jarvis-tray = "jarvis.__main__:main_tray"`

Repository:
- `Duong-Phuoc-Hung/JARVIS`
- Default branch: `main`

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

## 4. Current Git/release baseline

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
