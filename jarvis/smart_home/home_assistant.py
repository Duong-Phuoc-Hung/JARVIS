"""
jarvis/smart_home/home_assistant.py
===================================
Home Assistant REST & WebSocket Client, Entity Alias Resolution, and Service Invocations.
Covers Feature:
  - F-26: Home Assistant REST/WS Client (Entity state inspection & service invocations)
"""

from __future__ import annotations

import logging
import math
import os
import re
from typing import Any

from jarvis.core.models import ActionResult, ActionStatus
from jarvis.security.secrets import get_secret

log = logging.getLogger("jarvis.smart_home.ha")


class HomeAssistantClient:
    """Home Assistant REST API Client with robust offline error handling, alias mapping, and authoritative security gating."""

    ALLOWED_DOMAINS: frozenset[str] = frozenset(
        {
            "light",
            "switch",
            "climate",
            "media_player",
            "fan",
            "sensor",
        }
    )

    DISALLOWED_PREFIXES: tuple[str, ...] = (
        "lock.",
        "alarm_control_panel.",
        "camera.",
        "siren.",
        "valve.",
        "vacuum.",
    )

    def __init__(
        self,
        base_url: str = "http://homeassistant.local:8123",
        access_token: str | None = None,
        entity_aliases: dict[str, str] | None = None,
        timeout: float = 5.0,
        allowed_entity_ids: list[str] | None = None,
        dispatcher: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        if access_token is not None:
            self.token = access_token
        else:
            token = get_secret("HASS_TOKEN") or os.environ.get("HASS_TOKEN")
            self.token = token or ""
        self.timeout = timeout
        self.allowed_entity_ids = frozenset(allowed_entity_ids or [])
        self.last_result = ActionResult(success=False, code="NOT_STARTED")
        from jarvis.core.dispatcher import ActionDispatcher

        self.dispatcher = dispatcher or ActionDispatcher()
        self.bind_dispatcher(self.dispatcher)
        self.entity_aliases: dict[str, str] = entity_aliases or {
            "living_room_light": "light.living_room",
            "living room light": "light.living_room",
            "đèn phòng khách": "light.living_room",
            "desk_lamp": "light.desk_lamp",
            "đèn bàn": "light.desk_lamp",
            "temperature": "sensor.temperature",
            "nhiệt độ": "sensor.temperature",
            "ac": "climate.ac_unit",
            "điều hòa": "climate.ac_unit",
        }

    @property
    def is_configured(self) -> bool:
        """Returns True if a real (non-placeholder) token is configured."""
        return bool(self.token and self.token != "token_xyz")

    def resolve_entity(self, alias_or_id: str) -> str:
        """Resolves natural language or config alias to valid HA entity_id."""
        clean = alias_or_id.lower().strip()
        return self.entity_aliases.get(clean, alias_or_id)

    def validate_entity_allowed(self, entity_id: str) -> tuple[bool, str]:
        """
        Validates entity against authoritative security policies:
        - Must contain at least one dot separating domain and entity name
        - Entity must NOT start with any DISALLOWED_PREFIXES (e.g. lock.*, alarm.*)
        - Domain must belong to ALLOWED_DOMAINS
        - Entity must not contain shell/injection meta-characters
        """
        resolved = self.resolve_entity(entity_id).strip().lower()
        if not resolved or "." not in resolved:
            return False, f"Invalid entity ID format: '{entity_id}'"

        if any(resolved.startswith(p) for p in self.DISALLOWED_PREFIXES):
            return (
                False,
                f"SECURITY_REFUSAL: entity '{resolved}' belongs to restricted security domain",
            )

        domain = resolved.split(".", 1)[0]
        if domain not in self.ALLOWED_DOMAINS:
            return False, f"SECURITY_REFUSAL: domain '{domain}' is not in authoritative allowlist"

        # Check for invalid injection characters
        if any(c in resolved for c in (";", "&", "|", "`", "$", "<", ">", "\n", "\r", " ")):
            return False, f"SECURITY_REFUSAL: invalid characters in entity ID: '{resolved}'"

        return True, ""

    def _result(self, code: str, *, data=None, success=False, retryable=False) -> ActionResult:
        self.last_result = ActionResult(
            action_name="home_assistant_call",
            success=success,
            code=code,
            message=code,
            data=data,
            retryable=retryable,
        )
        return self.last_result

    def _request(self, method: str, path: str, payload=None) -> ActionResult:
        import requests

        if not self.is_configured:
            return self._result("NOT_CONFIGURED")
        try:
            response = requests.request(
                method,
                self.base_url + path,
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            )
            if response.status_code not in (200, 201):
                return self._result(
                    f"HTTP_{response.status_code}",
                    data={"http_status": response.status_code},
                    retryable=method == "GET"
                    and (response.status_code >= 500 or response.status_code == 429),
                )
            return self._result("OK", success=True, data=response.json())
        except (requests.Timeout, TimeoutError):
            return self._result("TIMEOUT", retryable=method == "GET")
        except ValueError:
            return self._result("INVALID_RESPONSE")
        except Exception:
            return self._result("CONNECTION_FAILED", retryable=method == "GET")

    def get_state(self, entity_id: str, mock_http: Any | None = None) -> dict[str, Any] | None:
        resolved = self.resolve_entity(entity_id)
        if (
            not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", resolved)
            or not self.validate_entity_allowed(resolved)[0]
        ):
            self._result("SECURITY_REFUSAL")
            return None
        if mock_http is not None:
            return mock_http.handle_ha_get_state(resolved)
        result = self._request("GET", f"/api/states/{resolved}")
        if not result.success:
            return None
        data = result.data
        if (
            not isinstance(data, dict)
            or data.get("entity_id") != resolved
            or not isinstance(data.get("state"), str)
        ):
            self._result("INVALID_RESPONSE")
            return None
        return data

    def get_entities(self) -> ActionResult:
        result = self._request("GET", "/api/states")
        if result.success and (
            not isinstance(result.data, list)
            or any(
                not isinstance(x, dict)
                or not isinstance(x.get("entity_id"), str)
                or "state" not in x
                for x in result.data
            )
        ):
            return self._result("INVALID_RESPONSE")
        return result

    def _validate_write(self, domain, service, service_data):
        if not self.is_configured:
            return "NOT_CONFIGURED"
        services = {
            "light": {"turn_on", "turn_off"},
            "switch": {"turn_on", "turn_off"},
            "fan": {"turn_on", "turn_off"},
            "climate": {"set_temperature"},
        }
        if service not in services.get(domain, set()) or not isinstance(service_data, dict):
            return "SECURITY_REFUSAL"
        entity = service_data.get("entity_id")
        if not isinstance(entity, str) or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", entity):
            return "SECURITY_REFUSAL"
        if entity.split(".")[0] != domain or entity not in self.allowed_entity_ids:
            return "ENTITY_NOT_ALLOWED"
        permitted = {"entity_id"} | (
            {"temperature"}
            if service == "set_temperature"
            else {"brightness"}
            if domain == "light" and service == "turn_on"
            else set()
        )
        if set(service_data) - permitted:
            return "SECURITY_REFUSAL"
        for name, low, high in (("brightness", 0, 255), ("temperature", 5, 35)):
            if name in service_data:
                value = service_data[name]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not low <= value <= high
                ):
                    return "INVALID_PARAMETER"
        if service == "set_temperature" and "temperature" not in service_data:
            return "INVALID_PARAMETER"
        return None

    def bind_dispatcher(self, dispatcher) -> None:
        """Bind public app and client entry points to the same confirmation gate."""
        self.dispatcher = dispatcher
        dispatcher.register_action("home_assistant_call", self._execute_service)
        dispatcher.register_action(
            "smart_home_turn_on",
            lambda entity=None, entity_id=None, brightness=None: self._execute_service(
                self.resolve_entity(entity or entity_id or "").split(".")[0],
                "turn_on",
                {
                    "entity_id": self.resolve_entity(entity or entity_id or ""),
                    **({"brightness": brightness} if brightness is not None else {}),
                },
            ),
        )
        dispatcher.register_action(
            "smart_home_turn_off",
            lambda entity=None, entity_id=None: self._execute_service(
                self.resolve_entity(entity or entity_id or "").split(".")[0],
                "turn_off",
                {"entity_id": self.resolve_entity(entity or entity_id or "")},
            ),
        )
        dispatcher.register_action(
            "smart_home_set_temp",
            lambda entity=None, entity_id=None, temperature=22.0: self._execute_service(
                "climate",
                "set_temperature",
                {
                    "entity_id": self.resolve_entity(entity or entity_id or ""),
                    "temperature": temperature,
                },
            ),
        )

    def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any],
        mock_http: Any | None = None,
        *,
        confirmation_token: str | None = None,
    ) -> ActionResult:
        if mock_http is not None:
            return self._result("MOCK_WRITE_UNAVAILABLE")
        if isinstance(service_data, dict) and isinstance(service_data.get("entity_id"), str):
            service_data = {
                **service_data,
                "entity_id": self.resolve_entity(service_data["entity_id"]),
            }
        error = self._validate_write(domain, service, service_data)
        if error:
            return self._result(error)
        return self.dispatcher.dispatch_action(
            "home_assistant_call",
            {"domain": domain, "service": service, "service_data": service_data},
            confirmation_token=confirmation_token,
        )

    def _execute_service(
        self,
        domain="light",
        service="turn_on",
        service_data=None,
        entity_id=None,
        entity=None,
        **kwargs,
    ) -> ActionResult:
        # Private registered handler; public callers use call_service/dispatcher.
        data = dict(service_data or {})
        if entity_id or entity:
            data.setdefault("entity_id", self.resolve_entity(entity_id or entity))
        data.update(kwargs)
        error = self._validate_write(domain, service, data)
        if error:
            return self._result(error)
        target = data["entity_id"]
        before = self.get_state(target)
        if before is None:
            return self.last_result
        if before["state"] in ("unknown", "unavailable"):
            return self._result("ENTITY_UNAVAILABLE")
        result = self._request("POST", f"/api/services/{domain}/{service}", data)
        if not result.success:
            return result
        after = self.get_state(target)
        evidence = {"before": before, "after": after, "request_accepted": True}
        expected = after is not None and (
            after.get("attributes", {}).get("temperature") == data["temperature"]
            if service == "set_temperature"
            else after["state"] == ("on" if service == "turn_on" else "off")
        )
        if not expected:
            return self._result("STATE_NOT_VERIFIED", data=evidence)
        return self._result("OK", success=True, data=evidence)

    def turn_on(
        self, entity: str, brightness: int | None = None, mock_http=None, *, confirmation_token=None
    ) -> ActionResult:
        resolved = self.resolve_entity(entity)
        return self.call_service(
            resolved.split(".")[0],
            "turn_on",
            {
                "entity_id": resolved,
                **({"brightness": brightness} if brightness is not None else {}),
            },
            mock_http,
            confirmation_token=confirmation_token,
        )

    def turn_off(self, entity: str, mock_http=None, *, confirmation_token=None) -> ActionResult:
        resolved = self.resolve_entity(entity)
        return self.call_service(
            resolved.split(".")[0],
            "turn_off",
            {"entity_id": resolved},
            mock_http,
            confirmation_token=confirmation_token,
        )

    def toggle(self, entity: str, mock_http=None) -> ActionResult:
        return self._result("UNSUPPORTED_SERVICE" if self.is_configured else "NOT_CONFIGURED")

    def set_temperature(
        self, entity: str, temperature: float, mock_http=None, *, confirmation_token=None
    ) -> ActionResult:
        resolved = self.resolve_entity(entity)
        return self.call_service(
            "climate",
            "set_temperature",
            {"entity_id": resolved, "temperature": temperature},
            mock_http,
            confirmation_token=confirmation_token,
        )
