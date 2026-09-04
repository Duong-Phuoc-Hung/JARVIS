"""
jarvis/plugins/spotify.py
=========================
Spotify music launcher plugin for JARVIS.
"""
from __future__ import annotations

import os
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PluginMetadata
from jarvis.core.plugin import BasePlugin
from jarvis.core.runaway_guard import canonical_app_key, launch_dedupe_guard


class SpotifyPlugin(BasePlugin):
    """Launches Spotify URI via os.startfile on Windows or webbrowser."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="spotify",
            version="1.0.0",
            description="Spotify music launcher",
        )

    def initialize(self, config: dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.config = config or {}
        self.dispatcher = dispatcher
        self.default_song_uri = (
            self.config.get("song_uri")
            or os.environ.get("SONG_URI")
            or "https://open.spotify.com/track/39shmbIHICJ2Wxnk1fPSdz?si=2900c75c2e2d4b82"
        )

        self.register_action(
            name="spotify",
            handler=self.play_track,
            description="Launch Spotify track or playlist URI",
        )
        self.register_action(
            name="spotify_play",
            handler=self.play_track,
            description="Play Spotify track URI",
        )
        self.register_action(
            name="play_song",
            handler=self.play_track,
            description="Play default configured song",
        )

    def play_track(self, song_uri: str | None = None, **kwargs) -> dict[str, Any]:
        """Launches target Spotify track or URL."""
        target = (song_uri or self.default_song_uri).strip()
        if not target:
            return {"status": "skipped", "reason": "empty_uri"}

        # P0 runaway-hardening: every prior call unconditionally re-launched
        # Spotify with no rate limit -- a repeated/runaway dispatch (e.g. a
        # passive acoustic-trigger loop) could spawn it over and over. Report
        # a suppressed repeat truthfully rather than silently no-op'ing or
        # claiming a fresh success. Keyed by canonical APP identity (not the
        # exact song URI) so this shares one budget with
        # ComputerController.open_app("spotify") -- the same real
        # application reached through a different code path.
        if not launch_dedupe_guard.should_allow("app_launch", canonical_app_key("spotify")):
            return {
                "success": False,
                "status": "suppressed",
                "error": "Yêu cầu mở Spotify bị chặn do lặp lại quá nhanh.",
                "error_code": "LAUNCH_RATE_LIMITED",
                "uri": target,
            }

        try:
            if hasattr(os, "startfile"):
                os.startfile(target)
            else:
                import webbrowser
                webbrowser.open(target)
            return {"status": "started", "success": True, "uri": target}
        except Exception as e:
            return {"status": "error", "message": str(e)}
