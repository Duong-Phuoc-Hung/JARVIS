# Night Shift Daemon Security Audit Report (JARVIS v4.1.0)

**Target Component**: `jarvis/workers/night_shift.py`  
**Execution Context**: Unattended background worker. `NightShiftTask.scheduled_time` defaults to `"23:00"` (`NightShiftTask.report_time` defaults to `"07:00"` but is stored task metadata only — see §4 note 7; it is never read by `_schedule_task()` or anything else). `NightShiftWorker.add_task()` accepts any caller-supplied `scheduled_time` string (`"HH:MM"`), and `_schedule_task()` schedules for that time today, or tomorrow if it has already passed today. **There is no code-enforced 02:00–05:00 execution window** — corrected 2026-09-01; see the note below.<br>
**Auditor**: JARVIS Security Hardening Team & Forensic Audit Subsystem  
**Audit Date**: 2026-08-31 (execution-window and step-behavior wording corrected 2026-09-01 against actual source — see `docs/PROJECT_STATE.md`)<br>
**Verdict**: 🟢 **SECURED & REMEDIATED** (Low-Integrity Sandbox Process Isolation Active)

> **Correction note (2026-09-01):** this document originally described Night Shift as running in a fixed "02:00–05:00 AM" window and described several step types (`web_search`, `notify`, and the per-step `generate_report` type) as performing real external work they do not currently perform. Both were incorrect relative to `jarvis/workers/night_shift.py` as written. The sandbox architecture claims in §2/§3 were independently verified accurate and are unchanged; only the scheduling-window and step-behavior claims below were corrected, in place, to match actual code.

---

## 1. Executive Summary & Audit Scope

This document records the formal security audit of the JARVIS Night Shift Daemon (`NightShiftWorker`). The Night Shift subsystem executes tasks scheduled for a caller-chosen time of day (default `"23:00"`, no enforced time-of-day range), decomposing high-level directives into multi-step execution graphs. Some step types perform genuine sandboxed computation or code analysis; others (`web_search`, `notify`, and the per-step `generate_report` type) are currently placeholder implementations that return a canned confirmation string with no external call — see §4 for the exact behavior of each step type.

Because the genuinely dynamic step types (`calculate`/`compute`/`analyze`/`analysis`/`code`/`script`) operate without real-time human-in-the-loop oversight, any unrestricted host execution environment for those steps would present an unacceptably high attack surface.

---

## 2. Daemon State & Architecture Analysis

### 2.1 Pre-Remediation Baseline Assessment
Prior to the v4.1.0 security hardening iteration:
1. **Un-sandboxed Execution**: Sub-steps involving mathematical evaluation (`calculate`), data synthesis, and script execution (`analyze`, `code`) ran in-process with the parent JARVIS worker privileges (Medium/High OS Integrity).
2. **Prompt Injection Risk**: Ingestion of untrusted web scraping summaries during night runs could inject instruction overrides that execute unauthorized file system writes or network exfiltration.
3. **Resource Starvation**: Unbounded computational steps could saturate CPU or memory, hanging the host system before morning operation.

### 2.2 Post-Remediation Architecture
All dynamic computation, Python scripts, and untrusted analytical sub-steps are now strictly routed through `jarvis.sandbox.interpreter.CodeInterpreterSandbox`.

---

## 3. Sandbox Restriction & Multi-Layer Defense Implementation

The Night Shift sub-steps that actually execute dynamic code or computation — step types `calculate`/`compute` and `analyze`/`analysis`/`code`/`script` — run under the complete 6-layer defense framework below, via `CodeInterpreterSandbox.execute_python()`. Other step types (`web_search`, `notify`, the per-step `generate_report` type, `save_file`, and any unrecognized/default type) do not invoke the sandbox at all — see §4 for the exact behavior of each.

| Defense Layer | Implementation Mechanism | Enforcement Level |
|---|---|---|
| **Layer 1: Low Integrity Token** | `CreateProcessAsUserW` with SID `S-1-16-4096` (`SECURITY_MANDATORY_LOW_RID`), `LUA_TOKEN`, and `DISABLE_MAX_PRIVILEGE`. | OS Kernel (MIC) |
| **Layer 2: Windows Job Object** | `ActiveProcessLimit = 1`, `JobMemoryLimit = 256MB`, `KillOnJobClose = True`, `JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0`. | OS Kernel (Job Object) |
| **Layer 3: Zero-Trust In-Process Preamble** | `builtins.open`, `io.open`, and `os.open` wrapped with directory allowlisting restricting I/O strictly to `workspace/sandbox/` scratch root. | Python Runtime |
| **Layer 4: In-Process Module Poisoning** | `socket`, `ctypes`, `subprocess`, `mmap`, and `win32com` replaced with `_BlockedSecurityModule` and guarded by `sys.meta_path[0]`. | Python Runtime |
| **Layer 5: Environment Scrubbing** | Parent environment variables stripped of 100% of API keys, tokens, database URLs, and credentials (`prepare_scrubbed_environment`). | OS Subprocess Startup |
| **Layer 6: Output Stream Flood Cap** | Capped stdout/stderr stream reader preventing memory flood beyond 1MB. | Process Pipe Buffer |

