import json
from collections import defaultdict
from pathlib import Path

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Loaded {len(data)} items")

# Group by category and by file
by_cat = defaultdict(list)
for d in data:
    by_cat[d["category"]].append(d)

print("Categories and counts:")
for cat, items in by_cat.items():
    print(f"  {cat}: {len(items)}")

# Let's inspect all non-abstract PASS_FUNCTION in test files vs prod files
test_pass_funcs = [d for d in data if d["file"].startswith("tests") and d["category"] == "PASS_FUNCTION"]
print(f"\nPass functions in tests: {len(test_pass_funcs)}")

# Let's inspect EMPTY_CLASS / EMPTY_CLASS_WITH_DOCSTRING in prod
empty_classes_prod = [d for d in data if d["file"].startswith("jarvis") and d["category"] in ["EMPTY_CLASS", "EMPTY_CLASS_WITH_DOCSTRING"]]
print(f"\nEmpty classes in prod: {len(empty_classes_prod)}")
for c in empty_classes_prod:
    print(f"  {c['file']}:{c['line']} -> {c['content']}")

# Let's inspect DOCSTRING_ONLY_FUNCTION in prod
doc_only_prod = [d for d in data if d["file"].startswith("jarvis") and d["category"] == "DOCSTRING_ONLY_FUNCTION"]
print(f"\nDocstring only functions in prod: {len(doc_only_prod)}")
for doc in doc_only_prod:
    print(f"  {doc['file']}:{doc['line']} -> {doc['class']}.{doc['name']} (abstract={doc.get('is_abstract')})")
