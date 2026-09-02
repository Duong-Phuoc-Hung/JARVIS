import ast
import os
import json
from collections import defaultdict

jarvis_dir = r"d:\Software GitCode\JARVIS\jarvis"

modules_by_package = defaultdict(list)

# Walk jarvis/
for root, dirs, files in os.walk(jarvis_dir):
    for f in sorted(files):
        if not f.endswith(".py"):
            continue
        full_path = os.path.join(root, f)
        rel_path = os.path.relpath(full_path, jarvis_dir).replace("\\", "/")
        parts = rel_path.split("/")
        pkg = parts[0] if len(parts) > 1 else "root"
        
        with open(full_path, "r", encoding="utf-8-sig", errors="ignore") as fp:
            content = fp.read()
            lines = content.splitlines()
            line_count = len(lines)
            
        modules_by_package[pkg].append({
            "file": rel_path,
            "filename": f,
            "lines": line_count,
            "content": content
        })

print(f"Total packages/folders in jarvis/: {len(modules_by_package)}")
for pkg, file_list in sorted(modules_by_package.items()):
    total_lines = sum(m["lines"] for m in file_list)
    print(f"Package: {pkg} | Files: {len(file_list)} | Lines: {total_lines}")

