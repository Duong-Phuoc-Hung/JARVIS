# Runtime regression fixes — 2026-09-23

## Changes

- `jarvis/vision/screen.py`: zero-area or empty ROI captures now produce a
  valid 1x1 fallback JPEG instead of raising Pillow `ValueError`.
- `jarvis/planner/safety_interceptor.py`: weather's fixed read-only `curl
  wttr.in` command is exempt from confirmation only when the command matches an
  exact allowlist. Arbitrary `shell_exec` payloads remain confirmation-gated.
- `jarvis/automation/control.py`: brightness uses an argument-list PowerShell
  invocation and `Invoke-CimMethod`; unavailable WMI hardware remains
  fail-closed (`None`).
- `jarvis/llm/router.py`: bounded oversized-input handling, project/app
  precedence, and accented/unaccented RAM/disk telemetry aliases.
- `jarvis/vision/computer_use.py`: explicit non-positive viewports now return
  `(0, 0)` instead of silently using host display dimensions.
- `jarvis/web/news.py` and `jarvis/web/hub.py`: strip markup from feed titles and
  expose the legacy `speech_text` briefing key.
- `jarvis/comms/telegram.py`: explicit HTTP test transports dispatch before the
  real credential check; real network calls still require a bot token.
- `jarvis/security/scanner.py`: authentication remains first; scanner test seams
  retain their legacy contract while real TShark output remains fail-closed.
- `jarvis/tts/manager.py` and `jarvis/ui/overlay.py`: callback failures no
  longer kill the worker; very large headless diagnostics are retained while
  normal HUD responses remain bounded.
- `jarvis/tts/cache.py`: invalid WAV containers are rejected before platform
  playback fallback, preventing corrupted-cache false success.
- `jarvis/core/result_model.py` and `jarvis/core/dispatcher.py`: shared
  `BackendResult`/`HealthStatus` seam with compatibility normalization.
- E2E brightness acceptance now distinguishes a real hardware value from the
  documented unavailable-hardware result.

## Fresh verification

| Scope | Result | Artifact |
|---|---:|---|
| Focused regression tests | 28 passed, 3 skipped / 16.53s | `reports/evidence/system_completion_targeted_final_20260923.xml` |
| Full E2E suite (fresh) | 290 passed, 21 skipped, 0 failed / 23.72s | `reports/evidence/system_completion_e2e_final_20260923.xml` |
| Full unit suite (fresh) | 3,002 passed, 3 skipped, 0 failed / 334.31s | `reports/evidence/system_completion_unit_final_20260923.xml` |
| Security subset | 66 passed, 0 skipped, 0 failed / 8.40s | `reports/evidence/system_completion_security_final_20260923.xml` |
| Static scanner | 0 findings / 202 files / 66,922 lines | `reports/evidence/system_completion_scanner_final_20260923.json` |
| Ruff on changed files | pass | command output |

The full `tests/` repository gate is intentionally **not certified**: historical
non-unit simulations still contain expectations that conflict with the current
safety/telemetry contracts. Repeated full-suite loops were stopped; no partial
run is promoted to “full-green”. External live credentials, optional devices,
installer and clean-machine acceptance remain separate gates. Existing unrelated
working-tree changes under `.agents/sentinel/` were preserved.
