import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

prod_findings = [d for d in data if d["file"].startswith("jarvis")]
pass_funcs = [d for d in prod_findings if d["category"] == "PASS_FUNCTION"]

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\pass_funcs_detail.txt", "w", encoding="utf-8") as out:
    for p in pass_funcs:
        out.write(f"File: {p['file']}:{p['line']}\n")
        out.write(f"Class: {p.get('class')}\n")
        out.write(f"Func: {p['name']}\n")
        out.write(f"Is Abstract: {p.get('is_abstract')}\n")
        out.write(f"Decorators: {p.get('decorators')}\n")
        out.write(f"Docstring: {p.get('docstring')}\n")
        out.write("Context:\n")
        for line in p.get("context", []):
            out.write(f"  {line}\n")
        out.write("="*60 + "\n\n")

print("Wrote pass_funcs_detail.txt")
