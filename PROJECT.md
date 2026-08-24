# Project: JARVIS Autonomous Agentic Superpower Upgrade

## Architecture
JARVIS is upgraded from single-turn reactive assistant to a fully autonomous, self-healing, multi-agent AI system.

```
                            [User Request / Voice / CLI / Telegram]
                                              │
                                              ▼
                                   [JarvisApp Lifecycle]
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
         [Simple Intent Path]                                [Autonomous ReAct Planner]
      (LLMIntentRouter / Fast-Path)                         (Task DAG / Self-Reflection)
                    │                                                   │
                    ▼                                                   ▼
           [ActionDispatcher] ◄────────────────────────────── [SubAgentWorkerPool]
                    │                                                   │
     ┌──────────────┼──────────────┬──────────────┬──────────────┐      │
     ▼              ▼              ▼              ▼              ▼      ▼
[BrowserAgent] [GUIActor]   [CodeSandbox]  [SkillLibrary]  [OS Control] [AlwaysOnOverlay HUD]
 (Playwright/   (Vision 0-1000  (Python /      (Persistent      (Win32/     (Live Task DAG,
  CDP/Scraper)   Grounding +     PowerShell     jarvis/skills/   Process/    Code Logs,
                 Verification)   AST Isolated)  Auto-Package)    Files)      Waveform)
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Autonomous ReAct Planner | Multi-step reasoning DAG, topological execution, parameter interpolation | M1 | R1, ORIGINAL_REQUEST §14-19 |
| 2 | Self-Reflection & Self-Healing | Dynamic root-cause diagnosis, strategy matrix, retry with backoff, tool replacement | M1 | R1, ORIGINAL_REQUEST §17 |
| 3 | Dual Mode with Safety Gate | Fully Autonomous vs 30s token confirmation on high-risk/destructive actions | M1 | R1, ORIGINAL_REQUEST §18 |
| 4 | Autonomous Background Workers | Concurrency pool, task lifecycle management, cooperative cancellation, watchdogs | M1 | R5, ORIGINAL_REQUEST §37-41 |
| 5 | Worker Telemetry & Notifications | EventBus broadcast, HUD progress updates, TTS voice notification, Telegram dispatch | M1 | R5, ORIGINAL_REQUEST §40 |
| 6 | Code Interpreter Sandbox | Isolated Python/PowerShell execution, AST safety validator, resource bounds, artifact capture | M2 | R2, ORIGINAL_REQUEST §20-24 |
| 7 | Persistent Skill Library | Automatic packaging into `jarvis/skills/`, metadata indexing, dynamic dispatcher registration | M2 | R2, ORIGINAL_REQUEST §23 |
| 8 | Full Browser Automation Driver | 4-tier driver (Playwright -> CDP -> HTTP scraper -> Mock), session/cookie persistence | M3 | R3, ORIGINAL_REQUEST §25-30 |
| 9 | Dynamic SPA Scraping & Forms | DOM interaction, form auto-fill, table extraction, file downloads, price comparison | M3 | R3, ORIGINAL_REQUEST §27-29 |
| 10 | Computer-Use Coordinate Grounding | 1000x1000 normalized coordinate system, 4-tier element grounding (Vision LLM, OCR, Win32, Template) | M4 | R4, ORIGINAL_REQUEST §31-36 |
| 11 | Visual Verification Loop & GUI Actor | Pre/post screenshot diffing, ROI state transition check, self-healing GUI retries | M4 | R4, ORIGINAL_REQUEST §35 |
| 12 | Enhanced AlwaysOnOverlay HUD | Task DAG visualization, live code log stream, visual result cards, telemetry bar | M5 | R6, ORIGINAL_REQUEST §45 |
| 13 | SQLite Memory Layer Upgrades | `task_history`, `browser_sessions`, `learned_workflows` tables with WAL mode | M5 | R6, ORIGINAL_REQUEST §46 |
| 14 | Unified Multi-Modal App Wiring | Wake-word-to-agent voice loop, action registrations in `ActionDispatcher`, core wiring | M5 | R6, ORIGINAL_REQUEST §42-47 |
| 15 | Diagnostic Health Check | Update `python -m jarvis health-check` reporting all autonomous subsystems READY | M5 | R7, ORIGINAL_REQUEST §51 |
| 16 | Comprehensive Regression Verification | 100% pass on 921+ baseline tests + >=30 new tests (total >=951), zero regressions | M6 | R7, ORIGINAL_REQUEST §48-52 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | ReAct Planner & Background Workers | `jarvis/planner/`, `jarvis/workers/` | none | DONE |
| M2 | Sandboxed Self-Coding & Skill Library | `jarvis/sandbox/`, `jarvis/skills/` | M1 | DONE |
| M3 | Browser Automation Agent | `jarvis/browser/` | M1 | DONE |
| M4 | Computer-Use Vision & GUI Actor | `jarvis/vision/computer_use.py`, `jarvis/vision/visual_verifier.py`, `jarvis/automation/gui_actor.py` | M1 | DONE |
| M5 | HUD Telemetry, Memory & System Integration | `jarvis/ui/overlay.py`, `jarvis/memory/sqlite_store.py`, `jarvis/core/app.py`, `jarvis/cli.py` | M1, M2, M3, M4 | DONE |
| M6 | Final Verification & Zero Regression Pass | Regression verification (921+ baseline), E2E test pass (Tiers 1-4), health-check status 0 | M1..M5 | DONE |

## Interface Contracts

### M1: Planner ↔ Dispatcher & Workers
```python
# TaskDAG & ReActEngine
class TaskDAG:
    def add_node(self, node: TaskNode) -> None: ...
    def get_ready_nodes(self) -> List[TaskNode]: ...
    def topological_sort(self) -> List[List[TaskNode]]: ...
    def interpolate_node_params(self, node: TaskNode) -> Dict[str, Any]: ...

