import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

prod_findings = [d for d in data if d["file"].startswith("jarvis")]

print("=== ALL PASS FUNCTIONS IN JARVIS ===")
pass_funcs = [d for d in prod_findings if d["category"] == "PASS_FUNCTION"]
for p in pass_funcs:
    print(f"File: {p['file']}:{p['line']} | Class: {p.get('class')} | Func: {p['name']} | Abstract: {p.get('is_abstract')} | Decorators: {p.get('decorators')}")

print("\n=== ALL TRIVIAL RETURN FUNCTIONS IN JARVIS ===")
triv_funcs = [d for d in prod_findings if d["category"] == "TRIVIAL_RETURN_FUNCTION"]
print(f"Total trivial return functions in jarvis: {len(triv_funcs)}")
# Group by return value
by_ret = {}
for t in triv_funcs:
    by_ret.setdefault(t.get("return_value", "None"), []).append(t)

for ret_val, items in by_ret.items():
    print(f"  Return value '{ret_val}': {len(items)}")

print("\n--- Sample / Suspicious Trivial Returns (empty dict, empty list, None, False, True, '') ---")
for t in triv_funcs:
    # Filter out simple property getters or standard bool checks
    if t.get("is_abstract"):
        print(f"  [ABSTRACT] {t['file']}:{t['line']} -> def {t['name']} returns {t['return_value']}")
    elif t.get("return_value") in ["{}", "[]", "None", "False", "True", "''", '""']:
        print(f"  {t['file']}:{t['line']} | Class: {t.get('class')} | def {t['name']} -> return {t['return_value']} | doc: {t.get('docstring') is not None}")
