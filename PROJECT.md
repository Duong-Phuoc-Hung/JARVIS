# Project: JARVIS v4.1.0 Security & Stability Hardening

## Architecture
JARVIS v4.1.0 is an AI assistant running on Windows 11 64-bit Python 3.13. This project fixes 7 critical security vulnerabilities and stability deficits across 4 core subsystems:
1. **Sandbox & Security Subsystem**: `jarvis/sandbox/security.py`, `jarvis/sandbox/validator.py`, and `jarvis/workers/night_shift.py`.
2. **AI Defense Subsystem**: `jarvis/security/prompt_guard.py`, `jarvis/browser/`, and `jarvis/skills/screen_context/`.
3. **Communications Subsystem**: `jarvis/comms/rate_limiter.py`, `jarvis/comms/telegram.py`, `zalo.py`, `discord.py`, and `mobile_bridge.py`.
4. **Resilience & Performance Subsystem**: `jarvis/automation/safety_gate.py`, `jarvis/healing/`, and `jarvis/stt/`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R1: Sandbox `__globals__` Escape Patch | Neutralize `type(fn).__call__.__globals__` access in sandbox preamble via private scope, metaclass protection, and globals purge. | M1 | ORIGINAL_REQUEST §R1 |
| 2 | R1: Adversarial Non-Mock Test | Verify class-level `__globals__` access is blocked and 15 existing sandbox tests pass. | M1 | ORIGINAL_REQUEST §R1 |
| 3 | R2: Night Shift Daemon Audit Report | Document audit findings in `docs/night_shift_audit.md` detailing un-sandboxed daemon state. | M2 | ORIGINAL_REQUEST §R2 |
| 4 | R2: Night Shift Sandboxing | Route night task execution through `CodeInterpreterSandbox` with Job Object and Low Integrity restrictions. | M2 | ORIGINAL_REQUEST §R2 |
| 5 | R3: AppContainer Network Blocking B2 | Wire `SECURITY_CAPABILITIES` with 0 network capabilities into Windows AppContainer subprocess creation. | M3 | ORIGINAL_REQUEST §R3 |
| 6 | R3: Real OS AppContainer Socket Test | Test `socket.connect(("8.8.8.8", 80))` raises `PermissionError`/`OSError` under `@pytest.mark.real_os` without mock. | M3 | ORIGINAL_REQUEST §R3 |
| 7 | R4: Prompt-Injection Defense Pipeline | Implement `PromptGuard` with Unicode normalization, template neutralization, and XML isolation tags. | M4 | ORIGINAL_REQUEST §R4 |
| 8 | R4: Browser & Screen Context Integration | Integrate `PromptGuard` into WebScraper, CDP controller, and ScreenContext before LLM prompts. | M4 | ORIGINAL_REQUEST §R4 |
| 9 | R4: Adversarial Injection Tests | Verify >=5 injection payloads (instruction override, script jailbreak, role spoof, etc.) are sanitized and not executed. | M4 | ORIGINAL_REQUEST §R4 |
| 10 | R5: Token Bucket Rate Limiter | Implement thread-safe `TokenBucketRateLimiter` supporting burst limit, rate per minute, and HTTP 429 status. | M5 | ORIGINAL_REQUEST §R5 |
| 11 | R5: Comms Channel Integration & Config | Add rate limiting per user_id to Telegram, Zalo, Discord, and Mobile Bridge with YAML config in `config/default_config.yaml`. | M5 | ORIGINAL_REQUEST §R5 |
| 12 | R5: Rate Limit Throttle Tests | Verify 30 req/s from single user_id yields >=50% HTTP 429 rejections across all 4 channels. | M5 | ORIGINAL_REQUEST §R5 |
| 13 | R6: Discord Functional Slash Command Tests | Add functional tests for `/help`, `/status`, `/calc`, `/skills`, and Rich Embed generation in Discord controller. | M6 | ORIGINAL_REQUEST §R6 |
| 14 | R6: Safety Gate Watchdog Chaos Test | Chaos test killing supervised subprocesses 3 times, verify MTTR < 10s per recovery, and log MTTR to stdout. | M6 | ORIGINAL_REQUEST §R6 |
| 15 | R7: Real STT Benchmark on CUDA | Benchmark Faster-Whisper `large-v3` on CUDA with synthetic 1s, 3s, 5s, 10s audio buffers and calculate real RTF. | M7 | ORIGINAL_REQUEST §R7 |
| 16 | R7: Benchmark Results Documentation | Create `docs/benchmark_results.md` with real CUDA metrics and mark old adapter measurements as `[MOCK — đo trên adapter, không phản ánh model thật]`. | M7 | ORIGINAL_REQUEST §R7 |
| 17 | Final: E2E Test Suite Validation | Execute comprehensive E2E test suite across all 7 items (Tiers 1-4) with 100% pass rate. | M8 | ORIGINAL_REQUEST Acceptance Criteria |
| 18 | Final: Adversarial Coverage Hardening | Run white-box adversarial stress tests (Tier 5) across all modified modules. | M8 | Orchestrator Quality Standard |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Suite Track | Design and construct opaque-box E2E test harness covering all 7 requirements (Tiers 1-4) and publish `TEST_READY.md`. | none | DONE |
| M1 | R1: Sandbox `__globals__` Escape Patch | Patch `jarvis/sandbox/security.py`, implement adversarial tests, verify no regression on 15 existing sandbox tests. | none | DONE |
| M2 | R2: Night Shift Daemon Audit & Sandboxing | Create `docs/night_shift_audit.md`, sandbox `jarvis/workers/night_shift.py` via `CodeInterpreterSandbox`, add verification tests. | none | DONE |
| M3 | R3: AppContainer Network Sandbox B2 | Implement AppContainer network socket blocking and real OS non-mock test `@pytest.mark.real_os`. | M1 | DONE |
| M4 | R4: Prompt-Injection Defense Pipeline | Implement `jarvis/security/prompt_guard.py`, integrate with browser/screen_context, add adversarial test suite (>=5 payloads). | none | DONE |
| M5 | R5: Comms Token Bucket Rate Limiting | Implement `TokenBucketRateLimiter`, update `config/default_config.yaml`, integrate with Telegram, Zalo, Discord, Mobile Bridge, write tests. | none | DONE |
| M6 | R6: Discord Tests & Watchdog Chaos Test | Implement Discord slash-command/Rich Embed tests, implement Watchdog 3x chaos test with MTTR measurement. | none | DONE |
| M7 | R7: Real STT Benchmark on CUDA & Docs | Measure Faster-Whisper `large-v3` CUDA RTF on 1s/3s/5s/10s, write `docs/benchmark_results.md`, mark mock numbers. | none | DONE |
| M8 | Final Milestone: 100% E2E Pass & Verification Gate | Pass 100% of test suite (1,189 tests), obtain APPROVE review and CLEAN forensic audit. | E2E, M1-M7 | DONE |

