"""
JARVIS Built-in Skill: Legal Contract & TOS Scanner
===================================================
Scans rental agreements, labor contracts, and service agreements to identify
hidden penalties, unilateral termination clauses, auto-renewals, and liability disclaimers.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.contract_scanner")

TRAP_DEFINITIONS: list[dict[str, Any]] = [
    {
        "category": "Phạt Vi Phạm & Mất Cọc",
        "severity": "CRITICAL",
        "patterns": [
            r"mất\s+(?:toàn\s+bộ\s+)?(?:tiền\s+)?cọc",
            r"phạt\s+(?:vi\s+phạm\s+)?(?:lên\s+đến\s+)?\d{2,3}%",
            r"bồi\s+thường\s+gấp\s+(?:\d+|hai|ba)\s+lần",
            r"không\s+hoàn\s+lại\s+(?:tiền\s+cọc|chi\s+phí)",
        ],
        "risk_explanation": "Điều khoản phạt vi phạm cọc hoặc bồi thường quá mức, có nguy cơ gây thiệt hại tài chính lớn.",
        "advice": "Đàm phán giới hạn mức phạt tối đa không quá 8% giá trị nghĩa vụ vi phạm theo Điều 301 Luật Thương mại.",
    },
    {
        "category": "Tự Động Gia Hạn Ngầm (Auto-Renew)",
        "severity": "WARNING",
        "patterns": [
            r"tự\s+động\s+gia\s+hạn",
            r"nếu\s+không\s+thông\s+báo\s+trước\s+\d+\s+ngày",
            r"auto-renew",
            r"tiếp\s+tục\s+có\s+hiệu\s+lực\s+thêm",
        ],
        "risk_explanation": "Hợp đồng sẽ tự động trói buộc thêm thời hạn nếu bạn quên gửi văn bản hủy đúng hạn.",
        "advice": "Yêu cầu bên cho thuê/cung cấp phải gửi thông báo bằng văn bản trước ít nhất 15-30 ngày khi hợp đồng sắp hết hạn.",
    },
    {
        "category": "Đơn Phương Chấm Dứt Bất Bình Đẳng",
        "severity": "CRITICAL",
        "patterns": [
            r"có\s+quyền\s+đơn\s+phương\s+(?:chấm\s+dứt|hủy)",
            r"không\s+cần\s+sự\s+đồng\s+ý\s+của\s+bên\s+(?:b|còn\s+lại)",
            r"ngay\s+lập\s+tức\s+thu\s+hồi",
        ],
        "risk_explanation": "Một bên có quyền tự ý hủy hợp đồng mà không cần sự đồng thuận hoặc không cần bồi thường tương xứng.",
        "advice": "Thêm điều kiện: Mọi hành vi chấm dứt phải có lý do vi phạm rõ ràng và có thời hạn khắc phục tối thiểu 7-15 ngày.",
    },
    {
        "category": "Miễn Trừ Trách Nhiệm Một Chiều",
        "severity": "WARNING",
        "patterns": [
            r"không\s+chịu\s+trách\s+nhiệm\s+về\s+(?:bất\s+kỳ\s+)?(?:thiệt\s+hại|mất\s+mát)",
            r"miễn\s+trừ\s+hoàn\s+toàn",
            r"rủi\s+ro\s+thuộc\s+về\s+bên\s+(?:b|mua|thuê)",
        ],
        "risk_explanation": "Bên cung cấp trút toàn bộ rủi ro kỹ thuật, hỏng hóc hoặc chậm trễ sang bạn.",
        "advice": "Yêu cầu bên cung cấp phải cam kết bảo hành và chịu trách nhiệm với lỗi phát sinh từ phía họ.",
    },
]


def scan_contract_text(text: str) -> dict[str, Any]:
    """Scan raw text for identified trap clauses."""
    detected_traps: list[dict[str, Any]] = []
    lines = text.splitlines()

    for trap in TRAP_DEFINITIONS:
        matched_sentences: list[str] = []
        for pattern in trap["patterns"]:
            regex = re.compile(pattern, re.IGNORECASE)
            for line in lines:
                clean_line = line.strip()
                if clean_line and regex.search(clean_line):
                    if clean_line not in matched_sentences:
                        matched_sentences.append(clean_line)

        if matched_sentences:
            detected_traps.append({
                "category": trap["category"],
                "severity": trap["severity"],
                "risk_explanation": trap["risk_explanation"],
                "advice": trap["advice"],
                "matched_count": len(matched_sentences),
                "samples": matched_sentences[:3],
            })

    return {
        "total_lines": len(lines),
        "traps_found": len(detected_traps),
        "traps": detected_traps,
    }


def execute(
    text: str = "",
    contract_text: str = "",
    file_path: str = "",
    action: str = "scan",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute legal contract risk inspection.
    """
    contract_content = contract_text.strip() or text.strip() or kwargs.get("content", "").strip()

    if file_path.strip():
        p = Path(file_path).resolve()
        if p.is_file():
            try:
                contract_content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                log.error("Could not read contract file '%s': %s", file_path, exc)

    if not contract_content:
        # Default representative baseline demonstration
        contract_content = (
            "Điều 5: Nếu Bên B vi phạm thời hạn thanh toán quá 5 ngày, Bên B sẽ bị mất toàn bộ tiền cọc.\n"
            "Điều 8: Hợp đồng này sẽ tự động gia hạn thêm 12 tháng nếu Bên B không thông báo trước 30 ngày.\n"
            "Điều 10: Bên A có quyền đơn phương chấm dứt hợp đồng mà không cần bồi thường thiệt hại."
        )

    scan_result = scan_contract_text(contract_content)
    traps = scan_result["traps"]

    lines: list[str] = [
        "⚖️ **KẾT QUẢ QUÉT BẪY PHÁP LÝ & RỦI RO HỢP ĐỒNG**",
    ]

    if not traps:
        lines.append("✨ Hợp đồng không phát hiện điều khoản bẫy nghiêm trọng nào theo danh mục quét cơ bản.")
    else:
        lines.append(f"🚨 Phát hiện **{len(traps)} nhóm điều khoản có mức độ rủi ro cao**:\n")
        for idx, t in enumerate(traps, start=1):
            severity_icon = "🔴" if t["severity"] == "CRITICAL" else "🟡"
            lines.append(f"### {idx}. {severity_icon} [{t['severity']}] {t['category']}")
            lines.append(f"• **Rủi ro:** {t['risk_explanation']}")
            lines.append(f"• **Khuyến nghị đàm phán:** *{t['advice']}*")
            lines.append("• **Trích đoạn phát hiện trong hợp đồng:**")
            for sample in t["samples"]:
                lines.append(f"  > *\"{sample}\"*")
            lines.append("")

    lines.append("💡 *Lưu ý:* Phân tích mang tính tham khảo kỹ thuật, hãy tham vấn luật sư chuyên môn trước khi ký kết các hợp đồng giá trị lớn.")

    risk_level = "LOW"
    if any(t["severity"] == "CRITICAL" for t in traps):
        risk_level = "CRITICAL"
    elif traps:
        risk_level = "HIGH"

    msg = "\n".join(lines)
    return {
        "data": {
            "traps_found": len(traps),
            "traps": traps,
            "findings": traps,
            "risk_level": risk_level,
            "success": True,
        },
        "output": msg,
    }
