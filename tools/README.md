# JARVIS Automated Security Hardening & Vulnerability Scanner (R4)

`tools/security_scanner.py` is a standalone, dependency-free static analysis and security scanning CLI tool built entirely using the Python standard library (`ast`, `re`, `argparse`, `pathlib`, `json`, `sys`, `typing`).

---

## 1. Overview & Architectural Philosophy

The security scanner enables continuous automated enforcement of security baselines across the JARVIS codebase. Designed to run both in local pre-commit hooks and CI/CD GitHub Actions pipelines, it inspects Python abstract syntax trees (AST), token definitions, and project manifests without needing third-party packages or compilation.

### Key Capabilities
- **Pure Standard Library**: Runs on any standard Python 3.10+ environment without installing external tools.
- **Sub-Second AST Scanning**: Analyzes 200+ source files (>65,000 LOC) in under 1.5 seconds.
- **Multi-Format Reporting**: Outputs human-readable terminal text, GitHub-flavored Markdown for PR summaries, and RFC 8259 structured JSON for automated pipelines.
- **Configurable Severity Gating**: Deterministic exit codes (`0` for clean, `1` for violations) tied to severity thresholds.

---

## 2. Rule Catalog (SEC-001 through SEC-010)

| Rule ID | Severity | Category | Description & Detection Scope |
|---|---|---|---|
| **`SEC-001`** | **CRITICAL** | Secrets Management | High-entropy string literals matching production API keys (OpenAI `sk-...`, Gemini `AIza...`, Telegram bot tokens, AWS keys, private key blocks). |
| **`SEC-002`** | **HIGH** | Credential Exposure | Logging or printing sensitive credentials (`password`, `api_key`, `secret_key`, `auth_token`) directly without redaction. |
| **`SEC-003`** | **CRITICAL** | Injection Vulnerability | Calls to `subprocess` or `os.system` with `shell=True` using dynamically interpolated commands (f-strings, `%`, `.format()`, string concat). |
| **`SEC-004`** | **HIGH** | Input Validation | Direct file access (`open()`, `Path()`) without canonical containment checks (`.is_relative_to()` or `validate_safe_path()`). |
| **`SEC-005`** | **HIGH** | Token Lifecycle | Token verification routines that omit temporal expiration checks (`entry.is_expired` or timestamp comparisons). |
| **`SEC-006`** | **MEDIUM** | Token Lifecycle | Token verification routines that fail to record verified tokens in a consumed set, risking replay attacks. |
| **`SEC-007`** | **MEDIUM** | Information Leakage | User-facing responses returning raw stack traces (`traceback.format_exc()`) or unhandled internal exceptions. |
| **`SEC-008`** | **HIGH** | Dependency Hygiene | Manifests (`requirements.txt`, `pyproject.toml`) declaring obsolete packages with known CVEs (e.g. `idna < 3.7`). |
| **`SEC-009`** | **MEDIUM** | Dependency Hygiene | Manifests omitting required core security dependencies (e.g. `keyring` for Windows Credential Vault). |
| **`SEC-010`** | **LOW** | Configuration Safety | Hardcoded `DEBUG = True` or `logging.DEBUG` flags in non-test production modules. |

---

## 3. CLI Usage & Options

```bash
python tools/security_scanner.py [OPTIONS]
```

### Options

| Flag | Argument | Default | Description |
|---|---|---|---|
| `--path` | `<path>` | `jarvis/` | Target directory or individual file to scan. |
| `--format` | `terminal`, `text`, `markdown`, `json` | `terminal` | Report output formatting. |
| `--output`, `-o` | `<file_path>` | `""` | File path to write the formatted report. |
| `--exit-code` | None | `True` | Return exit code 1 if findings meet/exceed severity threshold. |
| `--no-exit-code` | None | - | Return exit code 0 regardless of findings count. |
| `--rules` | `<id1,id2,...>` | All rules | Comma-separated list of rule IDs to activate (e.g. `SEC-001,SEC-003`). |
| `--severity-threshold` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | `HIGH` | Minimum severity level that triggers failure exit code. |
| `--verbose`, `-v` | None | `False` | Show source line snippets and detailed remediation advice. |
| `--help`, `-h` | None | - | Display comprehensive help and rule catalog. |

---

## 4. Integration Examples

### 1. Local Clean Codebase Verification
```bash
python tools/security_scanner.py --path jarvis/
```

### 2. Generate Markdown Report for GitHub Actions CI
```bash
python tools/security_scanner.py --path jarvis/ --format markdown --output security_report.md
```

### 3. Generate JSON Telemetry Artifact
```bash
python tools/security_scanner.py --path jarvis/ --format json --output reports/security_scan.json
```

### 4. Scan a Specific Module for Critical Secrets and Injections
```bash
python tools/security_scanner.py --path jarvis/planner/ --rules SEC-001,SEC-003 --severity-threshold CRITICAL
```

---

## 5. Exit Code Policy
- **`0`**: Clean scan — zero violations detected at or above `--severity-threshold`.
- **`1`**: Security violations detected at or above `--severity-threshold`.
- **`2`**: Command-line argument error or unhandled I/O error.
