"""
jarvis/plugins/chrome.py
========================
Google Chrome multi-monitor placement and snapping plugin for JARVIS.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PluginMetadata
from jarvis.core.plugin import BasePlugin


class ChromeMultiMonitorPlugin(BasePlugin):
    """Spawns Chrome windows positioned on specific desktop monitors."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="chrome",
            version="1.0.0",
            description="Chrome multi-monitor window placement and snapping",
        )

    def initialize(self, config: dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.config = config or {}
        self.dispatcher = dispatcher

        self.claude_url = (
            self.config.get("claude_url")
            or os.environ.get("CLAUDE_CODE_URL")
            or "https://claude.ai/new"
        )
        self.binance_url = (
            self.config.get("binance_url")
            or os.environ.get("BINANCE_BTC_URL")
            or "https://www.binance.com/en/trade/BTC_USDT"
        )
        self.claude_monitor = int(
            self.config.get("claude_monitor")
            or os.environ.get("CLAUDE_CHROME_MONITOR")
            or 1
        )
        self.binance_monitor = int(
            self.config.get("binance_monitor")
            or os.environ.get("BINANCE_CHROME_MONITOR")
            or 3
        )
        self.fullscreen = bool(self.config.get("fullscreen", True))

        self.register_action(
            name="chrome_claude",
            handler=self.open_claude,
            description="Open Claude in Chrome on Monitor 1",
        )
        self.register_action(
            name="chrome_binance",
            handler=self.open_binance,
            description="Open Binance in Chrome on Monitor 3",
        )
        self.register_action(
            name="chrome_open",
            handler=self.open_url,
            description="Open Chrome URL on specific monitor",
        )
        self.register_action(
            name="open_url",
            handler=self.open_url,
            description="Open generic URL in browser",
        )

    def _get_chrome_exe(self) -> str | None:
        """Resolves Chrome executable path across Windows installations."""
        if sys.platform == "win32":
            candidates = [
                os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            for p in candidates:
                if p and os.path.isfile(p):
                    return p
        return shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chrome.exe")

    def open_claude(self, **kwargs) -> dict[str, Any]:
        return self.open_url(self.claude_url, monitor=self.claude_monitor, fullscreen=self.fullscreen)

    def open_binance(self, **kwargs) -> dict[str, Any]:
        return self.open_url(self.binance_url, monitor=self.binance_monitor, fullscreen=self.fullscreen)

    def open_url(
        self,
        url: str,
        monitor: int = 1,
        fullscreen: bool = False,
        window_width: int = 1400,
        window_height: int = 900,
        **kwargs,
    ) -> dict[str, Any]:
        x_offset = (int(monitor) - 1) * 1920
        y_offset = 0

        chrome_exe = self._get_chrome_exe() or "chrome.exe"
        args = [chrome_exe, "--new-window", f"--window-position={x_offset},{y_offset}", url]
        if fullscreen:
            args.append("--start-fullscreen")

        try:
            kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(args, **kw)
            return {"success": True, "url": url, "monitor": monitor, "args": args}
        except (FileNotFoundError, OSError):
            import webbrowser
            webbrowser.open(url)
            return {"success": True, "fallback": "browser", "url": url}


# Backward compatibility alias
ChromePlugin = ChromeMultiMonitorPlugin
