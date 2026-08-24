"""
jarvis.comms
============
Multi-Channel Communications Hub: Telegram, Discord, and IMAP Email integrations.
"""

from jarvis.comms.discord import DiscordBotClient, DiscordBotIntegration
from jarvis.comms.email_imap import EmailMessage, EmailSummaryResult, IMAPEmailReader
from jarvis.comms.telegram import TelegramBotController, TelegramConfig, TelegramUpdate

__all__ = [
    "TelegramBotController",
    "TelegramConfig",
    "TelegramUpdate",
    "DiscordBotClient",
    "DiscordBotIntegration",
    "IMAPEmailReader",
    "EmailMessage",
    "EmailSummaryResult",
]
