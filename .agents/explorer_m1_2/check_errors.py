import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

syntax_errors = [d for d in data if d.get("category") == "SYNTAX_ERROR"]
print(f"Syntax error count: {len(syntax_errors)}")
for s in syntax_errors:
    print(f"File: {s['file']} -> {s['content']}")
