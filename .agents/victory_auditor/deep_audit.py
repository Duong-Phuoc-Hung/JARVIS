"""Deep verification script for production code authenticity."""
import os
import ast
import re
from pathlib import Path

PROJECT_ROOT = Path("d:/Software GitCode/JARVIS")
JARVIS_DIR = PROJECT_ROOT / "jarvis"

def check_modules_summary():
    subdirs = [d for d in JARVIS_DIR.iterdir() if d.is_dir() and d.name != "__pycache__"]
    print("=== Submodule Implementation Deep-Dive ===")
    for d in sorted(subdirs):
        py_files = list(d.rglob("*.py"))
        total_lines = 0
        classes = []
        functions = []
        for p in py_files:
            if "__pycache__" in str(p):
                continue
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                lines = content.splitlines()
                total_lines += len(lines)
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        classes.append(node.name)
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(node.name)
            except Exception as e:
                pass
        print(f"[{d.name}] {len(py_files)} files | {total_lines} lines | {len(classes)} classes | {len(functions)} functions/methods")

def search_suspicious_patterns():
    print("\n=== Scanning for Suspicious Patterns ===")
    patterns = [
        (r'return\s+["\']mock["\']', "returns 'mock' string literal"),
        (r'return\s+True\s*#.*always', "hardcoded always True"),
        (r'unittest\.mock', "unittest.mock reference"),
        (r'pytest', "pytest reference in production code"),
        (r'TODO|FIXME|XXX', "Unimplemented TODO markers"),
    ]
    
    for py_file in JARVIS_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, 1):
                for pat, desc in patterns:
                    if re.search(pat, line, re.IGNORECASE):
                        print(f"[FLAG: {desc}] {py_file.relative_to(PROJECT_ROOT)}:{idx}: {line.strip()}")

if __name__ == "__main__":
    check_modules_summary()
    search_suspicious_patterns()
