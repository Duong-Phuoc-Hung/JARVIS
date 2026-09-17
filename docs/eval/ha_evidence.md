# Real Runtime Evidence Report: Home Assistant HTTP Probe (R7d)

**Standard**: AUDIT_FRAMEWORK.md & AGENTS.md (Anti-Fabrication Principle)  
**Date of Audit**: 2026-09-17  
**Subsystem**: `jarvis.smart_home.home_assistant.HomeAssistantClient`  
**Host Target**: Windows 11 x64  
**Auditor**: `teamwork_preview_worker_m3`  
**Canonical Health Status**: `UNAVAILABLE` (Standardized Vocabulary per R3)

---

## 1. Executive Summary

Requirement **R7d** mandates empirical runtime probe evaluation of the Home Assistant smart home integration layer (`HomeAssistantClient`), inspecting connectivity to both local network and loopback broker endpoints, and verifying fail-closed handling under the standardized 5-state health vocabulary (`READY`, `LIMITED`, `BLOCKED`, `ERROR`, `UNAVAILABLE`).

Key audit findings:
1. **Network Endpoint Probes**: Real HTTP probes to default Home Assistant endpoints (`http://homeassistant.local:8123` and `http://localhost:8123`) failed truthfully due to non-existent DNS resolution and connection timeout, respectively.
2. **Canonical Status**: The subsystem is properly classified as **`UNAVAILABLE`** in accordance with Requirement R3 (`jarvis/ui/terminal/theme.py`).
3. **Graceful Fail-Closed Behavior**: When the broker is unreachable, `HomeAssistantClient` does not crash the host process or produce unhandled exceptions. Service invocations return structured `ActionResult(status=ActionStatus.ERROR, code="CONNECTION_FAILED")` with `retryable=True`.
4. **Authoritative Security Gating**: Restricted domains (e.g. `lock.*`, `alarm_control_panel.*`, `camera.*`) are rejected client-side with `code="SECURITY_REFUSAL"` prior to attempting any network call.

---

## 2. Empirical HTTP Probe Execution

A real Python HTTP probe was executed with a 2.0-second socket timeout against the two standard Home Assistant URLs:

### Probe 1: Local Network Multicast DNS Address
- **Target URL**: `http://homeassistant.local:8123/api/`
- **Method**: HTTP `GET`
- **Timeout**: 2.0 seconds
- **Observed Result**:  
  `FAILED: <urlopen error [Errno 11001] getaddrinfo failed>`
- **Root Cause**: The domain name `homeassistant.local` could not be resolved by Windows DNS resolver (no Home Assistant mDNS broadcaster or Bonjour daemon is advertising on the current LAN subnet).

### Probe 2: Loopback Daemon Address
- **Target URL**: `http://localhost:8123/api/`
- **Method**: HTTP `GET`
- **Timeout**: 2.0 seconds
- **Observed Result**:  
  `FAILED: <urlopen error timed out>`
- **Root Cause**: No service or container is listening on port 8123 on the local Windows host.

### Consolidated Probe Summary

| Endpoint | Probe Target | Observed Result | Subsystem Assessment |
|---|---|---|:---:|
| `http://homeassistant.local:8123` | Remote LAN Broker | `[Errno 11001] getaddrinfo failed` | Unreachable |
| `http://localhost:8123` | Local Host Broker | `timed out` (Connection Timed Out) | Unreachable |
| **Consolidated Status** | **Smart Home Subsystem** | **Network Unreachable** | **`UNAVAILABLE`** |

---

## 3. Subsystem Architecture & Fail-Closed Contract

### 3.1 Source Inspection: `jarvis/smart_home/home_assistant.py`

When `HomeAssistantClient` attempts an API call while offline:

```python
try:
    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
        ...
except Exception as exc:
    log.warning("Home Assistant service call failed: %s", exc)
    return ActionResult(
        action_name="home_assistant_call",
        success=False,
        status=ActionStatus.ERROR,
        code="CONNECTION_FAILED",
        message=f"Connection failed: Home Assistant unreachable - {exc}",
        retryable=True,
    )
```

Similarly, state queries (`get_state`) return `None` and log warnings rather than raising uncaught socket exceptions.

### 3.2 Security Gating & Safety Classification

1. **Domain Allowlist**: Only benign domains (`light`, `switch`, `climate`, `media_player`, `fan`, `sensor`) are permitted.
2. **Disallowed Security Prefixes**: High-security devices (`lock.`, `alarm_control_panel.`, `camera.`, `siren.`, `valve.`, `vacuum.`) trigger immediate client-side refusal with `SECURITY_REFUSAL`.
3. **Safety Interceptor Gating (R4)**: All Home Assistant actions (`home_assistant_call`, `home_assistant_turn_on`, `home_assistant_turn_off`) are classified as high-risk under `jarvis/planner/safety_interceptor.py`, enforcing mandatory user confirmation prior to dispatch.

### 3.3 Terminal Control Center Status Integration

In `jarvis/ui/terminal/modules/smart_home.py`, the adapter queries connection status:
- If unconfigured or unreachable, the module reports `StatusLevel.UNAVAILABLE`.
- The terminal UI displays:
  `Smart Home : UNAVAILABLE` (rendered in muted gray per `_STATUS_COLOR[StatusLevel.UNAVAILABLE] = "GRAY"`).

---

## 4. Verification Method

To verify the fail-closed offline handling of Home Assistant:

```python
from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.core.models import ActionStatus

client = HomeAssistantClient(base_url="http://homeassistant.local:8123", timeout=1.0)

# 1. State fetch on unreachable host returns None without exception
state = client.get_state("light.living_room")
assert state is None

# 2. Service invocation returns structured ActionResult with code="CONNECTION_FAILED"
result = client.call_service("light", "turn_on", {"entity_id": "light.living_room"})
assert result.success is False
assert result.status == ActionStatus.ERROR
assert result.code == "CONNECTION_FAILED"
assert result.retryable is True
```

The unit test suite in `tests/unit/test_home_assistant.py` verifies these contracts across all permutations.

---

## 5. Audit Conclusion

The Home Assistant subsystem satisfies **Requirement R7d**:
- Empirical runtime probes confirm endpoints are offline without speculation.
- Status is classified strictly as `UNAVAILABLE` within the R3 canonical vocabulary.
- System handles missing infrastructure fail-closed without crashes, ghost successes, or silent fallbacks.
