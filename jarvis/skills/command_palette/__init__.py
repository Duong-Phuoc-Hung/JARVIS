"""
JARVIS Built-in Skill: Command Palette & Global Shortcut Launcher
================================================================
Universal command launcher and fuzzy search index across all JARVIS skills,
system utility triggers, and workspace automation workflows.
"""
from __future__ import annotations

import difflib
import logging
import subprocess
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.command_palette")

# Catalog of available system commands and skill dispatchers
REGISTERED_COMMANDS: list[dict[str, Any]] = [
    {
        "id": "clean_downloads",
        "title": "Dọn Dẹp Thư Mục Downloads",
        "description": "Tự động phân loại tài liệu, ảnh, video, installer vào thư mục chuyên biệt.",
        "skill": "smart_downloads",
        "category": "File Management",
        "keywords": ["downloads", "clean", "organize", "files", "sort"],
    },
    {
        "id": "backup_usb",
        "title": "Sao Lưu Dự Án Ra USB",
        "description": "Tự động phát hiện ổ USB cắm ngoài và tạo bản nén ZIP dự án an toàn.",
        "skill": "usb_backup",
        "category": "Storage & Backup",
        "keywords": ["usb", "backup", "archive", "flash drive", "save"],
    },
    {
        "id": "scan_clipboard",
        "title": "Phân Tích & Làm Sạch Clipboard",
        "description": "Tự động định dạng JSON, gỡ bỏ tracking UTM trên URL, hoặc debug lỗi mã nguồn.",
        "skill": "smart_clipboard",
        "category": "Productivity",
        "keywords": ["clipboard", "copy", "json", "url", "clean"],
    },
    {
        "id": "desktop_toast",
        "title": "Gửi Thông Báo Toast Máy Tính",
        "description": "Bắn thông báo Windows Native kèm hiệu ứng âm thanh tùy biến.",
        "skill": "desktop_notifier",
        "category": "System Alert",
        "keywords": ["toast", "notify", "alert", "windows", "sound"],
    },
    {
        "id": "price_drop_check",
        "title": "Kiểm Tra Săn Deal Giá Rẻ",
        "description": "Quét danh mục hàng hóa Shopee/Lazada trong SQLite và cảnh báo nếu có giảm giá.",
        "skill": "price_tracker",
        "category": "Personal Finance",
        "keywords": ["price", "deal", "discount", "shopee", "buy"],
    },
    {
        "id": "health_scan",
        "title": "Phân Tích Chỉ Số Xét Nghiệm Máu",
        "description": "Đánh giá an toàn các chỉ số Glucose, Cholesterol, Men gan hoàn toàn offline.",
        "skill": "health_twin",
        "category": "Healthcare",
        "keywords": ["health", "blood", "glucose", "cholesterol", "medical"],
    },
    {
        "id": "legal_audit",
        "title": "Quét Rủi Ro Hợp Đồng Pháp Lý",
        "description": "Phát hiện bẫy phạt vi phạm, tự động gia hạn và điều khoản bồi thường vô căn cứ.",
        "skill": "contract_scanner",
        "category": "Legal",
        "keywords": ["contract", "legal", "law", "penalty", "agreement"],
    },
    {
        "id": "anki_make",
        "title": "Tạo Thẻ Ghi Nhớ Học Tập Anki",
        "description": "Trích xuất thuật ngữ và câu hỏi trắc nghiệm ra định dạng thẻ Flashcard TSV.",
        "skill": "anki_generator",
        "category": "Education",
        "keywords": ["anki", "flashcard", "study", "learn", "exam"],
    },
    {
        "id": "summarize_media",
        "title": "Tóm Tắt Video & Podcast",
        "description": "Chắt lọc luận điểm cốt lõi, mốc thời gian và hành động đề xuất từ video.",
        "skill": "video_summarizer",
        "category": "AI Research",
        "keywords": ["video", "youtube", "podcast", "summary", "notes"],
    },
    {
        "id": "code_ast_scan",
        "title": "Khảo Cổ & Đo Lường AST Mã Nguồn",
        "description": "Phân tích cấu trúc hàm, độ phức tạp cyclomatic và quan hệ module dự án.",
        "skill": "code_archaeologist",
        "category": "Developer Tools",
        "keywords": ["code", "ast", "python", "archaeologist", "refactor"],
    },
    {
        "id": "sys_lock_screen",
        "title": "Khóa Màn Hình Windows (Lock Workstation)",
        "description": "Khóa máy tính ngay lập tức để bảo vệ dữ liệu khi rời khỏi bàn làm việc.",
        "skill": "system_native",
        "category": "System Action",
        "keywords": ["lock", "screen", "workstation", "security"],
    },
]


