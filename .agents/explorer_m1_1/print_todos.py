import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_1\audit_raw.json", "r", encoding="utf-8") as fp:
    results = json.load(fp)

print("=== TODOs, NotImplementedError, Pass/Empty Functions ===")
for r in results:
    if r["todos"] or r["not_impl"] or r["pass_funcs"]:
        print(f"File: {r['rel_path']} (lines: {r['lines']})")
        if r["todos"]:
            print(f"  TODOs on lines: {r['todos']}")
        if r["not_impl"]:
            print(f"  NotImplementedError on lines: {r['not_impl']}")
        if r["pass_funcs"]:
            print(f"  Pass/Empty functions: {r['pass_funcs']}")
