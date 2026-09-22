# Project: JARVIS Codebase Scan, Verification, and Bug Remediation Sprint

## Architecture
JARVIS is an autonomous AI voice assistant and desktop automation platform for Windows 11 (Python 3.13).
- **Core Orchestration (`jarvis/core/`)**: EventBus, ActionDispatcher, JarvisApp lifecycle, ConfigManager, Logger, and RunawayGuard.
- **Automation Subsystem (`jarvis/automation/`)**: ComputerController, SafetyGate, VMOrchestrator, WorkspaceManager, ShellAssistant, and AppLauncher.
- **LLM & Intent Routing (`jarvis/llm/`)**: LLMIntentRouter, Gemini/OpenAI/Ollama clients, Tool calling schema generator, diacritic normalization, and parameter extraction.

## Feature Inventory & Bug Registry
| # | Defect ID | Description | Module / File | Milestone | Source |
|---|-----------|-------------|---------------|:---------:|--------|
| 1 | BUG-CORE-01 | Deadlock in `EventBus.publish` and `dispatch_action` when called from active async event loop | `jarvis/core/dispatcher.py:148-158, 584-594` | M1 | Survey (Core Explorer) |
| 2 | BUG-CORE-02 | `ActionStatus` enum demoted to `ActionStatus.FAILED` due to `'ACTIONSTATUS.BLOCKED'` str formatting | `jarvis/core/dispatcher.py:608-612, 746-750` | M1 | Survey (Core Explorer) |
| 3 | BUG-CORE-03 | `ActionStatus.RATE_LIMITED` and `LABS_DISABLED` normalized as `success=True` | `jarvis/core/dispatcher.py:268-270` | M1 | Survey (Core Explorer) |
| 4 | BUG-CORE-04 | Hotkey argument splatting mismatch in `_handle_new_tab` (`"ctrl+t"` string instead of splatted args) | `jarvis/core/app.py:1756` | M1 | Survey (Core Explorer) |
| 5 | BUG-CORE-05 | Inverted error/message contract in `_handle_system_brightness` leaking internal codes to TTS | `jarvis/core/app.py:1674, 1679` | M1 | Survey (Core Explorer) |
| 6 | BUG-CORE-06 | Grammatical sign bug in `_handle_system_volume` stating volume was adjusted up on negative delta | `jarvis/core/app.py:1666` | M1 | Survey (Core Explorer) |
| 7 | BUG-CORE-07 | Race condition in `JarvisApp.initialize()` allowing duplicate subsystem initialization | `jarvis/core/app.py:325-330` | M1 | Survey (Core Explorer) |
| 8 | BUG-CORE-08 | Fragile teardown in `JarvisApp.stop()` where one subsystem exception halts remaining cleanup | `jarvis/core/app.py:3127-3153` | M1 | Survey (Core Explorer) |
| 9 | BUG-AUTO-01 | `set_brightness` mutates internal state before hardware call and returns int on failure instead of `None` | `jarvis/automation/control.py:511-537` | M2 | Survey (Auto Explorer) |
| 10 | BUG-AUTO-02 | CRITICAL: `SafetyGate` confirms destructive action on negation (`"không đồng ý"`, `"không được"`, `"không ok"`) | `jarvis/automation/safety_gate.py:209-218` | M2 | Survey (Auto Explorer) |
| 11 | BUG-AUTO-03 | `SafetyGate` voice response fails on trailing punctuation (`"đồng ý."`, `"có!"`) | `jarvis/automation/safety_gate.py:177-196` | M2 | Survey (Auto Explorer) |
| 12 | BUG-AUTO-04 | Memory leak in `SafetyGate._pending` tokens never pruned upon confirmation or cancellation | `jarvis/automation/safety_gate.py:166-175` | M2 | Survey (Auto Explorer) |
| 13 | BUG-AUTO-05 | `VMOrchestrator` start/stop returns `success=True` when hypervisor binaries are missing | `jarvis/automation/vm.py:66-81, 130-145` | M2 | Survey (Auto Explorer) |
| 14 | BUG-AUTO-06 | `WorkspaceRecipe` AttributeError & recipe execution stub returning fake success | `jarvis/automation/workspace.py:68-94` | M2 | Survey (Auto Explorer) |
| 15 | BUG-AUTO-07 | Windows `cmd.exe` shell command syntax errors (`docker restart $(...)` and PowerShell cmdlets in cmd) | `jarvis/automation/shell_assistant.py:459-466, 219` | M2 | Survey (Auto Explorer) |
| 16 | BUG-AUTO-08 | `take_screenshot` returns destination path even when capture fails | `jarvis/automation/control.py:636-663` | M2 | Survey (Auto Explorer) |
| 17 | BUG-LLM-01 | Non-diacritic duration parsing unit collapse (`30 giay` -> 1800s, `2 gio` -> 120s) | `jarvis/llm/router.py:121-130` | M3 | Survey (LLM Explorer) |
| 18 | BUG-LLM-02 | Negation bypass on Spotify & Claude targets (`đừng mở spotify` triggers launch) | `jarvis/llm/router.py:2316-2340` | M3 | Survey (LLM Explorer) |
| 19 | BUG-LLM-03 | Gemini tool schema generator omits required `items` field on array parameters (HTTP 400) | `jarvis/llm/router.py:180-194` | M3 | Survey (LLM Explorer) |
| 20 | BUG-LLM-04 | Router emits action names unregistered in `JarvisApp.dispatcher` (`hardware_telemetry_check`, `reminder`, etc.) | `jarvis/llm/router.py` vs `jarvis/core/app.py` | M3 | Survey (LLM Explorer) |
| 21 | BUG-LLM-05 | Positional argument & key mismatch in `_handle_proactive_reminder` (`message`, `delay_s`) | `jarvis/core/app.py:1799` & `jarvis/llm/router.py:1520` | M3 | Survey (LLM Explorer) |
| 22 | BUG-LLM-06 | Gemini safety filter candidate with null content crashes with `AttributeError` | `jarvis/llm/client.py:560` | M3 | Survey (LLM Explorer) |
| 23 | BUG-LLM-07 | Missing standard vendor API key environment variable fallbacks (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) | `jarvis/llm/client.py:201-208` | M3 | Survey (LLM Explorer) |
| 24 | M4-DOC-01 | CHANGELOG.md and ROADMAP.md sync, full regression test execution, git commits and push | Repository Root | M4 | Original Request |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|:------:|
| M1 | Core Subsystem Remediation | Bugs 1 to 8: `dispatcher.py`, `app.py`, lifecycle, fail-closed & concurrency | none | DONE |
| M2 | Automation & Safety Gate Remediation | Bugs 9 to 16: `safety_gate.py`, `control.py`, `vm.py`, `workspace.py`, `shell_assistant.py` | M1 | DONE |
| M3 | LLM Router & Integration Remediation | Bugs 17 to 23: `router.py`, `client.py`, dispatcher action registrations | M1, M2 | DONE |
| M4 | Verification, Documentation & Release | Full pytest suite (>=2,200 tests), CHANGELOG, ROADMAP, >=3 commits, push origin/main | M1, M2, M3 | DONE |

