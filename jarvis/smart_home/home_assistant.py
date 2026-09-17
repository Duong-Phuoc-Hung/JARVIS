"""
jarvis/smart_home/home_assistant.py
===================================
Home Assistant REST & WebSocket Client, Entity Alias Resolution, and Service Invocations.
Covers Feature:
  - F-26: Home Assistant REST/WS Client (Entity state inspection & service invocations)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from jarvis.core.models import ActionResult, ActionStatus
from jarvis.security.secrets import get_secret

log = logging.getLogger("jarvis.smart_home.ha")


class HomeAssistantClient:
    """Home Assistant REST API Client with robust offline error handling, alias mapping, and authoritative security gating."""

    ALLOWED_DOMAINS: frozenset[str] = frozenset({
        "light",
        "switch",
        "climate",
        "media_player",
        "fan",
        "sensor",
    })

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
    ):
        self.base_url = base_url.rstrip("/")
        if access_token is not None:
            self.token = access_token
        else:
            token = get_secret("HASS_TOKEN") or os.environ.get("HASS_TOKEN")
            self.token = token if token else "token_xyz"
        self.timeout = timeout
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
            return False, f"SECURITY_REFUSAL: entity '{resolved}' belongs to restricted security domain"

        domain = resolved.split(".", 1)[0]
        if domain not in self.ALLOWED_DOMAINS:
            return False, f"SECURITY_REFUSAL: domain '{domain}' is not in authoritative allowlist"

        # Check for invalid injection characters
        if any(c in resolved for c in (";", "&", "|", "`", "$", "<", ">", "\n", "\r", " ")):
            return False, f"SECURITY_REFUSAL: invalid characters in entity ID: '{resolved}'"

        return True, ""

    def get_state(self, entity_id: str, mock_http: Any | None = None) -> dict[str, Any] | None:
        """Fetches current state and attributes for an entity."""
        resolved = self.resolve_entity(entity_id)
        is_allowed, err = self.validate_entity_allowed(resolved)
        if not is_allowed:
            log.warning("Home Assistant entity '%s' rejected: %s", resolved, err)
            return None

        if mock_http is not None:
            return mock_http.handle_ha_get_state(resolved)

        if not self.token:
            log.warning("Home Assistant not configured: missing access token")
            return None

        url = f"{self.base_url}/api/states/{resolved}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            log.warning("Home Assistant HTTP error %s querying entity '%s'", exc.code, resolved)
        except Exception as exc:
            log.warning("Failed to reach Home Assistant at %s: %s", url, exc)
        return None

    def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any],
        mock_http: Any | None = None,
    ) -> ActionResult:
        """Calls a Home Assistant domain service with authoritative security gating."""
        domain_clean = domain.strip().lower()
        if domain_clean not in self.ALLOWED_DOMAINS:
            return ActionResult(
                action_name="home_assistant_call",
                success=False,
                status=ActionStatus.ERROR,
                code="SECURITY_REFUSAL",
                message=f"SECURITY_REFUSAL: domain '{domain}' is not in authoritative allowlist",
                retryable=False,
                data={"domain": domain_clean, "service": service},
            )

        resolved_data = dict(service_data)
        if "entity_id" in resolved_data:
            resolved_entity = self.resolve_entity(resolved_data["entity_id"])
            resolved_data["entity_id"] = resolved_entity
            is_allowed, err = self.validate_entity_allowed(resolved_entity)
            if not is_allowed:
                return ActionResult(
                    action_name="home_assistant_call",
                    success=False,
                    status=ActionStatus.ERROR,
                    code="SECURITY_REFUSAL",
                    message=err or f"SECURITY_REFUSAL: entity '{resolved_entity}' is not allowed",
                    retryable=False,
                    data={"entity_id": resolved_entity},
                )

        if mock_http is not None:
            res = mock_http.handle_ha_call_service(domain_clean, service, resolved_data)
            return ActionResult(
                action_name="home_assistant_call",
                success=True,
                status=ActionStatus.SUCCESS,
                code="OK",
                message=f"Service {domain_clean}.{service} executed successfully",
                retryable=False,
                data=res,
            )

        if not self.token:
            return ActionResult(
                action_name="home_assistant_call",
                success=False,
                status=ActionStatus.ERROR,
                code="NOT_CONFIGURED",
                message="NOT_CONFIGURED: Home Assistant token missing",
                retryable=False,
            )

        url = f"{self.base_url}/api/services/{domain_clean}/{service}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        body = json.dumps(resolved_data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status in (200, 201):
                    res = json.loads(resp.read().decode("utf-8"))
                    return ActionResult(
                        action_name="home_assistant_call",
                        success=True,
                        status=ActionStatus.SUCCESS,
                        code="OK",
                        message=f"Service {domain_clean}.{service} executed successfully",
                        retryable=False,
                        data=res,
                    )
                return ActionResult(
                    action_name="home_assistant_call",
                    success=False,
                    status=ActionStatus.ERROR,
                    code=f"HTTP_{resp.status}",
                    message=f"Home Assistant returned HTTP {resp.status}",
                    retryable=(resp.status >= 500 or resp.status == 429),
                )
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

    def turn_on(
        self,
        entity: str,
        brightness: int | None = None,
        mock_http: Any | None = None,
    ) -> ActionResult:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        payload: dict[str, Any] = {"entity_id": resolved}
        if brightness is not None:
            payload["brightness"] = brightness
        return self.call_service(domain, "turn_on", payload, mock_http=mock_http)

    def turn_off(self, entity: str, mock_http: Any | None = None) -> ActionResult:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        return self.call_service(domain, "turn_off", {"entity_id": resolved}, mock_http=mock_http)

    def toggle(self, entity: str, mock_http: Any | None = None) -> ActionResult:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        return self.call_service(domain, "toggle", {"entity_id": resolved}, mock_http=mock_http)

    def set_temperature(
        self,
        entity: str,
        temperature: float,
        mock_http: Any | None = None,
    ) -> ActionResult:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "climate"
        return self.call_service(
            domain,
            "set_temperature",
            {"entity_id": resolved, "temperature": temperature},
            mock_http=mock_http,
        )
