# Architectural Specification & Survey Report: Requirements R1, R2, and R5
**JARVIS Autonomous Agentic Superpower Upgrade**
**Author**: Explorer Survey Agent (`explorer_survey_2`)
**Target Working Directory**: `d:/Software GitCode/JARVIS`
**Date**: 2026-08-24

---

## 1. Executive Summary

This report delivers the complete architectural design, data schemas, class definitions, execution algorithms, error-handling protocols, and test strategies for three core pillars of the JARVIS Autonomous Agentic Superpower upgrade:
1. **R1: Autonomous ReAct Planner & Multi-Step Task Engine** (Task Graph / DAG, topological step execution, dynamic parameter interpolation, self-reflection & self-healing recovery loop, Fully Autonomous vs Safety Gate modes).
2. **R2: Dynamic Skill Synthesis & Sandboxed Self-Coding** (Code Interpreter Sandbox for Python & PowerShell, AST security validator, result/artifact capture, persistent Skill Library in `jarvis/skills/`, auto-packaging, metadata indexing, and dynamic skill registration).
3. **R5: Autonomous Background Workers & Task Delegation** (Sub-agent worker lifecycle, concurrent thread/process pools, watchdog heartbeat telemetry, HUD real-time progress broadcast, and multi-channel TTS/HUD/Telegram notification hooks).

---

## 2. Baseline Architecture & Existing System Analysis

### 2.1 Existing Subsystems in `jarvis/`
Direct inspection of the codebase reveals a robust baseline consisting of 21 functional subdirectories and core architectural patterns:
- **Action Dispatcher & EventBus (`jarvis/core/dispatcher.py`, `models.py`)**:
  - `ActionDispatcher` provides centralized RBAC privilege management (`PrivilegeLevel.GUEST`, `NORMAL`, `HIGH`, `ADMIN`), action definition registration (`ActionDefinition`), schema validation, and synchronous/asynchronous execution returning `ActionResult`.
  - `EventBus` provides priority-ordered topic subscription (`subscribe`, `publish`, `unsubscribe`) with error isolation across subscribers.
- **Safety Gate (`jarvis/automation/safety_gate.py`)**:
  - `SafetyGate` implements a 30-second tokenized state machine (`PendingConfirmation`) for high-risk operations with affirmative (`có`, `đồng ý`, `yes`, `confirm`) and negative (`không`, `hủy`, `cancel`) phrase recognition.
- **Developer Shell Assistant (`jarvis/automation/shell_assistant.py`)**:
  - `ShellAssistant` translates natural language to shell commands, detects destructive regex patterns (`rm -rf`, `rmdir /s /q`, `del /s /q`, `format`, `drop database`), gates them via `SafetyGate`, and provides domain-specific summarization for CLI outputs >10 lines.
- **Self-Healing & Watchdogs (`jarvis/healing/terminator.py`, `watchdog.py`)**:
  - `ResourceWatchdog` tracks CPU/RAM saturation and thread heartbeats (`record_heartbeat`, `check_thread_health`).
  - `AutonomousTerminator` enforces an immutable OS-critical whitelist (`PROTECTED_PROCESS_WHITELIST`) and executes safe two-phase termination (`WM_CLOSE` -> `SIGKILL`).
- **LLM Reasoning & Intent Router (`jarvis/llm/router.py`, `client.py`)**:
  - `LLMIntentRouter` provides a 3-tier routing architecture: Tier 1 regex fast path (<1ms), Tier 2 multi-provider LLM tool calling (OpenAI/Gemini/Ollama), and Tier 3 Vietnamese rule fallback.
  - `generate_tool_schema_from_dispatcher` introspects registered action signatures and formats OpenAI-compliant tool schemas.
- **Persistent Memory Layer (`jarvis/memory/sqlite_store.py`, `manager.py`)**:
  - SQLite WAL-mode store for user facts, sliding 10-turn FIFO conversation context, and episodic task interaction logs.
- **Always-On Overlay HUD (`jarvis/ui/overlay.py`)**:
  - 380px collapsible sidebar HUD with 5-turn conversation cards, real-time hardware status bar, audio waveform visualizer, and action buttons.
- **Comms & Remote Notification (`jarvis/comms/telegram.py`)**:
  - `TelegramBotController` with user ID whitelist filtering and remote command dispatch.

---

## 3. Requirement R1: Autonomous ReAct Planner & Multi-Step Task Engine

