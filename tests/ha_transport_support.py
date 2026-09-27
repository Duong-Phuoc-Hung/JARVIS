"""Stateful HTTP double for unit tests only. Provider/HA runtime remains pending."""

from copy import deepcopy
from types import SimpleNamespace


class HAHTTP:
    def __init__(self):
        self.states = {
            "light.living_room": {
                "entity_id": "light.living_room",
                "state": "off",
                "attributes": {},
            }
        }
        self.posts = []

    def request(self, method, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        if method == "GET":
            state = self.states.get(url.rsplit("/", 1)[1])
            return SimpleNamespace(status_code=200 if state else 404, json=lambda: deepcopy(state))
        data = kwargs["json"]
        self.posts.append(data)
        state = self.states[data["entity_id"]]
        state["state"] = "on" if url.endswith("/turn_on") else "off"
        if "brightness" in data:
            state["attributes"]["brightness"] = data["brightness"]
        return SimpleNamespace(status_code=200, json=lambda: deepcopy([state]))


def confirm_call(client, domain, service, data):
    pending = client.call_service(domain, service, data)
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    token = pending.data["confirmation_token"]
    assert client.dispatcher.safety_interceptor.safety_gate.confirm(token)
    return client.call_service(domain, service, data, confirmation_token=token)
