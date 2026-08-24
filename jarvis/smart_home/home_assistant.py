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
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union
import urllib.error
import urllib.request

log = logging.getLogger("jarvis.smart_home.ha")


class HomeAssistantClient:
    """Home Assistant REST API Client with robust offline error handling and alias mapping."""

    def __init__(
        self,
        base_url: str = "http://homeassistant.local:8123",
        access_token: str = "token_xyz",
        entity_aliases: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = access_token
        self.timeout = timeout
        self.entity_aliases: Dict[str, str] = entity_aliases or {
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

    def resolve_entity(self, alias_or_id: str) -> str:
        """Resolves natural language or config alias to valid HA entity_id."""
        clean = alias_or_id.lower().strip()
        return self.entity_aliases.get(clean, alias_or_id)

    def get_state(self, entity_id: str, mock_http: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Fetches current state and attributes for an entity."""
        resolved = self.resolve_entity(entity_id)
        if mock_http is not None:
            return mock_http.handle_ha_get_state(resolved)

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
        service_data: Dict[str, Any],
        mock_http: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Calls a Home Assistant domain service (e.g. light/turn_on, climate/set_temperature)."""
        resolved_data = dict(service_data)
        if "entity_id" in resolved_data:
            resolved_data["entity_id"] = self.resolve_entity(resolved_data["entity_id"])

        if mock_http is not None:
            res = mock_http.handle_ha_call_service(domain, service, resolved_data)
            return {"success": True, "result": res}

        url = f"{self.base_url}/api/services/{domain}/{service}"
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
                    return {"success": True, "result": res}
                return {"success": False, "error": f"Home Assistant returned HTTP {resp.status}"}
        except Exception as exc:
            log.warning("Home Assistant service call failed: %s", exc)
            return {"success": False, "error": f"Connection failed: Home Assistant unreachable - {exc}"}

    def turn_on(
        self,
        entity: str,
        brightness: Optional[int] = None,
        mock_http: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        payload: Dict[str, Any] = {"entity_id": resolved}
        if brightness is not None:
            payload["brightness"] = brightness
        return self.call_service(domain, "turn_on", payload, mock_http=mock_http)

    def turn_off(self, entity: str, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        return self.call_service(domain, "turn_off", {"entity_id": resolved}, mock_http=mock_http)

    def toggle(self, entity: str, mock_http: Optional[Any] = None) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "light"
        return self.call_service(domain, "toggle", {"entity_id": resolved}, mock_http=mock_http)

    def set_temperature(
        self,
        entity: str,
        temperature: float,
        mock_http: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolved = self.resolve_entity(entity)
        domain = resolved.split(".")[0] if "." in resolved else "climate"
        return self.call_service(
            domain,
            "set_temperature",
            {"entity_id": resolved, "temperature": temperature},
            mock_http=mock_http,
        )
