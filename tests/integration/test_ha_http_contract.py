"""Real HTTP with a scripted HA server: transport evidence, not HA runtime acceptance."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.smart_home.home_assistant import HomeAssistantClient


@pytest.fixture
def ha_server():
    states = {
        "light.test": {"entity_id": "light.test", "state": "off", "attributes": {}},
        "climate.test": {
            "entity_id": "climate.test",
            "state": "heat",
            "attributes": {"temperature": 22.0},
        },
    }
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.headers.get("Authorization") != "Bearer test-token":
                return self.respond(401, {})
            if self.path == "/api/states":
                return self.respond(200, list(states.values()))
            state = states.get(self.path.removeprefix("/api/states/"))
            self.respond(200 if state else 404, state or {})

        def do_POST(self):
            calls.append(("POST", self.path))
            if self.headers.get("Authorization") != "Bearer test-token":
                return self.respond(403, {})
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state = states[data["entity_id"]]
            service = self.path.rsplit("/", 1)[1]
            if service == "set_temperature":
                state["attributes"]["temperature"] = data["temperature"]
            else:
                state["state"] = "on" if service == "turn_on" else "off"
            self.respond(200, [state])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", states, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def execute_confirmed(dispatcher, action, payload):
    pending = dispatcher.dispatch_action(action, payload)
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    token = pending.data["confirmation_token"]
    assert dispatcher.safety_interceptor.safety_gate.confirm(token)
    result = dispatcher.dispatch_action(action, payload, confirmation_token=token)
    assert not dispatcher.dispatch_action(action, payload, confirmation_token=token).success
    return result


@pytest.mark.parametrize(
    "entity,action,payload,restore",
    [
        (
            "light.test",
            "smart_home_turn_on",
            {"entity": "đèn thử"},
            ("smart_home_turn_off", {"entity": "đèn thử"}),
        ),
        (
            "climate.test",
            "smart_home_set_temp",
            {"entity": "climate.test", "temperature": 24.0},
            ("smart_home_set_temp", {"entity": "climate.test", "temperature": 22.0}),
        ),
    ],
)
def test_dispatcher_write_before_after_and_restore(ha_server, entity, action, payload, restore):
    url, states, calls = ha_server
    dispatcher = ActionDispatcher()
    client = HomeAssistantClient(
        url,
        "test-token",
        {"đèn thử": "light.test"},
        allowed_entity_ids=list(states),
        dispatcher=dispatcher,
    )
    before = client.get_state(entity)
    assert client.get_entities().success
    assert not dispatcher.dispatch_action(action, payload).success
    assert not any(m == "POST" for m, p in calls)
    result = execute_confirmed(dispatcher, action, payload)
    assert result.success
    assert result.data["before"] == before
    assert result.data["after"] == client.get_state(entity)
    assert execute_confirmed(dispatcher, *restore).success
    assert client.get_state(entity) == before


def test_unknown_entity_and_invalid_token_fail_closed(ha_server):
    url, states, calls = ha_server
    c = HomeAssistantClient(url, "test-token", allowed_entity_ids=["light.unknown"])
    result = execute_confirmed(
        c.dispatcher,
        "home_assistant_call",
        {"domain": "light", "service": "turn_on", "entity_id": "light.unknown"},
    )
    assert not result.success and result.code == "HTTP_404"
    invalid = HomeAssistantClient(url, "wrong-token", allowed_entity_ids=["light.test"])
    assert invalid.get_state("light.test") is None
    assert invalid.last_result.code == "HTTP_401"
    assert not any(method == "POST" for method, path in calls)
