import ast
import os
import re
import json

jarvis_dir = r"d:\Software GitCode\JARVIS\jarvis"

results = []

for root, dirs, files in os.walk(jarvis_dir):
    for f in sorted(files):
        if not f.endswith(".py"):
            continue
        full_path = os.path.join(root, f)
        rel_path = os.path.relpath(full_path, jarvis_dir).replace("\\", "/")
        
        with open(full_path, "r", encoding="utf-8-sig", errors="ignore") as fp:
            content = fp.read()
            lines = content.splitlines()
            line_count = len(lines)
            
        todos = [i+1 for i, l in enumerate(lines) if re.search(r"#\s*(TODO|FIXME|XXX|HACK)", l, re.IGNORECASE)]
        not_impl = [i+1 for i, l in enumerate(lines) if "NotImplementedError" in l]
        
        classes = []
        functions = []
        pass_funcs = []
        imports = []
        
        try:
            tree = ast.parse(content, filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                    body = node.body
                    if len(body) == 1 and isinstance(body[0], ast.Pass):
                        pass_funcs.append(f"{node.name}:{node.lineno}(pass)")
                    elif len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                        pass_funcs.append(f"{node.name}:{node.lineno}(docstring-only)")
                    elif len(body) == 2 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[1], ast.Pass):
                        pass_funcs.append(f"{node.name}:{node.lineno}(doc+pass)")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except Exception as e:
            pass_funcs.append(f"AST_PARSE_ERROR: {e}")
            
        results.append({
            "rel_path": rel_path,
            "lines": line_count,
            "classes": classes,
            "functions_count": len(functions),
            "todos": todos,
            "not_impl": not_impl,
            "pass_funcs": pass_funcs,
            "imports": sorted(set(imports))
        })

output_path = r"d:\Software GitCode\JARVIS\.agents\explorer_m1_1\audit_raw.json"
with open(output_path, "w", encoding="utf-8") as fp:
    json.dump(results, fp, indent=2, ensure_ascii=False)

print(f"Audit completed: {len(results)} files analyzed.")
print(f"Files with TODOs: {sum(1 for r in results if r['todos'])}")
print(f"Files with NotImplementedError: {sum(1 for r in results if r['not_impl'])}")
print(f"Files with pass/empty functions: {sum(1 for r in results if r['pass_funcs'])}")
