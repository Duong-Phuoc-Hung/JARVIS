"""
Safety Gate Interceptor for the JARVIS ReAct Planner subsystem.
Intercepts high-risk operations, destructive commands, and financial/system actions,
enforcing a 30-second tokenized confirmation state machine integrated with SafetyGate.
"""
from __future__ import annotations

import logging
from copy import deepcopy
import re
import threading
from typing import Any

from jarvis.automation.safety_gate import SafetyGate
from jarvis.planner.models import StepStatus, TaskNode
import unicodedata

_HOMOGLYPH_TABLE = str.maketrans({
    "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "ѕ": "s", "і": "i", "ј": "j",
    "у": "y", "х": "x", "ԁ": "d", "ԛ": "q", "ԝ": "w", "А": "A", "В": "B", "С": "C",
    "Е": "E", "Н": "H", "І": "I", "Ј": "J", "К": "K", "М": "M", "О": "O", "Р": "P",
    "Ѕ": "S", "Т": "T", "Х": "X", "Ү": "Y", "α": "a", "ο": "o", "ρ": "p", "κ": "k",
})


def normalize_homoglyphs(text: str) -> str:
    """Normalizes Unicode text via NFKD and collapses common Cyrillic/Greek homoglyphs."""
    if not text or text.isascii():
        return text
    norm = unicodedata.normalize("NFKD", text)
    return norm.translate(_HOMOGLYPH_TABLE)


logger = logging.getLogger("jarvis.planner.safety_interceptor")


