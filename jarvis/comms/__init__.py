"""
jarvis.comms
============
Multi-Channel Communications Hub: Telegram, Discord, and IMAP Email integrations.
"""

from jarvis.comms.discord import DiscordBotClient, DiscordBotIntegration
from jarvis.comms.email_imap import EmailMessage, EmailSummaryResult, IMAPEmailReader
from jarvis.comms.rate_limiter import RateLimitConfig, RateLimitResult, TokenBucketRateLimiter
from jarvis.comms.telegram import TelegramBotController, TelegramConfig, TelegramUpdate
from jarvis.comms.xiaozhi_gateway import (
    XiaozhiAudioParams,
    XiaozhiDeviceRegistry,
    XiaozhiGatewayConfig,
    XiaozhiGatewayServer,
    XiaozhiMcpBridge,
    XiaozhiSession,
    XiaozhiSessionState,
)

__all__ = [
    "TelegramBotController",
    "TelegramConfig",
    "TelegramUpdate",
    "DiscordBotClient",
    "DiscordBotIntegration",
    "IMAPEmailReader",
    "EmailMessage",
    "EmailSummaryResult",
    "RateLimitConfig",
    "RateLimitResult",
    "TokenBucketRateLimiter",
    "XiaozhiAudioParams",
    "XiaozhiDeviceRegistry",
    "XiaozhiGatewayConfig",
    "XiaozhiGatewayServer",
    "XiaozhiMcpBridge",
    "XiaozhiSession",
    "XiaozhiSessionState",
]