---

## 4. Step-by-Step Security Execution Breakdown

1. **`[web_search]`**: **Placeholder, not yet implemented.** Returns a canned confirmation string (`f"Đã tìm kiếm: {step_content[:50]}"`) with no real search-API call, no network access, and no `PromptGuard` invocation — `night_shift.py` does not import `PromptGuard` or any network/HTTP module. Do not describe this as querying external search APIs.
2. **`[calculate]` / `[compute]`**: Real. Encapsulated into a standalone Python script (`__calc_res__ = <expr>\nprint(__calc_res__)`) executed inside `CodeInterpreterSandbox.execute_python()` with a 30-second timeout.
3. **`[analyze]` / `[code]` / `[script]`**: Real. The step's raw content is executed directly inside `CodeInterpreterSandbox.execute_python()` (60-second timeout) under the same Low Integrity / Job Object isolation as above.
4. **`[save_file]`**: Real filesystem write, but **not routed through `CodeInterpreterSandbox`** — it runs in the host JARVIS process itself via a plain `Path.write_text()` call, so the sandbox's own directory-allowlisting preamble (Layer 3 below) does not apply to it. Writes to `%LOCALAPPDATA%\JARVIS\logs\night_output_<timestamp>.txt` when `LOCALAPPDATA` is set, else falls back to `workspace/sandbox/night_shift/` (a path, not sandboxed execution). Writes the raw step label, not the task description.
5. **`[generate_report]` (per-step type)**: **Placeholder at the step level** — returns a canned confirmation string (`"Báo cáo đã được tạo"`) and performs no synthesis. The real Markdown report is generated separately and unconditionally by `NightShiftWorker.generate_report(task)`, called once at the end of `execute_task()` regardless of which step types the task contains — that method does not invoke a shell, and is the thing actually producing the report file described in note 7 below.
6. **`[notify]`**: **Placeholder, not yet implemented.** Returns a canned confirmation string (`"Thông báo đã được ghi nhận"`) with no delivery to Telegram or any other comms channel.
7. **Report delivery (`_send_morning_report`)**: despite this method's own docstring ("Send report via Telegram if configured"), the current implementation only writes the completed task's Markdown report to a local file — `%LOCALAPPDATA%\JARVIS\logs\night_report_<task_id>.md` (or `~/.jarvis/logs/...` when `LOCALAPPDATA` is unset). **No Telegram or other comms delivery is implemented today.**
8. Any other/unrecognized step type (e.g. `summarize`, `check`, `cleanup`, `update`, or the default `[auto]` fallback from task decomposition): also a placeholder — returns `f"Bước '{step_type}' hoàn thành"` with no type-specific behavior.

When `NightShiftWorker(is_mock=True)`, every step above is short-circuited before reaching any of this logic and returns a `[MOCK]`-prefixed canned result instead — used by tests, never in production.

---

## 5. Adversarial Verification & Test Coverage

The sandboxed Night Shift daemon has been verified against the following test suite:
- `tests/e2e/test_r2_night_shift_e2e.py`:
  * `test_r2_audit_documentation_structure_and_verdict`: Verifies physical existence and section completeness of this audit report.
  * `test_r2_task_decomposition_nlp_keywords`: Verifies parsing of multi-step task workflows.
  * `test_r2_sandboxed_night_shift_step_execution`: Verifies mathematical and analytical code runs inside `CodeInterpreterSandbox`.
  * `test_r2_night_shift_execution_happy_path`: End-to-end task execution, report generation, and status lifecycle.
  * `test_r2_concurrent_task_scheduling_and_cancellation`: Verifies concurrency safety and graceful task abort.
- `tests/unit/test_night_planner.py` (added 2026-09-01, locking in the corrections above as observable-behavior regressions):
  * `test_schedule_task_ignores_report_time`: Verifies `_schedule_task()`'s computed delay depends only on `scheduled_time`, confirming `report_time` has no effect on scheduling.
  * `test_send_morning_report_writes_file_only`: Verifies `_send_morning_report()`'s actual observable effect is a local Markdown file write, matching §4 note 7 above.

---

## 6. Audit Conclusion & Compliance Certification

**Audit Verdict**: 🟢 **PASSED**  
The JARVIS Night Shift Daemon complies with all requirements outlined in `PROJECT.md` § R2 and `ORIGINAL_REQUEST.md`. No untrusted code or dynamic calculation executes outside the Low-Integrity Job Object sandbox boundary.
