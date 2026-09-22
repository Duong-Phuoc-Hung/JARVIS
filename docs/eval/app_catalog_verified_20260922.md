# Installed applications: routing, identity and live window verification

Date: 2026-09-22. Source version: 5.2.1, unreleased working tree.
This follow-up supersedes the stage-1 limitations for Notepad/Calculator routing
and Store-window verification; it does not certify every application or machine.

## What changed

| File | Root cause and correction |
|---|---|
| `jarvis/llm/router.py` | Earlier app regex swallowed explicit catalog commands. Full-input explicit parsing now precedes it; short desktop commands, static app rules and LLM app calls use the catalog. Negated LLM app requests are rejected; ambiguous/compound/overlong requests cannot launch a truncated app name. |
| `jarvis/automation/app_catalog.py` | Name-only records could not prove AppID/EXE equivalence. Exact package manifest/Shell metadata joins provide executable identity; equivalent entries merge, distinct IDs remain separate. Shared executable identities are marked. |
| `jarvis/automation/app_launcher.py` | Launch acknowledgement was mistaken for window evidence. Verify exact packaged AUMID on window/child PID, explicit window AUMID, or exact unshared desktop executable. Reuse/focus existing windows; poll up to 5 seconds after one launch; never retry/kill user apps. Requested EXEs retain visible UI; only discovery helpers run hidden. |
| `jarvis/platform/window_identity.py` | A real minimized Calculator detached its content child from ApplicationFrameHost. Read `System.AppUserModel.ID` via native COM instead; balance COM initialization, clear PROPVARIANT and release the property store. No new dependency. |
| `jarvis/automation/control.py` | Catalog opens now delegate to the verified launcher; fixed aliases resolve back to catalog executable names. Shared legacy cooldown preserved. |
| `jarvis/core/app.py` | App handler enforces catalog for desktop targets, preserves explicit success=false and timeout status so a suppressed result cannot become dispatcher SUCCESS. Canonical Settings / `ms-settings:` remains a separate legacy route unless explicitly catalog-only. |
| `scripts/verify_installed_apps_live.py` | Reproducible opt-in text-command live probe with real router, default dispatcher safety, real app handler and Windows APIs. No unrelated service startup or credentials. |

Identity matching follows Windows' process
[GetApplicationUserModelId](https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getapplicationusermodelid)
and [child-window enumeration](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumchildwindows),
plus the [explicit window AppUserModelID](https://learn.microsoft.com/en-us/windows/win32/properties/props-system-appusermodel-id)
read through [SHGetPropertyStoreForWindow](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shgetpropertystoreforwindow).
Window properties are identity metadata, not an authorization/security boundary.
For a `window_app_id_property` proof, PID can be the host PID, not the app's content PID.
Titles and executable basenames are not accepted as proof. Packaged apps without
readable AUMID and desktop shortcuts sharing executable identities fail closed
as unverified rather than claiming the requested profile/app is visible.

## Engineering verification

New suites: `test_app_catalog_identity.py` (29), `test_installed_app_routing.py`
(77), `test_app_launcher.py` (24), `test_window_identity.py` (17). Existing catalog tests adapted to stronger
path-identity verification; app/web handler fixture includes the catalog backend.

Scoped run:

```powershell
.venv\Scripts\python -m pytest tests/unit/test_app_launcher.py tests/unit/test_window_identity.py tests/unit/test_app_catalog.py tests/unit/test_app_catalog_identity.py tests/unit/test_installed_app_routing.py tests/unit/test_windows_command_targets.py tests/unit/test_h07_voice_app_intents.py tests/unit/test_app_web_dedupe_stress.py tests/unit/test_computer_control.py tests/unit/test_subprocess_no_window_r2.py -o addopts='' -q --tb=short --junitxml=reports/evidence/app_catalog_verified_scoped_final_20260922.xml
```

Result: **244 passed, 25 subtests passed / 7.48s**, exit 0.
Review and live testing found suppressed-status false-success, shared Store
executable false positive, minimized-window omission/detached content, and the
Settings URI routing regression. Regression tests cover these corrections.
Ruff passed for the new catalog/launcher/native helper/probe and their new tests.

The first complete unit run found **1 failed, 2613 passed, 4 skipped,
268 subtests / 363.24s**. Failure: no-window static scan (catalog flag was outside
its five-line check; launcher needed an explicit startup policy). Discovery still
uses hidden PowerShell. Requested apps instead use visible STARTUPINFO/new console,
without redirecting console output to DEVNULL; hiding an explicitly requested
console app would be wrong. This follows the distinction in Microsoft's
[process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags).
The original failing JUnit is retained; the final rerun uses a separate artifact.

## Runtime scope

```powershell
.venv\Scripts\python -m scripts.verify_installed_apps_live --run
```

This opens only Calculator and Notepad, then exercises repeat suppression,
missing-app handling, parse-only negation/compound cases, and reuse of a minimized
Calculator window. It leaves windows
open and never force-terminates processes, edits documents or accesses a mailbox.
Report files are created exclusively under `reports/evidence/`, with counts and
PID/HWND evidence, not full application inventories or document/window titles.

Observed discovery with final identity sources: **175 catalog entries**, 167
with executable metadata, 21 marked shared-executable, no mandatory source error.
The old 235 raw records are not directly comparable: source dedupe and exclusion
of maintenance/non-executable/unsafe targets changed the denominator.

## Real-machine result: 2026-09-22, 11:49 ICT

**8/8 checks passed**, exit 0: six real dispatched actions and two parse-only
guards. This is not eight Beta workflows and not a 175-app launch matrix.
Artifact: [runtime JSON](../../reports/evidence/app_catalog_runtime_20260922T044913513558Z.json).
Inventory scan in this run: **175 entries, 0 errors, 2.866s**.

| Check | Observed result | Verdict |
|---|---|---|
| `mở ứng dụng Calculator` | Fresh launch, HWND 14551740, explicit window AUMID; 0.679s | PASS runtime |
| `mở ứng dụng Notepad` | Fresh launch, PID 12492 / HWND 7667910, process AUMID; 0.557s | PASS runtime |
| Immediate repeat of each app | Both return `LAUNCH_RATE_LIMITED`, success=false | PASS fail-closed, runtime observed |
| Nonexistent probe app | `APP_NOT_FOUND`, success=false | PASS fail-closed, runtime observed |
| Negation and compound commands | Both `unknown_intent`; parse only, not dispatched | PASS engineering in live probe |
| Calculator already minimized | Minimized=true before, already_running=true, same HWND, restored=true after | PASS runtime |

Earlier live artifact `app_catalog_runtime_20260922T044051076804Z.json` is retained
with the failed minimized-window check. The corrected native property path was
added after this reproduction, not inferred from the passing mocked test.

## Acceptance boundary and remaining work

- PASS engineering / PASS fail-closed applies to the scoped tests only.
- PASS runtime can apply to the measured text-command cases on this machine,
  not all 175 entries, not microphone/STT/TTS, full app startup or an installer.
- Settings/Spotify specialized legacy routes are not recertified by this probe.
- Shared desktop launchers/profiles may open but remain unverified; no false success.
- Console-host correlation is not certified by the Calculator/Notepad probe.
- Genuine name collisions still return candidates; interactive choice/remembered
  defaults, portable-folder onboarding, background startup refresh and persistent
  atomic cache remain outstanding items from the broader design.
- Multi-machine/clean-machine acceptance and full release gates remain pending.
  No commit/push/release until the repository's full-suite requirement is satisfied.
