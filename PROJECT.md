# Project: JARVIS Comprehensive Security Audit, Hardening & Tooling Sprint

## Architecture
JARVIS is an autonomous AI voice assistant and desktop automation platform for Windows 11 (Python 3.13).
- **Core Subsystems (`jarvis/core/`)**: EventBus, ActionDispatcher, JarvisApp lifecycle, ConfigManager, Logger, RunawayGuard.
- **Security & Safety (`jarvis/security/`, `jarvis/automation/safety_gate.py`, `jarvis/planner/safety_interceptor.py`)**: SafetyInterceptor, AccessControl, TokenSecurity, JobObject sandbox, AST validation.
- **Automation & OS Control (`jarvis/automation/`, `jarvis/browser/`, `jarvis/os_control/`)**: ComputerController, ShellAssistant, BrowserController, DesktopAutomation.
- **Communications & Web (`jarvis/comms/`, `jarvis/web/`)**: TelegramBot, DiscordBot, Zalo, IMAP, WebSearch, TTLCache.
- **LLM & Speech (`jarvis/llm/`, `jarvis/stt/`, `jarvis/tts/`)**: Intent routing, Tool calling schemas, Whisper STT, TTS manager.

## Feature Inventory & Vulnerability Catalog
| # | Defect ID | Severity | Description | Module / File | Milestone | Status |
|---|-----------|:--------:|-------------|---------------|:---------:|:------:|
| 1 | VULN-CAT1-01 | Critical | Shell Injection via `shell=True` fallback in `ShellAssistant` | `jarvis/automation/shell_assistant.py` | M1 | RESOLVED |
| 2 | VULN-CAT1-02 | Critical | Unrestricted Shell Execution Sink (`shell_exec` missing from `HIGH_RISK_ACTIONS`) | `jarvis/plugins/shell.py`, `jarvis/planner/safety_interceptor.py` | M1 | RESOLVED |
| 3 | VULN-CAT1-03 | High | Path traversal in `BrowserActionExecutor.download_file` | `jarvis/browser/actions.py` | M1 | RESOLVED |
| 4 | VULN-CAT1-04 | High | Arbitrary directory deletion without canonical boundary check | `jarvis/automation/shell_assistant.py` | M1 | RESOLVED |
| 5 | VULN-CAT1-05 | Medium | Rate limiter state explosion / memory leak (uncalled `cleanup_idle`) | `jarvis/comms/rate_limiter.py` | M1 | RESOLVED |
| 6 | VULN-CAT2-01 | Critical | Unauthenticated Web Dashboard with Wildcard CORS (`*`) leaking `/api/config` and `/api/logs` | `jarvis/ui/dashboard.py` | M1 | RESOLVED |
| 7 | VULN-CAT2-02 | High | Hardcoded DEBUG level in rotating file handler on disk | `jarvis/core/logger.py` | M1 | RESOLVED |
| 8 | VULN-CAT2-03 | High | API keys in URL query params leaking into `RequestException` messages | `jarvis/web/weather.py`, `jarvis/vision/screen.py` | M1 | RESOLVED |
| 9 | VULN-CAT2-04 | Medium | Plaintext credentials in env override warning and `ConfigNode.__repr__` | `jarvis/core/config.py` | M1 | RESOLVED |
| 10 | VULN-CAT3-01 | Critical | LIFO race condition and pending confirmation hijacking in `_handle_safety_gate_confirm` | `jarvis/core/app.py`, `jarvis/automation/safety_gate.py` | M1 | RESOLVED |
| 11 | VULN-CAT3-02 | High | Safety gate token replay and lifecycle gap | `jarvis/automation/safety_gate.py` | M1 | RESOLVED |
| 12 | VULN-CAT3-03 | Critical | Unauthenticated remote skill execution (`!exec`) & screenshot exfiltration | `jarvis/comms/discord.py` | M1 | RESOLVED |
| 13 | VULN-CAT3-04 | High | Ambient privilege escalation via unauthenticated system and voice contexts | `jarvis/core/app.py`, `jarvis/core/models.py` | M1 | RESOLVED |
| 14 | VULN-CAT3-05 | High | Missing safety interception for VM termination, subagent spawning, sandbox code | `jarvis/planner/safety_interceptor.py`, `jarvis/automation/vm.py` | M1 | RESOLVED |
| 15 | VULN-CAT4-01 | High | `idna==2.10` vulnerable to CVE-2024-3651 & CVE-2026-45409 DoS | `requirements.txt:33`, `pyproject.toml:34` | M1 | RESOLVED |
| 16 | VULN-CAT4-02 | High | Missing `keyring` in `requirements.txt` bypassing Windows Credential Manager | `requirements.txt:34`, `jarvis/security/secrets.py:48-54` | M1 | RESOLVED |
| 17 | VULN-CAT4-03 | Medium | Outdated dependency bounds in requirements | `requirements.txt`, `pyproject.toml` | M1 | RESOLVED |
| 18 | VULN-CAT5-01 | Medium | Raw exception interpolation leaking paths & internals to voice/chat users | `jarvis/vision/screen.py`, `jarvis/comms/zalo.py`, `jarvis/comms/discord.py` | M1 | RESOLVED |
| 19 | VULN-CAT5-02 | Medium | Action handlers returning raw exception strings | `jarvis/core/dispatcher.py` | M1 | RESOLVED |
| 20 | VULN-CAT5-03 | High | PromptGuard `wrap_untrusted_context` unescaped XML breakout | `jarvis/security/prompt_guard.py` | M1 | RESOLVED |
| 21 | VULN-CAT5-04 | High | Sandbox AST validator omitting `importlib` and `builtins` | `jarvis/sandbox/validator.py` | M1 | RESOLVED |
| 22 | VULN-CAT5-05 | Low | Package exports missing `secrets.py` in `jarvis/security/__init__.py` | `jarvis/security/__init__.py` | M1 | RESOLVED |
| 23 | SEC-TEST-01 | N/A | Add 21+ new security-focused tests in `tests/unit/test_security_hardening.py` | `tests/unit/test_security_hardening.py` | M2 | DONE |
| 24 | SEC-TOOL-01 | N/A | Build standalone security scanner with `--help`, AST/regex rules, exit code 0 | `tools/security_scanner.py` | M3 | DONE |
| 25 | SEC-DOC-01 | N/A | Update `AUDIT_FRAMEWORK.md`, `CHANGELOG.md`, `docs/ROADMAP.md`, 3+ commits, push | Repository root & docs/ | M4 | DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|:------:|
| M0 | Survey & 5-Category Security Audit | 3 parallel Explorers scanning all 200 source files, dependencies, security modules | none | DONE |
| M1 | Vulnerability Remediation & Patching | Clean minimal fixes for all 22 discovered vulnerabilities, no cheat workarounds, tests pass | M0 | DONE |
| M2 | Security Test Suite Upgrade | 21+ new security unit tests added in tests/unit/, maintain ≥2,694 passing tests | M1 | DONE |
| M3 | Automated Security Scanner Tool | Build standalone security scanner in `tools/security_scanner.py` with docs & tests | M0, M1 | DONE |
| M4 | Documentation, Verification & Git Push | Update AUDIT_FRAMEWORK, CHANGELOG, ROADMAP, ≥3 commits after 7e973e4, push to origin/main | M1, M2, M3 | DONE |

