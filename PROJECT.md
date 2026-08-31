# Project: JARVIS v4.1.x Bug Fixes & Documentation

## Architecture
JARVIS is an AI voice assistant running on Windows 11/10 64-bit Python 3.13.
Key architectural boundaries:
- **LLM Routing Engine (`jarvis/llm/router.py`)**: 3-tier routing (Regex fast-path -> Rule Engine greedy dictionary -> LLM Tool calling -> Fallback).
- **Subprocess & OS Execution (`jarvis/`, `scripts/`)**: Windows console management and process isolation.
- **Documentation & Packaging (`README.md`, `installer/`)**: Installation guides, quick start, common diagnostics, and developer setup.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Mở / chuyển sang dự án | Recognize "mở dự án X", "switch sang project Y", "chuyển workspace" -> `workspace_prepare` | M1 | Survey R1 (DONE) |
| 2 | Tạo dự án / workspace mới | Recognize "tạo project mới", "tạo workspace tên ABC" -> `project_create` | M1 | Survey R1 (DONE) |
| 3 | Liệt kê dự án | Recognize "liệt kê dự án", "show projects", "các project đang có" -> `project_list` | M1 | Survey R1 (DONE) |
| 4 | Lệnh git liên quan dự án | Recognize "git status dự án", "commit dự án", "push project" -> `skill_git_assistant` | M1 | Survey R1 (DONE) |
| 5 | Router Tests (>= 5 cases) | Add at least 5 new tests in `tests/test_router_project_intents.py` without regressions | M1 | Survey R1 (DONE) |
| 6 | Subprocess Windows Flags | Update all `subprocess.Popen`, `run`, `call`, `check_output` across `jarvis/` and `scripts/` to use `creationflags=CREATE_NO_WINDOW` / `startupinfo` | M2 | Survey R2 (DONE) |
| 7 | Suppress Background Polling Flash | Ensure background polling in `jarvis/hardware/monitor.py` (`nvidia-smi`, `powershell`) and all background engines are silent | M2 | Survey R2 (DONE) |
| 8 | Validate `os.system` absence | Ensure no bare `os.system` in `jarvis/` and `scripts/` | M2 | Survey R2 (DONE) |
| 9 | README Prerequisites | Python 3.13 (link), Git (link), Visual C++ Redistributable (link), Windows 11/10 64-bit | M3 | Survey R3 (DONE) |
| 10 | README Step-by-Step Order | Clone -> venv -> pip install -> API key config -> first run (`python -m jarvis`) | M3 | Survey R3 (DONE) |
| 11 | README Common Errors & Fixes | At least 5 errors: SQLite locked/path, PIL/Pillow DLL, faster-whisper CTranslate2, UAC/admin rights, API key 401 | M3 | Survey R3 (DONE) |
| 12 | README Quick Start (End User) | Standalone installer instructions (no Python needed) | M3 | Survey R3 (DONE) |
| 13 | README Dev Setup (Developers) | Development installation workflow, testing with pytest, linting | M3 | Survey R3 (DONE) |
| 14 | E2E Acceptance Verification | Validate all acceptance criteria across R1, R2, R3, run all test suites, and pass integrity audit | M4 | ORIGINAL_REQUEST (DONE) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Intent Recognition (R1) | `jarvis/llm/router.py`, `tests/` | None | DONE |
| M2 | Suppress Console Flash (R2) | `jarvis/`, `scripts/` subprocess calls | None | DONE |
| M3 | Rewrite README (R3) | `README.md` complete rewrite | None | DONE |
| M4 | E2E Verification & Audit | Acceptance verification of R1, R2, R3, full test suite pass, and integrity audit | M1, M2, M3 | DONE |

## Interface Contracts
### Router Intent Contracts (M1)
- `parse_intent(text, force_llm=False)` returns `IntentResult`:
  - `action_name`: `"workspace_prepare"`, `"project_create"`, `"project_list"`, or `"skill_git_assistant"`
  - `action_name` must NOT be `"unknown_intent"` or `"generic_llm_response"` for the targeted test phrases.
  - Parameters dictionary contains extracted entities (e.g., project name, sub-action).

### Process Management Contracts (M2)
- Windows subprocess invocations must specify `creationflags=subprocess.CREATE_NO_WINDOW` (or `0x08000000`) or `startupinfo` (with `STARTF_USESHOWWINDOW` and `SW_HIDE`) within 5 lines of the call.
- Safe cross-platform helper pattern:
  `creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0`

### Documentation Contracts (M3)
- `README.md` must be self-contained, completely accurate for Windows 11 64-bit Python 3.13, and include all 5 required sections.

## Code Layout
- `jarvis/llm/router.py`: Intent routing logic (M1 - DONE)
- `tests/test_router_project_intents.py`: Intent routing tests (M1 - DONE)
- `jarvis/`, `scripts/`: Subprocess executions (M2 - DONE)
- `README.md`: Project documentation (M3 - DONE)
- `tests/`: Complete test suite (M4 - DONE)
