# CLAUDE.md — JARVIS Project Instructions

> Durable project instructions for Claude Code and coding agents.
> For historical PR logs, past release snapshots, and prior incident records, see `docs/CLAUDE_HISTORICAL.md`.
> Before non-trivial work, read `docs/PROJECT_STATE.md`.

---

## 0. Current Baseline

- **Current Runtime Version:** `5.2.1` (`jarvis.__version__` in `jarvis/__init__.py`).
- **Latest Formal Tagged Release:** `v5.0.0` (2026-09-03).
- **Active Branch:** `fix/truthfulness-bugs-1-to-6`.
- **Engineering Status:** `PASS engineering` (Unit tests 2,978+ passed, 0 failed; Security scanner 0 findings on 210 files).
- **Product GO Gate:** `CONDITIONAL GO (Internal Pilot)` — Live voice 50-case recall, 10-workflow Real-OS verification, and clean-machine installer remain pending hardware/operator test (`docs/ACCEPTANCE_GATES_PROTOCOL.md`).
- **Rule on Commits/SHAs:** Never treat documented commit SHAs as live pointers. Always run `git fetch origin --prune && git rev-parse origin/main`.

---

## 1. Project Identity & Architecture

JARVIS is a Windows-first autonomous personal AI assistant in Python (>=3.10, CI on 3.13).
Original feature concepts designed by **Huynh Minh Hoa ([@hoahuynh19a-crypto](https://github.com/hoahuynh19a-crypto))**.

- **Package:** `jarvis-assistant` (dynamic versioning via `jarvis.__version__`).
- **Console Entry Point:** `jarvis = "jarvis.__main__:main"`.
- **Tray Entry Point:** `jarvis-tray = "jarvis.__main__:main_tray"`.
- **Core Subsystems:**
  - `jarvis/core/` — Lifecycle, config, event bus, `ActionDispatcher`, runaway guards.
  - `jarvis/core/handlers/` — Domain action handlers (system, service, automation).
  - `jarvis/agent/` & `jarvis/planner/` — ReAct agent, DAG planner, deterministic `SafetyGateInterceptor`.
  - `jarvis/sandbox/` — Kernel-enforced OS Restricted Token + Job Object + AppContainer network isolation.
  - `jarvis/browser/` — Playwright/CDP driver, session persistence, truthful scraping.
  - `jarvis/audio/`, `jarvis/stt/`, `jarvis/tts/` — VAD, wake-word cascade, Faster-Whisper, Edge-TTS/SAPI5.
  - `jarvis/ui/` & `jarvis/ui/terminal/` — Always-on HUD overlay, Web dashboard, system tray, Terminal Control Center.
  - `jarvis/comms/` — Telegram, Discord, Zalo OA, mobile bridge with fail-closed allowlists and rate limiters.

---

## 2. Durable Invariants (Must Never Regress)

### 2.1 Truthfulness First (Anti-Fabrication)
- **Zero Ghost Success:** An action failure must remain a failure end-to-end. Never upgrade `success=False` or status `"failed"/"error"` to `True`.
- **Backend-Verified Outcomes:** Process kill, service restart, packet capture, email quarantine, or external app launch must report real observed OS/API state. No fabricated metrics (e.g., invented reclaimed RAM or mock protocol percentages).
- **Truthful Error Codes:** Return standard error codes (`NOT_CONFIGURED`, `ACTION_NOT_FOUND`, `LAUNCH_RATE_LIMITED`, `WEBHOOK_INVALID_URL`). Never return fake success payloads.

### 2.2 Safety & Authorization
- **Deterministic High-Risk Gating:** `SafetyGateInterceptor.is_high_risk()` classifies destructive operations (shutdown, reboot, process kill, file deletion) deterministically by pattern/name, never by LLM discretion.
- **One-Shot Token Binding:** Confirmation tokens bind strictly to `action_name` + exact parameters and expire after 30 seconds. One-time consumption prevents replay attacks.
- **Privilege Separation:** `ActionDispatcher.bypass_security` is RBAC-only and never bypasses destructive action safety gates in production.

### 2.3 Sandbox Isolation
- **Dual-Layer Kernel Isolation:** `CodeInterpreterSandbox.execute_python()` executes via AppContainer with safe fallback to Windows Restricted Token (Low Integrity SID `S-1-16-4096`) + Windows Job Object (1 process limit, 256MB RAM cap).
- **Readiness Sentinel:** Execution success requires observing the startup sentinel before user code runs. Bootstrap failures fail-closed and are not retried unless strictly `retry_safe=True`.
- **Bounded I/O:** Child stdout/stderr streams are concurrently drained with a 1MB memory ceiling to prevent pipe deadlocks and host RAM exhaustion.

### 2.4 Browser Automation (T-01 Contract)
- `jarvis/browser/driver.py` + `actions.py` + `agent.py` form the single canonical browser seam.
- Real Playwright Chromium or CDP attach required for interactive actions (click, type, screenshot). HTTP fallback is strictly read-only.
- Thread affinity: Playwright sync handles remain serialized on their single owner executor thread.

### 2.5 Terminal Control Center
- `jarvis/ui/terminal/` is a thin presentation and routing layer only. No duplicated business logic or private safety dispatchers.
- Batch action `[A]` requires `>= 2` eligible actions and strictly excludes destructive operations.

---

## 3. Developer Workflow & Quality Gates

### 3.1 Startup Routine
1. Run `git status`, `git branch --show-current`, and check recent commits.
2. Read current task requirements and relevant tests before touching code.
3. Code truth over documentation: When code and docs diverge, trust code + CI evidence.

### 3.2 Git Rules
- Never push directly to `main`. Work on focused feature/fix branches.
- Commit clean, atomic diffs. Never commit `.env`, credentials, `dist/`, `build/`, or generated caches.
- Keep line endings LF normalized.

### 3.3 Verification Commands
```powershell
# Fast static check
ruff check jarvis tests scripts/build_installer.py
mypy jarvis

# Core unit test suite
python -m pytest tests/unit/ -q --timeout=60 --tb=short

# Security scan
python tools/security_scanner.py --path jarvis --severity-threshold low
```

### 3.4 Definition of Done
A task is NOT done until:
1. Targeted and unit tests pass.
2. Ruff and static checks pass clean.
3. Relevant documentation (`CHANGELOG.md`, `docs/PROJECT_STATE.md`) is synchronized.
4. No simulated outcomes or unverified success claims were introduced.
