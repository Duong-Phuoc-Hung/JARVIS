# E2E Test Infra: JARVIS Autonomous Agentic Superpower Upgrade

## Test Philosophy
- Opaque-box & unit integration tests derived from user requirements in `ORIGINAL_REQUEST.md`.
- Zero-hardware, zero-cloud live API dependency: 100% deterministic test execution using hermetic mocks and multi-tier fallbacks.
- Dual testing methodology: Unit subsystem verification (Tiers 1 & 2) + Cross-feature interaction (Tier 3) + Real-world multi-step autonomous scenarios (Tier 4).

## Feature Inventory & Test Coverage Goals
| # | Feature | Source (Requirement) | Tier 1 (Happy Path) | Tier 2 (Boundary & Corner) | Tier 3 (Pairwise / Cross) | Tier 4 (Real-World) |
|---|---------|---------------------|:-------------------:|:--------------------------:|:-------------------------:|:-------------------:|
| 1 | Autonomous ReAct Planner | ORIGINAL_REQUEST §14-19 | >=3 | >=3 | >=2 | >=1 |
| 2 | Self-Healing & Reflection | ORIGINAL_REQUEST §17 | >=2 | >=2 | >=1 | >=1 |
| 3 | Safety Gate Mode | ORIGINAL_REQUEST §18 | >=2 | >=2 | >=1 | >=1 |
| 4 | Code Interpreter Sandbox | ORIGINAL_REQUEST §20-24 | >=3 | >=3 | >=1 | >=1 |
| 5 | Persistent Skill Library | ORIGINAL_REQUEST §23 | >=2 | >=2 | >=1 | >=1 |
| 6 | Browser Automation Agent | ORIGINAL_REQUEST §25-30 | >=3 | >=3 | >=1 | >=1 |
| 7 | Computer-Use Vision & GUI | ORIGINAL_REQUEST §31-36 | >=3 | >=3 | >=1 | >=1 |
| 8 | Background Workers | ORIGINAL_REQUEST §37-41 | >=2 | >=2 | >=1 | >=1 |
| 9 | HUD Telemetry & Memory | ORIGINAL_REQUEST §42-47 | >=2 | >=2 | >=1 | >=1 |
| 10| System Health Check | ORIGINAL_REQUEST §51 | >=1 | >=1 | >=1 | >=1 |

## Test Architecture & Directory Layout
- `tests/unit/test_react_planner.py`: ReAct engine, DAG cycle detection, parameter interpolation, reflection triage, safety gate tokens.
- `tests/unit/test_skill_synthesis.py`: Code interpreter sandbox, AST security validator, timeout bounds, artifact capture, persistent skill registry.
- `tests/unit/test_background_workers.py`: Sub-agent worker lifecycle, concurrency limits, watchdog heartbeats, telemetry broadcasting, notification hooks.
- `tests/unit/test_browser_agent.py`: Multi-tier browser driver, dynamic SPA scraping, table extraction, form fill, session cookies, price comparison.
- `tests/unit/test_computer_use_vision.py`: 1000x1000 coordinate normalization, bounding box calculations, visual verifier pixel diff, GUI actor verified click/type.
- `tests/unit/test_hud_telemetry_and_memory.py`: AlwaysOnOverlay Task DAG / Code log rendering, SQLiteMemoryStore tasks/browser schemas.
- `tests/e2e/test_autonomous_workflows.py`: Multi-step real-world autonomous workflows combining Planner + Sandbox + Browser + Vision + Background Workers + HUD.

## Target Thresholds
- Baseline test pass rate: 100% of 921+ existing tests pass without regressions.
- New test count: >= 30 new comprehensive tests.
- Total test count: >= 951 tests passing.
- System health-check: `python -m jarvis health-check` exits with status code 0 and all modules reporting OK/READY.
