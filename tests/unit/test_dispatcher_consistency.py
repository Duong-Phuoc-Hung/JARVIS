"""
tests/unit/test_dispatcher_consistency.py
==========================================
D-11: Core Dispatcher Consistency Tests

Verifies:
- ActionDispatcher routes same action to same handler regardless of entry point
- Actions from voice, terminal, and comms paths follow the same policy
- No duplicate handler registration creates ghost success
- Error isolation: one handler failing does not affect others
- Event deduplication across subscribers
"""
from __future__ import annotations

import pytest
from jarvis.core.dispatcher import EventBus, ActionDispatcher


class TestEventBusConsistency:
    """EventBus must route events consistently and enforce error isolation."""

    def test_subscribe_and_publish_single(self):
        bus = EventBus()
        received = []
        bus.subscribe("action.test", lambda value: received.append(value))
        bus.publish("action.test", value=42)
        assert received == [42]

    def test_same_event_same_handler_any_source(self):
        """Same action must produce same handler call regardless of caller."""
        bus = EventBus()
        calls = []
        bus.subscribe("action.open_app", lambda app: calls.append(app))

        # Simulate voice, terminal, and comms calling the same action event
        bus.publish("action.open_app", app="spotify")   # voice path
        bus.publish("action.open_app", app="spotify")   # terminal path
        bus.publish("action.open_app", app="spotify")   # comms path

        assert calls == ["spotify", "spotify", "spotify"]

    def test_wildcard_subscriber_receives_all(self):
        """Wildcard '*' subscriber receives all events."""
        bus = EventBus()
        all_events = []
        bus.subscribe("*", lambda **kw: all_events.append(kw))
        bus.publish("action.open_app", app="settings")
        bus.publish("action.volume", level=80)
        assert len(all_events) == 2

    def test_handler_exception_does_not_block_next_handler(self):
        """Error isolation: failing handler must not stop subsequent handlers."""
        bus = EventBus()
        second_called = []

        def bad_handler(**kw):
            raise RuntimeError("handler crash")

        def good_handler(**kw):
            second_called.append(True)

        bus.subscribe("action.test", bad_handler)
        bus.subscribe("action.test", good_handler)
        results = bus.publish("action.test")

        # First failed, second must still run
        assert any(not r.success for r in results)
        assert second_called == [True]

    def test_unsubscribe_removes_handler(self):
        """Unsubscribed handler must not receive future events."""
        bus = EventBus()
        received = []
        sub_id = bus.subscribe("action.test", lambda: received.append(1))
        bus.unsubscribe(sub_id)
        bus.publish("action.test")
        assert received == []

    def test_no_duplicate_delivery_to_same_sub(self):
        """A subscriber registered once must receive each event exactly once."""
        bus = EventBus()
        count = []
        bus.subscribe("action.test", lambda: count.append(1))
        bus.publish("action.test")
        assert len(count) == 1

    def test_priority_order_respected(self):
        """Higher-priority handlers run first."""
        bus = EventBus()
        order = []
        bus.subscribe("action.test", lambda: order.append("low"), priority=1)
        bus.subscribe("action.test", lambda: order.append("high"), priority=10)
        bus.publish("action.test")
        assert order == ["high", "low"]

    def test_unsubscribe_nonexistent_returns_false(self):
        bus = EventBus()
        assert bus.unsubscribe("nonexistent-id") is False

    def test_unsubscribe_all_clears_all_handlers(self):
        bus = EventBus()
        received = []
        bus.subscribe("action.a", lambda: received.append("a"))
        bus.subscribe("action.b", lambda: received.append("b"))
        bus.unsubscribe_all()
        bus.publish("action.a")
        bus.publish("action.b")
        assert received == []


class TestActionDispatcherConsistency:
    """ActionDispatcher must provide consistent action routing API."""

    def test_dispatch_unknown_action_returns_action_result(self):
        """Unknown action returns ActionResult with success=False, not exception."""
        from jarvis.core.dispatcher import ActionResult
        disp = ActionDispatcher()
        result = disp.dispatch_action("jarvis.noop")
        assert isinstance(result, ActionResult)
        assert result.success is False
        assert result.error_code == "ACTION_NOT_FOUND"

    def test_registered_action_called_once(self):
        disp = ActionDispatcher()
        calls = []

        def open_app_handler(app: str, **kw):
            calls.append(app)

        disp.register_action("jarvis.open_app", open_app_handler)
        result = disp.dispatch_action("jarvis.open_app", payload={"app": "chrome"})
        assert result.success is True
        assert calls == ["chrome"]

    def test_cross_entry_point_same_semantics(self):
        """Same action from voice/terminal entry points invokes the same handler."""
        disp = ActionDispatcher()
        invocations = []

        disp.register_action("jarvis.set_volume", lambda level, **kw: invocations.append(level))

        # Voice entry point
        disp.dispatch_action("jarvis.set_volume", payload={"level": 50}, requester="voice")
        # Terminal entry point
        disp.dispatch_action("jarvis.set_volume", payload={"level": 50}, requester="terminal")

        assert invocations == [50, 50]

    def test_unknown_action_error_code(self):
        """Unknown action must set error_code ACTION_NOT_FOUND, not raise."""
        disp = ActionDispatcher()
        result = disp.dispatch_action("jarvis.undefined_action_xyz")
        assert result.error_code == "ACTION_NOT_FOUND"
        assert result.success is False
