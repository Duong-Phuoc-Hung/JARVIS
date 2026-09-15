"""Own a real Chromium process for cross-process CDP end-to-end tests."""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    port = int(sys.argv[1])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
            ],
        )
        print("READY", flush=True)
        for raw_command in sys.stdin:
            command = raw_command.strip().lower()
            if command == "close":
                if browser.is_connected():
                    browser.close()
                print("CLOSED", flush=True)
            elif command == "stop":
                if browser.is_connected():
                    browser.close()
                return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
