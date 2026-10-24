"""
jarvis/core/tiel_ledger.py
==========================
Transactional Intent-Execution Ledger (TIEL) for Asymmetric Cognitive Coordination.
Engineered for Argon Sovereign v5.8.0.

Key Architectural Responsibilities:
  1. Acoustic Timestamp HWND Snapshotting:
     Captures the exact active window, process name, PID, and HWND at speech onset (t_speech_start)
     preventing Alt-Tab race conditions when a user switches windows while speaking.
  2. Two-Phase Commit (2PC) Macro Coordination:
     Coordinates multi-tier intent execution between Tier 2 Local Reflex and Tier 3 Cloud LLM.
     If an action requires synthesized content (e.g., summarization before messaging),
     it enters STAGED_WAITING_PAYLOAD. Execution is blocked until Tier 3 delivers and validates
     the required payload keys, preventing empty or partial side-effect execution.
  3. Fail-Closed Abort & Rollback:
     If payload generation fails, times out, or misses required keys, the transaction transitions
     to ABORTED immediately, discarding staged reservations and logging forensic telemetry.
  4. Windows Atomic Persistence:
     Follows the AGENTS.md §3 Windows Atomic Persistence standard using unique temp files
     and backoff retry loops to prevent WinError 5 access conflicts.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger("jarvis.core.tiel_ledger")


class TransactionStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    STAGED_WAITING_PAYLOAD = "STAGED_WAITING_PAYLOAD"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    EXECUTED = "EXECUTED"


@dataclass(frozen=True)
class AcousticContextSnapshot:
    """Acoustic-anchored OS context snapshot taken at speech start."""

    timestamp_ns: int
    hwnd: int
    window_title: str
    process_name: str
    pid: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "hwnd": self.hwnd,
            "window_title": self.window_title,
            "process_name": self.process_name,
            "pid": self.pid,
        }


@dataclass(frozen=True)
class TransactionRecord:
    """An immutable record representing a coordinated intent execution transaction."""

    tx_id: str
    created_at_ns: int
    intent: str
    slots: dict[str, Any]
    acoustic_snapshot: AcousticContextSnapshot
    required_payload_keys: tuple[str, ...]
    payload: dict[str, Any] = field(default_factory=dict)
    status: TransactionStatus = TransactionStatus.INITIALIZED
    error_message: str | None = None
    committed_at_ns: int | None = None
    executed_at_ns: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "created_at_ns": self.created_at_ns,
            "intent": self.intent,
            "slots": self.slots,
            "acoustic_snapshot": self.acoustic_snapshot.to_dict(),
            "required_payload_keys": list(self.required_payload_keys),
            "payload": self.payload,
            "status": self.status.value,
            "error_message": self.error_message,
            "committed_at_ns": self.committed_at_ns,
            "executed_at_ns": self.executed_at_ns,
        }


class TransactionalIntentExecutionLedger:
    """
    Thread-safe Two-Phase Commit Transactional Ledger for JARVIS.
    Synchronizes local reflexes with slow cognitive planners.
    """

    def __init__(self, persist_path: Path | str | None = None) -> None:
        self._lock = threading.RLock()
        self._save_lock = threading.Lock()
        self._persist_path: Path | None = Path(persist_path) if persist_path else None
        self._transactions: dict[str, TransactionRecord] = {}

    @staticmethod
    def capture_acoustic_snapshot() -> AcousticContextSnapshot:
        """
        Captures foreground window state at speech start.
        Uses native Win32 user32/kernel32 calls when available, with safe fallbacks.
        """
        now_ns = time.time_ns()
        hwnd = 0
        window_title = "Unknown"
        process_name = "unknown.exe"
        pid = 0

        try:
            if os.name == "nt":
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                hwnd = int(user32.GetForegroundWindow())
                if hwnd != 0:
                    # Get Window Title
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        window_title = buff.value

                    # Get Process ID
                    lpdw_process_id = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_process_id))
                    pid = int(lpdw_process_id.value)

                    # Get Process Image Name
                    if pid > 0:
                        process_handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                        if process_handle:
                            try:
                                img_buf = ctypes.create_unicode_buffer(1024)
                                size = ctypes.c_ulong(1024)
                                if kernel32.QueryFullProcessImageNameW(process_handle, 0, img_buf, ctypes.byref(size)):
                                    process_name = Path(img_buf.value).name
                            finally:
                                kernel32.CloseHandle(process_handle)
        except Exception as exc:
            logger.debug("Non-fatal Win32 snapshot query error: %s", exc)

        return AcousticContextSnapshot(
            timestamp_ns=now_ns,
            hwnd=hwnd,
            window_title=window_title,
            process_name=process_name,
            pid=pid,
        )

    def prepare_transaction(
        self,
        intent: str,
        slots: Mapping[str, Any] | None = None,
        acoustic_snapshot: AcousticContextSnapshot | None = None,
        required_payload_keys: Sequence[str] = (),
    ) -> TransactionRecord:
        """
        Stages a new intent transaction.
        If required_payload_keys is provided, status is set to STAGED_WAITING_PAYLOAD.
        Otherwise, status is set directly to COMMITTED.
        """
        now_ns = time.time_ns()
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        snapshot = acoustic_snapshot or self.capture_acoustic_snapshot()
        req_keys = tuple(sorted(str(k) for k in required_payload_keys))
        slot_dict = dict(slots) if slots else {}

        status = TransactionStatus.STAGED_WAITING_PAYLOAD if req_keys else TransactionStatus.COMMITTED
        committed_at = now_ns if status == TransactionStatus.COMMITTED else None

        record = TransactionRecord(
            tx_id=tx_id,
            created_at_ns=now_ns,
            intent=str(intent),
            slots=slot_dict,
            acoustic_snapshot=snapshot,
            required_payload_keys=req_keys,
            payload={},
            status=status,
            committed_at_ns=committed_at,
        )

        with self._lock:
            self._transactions[tx_id] = record

        logger.debug(
            "Transaction prepared: id=%s intent=%s status=%s req_keys=%s",
            tx_id,
            intent,
            status.value,
            req_keys,
        )
        return record

    def commit_payload(self, tx_id: str, payload: Mapping[str, Any]) -> TransactionRecord:
        """
        Commits payload generated by Tier 3 (Cloud LLM / reasoning agent).
        Transitions transaction to COMMITTED if all required keys are present and valid.
        Transitions to ABORTED if any required key is missing or empty.
        """
        with self._lock:
            record = self._transactions.get(tx_id)
            if not record:
                raise KeyError(f"Transaction '{tx_id}' not found in ledger.")

            if record.status not in (TransactionStatus.INITIALIZED, TransactionStatus.STAGED_WAITING_PAYLOAD):
                raise ValueError(f"Cannot commit payload to transaction '{tx_id}' with status {record.status.value}")

            payload_dict = dict(payload)
            missing_keys = [k for k in record.required_payload_keys if k not in payload_dict or payload_dict[k] is None or payload_dict[k] == ""]

            now_ns = time.time_ns()
            if missing_keys:
                err_msg = f"Missing or empty required payload keys: {missing_keys}"
                updated = TransactionRecord(
                    tx_id=record.tx_id,
                    created_at_ns=record.created_at_ns,
                    intent=record.intent,
                    slots=record.slots,
                    acoustic_snapshot=record.acoustic_snapshot,
                    required_payload_keys=record.required_payload_keys,
                    payload=payload_dict,
                    status=TransactionStatus.ABORTED,
                    error_message=err_msg,
                )
                self._transactions[tx_id] = updated
                logger.warning("Transaction %s aborted fail-closed: %s", tx_id, err_msg)
                return updated

            updated = TransactionRecord(
                tx_id=record.tx_id,
                created_at_ns=record.created_at_ns,
                intent=record.intent,
                slots=record.slots,
                acoustic_snapshot=record.acoustic_snapshot,
                required_payload_keys=record.required_payload_keys,
                payload=payload_dict,
                status=TransactionStatus.COMMITTED,
                committed_at_ns=now_ns,
            )
            self._transactions[tx_id] = updated
            logger.debug("Transaction %s successfully committed with payload keys=%s", tx_id, list(payload_dict.keys()))
            return updated

    def abort_transaction(self, tx_id: str, reason: str = "Explicit abortion") -> TransactionRecord:
        """Aborts a transaction with reason."""
        with self._lock:
            record = self._transactions.get(tx_id)
            if not record:
                raise KeyError(f"Transaction '{tx_id}' not found in ledger.")

            updated = TransactionRecord(
                tx_id=record.tx_id,
                created_at_ns=record.created_at_ns,
                intent=record.intent,
                slots=record.slots,
                acoustic_snapshot=record.acoustic_snapshot,
                required_payload_keys=record.required_payload_keys,
                payload=record.payload,
                status=TransactionStatus.ABORTED,
                error_message=reason,
            )
            self._transactions[tx_id] = updated
            logger.info("Transaction %s aborted: %s", tx_id, reason)
            return updated

    def mark_executed(self, tx_id: str) -> TransactionRecord:
        """Marks a committed transaction as executed on Win32."""
        with self._lock:
            record = self._transactions.get(tx_id)
            if not record:
                raise KeyError(f"Transaction '{tx_id}' not found in ledger.")
            if record.status != TransactionStatus.COMMITTED:
                raise RuntimeError(f"Cannot execute transaction '{tx_id}' in state {record.status.value}. Must be COMMITTED.")

            updated = TransactionRecord(
                tx_id=record.tx_id,
                created_at_ns=record.created_at_ns,
                intent=record.intent,
                slots=record.slots,
                acoustic_snapshot=record.acoustic_snapshot,
                required_payload_keys=record.required_payload_keys,
                payload=record.payload,
                status=TransactionStatus.EXECUTED,
                committed_at_ns=record.committed_at_ns,
                executed_at_ns=time.time_ns(),
            )
            self._transactions[tx_id] = updated
            return updated

    def get_transaction(self, tx_id: str) -> TransactionRecord | None:
        """Retrieves transaction record by ID."""
        with self._lock:
            return self._transactions.get(tx_id)

    def get_active_transactions(self) -> list[TransactionRecord]:
        """Returns list of pending/active transactions."""
        with self._lock:
            return [
                tx for tx in self._transactions.values()
                if tx.status in (TransactionStatus.INITIALIZED, TransactionStatus.STAGED_WAITING_PAYLOAD)
            ]

    def save_to_disk(self) -> bool:
        """
        Persists ledger records atomically to disk according to AGENTS.md §3 standards.
        """
        if not self._persist_path:
            return False

        with self._save_lock:
            with self._lock:
                snapshot = {k: v.to_dict() for k, v in self._transactions.items()}

            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tid = threading.get_ident()
            tns = time.time_ns()
            tmp_path = self._persist_path.parent / f".tmp.{tid}.{tns}.json"

            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, ensure_ascii=False)

                # Atomic replace with retry for Windows handle locking
                for attempt in range(5):
                    try:
                        tmp_path.replace(self._persist_path)
                        return True
                    except OSError as exc:
                        if attempt == 4:
                            raise
                        time.sleep(0.02 * (attempt + 1))
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
        return False
