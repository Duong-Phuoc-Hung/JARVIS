"""
Action plugins package for JARVIS.
Provides built-in plugins for Spotify playback, Chrome multi-monitor window placement,
Cursor IDE focus and control, Shell execution, and Webhook dispatching.
"""
from jarvis.plugins.chrome import ChromeMultiMonitorPlugin, ChromePlugin
from jarvis.plugins.cursor import CursorPlugin
from jarvis.plugins.shell import ShellPlugin
from jarvis.plugins.spotify import SpotifyPlugin
from jarvis.plugins.webhook import WebhookPlugin

__all__ = [
    "SpotifyPlugin",
    "ChromeMultiMonitorPlugin",
    "ChromePlugin",
    "CursorPlugin",
    "ShellPlugin",
    "WebhookPlugin",
]
