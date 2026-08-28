"""
jarvis/skills/sound_board/__init__.py
======================================
Sound Board skill: trigger Stark UI sound effects via JARVIS commands.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger("jarvis.skills.sound_board")

_PLAYER = None


def _get_player():
    global _PLAYER
    if _PLAYER is None:
        from jarvis.audio.sound_effects import SoundEffectsPlayer, SoundConfig
        _PLAYER = SoundEffectsPlayer(config=SoundConfig(enabled=True, volume=0.4))
    return _PLAYER


_SOUND_MAP = {
    "activation": "play_activation",
    "activate":   "play_activation",
    "kích hoạt":  "play_activation",
    "completion": "play_completion",
    "complete":   "play_completion",
    "hoàn thành": "play_completion",
    "error":      "play_error",
    "lỗi":        "play_error",
    "thinking":   "play_thinking",
    "suy nghĩ":   "play_thinking",
    "alert":      "play_alert",
    "cảnh báo":   "play_alert",
    "chime":      "play_activation",
}


def execute(
    action: str = "chime",
    sound: str = "activation",
    volume: float = 0.4,
    frequency: float = 440.0,
    duration: float = 0.1,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Sound Board skill — play Stark UI audio feedback tones.

    Args:
        action: 'play' | 'chime' | 'alarm' | 'alert' | 'stop'
        sound:  'activation' | 'completion' | 'error' | 'thinking' | 'alert'
        volume: 0.0–1.0 volume level
        frequency: Hz for custom tone
        duration: seconds for custom tone
    """
    player = _get_player()
    player.config.volume = max(0.0, min(1.0, volume))
    act = action.lower().strip()

    if act in ("play", "chime"):
        method_name = _SOUND_MAP.get(sound.lower(), "play_activation")
        method = getattr(player, method_name, player.play_activation)
        method()
        msg = f"🔊 Phát âm thanh [{sound}]"

    elif act == "alarm":
        player.play_alert()
        msg = "🔔 Alarm! Cảnh báo đã phát."

    elif act == "alert":
        player.play_alert()
        msg = "⚠️ Alert tone đã phát."

    elif act == "stop":
        try:
            import sounddevice as sd  # type: ignore[import]
            sd.stop()
            msg = "⏹️ Đã dừng âm thanh."
        except ImportError:
            msg = "sounddevice chưa cài đặt — không có âm thanh nào đang phát."

    elif act == "custom":
        player.play_tone(frequency_hz=frequency, duration_s=duration)
        msg = f"🎵 Đã phát tone tùy chỉnh: {frequency:.0f}Hz, {duration:.2f}s"

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: play, chime, alarm, alert, stop, custom."
        return {"data": {"text": msg, "success": False}, "output": msg}

    return {"data": {"text": msg, "sound": sound, "action": act, "success": True}, "output": msg}
