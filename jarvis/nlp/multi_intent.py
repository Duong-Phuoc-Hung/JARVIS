"""
jarvis/nlp/multi_intent.py
==========================
Compound Multi-Intent Decomposer and Sequential Execution Pipeline.
Enables parsing and executing compound natural language commands in Vietnamese.
Handles:
  - Clause splitting across conjunctions ('và', 'đồng thời', 'sau đó', 'rồi', ',').
  - Predicate ellipsis resolution (e.g. 'tắt đèn phòng khách và phòng ngủ').
  - Entity protection for search queries and quoted text.
  - Coordination and sequential execution across ActionDispatcher.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from jarvis.llm.models import IntentResult

logger = logging.getLogger("jarvis.nlp.multi_intent")

# Explicit conjunction patterns sorted from longest/most specific to shortest
_STRONG_SEPARATORS = [
    re.compile(r"\s*(?:;\s*|\.\s+)\s*"),
    re.compile(r"\s+(?:sau đó|rồi sau đó|tiep theo|kế tiếp)\s+", re.IGNORECASE),
    re.compile(r"\s+(?:đồng thời|dong thoi|tiện thể|nhân tiện)\s+", re.IGNORECASE),
    re.compile(r"\s+(?:rồi|roi)\s+", re.IGNORECASE),
]

_WEAK_SEPARATORS = [
    re.compile(r"\s+(?:và|va)\s+", re.IGNORECASE),
    re.compile(r",\s*"),
]

# Vietnamese action verbs that indicate a standalone command clause
_ACTION_VERBS = [
    "bật", "bat", "tắt", "tat", "mở", "mo", "đóng", "dong", "thoát", "thoat",
    "tăng", "tang", "giảm", "giam", "chỉnh", "chinh", "vặn", "van", "cho",
    "phát", "phat", "dừng", "dung", "tạm dừng", "tam dung", "chuyển", "chuyen",
    "quay lại", "quay lai", "lùi", "lui", "kiểm tra", "kiem tra", "báo cáo", "bao cao",
    "đặt", "dat", "hẹn", "hen", "nhắc", "nhac", "tìm kiếm", "tim kiem", "tra cứu", "tra cuu",
    "khởi động", "khoi dong", "chạy", "chay", "thu nhỏ", "thu nho", "phóng to", "phong to",
    "sao chép", "sao chep", "copy", "dán", "dan", "paste", "xóa", "xoa", "dọn dẹp", "don dep",
]

# Patterns where conjunctions should NOT be split (Entity Protection)
_SEARCH_PREFIXES = (
    "tìm kiếm", "tim kiem", "tra cứu", "tra cuu", "tìm trên mạng", "tim tren mang",
    "tra google", "tìm", "tim", "google",
)


def _starts_with_action_verb(clause: str) -> bool:
    """Checks if a clause starts with an actionable command verb."""
    cleaned = clause.strip().lower()
    for verb in _ACTION_VERBS:
        if cleaned == verb or cleaned.startswith(f"{verb} "):
            return True
    return False


def _extract_predicate_phrase(clause: str) -> str:
    """
    Extracts the action verb + entity category (e.g. 'tắt đèn', 'mở', 'bật quạt')
    from the beginning of a clause to resolve predicate ellipsis.
    """
    words = clause.strip().split()
    if not words:
        return ""
    # Check 2-word verb phrases first (e.g. 'tắt đèn', 'bật quạt', 'vặn to')
    if len(words) >= 2:
        two_words = f"{words[0]} {words[1]}".lower()
        if any(two_words.startswith(v) for v in ["tắt đèn", "bật đèn", "bật quạt", "tắt quạt", "bật điều hòa", "tắt điều hòa", "mở ứng dụng", "đóng ứng dụng", "tăng âm", "giảm âm"]):
            return f"{words[0]} {words[1]}"
    # Fallback to single verb
    for verb in _ACTION_VERBS:
        if words[0].lower() == verb:
            return words[0]
    return ""


def split_compound_utterance(raw_text: str) -> list[str]:
    """
    Splits a compound Vietnamese natural language utterance into individual command clauses.
    Applies entity protection and predicate ellipsis resolution.

    Args:
        raw_text: Raw input utterance string.

    Returns:
        List of individual actionable command strings.
    """
    text = raw_text.strip()
    if not text:
        return []

    text_lower = text.lower()

    # Entity protection: If the command is a web search query without strong sequential markers,
    # do not split on 'và' or commas (e.g. 'tìm kiếm tom và jerry').
    is_search = any(text_lower.startswith(p) for p in _SEARCH_PREFIXES)
    has_strong_sep = any(sep.search(text) for sep in _STRONG_SEPARATORS)

    if is_search and not has_strong_sep:
        return [text]

    # Step 1: Split by strong separators first
    clauses: list[str] = [text]
    for sep in _STRONG_SEPARATORS:
        new_clauses: list[str] = []
        for c in clauses:
            parts = [p.strip() for p in sep.split(c) if p.strip()]
            new_clauses.extend(parts if parts else [c])
        clauses = new_clauses

    # Step 2: Split by weak separators ('và', ',') if the right side is an action or elided target
    final_clauses: list[str] = []
    for c in clauses:
        sub_parts: list[str] = [c]
        for weak_sep in _WEAK_SEPARATORS:
            splitted: list[str] = []
            for sp in sub_parts:
                tokens = [t.strip() for t in weak_sep.split(sp) if t.strip()]
                if len(tokens) <= 1:
                    splitted.append(sp)
                    continue

                # Verify each split
                valid_split = True
                curr_assembled: list[str] = []
                left_clause = tokens[0]
                curr_assembled.append(left_clause)

                for next_clause in tokens[1:]:
                    # Case A: next clause has its own action verb -> valid split
                    if _starts_with_action_verb(next_clause):
                        curr_assembled.append(next_clause)
                    else:
                        # Case B: next clause does not have an action verb
                        # Check predicate ellipsis (e.g. 'tắt đèn phòng khách' + 'phòng ngủ')
                        pred = _extract_predicate_phrase(curr_assembled[-1])
                        if pred and len(next_clause.split()) <= 4:
                            # Inherit predicate!
                            restored = f"{pred} {next_clause}"
                            curr_assembled.append(restored)
                        else:
                            # Not an actionable split (e.g. "tom và jerry"), merge back
                            valid_split = False
                            break

                if valid_split:
                    splitted.extend(curr_assembled)
                else:
                    splitted.append(sp)
            sub_parts = splitted
        final_clauses.extend(sub_parts)

    return [cl.strip() for cl in final_clauses if cl.strip()]


class CompoundIntentDecomposer:
    """
    Decomposes multi-intent utterances into sequential IntentResults and coordinates execution.
    """

    def __init__(self, router_instance: Any = None) -> None:
        self.router = router_instance

    def decompose(self, text: str) -> list[str]:
        """Splits raw text into command clauses."""
        return split_compound_utterance(text)

    def resolve(self, text: str, router_parser: Any) -> list[IntentResult]:
        """
        Parses all sub-intents in a compound command using the provided router parser.

        Args:
            text: Raw input text.
            router_parser: Callable that takes text and returns IntentResult.

        Returns:
            List of resolved IntentResults.
        """
        clauses = self.decompose(text)
        if not clauses:
            return []

        results: list[IntentResult] = []
        for clause in clauses:
            res = router_parser(clause)
            if res:
                results.append(res)
        return results
