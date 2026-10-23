"""
jarvis/llm/local_reasoner.py
============================
In-Process Argon Native Nano Local Reasoner Adapter (Argon Sovereign Tier 2 Cortex).
Provides sub-5ms local heuristic and slot reasoning on CPU with 0 MB VRAM:
- Resolves multi-turn anaphoric pronouns ('nó', 'cái đó', 'lúc nãy', 'trước đó', 'lại').
- Resolves colloquial and descriptive system commands ('phần mềm nghe nhạc', 'máy có nóng không', 'dọn ram').
- Functions as Tier 2 Local Offline Reasoner in LLMIntentRouter.parse_intent when Tier 1
  NLU confidence is < 0.35 or when offline without cloud LLM keys.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.context.screen_context import AWACIEngine, WindowContext
from jarvis.llm.models import IntentResult
from jarvis.planner.action_tree import ActionCandidateNode, InProcessGrammarTreeSearch

logger = logging.getLogger("jarvis.llm.local_reasoner")


class ArgonNanoLocalReasoner:
    """
    Tier 2 In-Process Local Reasoner Adapter.
    Performs fast heuristic and slot resolution offline before falling back to unknown_intent.
    """

    def __init__(
        self,
        awaci_engine: AWACIEngine | None = None,
        confidence_threshold: float = 0.35,
        action_tree: InProcessGrammarTreeSearch | None = None,
    ) -> None:
        self.awaci_engine = awaci_engine or AWACIEngine()
        self.confidence_threshold = float(confidence_threshold)
        self.action_tree = action_tree or InProcessGrammarTreeSearch(confidence_cutoff=self.confidence_threshold)

    def reason(
        self,
        text: str,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        awaci_context: WindowContext | None = None,
    ) -> IntentResult | None:
        """
        Attempts to resolve ambiguous or multi-turn natural language utterances locally.

        Args:
            text: Raw input text utterance.
            context: Optional conversational or session context.
            history: Optional list of previous interaction turns.
            awaci_context: Optional current active window context.

        Returns:
            IntentResult with source='argon_nano_local_reasoner' if resolved, else None.
        """
        clean = text.strip()
        if not clean:
            return None

        clean_lower = clean.lower()

        # 1. Multi-turn Anaphora & Repetition Resolution
        anaphora_result = self._resolve_anaphora(clean_lower, clean, history=history, awaci_context=awaci_context)
        if anaphora_result is not None:
            return anaphora_result

        # 2. Colloquial / Descriptive Hardware & System Queries
        system_result = self._resolve_system_heuristics(clean_lower, clean)
        if system_result is not None:
            return system_result

        # 3. Colloquial Application / Media Invocations
        app_result = self._resolve_app_heuristics(clean_lower, clean)
        if app_result is not None:
            return app_result

        # 4. In-Process Grammar-Constrained Action-Tree Search (Argon Sovereign v6.0)
        tree_result = self._resolve_action_tree(clean_lower, clean, awaci_context=awaci_context)
        if tree_result is not None:
            return tree_result

        return None

    def _resolve_anaphora(
        self,
        clean_lower: str,
        raw_text: str,
        history: list[dict[str, Any]] | None = None,
        awaci_context: WindowContext | None = None,
    ) -> IntentResult | None:
        """Resolves pronoun references ('nó', 'cái này', 'lúc nãy', 'làm lại')."""
        # A. Repetition: "làm lại cái này", "làm lại cái đó", "làm lại", "lặp lại"
        if re.search(
            r"^(?:jarvis[,\s]*)?(?:làm\s*lại(?:\s*cái\s*(?:đó|do|này|nay|đây|day))?|lặp\s*lại(?:\s*(?:cái\s*(?:đó|do|này|nay)|lệnh))?|thực\s*hiện\s*lại(?:\s*cái\s*(?:đó|này))?|chạy\s*lại(?:\s*lệnh)?)[.!?]?$",
            clean_lower,
        ):
            last_intent = self._get_last_meaningful_intent(history)
            if last_intent is not None:
                return IntentResult(
                    action_name=last_intent.get("action_name", "unknown_intent"),
                    parameters=dict(last_intent.get("parameters", {})),
                    confidence=0.88,
                    source="argon_nano_local_reasoner",
                    raw_text=raw_text,
                    response_text="Đang thực hiện lại hành động vừa rồi cho Ngài.",
                )

        # B. Close current / referred item: "đóng nó lại", "tắt nó đi", "thoát cái này", "đóng cái đó"
        if re.search(
            r"\b(?:đóng|dong|tắt|tat|thoát|thoat)\s+(?:nó|no|cái\s*(?:này|nay|đó|do|kia)|cửa\s*sổ\s*(?:này|nay|đó|do))\b",
            clean_lower,
        ):
            # Target from active window
            app_target = "current"
            win_ctx = self._get_window_context(awaci_context)
            if win_ctx and win_ctx.process_name:
                app_target = win_ctx.process_name.replace(".exe", "")
            else:
                last_intent = self._get_last_meaningful_intent(history)
                if last_intent and isinstance(last_intent.get("parameters"), dict):
                    params = last_intent["parameters"]
                    if params.get("app_name"):
                        app_target = params["app_name"]
                    elif params.get("target"):
                        app_target = params["target"]

            return IntentResult(
                action_name="app_close",
                parameters={"app_name": app_target, "target": app_target},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text=f"Đang đóng ứng dụng {app_target} cho Ngài.",
            )

        # C. Maximize / minimize current: "phóng to nó", "thu nhỏ nó", "phóng to toàn màn hình"
        if re.search(r"\b(?:phóng\s*to|phong\s*to|toàn\s*màn\s*hình)\s*(?:nó|lên|cửa\s*sổ)?\b", clean_lower):
            return IntentResult(
                action_name="window_control",
                parameters={"action": "maximize"},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang phóng to cửa sổ cho Ngài.",
            )

        if re.search(r"\b(?:thu\s*nhỏ|thu\s*nho|ẩn)\s*(?:nó|xuống|cửa\s*sổ)?\b", clean_lower):
            return IntentResult(
                action_name="window_control",
                parameters={"action": "minimize"},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang thu nhỏ cửa sổ cho Ngài.",
            )

        # D. Anaphoric similarity: "tương tự với cửa sổ lúc nãy"
        if "tương tự" in clean_lower or "tuong tu" in clean_lower:
            last_intent = self._get_last_meaningful_intent(history)
            if last_intent is not None:
                return IntentResult(
                    action_name=last_intent.get("action_name", "unknown_intent"),
                    parameters=dict(last_intent.get("parameters", {})),
                    confidence=0.80,
                    source="argon_nano_local_reasoner",
                    raw_text=raw_text,
                    response_text="Đang thực hiện lệnh tương tự cho Ngài.",
                )

        return None

    def _resolve_system_heuristics(self, clean_lower: str, raw_text: str) -> IntentResult | None:
        """Resolves colloquial hardware and system power inquiries."""
        # Hardware heat / fans: "máy có nóng không", "quạt kêu to quá", "nhiệt độ thế nào"
        if any(k in clean_lower for k in ("nóng không", "nong khong", "quạt kêu", "quat keu", "nhiệt độ máy", "nhiet do may", "nhiệt độ pc")):
            return IntentResult(
                action_name="hardware_status_query",
                parameters={"component": "cpu"},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang kiểm tra nhiệt độ và cảm biến phần cứng cho Ngài.",
            )

        # Memory cleaning: "dọn dẹp ram", "dọn ram", "giải phóng bộ nhớ", "máy lag quá"
        if any(k in clean_lower for k in ("dọn dẹp ram", "don dep ram", "dọn ram", "don ram", "giải phóng ram", "máy lag", "may lag", "giải phóng bộ nhớ", "tối ưu ram")):
            return IntentResult(
                action_name="healing_watchdog_heal",
                parameters={"auto_kill": False},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang giải phóng bộ nhớ RAM và tối ưu tiến trình cho Ngài.",
            )

        # Screen rest: "cho màn hình nghỉ", "tắt màn hình", "nghỉ ngơi chút"
        if any(k in clean_lower for k in ("màn hình nghỉ", "man hinh nghi", "tắt màn hình", "tat man hinh")):
            return IntentResult(
                action_name="system_power",
                parameters={"action": "screen_off"},
                confidence=0.88,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang tắt màn hình để tiết kiệm năng lượng cho Ngài.",
            )

        return None

    def _resolve_app_heuristics(self, clean_lower: str, raw_text: str) -> IntentResult | None:
        """Resolves descriptive software invocations ('phần mềm nghe nhạc', 'trình duyệt')."""
        if any(k in clean_lower for k in ("nghe nhạc", "nghe nhac", "phần mềm nghe nhạc", "trình phát nhạc", "bật nhạc", "bat nhac", "mở nhạc", "mo nhac", "phát nhạc", "phat nhac", "bật bài", "bat bai", "phát bài", "phat bai", "mở bài", "mo bai")) or clean_lower.startswith(("bật bài ", "phát bài ", "mở bài ")):
            query = ""
            m_song = re.search(r"(?:bài\s*(?:hát)?|bài|nhạc)\s+([a-zA-Z0-9\s_à-ỹÀ-Ỹ]+)$", raw_text.strip(), re.IGNORECASE)
            if m_song:
                candidate = m_song.group(1).strip()
                if candidate.lower() not in ("lên", "đi", "nghe", "cho tôi", "nhé", "nào", "nữa", "lên đi", "spotify", "spotifile"):
                    query = candidate
            return IntentResult(
                action_name="spotify",
                parameters={"query": query, "action": "play"} if query else {"query": "", "name": "spotify", "action": "play"},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang phát nhạc trên Spotify cho Ngài." if not query else f"Đang phát bài {query} trên Spotify cho Ngài.",
            )

        # Web browser / video viewing: "mở trình duyệt xem video", "vào mạng xem phim", "lên youtube", "mở youtube"
        if any(k in clean_lower for k in ("lên youtube", "len youtube", "xem youtube", "vào mạng", "trình duyệt xem", "mở youtube", "mo youtube", "bật youtube", "bat youtube")):
            return IntentResult(
                action_name="app_open",
                parameters={"app_name": "chrome", "installed_only": True},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang mở trình duyệt cho Ngài.",
            )

        # Coding / programming: "mở công cụ gõ code", "vào visual studio", "viết code"
        if any(k in clean_lower for k in ("gõ code", "go code", "lập trình", "lap trinh", "công cụ code", "viết code", "viet code", "mở code", "mo code")):
            return IntentResult(
                action_name="app_open",
                parameters={"app_name": "vscode", "installed_only": True},
                confidence=0.85,
                source="argon_nano_local_reasoner",
                raw_text=raw_text,
                response_text="Đang mở Visual Studio Code cho Ngài.",
            )

        return None

    def _get_last_meaningful_intent(self, history: list[Any] | None) -> dict[str, Any] | None:
        """Extracts the most recent actionable intent from conversation history."""
        if not history:
            return None
        for turn in reversed(history):
            if isinstance(turn, dict) and "action_name" in turn:
                act = turn.get("action_name")
                if act and act not in ("unknown_intent", "generic_llm_response"):
                    return turn
            elif hasattr(turn, "action_name"):
                act = getattr(turn, "action_name")
                if act and act not in ("unknown_intent", "generic_llm_response"):
                    params = dict(getattr(turn, "parameters", {})) if isinstance(getattr(turn, "parameters", None), dict) else {}
                    return {
                        "action_name": act,
                        "parameters": params,
                        "confidence": float(getattr(turn, "confidence", 1.0)),
                        "raw_text": getattr(turn, "raw_text", ""),
                    }
        return None

    def _get_window_context(self, override_ctx: WindowContext | None) -> WindowContext | None:
        """Retrieves active window context safely."""
        if override_ctx is not None:
            return override_ctx
        if self.awaci_engine is not None:
            try:
                if hasattr(self.awaci_engine, "get_active_window_context"):
                    return self.awaci_engine.get_active_window_context()
                elif hasattr(self.awaci_engine, "get_current_window_context"):
                    return self.awaci_engine.get_current_window_context()
            except Exception:
                pass
        return None

    def _resolve_action_tree(
        self,
        clean_lower: str,
        raw_text: str,
        awaci_context: WindowContext | None = None,
    ) -> IntentResult | None:
        """Resolves intent via In-Process Grammar-Constrained Action-Tree Search."""
        if self.action_tree is None:
            return None

        priors: dict[str, float] = {}
        if re.search(r"\b(?:âm lượng|am luong|chỉnh âm lượng|tăng âm lượng|giảm âm lượng|bật loa|tắt loa)\b", clean_lower):
            priors["system_volume"] = 0.85
            priors["system"] = 0.85
        elif re.search(r"\b(?:độ sáng|do sang|chỉnh độ sáng|tăng độ sáng|giảm độ sáng)\b", clean_lower):
            priors["screen_brightness"] = 0.85
            priors["system"] = 0.85
        elif re.search(r"\b(?:nghe nhạc|nghe nhac|bật nhạc|bat nhac|phát nhạc|phat nhac|bài hát|bai hat|ca khúc|ca khuc|spotify)\b", clean_lower):
            priors["spotify_play"] = 0.85
            priors["media"] = 0.85
        elif re.search(r"\b(?:tắt máy(?:\s*tính)?|tat may|khởi động lại|khoi dong lai|shutdown|reboot)\b", clean_lower):
            priors["system_power"] = 0.85
            priors["system"] = 0.85
        elif re.search(r"\b(?:ghi chú|ghi chu|tạo ghi chú|tao ghi chu|viết ghi chú|viet ghi chu)\b", clean_lower):
            priors["note_create"] = 0.85
            priors["productivity"] = 0.85
        elif re.search(r"\b(?:thời tiết|thoi tiet|dự báo thời tiết|du bao thoi tiet)\b", clean_lower):
            priors["weather_query"] = 0.85
            priors["productivity"] = 0.85
        elif re.search(r"\b(?:tab mới|tab moi|mở tab mới|mo tab moi)\b", clean_lower):
            priors["tab_new"] = 0.85
            priors["navigation"] = 0.85
        elif re.search(r"\b(?:đóng tab|dong tab|tắt tab|tat tab)\b", clean_lower):
            priors["tab_close"] = 0.85
            priors["navigation"] = 0.85

        if not priors:
            return None

        win_ctx = self._get_window_context(awaci_context)
        win_title = win_ctx.title if win_ctx else ""

        candidate = self.action_tree.search(
            text=raw_text,
            nlu_priors=priors,
            active_window_title=win_title,
            privilege_level="USER",
        )

        if candidate is not None and candidate.value_score >= self.confidence_threshold:
            return IntentResult(
                action_name=candidate.intent,
                parameters=candidate.parameters,
                confidence=candidate.value_score,
                source="argon_action_tree_search",
                raw_text=raw_text,
            )

        return None


__all__ = ["ArgonNanoLocalReasoner"]
