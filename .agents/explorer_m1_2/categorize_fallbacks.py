import re
from pathlib import Path
from collections import defaultdict

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\import_fallbacks.txt", "r", encoding="utf-8") as f:
    text = f.read()

entries = text.split("="*60 + "\n\n")

print(f"Loaded {len(entries)-1} entries")

categorized = defaultdict(list)

for entry in entries:
    if not entry.strip():
        continue
    lines = entry.strip().splitlines()
    header = lines[0]
    context = "\n".join(lines[1:])
    
    # Identify what package was attempted to import
    m = re.search(r"import\s+([a-zA-Z0-9_\.]+)|from\s+([a-zA-Z0-9_\.]+)\s+import", context)
    pkg = "unknown"
    if m:
        pkg = m.group(1) or m.group(2)
        pkg = pkg.split(".")[0]
    
    categorized[pkg].append({
        "header": header,
        "context": context
    })

print("\n--- OPTIONAL / CONDITIONAL PACKAGES IMPORTED ---")
for pkg, items in sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"  Package '{pkg}': {len(items)} locations")
    for it in items[:3]:
        print(f"    - {it['header']}")
