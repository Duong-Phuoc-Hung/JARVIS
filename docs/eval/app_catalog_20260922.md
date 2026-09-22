# Installed app catalog — stage 1 evidence

Date 2026-09-22; source version 5.2.1; uncommitted working tree. Existing Windows
and security patches preserved. This is a partial delivery of the approved design.

## Available path

`mở ứng dụng <exact installed name>` → existing router app_open → dispatcher →
app handler installed_only → local catalog → one exact target or explicit error.
Simple existing commands keep the previous app path; arbitrary short `mở <name>`
has not yet been integrated with the new inventory.

Sources: Windows Get-StartApps plus App Paths HKCU/HKLM, both registry views.
Only current-user-accessible inventory is in scope. The inventory is not uploaded
to an LLM. Memory cache TTL 300 seconds; manual Python refresh is available.
No disk persistence, background watcher or configuration UI is claimed.

Microsoft references:
- [Get-StartApps](https://learn.microsoft.com/en-us/powershell/module/startlayout/get-startapps)
- [App registration / App Paths](https://learn.microsoft.com/en-us/windows/win32/shell/app-registration)

## Verification

- Read-only real local discovery: 235 records (189 AppID, 46 exe), errors empty.
  These are not unique applications and are not live launch passes.
- TDD regressions cover normalized exact lookup, ambiguity, maintenance labels,
  provider failure, cache, explicit command, shared cooldown, unverified AppID
  acknowledgement, matching/nonmatching process-window PID.
- Scoped command: `.venv\Scripts\python -m pytest tests/unit/test_app_catalog.py tests/unit/test_windows_command_targets.py tests/unit/test_h07_voice_app_intents.py tests/unit/test_app_web_dedupe_stress.py tests/unit/test_computer_control.py -o addopts='' -q --tb=short --junitxml=reports/evidence/app_catalog_scoped_20260922.xml`
- Result: **90 passed, 25 subtests passed / 6.29 seconds**, exit 0.
- Full-suite diagnostic after final code: `pytest tests -o addopts='' -q --maxfail=1`
  with JUnit at `reports/evidence/app_catalog_full_20260922.xml` returned
  **182 passed, 1 failed, 23 skipped / 20.90 seconds**, exit 1. Stops at first
  failure, not an exhaustive failure count. Existing zero-sized screenshot JPEG
  failure remains in `tests/e2e/test_tiers_1_to_4.py:969` / `jarvis/vision/screen.py:230`.
- `git diff --check`: exit 0; LF/CRLF warnings only. No commit or push.
- Reviewer identified independent cooldown budgets; new cross-route test observed
  RED then passed after canonical name key fix. Read-only review also confirmed
  duplicate Notepad records across sources; deliberately not guessed away.

## Honest runtime contract

EXE launch success requires visible window for the started process PID. A process
that exits successfully may be a launcher: it is still UNVERIFIED. Store AppID
requests are UNVERIFIED, not SUCCESS. Slow apps, already-running apps and child
process launchers may therefore open but return unverified in this stage.

## Remaining work

1. Resolve duplicate source identity without incorrectly merging different versions.
2. Provide user choice/remembered defaults and configuration for portable folders.
3. Recognize short natural commands for arbitrary installed names safely.
4. Background inventory refresh and Windows atomic persisted cache.
5. Correlate Store/launcher windows, focus existing instances and add bounded polling.
6. Provider-specific error/timeout tests and multi-machine launch evidence.
7. Fix full-suite failures and rerun before commit/push. No release authorization.
