import json
from collections import defaultdict

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Group by location (jarvis vs tests vs scripts)
prod_findings = [d for d in data if d["file"].startswith("jarvis")]
test_findings = [d for d in data if d["file"].startswith("tests")]
script_findings = [d for d in data if d["file"].startswith("scripts") or d["file"].startswith("docs")]

print(f"Total findings: {len(data)}")
print(f"Production (jarvis/): {len(prod_findings)}")
print(f"Tests (tests/): {len(test_findings)}")
print(f"Scripts/Docs: {len(script_findings)}")

print("\n--- PRODUCTION FINDINGS BY CATEGORY ---")
prod_by_cat = defaultdict(list)
for d in prod_findings:
    prod_by_cat[d["category"]].append(d)

for cat, items in prod_by_cat.items():
    print(f"  {cat}: {len(items)}")

print("\n--- 1. TODOs in Production ---")
for d in prod_by_cat["TODO"]:
    print(f"  {d['file']}:{d['line']} -> {d['content']}")

print("\n--- 2. RAISE_NOT_IMPLEMENTED in Production ---")
for d in prod_by_cat["RAISE_NOT_IMPLEMENTED"]:
    print(f"  {d['file']}:{d['line']} ({d.get('class')}) -> {d['exc_str']}")

print("\n--- 3. PASS_FUNCTION in Production (Abstract vs Non-Abstract) ---")
abstract_pass = [d for d in prod_by_cat["PASS_FUNCTION"] if d.get("is_abstract")]
non_abstract_pass = [d for d in prod_by_cat["PASS_FUNCTION"] if not d.get("is_abstract")]
print(f"  Abstract @abstractmethod pass functions: {len(abstract_pass)}")
for d in abstract_pass:
    print(f"    {d['file']}:{d['line']} | class {d.get('class')} | def {d['name']}")

print(f"\n  Non-Abstract pass functions: {len(non_abstract_pass)}")
for d in non_abstract_pass:
    print(f"    {d['file']}:{d['line']} | class {d.get('class')} | def {d['name']} | decorators: {d.get('decorators')}")

print("\n--- 4. EMPTY_CLASS_WITH_DOCSTRING in Production ---")
for d in prod_by_cat["EMPTY_CLASS_WITH_DOCSTRING"]:
    print(f"  {d['file']}:{d['line']} | class {d['name']}({', '.join(d.get('bases', []))}) | is_exception: {d.get('is_exception')}")

print("\n--- 5. EXCEPT_PASS in Production ---")
print(f"  Total except pass in prod: {len(prod_by_cat['EXCEPT_PASS'])}")
for d in prod_by_cat["EXCEPT_PASS"]:
    print(f"    {d['file']}:{d['line']} -> {d['content']}")
