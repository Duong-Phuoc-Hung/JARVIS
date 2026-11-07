"""
Unit tests for JARVIS Extended Skills Suite
===========================================
Validates discovery, contracts, inputs, outputs, and edge cases for the 13 newly
integrated local skills in JARVIS.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from jarvis.skills.registry import SkillRegistry


@pytest.fixture
def registry() -> SkillRegistry:
    """Fixture providing initialized SkillRegistry."""
    skills_dir = Path("jarvis/skills").resolve()
    return SkillRegistry(skills_dir=skills_dir, auto_discover=True)


class TestExtendedSkillsRegistry:
    """Test registry discovery and metadata for extended skills."""

    NEW_SKILLS = [
        "desktop_notifier",
        "smart_downloads",
        "smart_renamer",
        "usb_backup",
        "deep_search",
        "smart_clipboard",
        "health_twin",
        "contract_scanner",
        "anki_generator",
        "price_tracker",
        "video_summarizer",
        "command_palette",
        "code_archaeologist",
    ]

    def test_all_extended_skills_discovered(self, registry: SkillRegistry) -> None:
        skills = registry.discover_skills()
        for skill_name in self.NEW_SKILLS:
            assert skill_name in skills, f"Skill '{skill_name}' was not discovered by registry!"

    def test_extended_skills_metadata_integrity(self, registry: SkillRegistry) -> None:
        skills = registry.discover_skills()
        for skill_name in self.NEW_SKILLS:
            skill_def = skills[skill_name]
            meta = skill_def.metadata
            assert meta.name == skill_name
            assert meta.display_name, f"Missing display_name for {skill_name}"
            assert meta.description, f"Missing description for {skill_name}"


class TestDesktopNotifier:
    """Test desktop_notifier skill."""

    def test_toast_execution_dry_run(self, registry: SkillRegistry) -> None:
        result = registry.invoke_skill(
            "desktop_notifier",
            title="JARVIS Test",
            message="Verification Toast Alert",
            sound="Default",
        )
        assert result.success is True
        assert result.data["success"] is True
        assert "JARVIS Test" in str(result.data)


class TestSmartDownloads:
    """Test smart_downloads skill."""

    def test_downloads_categorization(self, registry: SkillRegistry, tmp_path: Path) -> None:
        doc_file = tmp_path / "report_2026.pdf"
        doc_file.write_text("dummy pdf content")
        img_file = tmp_path / "photo.png"
        img_file.write_text("dummy png")
        code_file = tmp_path / "script.py"
        code_file.write_text("print('hello')")

        result = registry.invoke_skill(
            "smart_downloads",
            directory=str(tmp_path),
            dry_run=False,
            notify=False,
            min_age_seconds=0.0,
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["total_files"] == 3
        assert (tmp_path / "Documents" / "report_2026.pdf").exists()
        assert (tmp_path / "Pictures" / "photo.png").exists()
        assert (tmp_path / "Code" / "script.py").exists()


class TestSmartRenamer:
    """Test smart_renamer skill."""

    def test_renamer_date_and_clean(self, registry: SkillRegistry, tmp_path: Path) -> None:
        messy_file = tmp_path / "download (1) [final].md"
        messy_file.write_text("# Bao Cao Tai Chinh Quy 4 2026\nNoi dung tong quan ve doanh thu va chi phi...")

        result = registry.invoke_skill(
            "smart_renamer",
            path=str(messy_file),
            auto_rename=True,
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["total_renamed"] == 1
        renamed_item = result.data["renamed"][0]
        assert "Bao_Cao" in renamed_item["new"] or "2026" in renamed_item["new"]


class TestUsbBackup:
    """Test usb_backup skill."""

    def test_usb_backup_to_custom_destination(self, registry: SkillRegistry, tmp_path: Path) -> None:
        src_dir = tmp_path / "my_project"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('source code')")

        backup_dest = tmp_path / "backup_storage"
        backup_dest.mkdir()

        result = registry.invoke_skill(
            "usb_backup",
            source=str(src_dir),
            target_drive=str(backup_dest),
            notify=False,
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["file_count"] == 1
        zip_path = Path(result.data["archive_path"])
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"


class TestDeepSearch:
    """Test deep_search skill."""

    def test_deep_search_synthesis(self, registry: SkillRegistry) -> None:
        result = registry.invoke_skill(
            "deep_search",
            query="Local LLM Inference Optimization",
            depth="fast",
            max_results=3,
            notify=False,
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["sources_count"] > 0
        assert len(result.data["citations"]) > 0


class TestSmartClipboard:
    """Test smart_clipboard skill."""

    def test_clipboard_json_formatter(self, registry: SkillRegistry) -> None:
        raw_json = '{"name":"jarvis","version":2,"status":"active"}'
        result = registry.invoke_skill(
            "smart_clipboard",
            content=raw_json,
            notify=False,
        )
        assert result.success is True
        assert result.data["detected_type"] == "json"
        assert result.data["success"] is True
        assert "{\n" in result.data["transformed"]

    def test_clipboard_url_utm_cleaner(self, registry: SkillRegistry) -> None:
        tracked_url = "https://example.com/product?id=123&utm_source=facebook&utm_medium=cpc&fbclid=abcdef"
        result = registry.invoke_skill(
            "smart_clipboard",
            content=tracked_url,
            notify=False,
        )
        assert result.success is True
        assert result.data["detected_type"] == "url"
        cleaned = result.data["transformed"]
        assert "utm_source" not in cleaned
        assert "fbclid" not in cleaned
        assert "id=123" in cleaned


class TestHealthTwin:
    """Test health_twin skill."""

    def test_biomarkers_analysis(self, registry: SkillRegistry) -> None:
        data = {
            "glucose": 6.8,  # High (> 5.5)
            "cholesterol": 6.2,  # High (> 5.2)
            "triglycerides": 1.2,  # Normal (0.4 - 1.7)
        }
        result = registry.invoke_skill(
            "health_twin",
            biomarkers=data,
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["total_evaluated"] == 3
        assert result.data["abnormal_count"] == 2


class TestContractScanner:
    """Test contract_scanner skill."""

    def test_contract_penalty_detection(self, registry: SkillRegistry) -> None:
        sample_contract = (
            "Bên B nếu vi phạm bất kỳ điều khoản nào sẽ bị phạt vi phạm 30% giá trị hợp đồng.\n"
            "Bên A có toàn quyền đơn phương chấm dứt hợp đồng bất cứ lúc nào mà không cần bồi thường.\n"
            "Hợp đồng này sẽ tự động gia hạn thêm 12 tháng nếu không có văn bản từ chối trước 60 ngày."
        )
        result = registry.invoke_skill(
            "contract_scanner",
            contract_text=sample_contract,
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["risk_level"] in ["HIGH", "CRITICAL"]
        assert len(result.data["findings"]) >= 2


class TestAnkiGenerator:
    """Test anki_generator skill."""

    def test_anki_card_extraction(self, registry: SkillRegistry, tmp_path: Path) -> None:
        study_text = (
            "REST API : Chuan kien truc giao tiep HTTP mang.\n"
            "GraphQL : Ngon ngu truy van du lieu manh me do Meta phat trien.\n"
        )
        dest_tsv = tmp_path / "flashcards.tsv"
        result = registry.invoke_skill(
            "anki_generator",
            text=study_text,
            deck_name="Computer Science",
            output_file=str(dest_tsv),
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["card_count"] >= 1
        assert dest_tsv.exists()


class TestPriceTracker:
    """Test price_tracker skill."""

    def test_price_tracker_add_and_list(self, registry: SkillRegistry) -> None:
        res_add = registry.invoke_skill(
            "price_tracker",
            action="add",
            name="Màn Hình Dell UltraSharp",
            url="https://tiki.vn/dell-u2723qe",
            target_price=10500000.0,
            initial_price=12000000.0,
        )
        assert res_add.success is True
        assert res_add.data["success"] is True

        res_list = registry.invoke_skill("price_tracker", action="list", notify=False)
        assert res_list.success is True
        assert res_list.data["success"] is True
        assert res_list.data["items_count"] >= 1


class TestVideoSummarizer:
    """Test video_summarizer skill."""

    def test_video_summarizer_text(self, registry: SkillRegistry, tmp_path: Path) -> None:
        sample_transcript = (
            "Hôm nay chúng ta tìm hiểu về kiến trúc RAG cục bộ. "
            "RAG giúp kết hợp mô hình ngôn ngữ lớn với cơ sở dữ liệu vector cá nhân. "
            "Nhờ đó phản hồi luôn chính xác và không sợ rò rỉ dữ liệu lên máy chủ công cộng."
        )
        result = registry.invoke_skill(
            "video_summarizer",
            input_text=sample_transcript,
            title="Kiến Trúc RAG",
            export_markdown=True,
            output_dir=str(tmp_path),
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["exported_file"] is not None
        assert Path(result.data["exported_file"]).exists()


class TestCommandPalette:
    """Test command_palette skill."""

    def test_palette_search(self, registry: SkillRegistry) -> None:
        result = registry.invoke_skill(
            "command_palette",
            query="usb",
        )
        assert result.success is True
        assert result.data["success"] is True
        assert result.data["total_matches"] >= 1
        matched_ids = [cmd["id"] for cmd in result.data["commands"]]
        assert "backup_usb" in matched_ids


class TestCodeArchaeologist:
    """Test code_archaeologist skill."""

    def test_ast_file_analysis(self, registry: SkillRegistry, tmp_path: Path) -> None:
        py_file = tmp_path / "sample_service.py"
        py_file.write_text(
            '"""Sample test module."""\n\n'
            'class Worker:\n'
            '    """Worker doc."""\n'
            '    def run(self, count: int) -> int:\n'
            '        total = 0\n'
            '        for i in range(count):\n'
            '            if i % 2 == 0:\n'
            '                total += i\n'
            '            else:\n'
            '                total -= 1\n'
            '        return total\n'
        )

        result = registry.invoke_skill(
            "code_archaeologist",
            target_path=str(py_file),
        )
        assert result.success is True
        assert result.data["success"] is True
        file_info = result.data["file_info"]
        assert file_info["loc"] >= 10
        assert len(file_info["classes"]) == 1
        assert len(file_info["functions"]) == 1
        func = file_info["functions"][0]
        assert func["name"] == "run"
        assert func["complexity"] >= 3
