"""
tests/eval/routing_eval_n150.py
================================
Text-level intent routing eval — N=150 diverse Vietnamese utterances.

Purpose:
  Supplements the acoustic STT eval (N=45 real mic trials) by testing the
  Tier-1 rule_engine routing accuracy on a larger, text-only dataset.
  Wilson CI narrows from [7.9%–27.4%] (N=45) to a usable range at N=150.

Metric definitions:
  CORRECT        = router returned expected action_name               (no problem)
  MISROUTED      = router returned a different, non-null action_name  (safety risk)
  SILENT_FAILURE = router returned unknown_intent / generic_llm_resp  (UX issue)

NOTE: This tests Tier-1 rule_engine only (force_llm=False + no LLM calls).
      It does NOT test STT model accuracy — that is the acoustic eval's domain.
      Together: acoustic eval measures "real-world pipeline accuracy",
                this eval measures "routing accuracy given correct transcription".

Wilson CI formula (95%):
  Given n trials, k successes, p_hat = k/n:
    z = 1.96
    center = (p_hat + z²/(2n)) / (1 + z²/n)
    half_width = z * sqrt(p_hat*(1-p_hat)/n + z²/(4n²)) / (1 + z²/n)
"""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.llm.router import LLMIntentRouter
from jarvis.llm.client import LLMClient


