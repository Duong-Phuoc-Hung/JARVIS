"""Integrity Forensics AST & Static Analysis Script for JARVIS Victory Audit."""
import ast
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path("d:/Software GitCode/JARVIS")
JARVIS_DIR = PROJECT_ROOT / "jarvis"

def check_file_ast(file_path: Path):
    issues = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return [f"AST Parse Error in {file_path}: {e}"]

    # 1. Check for mock imports in production code
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "mock" in alias.name.lower() or "pytest" in alias.name.lower():
                    issues.append(f"Mock/Pytest import in production code: 'import {alias.name}' at line {node.lineno}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "mock" in mod.lower() or "pytest" in mod.lower():
                issues.append(f"Mock/Pytest import in production code: 'from {mod}' at line {node.lineno}")

    # 2. Check for empty/stub functions or facade patterns
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check body length
            body = node.body
            # Filter out docstrings
            meaningful_stmts = []
            for stmt in body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    continue # docstring
                meaningful_stmts.append(stmt)
            
            if not meaningful_stmts:
                # Is it an abstract method or protocol?
                is_abstract = any(
                    isinstance(d, ast.Name) and d.id in ("abstractmethod", "override")
                    or isinstance(d, ast.Attribute) and d.attr in ("abstractmethod", "override")
                    for d in node.decorator_list
                )
                if not is_abstract:
                    issues.append(f"Empty/Stub function '{node.name}' at line {node.lineno} in {file_path.name}")
            elif len(meaningful_stmts) == 1:
                single_stmt = meaningful_stmts[0]
                if isinstance(single_stmt, ast.Pass):
                    is_abstract = any(
                        isinstance(d, ast.Name) and d.id in ("abstractmethod", "override")
                        or isinstance(d, ast.Attribute) and d.attr in ("abstractmethod", "override")
                        for d in node.decorator_list
                    )
                    if not is_abstract:
                        issues.append(f"Function with only 'pass': '{node.name}' at line {node.lineno} in {file_path.name}")
                elif isinstance(single_stmt, ast.Raise):
                    # Check if raising NotImplementedError outside abstract class
                    if isinstance(single_stmt.exc, ast.Call) and isinstance(single_stmt.exc.func, ast.Name):
                        if single_stmt.exc.func.id == "NotImplementedError":
                            is_abstract = any(
                                isinstance(d, ast.Name) and d.id in ("abstractmethod", "override")
                                or isinstance(d, ast.Attribute) and d.attr in ("abstractmethod", "override")
                                for d in node.decorator_list
                            )
                            if not is_abstract:
                                issues.append(f"Function with only 'raise NotImplementedError': '{node.name}' at line {node.lineno} in {file_path.name}")

    return issues

def main():
    print(f"Scanning directory: {JARVIS_DIR}")
    py_files = list(JARVIS_DIR.rglob("*.py"))
    print(f"Found {len(py_files)} Python source files under jarvis/")
    
    total_issues = 0
    file_count = 0
    total_loc = 0
    
    for py_file in py_files:
        if "__pycache__" in str(py_file):
            continue
        file_count += 1
        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            total_loc += len(lines)
            
        file_issues = check_file_ast(py_file)
        if file_issues:
            print(f"\n[FLAG] {py_file.relative_to(PROJECT_ROOT)}:")
            for issue in file_issues:
                print(f"  - {issue}")
                total_issues += 1
        else:
            # print(f"[OK] {py_file.relative_to(PROJECT_ROOT)} ({len(lines)} lines)")
            pass
            
    print(f"\nTotal Python files scanned: {file_count}")
    print(f"Total Lines of Code: {total_loc}")
    print(f"Total potential integrity issues flagged: {total_issues}")

if __name__ == "__main__":
    main()
