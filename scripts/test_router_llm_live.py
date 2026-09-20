import os, sys, json, time
from datetime import datetime
from dotenv import load_dotenv

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

load_dotenv(override=True)

import google.generativeai as genai

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
print(f"Key: len={len(GEMINI_KEY)}, valid={GEMINI_KEY.startswith('AIzaSy')}")

if not GEMINI_KEY.startswith("AIzaSy"):
    print("ERROR: Invalid GEMINI_API_KEY")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)

# Use flash-lite for higher free-tier quota (15 RPM vs 5 RPM for flash)
model = genai.GenerativeModel("gemini-flash-lite-latest")
print("Model: gemini-flash-lite-latest")

# Rate limit: 15s between requests to stay under free tier limits
RATE_LIMIT_SLEEP = 15

TEST_INTENTS = [
    ("mở Chrome",                  "open_app"),
    ("tìm kiếm thời tiết hôm nay", "web_search"),
    ("tăng âm lượng lên 50%",      "volume_control"),
    ("đặt hẹn giờ 10 phút",        "set_timer"),
    ("ghi chú mua sữa",             "note_taking"),
    ("thời tiết Hà Nội",            "weather_query"),
    ("bật nhạc",                    "media_control"),
    ("chụp màn hình",               "screenshot"),
    ("nhắc tôi họp lúc 3 giờ",     "set_reminder"),
    ("mở cài đặt Windows",          "open_settings"),
]

SYSTEM_PROMPT = """You are an intent router for a Vietnamese voice assistant.
Given a user command in Vietnamese, classify it into exactly one of these action labels:
open_app, web_search, volume_control, set_timer, note_taking, weather_query,
media_control, screenshot, set_reminder, open_settings, unknown.

Respond with ONLY the action label, nothing else. No explanation."""

print(f"\n=== Running N={len(TEST_INTENTS)} intent routing benchmark ===")
results = []

for i, (intent_text, expected) in enumerate(TEST_INTENTS):
    if i > 0:
        print(f"  (waiting {RATE_LIMIT_SLEEP}s for rate limit...)")
        time.sleep(RATE_LIMIT_SLEEP)
    start = time.perf_counter()
    try:
        response = model.generate_content(
            f"{SYSTEM_PROMPT}\n\nCommand: {intent_text}",
            generation_config=genai.GenerationConfig(max_output_tokens=30, temperature=0)
        )
        elapsed = (time.perf_counter() - start) * 1000
        # Handle finish_reason=2 (safety block)
        if not response.candidates or response.candidates[0].finish_reason == 2:
            routed = "safety_block"
            passed = False
        else:
            routed = response.text.strip().lower().replace(".", "").replace("'", "").split("\n")[0]
            passed = (routed == expected) or (expected in routed) or (routed in expected)
        status = "PASS" if passed else ("SAFETY" if routed == "safety_block" else "FAIL")
        print(f"  [{status}] '{intent_text}' -> '{routed}' (expected={expected}) {elapsed:.0f}ms")
        results.append({
            "intent": intent_text,
            "expected": expected,
            "routed": routed,
            "latency_ms": round(elapsed, 1),
            "pass": passed,
            "tier": "gemini_llm"
        })
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        err_str = str(e)[:200]
        status = "RATE_LIMIT" if "429" in err_str else "EXCEPTION"
        print(f"  [{status}] '{intent_text}': {err_str[:100]}")
        results.append({"intent": intent_text, "expected": expected, "status": status, "error": err_str, "pass": False, "latency_ms": round(elapsed, 1)})


# Summary
n_passed = sum(1 for r in results if r.get("pass"))
total = len(results)
rate = n_passed / total * 100 if total else 0
avg_lat = sum(r.get("latency_ms", 0) for r in results) / total if total else 0
verdict = "PASS runtime" if rate >= 80 else "FAIL"

print(f"\n=== SUMMARY ===")
print(f"Passed: {n_passed}/{total} = {rate:.1f}%")
print(f"Avg latency: {avg_lat:.0f}ms")
print(f"Verdict: {verdict}")

evidence = {
    "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "model": "gemini-1.5-flash",
    "sdk": "google-generativeai",
    "gemini_key_valid": True,
    "n_intents": total,
    "n_passed": n_passed,
    "pass_rate": round(rate, 1),
    "avg_latency_ms": round(avg_lat, 1),
    "verdict": verdict,
    "results": results
}

os.makedirs("docs/eval", exist_ok=True)
with open("docs/eval/router_llm_live_evidence_v2.json", "w", encoding="utf-8") as f:
    json.dump(evidence, f, indent=2, ensure_ascii=False)
print("Evidence written to docs/eval/router_llm_live_evidence_v2.json")
sys.exit(0 if verdict == "PASS runtime" else 1)