## Interface Contracts
### Dispatcher & Action Execution Contract (`jarvis/core/dispatcher.py`)
- `dispatch_action(action_name, payload)` must not block active asyncio loops or deadlock when called from an async thread.
- `_normalize_handler_outcome` must preserve `ActionStatus.RATE_LIMITED` and `ActionStatus.LABS_DISABLED` with `success=False`.
- `ActionStatus` enum string serialization must correctly map back to enum members without falling back to `FAILED`.

### Safety Gate Verification Contract (`jarvis/automation/safety_gate.py`)
- Negated phrases (`"không đồng ý"`, `"không được"`, `"không ok"`, `"huỷ"`, `"dừng lại"`) MUST be evaluated before affirmative phrases.
- Voice response text must be sanitized (strip punctuation, trim whitespace, normalize lowercase) before matching word boundaries.
- Confirmed, cancelled, or expired requests MUST be purged from `_pending` dictionary.

### LLM Intent Router & Schema Contract (`jarvis/llm/router.py`, `jarvis/llm/client.py`)
- Duration parsing regex must correctly match non-diacritic `"giay"`, `"phut"`, `"gio"` without colliding with wrong unit multipliers.
- Negation prefixes (`"đừng"`, `"không"`, `"chớ"`, `"never"`, `"don't"`) must not be stripped or ignored when routing app launch targets.
- Tool schema generation for `type: "array"` must provide a valid `items: {"type": "string"}` schema dictionary for Gemini API.

## Code Layout
- `jarvis/core/`: Application orchestrator, event bus, action dispatcher, configuration, and logging.
- `jarvis/automation/`: Desktop automation, safety gate, virtual machine control, workspace recipes, shell assistance.
- `jarvis/llm/`: Intent routing, LLM clients, tool schema definition, diacritic normalization.
- `tests/unit/`: Pytest unit and regression test suite.
- `CHANGELOG.md`: Project change log.
- `docs/ROADMAP.md`: Master project roadmap.
