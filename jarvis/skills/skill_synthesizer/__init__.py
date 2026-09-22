"""
jarvis/skills/skill_synthesizer/__init__.py
============================================
Self-Coding Skill Synthesizer: generates new JARVIS skills from Vietnamese
natural language descriptions and creates files. Runtime registration is separate.
"""
from __future__ import annotations

import ast
import datetime
import json
import logging
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.skill_synthesizer")

_SKILLS_ROOT = Path("jarvis/skills")

# Template categories based on keyword analysis
_KEYWORD_TEMPLATES = {
    "fetch|lấy|tải|get|download|scrape": "web_fetch",
    "tính|calculate|compute|eval|math": "calculator",
    "theo dõi|monitor|watch|track|theo dõi": "monitor",
    "thông báo|notify|alert|nhắc|reminder": "notifier",
    "lưu|save|ghi|store|write|file": "file_writer",
    "đọc|read|xem|view|open|mở": "file_reader",
    "gửi|send|post|email|message": "sender",
    "kiểm tra|check|test|verify|validate": "checker",
    "chuyển đổi|convert|transform|parse": "converter",
}


def _detect_template(description: str) -> str:
    """Detect the most appropriate template from description keywords."""
    lower = description.lower()
    for pattern, template in _KEYWORD_TEMPLATES.items():
        if re.search(pattern, lower):
            return template
    return "generic"


def _generate_skill_code(
    skill_name: str,
    description: str,
    template: str,
    actions: list[str],
) -> str:
    """Generate the execute() function for a new skill."""
    actions_str = ", ".join([f"'{a}'" for a in actions])
    created_at = datetime.datetime.now().isoformat()

    if template == "web_fetch":
        logic = textwrap.dedent("""\
            try:
                import urllib.request
                url = kwargs.get('url', query)
                if not url.startswith('http'):
                    url = f'https://duckduckgo.com/html/?q={urllib.parse.quote(url)}'
                req = urllib.request.urlopen(url, timeout=10)
                content = req.read().decode('utf-8', errors='replace')[:2000]
                text = f'Đã lấy nội dung từ {url}: {content[:200]}...'
            except Exception as e:
                success = False
                text = f'Lỗi lấy dữ liệu: {e}'""")
    elif template == "monitor":
        logic = textwrap.dedent("""\
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory().percent
            text = f'Theo dõi hệ thống: CPU {cpu:.1f}%, RAM {ram:.1f}%'""")
    elif template == "notifier":
        logic = textwrap.dedent("""\
            success = False
            text = 'NOT_IMPLEMENTED: notification scheduling requires a connected backend.'""")
    elif template == "file_writer":
        logic = textwrap.dedent("""\
            from pathlib import Path
            content = kwargs.get('content', query)
            filepath = Path(kwargs.get('path', 'logs/skill_output.txt'))
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding='utf-8')
            text = f'Đã ghi dữ liệu vào {filepath}'""")
    elif template == "checker":
        logic = textwrap.dedent("""\
            import subprocess, sys
            target = kwargs.get('target', query)
            try:
                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                result = subprocess.run(['ping', '-n', '1', target], capture_output=True, text=True, timeout=5, creationflags=_cflags)
                success = result.returncode == 0
                status = 'OK' if result.returncode == 0 else 'Timeout/Không phản hồi'
            except Exception as e:
                success = False
                status = f'Lỗi: {e}'
            text = f'Kết quả kiểm tra [{target}]: {status}'""")
    else:
        logic = textwrap.dedent("""\
            success = False
            text = 'NOT_IMPLEMENTED: this template has no execution backend.'""")

    # Pre-compute indented logic block (avoid double-indent in f-string)
    logic_indented = "\n".join("        " + ln for ln in logic.strip().splitlines())

    # Descriptions/actions are user data, never source-code fragments.
    module_doc = repr(
        f"Auto-generated skill: {description}\nCreated: {created_at}\n"
        f"Template: {template}\n[synthesized=true]"
    )
    function_doc = repr(f"{description}\nActions: {actions_str}")
    return f'''{module_doc}
from __future__ import annotations
import logging, urllib.parse
from typing import Any, Dict

log = logging.getLogger("jarvis.skills.{skill_name}")


def execute(
    action: str = "run",
    query: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    {function_doc}
    act = action.lower().strip()
    text = ""
    success = True

    try:
{logic_indented}
    except Exception as exc:
        log.error("Skill [{skill_name}] error: %s", exc)
        text = f"Loi thuc thi [{skill_name}]: {{exc}}"
        success = False

    return {{"data": {{"text": text, "action": act, "success": success}}, "output": text}}
'''