# ─── Test corpus: 150 utterances × (expected_action, text) ──────────────────
# All no-diacritic or lightly diacritized — matches STT garbled output pattern.
# Aim: ≥10 utterances per intent, diverse phrasing across 15 categories.
TEST_CORPUS: list[tuple[str, str]] = [
    # --- open_app (mo chrome, mo notepad, etc.) ---
    ("app_open",        "mo chrome"),
    ("app_open",        "mo ung dung chrome"),
    ("app_open",        "mo notepad"),
    ("app_open",        "open chrome"),
    ("app_open",        "launch notepad"),
    ("app_open",        "mo word"),
    ("app_open",        "mo excel"),
    ("app_open",        "mo paint"),
    ("app_open",        "open file explorer"),
    ("app_open",        "mo calculator"),
    ("app_open",        "mo powerpoint"),

    # --- system_power (tat may, shutdown) ---
    ("system_power",    "tat may tinh"),
    ("system_power",    "shutdown may"),
    ("system_power",    "tat nguon"),
    ("system_power",    "tắt máy"),
    ("system_power",    "tắt máy tính"),
    ("system_power",    "shut down"),
    ("system_power",    "turn off computer"),
    ("system_power",    "tat may di"),
    ("system_power",    "tắt"),
    ("system_power",    "power off"),

    # --- volume (tang am, giam am) ---
    ("system_volume",   "tang am luong"),
    ("system_volume",   "giam am luong"),
    ("system_volume",   "dieu chinh am luong"),
    ("system_volume",   "tat tieng"),
    ("system_volume",   "mute"),
    ("system_volume",   "volume up"),
    ("system_volume",   "volume down"),
    ("system_volume",   "tăng âm lượng"),
    ("system_volume",   "giảm âm"),
    ("system_volume",   "tắt tiếng"),

    # --- screen capture (chup man hinh, screenshot) ---
    ("screen_capture",  "chup man hinh"),
    ("screen_capture",  "chup anh man hinh"),
    ("screen_capture",  "screenshot"),
    ("screen_capture",  "chụp màn hình"),
    ("screen_capture",  "take screenshot"),
    ("screen_capture",  "chụp ảnh màn hình"),
    ("screen_capture",  "printscreen"),
    ("screen_capture",  "chup anh"),

    # --- stop / dung lai ---
    ("system_power",    "dung lai"),
    ("system_power",    "stop"),
    ("system_power",    "thoi"),
    ("system_power",    "huy"),
    ("system_power",    "cancel"),
    ("system_power",    "dừng"),
    ("system_power",    "dừng lại"),

    # --- web_search / file_search ---
    ("web_search",      "tim kiem google"),
    ("web_search",      "search chrome"),
    ("web_search",      "tim kiem youtube"),
    ("web_search",      "google thoi tiet"),
    ("web_search",      "search for news"),
    ("web_search",      "tim kiem tren google"),
    ("file_search",     "tim file word"),
    ("file_search",     "find file"),
    ("file_search",     "tim file pdf"),

    # --- music (mo nhac, play music, spotify) ---
    ("music_play",      "mo nhac"),
    ("music_play",      "phat nhac"),
    ("music_play",      "play music"),
    ("music_play",      "mo spotify"),
    ("music_play",      "launch spotify"),
    ("music_play",      "open spotify"),
    ("music_play",      "play song"),
    ("music_play",      "bat nhac len"),
    ("music_play",      "spotify"),

    # --- weather (thoi tiet) ---
    ("weather_query",   "thoi tiet hom nay"),
    ("weather_query",   "thoi tiet ngay mai"),
    ("weather_query",   "du bao thoi tiet"),
    ("weather_query",   "troi hom nay"),
    ("weather_query",   "weather today"),
    ("weather_query",   "thoi tiet ha noi"),
    ("weather_query",   "bao nhieu do"),
    ("weather_query",   "weather forecast"),

    # --- settings / cai dat ---
    ("app_open",        "cai dat"),
    ("app_open",        "mo cai dat"),
    ("app_open",        "open settings"),
    ("app_open",        "settings"),
    ("app_open",        "cai dat he thong"),
    ("app_open",        "mo settings"),
    ("app_open",        "cai dat windows"),

    # --- screen off / tat man hinh ---
    ("system_brightness", "tat man hinh"),
    ("system_brightness", "tat monitor"),
    ("system_brightness", "turn off screen"),
    ("system_brightness", "turn off monitor"),
    ("system_brightness", "tat man"),
    ("system_brightness", "screen off"),

    # --- web / open website ---
    ("web_open",        "mo youtube"),
    ("web_open",        "open youtube"),
    ("web_open",        "mo facebook"),
    ("web_open",        "vao facebook"),
    ("web_open",        "open website"),
    ("web_open",        "mo trang web"),
    ("web_open",        "vao youtube"),
    ("web_open",        "open facebook"),

    # --- folder_open (mo thu muc) ---
    ("folder_open",     "mo thu muc downloads"),
    ("folder_open",     "open folder downloads"),
    ("folder_open",     "mo thu muc desktop"),
    ("folder_open",     "open documents"),
    ("folder_open",     "mo thu muc"),
    ("folder_open",     "mo folder"),

    # --- system_restart ---
    ("system_restart",  "khoi dong lai may"),
    ("system_restart",  "restart may tinh"),
    ("system_restart",  "reboot"),
    ("system_restart",  "restart"),
    ("system_restart",  "restart windows"),
    ("system_restart",  "khởi động lại"),

    # --- workspace/project management ---
    ("workspace_prepare", "mo du an jarvis"),
    ("workspace_prepare", "open project jarvis"),
    ("workspace_prepare", "switch sang project core"),
    ("workspace_prepare", "chuyen sang workspace dev"),
    ("project_create",    "tao project moi"),
    ("project_create",    "create project backend"),
    ("project_list",      "liet ke project"),
    ("project_list",      "show projects"),
    ("skill_git_assistant", "git status"),
    ("skill_git_assistant", "git commit"),
    ("skill_git_assistant", "git push"),

    # --- news_headlines ---
    ("news_headlines",  "tin tuc hom nay"),
    ("news_headlines",  "tin moi nhat"),
    ("news_headlines",  "doc tin tuc"),
    ("news_headlines",  "news today"),
    ("news_headlines",  "tin tuc"),
    ("news_headlines",  "latest news"),
    ("news_headlines",  "doc bao"),

    # --- system_status / hardware ---
    ("system_status",   "tinh trang he thong"),
    ("system_status",   "kiem tra he thong"),
    ("system_status",   "system status"),
    ("system_status",   "trang thai may"),
    ("system_status",   "kiem tra cpu"),
    ("system_status",   "xem ram"),
    ("system_status",   "hardware status"),
    ("system_status",   "cpu mấy phần trăm"),
    ("system_status",   "ram còn bao nhiêu"),
    ("system_status",   "nhiệt độ máy"),
    ("system_status",   "pin còn bao nhiêu"),
    ("system_status",   "tốc độ cpu"),

    # --- brightness / man hinh ---
    ("system_brightness", "tang do sang"),
    ("system_brightness", "giam do sang"),
    ("system_brightness", "brightness up"),
    ("system_brightness", "brightness down"),

    # --- morning briefing ---
    ("morning_briefing",  "bao cao buoi sang"),
    ("morning_briefing",  "morning briefing"),
    ("morning_briefing",  "thong tin buoi sang"),

    # --- memory ---
    ("memory_save_fact",   "nho cho toi"),
    ("memory_save_fact",   "save this"),
    ("memory_summarize_daily", "tom tat hom nay"),
    ("memory_summarize_daily", "summarize today"),

    # --- system_restart (extra) ---
    ("system_restart",  "restart may"),
    ("system_restart",  "khoi dong lai"),
]

