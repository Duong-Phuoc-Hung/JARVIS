"""
JARVIS: Autonomous Windows AI Desktop Assistant Rebuild.
"""
from __future__ import annotations

# Single canonical source for the package/runtime version. pyproject.toml
# reads this via [tool.setuptools.dynamic] version = {attr = "jarvis.__version__"}
# instead of duplicating the literal. jarvis/workers/auto_updater.py and
# scripts/health_check_report.py also locate it by scanning this file's raw
# source text for a "__version__ = ..." line, so keep this a plain top-level
# string-literal assignment — do not move it behind an import or compute it.
__version__ = "4.6.0"
__author__ = "Duong Phuoc Hung"

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
