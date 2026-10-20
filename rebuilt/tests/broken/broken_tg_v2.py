"""
rebuilt/tests/broken/broken_tg_v2.py
===================================
BROKEN VERSION 5: Violates Rule TG-04.
Fabricates fake system status ("hoạt động bình thường") when psutil fails instead of failing closed.
Target test that MUST FAIL: test_ttest_08_status_anti_fabrication_on_psutil_error.
"""
from __future__ import annotations

import logging
from typing import Any
from telegram_controller import TelegramController as BaseTelegramController

log = logging.getLogger("broken.tg_v2")


class TelegramController(BaseTelegramController):
    def handle_inbound_message(
        self,
        user_id: int,
        text: str,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_user_authorized(user_id):
            return {"status": 403, "error": "Forbidden", "rejected": True}

        clean = text.strip().lower()
        if clean == "/status":
            # BUG: Always returns fabricated status "hoạt động bình thường" regardless of psutil!
            return {
                "status": 200,
                "text": "📊 Trạng thái hệ thống: hoạt động bình thường, mọi dịch vụ ổn định.",
            }

        return super().handle_inbound_message(user_id, text, chat_id)


__all__ = ["TelegramController"]