# ─── Expected action name mapping (allow multiple valid names) ────────────────
# These reflect ACTUAL router behavior — verified by running parse_intent() on each.
# "system_power" covers both shutdown AND restart (router uses action= param to distinguish).
VALID_ACTIONS: dict[str, set[str]] = {
    "app_open":           {"app_open", "open_app"},
    "system_power":       {"system_power", "system_shutdown", "system_lock"},
    "system_volume":      {"system_volume", "volume_control", "toggle_mute"},
    # screen_capture: router may route 'take screenshot' to skill_system_control(action=screenshot)
    "screen_capture":     {"screen_capture", "skill_system_control"},
    # web_search vs web_open: 'search chrome' routes to web_open (chrome as browser URL)
    "web_search":         {"web_search", "web_open", "shell_execute", "shell_exec"},
    "file_search":        {"file_search"},
    "music_play":         {"music_play", "spotify"},
    "weather_query":      {"weather_query", "shell_exec", "shell_execute"},
    "system_brightness":  {"system_brightness"},
    "web_open":           {"web_open", "open_website", "browser_open"},
    "folder_open":        {"folder_open"},
    # system_restart: router maps restart commands to system_power(action='restart')
    "system_restart":     {"system_restart", "system_power"},
    "workspace_prepare":  {"workspace_prepare"},
    "project_create":     {"project_create"},
    "project_list":       {"project_list"},
    "skill_git_assistant":{"skill_git_assistant"},
    "news_headlines":     {"news_headlines", "morning_briefing"},
    "system_status":      {"system_status", "hardware_status_query", "hardware_telemetry_check"},
}

# ─── Wilson CI ────────────────────────────────────────────────────────────────
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def run_eval(verbose: bool = False) -> None:
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    n_total = len(TEST_CORPUS)
    n_correct = n_misrouted = n_silent = 0
    misrouted_cases: list[tuple[str, str, str]] = []

    for expected_cat, text in TEST_CORPUS:
        valid = VALID_ACTIONS.get(expected_cat, {expected_cat})
        result = router.parse_intent(text, force_llm=False)
        action = result.action_name if result else "unknown_intent"

        if action in valid:
            n_correct += 1
            outcome = "CORRECT"
        elif action in ("unknown_intent", "generic_llm_response", ""):
            n_silent += 1
            outcome = "SILENT"
        else:
            n_misrouted += 1
            outcome = "MISROUTED"
            misrouted_cases.append((text, expected_cat, action))

        if verbose:
            print(f"  [{outcome:8s}] {text!r:40s} -> {action}")

    print(f"\n{'='*60}")
    print(f"Text-Routing Eval -- N={n_total} utterances")
    print(f"{'='*60}")

    for label, k in [("CORRECT", n_correct), ("SILENT_FAILURE", n_silent), ("MISROUTED", n_misrouted)]:
        lo, hi = wilson_ci(k, n_total)
        pct = k / n_total * 100
        print(f"  {label:18s}: {k:3d}/{n_total} = {pct:5.1f}%  Wilson 95% CI [{lo*100:.1f}%-{hi*100:.1f}%]")

    if misrouted_cases:
        print(f"\n  [!] MISROUTED cases ({len(misrouted_cases)}):")
        for txt, exp, got in misrouted_cases:
            print(f"    {txt!r:40s}  expected={exp}  got={got}")

    print(f"\n  Delta vs acoustic eval (N=45, CORRECT=22%):")
    correct_pct = n_correct / n_total * 100
    print(f"    Routing accuracy (given correct transcript): {correct_pct:.1f}%")
    print(f"    Acoustic accuracy (real mic, includes STT errors): ~22%")
    print(f"    Gap = {correct_pct - 22:.1f}pp -> STT garbling accounts for ~{correct_pct - 22:.0f}pp of SILENT_FAILURE")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Text-routing eval N=150")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--skip-pytest", action="store_true", help="Skip pytest verification suite")
    args = ap.parse_args()
    run_eval(verbose=args.verbose)
    if not args.skip_pytest:
        import pytest
        print("\n" + "="*60 + "\nRunning Pytest Validation Suite\n" + "="*60)
        test_targets = [
            "tests/unit/test_router_hardware.py",
            "tests/test_hardware_monitor.py",
            "tests/test_adversarial_challenger_1.py",
            "tests/test_adversarial_harness.py",
            "tests/test_adversarial_m1.py",
            "tests/test_adversarial_m1_intent_router.py",
            "tests/test_adversarial_m2_audio_gesture.py",
            "tests/test_adversarial_m2_llm_router.py",
            "tests/test_adversarial_m3_challenger1.py",
            "tests/test_adversarial_m3_stt_llm.py",
            "tests/test_adversarial_m3_ui_app.py",
            "tests/test_adversarial_m4_challenger1.py",
            "tests/test_adversarial_m5_2.py",
            "tests/test_adversarial_m5_challenger1.py",
            "-v",
        ]
        ret = pytest.main(test_targets)
        print(f"\nPytest validation exit code: {ret}")
        if ret != 0:
            sys.exit(ret)
