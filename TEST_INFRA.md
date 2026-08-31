# E2E Test Infra: JARVIS v4.1.0 Security & Stability Hardening

## Test Philosophy
- Opaque-box, requirement-driven testing derived strictly from `ORIGINAL_REQUEST.md`.
- Zero coupling to internal private state where public interfaces exist.
- Non-mock real OS execution for security boundaries on Windows.
- Tiered methodology:
  - Tier 1: Feature Coverage (>=5 test cases per requirement)
  - Tier 2: Boundary & Corner Cases (>=5 test cases per requirement)
  - Tier 3: Cross-Feature Combinations (Pairwise coverage)
  - Tier 4: Real-World Application Workloads
  - Tier 5: White-Box Adversarial Hardening

## Feature Inventory & Test Mapping
| # | Feature | Requirement | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|-------------|:------:|:------:|:------:|:------:|
| 1 | R1: `__globals__` Sandbox Escape Patch | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | R2: Night Shift Daemon Audit & Sandboxing | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 3 | R3: AppContainer Network Sandbox Socket Blocking | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 4 | R4: Prompt-Injection Defense Pipeline | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 5 | R5: Comms Token Bucket Rate-Limiting | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |
| 6 | R6: Discord Slash Commands & Watchdog Chaos Test | ORIGINAL_REQUEST §R6 | 5 | 5 | ✓ | ✓ |
| 7 | R7: Real STT Benchmark on CUDA & Docs Classification | ORIGINAL_REQUEST §R7 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test Runner: `pytest`
- Directory: `tests/e2e/`
  - `tests/e2e/test_r1_sandbox_globals_e2e.py`
  - `tests/e2e/test_r2_night_shift_e2e.py`
  - `tests/e2e/test_r3_network_sandbox_e2e.py`
  - `tests/e2e/test_r4_prompt_injection_e2e.py`
  - `tests/e2e/test_r5_rate_limiting_e2e.py`
  - `tests/e2e/test_r6_discord_watchdog_e2e.py`
  - `tests/e2e/test_r7_stt_benchmark_e2e.py`
  - `tests/e2e/test_combined_security_stability_e2e.py`

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Web Scraping with Embedded Jailbreak & Night Shift Scheduled Task | R1, R2, R4 | High |
| 2 | Heavy Inbound Attack across Discord/Telegram/Zalo with Rapid Injection Payloads | R4, R5, R6 | High |
| 3 | Sandboxed AppContainer Execution with Socket Exfiltration & Process Crash Recovery | R1, R3, R6 | High |
| 4 | Full Audio Processing & STT Pipeline with Concurrency & Throttling | R5, R7 | Medium |
| 5 | Complete System Stress Test: 4 Comms Channels + Sandbox + Watchdog Under Load | R1, R2, R3, R4, R5, R6, R7 | High |

## Coverage Thresholds
- Minimum Tier 1 Test Cases: 35 (5 per requirement × 7)
- Minimum Tier 2 Test Cases: 35 (5 per requirement × 7)
- Minimum Tier 3 Test Cases: 7 cross-feature interaction scenarios
- Minimum Tier 4 Test Cases: 5 end-to-end workload application scenarios
- Total Target: >= 82 E2E test cases