def execute_system_action(action_id: str) -> str:
    """Execute low-level system action."""
    if action_id == "sys_lock_screen":
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return "🔒 Đã khóa màn hình máy tính Windows thành công."
        except Exception as e:
            return f"❌ Lỗi khóa màn hình: {e}"
    return f"Lệnh hệ thống '{action_id}' không được hỗ trợ."


def search_palette(query: str) -> list[dict[str, Any]]:
    """Fuzzy search across command registry."""
    q = query.lower().strip()
    if not q:
        return REGISTERED_COMMANDS

    matched: list[dict[str, Any]] = []
    for cmd in REGISTERED_COMMANDS:
        score = 0.0
        # Direct keyword match
        if any(q in kw for kw in cmd["keywords"]):
            score += 0.8
        if q in cmd["title"].lower():
            score += 0.9
        if q in cmd["description"].lower():
            score += 0.5
        # Fuzzy match
        ratio = difflib.SequenceMatcher(None, q, cmd["title"].lower()).ratio()
        if ratio > 0.4:
            score += ratio

        if score > 0.4:
            matched.append({**cmd, "_score": score})

    matched.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return matched


def execute(
    query: str = "",
    action_id: str = "",
    run_matched_skill: bool = False,
    skill_args: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Search or trigger commands from the global palette.

    Args:
        query: Search term for matching commands.
        action_id: Exact command ID to execute immediately.
        run_matched_skill: If True and action_id/first match has a skill, executes it.
        skill_args: Keyword arguments passed directly to the invoked skill.
    """
    # 1. Direct action trigger
    if action_id:
        target_cmd = next((c for c in REGISTERED_COMMANDS if c["id"] == action_id), None)
        if not target_cmd:
            return {
                "data": {"error": f"Không tìm thấy lệnh '{action_id}'", "success": False},
                "output": f"❌ Không tìm thấy lệnh mang ID `{action_id}` trong bảng điều khiển.",
            }

        if target_cmd["skill"] == "system_native":
            res_str = execute_system_action(action_id)
            return {"data": {"action_id": action_id, "success": True}, "output": res_str}

        if run_matched_skill and target_cmd["skill"]:
            try:
                from jarvis.skills.registry import SkillRegistry
                registry = SkillRegistry()
                args = skill_args or {}
                result = registry.invoke_skill(target_cmd["skill"], **args)
                return {
                    "data": {
                        "action_id": action_id,
                        "executed_skill": target_cmd["skill"],
                        "skill_result": result,
                        "success": True,
                    },
                    "output": f"🚀 **ĐÃ KÍCH HOẠT LỆNH:** `{target_cmd['title']}`\n\n{result.get('output', '')}",
                }
            except Exception as e:
                log.error("Lỗi thực thi skill từ command palette: %s", e)
                return {
                    "data": {"error": str(e), "success": False},
                    "output": f"❌ Lỗi khi khởi động skill `{target_cmd['skill']}`: {e}",
                }

    # 2. Search / List palette commands
    matches = search_palette(query)
    lines: list[str] = [
        "🎮 **JARVIS GLOBAL COMMAND PALETTE (BẢNG ĐIỀU KHIỂN ĐA NĂNG)**",
        f"• Từ khóa tìm kiếm: `{query if query else 'Tất cả lệnh'}`",
        f"• Tổng số lệnh khả dụng: **{len(matches)}**\n",
        "| ID Lệnh | Tên chức năng | Phân loại | Thao tác tự động |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for m in matches:
        skill_badge = f"`{m['skill']}`" if m["skill"] else "System API"
        lines.append(f"| `{m['id']}` | **{m['title']}** | {m['category']} | {skill_badge} |")

    lines.extend([
        "\n💡 *Mẹo sử dụng:* Bạn có thể truyền `action_id` kèm `run_matched_skill=True` để thực thi ngay lập tức.",
    ])

    return {
        "data": {
            "query": query,
            "total_matches": len(matches),
            "commands": matches,
            "success": True,
        },
        "output": "\n".join(lines),
    }
