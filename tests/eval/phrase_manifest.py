"""
tests/eval/phrase_manifest.py
==============================
Single source of truth for the STT eval recorded-phrase manifest.

Background (audit 2026-09-02): tests/eval/stt_intent_eval.py previously carried
its own copy of the phrase list using ASCII/unaccented strings (e.g. "mo chrome"),
while tests/eval/record_test_set.py — the script that actually drove the
microphone recording sessions committed under tests/eval/audio/ — used the real
accented Vietnamese prompts (e.g. "mo chrome" vs "mở chrome"). The two copies had
also drifted in content, not just accenting: record_test_set.py's fifth open_app
variant is "khởi động chrome", while stt_intent_eval.py's copy claimed variant 4
was "launch spotify" — a phrase that was never actually recorded for that slot.

The WAV files under tests/eval/audio/ were recorded using record_test_set.py's
prompts. Any manifest used to describe "what was said" for a given WAV file must
therefore preserve record_test_set.py's phrase list verbatim — not
stt_intent_eval.py's stale, drifted copy.

This module is the single source both scripts import from, so recorder and
evaluator can no longer drift apart. Do not duplicate PHRASE_MANIFEST anywhere
else — extend or correct it here only.
"""
from __future__ import annotations

from pathlib import Path

# Real recording prompts (verbatim from tests/eval/record_test_set.py at the time
# the committed tests/eval/audio/ WAV files were recorded). Order matters: index N
# corresponds to variant_N.wav within that intent's directory.
PHRASE_MANIFEST: dict[str, list[str]] = {
    "open_app":        ["mở chrome", "mở ứng dụng chrome", "mở notepad", "mở spotify", "khởi động chrome"],
    "system_shutdown": ["tắt máy tính", "shutdown máy", "tắt nguồn"],
    "system_restart":  ["khởi động lại máy", "restart máy tính", "reboot"],
    "volume_control":  ["tăng âm lượng", "giảm âm lượng", "điều chỉnh âm lượng", "tắt tiếng", "mute"],
    "weather_query":   ["thời tiết hôm nay", "thời tiết ngày mai", "dự báo thời tiết", "trời hôm nay thế nào"],
    "timer_set":       ["hẹn giờ 5 phút", "đặt timer 10 phút", "nhắc tôi sau 15 phút"],
    "reminder_set":    ["nhắc nhở lúc 3 giờ", "đặt nhắc lúc 8 giờ sáng"],
    "screenshot":      ["chụp màn hình", "chụp ảnh màn hình", "screenshot"],
    "stop":            ["dừng lại", "stop", "thôi", "hủy"],
    "search":          ["tìm kiếm google", "tìm file word", "search chrome", "tìm kiếm youtube"],
    "music_play":      ["mở nhạc", "phát nhạc", "play music"],
    "screen_off":      ["tắt màn hình", "turn off monitor"],
    "note_take":       ["ghi chú", "tạo ghi chú mới"],
    "settings_open":   ["mở cài đặt", "open settings"],
}


def resolve_phrase(intent: str, variant_index: int) -> str | None:
    """Return the exact recording prompt for (intent, variant_index), or None if unknown."""
    phrases = PHRASE_MANIFEST.get(intent)
    if not phrases or variant_index < 0 or variant_index >= len(phrases):
        return None
    return phrases[variant_index]


def _parse_variant_index(stem: str) -> int | None:
    """'variant_3' -> 3. Anything else -> None."""
    if not stem.startswith("variant_"):
        return None
    suffix = stem[len("variant_"):]
    if not suffix.isdigit():
        return None
    return int(suffix)


def resolve_phrase_for_wav(wav_path: Path) -> str | None:
    """
    Map a committed WAV path (.../<condition>/<intent>/variant_N.wav) to the
    exact recording prompt spoken for it. Returns None if the path does not
    resolve to a known manifest entry (unknown intent, unknown variant index,
    or a filename that doesn't match the 'variant_N.wav' convention).
    """
    idx = _parse_variant_index(wav_path.stem)
    if idx is None:
        return None
    intent = wav_path.parent.name
    return resolve_phrase(intent, idx)


def validate_audio_root(audio_root: Path, conditions: tuple[str, ...] = ("clean", "noisy")) -> list[str]:
    """
    Validate that every committed *.wav file under audio_root/{condition}/{intent}/
    resolves to a manifest phrase. Returns a list of problem descriptions —
    empty list means every WAV file resolved cleanly.
    """
    problems: list[str] = []
    for condition in conditions:
        cond_dir = audio_root / condition
        if not cond_dir.exists():
            continue
        for intent_dir in sorted(cond_dir.iterdir()):
            if not intent_dir.is_dir():
                continue
            for wav_path in sorted(intent_dir.glob("*.wav")):
                if resolve_phrase_for_wav(wav_path) is None:
                    problems.append(
                        f"{wav_path.relative_to(audio_root)}: does not resolve to a "
                        f"manifest phrase (intent={intent_dir.name!r})"
                    )
    return problems
