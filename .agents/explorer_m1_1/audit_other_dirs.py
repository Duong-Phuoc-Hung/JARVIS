import ast
import os
import re
import json

base_dir = r"d:\Software GitCode\JARVIS"

for folder in ["tests", "scripts", "config", "docs"]:
    target_dir = os.path.join(base_dir, folder)
    if not os.path.exists(target_dir):
        continue
    
    todos_found = []
    not_impl_found = []
    
    for root, dirs, files in os.walk(target_dir):
        for f in sorted(files):
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, base_dir).replace("\\", "/")
            
            try:
                with open(full_path, "r", encoding="utf-8-sig", errors="ignore") as fp:
                    lines = fp.readlines()
            except Exception:
                continue
                
            for i, l in enumerate(lines):
                if re.search(r"#\s*(TODO|FIXME|XXX|HACK)", l, re.IGNORECASE):
                    todos_found.append(f"{rel_path}:{i+1}: {l.strip()}")
                if "NotImplementedError" in l:
                    not_impl_found.append(f"{rel_path}:{i+1}: {l.strip()}")
                    
    print(f"=== {folder}/: {len(todos_found)} TODOs, {len(not_impl_found)} NotImplementedErrors ===")
    if todos_found:
        for t in todos_found[:15]:
            print(f"  TODO: {t}")
        if len(todos_found) > 15:
            print(f"  ... and {len(todos_found)-15} more TODOs")
    if not_impl_found:
        for n in not_impl_found[:15]:
            print(f"  NotImpl: {n}")
        if len(not_impl_found) > 15:
            print(f"  ... and {len(not_impl_found)-15} more NotImpls")