## Interface & Security Contracts
### Safety Interceptor & Action Confirmation Contract
- High-risk and destructive actions (`shell_exec`, `shell_execute`, `shell_command`, `sandbox_execute_code`, `sandbox_python_exec`, file deletion, shutdown, reboot, VM destruction) MUST trigger confirmation requests.
- Confirmation tokens MUST enforce a strictly monotonic TTL expiration and cannot be reused or bypassed via parameter injection.
- Fail-closed semantics: Any invalid or expired token must result in denial.

### Sanitization & Shell Safety Contract
- No user/STT/LLM supplied strings may be passed directly to shell command execution without strict tokenization, allowlisting, and rejection of chaining operators (`&`, `|`, `;`, `>`, `<`, `^`).
- Path operations must resolve canonical paths and ensure they do not traverse outside designated workspace/cache boundaries.

### Information Disclosure & Logging Contract
- Logging calls and exception handlers must mask credentials, tokens, passwords, and sensitive system internals.
- Debug mode must default to False in production configuration.
- Local web dashboard endpoints (`/api/config`, `/api/logs`) must NOT use wildcard CORS and must redact secrets. Origin strictly limited to loopback addresses.

## Code Layout
- `jarvis/core/`: Application orchestrator, event bus, action dispatcher, configuration, and logging.
- `jarvis/security/`: Safety interceptor, credential manager, sandbox, AST validator.
- `jarvis/automation/`: Desktop automation, safety gate, shell assistant.
- `jarvis/comms/`: Communication adapters (Telegram, Discord, Zalo, Email).
- `jarvis/web/`: Web search, scraping, cache.
- `tools/`: Standalone developer and security tools (`tools/security_scanner.py`).
- `tests/unit/`: Pytest unit and security test suite.
- `docs/AUDIT_FRAMEWORK.md`: Security audit criteria and results.
- `CHANGELOG.md`: Project change log.
- `docs/ROADMAP.md`: Master project roadmap.
