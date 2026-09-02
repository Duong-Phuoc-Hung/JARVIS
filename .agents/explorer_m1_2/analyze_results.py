import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

syntax_errors = [d for d in data if d.get("type") == "SYNTAX_ERROR"]
print("=== SYNTAX ERRORS ===")
for s in syntax_errors:
    print(f"File: {s['file']}, Error: {s['content']}")

todo_items = [d for d in data if d.get("type") == "TODO"]
print("\n=== TODO ITEMS ===")
for t in todo_items:
    print(f"File: {t['file']}:{t['line']} -> {t['content']}")

not_impl = [d for d in data if d.get("type") == "RAISE_NOT_IMPLEMENTED"]
print("\n=== RAISE_NOT_IMPLEMENTED ===")
for n in not_impl:
    print(f"File: {n['file']}:{n['line']} in class {n.get('class')} -> {n['content']}")

pass_funcs = [d for d in data if d.get("type") == "PASS_FUNCTION"]
print(f"\n=== PASS_FUNCTIONS ({len(pass_funcs)}) ===")
for p in pass_funcs:
    print(f"File: {p['file']}:{p['line']} Class: {p.get('class')} Func: {p.get('name')} Decorators: {p.get('decorators')} HasDoc: {p.get('has_docstring')}")
