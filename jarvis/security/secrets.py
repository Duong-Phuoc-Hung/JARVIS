"""
jarvis/security/secrets.py
==========================
Secrets manager: reads API keys from Windows Credential Manager (keyring),
then falls back to environment variables. API keys are NEVER stored plaintext
in config files.

Usage:
  from jarvis.security.secrets import get_secret, set_secret

  # Store once (e.g. during setup):
  set_secret("GEMINI_API_KEY", "AIza...")

  # Read anywhere in the app:
  key = get_secret("GEMINI_API_KEY")

Migration from .env / plaintext config:
  1. Run: python -m jarvis.security.secrets --migrate
  2. It reads current env vars and saves them to Credential Manager
  3. Delete plaintext values from .env / config after confirming migration
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("jarvis.security.secrets")

# Service name used as namespace in Windows Credential Manager
_SERVICE = "JARVIS"

# Known secrets managed by this module
KNOWN_SECRETS = (
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "ZALO_API_KEY",
    "EMAIL_PASSWORD",
    "WEATHER_API_KEY",
)


def _keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


def get_secret(name: str, fallback_env: bool = True) -> str | None:
    """
    Read a secret by name.

    Priority order:
      1. Windows Credential Manager (via keyring) — preferred
      2. Environment variable (fallback, for CI/Docker compatibility)
      3. None if not found anywhere

    Args:
        name: Secret name (e.g. "GEMINI_API_KEY")
        fallback_env: If True, check os.environ when keyring has no value.
    """
    # 1. Try keyring / Windows Credential Manager
    if _keyring_available():
        try:
            import keyring
            value = keyring.get_password(_SERVICE, name)
            if value:
                log.debug("secrets: loaded %s from Credential Manager", name)
                return value
        except Exception as exc:
            log.warning("secrets: keyring error for %s: %s", name, exc)

    # 2. Fallback to environment variable
    if fallback_env:
        value = os.environ.get(name)
        if value:
            log.debug("secrets: loaded %s from environment variable", name)
            return value

    log.warning("secrets: %s not found in Credential Manager or environment", name)
    return None


def set_secret(name: str, value: str) -> bool:
    """
    Store a secret in Windows Credential Manager.

    Returns True on success, False on failure.
    """
    if not _keyring_available():
        log.error("secrets: keyring not installed — pip install keyring")
        return False
    try:
        import keyring
        keyring.set_password(_SERVICE, name, value)
        log.info("secrets: saved %s to Credential Manager", name)
        return True
    except Exception as exc:
        log.error("secrets: failed to save %s: %s", name, exc)
        return False


def delete_secret(name: str) -> bool:
    """Remove a secret from Windows Credential Manager."""
    if not _keyring_available():
        return False
    try:
        import keyring
        keyring.delete_password(_SERVICE, name)
        return True
    except Exception:
        return False


def migrate_from_env(dry_run: bool = False) -> dict[str, str]:
    """
    One-time migration: read known secrets from env vars, save to Credential Manager.

    Returns dict of {name: "migrated" | "skipped" | "not_found"}.
    Safe to run multiple times (idempotent).
    """
    results = {}
    for name in KNOWN_SECRETS:
        value = os.environ.get(name)
        if not value:
            results[name] = "not_found"
            continue
        if dry_run:
            results[name] = f"would_migrate (len={len(value)})"
            continue
        ok = set_secret(name, value)
        results[name] = "migrated" if ok else "failed"
    return results


def _parse_dotenv_lines(content: str) -> list[tuple[str, str, str]]:
    """
    Parses dotenv content into list of (raw_line, key, value).
    Preserves comments and empty lines as (raw_line, "", "").
    """
    items = []
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in line:
            items.append((line, "", ""))
            continue
        k, v = line.split("=", 1)
        k_clean = k.strip()
        v_clean = v.strip().strip("'\"")
        items.append((line, k_clean, v_clean))
    return items


def migrate_from_dotenv(
    dotenv_path: str | Path = ".env",
    dry_run: bool = False,
    purge_secrets: bool = False,
) -> dict[str, str]:
    """
    Reads secrets from a .env file and migrates them to Windows Credential Manager.

    Args:
        dotenv_path: Path to the .env file.
        dry_run: If True, do not write to keyring or modify the file.
        purge_secrets: If True and migration succeeds, purge plaintext secrets from .env.

    Returns:
        dict[str, str] mapping secret names to status.
    """
    path = Path(dotenv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dotenv file not found: {path}")

    content = path.read_text(encoding="utf-8")
    parsed_lines = _parse_dotenv_lines(content)

    results: dict[str, str] = {}
    migrated_keys: set[str] = set()

    for _, key, val in parsed_lines:
        if not key or key not in KNOWN_SECRETS or not val:
            continue

        if dry_run:
            results[key] = f"would_migrate (len={len(val)})"
            continue

        ok = set_secret(key, val)
        if ok:
            results[key] = "migrated"
            migrated_keys.add(key)
        else:
            results[key] = "failed"

    if purge_secrets and not dry_run and migrated_keys:
        new_lines = []
        for raw_line, key, _ in parsed_lines:
            if key in migrated_keys:
                new_lines.append(f"# {key}=<migrated to Windows Credential Manager>")
            else:
                new_lines.append(raw_line)
        trailing_newline = "\n" if content.endswith("\n") else ""
        path.write_text("\n".join(new_lines) + trailing_newline, encoding="utf-8")

    return results


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(description="JARVIS Secrets Manager")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("migrate", help="Migrate secrets from env vars to Credential Manager")
    sub.add_parser("migrate-dry", help="Dry-run: show what would be migrated")

    mig_dotenv = sub.add_parser("migrate-dotenv", help="Migrate secrets from a .env file to Credential Manager")
    mig_dotenv.add_argument("--path", default=".env", help="Path to .env file (default: .env)")
    mig_dotenv.add_argument("--dry-run", action="store_true", help="Preview migration without storing")
    mig_dotenv.add_argument("--purge", action="store_true", help="Comment out plaintext secrets in .env upon success")

    set_p = sub.add_parser("set", help="Store a secret")
    set_p.add_argument("name"); set_p.add_argument("value")

    get_p = sub.add_parser("get", help="Read a secret")
    get_p.add_argument("name")

    del_p = sub.add_parser("delete", help="Delete a secret")
    del_p.add_argument("name")

    args = ap.parse_args()

    if args.cmd == "migrate":
        results = migrate_from_env(dry_run=False)
        for k, v in results.items(): print(f"  {k}: {v}")
    elif args.cmd == "migrate-dry":
        results = migrate_from_env(dry_run=True)
        for k, v in results.items(): print(f"  {k}: {v}")
    elif args.cmd == "migrate-dotenv":
        results = migrate_from_dotenv(dotenv_path=args.path, dry_run=args.dry_run, purge_secrets=args.purge)
        for k, v in results.items(): print(f"  {k}: {v}")
    elif args.cmd == "set":
        ok = set_secret(args.name, args.value)
        sys.exit(0 if ok else 1)
    elif args.cmd == "get":
        v = get_secret(args.name)
        print(v or "(not found)")
    elif args.cmd == "delete":
        ok = delete_secret(args.name)
        print("deleted" if ok else "failed")
    else:
        ap.print_help()
