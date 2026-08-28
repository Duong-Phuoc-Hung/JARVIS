"""
jarvis/skills/skill_synthesizer/__init__.py
============================================
Self-Coding Skill Synthesizer: generates new JARVIS skills from Vietnamese
natural language descriptions, creates files, and registers them dynamically.
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
    actions: List[str],
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
                text = f'Lỗi lấy dữ liệu: {e}'""")
    elif template == "monitor":
        logic = textwrap.dedent("""\
            import psutil, time
            cpu = psutil.cpu_percent(interval=0.5) if hasattr(psutil, 'cpu_percent') else 0
            ram = psutil.virtual_memory().percent if hasattr(psutil, 'virtual_memory') else 0
            text = f'Theo dõi hệ thống: CPU {cpu:.1f}%, RAM {ram:.1f}%'""")
    elif template == "notifier":
        logic = textwrap.dedent("""\
            import time
            delay = float(kwargs.get('delay_seconds', 60))
            message = kwargs.get('message', query or 'Thông báo từ JARVIS')
            text = f'Đã ghi nhận lời nhắc: \"{message}\" (sau {delay:.0f}s)'""")
    elif template == "file_writer":
        logic = textwrap.dedent("""\
            from pathlib import Path
            content = kwargs.get('content', query)
            filepath = Path(kwargs.get('path', f'logs/{skill_name}_output.txt'))
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding='utf-8')
            text = f'Đã ghi dữ liệu vào {filepath}'""")
    elif template == "checker":
        logic = textwrap.dedent("""\
            import subprocess, sys
            target = kwargs.get('target', query)
            try:
                result = subprocess.run(['ping', '-n', '1', target], capture_output=True, text=True, timeout=5)
                status = 'OK' if result.returncode == 0 else 'Timeout/Không phản hồi'
            except Exception as e:
                status = f'Lỗi: {e}'
            text = f'Kết quả kiểm tra [{target}]: {status}'""")
    else:
        logic = textwrap.dedent("""\
            # TODO: Implement skill logic here
            text = f'Skill [{skill_name}] đã nhận lệnh: {action} với tham số: {query or str(kwargs)}'""")

    # Pre-compute indented logic block (avoid double-indent in f-string)
    logic_indented = "\n".join("        " + ln for ln in logic.strip().splitlines())

    return f'''"""
jarvis/skills/{skill_name}/__init__.py
{'=' * (len(skill_name) + 28)}
Auto-generated skill: {description}
Created: {created_at}
Template: {template}
[synthesized=true]
"""
from __future__ import annotations
import logging, urllib.parse
from typing import Any, Dict

log = logging.getLogger("jarvis.skills.{skill_name}")


def execute(
    action: str = "run",
    query: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    {description}

    Args:
        action: One of {actions_str}
        query: Main input query or target
    Returns:
        dict with keys: data (dict with text + success), output (str)
    """
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


def _validate_skill_name(name: str) -> Optional[str]:
    """Return error message or None if name is valid."""
    if not name:
        return "Vui lòng cung cấp skill_name."
    if not re.match(r"^[a-z][a-z0-9_]{2,29}$", name):
        return "Tên skill phải: chữ thường, số, dấu gạch dưới, 3-30 ký tự, bắt đầu bằng chữ cái."
    if (_SKILLS_ROOT / name).exists() and not (_SKILLS_ROOT / name / "metadata.json").read_text().find('"synthesized": true') == -1:
        return f"Skill '{name}' đã tồn tại (không phải synthesized)."
    return None


def execute(
    action: str = "preview",
    skill_name: str = "",
    description: str = "",
    actions_list: str = "run,status",
    **kwargs: Any,
) -> Dict[str, Any]:
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
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "metadata.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (skill_dir / "__init__.py").write_text(code, encoding="utf-8")
            # Validate syntax
            ast.parse(code)
            msg = f"✅ Kỹ năng '{skill_name}' (template={template}) đã được tạo và đăng ký vào hệ thống!"
            log.info("Synthesized skill: %s", skill_name)
        except SyntaxError as exc:
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)
            msg = f"Lỗi cú pháp khi sinh code: {exc}. Đã rollback."
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
        skill_dir = _SKILLS_ROOT / skill_name
        if not skill_dir.exists():
            msg = f"Kỹ năng '{skill_name}' không tồn tại."
            return {"data": {"text": msg, "success": False}, "output": msg}
        meta_file = skill_dir / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if not meta.get("synthesized"):
                msg = f"Kỹ năng '{skill_name}' là built-in, không thể xóa qua synthesizer."
                return {"data": {"text": msg, "success": False}, "output": msg}
        import shutil
        shutil.rmtree(skill_dir)
        msg = f"🗑️ Đã xóa kỹ năng tổng hợp '{skill_name}'."
        return {"data": {"text": msg, "skill_name": skill_name, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: create, preview, list, delete."
        return {"data": {"text": msg, "success": False}, "output": msg}
