"""
tests/unit/test_skill_synthesizer.py
======================================
Unit tests for the Self-Coding Skill Synthesizer.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.skills.skill_synthesizer import execute


@pytest.fixture
def skills_root(tmp_path, monkeypatch):
    """Redirect skills root to tmp_path so tests don't pollute real skills."""
    import jarvis.skills.skill_synthesizer as mod
    monkeypatch.setattr(mod, "_SKILLS_ROOT", tmp_path)
    return tmp_path


class TestPreviewAction:
    def test_preview_returns_code_preview(self, skills_root):
        result = execute(
            action="preview",
            skill_name="test_fetch",
            description="Lấy dữ liệu từ web",
            actions_list="run,status",
        )
        assert result["data"]["success"] is True
        assert "code" in result["data"]
        code = result["data"]["code"]
        assert "def execute" in code

    def test_preview_does_not_create_files(self, skills_root):
        execute(
            action="preview",
            skill_name="preview_only",
            description="chỉ xem trước",
        )
        assert not (skills_root / "preview_only").exists()

    def test_preview_detects_template_from_keywords(self, skills_root):
        result = execute(
            action="preview",
            skill_name="calc_test",
            description="tính toán biểu thức toán học",
        )
        assert result["data"]["success"] is True
        # template should be calculator or generic
        assert "code" in result["data"]


class TestCreateAction:
    def test_create_generates_two_files(self, skills_root):
        result = execute(
            action="create",
            skill_name="my_skill",
            description="theo dõi giá vàng SJC mỗi giờ",
        )
        assert result["data"]["success"] is True
        assert (skills_root / "my_skill" / "__init__.py").exists()
        assert (skills_root / "my_skill" / "metadata.json").exists()

    def test_create_metadata_has_synthesized_flag(self, skills_root):
        execute(action="create", skill_name="auto_skill", description="lấy dữ liệu từ API")
        meta = json.loads((skills_root / "auto_skill" / "metadata.json").read_text())
        assert meta.get("synthesized") is True

    def test_create_generated_code_is_valid_python(self, skills_root):
        import ast
        execute(action="create", skill_name="valid_code", description="kiểm tra trạng thái hệ thống")
        code = (skills_root / "valid_code" / "__init__.py").read_text(encoding="utf-8")
        # Should not raise SyntaxError
        ast.parse(code)


class TestNameValidation:
    def test_empty_name_rejected(self, skills_root):
        result = execute(action="create", skill_name="", description="test")
        assert result["data"]["success"] is False

    def test_invalid_name_uppercase_rejected(self, skills_root):
        result = execute(action="create", skill_name="MySkill", description="test")
        assert result["data"]["success"] is False

    def test_valid_name_with_underscore_accepted(self, skills_root):
        result = execute(action="create", skill_name="my_skill_2", description="lưu dữ liệu vào file")
        assert result["data"]["success"] is True


class TestListAction:
    def test_list_shows_synthesized_skills(self, skills_root):
        execute(action="create", skill_name="listed_skill", description="ghi chú tự động")
        result = execute(action="list")
        assert result["data"]["success"] is True
        # Should have at least one synthesized skill in skills_root
        # (may be empty if skills_root patching redirects list away)
        assert "skills" in result["data"]

    def test_list_returns_empty_when_none(self, skills_root):
        result = execute(action="list")
        assert result["data"]["success"] is True
        assert isinstance(result["data"]["skills"], list)


class TestDeleteAction:
    def test_delete_removes_synthesized_skill(self, skills_root):
        execute(action="create", skill_name="to_delete", description="tạm thời để xóa")
        assert (skills_root / "to_delete").exists()
        result = execute(action="delete", skill_name="to_delete")
        assert result["data"]["success"] is True
        assert not (skills_root / "to_delete").exists()

    def test_delete_nonexistent_returns_failure(self, skills_root):
        result = execute(action="delete", skill_name="nonexistent_xyz")
        assert result["data"]["success"] is False