### 3.1 Component Architecture & Module Boundaries
The ReAct Planner will reside in `jarvis/planner/` with the following structure:
```
jarvis/planner/
├── __init__.py          # Exports TaskDAG, ReActTaskEngine, SelfReflectionEngine, TaskNode
├── models.py            # Dataclasses & Enums: StepStatus, PlanMode, TaskNode, PlanResult, ReflectionResult
├── dag.py               # TaskDAG: Dependency graph, cycle detection, topological sort, variable interpolation
├── engine.py            # ReActTaskEngine: Execution loop, parallel step runner, safety gate interception
└── reflection.py        # SelfReflectionEngine: Root cause diagnosis, dynamic replanning, strategy matrix
```

### 3.2 Data Schemas (`jarvis/planner/models.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional, Set, Union


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    WAITING_CONFIRMATION = "waiting_confirmation"


class PlanMode(str, Enum):
    FULLY_AUTONOMOUS = "fully_autonomous"
    SAFETY_GATE = "safety_gate"


class RecoveryStrategy(str, Enum):
    RETRY = "retry"                          # Retry same step with backoff / modified params
    ALTERNATIVE_TOOL = "alternative_tool"    # Switch tool (e.g. Playwright -> direct HTTP/requests)
    REPLAN = "replan"                        # Regenerate downstream sub-graph
    ABORT = "abort"                          # Terminate plan with explanation


@dataclass
class TaskNode:
    """Represents a discrete step in the task execution graph."""
    step_id: str
    action_name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    is_high_risk: bool = False
    max_retries: int = 3
    retry_count: int = 0
    result_data: Any = None
    error_message: Optional[str] = None
    confirmation_token: Optional[str] = None
    execution_time_ms: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_name": self.action_name,
            "description": self.description,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "is_high_risk": self.is_high_risk,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "confirmation_token": self.confirmation_token,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class ReflectionResult:
    """Outcome of self-reflection evaluation after a step failure."""
    step_id: str
    strategy: RecoveryStrategy
    diagnosis: str
    suggested_action: Optional[str] = None
    suggested_parameters: Optional[Dict[str, Any]] = None
    new_subgraph_nodes: Optional[List[TaskNode]] = None
    reasoning: str = ""


@dataclass
class PlanResult:
    """Overall outcome of task plan execution."""
    plan_id: str
    goal: str
    success: bool
    mode: PlanMode
    nodes: Dict[str, TaskNode]
    total_steps: int
    completed_steps: int
    failed_steps: int
    total_duration_ms: float
    final_output: Any = None
    error: Optional[str] = None
    summary_message: str = ""
```

### 3.3 Graph Engine & Dynamic Variable Interpolation (`jarvis/planner/dag.py`)
- **Cycle Detection**: Kahn's algorithm or DFS color-marking to validate that the Task Graph is a strictly acyclic DAG upon construction.
- **Topological Sorting**: Determines executable waves of tasks.
- **Ready Node Resolution**: Finds all nodes where `status == PENDING` and all IDs in `depends_on` are in `COMPLETED` state.
- **Dynamic Variable Interpolation**:
  - Supports references like `{{steps.step_1.output.file_path}}`, `{{steps.step_2.data[0].id}}`, or `{{context.user_id}}`.
  - Evaluates expressions against completed predecessor output dictionaries prior to node dispatch.

```python
import re