class ReActTaskEngine:
    def create_plan(self, goal: str, context: Optional[Dict[str, Any]] = None) -> TaskDAG: ...
    def execute_plan(self, dag: TaskDAG, mode: PlanMode = PlanMode.FULLY_AUTONOMOUS) -> PlanResult: ...

class SubAgentManager:
    def spawn_worker(self, task: WorkerTask) -> str: ...
    def cancel_worker(self, worker_id: str) -> bool: ...
    def get_worker_status(self, worker_id: str) -> Optional[WorkerTelemetry]: ...
```

### M2: Sandbox ↔ Skill Library
```python
class CodeInterpreterSandbox:
    def execute_python(self, code: str, timeout_seconds: float = 15.0) -> SandboxResult: ...
    def execute_powershell(self, script: str, timeout_seconds: float = 15.0) -> SandboxResult: ...

class SkillRegistry:
    def register_skill(self, skill_def: SkillDefinition) -> bool: ...
    def load_skill(self, skill_name: str) -> Optional[SkillDefinition]: ...
    def list_skills(self) -> List[SkillMetadata]: ...
    def invoke_skill(self, skill_name: str, **kwargs) -> Any: ...
```

### M3: Browser Automation
```python
class BrowserAgent:
    def navigate(self, url: str) -> BrowserActionResult: ...
    def scrape_page(self, url: str) -> ScrapeResult: ...
    def fill_form(self, url: str, fields: Dict[str, str], submit_selector: Optional[str] = None) -> BrowserActionResult: ...
    def compare_prices(self, product: str, stores: List[str]) -> List[PriceComparisonItem]: ...
```

### M4: Computer-Use Vision & GUI Actor
```python
class ComputerUseVision:
    def locate_element(self, query: str, screenshot_bytes: Optional[bytes] = None) -> Optional[UIElement]: ...
    def norm_to_pixel(self, x_norm: int, y_norm: int) -> Tuple[int, int]: ...

class GUIActor:
    def click_element(self, query: str, verify: bool = True) -> bool: ...
    def type_into_element(self, query: str, text: str, verify: bool = True) -> bool: ...
```

### M5: HUD Telemetry & Memory Layer
```python
# Overlay HUD additions
class AlwaysOnOverlay:
    def update_task_dag(self, dag_data: Dict[str, Any]) -> None: ...
    def append_code_log(self, log_line: str, stream: str = "stdout") -> None: ...
    def display_visual_result(self, result_info: Dict[str, Any]) -> None: ...

# SQLiteMemoryStore additions
class SQLiteMemoryStore:
    def record_task_execution(self, task_id: str, goal: str, dag_json: str, status: str, duration: float) -> None: ...
    def get_task_history(self, limit: int = 50) -> List[Dict[str, Any]]: ...
    def save_browser_session(self, domain: str, cookies: List[Dict[str, Any]], storage: Dict[str, Any]) -> None: ...
```

## Code Layout
- `jarvis/planner/`: Task graph, ReAct loop, self-reflection, safety gate interceptor.
- `jarvis/workers/`: Background worker threads, task lifecycle, concurrency, notifications.
- `jarvis/sandbox/`: AST security validator, isolated Python/PowerShell execution, artifact manager.
- `jarvis/skills/`: Skill metadata, persistent registry, auto-synthesizer, dynamic importer.
- `jarvis/browser/`: Multi-tier driver (Playwright/CDP/HTTP/Mock), scraper, form filler, session manager.
- `jarvis/vision/`: Coordinate mapping (`computer_use.py`), visual verifier (`visual_verifier.py`).
- `jarvis/automation/`: `gui_actor.py` (Vision-grounded verified desktop interaction).
- `jarvis/ui/`: `overlay.py` (Enhanced HUD widgets for Task DAG, Code Stream, Visual Results).
- `jarvis/memory/`: `sqlite_store.py` (Schema upgrades for tasks, browser sessions, workflows).
- `jarvis/cli.py`: Extended `run_health_check()` verifying all new autonomous subsystems.
- `tests/unit/`: Test suites covering each new subsystem.
- `tests/e2e/`: E2E autonomous workflow tests.