class SafetyGateInterceptor:
    """
    Coordinates safety verification for planner steps.
    Intercepts risky or destructive TaskNodes and gates their execution
    until affirmative user authorization is received.
    """

    HIGH_RISK_ACTIONS: set[str] = {
        "file_delete", "delete_file", "delete_folder", "remove_directory",
        "format_disk", "system_shutdown", "system_reboot", "registry_edit",
        "drop_database", "truncate_table", "telegram_send_document",
        "telegram_send_photo", "bank_transfer", "order_checkout",
        "shell_execute_destructive", "os_kill_process",
        # Outbound Email
        "email_send", "send_email", "send_mail", "email_send_message",
        # Outbound Zalo
        "zalo_send_message", "zalo_send_image", "send_zalo_message", "zalo_broadcast",
        # Outbound Discord
        "discord_send_message", "discord_send_file", "send_discord_message",
        # Home Assistant actuation
        "home_assistant_call", "smart_home_turn_on", "smart_home_turn_off",
        "smart_home_set_temp", "smart_home_toggle", "home_assistant_turn_on",
        "home_assistant_turn_off", "home_assistant_toggle", "home_assistant_set_temp",
        "home_assistant_set_temperature",
        # Shell Execution
        "shell_exec", "shell_execute", "shell_command",
        # VM lifecycle destructive
        "vm_stop", "vm_delete", "vm_destroy",
        "vm.vmware.stop", "vm.virtualbox.stop",
        "vm.vmware.delete", "vm.virtualbox.delete",
        # Sandbox execution & Subagent lifecycle
        "sandbox_execute_code", "sandbox_python_exec",
        "subagent_spawn", "subagent_kill",
    }

    DANGEROUS_PATTERNS: list[re.Pattern] = [
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
        re.compile(r"[;&|`]\s*(?:rm|del|dir|format|calc|cmd|powershell|bash|sh|net\s+user|whoami|curl|wget)\b", re.IGNORECASE),
        re.compile(r"\$\((?:whoami|id|cat|ls|dir|rm|del|net|curl|wget)[^\)]*\)", re.IGNORECASE),
        re.compile(r"`(?:whoami|id|cat|ls|dir|rm|del|net|curl|wget)[^`]*`", re.IGNORECASE),
        re.compile(r"\|\s*calc(?:\.exe)?\b", re.IGNORECASE),
        re.compile(r"\bdelete\s+all\b", re.IGNORECASE),
        re.compile(r"\bxóa\s+(?:toàn\s+bộ|hết|sạch)\b", re.IGNORECASE),
        re.compile(r"\bxoa\s+(?:toan\s+bo|het|sach)\b", re.IGNORECASE),
        re.compile(r"\bformat\s+(?:ổ|o)\b", re.IGNORECASE),
        re.compile(r"\b(?:bỏ\s+qua|disregard|ignore)\s+.*(?:chỉ\s+thị|hướng\s+dẫn|instruction|command)", re.IGNORECASE),
    ]

    # Deterministic, authoritative recognition of OS power actions. This is
    # independent of (and must never rely on) any LLM/router-computed
    # `IntentResult.requires_confirmation` flag -- that flag may only ever
    # provide an additional UX signal, never the security decision itself.
    SYSTEM_POWER_ACTION_NAMES: set[str] = {"system_power", "power_action"}
    SYSTEM_POWER_DESTRUCTIVE_SUBACTIONS: set[str] = {
        "shutdown", "restart", "reboot", "poweroff", "power_off", "sleep", "hibernate",
    }

    def __init__(
        self,
        safety_gate: SafetyGate | None = None,
        timeout_seconds: float = 30.0,
        custom_high_risk_actions: set[str] | None = None,
    ) -> None:
        self.safety_gate = safety_gate or SafetyGate(timeout_seconds=timeout_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.high_risk_actions = set(self.HIGH_RISK_ACTIONS)
        if custom_high_risk_actions:
            self.high_risk_actions.update(custom_high_risk_actions)
        # Pending-action binding layer: SafetyGate's bare token contract
        # (see jarvis/automation/safety_gate.py) does not itself bind a
        # token to a specific (action_name, parameters) pair or enforce
        # one-shot consumption after successful confirmation -- it only
        # tracks PENDING/CONFIRMED/REJECTED/EXPIRED status. This set +
        # lock is the smallest coherent layer added on top to provide
        # that binding, without changing SafetyGate's own contract (so
        # existing direct SafetyGate consumers, e.g. ShellAssistant, are
        # unaffected).
        self._consumed_tokens: set[str] = set()
        self._verify_lock = threading.RLock()

    def is_high_risk(
        self,
        action_name: str,
        parameters: Any,
        *,
        explicit_flag: bool = False,
    ) -> bool:
        """
        Determines whether an (action_name, parameters) pair constitutes a
        high-risk/destructive operation. This is the single, authoritative
        classifier shared by the planner (via `is_high_risk_node`) and by
        `ActionDispatcher` (via a directly-supplied action_name/payload) --
        it must not be reimplemented elsewhere.

        Checks:
        1. Explicit caller-supplied high-risk flag (e.g. TaskNode.is_high_risk).
        2. Known high-risk action names.
        3. Deterministic OS power-action recognition (shutdown/restart/sleep),
           independent of any LLM/router-supplied confirmation flag.
        4. Action-name prefixes conventionally implying destruction.
        5. Regex pattern matching against parameter string contents.
        """
        if explicit_flag:
            return True

        if not isinstance(action_name, str):
            action_clean = str(action_name or "").strip().lower()
        else:
            action_clean = action_name.strip().lower()
        action_clean_norm = normalize_homoglyphs(action_clean)
        if action_clean_norm in self.high_risk_actions:
            return True
        if action_clean in self.high_risk_actions:
            return True

        if action_clean in self.SYSTEM_POWER_ACTION_NAMES:
            sub_action = ""
            if isinstance(parameters, dict):
                sub_action = str(parameters.get("action") or parameters.get("power_action") or "").strip().lower()
            if sub_action in self.SYSTEM_POWER_DESTRUCTIVE_SUBACTIONS:
                return True

        # Explicitly exclude read-only suffixes/actions from high-risk classification
        safe_actions = {"smart_home_get_state", "home_assistant_get_state",
                        "home_assistant_status", "home_assistant_query",
                        "home_assistant_read", "home_assistant_get_temperature"}
        if action_clean in safe_actions:
            return False

        # Sandbox code execution safety gate: gate if code contains destructive patterns
        if action_clean in ("sandbox_execute_code", "sandbox_python_exec"):
            code_str = ""
            if isinstance(parameters, dict):
                code_str = str(parameters.get("code") or parameters.get("script") or "")
                if parameters.get("is_high_risk"):
                    return True
            elif isinstance(parameters, str):
                code_str = str(parameters)
            if any(pattern.search(code_str) for pattern in self.DANGEROUS_PATTERNS):
                return True
            if any(term in code_str for term in ("os.remove", "os.unlink", "os.system", "subprocess", "shutil.rmtree", "winreg", "format ", "rmdir ")):
                return True
            return False

        # Check action prefixes
        risky_prefixes = (
            "delete_", "remove_", "drop_", "truncate_", "format_", "destroy_",
            "system_shutdown", "system_reboot", "shutdown_", "reboot_",
            "email_send", "send_email",
            "zalo_send", "send_zalo",
            "discord_send", "send_discord",
            "home_assistant_", "smart_home_turn_", "smart_home_set_", "smart_home_toggle",
            "vm_stop", "vm_delete", "vm_destroy", "subagent_",
        )
        if any(action_clean.startswith(prefix) for prefix in risky_prefixes):
            return True

        # Scan string parameters for destructive CLI patterns
        param_strings = self._extract_strings_from_params(parameters)
        _MAX_SCAN_LEN = 4096
        for text in param_strings:
            # ReDoS defense: cap scanning chunks to prevent exponential regex backtracking
            scan_chunks = [text[:_MAX_SCAN_LEN]]
            if len(text) > _MAX_SCAN_LEN:
                scan_chunks.append(text[-_MAX_SCAN_LEN:])
            for chunk in scan_chunks:
                norm_chunk = normalize_homoglyphs(chunk)
                is_same = (norm_chunk is chunk)
                for pattern in self.DANGEROUS_PATTERNS:
                    if pattern.search(chunk) or (not is_same and pattern.search(norm_chunk)):
                        return True

        return False

    def is_high_risk_node(self, node: TaskNode) -> bool:
        """
        Determines whether a TaskNode constitutes a high-risk operation.
        Thin wrapper around `is_high_risk()` so the planner and
        `ActionDispatcher` can never diverge in classification.
        """
        return self.is_high_risk(node.action_name, node.parameters, explicit_flag=node.is_high_risk)

    def _extract_strings_from_params(
        self,
        params: Any,
        seen: set[int] | None = None,
        depth: int = 0,
        max_depth: int = 64,
    ) -> list[str]:
        """Recursively extracts all string values from parameter objects with cycle and depth guards."""
        if depth > max_depth:
            return []
        if seen is None:
            seen = set()
        obj_id = id(params)
        if isinstance(params, (dict, list, tuple, set)):
            if obj_id in seen:
                return []
            seen.add(obj_id)

        strings: list[str] = []
        if isinstance(params, str):
            strings.append(params)
        elif isinstance(params, (bytes, bytearray)):
            try:
                strings.append(params.decode("utf-8", errors="replace"))
            except Exception:
                pass
        elif isinstance(params, dict):
            for k, v in params.items():
                if isinstance(k, str):
                    strings.append(k)
                strings.extend(self._extract_strings_from_params(v, seen=seen, depth=depth + 1, max_depth=max_depth))
        elif isinstance(params, (list, tuple, set)):
            for item in params:
                strings.extend(self._extract_strings_from_params(item, seen=seen, depth=depth + 1, max_depth=max_depth))
        return strings

    def intercept_node(
        self,
        node: TaskNode,
        event_bus: Any | None = None,
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
                "parameters": deepcopy(node.parameters),
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

    def check_confirmation(self, token: str) -> tuple[bool, str]:
        """
        Checks the status of a confirmation token.
        
        Returns:
            (is_confirmed, status_string)
            e.g. (True, "CONFIRMED"), (False, "PENDING"), (False, "EXPIRED"), (False, "REJECTED")
        """
        entry = self.safety_gate.get_pending(token)
        if not entry:
            return False, "UNKNOWN"

        if entry.is_expired:
            entry.status = "EXPIRED"

        is_confirmed = (entry.status == "CONFIRMED")
        return is_confirmed, entry.status

    def gate(
        self,
        action_name: str,
        parameters: Any,
        *,
        description: str | None = None,
        event_bus: Any | None = None,
    ) -> str:
        if not action_name or not isinstance(action_name, str) or not action_name.strip():
            raise ValueError("EMPTY_ACTION: Action name must be a non-empty string.")
        if "\x00" in action_name:
            raise ValueError("INVALID_CHARACTERS: Action name contains null bytes.")
        """
        Generic (non-TaskNode) counterpart to `intercept_node()`, used by
        callers -- primarily `ActionDispatcher` -- that gate a raw
        (action_name, parameters) pair rather than a planner TaskNode.
        Stores the same `{"action_name", "parameters"}` payload shape as
        `intercept_node()` so `verify()` works uniformly against tokens
        issued by either method.
        """
        desc = description or f"Thực thi hành động rủi ro cao: {action_name}"
        token = self.safety_gate.request_confirmation(
            action_desc=desc,
            payload={"action_name": action_name, "parameters": deepcopy(parameters)},
        )
        logger.info("Action '%s' gated by SafetyGate. Token: %s", action_name, token)

        if event_bus and hasattr(event_bus, "publish"):
            try:
                event_bus.publish(
                    "security.confirmation_required",
                    action_name=action_name,
                    token=token,
                    description=desc,
                    parameters=parameters,
                    timeout_seconds=self.timeout_seconds,
                )
            except Exception as e:
                logger.debug("Failed to publish confirmation_required event: %s", e)

        return token

    def verify(self, token: str, action_name: str, parameters: Any) -> tuple[bool, str]:
        """
        Validates and, on success, one-shot-consumes a confirmation token
        against the EXACT (action_name, parameters) pair a caller is about
        to execute. This is the pending-action binding layer: a bare
        SafetyGate token only tracks confirm/reject/expiry, so this method
        additionally enforces that the token was issued for this specific
        action and this specific payload, and can never be reused after a
        successful verification.

        Returns (True, "OK") only if all of the following hold:
        - the token is known,
        - it has not already been consumed by a prior successful verify(),
        - it is not expired,
        - it was not explicitly rejected,
        - its status is exactly "CONFIRMED",
        - its bound action_name matches `action_name` exactly,
        - its bound parameters match `parameters` exactly.

        Otherwise returns (False, reason), where reason is one of:
        "UNKNOWN_TOKEN", "ALREADY_CONSUMED", "EXPIRED", "REJECTED",
        "NOT_CONFIRMED", "ACTION_MISMATCH", "PAYLOAD_MISMATCH".
        """
        with self._verify_lock:
            norm_token = token.strip().upper() if isinstance(token, str) else str(token)
            entry = self.safety_gate.get_pending(token)
            if not entry:
                return False, "UNKNOWN_TOKEN"

            if norm_token in self._consumed_tokens:
                return False, "ALREADY_CONSUMED"

            if entry.is_expired:
                entry.status = "EXPIRED"

            if entry.status == "EXPIRED":
                return False, "EXPIRED"
            if entry.status == "REJECTED":
                return False, "REJECTED"
            if entry.status != "CONFIRMED":
                return False, "NOT_CONFIRMED"

            stored = entry.payload if isinstance(entry.payload, dict) else {}
            if stored.get("action_name") != action_name:
                return False, "ACTION_MISMATCH"
            if stored.get("parameters") != parameters:
                return False, "PAYLOAD_MISMATCH"

            self._consumed_tokens.add(norm_token)
            if hasattr(self.safety_gate, "consume"):
                self.safety_gate.consume(token)
            return True, "OK"

    def confirm(self, token: str) -> bool:
        """Manually confirms a pending safety gate token."""
        return self.safety_gate.confirm(token)

    def confirm_action(self, token: str) -> bool:
        """Manually confirms a pending safety gate token (alias for confirm)."""
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
