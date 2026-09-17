"""
tests/unit/test_action_result_contract.py
=========================================
Unit tests for the unified ActionResult contract (Milestone M2 / R2).
Verifies:
  1. ActionResult 4 required fields: status, code, message, retryable
  2. Dict emulation interface: __getitem__, get, __contains__, keys
  3. HomeAssistantClient returning ActionResult across all mutating methods
  4. MobileFileBridge returning ActionResult with rate limit retryable semantics
  5. VMOrchestrator returning ActionResult across all VM lifecycle methods
  6. Bidirectional synchronization and to_dict serialization
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.automation.vm import VMOrchestrator
from jarvis.comms.mobile_bridge import MobileFileBridge
from jarvis.core.models import ActionResult, ActionStatus
from jarvis.smart_home.home_assistant import HomeAssistantClient


# ============================================================================
# 1. ActionResult Contract & Field Verification
# ============================================================================

def test_action_result_has_all_four_required_fields():
    """Verify that ActionResult instances contain status, code, message, and retryable with proper types."""
    res = ActionResult(
        action_name="test_action",
        status=ActionStatus.SUCCESS,
        code="OK",
        message="Operation succeeded",
        retryable=False,
    )
    assert hasattr(res, "status")
    assert hasattr(res, "code")
    assert hasattr(res, "message")
    assert hasattr(res, "retryable")

    assert res.status == ActionStatus.SUCCESS
    assert res.code == "OK"
    assert res.message == "Operation succeeded"
    assert res.retryable is False
    assert res.success is True
    assert isinstance(res.status, (ActionStatus, str))
    assert isinstance(res.code, str)
    assert isinstance(res.message, str)
    assert isinstance(res.retryable, bool)


def test_action_result_default_values():
    """Verify default values when constructing an empty or minimal ActionResult."""
    res = ActionResult()
    assert res.action_name == ""
    assert res.success is True
    assert res.status == ActionStatus.SUCCESS
    assert res.code == "OK"
    assert res.message == ""
    assert res.retryable is False
    assert res.data is None
    assert res.error is None
    assert res.error_code is None


def test_action_result_dict_emulation():
    """Verify dict-like subscripting and lookup: res['status'], res['code'], res['message'], res['retryable'], res['success'], res.get('code'), 'status' in res."""
    res = ActionResult(
        action_name="dict_test",
        status=ActionStatus.SUCCESS,
        code="OK",
        message="All systems nominal",
        retryable=False,
        data={"payload_key": "payload_val", "count": 42},
    )

    # Subscripting on core fields
    assert res["status"] == ActionStatus.SUCCESS
    assert res["code"] == "OK"
    assert res["message"] == "All systems nominal"
    assert res["retryable"] is False
    assert res["success"] is True

    # Subscripting on data payload
    assert res["payload_key"] == "payload_val"
    assert res["count"] == 42
    assert res["result"] == {"payload_key": "payload_val", "count": 42}

    # .get() interface
    assert res.get("code") == "OK"
    assert res.get("status") == ActionStatus.SUCCESS
    assert res.get("payload_key") == "payload_val"
    assert res.get("missing_key", "default_val") == "default_val"

    # __contains__ interface
    assert "status" in res
    assert "code" in res
    assert "message" in res
    assert "retryable" in res
    assert "success" in res
    assert "payload_key" in res
    assert "nonexistent_key" not in res

    # Missing key raises KeyError
    with pytest.raises(KeyError):
        _ = res["absolutely_nonexistent"]


def test_action_result_to_dict_serialization():
    """Verify to_dict() outputs all required fields including status, code, message, and retryable."""
    res = ActionResult(
        action_name="serialize_action",
        status=ActionStatus.ERROR,
        code="RESOURCE_EXHAUSTED",
        message="Disk quota exceeded",
        retryable=True,
        data={"free_mb": 0},
    )
    d = res.to_dict()
    assert d["action_name"] == "serialize_action"
    assert d["status"] == "ERROR"
    assert d["code"] == "RESOURCE_EXHAUSTED"
    assert d["message"] == "Disk quota exceeded"
    assert d["retryable"] is True
    assert d["success"] is False
    assert d["data"] == {"free_mb": 0}
    assert d["error"] == "Disk quota exceeded"
    assert d["error_code"] == "RESOURCE_EXHAUSTED"


def test_action_result_bidirectional_synchronization():
    """Verify __post_init__ harmonizes legacy (success, error, error_code) with modern (status, code, message)."""
    # Legacy error sets status, code, message
    res_legacy_fail = ActionResult(
        action_name="legacy_fail",
        success=False,
        error="Permission denied to access resource",
        error_code="PERMISSION_DENIED",
    )
    assert res_legacy_fail.status == ActionStatus.ERROR
    assert res_legacy_fail.code == "PERMISSION_DENIED"
    assert res_legacy_fail.message == "Permission denied to access resource"
    assert res_legacy_fail.error == "Permission denied to access resource"
    assert res_legacy_fail.error_code == "PERMISSION_DENIED"

    # Modern error sets legacy fields
    res_modern_fail = ActionResult(
        action_name="modern_fail",
        status=ActionStatus.ERROR,
        code="INVALID_ARGUMENT",
        message="Parameter 'foo' must be integer",
        retryable=False,
    )
    assert res_modern_fail.success is False
    assert res_modern_fail.error == "Parameter 'foo' must be integer"
    assert res_modern_fail.error_code == "INVALID_ARGUMENT"


# ============================================================================
# 2. HomeAssistantClient Migration Verification
# ============================================================================

class MockHAHttp:
    """Mock HTTP helper for HomeAssistantClient test isolation."""
    def __init__(self):
        self.calls = []

    def handle_ha_call_service(self, domain: str, service: str, data: dict):
        self.calls.append((domain, service, data))
        return {"status": "ok", "domain": domain, "service": service}


def test_home_assistant_client_returns_action_result():
    """Verify that HomeAssistantClient methods return ActionResult instances."""
    mock_http = MockHAHttp()
    client = HomeAssistantClient(access_token="mock_token", base_url="http://ha.local:8123")

    # 1. turn_on
    res_turn_on = client.turn_on("đèn phòng khách", brightness=200, mock_http=mock_http)
    assert isinstance(res_turn_on, ActionResult)
    assert res_turn_on.success is True
    assert res_turn_on.status == ActionStatus.SUCCESS
    assert res_turn_on.code == "OK"
    assert res_turn_on["success"] is True

    # 2. turn_off
    res_turn_off = client.turn_off("light.living_room", mock_http=mock_http)
    assert isinstance(res_turn_off, ActionResult)
    assert res_turn_off.success is True
    assert res_turn_off.status == ActionStatus.SUCCESS

    # 3. toggle
    res_toggle = client.toggle("light.living_room", mock_http=mock_http)
    assert isinstance(res_toggle, ActionResult)
    assert res_toggle.success is True

    # 4. set_temperature
    res_temp = client.set_temperature("climate.ac_unit", 24.0, mock_http=mock_http)
    assert isinstance(res_temp, ActionResult)
    assert res_temp.success is True
    assert res_temp.code == "OK"

    # 5. call_service (security refusal on disallowed domain)
    res_refusal = client.call_service("lock", "unlock", {"entity_id": "lock.front_door"}, mock_http=mock_http)
    assert isinstance(res_refusal, ActionResult)
    assert res_refusal.success is False
    assert res_refusal.status == ActionStatus.ERROR
    assert res_refusal.code == "SECURITY_REFUSAL"
    assert res_refusal.retryable is False
    assert "SECURITY_REFUSAL" in res_refusal.message
    assert "SECURITY_REFUSAL" in res_refusal["error"]

    # 6. call_service (not configured token)
    unauth_client = HomeAssistantClient(access_token="", base_url="http://ha.local:8123")
    res_unauth = unauth_client.call_service("light", "turn_on", {"entity_id": "light.hallway"})
    assert isinstance(res_unauth, ActionResult)
    assert res_unauth.success is False
    assert res_unauth.status == ActionStatus.ERROR
    assert res_unauth.code == "NOT_CONFIGURED"
    assert res_unauth.retryable is False


# ============================================================================
# 3. MobileFileBridge Migration Verification
# ============================================================================

def test_mobile_bridge_returns_action_result(tmp_path):
    """Verify that MobileFileBridge methods return ActionResult and 429 sets retryable=True and code='RATE_LIMITED'."""
    bridge = MobileFileBridge(
        save_directory=str(tmp_path / "mb_downloads"),
        max_file_size_mb=5,
    )

    # 1. receive_file - valid file
    res_file = bridge.receive_file(b"Test content for mobile bridge", "notes.txt")
    assert isinstance(res_file, ActionResult)
    assert res_file.success is True
    assert res_file.status == ActionStatus.SUCCESS
    assert res_file.code == "OK"
    assert res_file["success"] is True
    assert "saved_path" in res_file
    assert res_file["size_kb"] >= 0

    # 2. receive_file - invalid extension
    res_bad = bridge.receive_file(b"payload", "malware.exe")
    assert isinstance(res_bad, ActionResult)
    assert res_bad.success is False
    assert res_bad.status == ActionStatus.ERROR
    assert res_bad.code == "VALIDATION_ERROR"
    assert res_bad.retryable is False

    # 3. receive_file - rate limited (burst exhaustion)
    # Configure tight rate limiter to trigger 429
    from jarvis.comms.rate_limiter import RateLimitConfig
    tight_bridge = MobileFileBridge(
        save_directory=str(tmp_path / "mb_tight"),
        rate_limit_config=RateLimitConfig(requests_per_minute=1, burst_limit=1),
    )
    r1 = tight_bridge.receive_file(b"1", "f1.txt", metadata={"device_id": "dev1"})
    assert r1.success is True
    r2 = tight_bridge.receive_file(b"2", "f2.txt", metadata={"device_id": "dev1"})
    assert isinstance(r2, ActionResult)
    assert r2.success is False
    assert r2.status == ActionStatus.ERROR
    assert r2.code == "RATE_LIMITED"
    assert r2.retryable is True
    assert "retry_after_s" in r2
    assert r2.get("status") == 429

    # 4. send_clipboard_to_mobile (empty or unconfigured)
    with patch.object(bridge, "_get_clipboard_text", return_value="Test clipboard"):
        res_clip = bridge.send_clipboard_to_mobile()
        assert isinstance(res_clip, ActionResult)
        assert res_clip.success is False
        assert res_clip.code == "NOT_CONFIGURED"
        assert res_clip.retryable is False

    # 5. send_screenshot_to_mobile (unconfigured telegram)
    with patch.object(bridge, "_capture_screenshot", return_value=b"\x89PNG\r\n\x1a\nfakeimage"):
        res_screen = bridge.send_screenshot_to_mobile()
        assert isinstance(res_screen, ActionResult)
        assert res_screen.success is False
        assert res_screen.code == "NOT_CONFIGURED"
        assert res_screen.retryable is False
        assert "saved_path" in res_screen


# ============================================================================
# 4. VMOrchestrator Migration Verification
# ============================================================================

def test_vm_orchestrator_returns_action_result():
    """Verify that VMOrchestrator methods return ActionResult instances."""
    orchestrator = VMOrchestrator(dry_run=True)

    # 1. start_vm
    res_start = orchestrator.start_vm("Ubuntu-Dev", hypervisor="vmware")
    assert isinstance(res_start, ActionResult)
    assert res_start.success is True
    assert res_start.status == ActionStatus.SUCCESS
    assert res_start.code == "OK"
    assert res_start.retryable is False
    assert res_start["vm_name"] == "Ubuntu-Dev"
    assert res_start["hypervisor"] == "vmware"
    assert res_start["state"] == "RUNNING"

    # 2. stop_vm
    res_stop = orchestrator.stop_vm("Ubuntu-Dev", hypervisor="vmware")
    assert isinstance(res_stop, ActionResult)
    assert res_stop.success is True
    assert res_stop.status == ActionStatus.SUCCESS
    assert res_stop.code == "OK"
    assert res_stop["state"] == "STOPPED"

    # 3. suspend_vm
    res_suspend = orchestrator.suspend_vm("Ubuntu-Dev", hypervisor="vmware")
    assert isinstance(res_suspend, ActionResult)
    assert res_suspend.success is True
    assert res_suspend.status == ActionStatus.SUCCESS
    assert res_suspend["state"] == "SUSPENDED"

    # 4. snapshot_vm
    res_snap = orchestrator.snapshot_vm("Ubuntu-Dev", "pre-upgrade")
    assert isinstance(res_snap, ActionResult)
    assert res_snap.success is True
    assert res_snap.status == ActionStatus.SUCCESS
    assert res_snap["snapshot_name"] == "pre-upgrade"


# ============================================================================
# 5. Adversarial Probe & Stress-Testing Harness (Empirical Challenger)
# ============================================================================

def test_adversarial_unknown_keys_getitem_raises_keyerror_vs_get_returns_default():
    """Adversarial Test 1: Accessing unknown keys via __getitem__ must raise KeyError, while get() returns default."""
    # 1. Probe with default empty ActionResult
    res_empty = ActionResult()
    adversarial_keys = [
        "absolutely_unknown",
        "__proto__",
        "constructor",
        "",
        "non_existent_key_12345",
        "status_code_fake",
        "nested.key.probe",
    ]
    for key in adversarial_keys:
        # __getitem__ MUST raise KeyError
        with pytest.raises(KeyError) as exc_info:
            _ = res_empty[key]
        assert key in str(exc_info.value) or "not found" in str(exc_info.value)

        # get() without default returns None
        assert res_empty.get(key) is None

        # get() with explicit default returns the default
        sentinel = f"default_for_{key}"
        assert res_empty.get(key, sentinel) == sentinel
        assert res_empty.get(key, default=42) == 42
        assert res_empty.get(key, default={"nested": True}) == {"nested": True}

        # __contains__ must be False
        assert key not in res_empty

    # 2. Probe when data is explicitly an empty dict {}
    res_with_empty_dict = ActionResult(data={})
    for key in adversarial_keys:
        with pytest.raises(KeyError):
            _ = res_with_empty_dict[key]
        assert res_with_empty_dict.get(key) is None
        assert res_with_empty_dict.get(key, "fallback") == "fallback"
        assert key not in res_with_empty_dict

    # 3. Probe when data is a populated dict: unknown keys not in data still raise KeyError
    res_with_data = ActionResult(data={"present_key": "val1", "zero": 0, "null": None})
    for key in adversarial_keys:
        with pytest.raises(KeyError):
            _ = res_with_data[key]
        assert res_with_data.get(key) is None
        assert res_with_data.get(key, "fallback") == "fallback"
        assert key not in res_with_data

    # Valid data keys work properly
    assert res_with_data["present_key"] == "val1"
    assert res_with_data["zero"] == 0
    assert res_with_data["null"] is None
    assert res_with_data.get("present_key") == "val1"
    assert res_with_data.get("zero") == 0


def test_adversarial_modifying_fields_and_reserializing_to_dict():
    """Adversarial Test 2: Modifying core/extended fields dynamically and re-serializing via to_dict()."""
    res = ActionResult(
        action_name="initial_action",
        status=ActionStatus.SUCCESS,
        code="OK",
        message="Initial message",
        retryable=False,
        data={"step": 1},
    )

    # Verify baseline before modification
    d_initial = res.to_dict()
    assert d_initial["status"] == "SUCCESS"
    assert d_initial["code"] == "OK"
    assert d_initial["retryable"] is False

    # 1. Mutate fields to failure state
    res.status = ActionStatus.FAILED
    res.code = "CRITICAL_CIRCUIT_BREAKER_TRIGGERED"
    res.message = "Over-temperature emergency shutdown"
    res.retryable = True
    res.success = False
    res.data = {"temp_celsius": 105.8, "tripped_relays": ["R1", "R2"]}
    res.error = "Hardware thermal protection tripped"
    res.error_code = "HARDWARE_THERMAL_FAULT"
    res.execution_time_ms = 789.12
    res.requester = "telemetry_daemon"

    d_mutated = res.to_dict()
    assert d_mutated["action_name"] == "initial_action"
    assert d_mutated["status"] == "FAILED"
    assert d_mutated["code"] == "CRITICAL_CIRCUIT_BREAKER_TRIGGERED"
    assert d_mutated["message"] == "Over-temperature emergency shutdown"
    assert d_mutated["retryable"] is True
    assert d_mutated["success"] is False
    assert d_mutated["data"] == {"temp_celsius": 105.8, "tripped_relays": ["R1", "R2"]}
    assert d_mutated["error"] == "Hardware thermal protection tripped"
    assert d_mutated["error_code"] == "HARDWARE_THERMAL_FAULT"
    assert d_mutated["execution_time_ms"] == 789.12
    assert d_mutated["requester"] == "telemetry_daemon"

    # 2. Mutate status using raw string values (non-enum)
    for raw_status in ["TIMEOUT", "RATE_LIMITED", "CUSTOM_USER_STATUS", "ERROR"]:
        res.status = raw_status
        d_str_status = res.to_dict()
        assert d_str_status["status"] == raw_status

    # 3. Verify returned dictionary isolation (modifying to_dict() output does not corrupt model)
    exported = res.to_dict()
    exported["code"] = "TAMPERED_IN_EXPORT"
    exported["status"] = "TAMPERED_STATUS"
    assert res.code == "CRITICAL_CIRCUIT_BREAKER_TRIGGERED"
    assert res.status == "ERROR"


def test_adversarial_json_serialization_roundtrip():
    """Adversarial Test 3: Robust JSON serialization using json.dumps(res.to_dict()) and round-trip parsing."""
    # 1. Verify JSON serialization across ALL ActionStatus enum variants
    for status_member in ActionStatus:
        res = ActionResult(
            action_name=f"test_{status_member.name.lower()}",
            status=status_member,
            code=f"CODE_{status_member.name}",
            message=f"Status is {status_member.value}",
            retryable=(status_member in (ActionStatus.TIMEOUT, ActionStatus.RATE_LIMITED)),
            data={"status_tested": status_member.value},
        )
        dict_payload = res.to_dict()
        raw_json = json.dumps(dict_payload)
        parsed = json.loads(raw_json)

        assert parsed["status"] == status_member.value
        assert parsed["code"] == f"CODE_{status_member.name}"
        assert parsed["message"] == f"Status is {status_member.value}"
        assert parsed["retryable"] is (status_member in (ActionStatus.TIMEOUT, ActionStatus.RATE_LIMITED))
        assert parsed["data"] == {"status_tested": status_member.value}

    # 2. Complex nested data, numbers, booleans, nulls, and Vietnamese diacritics
    complex_data = {
        "device_info": {
            "name": "Điều hòa phòng khách",
            "firmware": "v2.1.0-beta",
            "target_temp": 24.5,
            "eco_mode": True,
            "sensors": [
                {"id": "temp_sensor", "val": 26.1, "unit": "°C"},
                {"id": "humidity_sensor", "val": 65, "unit": "%"},
            ],
            "schedule": None,
        },
        "history": [10, 20, 30, 40, 50],
    }
    res_unicode = ActionResult(
        action_name="smart_home_set_temp",
        status=ActionStatus.SUCCESS,
        code="OK",
        message="Đã thiết lập nhiệt độ phòng khách thành 24.5°C thành công!",
        retryable=False,
        data=complex_data,
    )
    json_str = json.dumps(res_unicode.to_dict(), ensure_ascii=False)
    parsed_unicode = json.loads(json_str)

    assert parsed_unicode["action_name"] == "smart_home_set_temp"
    assert parsed_unicode["message"] == "Đã thiết lập nhiệt độ phòng khách thành 24.5°C thành công!"
    assert parsed_unicode["data"]["device_info"]["name"] == "Điều hòa phòng khách"
    assert parsed_unicode["data"]["device_info"]["sensors"][0]["unit"] == "°C"
    assert parsed_unicode["data"]["device_info"]["target_temp"] == 24.5


def test_adversarial_arbitrary_types_in_data():
    """Adversarial Test 4: Passing arbitrary, unconventional, or non-dict types into data."""
    class CustomObject:
        def __init__(self, identifier: str, count: int):
            self.identifier = identifier
            self.count = count

        def compute(self) -> int:
            return self.count * 10

    test_arbitrary_payloads = [
        ("none_type", None),
        ("integer", 1337),
        ("negative_float", -99.99),
        ("boolean_false", False),
        ("string_scalar", "scalar string data"),
        ("list_of_heterogeneous", [1, "two", 3.0, None, True]),
        ("tuple_data", (10, 20, 30)),
        ("set_data", {"tag1", "tag2", "tag3"}),
        ("bytes_payload", b"\xde\xad\xbe\xef\x00\x01"),
        ("custom_class_instance", CustomObject("sensor_node_01", 7)),
        ("exception_instance", RuntimeError("Hardware interrupt failure")),
        ("callable_function", lambda x: x ** 2),
    ]

    for type_label, payload in test_arbitrary_payloads:
        res = ActionResult(
            action_name=f"probe_{type_label}",
            status=ActionStatus.SUCCESS,
            code="OK",
            message=f"Testing type {type_label}",
            data=payload,
        )

        # 1. Verify data attribute holds exact reference
        assert res.data is payload

        # 2. Verify 'result' key subscripting and get() access
        assert res["result"] is payload
        assert res.get("result") is payload

        # 3. Verify __contains__ behavior
        if payload is not None:
            assert "result" in res
        else:
            assert "result" not in res

        # 4. Unknown key lookup MUST raise KeyError without crashing on non-dict data
        with pytest.raises(KeyError) as exc_info:
            _ = res["arbitrary_unknown_key"]
        assert "arbitrary_unknown_key" in str(exc_info.value) or "not found" in str(exc_info.value)

        # 5. get() on unknown key MUST return default safely without throwing TypeError
        assert res.get("arbitrary_unknown_key") is None
        assert res.get("arbitrary_unknown_key", "SAFE_DEFAULT") == "SAFE_DEFAULT"

        # 6. keys() must execute safely and contain core fields + 'result' (if not None)
        k = res.keys()
        assert "status" in k
        assert "code" in k
        assert "message" in k
        assert "retryable" in k
        if payload is not None:
            assert "result" in k

        # 7. to_dict() must execute safely
        d = res.to_dict()
        assert d["data"] is payload
        assert d["status"] == "SUCCESS"

        # 8. JSON serialization with default=str fallback handles arbitrary types
        json_repr = json.dumps(d, default=str)
        assert len(json_repr) > 0