def _validate_skill_name(name: str) -> str | None:
    """Return error message or None if name is valid."""
    if not name:
        return "Vui lòng cung cấp skill_name."
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,29}", name):
        return "Tên skill phải: chữ thường, số, dấu gạch dưới, 3-30 ký tự, bắt đầu bằng chữ cái."
    target = _SKILLS_ROOT / name
    if target.is_symlink() or target.resolve().parent != _SKILLS_ROOT.resolve():
        return "Skill path nằm ngoài thư mục skills hoặc là liên kết."
    if target.exists():
        return f"Skill '{name}' đã tồn tại; không ghi đè."
    return None


def execute(
    action: str = "preview",
    skill_name: str = "",
    description: str = "",
    actions_list: str = "run,status",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Self-Coding Skill Synthesizer.

    Args:
        action: 'create' | 'preview' | 'list' | 'delete'
        skill_name: Python identifier for the new skill (lowercase, underscores)
        description: Vietnamese description of what the skill does
        actions_list: Comma-separated list of actions the skill will support
    """
    act = action.lower().strip()
    actions = [a.strip() for a in actions_list.split(",") if a.strip()] or ["run"]
    template = _detect_template(description)

    if act in ("create", "preview"):
        err = _validate_skill_name(skill_name)
        if err:
            return {"data": {"text": err, "success": False}, "output": err}
        if not description.strip():
            return {"data": {"text": "Vui lòng mô tả chức năng của kỹ năng.", "success": False},
                    "output": "Vui lòng mô tả chức năng của kỹ năng."}

        code = _generate_skill_code(skill_name, description, template, actions)
        metadata = {
            "name": skill_name,
            "display_name": description[:60],
            "description": description,
            "version": "1.0.0",
            "author": "JARVIS Synthesizer",
            "synthesized": True,
            "template": template,
            "created_at": datetime.datetime.now().isoformat(),
            "tags": ["synthesized", template],
            "actions": actions,
        }

        if act == "preview":
            preview_text = f"📋 Preview skill '{skill_name}' (template={template}):\n\n```python\n{code[:800]}...\n```"
            return {"data": {"text": preview_text, "code": code, "metadata": metadata, "success": True},
                    "output": preview_text}

        # Create
        skill_dir = _SKILLS_ROOT / skill_name
        try:
            ast.parse(code)
            skill_dir.mkdir(parents=True, exist_ok=False)
            (skill_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (skill_dir / "__init__.py").write_text(code, encoding="utf-8")
            msg = f"Đã tạo tệp kỹ năng '{skill_name}' (template={template}); chưa xác minh thực thi hoặc đăng ký runtime."
            log.info("Synthesized skill: %s", skill_name)
        except SyntaxError as exc:
            msg = f"Lỗi cú pháp khi sinh code: {exc}. Không ghi tệp."
            return {"data": {"text": msg, "success": False}, "output": msg}
        except Exception as exc:
            msg = f"Lỗi tạo kỹ năng '{skill_name}': {exc}"
            return {"data": {"text": msg, "success": False}, "output": msg}

        return {"data": {"text": msg, "skill_name": skill_name, "template": template, "code": code, "success": True},
                "output": msg}

    elif act == "list":
        synthesized = []
        for d in _SKILLS_ROOT.iterdir():
            meta_file = d / "metadata.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if meta.get("synthesized"):
                        synthesized.append({"name": meta["name"], "description": meta.get("description", ""), "template": meta.get("template", "")})
                except Exception:
                    pass
        if not synthesized:
            msg = "Chưa có kỹ năng nào được tổng hợp tự động."
        else:
            lines = [f"🧬 {len(synthesized)} kỹ năng được tổng hợp:"]
            for s in synthesized:
                lines.append(f"  • '{s['name']}' [{s['template']}]: {s['description'][:50]}")
            msg = "\n".join(lines)
        return {"data": {"skills": synthesized, "text": msg, "success": True}, "output": msg}

    elif act == "delete":
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,29}", skill_name):
            msg = "Tên skill không hợp lệ; không xóa."
            return {"data": {"text": msg, "success": False}, "output": msg}
        skill_dir = _SKILLS_ROOT / skill_name
        if skill_dir.is_symlink() or skill_dir.resolve().parent != _SKILLS_ROOT.resolve():
            msg = "Skill path nằm ngoài thư mục skills hoặc là liên kết; không xóa."
            return {"data": {"text": msg, "success": False}, "output": msg}
        if not skill_dir.exists():
            msg = f"Kỹ năng '{skill_name}' không tồn tại."
            return {"data": {"text": msg, "success": False}, "output": msg}
        meta_file = skill_dir / "metadata.json"
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
        if not isinstance(meta, dict) or meta.get("synthesized") is not True:
            msg = f"Kỹ năng '{skill_name}' không có metadata synthesized hợp lệ; không xóa."
            return {"data": {"text": msg, "success": False}, "output": msg}
        import shutil
        shutil.rmtree(skill_dir)
        msg = f"🗑️ Đã xóa kỹ năng tổng hợp '{skill_name}'."
        return {"data": {"text": msg, "skill_name": skill_name, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: create, preview, list, delete."
        return {"data": {"text": msg, "success": False}, "output": msg}
