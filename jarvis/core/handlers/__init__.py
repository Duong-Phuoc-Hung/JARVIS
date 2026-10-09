"""
jarvis/core/handlers
====================
Action handler mixins for JarvisApp.
Decomposes action execution into focused, maintainable domains:
  - SystemHandlersMixin: Power, volume, window, clipboard, app launch, shell, safety gates.
  - ServiceHandlersMixin: Smart home, security scanning, healing, web intelligence, proactive routines, notes.
  - AutomationHandlersMixin: Browser CDP/driver, ReAct planner, subagents, sandbox, skills, vision GUI.
"""
from __future__ import annotations

from jarvis.core.handlers.automation_handlers import AutomationHandlersMixin
from jarvis.core.handlers.base import (
    _POWER_ACTION_ALIASES,
    _UNSUPPORTED_POWER_ACTIONS,
    _DualErrorStr,
    _build_browser_config,
    _safe_browser_failure_url,
)
from jarvis.core.handlers.service_handlers import ServiceHandlersMixin
from jarvis.core.handlers.system_handlers import SystemHandlersMixin

__all__ = [
    "AutomationHandlersMixin",
    "ServiceHandlersMixin",
    "SystemHandlersMixin",
    "_DualErrorStr",
    "_POWER_ACTION_ALIASES",
    "_UNSUPPORTED_POWER_ACTIONS",
    "_build_browser_config",
    "_safe_browser_failure_url",
]
