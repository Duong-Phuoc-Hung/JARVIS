from unittest.mock import Mock, patch

import pytest

from jarvis.smart_home.home_assistant import HomeAssistantClient


def test_missing_token_never_uses_placeholder_or_network():
    with (
        patch("jarvis.smart_home.home_assistant.get_secret", return_value=None),
        patch.dict("os.environ", {"HASS_TOKEN": ""}),
        patch("urllib.request.urlopen") as network,
    ):
        client = HomeAssistantClient()
        assert client.get_state("light.test") is None
        result = client.turn_on("light.test")
    assert not result.success
    network.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"entity_id": "all"},
        {"entity_id": "light.other"},
        {"entity_id": "climate.test"},
        {"entity_id": ["light.test"]},
        {"entity_id": "light.test", "area_id": "all"},
    ],
)
def test_write_requires_explicit_single_matching_allowed_entity(payload):
    c = HomeAssistantClient(access_token="dummy", allowed_entity_ids=["light.test"])
    with patch("urllib.request.urlopen") as network:
        result = c.call_service("light", "turn_on", payload)
    assert not result.success
    network.assert_not_called()


def test_public_write_requires_confirmation_even_without_app():
    c = HomeAssistantClient(access_token="dummy", allowed_entity_ids=["light.test"])
    with patch("urllib.request.urlopen") as network:
        result = c.turn_on("light.test")
    assert result.error_code == "CONFIRMATION_REQUIRED"
    network.assert_not_called()


import requests

from jarvis.core.dispatcher import ActionDispatcher


def confirmed(client, action, payload):
    pending = client.dispatcher.dispatch_action(action, payload)
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    token = pending.data["confirmation_token"]
    assert client.dispatcher.safety_interceptor.safety_gate.confirm(token)
    return client.dispatcher.dispatch_action(action, payload, confirmation_token=token)


def http_response(status, data):
    r = Mock(status_code=status)
    r.json.return_value = data
    return r


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_confirmed_write_read_failure_never_posts(status):
    client = HomeAssistantClient(access_token="dummy", allowed_entity_ids=["light.test"])
    with patch("requests.request", return_value=http_response(status, {})) as net:
        result = confirmed(
            client,
            "home_assistant_call",
            {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.test"}},
        )
    assert not result.success and result.code == f"HTTP_{status}"
    assert all(c.args[0] == "GET" for c in net.call_args_list)


@pytest.mark.parametrize(
    "failure", [requests.Timeout("private-canary"), requests.ConnectionError("private-canary")]
)
def test_network_failure_is_redacted(failure, caplog):
    client = HomeAssistantClient(access_token="dummy", allowed_entity_ids=["light.test"])
    with patch("requests.request", side_effect=failure):
        result = confirmed(
            client,
            "home_assistant_call",
            {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.test"}},
        )
    assert not result.success
    assert "private-canary" not in str(result) + caplog.text


def test_confirmed_noop_response_does_not_claim_write():
    client = HomeAssistantClient(access_token="dummy", allowed_entity_ids=["light.test"])
    off = {"entity_id": "light.test", "state": "off", "attributes": {}}
    with patch(
        "requests.request",
        side_effect=[http_response(200, off), http_response(200, []), http_response(200, off)],
    ):
        result = confirmed(
            client,
            "home_assistant_call",
            {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.test"}},
        )
    assert not result.success and result.code == "STATE_NOT_VERIFIED"
    assert result.data["request_accepted"] is True
