"""
tests/unit/test_app_composition.py
==================================
Unit tests verifying the composition refactor of JarvisApp and BaseActionService.
Confirms:
  1. JarvisApp composes action services rather than inheriting via mixins.
  2. Injected services reference the host app.
  3. Transparent bidirectional delegation works without infinite recursion.
  4. Backward compatibility aliases (SystemHandlersMixin, etc.) are preserved.
"""
from __future__ import annotations

import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.handlers import (
    AutomationHandlers,
    AutomationHandlersMixin,
    BaseActionService,
    ServiceHandlers,
    ServiceHandlersMixin,
    SystemHandlers,
    SystemHandlersMixin,
)


def test_composition_attributes_present():
    """Verify JarvisApp instantiates the composed service instances."""
    app = JarvisApp(headless=True, no_hot_reload=True)

    assert hasattr(app, "system_service")
    assert hasattr(app, "service_service")
    assert hasattr(app, "automation_service")

    assert isinstance(app.system_service, SystemHandlers)
    assert isinstance(app.service_service, ServiceHandlers)
    assert isinstance(app.automation_service, AutomationHandlers)

    assert isinstance(app.system_service, BaseActionService)
    assert isinstance(app.service_service, BaseActionService)
    assert isinstance(app.automation_service, BaseActionService)


def test_injected_app_reference():
    """Verify composed services hold a reference to the host application."""
    app = JarvisApp(headless=True, no_hot_reload=True)

    assert app.system_service.app is app
    assert app.service_service.app is app
    assert app.automation_service.app is app


def test_app_to_service_delegation():
    """Verify JarvisApp transparently delegates handler methods to composed services."""
    app = JarvisApp(headless=True, no_hot_reload=True)

    # Handlers defined on system_service
    assert callable(app._handle_system_volume)
    assert app._handle_system_volume.__name__ == "_handle_system_volume"

    # Handlers defined on service_service
    assert callable(app._handle_web_search)
    assert app._handle_web_search.__name__ == "_handle_web_search"

    # Handlers defined on automation_service
    assert callable(app._handle_browser_navigate)
    assert app._handle_browser_navigate.__name__ == "_handle_browser_navigate"


def test_service_to_app_delegation():
    """Verify BaseActionService transparently accesses host app properties."""
    app = JarvisApp(headless=True, no_hot_reload=True)

    # Access config and dispatcher from within system_service
    assert app.system_service.config is app.config
    assert app.system_service.dispatcher is app.dispatcher
    assert app.service_service.config is app.config
    assert app.automation_service.config is app.config


def test_no_infinite_recursion_on_missing_attribute():
    """Verify missing attributes cleanly raise AttributeError without recursion errors."""
    app = JarvisApp(headless=True, no_hot_reload=True)

    with pytest.raises(AttributeError, match="has no attribute 'non_existent_attribute_xyz'"):
        _ = app.non_existent_attribute_xyz

    with pytest.raises(AttributeError, match="has no attribute 'non_existent_service_attr_123'"):
        _ = app.system_service.non_existent_service_attr_123


def test_backward_compatibility_aliases():
    """Verify *Mixin aliases point to the corresponding Service classes."""
    assert SystemHandlersMixin is SystemHandlers
    assert ServiceHandlersMixin is ServiceHandlers
    assert AutomationHandlersMixin is AutomationHandlers