def interpolate_parameters(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively replaces `{{steps.<step_id>.<path>}}` tokens in parameters
    with actual resolved values from the execution context.
    """
    pattern = re.compile(r"\{\{([^}]+)\}\}")

    def _resolve(val: Any) -> Any:
        if isinstance(val, str):
            match = pattern.fullmatch(val.strip())
            if match:
                path_expr = match.group(1).strip()
                return _lookup_path(path_expr, context)
            
            # Sub-string template replacement
            def _replace_sub(m: re.Match) -> str:
                res = _lookup_path(m.group(1).strip(), context)
                return str(res) if res is not None else ""
            return pattern.sub(_replace_sub, val)
        elif isinstance(val, dict):
            return {k: _resolve(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [_resolve(item) for item in val]
        return val

    def _lookup_path(path: str, ctx: Dict[str, Any]) -> Any:
        parts = path.split(".")
        curr = ctx
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            elif hasattr(curr, part):
                curr = getattr(curr, part)
            else:
                return None
        return curr

    return _resolve(params)
```

### 3.4 Self-Reflection & Self-Healing Loop (`jarvis/planner/reflection.py`)
When a node execution raises an exception or returns a failure `ActionResult`:
1. **Diagnosis Extraction**: Captures `error_code`, `error_message`, `stderr`, parameter payload, and predecessor outputs.
2. **Deterministic Heuristic Triage**:
   - If error is `TimeoutExpired` -> Retry with doubled timeout (if retry_count < max_retries).
   - If error is `RateLimitError` / 429 -> Exponential backoff (2s, 4s, 8s).
   - If error is `FileNotFoundError` -> Check if predecessor produced alternative artifact path.
3. **LLM Reflection Fallback**:
   - Sends structured prompt containing goal, current step, failure message, and registered tool definitions.
   - LLM returns a structured JSON payload recommending `RecoveryStrategy`, parameter corrections, or alternative tool selection (e.g., `browser_scrape` failed due to Cloudflare protection -> fallback to `web_search_direct` or `sandbox_python_crawler`).

### 3.5 Dual Operating Modes & Safety Gate Interception
- **Fully Autonomous Mode**:
  - Non-destructive actions execute immediately.
- **Safety Gate Mode (High-Risk Interception)**:
  - If a step matches high-risk criteria (destructive file removal, system configuration change, external financial transfer, un-sandboxed shell script):
    1. The node enters `WAITING_CONFIRMATION` status.
    2. Registers a 30s confirmation request with `SafetyGate.request_confirmation(action_desc, payload)`.
    3. Emits event `planner:waiting_confirmation` over `EventBus`.
    4. Triggers voice alert via TTS ("Thưa Ngài, bước tiếp theo yêu cầu xóa thư mục X. Ngài có đồng ý không?") and displays confirmation card on HUD Overlay.
    5. The execution engine suspends execution of dependent nodes while allowing independent parallel branches to continue.
    6. When user confirms (`SafetyGate.confirm(token)`), node switches to `RUNNING` and executes. If rejected or expired (30s), node transitions to `FAILED` / `SKIPPED`, and Reflection initiates an alternative plan.

---

## 4. Requirement R2: Dynamic Skill Synthesis & Sandboxed Self-Coding

### 4.1 Component Architecture & Module Boundaries
Skill synthesis and execution will reside across `jarvis/sandbox/` and `jarvis/skills/`:
```
jarvis/
├── sandbox/
│   ├── __init__.py          # Exports CodeInterpreterSandbox, SandboxResult, ASTCodeValidator
│   ├── interpreter.py       # CodeInterpreterSandbox: Subprocess execution, scratch dir, resource limits
│   ├── validator.py         # ASTCodeValidator: Static code analysis, import and syscall safety checks
│   └── artifacts.py         # ArtifactManager: Captures and indexes generated files (.xlsx, .csv, .png, .pdf)
└── skills/
    ├── __init__.py          # Auto-exports SkillRegistry and built-in/dynamic skills
    ├── models.py            # SkillMetadata, SkillDefinition, SkillExecutionResult
    ├── registry.py          # SkillRegistry: Persistent indexing, auto-discovery, hot-reloading
    └── synthesizer.py       # DynamicSkillSynthesizer: LLM code gen, test verification, auto-packaging
```

### 4.2 Code Interpreter Sandbox (`jarvis/sandbox/interpreter.py`)

#### Security Architecture & AST Validation (`jarvis/sandbox/validator.py`):
Before executing any self-generated code:
- **AST Visitor**: Parses code into Python AST (`ast.parse`) and verifies:
  - **Forbidden Modules**: `win32api`, `ctypes`, `subprocess` (within code sandbox), `sys.modules` tampering, `socket` (for low-level port scanning unless whitelisted), `shutil.rmtree` on root directories.
  - **Forbidden Function Calls**: `eval`, `exec` (nested), `os.system`, `os.remove` on files outside sandbox scratch directory.
  - **Permitted Data Science & Automation Stack**: `pandas`, `openpyxl`, `xlsxwriter`, `matplotlib`, `seaborn`, `numpy`, `scipy`, `requests`, `bs4`, `csv`, `json`, `math`, `re`, `datetime`, `pathlib`.

#### Execution Isolation & Artifact Capture:
- **Process Isolation**: Code is written to a temporary Python script in an isolated scratch directory (`workspace/sandbox/run_<uuid>/`).
- **Resource Enforcement**: Executed via `subprocess.run([sys.executable, script_path], cwd=scratch_dir, timeout=timeout_s, env=sanitized_env, capture_output=True)`.
- **Artifact Discovery**: Compares directory file manifest before and after execution to automatically register generated files with MIME types, file sizes, and paths.

```python
@dataclass
class ArtifactInfo:
    filename: str
    file_path: str
    file_type: str        # "image", "spreadsheet", "csv", "document", "json", "binary"
    size_bytes: int
    created_at: float = field(default_factory=time.time)


@dataclass
class SandboxResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    artifacts: List[ArtifactInfo] = field(default_factory=list)
    data: Any = None
    execution_time_ms: float = 0.0
    error: Optional[str] = None
```

### 4.3 Persistent Skill Library & Synthesizer (`jarvis/skills/`)

#### Skill Auto-Packaging Protocol (`jarvis/skills/synthesizer.py`):
When a dynamic tool generation succeeds in the sandbox and solves a user's novel task:
1. **Packaging**: Formats the code into a clean, reusable Python module under `jarvis/skills/<skill_name>/` or `jarvis/skills/<skill_name>.py`.
2. **Metadata Generation (`metadata.json` / `SKILL.md`)**:
   - `name`: Unique alphanumeric identifier (e.g. `excel_revenue_aggregator`).
   - `description`: Detailed capability description in English and Vietnamese for LLM tool calling.
   - `parameters_schema`: JSON schema defining inputs, types, default values, and descriptions.
   - `tags`: Domain keywords (e.g. `["excel", "finance", "data_analysis"]`).
   - `version`: SemVer string (e.g. `1.0.0`).
   - `synthesized_by`: `"jarvis_agentic_synthesizer"`.
3. **Registry Ingestion (`jarvis/skills/registry.py`)**:
   - Loads the skill dynamically via `importlib.util.spec_from_file_location`.
   - Validates that the skill exports an entrypoint `def execute(**kwargs) -> Dict[str, Any]`.
   - Registers the skill in `ActionDispatcher` via `dispatcher.register_action(name=f"skill_{skill_name}", handler=..., description=...)`.
   - Updates persistent SQLite / JSON index with invocation counters and latency telemetry.

---

## 5. Requirement R5: Autonomous Background Workers & Task Delegation

### 5.1 Component Architecture & Module Boundaries
Background worker management will reside in `jarvis/workers/`:
```
jarvis/workers/
├── __init__.py          # Exports SubAgentManager, BackgroundWorker, WorkerTask
├── models.py            # Dataclasses: WorkerStatus, WorkerPriority, WorkerTask, WorkerTelemetry
├── worker.py            # BackgroundWorker: Worker execution thread, heartbeat, progress tracking
├── manager.py           # SubAgentManager: Worker pool, concurrency management, cancellation
└── notifications.py     # WorkerNotificationDispatcher: TTS, HUD card, and Telegram dispatchers
```

### 5.2 Worker Lifecycle & Concurrency (`jarvis/workers/manager.py`)

#### Lifecycle State Machine:
`INITIALIZING` ➔ `RUNNING` ➔ `COMPLETED` / `FAILED` / `CANCELLED` (with optional `PAUSED`).

#### Concurrency & Thread Safety:
- **Pool Management**: `SubAgentManager` maintains a bounded `ThreadPoolExecutor` (default max 4 concurrent workers) and tracks active workers in a thread-safe dict protected by `threading.RLock()`.
- **Cancellation Tokens**: Each worker is assigned a `threading.Event` cancellation flag. Long-running worker loops periodically check `self._cancel_token.is_set()` to terminate gracefully.
- **Heartbeat & Watchdog Integration**:
  - Each `BackgroundWorker` periodically calls `ResourceWatchdog.record_heartbeat(f"worker_{worker_id}", timeout_s=60.0)` to ensure stuck worker threads are detected by `HealingEngine`.

```python
class WorkerStatus(str, Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkerTask:
    task_id: str
    name: str
    task_type: str             # e.g., "batch_data_processing", "price_monitor", "security_scan"
    payload: Dict[str, Any]
    priority: int = 0
    timeout_seconds: float = 300.0
    notify_tts: bool = True
    notify_overlay: bool = True
    notify_telegram: bool = False
    telegram_chat_id: Optional[int] = None


@dataclass
class WorkerTelemetry:
    worker_id: str
    task_name: str
    status: WorkerStatus
    progress_pct: float        # 0.0 to 100.0
    current_step: str
    elapsed_seconds: float
    estimated_remaining_seconds: Optional[float] = None
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None
```

### 5.3 Real-Time Telemetry & Multi-Channel Notification Hooks

#### Telemetry Pipeline:
1. When a worker updates progress via `worker.update_progress(pct=45.0, step="Aggregating Q3 metrics")`:
   - An event `worker:progress` is published on `EventBus`.
   - `AlwaysOnOverlay` receives the event and updates the HUD sidebar with a real-time progress bar, task name, and percentage.
   - `DashboardServer` broadcasts the JSON telemetry over WebSocket to connected browser clients.

#### Multi-Channel Completion Dispatcher (`jarvis/workers/notifications.py`):
When a worker reaches `COMPLETED` or `FAILED`:
1. **Voice / TTS (`TTSManager.speak`)**:
   - Formulates natural Vietnamese speech: *"Thưa Ngài, tác vụ nền 'Tổng hợp dữ liệu doanh thu' đã hoàn thành trong 12 giây. Đã tạo file Excel báo cáo."*
2. **HUD Overlay (`AlwaysOnOverlay.add_turn` / notification banner)**:
   - Appends a completed task card to the HUD 5-turn history with direct links to generated artifact paths.
3. **Telegram Remote Dispatch (`TelegramBotController`)**:
   - If `notify_telegram` is True or configured in user profile:
     - Sends text summary to user's Telegram chat.
     - Uploads generated artifacts (charts, spreadsheets, PDF reports) via Telegram document/photo API.

---

## 6. Detailed Interface & Data Flow Specifications

### 6.1 End-to-End ReAct Task Execution Flow
```
User Command ("Tổng hợp file CSV trong Downloads, tính tổng doanh thu và gửi báo cáo qua Telegram")
   │
   ▼
JarvisApp.process_text_command()
   │
   ▼
LLMIntentRouter ──[Complex multi-step prompt]──► ReActTaskEngine.create_plan(goal)
   │
   ▼
TaskDAG Initialized:
  Node 1: [file_search] Find CSV files in Downloads
  Node 2: [sandbox_execute] Run python script to aggregate totals & export excel (depends on Node 1)
  Node 3: [telegram_send_document] Send report to Telegram (depends on Node 2, GATED)
   │
   ▼
ReActTaskEngine.execute_plan()
  ├─ Node 1 runs ➔ Returns list of CSV files
  ├─ Interpolates CSV paths into Node 2 parameters: {{steps.node_1.output.files}}
  ├─ Node 2 runs in CodeInterpreterSandbox ➔ Generates `revenue_report.xlsx`
  ├─ Node 2 succeeds ➔ DynamicSkillSynthesizer packages it into `jarvis/skills/csv_revenue_aggregator/`
  ├─ Node 3 triggered ➔ Safety Gate intercepts (external communication) ➔ Prompts user
  ├─ User says "Đồng ý" ➔ Node 3 executes ➔ TelegramBotController sends file
  └─ Plan COMPLETED ➔ TTS speaks summary & HUD updates
```

---

## 7. Verification & Test Strategy for R1, R2, and R5

A comprehensive test suite of **≥30 new test cases** across 3 new test modules must be implemented to achieve 100% test pass rate and zero regressions:

### 7.1 ReAct Planner Tests (`tests/unit/test_react_planner.py` - 12 Tests)
1. `test_task_dag_creation_and_topological_sort`: Validates DAG node ordering and resolution of parallel vs sequential branches.
2. `test_task_dag_cycle_detection_error`: Confirms error raising when a circular dependency is introduced.
3. `test_dynamic_parameter_interpolation_nested`: Tests resolution of `{{steps.node_1.output.data.id}}` across multi-level dicts and lists.
4. `test_planner_multi_step_sequential_execution_happy_path`: End-to-end 3-step execution with parameter passing.
5. `test_planner_parallel_independent_step_execution`: Ensures independent nodes execute concurrently in separate worker threads.
6. `test_planner_self_healing_retry_on_transient_failure`: Simulates transient exception, verifies exponential backoff and recovery.
7. `test_planner_self_reflection_alternative_tool_selection`: Simulates failed tool, verifies reflection engine switches to secondary tool.
8. `test_planner_self_healing_max_retries_exceeded_abort`: Validates clean failure state and error summary when retries exhaust.
9. `test_planner_safety_gate_interception_and_confirmation`: Verifies node pauses on `WAITING_CONFIRMATION` until token confirmed.
10. `test_planner_safety_gate_rejection_and_alternative_branch`: Verifies node handles user cancellation gracefully.
11. `test_planner_safety_gate_30s_timeout_expiration`: Tests automated expiration and cancellation of unconfirmed high-risk node.
12. `test_planner_telemetry_event_bus_emission`: Asserts `planner:step_started`, `planner:step_completed`, `planner:plan_finished` events.

### 7.2 Code Interpreter & Skill Library Tests (`tests/unit/test_skill_synthesis.py` - 10 Tests)
1. `test_sandbox_python_execution_data_processing`: Executes Python script computing CSV aggregations and asserts return data.
2. `test_sandbox_powershell_execution_safe`: Executes safe PowerShell query and validates captured output.
3. `test_sandbox_timeout_termination`: Runs infinite loop script and ensures subprocess terminates within configured timeout (e.g. 2s in test).
4. `test_sandbox_artifact_capture_image_and_excel`: Generates a `.png` chart and `.xlsx` file, verifies automatic `ArtifactInfo` indexing.
5. `test_ast_validator_blocks_forbidden_imports`: Validates `ctypes`, `win32api`, unauthorized socket tampering are rejected before execution.
6. `test_ast_validator_permits_safe_scientific_libraries`: Validates `pandas`, `numpy`, `math`, `json`, `pathlib` pass validation.
7. `test_skill_auto_packaging_creates_valid_module`: Tests `DynamicSkillSynthesizer` generates module file and `metadata.json` with correct schemas.
8. `test_skill_registry_dynamic_loading_and_introspection`: Asserts `SkillRegistry` discovers, loads, and indexes newly created skill.
9. `test_skill_registry_action_dispatcher_integration`: Verifies synthesized skill can be dispatched as a native action via `dispatcher.dispatch_action`.
10. `test_skill_metrics_and_usage_tracking`: Verifies execution count, success rate, and latency metrics increment accurately.

### 7.3 Background Sub-Agents & Telemetry Tests (`tests/unit/test_background_workers.py` - 10 Tests)
1. `test_worker_lifecycle_creation_to_completion`: Spawns worker, verifies transition from `INITIALIZING` -> `RUNNING` -> `COMPLETED`.
2. `test_worker_cooperative_cancellation`: Sets cancellation token on running worker and asserts graceful termination with `CANCELLED` status.
3. `test_sub_agent_manager_concurrency_limit`: Enqueues 6 tasks with pool limit 4, asserts queueing and non-blocking execution.
4. `test_worker_telemetry_progress_broadcasting`: Verifies intermediate progress updates emit to `EventBus` and HUD telemetry listeners.
5. `test_worker_watchdog_heartbeat_registration`: Asserts worker pulses `ResourceWatchdog.record_heartbeat` periodically.
6. `test_worker_completion_tts_notification_hook`: Verifies completion triggers TTS manager voice formulation.
7. `test_worker_completion_overlay_card_notification`: Asserts completed task card with artifact links is inserted into overlay queue.
8. `test_worker_telegram_notification_and_attachment_dispatch`: Tests formatted message and file attachment delivery to Telegram controller.
9. `test_worker_failure_error_isolation`: Simulates worker crash and ensures other sub-agents and main thread remain unaffected.
10. `test_worker_timeout_enforcement`: Tests worker hard deadline expiration and cleanup.

---

## 8. Five-Component Handoff Report

### 8.1 Observation
1. **Existing Baseline Capabilities**:
   - `jarvis/core/dispatcher.py` (lines 236-350) provides `ActionDispatcher` with dynamic introspection via `list_actions()`, schema registration, and RBAC privilege enforcement.
   - `jarvis/automation/safety_gate.py` (lines 30-120) provides `SafetyGate` implementing 30-second tokenized state machine with affirmative/negative phrase evaluation.
   - `jarvis/automation/shell_assistant.py` (lines 25-43, 529-549) defines `DANGEROUS_PATTERNS` regex and intercepts high-risk operations via `SafetyGate`.
   - `jarvis/healing/watchdog.py` (lines 120-165) provides `ResourceWatchdog` with thread heartbeat registration (`record_heartbeat`) and stale thread detection (`check_thread_health`).
   - `jarvis/healing/terminator.py` (lines 34-54, 111-220) maintains `PROTECTED_PROCESS_WHITELIST` for safe termination.
   - `jarvis/ui/overlay.py` (lines 200-300) implements `AlwaysOnOverlay` with 5-turn history deque, real-time hardware status bar, and dynamic waveform visualizer.
   - `jarvis/comms/telegram.py` (lines 42-100) implements `TelegramBotController` with whitelist authorization.
2. **Existing Test Suite Baseline**:
   - `tests/e2e/test_tiers_1_to_4.py` executes 93 comprehensive end-to-end tests across all prior milestones (M1–M6).
   - In live test execution, 88/93 tests pass immediately in headless mode; 5 minor test fixtures require small parameter adjustments (e.g. `WeatherData` missing `wind_kph`, `subprocess.TimeoutExpired` patch import).
3. **Absence of Autonomous Planner & Skill Library**:
   - No `jarvis/planner/`, `jarvis/sandbox/`, `jarvis/skills/`, or `jarvis/workers/` subdirectories exist yet in the codebase. All 3 subsystems must be created from the ground up while maintaining 100% backwards compatibility with all 92 existing modules.

### 8.2 Logic Chain
1. **R1 (ReAct Planner)**:
   - Because complex tasks require multi-step ordering, independent tasks must run in parallel while dependent tasks await predecessor outputs.
   - Using a DAG data structure with topological sorting and cycle detection guarantees deterministic scheduling.
   - Dynamic parameter interpolation (`{{steps.node_id.output}}`) provides seamless data flow between steps without hardcoding.
   - Integrating `SafetyGate` ensures high-risk steps automatically pause with a 30s token and prompt the user via TTS/Overlay before executing.
   - Self-reflection with heuristic triage and LLM fallback allows JARVIS to auto-heal when steps fail.
2. **R2 (Skill Synthesis & Sandbox)**:
   - To safely execute self-generated Python/PowerShell code, static AST validation must run before execution to reject dangerous syscalls, unauthorized memory inspection, or forbidden modules.
   - Running in an isolated subprocess with a scratch directory and wall-clock timeout protects the host OS from runaway loops.
   - Successful tools must be auto-packaged as modular Python packages with `metadata.json` so `SkillRegistry` can index them and register them into `ActionDispatcher` for zero-shot re-use in future sessions.
3. **R5 (Background Workers & Delegation)**:
   - Long-running background tasks must not block the main voice loop or Tkinter UI thread.
   - Managing workers via a bounded `ThreadPoolExecutor` with cooperative cancellation tokens and `ResourceWatchdog` heartbeats ensures deadlock-free execution.
   - Progress events emitted to `EventBus` dynamically update the `AlwaysOnOverlay` HUD sidebar and `DashboardServer` WebSockets.
   - Multi-channel completion hooks ensure the user is notified via voice TTS, HUD cards, and Telegram with attached files.

### 8.3 Caveats
1. **Network Independence for Testing**: All unit and integration tests must run 100% hermetically in headless mode without requiring active external internet access, live API keys, or cloud LLM endpoints (using mock LLM clients and mock subprocess runners where necessary).
2. **Subprocess Isolation on Windows**: On Windows OS, subprocess timeout handling must ensure child process trees are terminated properly (using `taskkill /F /T /PID` or `proc.kill()` with process group handling).
3. **Tkinter Threading**: UI updates to `AlwaysOnOverlay` must always be scheduled onto the Tkinter main thread via `root.after()` or queue mechanisms to prevent Tkinter cross-thread exceptions.

### 8.4 Conclusion
The architecture defined herein provides a modular, secure, and extensible implementation for Requirements R1, R2, and R5. It cleanly extends the existing `JarvisApp`, `ActionDispatcher`, `SafetyGate`, `ResourceWatchdog`, and `AlwaysOnOverlay` without introducing breaking changes to existing subsystems or tests.

### 8.5 Verification Method
To independently verify the implementation:
1. **Execute E2E Baseline Test Suite**:
   ```powershell
   pytest tests/e2e/test_tiers_1_to_4.py -v
   ```
2. **Execute R1, R2, and R5 Unit Test Suites**:
   ```powershell
   pytest tests/unit/test_react_planner.py tests/unit/test_skill_synthesis.py tests/unit/test_background_workers.py -v
   ```
3. **Execute System Health Check**:
   ```powershell
   python -m jarvis health-check
   ```
   *Expected Outcome*: Return code `0`, diagnostic output reporting all subsystems including ReAct Planner, Skill Synthesis Sandbox, and Background Workers as `READY / OK`.
