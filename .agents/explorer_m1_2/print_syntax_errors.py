import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

syntax_errors = [d for d in data if d.get("type") == "SYNTAX_ERROR"]
for s in syntax_errors:
    print(f"File: {s['file']}")
    print(f"Content: {s['content']}\n")
