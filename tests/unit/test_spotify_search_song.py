"""
tests/unit/test_spotify_search_song.py
======================================
Tests for Spotify track query search, phonetic normalizer for 'spotifile',
and YouTube video search intent routing.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from jarvis.llm.router import LLMIntentRouter
from jarvis.nlp.phonetic_normalizer import normalize_phonetic_stt
from jarvis.plugins.spotify import SpotifyPlugin


def test_youtube_video_search_routing():
    """Verify 'mở video Độ Mixi trên youtube' routes to web_open with exact search URL."""
    router = LLMIntentRouter(llm_client=None)
    cmd = "mở video Độ Mixi trên youtube"
    res = router.route(cmd)

    assert res.action_name == "web_open"
    assert res.parameters.get("site") == "youtube"
    assert "search_query=%C4%90%E1%BB%99+Mixi" in res.parameters.get("target", "")
    assert "Độ Mixi" in res.response_text


def test_spotifile_phonetic_normalization():
    """Verify 'spotifile' is normalized to canonical 'spotify'."""
    cmd = "mở nhạc bài nắng trên spotifile"
    norm = normalize_phonetic_stt(cmd)
    assert "spotify" in norm
    assert "spotifile" not in norm


def test_spotify_song_search_routing():
    """Verify 'mở nhạc bài nắng trên spotifile' extracts clean query and routes to spotify."""
    router = LLMIntentRouter(llm_client=None)
    raw_cmd = "mở nhạc bài nắng trên spotifile"
    norm_cmd = normalize_phonetic_stt(raw_cmd)
    res = router.route(norm_cmd)

    assert res.action_name == "spotify"
    assert res.parameters.get("query") == "bài nắng"
    assert "Spotify" in res.response_text


def test_spotify_plugin_launches_search_uri():
    """Verify SpotifyPlugin launches spotify:search: URI for track query."""
    plugin = SpotifyPlugin()
    plugin.initialize({}, MagicMock())

    with patch("os.startfile") as mock_start:
        res = plugin.play_track(query="bài nắng")
        assert res.get("status") == "started"
        assert res.get("success") is True
        assert res.get("uri") == "spotify:search:n%E1%BA%AFng"
        mock_start.assert_called_once_with("spotify:search:n%E1%BA%AFng")


def test_spotify_plugin_fallbacks_to_web_search_on_os_error():
    """Verify SpotifyPlugin fallbacks to web search when desktop app protocol fails."""
    plugin = SpotifyPlugin()
    plugin.initialize({}, MagicMock())

    with patch("os.startfile", side_effect=OSError("No app associated")):
        with patch("webbrowser.open") as mock_web:
            res = plugin.play_track(query="bài nắng")
            assert res.get("status") == "started"
            assert res.get("success") is True
            mock_web.assert_called_once_with("https://open.spotify.com/search/n%E1%BA%AFng")
