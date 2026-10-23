"""
jarvis/context
==============
Active Window & Context Awareness Package for JARVIS (AWACI Engine).
"""
from __future__ import annotations

from jarvis.context.screen_context import (
    AWACIEngine,
    WindowContext,
    get_active_window_context,
)

__all__ = [
    "AWACIEngine",
    "WindowContext",
    "get_active_window_context",
]
