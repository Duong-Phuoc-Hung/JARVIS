"""
Comprehensive AST and regex code scanner for stubs, placeholders, TODOs, FIXMEs,
NotImplementedErrors, dummy functions, and pass statements in JARVIS.
"""
import ast
import os
import re
import json
from pathlib import Path

ROOT = Path(r"d:\Software GitCode\JARVIS")

def node_to_str(node):
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return str(node)

def analyze_ast(tree, content, lines, rel_path):
    findings = []
    
    class ASTVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current_class = None
            self.class_stack = []

        def visit_ClassDef(self, node):
            self.class_stack.append(node.name)
            self.current_class = ".".join(self.class_stack)
            
            bases_str = [node_to_str(b) for b in node.bases]
            is_exception = any("Error" in b or "Exception" in b for b in bases_str)
            
            # Check if class body is just pass
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append({
                    "category": "EMPTY_CLASS",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "name": node.name,
                    "bases": bases_str,
                    "is_exception": is_exception,
                    "content": f"class {node.name}({', '.join(bases_str)}): pass",
                    "context": lines[max(0, node.lineno-1):min(len(lines), node.lineno+2)]
                })
            elif len(node.body) == 2 and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[1], ast.Pass):
                findings.append({
                    "category": "EMPTY_CLASS_WITH_DOCSTRING",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "name": node.name,
                    "bases": bases_str,
                    "is_exception": is_exception,
                    "content": f"class {node.name}({', '.join(bases_str)}): [docstring]; pass",
                    "context": lines[max(0, node.lineno-1):min(len(lines), node.lineno+3)]
                })
            
            self.generic_visit(node)
            self.class_stack.pop()
            self.current_class = ".".join(self.class_stack) if self.class_stack else None

        def visit_FunctionDef(self, node):
            self._check_func(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            self._check_func(node)
            self.generic_visit(node)

        def _check_func(self, node):
            decorators = [node_to_str(d) for d in node.decorator_list]
            is_abstract = any("abstractmethod" in d for d in decorators)
            body_stmts = node.body
            is_empty_pass = False
            has_docstring = False
            docstring = None
            
            # Case 1: single pass
            if len(body_stmts) == 1 and isinstance(body_stmts[0], ast.Pass):
                is_empty_pass = True
            # Case 2: docstring + pass
            elif len(body_stmts) == 2 and isinstance(body_stmts[0], ast.Expr) and isinstance(body_stmts[0].value, ast.Constant) and isinstance(body_stmts[0].value.value, str) and isinstance(body_stmts[1], ast.Pass):
                is_empty_pass = True
                has_docstring = True
                docstring = body_stmts[0].value.value
            # Case 3: docstring only (no other statements)
            elif len(body_stmts) == 1 and isinstance(body_stmts[0], ast.Expr) and isinstance(body_stmts[0].value, ast.Constant) and isinstance(body_stmts[0].value.value, str):
                has_docstring = True
                docstring = body_stmts[0].value.value
                findings.append({
                    "category": "DOCSTRING_ONLY_FUNCTION",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "name": node.name,
                    "decorators": decorators,
                    "docstring": docstring,
                    "is_abstract": is_abstract,
                    "content": f"def {node.name}(...): [docstring only]",
                    "context": lines[max(0, node.lineno-1):min(len(lines), node.lineno+5)]
                })
            # Case 4: single return None / return / return {} / return [] / return False / return True / return ""
            elif len(body_stmts) == 1 and isinstance(body_stmts[0], ast.Return):
                ret_val = node_to_str(body_stmts[0].value)
                findings.append({
                    "category": "TRIVIAL_RETURN_FUNCTION",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "name": node.name,
                    "decorators": decorators,
                    "return_value": ret_val,
                    "is_abstract": is_abstract,
                    "content": f"def {node.name}(...): return {ret_val}",
                    "context": lines[max(0, node.lineno-1):min(len(lines), node.lineno+4)]
                })
            # Case 5: docstring + single return
            elif len(body_stmts) == 2 and isinstance(body_stmts[0], ast.Expr) and isinstance(body_stmts[0].value, ast.Constant) and isinstance(body_stmts[0].value.value, str) and isinstance(body_stmts[1], ast.Return):
                ret_val = node_to_str(body_stmts[1].value)
                findings.append({
                    "category": "TRIVIAL_RETURN_FUNCTION",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "name": node.name,
                    "decorators": decorators,
                    "docstring": body_stmts[0].value.value,
                    "return_value": ret_val,
                    "is_abstract": is_abstract,
                    "content": f"def {node.name}(...): [docstring]; return {ret_val}",
                    "context": lines[max(0, node.lineno-1):min(len(lines), node.lineno+5)]
                })

            if is_empty_pass:
                findings.append({
                    "category": "PASS_FUNCTION",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "name": node.name,
                    "decorators": decorators,
                    "has_docstring": has_docstring,
                    "docstring": docstring,
                    "is_abstract": is_abstract,
                    "content": f"def {node.name}(...): pass",
                    "context": lines[max(0, node.lineno-1):min(len(lines), node.lineno+4)]
                })

        def visit_Raise(self, node):
            if node.exc:
                exc_str = node_to_str(node.exc)
                if "NotImplementedError" in exc_str:
                    findings.append({
                        "category": "RAISE_NOT_IMPLEMENTED",
                        "file": str(rel_path),
                        "line": node.lineno,
                        "class": self.current_class,
                        "exc_str": exc_str,
                        "content": lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "raise NotImplementedError",
                        "context": lines[max(0, node.lineno-3):min(len(lines), node.lineno+3)]
                    })
            self.generic_visit(node)

        def visit_ExceptHandler(self, node):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                exc_type = node_to_str(node.type) if node.type else "Exception"
                findings.append({
                    "category": "EXCEPT_PASS",
                    "file": str(rel_path),
                    "line": node.lineno,
                    "class": self.current_class,
                    "exc_type": exc_type,
                    "content": f"except {exc_type}: pass",
                    "context": lines[max(0, node.lineno-2):min(len(lines), node.lineno+3)]
                })
            self.generic_visit(node)

    visitor = ASTVisitor()
    visitor.visit(tree)
    return findings

def scan_file(filepath: Path):
    rel_path = filepath.relative_to(ROOT)
    try:
        content = filepath.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e:
        return [{"category": "READ_ERROR", "file": str(rel_path), "content": str(e)}]

    lines = content.splitlines()
    findings = []

    # 1. Regex checks
    for idx, line in enumerate(lines, 1):
        if re.search(r"#\s*TODO\b", line, re.IGNORECASE):
            findings.append({
                "category": "TODO",
                "file": str(rel_path),
                "line": idx,
                "content": line.strip(),
                "context": lines[max(0, idx-3):min(len(lines), idx+3)]
            })
        if re.search(r"#\s*FIXME\b", line, re.IGNORECASE):
            findings.append({
                "category": "FIXME",
                "file": str(rel_path),
                "line": idx,
                "content": line.strip(),
                "context": lines[max(0, idx-3):min(len(lines), idx+3)]
            })
        if re.search(r"#\s*STUB\b", line, re.IGNORECASE):
            findings.append({
                "category": "STUB_COMMENT",
                "file": str(rel_path),
                "line": idx,
                "content": line.strip(),
                "context": lines[max(0, idx-3):min(len(lines), idx+3)]
            })
        if re.search(r"#\s*XXX\b", line):
            findings.append({
                "category": "XXX",
                "file": str(rel_path),
                "line": idx,
                "content": line.strip(),
                "context": lines[max(0, idx-3):min(len(lines), idx+3)]
            })

    # 2. AST parsing for python files
    if filepath.suffix == ".py":
        try:
            tree = ast.parse(content, filename=str(filepath))
            ast_findings = analyze_ast(tree, content, lines, rel_path)
            findings.extend(ast_findings)
        except Exception as e:
            findings.append({
                "category": "SYNTAX_ERROR",
                "file": str(rel_path),
                "line": 0,
                "content": str(e),
                "context": []
            })

    return findings

def main():
    target_dirs = ["jarvis", "tests", "scripts", "docs"]
    all_findings = []
    
    for d in target_dirs:
        dir_path = ROOT / d
        if not dir_path.exists():
            continue
        for f in dir_path.rglob("*"):
            if f.is_file() and f.suffix in [".py", ".md", ".yaml", ".json", ".toml"]:
                res = scan_file(f)
                all_findings.extend(res)

    print(f"Total findings: {len(all_findings)}")
    by_category = {}
    for f in all_findings:
        c = f.get("category", "UNKNOWN")
        by_category.setdefault(c, []).append(f)

    for c, items in by_category.items():
        print(f"Category {c}: {len(items)}")

    with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_2\scan_results.json", "w", encoding="utf-8") as out:
        json.dump(all_findings, out, indent=2, ensure_ascii=False)
    print("Saved to scan_results.json")

if __name__ == "__main__":
    main()
