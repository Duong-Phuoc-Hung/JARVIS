"""Live roundtrip tests for D-06 (Telegram) and D-08 (Discord) — 2026-09-20
Uses python-dotenv to handle .env encoding properly.
"""
import os, sys, json, requests
from datetime import datetime

# Use python-dotenv to read .env
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    # Manual fallback with encoding errors ignored
    with open(".env", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
results = {}

# ─── D-06 Telegram ───────────────────────────────────────────────────
print("\n=== D-06 Telegram Live Roundtrip ===")
tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
tg_chat  = os.getenv("TELEGRAM_CHAT_ID", "")
print(f"Token: {'SET len=' + str(len(tg_token)) if tg_token else 'NOT SET'}")
print(f"ChatID: {'SET' if tg_chat else 'NOT SET'}")

try:
    if not tg_token:
        results["telegram"] = {"status": "NOT_CONFIGURED", "error": "No TELEGRAM_BOT_TOKEN"}
    else:
        r = requests.get(f"https://api.telegram.org/bot{tg_token}/getMe", timeout=10)
        print(f"getMe: HTTP {r.status_code}")
        if r.status_code == 401:
            results["telegram"] = {"status": "AUTH_FAILED", "http": 401, "note": "Invalid token"}
        elif r.status_code == 200:
            bot_username = r.json().get("result", {}).get("username", "?")
            print(f"Bot: @{bot_username}")
            if tg_chat:
                r2 = requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": f"[JARVIS v5.2.0 D-06] Live roundtrip evidence {timestamp}"},
                    timeout=10
                )
                print(f"sendMessage: HTTP {r2.status_code}")
                if r2.status_code == 200:
                    msg_id = r2.json().get("result", {}).get("message_id")
                    print(f"SUCCESS message_id={msg_id}")
                    results["telegram"] = {"status": "PASS_RUNTIME", "bot": bot_username, "message_id": msg_id, "timestamp": timestamp}
                else:
                    results["telegram"] = {"status": "SEND_FAILED", "http": r2.status_code, "body": r2.text[:300]}
            else:
                results["telegram"] = {"status": "PASS_AUTH_NO_CHAT", "bot": bot_username}
                print("Auth OK — no TELEGRAM_CHAT_ID for send")
        else:
            results["telegram"] = {"status": "ERROR", "http": r.status_code}
except Exception as e:
    results["telegram"] = {"status": "EXCEPTION", "error": str(e)}
    print(f"Exception: {e}")

# ─── D-08 Discord ───────────────────────────────────────────────────
print("\n=== D-08 Discord Live Roundtrip ===")
dc_token   = os.getenv("DISCORD_BOT_TOKEN", "")
dc_channel = os.getenv("DISCORD_CHANNEL_ID", "")
print(f"Token: {'SET len=' + str(len(dc_token)) if dc_token else 'NOT SET'}")
print(f"Channel: {'SET' if dc_channel else 'NOT SET'}")

try:
    if not dc_token:
        results["discord"] = {"status": "NOT_CONFIGURED", "error": "No DISCORD_BOT_TOKEN"}
    else:
        headers = {"Authorization": f"Bot {dc_token}", "Content-Type": "application/json"}
        r = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=10)
        print(f"auth: HTTP {r.status_code}")
        if r.status_code == 401:
            results["discord"] = {"status": "AUTH_FAILED", "http": 401}
        elif r.status_code == 200:
            d = r.json()
            bot_name = f"{d.get('username','?')}#{d.get('discriminator','0000')}"
            print(f"Bot: {bot_name}")
            if dc_channel:
                r2 = requests.post(
                    f"https://discord.com/api/v10/channels/{dc_channel}/messages",
                    headers=headers,
                    json={"content": f"[JARVIS v5.2.0 D-08] Live roundtrip evidence {timestamp}"},
                    timeout=10
                )
                print(f"sendMessage: HTTP {r2.status_code}")
                if r2.status_code in (200, 201):
                    msg_id = r2.json().get("id")
                    print(f"SUCCESS message_id={msg_id}")
                    results["discord"] = {"status": "PASS_RUNTIME", "bot": bot_name, "message_id": msg_id, "timestamp": timestamp}
                else:
                    results["discord"] = {"status": "SEND_FAILED", "http": r2.status_code, "body": r2.text[:300]}
                    print(f"FAILED: {r2.text[:300]}")
            else:
                results["discord"] = {"status": "PASS_AUTH_NO_CHANNEL", "bot": bot_name}
                print("Auth OK — no DISCORD_CHANNEL_ID for send")
        else:
            results["discord"] = {"status": "ERROR", "http": r.status_code}
except Exception as e:
    results["discord"] = {"status": "EXCEPTION", "error": str(e)}
    print(f"Exception: {e}")

# ─── Gemini key check ───────────────────────────────────────────────
print("\n=== GATE-05 Gemini Key Check ===")
gemini_key = os.getenv("GEMINI_API_KEY", "")
print(f"Key present: {bool(gemini_key)}, len={len(gemini_key)}")
print(f"Prefix (first 8): {gemini_key[:8]}...")
print(f"Valid format (AIzaSy): {gemini_key.startswith('AIzaSy')}")
results["gemini_key"] = {
    "present": bool(gemini_key),
    "length": len(gemini_key),
    "valid_format": gemini_key.startswith("AIzaSy"),
    "prefix": gemini_key[:8] if gemini_key else "EMPTY"
}

# ─── Summary ─────────────────────────────────────────────────────────
print("\n=== FINAL SUMMARY ===")
print(json.dumps(results, indent=2, ensure_ascii=False))

os.makedirs("docs/eval", exist_ok=True)
with open("docs/eval/comms_live_roundtrip_evidence.json", "w", encoding="utf-8") as f:
    json.dump({"run_time": timestamp, "results": results}, f, indent=2, ensure_ascii=False)
print("\nEvidence written to docs/eval/comms_live_roundtrip_evidence.json")
