"""
jarvis/ui/terminal/context.py
================================
Shared, dependency-injectable context passed to every module adapter.
Holds only presentation-layer state (selected target/file, per-session
caches of cheap-to-construct backend objects) -- never a second copy of
business logic or security decisions.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.core.config import ConfigManager
from jarvis.ui.terminal.console import TerminalConsole
from jarvis.ui.terminal.models import ActionOutcome
from jarvis.ui.terminal.report import ReportWriter
from jarvis.ui.terminal.session import SessionHistory
from jarvis.ui.terminal.theme import TerminalTheme


@dataclass
class TerminalContext:
    theme: TerminalTheme
    console: TerminalConsole
    session: SessionHistory
    report_writer: ReportWriter
    config: ConfigManager
    start_jarvis: Callable[[], bool]
    state: dict[str, Any] = field(default_factory=dict)


def run_timed(fn: Callable[[], ActionOutcome]) -> ActionOutcome:
    """Wraps an adapter body, stamping real start time / duration onto the
    returned ActionOutcome. Adapters build the ActionOutcome's `status`/
    `fields`/etc. themselves -- this only fills in truthful timing."""
    started = time.time()
    outcome = fn()
    outcome.started_at = started
    outcome.duration_s = time.time() - started
    return outcome
