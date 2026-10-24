"""
jarvis/learning/macro_miner.py
==============================
Sequential Action Trajectory Miner (PrefixSpan / Frequent Workflow Mining).
Engineered for Argon Sovereign v5.9.5.

Responsibilities:
  1. Action Trajectory Recording:
     Captures sequentially executed Win32 commands (intent, parameters, active app, timestamp).
  2. Frequent Sequential Subsequence Mining:
     Mines repeated compound action patterns of length 2 to 5 that occur >= min_support times
     within a coherent time window (e.g., < 60s per session).
  3. Candidate Macro Generation:
     Synthesizes candidate compound workflows and generates natural language voice trigger hypotheses
     ready for In-Situ GRPO validation and ActionTree crystallization.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

logger = logging.getLogger("jarvis.learning.macro_miner")


@dataclass(frozen=True)
class LoggedAction:
    """An individual recorded user action."""

    intent: str
    slots: dict[str, Any]
    context_app: str
    timestamp_s: float


@dataclass(frozen=True)
class CandidateMacro:
    """A mined frequent action sequence proposed for macro crystallization."""

    macro_id: str
    action_intents: tuple[str, ...]
    action_slots: tuple[dict[str, Any], ...]
    support_count: int
    context_app: str
    suggested_triggers: tuple[str, ...]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro_id": self.macro_id,
            "action_intents": list(self.action_intents),
            "action_slots": list(self.action_slots),
            "support_count": self.support_count,
            "context_app": self.context_app,
            "suggested_triggers": list(self.suggested_triggers),
            "confidence": self.confidence,
        }


class SequentialMacroMiner:
    """
    Mines frequent action patterns from user session history using sequential pattern analysis.
    """

    def __init__(
        self,
        max_history_len: int = 1000,
        session_gap_threshold_s: float = 60.0,
    ) -> None:
        self.max_history_len = max(50, int(max_history_len))
        self.session_gap_threshold_s = float(session_gap_threshold_s)
        self._history: list[LoggedAction] = []

    def record_action(
        self,
        intent: str,
        slots: Mapping[str, Any] | None = None,
        context_app: str = "desktop",
        timestamp_s: float | None = None,
    ) -> None:
        """Records an executed action into the sequence trajectory."""
        entry = LoggedAction(
            intent=str(intent).strip(),
            slots=dict(slots) if slots else {},
            context_app=str(context_app).strip().lower(),
            timestamp_s=time.time() if timestamp_s is None else float(timestamp_s),
        )
        self._history.append(entry)
        if len(self._history) > self.max_history_len:
            self._history.pop(0)

    def extract_sessions(self) -> list[list[LoggedAction]]:
        """Partitions the linear history into cohesive sessions based on time gaps."""
        if not self._history:
            return []

        sessions: list[list[LoggedAction]] = []
        current_session: list[LoggedAction] = [self._history[0]]

        for i in range(1, len(self._history)):
            prev_act = self._history[i - 1]
            curr_act = self._history[i]
            if (curr_act.timestamp_s - prev_act.timestamp_s) <= self.session_gap_threshold_s:
                current_session.append(curr_act)
            else:
                sessions.append(current_session)
                current_session = [curr_act]

        if current_session:
            sessions.append(current_session)

        return sessions

    def mine_frequent_macros(
        self,
        min_support: int = 3,
        min_length: int = 2,
        max_length: int = 4,
    ) -> list[CandidateMacro]:
        """
        Mines frequent contiguous subsequences occurring >= min_support times across sessions.
        """
        sessions = self.extract_sessions()
        if not sessions:
            return []

        # Count occurrences of n-gram intent sequences
        ngram_counts: dict[tuple[str, ...], int] = collections.defaultdict(int)
        ngram_slots: dict[tuple[str, ...], list[tuple[dict[str, Any], ...]]] = collections.defaultdict(list)
        ngram_contexts: dict[tuple[str, ...], list[str]] = collections.defaultdict(list)

        for session in sessions:
            n = len(session)
            if n < min_length:
                continue

            # Extract all contiguous sub-sequences of lengths from min_length to max_length
            for length in range(min_length, min(n + 1, max_length + 1)):
                for start_idx in range(n - length + 1):
                    subseq = session[start_idx : start_idx + length]
                    intent_key = tuple(a.intent for a in subseq)
                    slot_key = tuple(a.slots for a in subseq)
                    ctx = subseq[0].context_app

                    ngram_counts[intent_key] += 1
                    ngram_slots[intent_key].append(slot_key)
                    ngram_contexts[intent_key].append(ctx)

        # Filter by min_support
        candidates: list[CandidateMacro] = []
        total_sessions = max(1, len(sessions))

        for intent_tuple, count in ngram_counts.items():
            if count >= min_support:
                dominant_ctx = collections.Counter(ngram_contexts[intent_tuple]).most_common(1)[0][0]
                # Canonical slots: use the most recent occurrence
                canonical_slots = ngram_slots[intent_tuple][-1]
                confidence = min(1.0, float(count) / float(total_sessions))

                # Generate natural Vietnamese trigger phrase hypotheses
                triggers = self._generate_suggested_triggers(intent_tuple)
                macro_hash = abs(hash(intent_tuple)) % 100000

                candidates.append(
                    CandidateMacro(
                        macro_id=f"macro_auto_{macro_hash:05d}",
                        action_intents=intent_tuple,
                        action_slots=canonical_slots,
                        support_count=count,
                        context_app=dominant_ctx,
                        suggested_triggers=tuple(triggers),
                        confidence=confidence,
                    )
                )

        # Sort by support count descending
        candidates.sort(key=lambda m: m.support_count, reverse=True)
        return candidates

    @staticmethod
    def _generate_suggested_triggers(intents: tuple[str, ...]) -> list[str]:
        """Synthesizes human-friendly trigger phrase suggestions for the macro."""
        human_readable_intents = [i.replace("_", " ") for i in intents]
        base_phrase = " và ".join(human_readable_intents)
        return [
            base_phrase,
            f"thực hiện quy trình {' rồi '.join(human_readable_intents)}",
            f"chạy macro {intents[0].replace('_', ' ')}",
        ]

    def clear_history(self) -> None:
        """Clears action trajectory history."""
        self._history.clear()
