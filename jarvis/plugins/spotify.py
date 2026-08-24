"""
jarvis/plugins/spotify.py
=========================
Spotify music launcher plugin for JARVIS.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PluginMetadata
from jarvis.core.plugin import BasePlugin


class SpotifyPlugin(BasePlugin):
    """Launches Spotify URI via os.startfile on Windows or webbrowser."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="spotify",
            version="1.0.0",
            description="Spotify music launcher",
        )

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
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

    def play_track(self, song_uri: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Launches target Spotify track or URL."""
        target = (song_uri or self.default_song_uri).strip()
        if not target:
            return {"status": "skipped", "reason": "empty_uri"}

        try:
            if hasattr(os, "startfile"):
                os.startfile(target)
            else:
                import webbrowser
                webbrowser.open(target)
            return {"status": "started", "success": True, "uri": target}
        except Exception as e:
            return {"status": "error", "message": str(e)}
