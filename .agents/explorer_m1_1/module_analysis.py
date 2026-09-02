import ast
import os
import json
import re

jarvis_dir = r"d:\Software GitCode\JARVIS\jarvis"
tests_dir = r"d:\Software GitCode\JARVIS\tests"

# Let's map test files to modules
test_files = []
for root, _, fs in os.walk(tests_dir):
    for f in fs:
        if f.startswith("test_") and f.endswith(".py"):
            test_files.append(os.path.join(root, f))

print(f"Found {len(test_files)} test files.")

module_info = []

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
            
        todos = [i+1 for i, l in enumerate(lines) if re.search(r"#\s*(TODO|FIXME|XXX|HACK)", l, re.IGNORECASE)]
        not_impl = [i+1 for i, l in enumerate(lines) if "NotImplementedError" in l]
        
        # Check imports
        imports = []
        try:
            tree = ast.parse(content, filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        imports.append(a.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except Exception:
            pass
            
        # Check matching tests
        mod_stem = f.replace(".py", "")
        matching_tests = []
        for tf in test_files:
            try:
                with open(tf, "r", encoding="utf-8-sig", errors="ignore") as tfp:
                    tcontent = tfp.read()
                    if rel_path.replace("/", ".") in tcontent or f"jarvis.{pkg}" in tcontent or mod_stem in tcontent:
                        matching_tests.append(os.path.basename(tf))
            except Exception:
                pass
                
        module_info.append({
            "pkg": pkg,
            "rel_path": rel_path,
            "filename": f,
            "lines": line_count,
            "todos": todos,
            "not_impl": not_impl,
            "imports": sorted(set(imports)),
            "matching_tests": sorted(set(matching_tests))[:5]
        })

print(f"Total modules analyzed: {len(module_info)}")
with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_1\modules_detailed.json", "w", encoding="utf-8") as fp:
    json.dump(module_info, fp, indent=2, ensure_ascii=False)
