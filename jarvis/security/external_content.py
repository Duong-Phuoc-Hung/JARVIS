"""External observations are data, never an action-authority source.

Scopes are installed by trusted host code, outside model-controlled arguments.
An exact, single-use grant authorizes parameters, not just a tool name. This is
an application boundary, not a sandbox against arbitrary Python/plugin code.
"""

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy

_scope = ContextVar("external_action_scope", default=None)


class ActionScope:
    def __init__(self, grants=()):
        self._grants = deepcopy(list(grants))
        self._lock = threading.Lock()

    def consume(self, action, parameters):
        with self._lock:
            for index, (name, payload) in enumerate(self._grants):
                if name == action and payload == parameters:
                    self._grants.pop(index)
                    return True
        return False


@contextmanager
def external_action_scope(scope=None):
    # A nested scope cannot widen authority inherited from its caller.
    token = _scope.set(_scope.get() or scope or ActionScope())
    try:
        yield
    finally:
        _scope.reset(token)


def external_action_allowed(action, parameters):
    scope = _scope.get()
    return (
        (not contains_external((action, parameters)))
        if scope is None
        else scope.consume(action, parameters)
    )


class UntrustedText(str):
    """Provenance marker at in-process browser/router seams, not a serialization format."""


def mark_external(value):
    from enum import Enum

    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        return UntrustedText(value)
    if isinstance(value, dict):
        return {k: mark_external(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(mark_external(v) for v in value)
    return value


def contains_external(value):
    pending = [value]
    visited = set()
    while pending:
        item = pending.pop()
        if isinstance(item, UntrustedText):
            return True
        if isinstance(item, (dict, list, tuple)) and id(item) not in visited:
            visited.add(id(item))
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            else:
                pending.extend(item)
    return False
