"""
rebuilt/tests/broken/broken_tg_v1.py
===================================
BROKEN VERSION 4: Violates Rule TG-05.
Returns fake hardcoded text ("Lệnh thoại đã nhận") when STT throws an error instead of failing closed.
Target test that MUST FAIL: test_ttest_05_voice_stt_exception_fail_closed.
"""
from __future__ import annotations

import logging
from typing import Any
from telegram_controller import TelegramController as BaseTelegramController

log = logging.getLogger("broken.tg_v1")


class TelegramController(BaseTelegramController):
    def handle_inbound_voice(
        self,
        user_id: int,
        voice_bytes: bytes,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_user_authorized(user_id):
            return {"status": 403, "error": "Forbidden: Unauthorized User ID", "rejected": True}

        if not (self.stt_engine and hasattr(self.stt_engine, "transcribe")):
            return {"ok": False, "status": 503, "error_code": "STT_UNAVAILABLE"}

        try:
            transcribed_text = self.stt_engine.transcribe(voice_bytes)
        except Exception:
            # BUG: Fabricates fake success message instead of failing closed!
            return {
                "ok": True,
                "status": 200,
                "text": "Lệnh thoại đã nhận",
            }

        return self.handle_inbound_message(user_id, transcribed_text, chat_id)


__all__ = ["TelegramController"]
