import re
from pathlib import Path

ROOT = Path(r"d:\Software GitCode\JARVIS\jarvis")

import_fallbacks = []

for py_file in ROOT.rglob("*.py"):
    rel_path = py_file.relative_to(ROOT.parent)
    try:
        content = py_file.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        continue

    lines = content.splitlines()
    for idx, line in enumerate(lines, 1):
        if re.search(r"except\s+(?:\([^\)]*ImportError[^\)]*\)|ImportError|ModuleNotFoundError)", line):
            # Capture context
            start = max(0, idx - 6)
            end = min(len(lines), idx + 10)
            import_fallbacks.append({
                "file": str(rel_path),
                "line": idx,
                "content": line.strip(),
                "context": lines[start:end]
            })

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\import_fallbacks.txt", "w", encoding="utf-8") as out:
    for f in import_fallbacks:
        out.write(f"File: {f['file']}:{f['line']} -> {f['content']}\n")
        for l in f['context']:
            out.write(f"  {l}\n")
        out.write("="*60 + "\n\n")

print(f"Total import fallback locations: {len(import_fallbacks)}")
