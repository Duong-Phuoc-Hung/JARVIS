"""
Safety Gate Interceptor for the JARVIS ReAct Planner subsystem.
Intercepts high-risk operations, destructive commands, and financial/system actions,
enforcing a 30-second tokenized confirmation state machine integrated with SafetyGate.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from jarvis.automation.safety_gate import PendingConfirmation, SafetyGate
from jarvis.planner.models import StepStatus, TaskNode

logger = logging.getLogger("jarvis.planner.safety_interceptor")


class SafetyGateInterceptor:
    """
    Coordinates safety verification for planner steps.
    Intercepts risky or destructive TaskNodes and gates their execution
    until affirmative user authorization is received.
    """

    HIGH_RISK_ACTIONS: Set[str] = {
        "file_delete", "delete_file", "delete_folder", "remove_directory",
        "format_disk", "system_shutdown", "system_reboot", "registry_edit",
        "drop_database", "truncate_table", "telegram_send_document",
        "telegram_send_photo", "bank_transfer", "order_checkout",
        "shell_execute_destructive", "os_kill_process",
    }

    DANGEROUS_PATTERNS: List[re.Pattern] = [
        re.compile(r"\brm\s+-[rf]{1,2}\b", re.IGNORECASE),
        re.compile(r"\brmdir\s+/[sq]\b", re.IGNORECASE),
        re.compile(r"\bdel\s+/[sqf]\b", re.IGNORECASE),
        re.compile(r"\berase\s+/[sqf]\b", re.IGNORECASE),
        re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
        re.compile(r"\bdrop\s+(database|table)\b", re.IGNORECASE),
        re.compile(r"\bdelete\s+from\b", re.IGNORECASE),
        re.compile(r"\btruncate\s+table\b", re.IGNORECASE),
        re.compile(r"\btaskkill\s+/[fF]\s+/im\s+(explorer|csrss|lsass|svchost)\.exe", re.IGNORECASE),
        re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
        re.compile(r"\bgit\s+clean\s+-[fF]", re.IGNORECASE),
        re.compile(r"\bdd\s+if=", re.IGNORECASE),
        re.compile(r"\bmkfs\b", re.IGNORECASE),
        re.compile(r"\bdiskpart\b", re.IGNORECASE),
        re.compile(r"\bRemove-Item\b.*-Recurse", re.IGNORECASE),
        re.compile(r"\bshutil\.rmtree\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        safety_gate: Optional[SafetyGate] = None,
        timeout_seconds: float = 30.0,
        custom_high_risk_actions: Optional[Set[str]] = None,
    ) -> None:
        self.safety_gate = safety_gate or SafetyGate(timeout_seconds=timeout_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.high_risk_actions = set(self.HIGH_RISK_ACTIONS)
        if custom_high_risk_actions:
            self.high_risk_actions.update(custom_high_risk_actions)

    def is_high_risk_node(self, node: TaskNode) -> bool:
        """
        Determines whether a TaskNode constitutes a high-risk operation.
        
        Checks:
        1. Explicit `node.is_high_risk` flag.
        2. Known high-risk action names.
        3. Regex pattern matching against parameter string contents.
        """
        if node.is_high_risk:
            return True

        action_clean = node.action_name.strip().lower()
        if action_clean in self.high_risk_actions:
            return True

        # Check action prefixes
        risky_prefixes = ("delete_", "remove_", "drop_", "truncate_", "format_", "destroy_")
        if any(action_clean.startswith(prefix) for prefix in risky_prefixes):
            return True

        # Scan string parameters for destructive CLI patterns
        param_strings = self._extract_strings_from_params(node.parameters)
        for text in param_strings:
            for pattern in self.DANGEROUS_PATTERNS:
                if pattern.search(text):
                    return True

        return False

    def _extract_strings_from_params(self, params: Any) -> List[str]:
        """Recursively extracts all string values from parameter objects."""
        strings: List[str] = []
        if isinstance(params, str):
            strings.append(params)
        elif isinstance(params, dict):
            for k, v in params.items():
                if isinstance(k, str):
                    strings.append(k)
                strings.extend(self._extract_strings_from_params(v))
        elif isinstance(params, (list, tuple, set)):
            for item in params:
                strings.extend(self._extract_strings_from_params(item))
        return strings

    def intercept_node(
        self,
        node: TaskNode,
        event_bus: Optional[Any] = None,
    ) -> str:
        """
        Gates the given node, setting its status to WAITING_CONFIRMATION,
        generating a confirmation token, and publishing an event.
        
        Args:
            node: Target TaskNode.
            event_bus: Optional EventBus instance to broadcast notification.
            
        Returns:
            The generated confirmation token string.
        """
        desc = node.description or f"Thực thi hành động rủi ro cao: {node.action_name}"
        token = self.safety_gate.request_confirmation(
            action_desc=desc,
            payload={
                "step_id": node.step_id,
                "action_name": node.action_name,
                "parameters": node.parameters,
            },
        )
        node.confirmation_token = token
        node.status = StepStatus.WAITING_CONFIRMATION

        logger.info(
            "Node '%s' intercepted by SafetyGate. Token: %s, Description: %s",
            node.step_id, token, desc
        )

        if event_bus and hasattr(event_bus, "publish"):
            try:
                event_bus.publish(
                    "planner:waiting_confirmation",
                    step_id=node.step_id,
                    token=token,
                    action_name=node.action_name,
                    description=desc,
                    parameters=node.parameters,
                    timeout_seconds=self.timeout_seconds,
                )
            except Exception as e:
                logger.debug("Failed to publish waiting_confirmation event: %s", e)

        return token

    def check_confirmation(self, token: str) -> Tuple[bool, str]:
        """
        Checks the status of a confirmation token.
        
        Returns:
            (is_confirmed, status_string)
            e.g. (True, "CONFIRMED"), (False, "PENDING"), (False, "EXPIRED"), (False, "REJECTED")
        """
        entry = self.safety_gate.get_pending(token)
        if not entry:
            return False, "UNKNOWN"

        if entry.is_expired and entry.status == "PENDING":
            entry.status = "EXPIRED"

        is_confirmed = (entry.status == "CONFIRMED")
        return is_confirmed, entry.status

    def confirm(self, token: str) -> bool:
        """Manually confirms a pending safety gate token."""
        return self.safety_gate.confirm(token)

    def reject(self, token: str) -> bool:
        """Manually rejects/cancels a pending safety gate token."""
        return self.safety_gate.reject(token)

    def is_affirmative(self, phrase: str) -> bool:
        """Checks if a user phrase represents affirmative confirmation."""
        return self.safety_gate.is_affirmative(phrase)

    def is_negative(self, phrase: str) -> bool:
        """Checks if a user phrase represents rejection/cancellation."""
        return self.safety_gate.is_negative(phrase)
