"""
rebuilt/tests/broken/broken_tg_v3.py
===================================
BROKEN VERSION 6: Violates Rule TG-01.
Skips whitelist verification, granting access to arbitrary unauthorized users.
Target test that MUST FAIL: test_ttest_01_unauthorized_user_rejection.
"""
from __future__ import annotations

import logging
from typing import Any
from telegram_controller import TelegramController as BaseTelegramController

log = logging.getLogger("broken.tg_v3")


class TelegramController(BaseTelegramController):
    def is_user_authorized(self, user_id: int) -> bool:
        # BUG: Always authorizes everyone without checking allowed_user_ids!
        return True


__all__ = ["TelegramController"]
