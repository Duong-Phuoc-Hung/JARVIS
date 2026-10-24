"""
JARVIS Core Framework & Subsystems.
"""
from __future__ import annotations

from jarvis.core.config import ConfigManager, get_config
from jarvis.core.logger import JarvisLoggerAdapter, get_logger, setup_logging
from jarvis.core.hd_vsa import (
    CompoundMacroComposer,
    HD_DIMENSION_BITS,
    HyperVector,
    HyperdimensionalItemMemory,
    bundle_hypervectors,
)
from jarvis.core.models import (
    ActionDefinition,
    ActionResult,
    HandlerResult,
    MonitorInfo,
    PluginHealth,
    PluginMetadata,
    PluginStatus,
    PrivilegeLevel,
    RequesterContext,
    SubscriptionRecord,
    WindowInfo,
)

__all__ = [
    "ConfigManager",
    "get_config",
    "setup_logging",
    "get_logger",
    "JarvisLoggerAdapter",
    "PrivilegeLevel",
    "PluginStatus",
    "RequesterContext",
    "HandlerResult",
    "ActionResult",
    "ActionDefinition",
    "SubscriptionRecord",
    "PluginMetadata",
    "PluginHealth",
    "MonitorInfo",
    "WindowInfo",
    "HD_DIMENSION_BITS",
    "HyperVector",
    "bundle_hypervectors",
    "HyperdimensionalItemMemory",
    "CompoundMacroComposer",
]

