"""
JARVIS Built-in Skill: Auto Anki Flashcard Generator
====================================================
Transforms lecture notes, textbook summaries, and vocabulary lists into
standard Flashcard Q&A pairs formatted for direct 1-click import into Anki (TSV / CSV).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.anki_generator")


def extract_flashcards_from_text(text: str) -> list[dict[str, str]]:
    """Extract Q&A pairs from text using regex and semantic pattern heuristics."""
    cards: list[dict[str, str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Pattern 1: Term : Definition or Term - Definition
    term_def_pattern = re.compile(r"^([^:—–\-]{2,50})\s*[:—–\-]\s*(.{10,})$")

    # Pattern 2: Q: ... A: ...
    curr_q: str | None = None

    for line in lines:
        if line.lower().startswith(("q:", "hỏi:", "câu hỏi:")):
            curr_q = re.sub(r"^(?:q|hỏi|câu hỏi):\s*", "", line, flags=re.IGNORECASE).strip()
            continue
        elif curr_q and line.lower().startswith(("a:", "đáp:", "trả lời:")):
            curr_a = re.sub(r"^(?:a|đáp|trả lời):\s*", "", line, flags=re.IGNORECASE).strip()
            cards.append({"front": curr_q, "back": curr_a})
            curr_q = None
            continue

        match = term_def_pattern.match(line)
        if match:
            front = match.group(1).strip()
            back = match.group(2).strip()
            cards.append({"front": front, "back": back})

    return cards


def export_anki_tsv(cards: list[dict[str, str]], output_file: Path) -> Path:
    """Export cards into tab-separated values (.tsv / .txt) format for Anki."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        # Anki TSV format: Front<TAB>Back
        for card in cards:
            front_clean = card["front"].replace("\t", " ").replace("\n", "<br>")
            back_clean = card["back"].replace("\t", " ").replace("\n", "<br>")
            f.write(f"{front_clean}\t{back_clean}\n")
    return output_file


def execute(
    text: str = "",
    file_path: str = "",
    deck_name: str = "JARVIS_Study_Deck",
    output_file: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute Anki flashcard generation.
    """
    study_content = text.strip()
    if file_path.strip():
        p = Path(file_path).resolve()
        if p.is_file():
            try:
                study_content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                log.error("Could not read study file '%s': %s", file_path, exc)

    if not study_content:
        # Default representative baseline demonstration
        study_content = (
            "Overfitting : Hiện tượng mô hình máy học học quá kỹ dữ liệu huấn luyện nhưng dự đoán kém trên dữ liệu mới.\n"
            "Underfitting : Hiện tượng mô hình quá đơn giản, không học được quy luật của dữ liệu.\n"
            "Quantization : Kỹ thuật nén trọng số mô hình từ Float32/Float16 xuống Int8/Int4 để tiết kiệm VRAM.\n"
            "RAG (Retrieval-Augmented Generation) : Kỹ thuật kết hợp truy xuất tài liệu từ cơ sở dữ liệu vector với mô hình ngôn ngữ để trả lời chính xác, tránh ảo giác.\n"
            "Hỏi: VRAM tối thiểu để chạy mô hình Llama-3.2 3B lượng tử hóa 4-bit là bao nhiêu?\n"
            "Đáp: Khoảng 2.0GB đến 2.5GB VRAM."
        )

    cards = extract_flashcards_from_text(study_content)

    out_tsv_path: Path
    if output_file.strip():
        out_tsv_path = Path(output_file).resolve()
    else:
        out_tsv_path = Path(f"D:/Software GitCode/JARVIS/data/{deck_name}.txt")

    if cards:
        export_anki_tsv(cards, out_tsv_path)

    lines: list[str] = [
        f"🎴 **BỘ THẺ NHỚ ANKI FLASHCARDS: {deck_name.upper()}**",
        f"• Đã trích xuất thành công: **{len(cards)} thẻ ghi nhớ (Q&A)**.",
        f"• Tệp xuất tương thích Anki: `{out_tsv_path}`\n",
        "| Mặt trước (Câu hỏi / Thuật ngữ) | Mặt sau (Giải thích / Định nghĩa) |",
        "| :--- | :--- |",
    ]

    for c in cards[:5]:
        lines.append(f"| **{c['front']}** | {c['back']} |")

    if len(cards) > 5:
        lines.append(f"| *... và {len(cards) - 5} thẻ nhớ khác ...* | *Xem chi tiết trong tệp xuất* |")

    lines.append("\n💡 **Cách nạp vào Anki:** Mở ứng dụng Anki -> Chọn `File` -> `Import` -> Chọn tệp `.txt` trên là hoàn tất!")

    msg = "\n".join(lines)
    return {
        "data": {
            "deck_name": deck_name,
            "card_count": len(cards),
            "cards": cards,
            "export_path": str(out_tsv_path),
            "success": True,
        },
        "output": msg,
    }
