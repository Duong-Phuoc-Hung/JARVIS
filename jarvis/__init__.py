"""
JARVIS: Autonomous Windows AI Desktop Assistant Rebuild.
"""
from __future__ import annotations

__version__ = "1.0.0"
__author__ = "JARVIS Rebuild Team"

from jarvis.core.config import ConfigManager, get_config
from jarvis.core.logger import get_logger, setup_logging

__all__ = [
    "__version__",
    "__author__",
    "ConfigManager",
    "get_config",
    "get_logger",
    "setup_logging",
]