## Interface Contracts
### `jarvis.security.prompt_guard` ↔ Browser & Screen Context
- `PromptGuard.sanitize(text: str, source: str = "web") -> SanitizationResult(str)`: Returns XML-quarantined string `<untrusted_external_content source="...">...</untrusted_external_content>` while exposing inspection attributes `.clean_text`, `.is_suspicious`, `.risk_level`, `.detected_patterns`.
- `PromptGuard.contains_injection(text: str) -> tuple[bool, str | None]`: Checks for malicious instruction override signatures.

### `jarvis.comms.rate_limiter` ↔ Comms Channels (Telegram, Zalo, Discord, Mobile Bridge)
- `TokenBucketRateLimiter(rate_per_minute: float = 60.0, burst_limit: int = 10, requests_per_minute: float | None = None)`
- `limiter.acquire(user_id: str | int) -> RateLimitResult`: Evaluates as boolean and unpacks as `(allowed: bool, retry_after_s: float)`.
- Rejections return standard HTTP 429 status response.

### `jarvis.workers.night_shift` ↔ `jarvis.sandbox.security`
- Night Shift background execution delegates untrusted/dynamic script steps to `CodeInterpreterSandbox` using Low Integrity Token and Job Object restrictions.

## Code Layout
- `jarvis/sandbox/security.py`: Sandbox bootstrap preamble, AppContainer and Low Integrity process isolation.
- `jarvis/workers/night_shift.py`: Night shift worker daemon with sandbox execution wrapper.
- `jarvis/security/prompt_guard.py`: Prompt injection sanitization and XML quarantine pipeline.
- `jarvis/comms/rate_limiter.py`: Token bucket rate limiter.
- `jarvis/comms/`: Telegram, Zalo, Discord, and Mobile Bridge inbound message handlers.
- `jarvis/automation/safety_gate.py`: Safety gate confirmation and watchdog supervision.
- `jarvis/stt/`: Faster-Whisper STT engine and benchmarking scripts.
- `docs/night_shift_audit.md`: Formal Night Shift daemon security audit report.
- `docs/benchmark_results.md`: Formal STT CUDA benchmark report with RTF metrics and mock data classification.
- `tests/unit/`: Unit tests for rate limiting, discord controller, prompt guard, and watchdog chaos.
- `tests/integration/`: Integration tests for sandbox OS boundaries and AppContainer socket blocking.
- `tests/e2e/`: E2E test suite covering all 7 requirements.
