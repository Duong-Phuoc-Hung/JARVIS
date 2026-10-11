"""
jarvis/core/handlers
====================
Action handler service components for JarvisApp (Composition pattern).
Decomposes action execution into focused, maintainable domains:
  - SystemHandlers: Power, volume, window, clipboard, app launch, shell, safety gates.
  - ServiceHandlers: Smart home, security scanning, healing, web intelligence, proactive routines, notes.
  - AutomationHandlers: Browser CDP/driver, ReAct planner, subagents, sandbox, skills, vision GUI.
"""
from __future__ import annotations

from jarvis.core.handlers.automation_handlers import (
    AutomationHandlers,
    AutomationHandlersMixin,
)
from jarvis.core.handlers.base import (
    BaseActionService,
    _POWER_ACTION_ALIASES,
    _UNSUPPORTED_POWER_ACTIONS,
    _DualErrorStr,
    _build_browser_config,
    _safe_browser_failure_url,
)
from jarvis.core.handlers.service_handlers import (
    ServiceHandlers,
    ServiceHandlersMixin,
)
from jarvis.core.handlers.system_handlers import (
    SystemHandlers,
    SystemHandlersMixin,
)

__all__ = [
    "AutomationHandlers",
    "AutomationHandlersMixin",
    "BaseActionService",
    "ServiceHandlers",
    "ServiceHandlersMixin",
    "SystemHandlers",
    "SystemHandlersMixin",
    "_DualErrorStr",
    "_POWER_ACTION_ALIASES",
    "_UNSUPPORTED_POWER_ACTIONS",
    "_build_browser_config",
    "_safe_browser_failure_url",
]

