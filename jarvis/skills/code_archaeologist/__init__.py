"""
JARVIS Built-in Skill: Codebase Archaeologist & AST Health Inspector
===================================================================
Static AST parser and architectural health inspector for local repositories.
Analyzes syntax trees, extracts classes/functions, estimates cyclomatic complexity,
audits docstring coverage, and highlights architectural debt.
"""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("jarvis.skills.code_archaeologist")


class ComplexityVisitor(ast.NodeVisitor):
    """AST visitor to compute cyclomatic complexity and code entities."""

    def __init__(self) -> None:
        self.complexity: int = 1
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.imports: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_func(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_func(node, is_async=True)
        self.generic_visit(node)

    def _analyze_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        doc = ast.get_docstring(node)
        func_comp = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.Assert,
                ),
            ):
                func_comp += 1
            elif isinstance(child, ast.BoolOp):
                func_comp += len(child.values) - 1

        self.functions.append(
            {
                "name": node.name,
                "lineno": node.lineno,
                "is_async": is_async,
                "has_docstring": bool(doc),
                "arg_count": len(node.args.args),
                "complexity": func_comp,
            }
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        doc = ast.get_docstring(node)
        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
        self.classes.append(
            {
                "name": node.name,
                "lineno": node.lineno,
                "has_docstring": bool(doc),
                "bases": bases,
            }
        )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for alias in node.names:
            self.imports.append(f"{mod}.{alias.name}" if mod else alias.name)
        self.generic_visit(node)


def analyze_python_file(file_path: Path) -> dict[str, Any]:
    """Parse and inspect a single Python source file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"error": str(e), "file": str(file_path)}

    lines = content.splitlines()
    loc = len(lines)
    blank_lines = sum(1 for line in lines if not line.strip())
    comment_lines = sum(1 for line in lines if line.strip().startswith("#"))

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        return {
            "file": str(file_path),
            "loc": loc,
            "syntax_error": f"Line {e.lineno}: {e.msg}",
        }

    visitor = ComplexityVisitor()
    visitor.visit(tree)

    module_doc = ast.get_docstring(tree)

    return {
        "file": str(file_path),
        "loc": loc,
        "blank_lines": blank_lines,
        "comment_lines": comment_lines,
        "has_module_doc": bool(module_doc),
        "classes": visitor.classes,
        "functions": visitor.functions,
        "imports": visitor.imports,
        "syntax_error": None,
    }


def scan_codebase(root_path: Path, max_files: int = 50) -> dict[str, Any]:
    """Scan a project directory recursively for Python files."""
    results: list[dict[str, Any]] = []
    py_files = list(root_path.rglob("*.py"))
    # Filter out hidden or build folders
    filtered = [
        f for f in py_files
        if not any(part.startswith(".") or part in ("venv", "node_modules", "__pycache__", "dist", "build") for part in f.parts)
    ][:max_files]

    total_loc = 0
    total_funcs = 0
    total_classes = 0
    high_complexity_funcs: list[dict[str, Any]] = []

    for pf in filtered:
        info = analyze_python_file(pf)
        results.append(info)
        total_loc += info.get("loc", 0)
        funcs = info.get("functions", [])
        total_funcs += len(funcs)
        total_classes += len(info.get("classes", []))
        for fn in funcs:
            if fn.get("complexity", 1) >= 8:
                high_complexity_funcs.append(
                    {
                        "file": str(pf.name),
                        "function": fn["name"],
                        "line": fn["lineno"],
                        "complexity": fn["complexity"],
                    }
                )

    return {
        "files_scanned": len(filtered),
        "total_loc": total_loc,
        "total_classes": total_classes,
        "total_functions": total_funcs,
        "high_complexity_functions": high_complexity_funcs,
        "details": results,
    }


def execute(
    target_path: str = "D:/Software GitCode/JARVIS/jarvis",
    max_files: int = 25,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute codebase archaeology and AST analysis.

    Args:
        target_path: Directory or file path to analyze.
        max_files: Maximum number of files to process.
    """
    path_obj = Path(target_path)
    if not path_obj.exists():
        return {
            "data": {"error": f"Đường dẫn '{target_path}' không tồn tại.", "success": False},
            "output": f"❌ Không tìm thấy đường dẫn mã nguồn: `{target_path}`",
        }

    if path_obj.is_file():
        file_info = analyze_python_file(path_obj)
        funcs = file_info.get("functions", [])
        classes = file_info.get("classes", [])

        lines: list[str] = [
            f"🔍 **KHẢO CỔ MÃ NGUỒN (CODEBASE ARCHAEOLOGIST):** `{path_obj.name}`",
            f"• Số dòng mã (LOC): **{file_info.get('loc', 0)}** (Trống: {file_info.get('blank_lines', 0)}, Chú thích: {file_info.get('comment_lines', 0)})",
            f"• Module Docstring: {'✅ Có' if file_info.get('has_module_doc') else '⚠️ Thiếu'}",
            f"• Tổng số Class: **{len(classes)}** | Tổng số Hàm: **{len(funcs)}**\n",
            "### 🧬 Danh Sách Hàm & Độ Phức Tạp (Cyclomatic Complexity)",
            "| Tên hàm | Dòng | Async | Docstring | Tham số | Độ phức tạp |",
            "| :--- | :---: | :---: | :---: | :---: | :---: |",
        ]
        for fn in funcs:
            comp_badge = f"🔥 {fn['complexity']}" if fn["complexity"] >= 8 else f"{fn['complexity']}"
            doc_badge = "✅" if fn["has_docstring"] else "❌"
            async_badge = "⚡" if fn["is_async"] else "—"
            lines.append(
                f"| `{fn['name']}` | {fn['lineno']} | {async_badge} | {doc_badge} | {fn['arg_count']} | {comp_badge} |"
            )

        return {
            "data": {"file_info": file_info, "success": True},
            "output": "\n".join(lines),
        }

    # Directory scan
    report = scan_codebase(path_obj, max_files=max_files)
    high_comp = report["high_complexity_functions"]

    lines = [
        f"🏛️ **BÁO CÁO KIỂM TOÁN KIẾN TRÚC & AST:** `{path_obj.name}`",
        f"• Thư mục quét: `{target_path}`",
        f"• Số tệp Python phân tích: **{report['files_scanned']}**",
        f"• Tổng số dòng mã (LOC): **{report['total_loc']:,}**",
        f"• Tổng số Classes: **{report['total_classes']}**",
        f"• Tổng số Functions: **{report['total_functions']}**\n",
        "---",
        "### ⚠️ Điểm Nóng Cần Refactor (Hàm có độ phức tạp cao >= 8)",
    ]

    if high_comp:
        lines.append("| Tệp nguồn | Hàm | Dòng | Độ phức tạp | Đánh giá |")
        lines.append("| :--- | :--- | :---: | :---: | :--- |")
        for hc in high_comp[:10]:
            lines.append(f"| `{hc['file']}` | `{hc['function']}` | {hc['line']} | 🔥 **{hc['complexity']}** | Cần tách nhỏ module |")
    else:
        lines.append("🎉 *Kiến trúc sạch sẽ! Không có hàm nào vượt quá ngưỡng phức tạp cho phép.*")

    lines.extend([
        "\n### 📊 Đề Xuất Tối Ưu Hóa (Architectural Next Steps)",
        "1. **Bổ sung Type Hints** triệt để trên tất cả các hàm chưa có annotations.",
        "2. **Tăng độ phủ Docstrings** cho các hàm public interface.",
        "3. **Tách các khối lồng nhau** (nested conditions) để giảm Cyclomatic Complexity về dưới 6.",
    ])

    return {
        "data": {"report": report, "success": True},
        "output": "\n".join(lines),
    }
