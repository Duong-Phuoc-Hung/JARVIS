import ast
from pathlib import Path

ROOT = Path(r"d:\Software GitCode\JARVIS")

mock_classes = []

for d in ["jarvis", "tests"]:
    dir_path = ROOT / d
    if not dir_path.exists():
        continue
    for py_file in dir_path.rglob("*.py"):
        rel = py_file.relative_to(ROOT)
        try:
            content = py_file.read_text(encoding="utf-8-sig", errors="replace")
            tree = ast.parse(content, filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if any(k in node.name for k in ["Mock", "Fake", "Dummy", "Stub"]):
                    mock_classes.append({
                        "file": str(rel),
                        "line": node.lineno,
                        "name": node.name,
                        "bases": [ast.unparse(b) for b in node.bases]
                    })

print(f"Total Mock/Fake/Dummy classes: {len(mock_classes)}")
with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\mock_classes.txt", "w", encoding="utf-8") as out:
    for m in mock_classes:
        out.write(f"{m['file']}:{m['line']} -> class {m['name']}({', '.join(m['bases'])})\n")
print("Saved to mock_classes.txt")
