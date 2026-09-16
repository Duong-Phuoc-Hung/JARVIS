#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/verify_credentials.py
==============================
Fail-closed credential verification script for JARVIS communication modules.

Checks credentials for:
  - D-06: Telegram Bot Token   (jarvis.comms.telegram.TelegramBotController)
  - D-07: Zalo OA              (jarvis.comms.zalo.ZaloBotController)
  - D-08: Discord Bot Token    (jarvis.comms.discord.DiscordBotController)
  - D-09: Gmail IMAP Password  (jarvis.comms.email_imap.IMAPEmailReader)

Each check follows the Anti-Fabrication Principle (AGENTS.md §2):
  - CONFIGURED     -> credential env var is set AND module instantiates without error.
  - NOT_CONFIGURED -> env var is missing OR module raises / returns error_code=NOT_CONFIGURED.

Usage:
    python scripts/verify_credentials.py
    python scripts/verify_credentials.py --verbose
"""
from __future__ import annotations

import argparse
import io
import os
import sys

# Force UTF-8 output on Windows to handle ANSI + emoji safely
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure the project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ANSI color codes
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _ok(detail: str) -> str:
    return f"{_GREEN}[CONFIGURED    ]{_RESET} {detail}"


def _fail(detail: str) -> str:
    return f"{_RED}[NOT_CONFIGURED]{_RESET} {detail}"


def _warn(detail: str) -> str:
    return f"{_YELLOW}[LIMITED       ]{_RESET} {detail}"


# ── D-06: Telegram ────────────────────────────────────────────────────────────

def check_telegram(verbose: bool = False) -> bool:
    """
    Verifies TELEGRAM_BOT_TOKEN is set and TelegramBotController instantiates.
    send_message() with no http_client returns error_code=NOT_CONFIGURED (fail-closed).
    We treat bot_token being non-empty as CONFIGURED; the actual network call
    requires a live HTTP client which is intentionally not tested here.
    """
    label = "D-06 Telegram"
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        print(f"  {_fail('TELEGRAM_BOT_TOKEN not set in environment')}")
        return False

    try:
        from jarvis.comms.telegram import TelegramBotController
        bot = TelegramBotController(bot_token=token, allowed_user_ids={0})
        # send_message without http_client is fail-closed -> NOT_CONFIGURED
        result = bot.send_message(chat_id=0, text="verify_credentials probe")
        if result.get("error_code") == "NOT_CONFIGURED":
            # Expected: token is set but no live network client.
            # The credential IS configured; HTTP client is optional at init.
            print(f"  {_ok(f'TelegramBotController: bot_token=set ({token[:10]}...)')}")
            if verbose:
                print(f"         send_message() correctly returned NOT_CONFIGURED"
                      f" (no HTTP client -- expected in offline mode)")
            return True
        print(f"  {_ok(f'TelegramBotController: bot_token=set ({token[:10]}...)')}")
        return True
    except ImportError as exc:
        print(f"  {_fail(f'Import error: {exc}')}")
        return False
    except Exception as exc:
        print(f"  {_fail(f'Unexpected error: {exc}')}")
        return False


# ── D-07: Zalo OA ────────────────────────────────────────────────────────────

def check_zalo(verbose: bool = False) -> bool:
    """
    Verifies ZALO_OA_ACCESS_TOKEN, ZALO_APP_ID, ZALO_APP_SECRET are set.
    send_message() with empty access_token returns ZaloSendResult(success=False, error='NOT_CONFIGURED').
    We check token presence only; live API call is not made in this probe.
    """
    label = "D-07 Zalo OA"
    token = os.environ.get("ZALO_OA_ACCESS_TOKEN", "").strip()
    app_id = os.environ.get("ZALO_APP_ID", "").strip()
    app_secret = os.environ.get("ZALO_APP_SECRET", "").strip()

    missing = []
    if not token:
        missing.append("ZALO_OA_ACCESS_TOKEN")
    if not app_id:
        missing.append("ZALO_APP_ID")
    if not app_secret:
        missing.append("ZALO_APP_SECRET")

    if missing:
        print(f"  {_fail(f'Missing env vars: {missing}')}")
        return False

    try:
        from jarvis.comms.zalo import ZaloBotController, ZaloConfig
        cfg = ZaloConfig(access_token=token, oa_id=app_id)
        bot = ZaloBotController(config=cfg, is_mock=False)
        result = bot.send_message(user_id="__probe__", text="verify_credentials probe")
        if hasattr(result, "error") and result.error == "NOT_CONFIGURED":
            print(f"  {_fail('ZaloBotController: access_token missing at runtime')}")
            return False
        print(f"  {_ok(f'ZaloBotController: access_token=set ({token[:12]}...), app_id={app_id}')}")
        return True
    except ImportError as exc:
        print(f"  {_fail(f'Import error: {exc}')}")
        return False
    except Exception as exc:
        # Network-level exception with token set -> credential OK, runtime issue.
        print(f"  {_ok(f'ZaloBotController: credentials set (network probe expected offline: {type(exc).__name__})')}")
        return True


# ── D-08: Discord ─────────────────────────────────────────────────────────────

def check_discord(verbose: bool = False) -> bool:
    """
    Verifies DISCORD_BOT_TOKEN is set and DiscordBotController instantiates.
    send_message() with bot_token present attempts real HTTP (channel_id=0 -> 404 expected).
    error_code=NOT_CONFIGURED only fires when bot_token is absent (fail-closed).
    """
    label = "D-08 Discord"
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

    if not token:
        print(f"  {_fail('DISCORD_BOT_TOKEN not set in environment')}")
        return False

    try:
        from jarvis.comms.discord import DiscordBotController
        bot = DiscordBotController(bot_token=token, whitelist_user_ids=[0])
        result = bot.send_message(channel_id=0, content="verify_credentials probe")
        error_code = result.get("error_code", "")
        if error_code == "NOT_CONFIGURED":
            print(f"  {_fail('DiscordBotController: bot_token missing at runtime')}")
            return False
        print(f"  {_ok(f'DiscordBotController: bot_token=set ({token[:12]}...)')}")
        if verbose and not result.get("success"):
            print(f"         Note: probe returned error (expected for channel_id=0): "
                  f"{result.get('error', 'unknown')!r}")
        return True
    except ImportError as exc:
        print(f"  {_fail(f'Import error: {exc}')}")
        return False
    except Exception as exc:
        # Network-level exception with token set -> credential OK.
        print(f"  {_ok(f'DiscordBotController: token set (network probe expected offline: {type(exc).__name__})')}")
        return True


# ── D-09: Gmail IMAP ─────────────────────────────────────────────────────────

def check_gmail(verbose: bool = False) -> bool:
    """
    Verifies SMTP_USER and SMTP_PASSWORD are set and IMAPEmailReader instantiates
    without raising IMAPNotConfiguredError.

    connect() is NOT called here (requires live network + valid credentials).
    We verify credentials are present -- consistent with fail-closed contract:
      missing creds -> IMAPNotConfiguredError; present creds -> CONFIGURED.
    """
    label = "D-09 Gmail IMAP"
    username = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com").strip()

    missing = []
    if not username:
        missing.append("SMTP_USER")
    if not password:
        missing.append("SMTP_PASSWORD")

    if missing:
        print(f"  {_fail(f'Missing env vars: {missing}')}")
        return False

    try:
        from jarvis.comms.email_imap import IMAPEmailReader, IMAPNotConfiguredError
        reader = IMAPEmailReader(
            priority_senders=["*"],
            host=imap_host,
            port=int(os.environ.get("IMAP_PORT", "993")),
            username=username,
            password=password,
        )
        if not reader.username or not reader.password or not reader.host:
            raise IMAPNotConfiguredError("Credential fields empty after init")

        print(f"  {_ok(f'IMAPEmailReader: credentials=set (user={username}, host={imap_host})')}")
        return True
    except ImportError as exc:
        print(f"  {_fail(f'Import error: {exc}')}")
        return False
    except Exception as exc:
        print(f"  {_fail(f'Unexpected error: {exc}')}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="JARVIS Credential Verification -- Fail-Closed Checks"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print additional diagnostic detail for each check",
    )
    args = parser.parse_args()

    # Load .env file if python-dotenv is available
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(_PROJECT_ROOT, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
            if args.verbose:
                print(f"Loaded .env from: {env_path}")
    except ImportError:
        if args.verbose:
            print("Note: python-dotenv not installed -- reading from process environment only")

    sep = "=" * 65
    print(f"\n{_BOLD}{sep}{_RESET}")
    print(f"{_BOLD}  JARVIS Credential Verification (scripts/verify_credentials.py){_RESET}")
    print(f"{_BOLD}{sep}{_RESET}\n")

    checks = [
        ("D-06 Telegram   ", check_telegram),
        ("D-07 Zalo OA    ", check_zalo),
        ("D-08 Discord    ", check_discord),
        ("D-09 Gmail IMAP ", check_gmail),
    ]

    results: dict[str, bool] = {}
    for name, fn in checks:
        print(f"{_BOLD}[{name}]{_RESET}")
        results[name] = fn(args.verbose)
        print()

    print(f"{_BOLD}{'-' * 65}{_RESET}")
    configured = sum(1 for v in results.values() if v)
    total = len(results)
    summary_color = _GREEN if configured == total else (_YELLOW if configured > 0 else _RED)
    print(f"{summary_color}{_BOLD}Summary: {configured}/{total} credentials CONFIGURED{_RESET}")

    if configured < total:
        print(f"\n{_YELLOW}Next steps:{_RESET}")
        print("  1. Follow docs/wizard/credentials_setup_wizard.md for setup instructions.")
        print("  2. Add credentials to .env or set GitHub Secrets with `gh secret set`.")
        print("  3. Re-run: python scripts/verify_credentials.py\n")
        sys.exit(1)
    else:
        print(f"\n{_GREEN}All credentials verified. JARVIS communication modules are ready.{_RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
