"""Update GEMINI_API_KEY in .env with the valid key from GOOGLE_API_KEY"""
from dotenv import load_dotenv, set_key
import os

load_dotenv(override=True)

google_key = os.getenv("GOOGLE_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "")

print(f"GOOGLE_API_KEY: len={len(google_key)}, valid={google_key.startswith('AIzaSy')}")
print(f"GEMINI_API_KEY: len={len(gemini_key)}, valid={gemini_key.startswith('AIzaSy')}")

if google_key.startswith("AIzaSy") and not gemini_key.startswith("AIzaSy"):
    print("\nUpdating GEMINI_API_KEY in .env with GOOGLE_API_KEY value...")
    result = set_key(".env", "GEMINI_API_KEY", google_key)
    print(f"set_key result: {result}")
    
    # Verify
    from dotenv import dotenv_values
    vals = dotenv_values(".env")
    updated = vals.get("GEMINI_API_KEY", "")
    print(f"Verified GEMINI_API_KEY: len={len(updated)}, valid={updated.startswith('AIzaSy')}")
elif gemini_key.startswith("AIzaSy"):
    print("GEMINI_API_KEY already valid — no action needed")
else:
    print("ERROR: Neither GOOGLE_API_KEY nor GEMINI_API_KEY is a valid Gemini key (AIzaSy...)")
