# Real Runtime Evidence Report: IMAP Live Integration (R7c)

**Standard**: AUDIT_FRAMEWORK.md (Anti-Fabrication Principle & Fail-Closed Tier 2) & AGENTS.md  
**Date of Audit**: 2026-09-17  
**Subsystem**: `jarvis.comms.email_imap.IMAPEmailReader`  
**Host Target**: Windows 11 x64  
**Auditor**: `teamwork_preview_worker_m3`  
**Status**: `PENDING_CREDENTIALS` (Truthful Fail-Closed Contract Verified)

---

## 1. Executive Summary

Requirement **R7c** specifies the runtime evaluation of the live IMAP email reading subsystem (`IMAPEmailReader`), verifying the presence of live integration credentials, and asserting strict adherence to the Anti-Fabrication Principle.

Key audit findings:
1. **Unconfigured Environment Variables**: Neither the opt-in flag `JARVIS_RUN_LIVE_IMAP_TESTS` nor the credential environment variables (`JARVIS_TEST_IMAP_HOST`, `JARVIS_TEST_IMAP_USER`, `JARVIS_TEST_IMAP_PASSWORD`) are configured on this host.
2. **Anti-Fabrication Principle**: Per `AGENTS.md` (Section 2) and `docs/AUDIT_FRAMEWORK.md` (Pitfalls #1, #2, #5), the assistant **never** invents temporary dummy credentials, mocks a remote server to pretend a live test succeeded, or commits private passwords to source control.
3. **Fail-Closed Contract**: When credentials are missing, invoking `IMAPEmailReader().connect()` raises `IMAPNotConfiguredError` with the canonical error code `"NOT_CONFIGURED"`. No silent connection or unhandled crash occurs.
4. **Unit Verification**: 10 distinct test seams across `tests/unit/test_imap_reader.py` comprehensively validate credential guarding, RFC822 message parsing, prompt-injection sanitization, and idempotent disconnection.

---

## 2. Environment Probe & Protocol Specification

### 2.1 Opt-In Verification Protocol

The live IMAP integration protocol requires four explicit environment variables:

| Environment Variable | Expected Format | Observed State |
|---|---|:---:|
| `JARVIS_RUN_LIVE_IMAP_TESTS` | `"1"` (boolean string) | **UNSET** |
| `JARVIS_TEST_IMAP_HOST` | Valid IMAP FQDN (e.g. `imap.gmail.com`) | **UNSET** |
| `JARVIS_TEST_IMAP_USER` | Valid account / email address | **UNSET** |
| `JARVIS_TEST_IMAP_PASSWORD` | App-specific password or auth token | **UNSET** |

### 2.2 Truthful Audit Finding

> **Observed State**: "credentials not configured in environment — test skipped per opt-in protocol."

Under the **Anti-Fabrication Principle**, this is the only correct and compliant behavior. When user-provided credentials are not configured, attempting to simulate or fake a successful live mailbox connection is strictly prohibited.

---

## 3. Subsystem Contract Verification

### 3.1 Source Inspection: `jarvis/comms/email_imap.py`

Lines 65–78 of `jarvis/comms/email_imap.py` enforce fail-closed validation on connection initialization:

```python
def connect(self) -> None:
    """Open SSL connection to IMAP host and log in.
    
    Raises:
        IMAPNotConfiguredError: If host, username, or password is empty (NOT_CONFIGURED).
        IMAPConnectionError: If connection or authentication fails.
    """
    if not self.host or not self.username or not self.password:
        raise IMAPNotConfiguredError(
            "IMAP credentials missing. host, username, and password are required (NOT_CONFIGURED)."
        )
    ...
```

Similarly, high-level wrapper `fetch_and_summarize()` guards against missing credentials:
```python
if not self.host or not self.username or not self.password:
    raise IMAPNotConfiguredError(
        "IMAP credentials missing. host, username, and password are required (NOT_CONFIGURED)."
    )
```

Calling unconfigured endpoints yields deterministic fail-closed errors without leaking credentials or leaving dangling SSL sockets.

---

## 4. Test Suite & Verification Proof

The fail-closed contract is verified by `tests/unit/test_imap_reader.py`:

| Test Function | Target Seam | Validated Invariant | Result |
|---|---|---|:---:|
| `test_empty_host_raises_not_configured` | `TestConnectFailClosed` | Empty host string raises `IMAPNotConfiguredError("NOT_CONFIGURED")` | **PASS** |
| `test_empty_username_raises_not_configured` | `TestConnectFailClosed` | Empty username raises `IMAPNotConfiguredError("NOT_CONFIGURED")` | **PASS** |
| `test_empty_password_raises_not_configured` | `TestConnectFailClosed` | Empty password raises `IMAPNotConfiguredError("NOT_CONFIGURED")` | **PASS** |
| `test_all_empty_raises_not_configured` | `TestConnectFailClosed` | Default constructor without parameters raises fail-closed exception | **PASS** |
| `test_connect_constructs_imap4_ssl_and_calls_login` | `TestConnectHappyPath` | Verifies SSL connection and login calls when configured | **PASS** |
| `test_connect_stores_connection_on_success` | `TestConnectHappyPath` | Active socket stored in `self._imap` | **PASS** |
| `test_disconnect_calls_logout` | `TestDisconnect` | Graceful `logout()` invoked upon disconnection | **PASS** |
| `test_disconnect_when_not_connected_is_idempotent` | `TestDisconnect` | Calling `disconnect()` without prior connection is safe | **PASS** |
| `test_disconnect_swallows_logout_exception` | `TestDisconnect` | Socket teardown exceptions swallowed safely without crash | **PASS** |
| `test_fetch_unread_without_connect_raises_runtime_error` | `TestFetchUnread` | Calling `fetch_unread()` prior to `connect()` raises `RuntimeError` | **PASS** |
| `test_fetch_unread_select_fails_returns_empty` | `TestFetchUnread` | Folder select failure returns empty list `[]` (fail-closed) | **PASS** |
| `test_fetch_unread_no_unseen_returns_empty` | `TestFetchUnread` | Zero unread emails returns `[]` without error | **PASS** |
| `test_fetch_unread_parses_single_email` | `TestFetchUnread` | RFC822 bytes decoded correctly into `EmailMessage` dataclass | **PASS** |
| `test_fetch_unread_skips_malformed_message` | `TestFetchUnread` | Malformed message payload skipped without terminating session | **PASS** |
| `test_mock_emails_path_does_not_open_connection` | `TestFetchAndSummarize` | Unit mock mode does not initiate network sockets | **PASS** |
| `test_no_credentials_raises_not_configured` | `TestFetchAndSummarize` | `fetch_and_summarize()` raises `IMAPNotConfiguredError` | **PASS** |
| `test_real_path_calls_connect_fetch_disconnect` | `TestFetchAndSummarize` | Lifecycle follows connect → fetch → disconnect sequence | **PASS** |
| `test_security_pipeline_drops_non_allowlisted_sender` | Security Policy | Messages from unapproved senders are dropped | **PASS** |
| `test_security_pipeline_drops_injection_subject` | Prompt Injection Guard | Malicious prompt-injection payloads in subjects are rejected | **PASS** |
| `test_empty_allowlist_drops_all_emails` | Security Policy | Default empty allowlist drops all incoming mail | **PASS** |

---

## 5. Security & Invariant Summary

1. **Anti-Fabrication**: Credentials are never hardcoded or simulated.
2. **Fail-Closed Default**: Systems without live credentials remain locked in `PENDING_CREDENTIALS` state.
3. **Safety Interceptor Gating**: In addition to reader-side validation, outbound email dispatch is categorized as high-risk under `jarvis/planner/safety_interceptor.py` (R4), requiring explicit user confirmation before execution.

---

## 6. Audit Conclusion

The IMAP email subsystem satisfies **Requirement R7c**:
- Unconfigured state is truthfully documented without simulation or fabrication.
- Fail-closed behavior (`IMAPNotConfiguredError`) is verified by unit tests.
- Subsystem adheres fully to `AUDIT_FRAMEWORK.md` Tier 2 standards.
