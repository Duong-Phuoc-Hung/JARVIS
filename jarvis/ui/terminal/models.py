"""
jarvis/ui/terminal/models.py
=============================
Data models for the J.A.R.V.I.S. Terminal Control Center.

This module defines the *presentation-layer* action metadata contract
(read_only / safe_for_batch / requires_confirmation / side_effect_level).
It is NOT a second security authority: existing SafetyGate / ActionDispatcher
/ RBAC / confirmation-token contracts remain the sole authorization boundary
for any side-effecting operation. This metadata only controls terminal-UI
presentation and [A] batch-eligibility -- it must never be used to bypass,
weaken, or duplicate the real safety gate.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.ui.terminal.theme import StatusLevel


@dataclass
class ActionOutcome:
    """Truthful result of running one terminal action.

    `status` must be derived from a real backend observation -- never
    defaulted to READY/PASS merely because a call did not raise.
    """
    status: StatusLevel
    title: str
    fields: list[tuple[str, str]] = field(default_factory=list)
    detail_lines: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    started_at: float = field(default_factory=time.time)
    structured_data: dict[str, Any] = field(default_factory=dict)
    error_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (StatusLevel.READY, StatusLevel.AVAILABLE, StatusLevel.PASS)


@dataclass
class MenuAction:
    """One selectable terminal menu entry.

    A leaf action has `handler` set (a zero-arg callable returning an
    ActionOutcome). A navigational entry has `is_submenu=True` and
    `submenu_id` pointing at another MenuScreen's id instead.
    """
    id: str
    key: str
    label: str
    description: str = ""
    handler: Callable[[], ActionOutcome] | None = None
    read_only: bool = True
    safe_for_batch: bool = False
    requires_confirmation: bool = False
    requires_target: bool = False
    side_effect_level: str = "none"  # "none" | "state_change" | "destructive" | "external_send"
    help_text: str = ""
    available: bool = True
    unavailable_reason: str = ""
    is_submenu: bool = False
    submenu_id: str | None = None


@dataclass
class MenuScreen:
    """A single navigable screen: a module menu, a detail view, etc."""
    id: str
    title: str
    breadcrumb: list[str]
    actions: list[MenuAction] = field(default_factory=list)
    batch_label: str = "Run All Safe Checks"
    help_intro: str = ""
    on_enter: Callable[[], None] | None = None

    def batch_eligible(self) -> list[MenuAction]:
        return [a for a in self.actions if a.safe_for_batch and a.available and a.handler is not None]

    def batch_visible(self) -> bool:
        """[A] is offered only when TWO OR MORE currently meaningful actions
        can be executed safely as a batch -- a single eligible action does
        not warrant a separate "run everything" affordance distinct from
        just selecting that one action directly."""
        return len(self.batch_eligible()) >= 2


@dataclass
class BatchItemResult:
    action: MenuAction
    outcome: ActionOutcome


@dataclass
class BatchResult:
    module: str
    operation: str
    items: list[BatchItemResult] = field(default_factory=list)
    duration_s: float = 0.0
    started_at: float = field(default_factory=time.time)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            key = item.outcome.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts


@dataclass
class SessionRecord:
    """One safe, redacted record of a completed terminal operation.
    Never contains secrets or raw biometric embeddings -- see
    jarvis.ui.terminal.session.redact_structured() which every adapter's
    structured_data passes through before it reaches this record."""
    timestamp: float
    module: str
    action: str
    status: str
    duration_s: float
    summary: str
    structured_data: dict[str, Any] = field(default_factory=dict)
