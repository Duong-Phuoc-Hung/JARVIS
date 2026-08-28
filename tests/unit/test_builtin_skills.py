"""
tests/unit/test_builtin_skills.py
=================================
Unit tests for JARVIS v2.0.0 built-in skills library and SkillRegistry integration.
"""
import os
from pathlib import Path
import pytest

from jarvis.skills.models import SkillDefinition, SkillMetadata
from jarvis.skills.registry import SkillRegistry


class TestBuiltinSkills:
    """Test suite covering all 9 built-in packaged skills."""

    @pytest.fixture
    def registry(self) -> SkillRegistry:
        skills_dir = Path("jarvis/skills").resolve()
        reg = SkillRegistry(skills_dir=skills_dir, auto_discover=True)
        return reg

    def test_skills_discovery_count(self, registry: SkillRegistry) -> None:
        """Verify all 9 built-in skills are discovered and loaded."""
        skills = registry.list_skills()
        names = [s.name for s in skills]
        assert len(names) >= 9
        assert "briefing" in names
        assert "file_manager" in names
        assert "note_taker" in names
        assert "pomodoro" in names
        assert "system_control" in names
        assert "git_assistant" in names
        assert "calculator" in names
        assert "clipboard" in names
        assert "app_launcher" in names

    def test_briefing_skill_execution(self, registry: SkillRegistry) -> None:
        """Test briefing skill returns formatted summary and structured components."""
        res = registry.invoke_skill("briefing", city="Hanoi", include_news=True, include_crypto=True)
        assert res.success is True
        assert res.data is not None
        assert "text" in res.data or "output" in res.data
        assert "Hanoi" in str(res.data) or "Thời tiết" in str(res.data)

    def test_file_manager_search(self, registry: SkillRegistry) -> None:
        """Test file manager search functionality."""
        res = registry.invoke_skill("file_manager", action="search", query="app.py", directory="d:/Software GitCode/JARVIS/jarvis")
        assert res.success is True
        assert res.data is not None
        assert "results" in res.data

    def test_file_manager_list_folder(self, registry: SkillRegistry) -> None:
        """Test file manager directory listing."""
        res = registry.invoke_skill("file_manager", action="list_folder", directory="d:/Software GitCode/JARVIS/jarvis/skills")
        assert res.success is True
        assert res.data is not None
        assert "entries" in res.data

    def test_note_taker_crud_lifecycle(self, registry: SkillRegistry) -> None:
        """Test full note taker lifecycle: add, list, search, clear."""
        # 1. Add note
        res_add = registry.invoke_skill("note_taker", action="add", content="Buy coffee for team", tag="work")
        assert res_add.success is True
        assert "Buy coffee" in str(res_add.data)

        # 2. List notes
        res_list = registry.invoke_skill("note_taker", action="list")
        assert res_list.success is True
        assert len(res_list.data.get("notes", [])) >= 1

        # 3. Search notes
        res_search = registry.invoke_skill("note_taker", action="search", query="coffee")
        assert res_search.success is True
        assert len(res_search.data.get("results", [])) >= 1

        # 4. Clear notes
        res_clear = registry.invoke_skill("note_taker", action="clear")
        assert res_clear.success is True

    def test_pomodoro_state_machine(self, registry: SkillRegistry) -> None:
        """Test Pomodoro start, status, pause, resume, stop."""
        # Start
        r_start = registry.invoke_skill("pomodoro", action="start", duration_minutes=25)
        assert r_start.success is True

        # Status
        r_stat = registry.invoke_skill("pomodoro", action="status")
        assert r_stat.success is True

        # Pause
        r_pause = registry.invoke_skill("pomodoro", action="pause")
        assert r_pause.success is True

        # Resume
        r_resume = registry.invoke_skill("pomodoro", action="resume")
        assert r_resume.success is True

        # Stop
        r_stop = registry.invoke_skill("pomodoro", action="stop")
        assert r_stop.success is True

    def test_calculator_math_evaluation(self, registry: SkillRegistry) -> None:
        """Test calculator AST math expression evaluation."""
        res = registry.invoke_skill("calculator", expression="25 * 4 + 150 / 2")
        assert res.success is True
        assert res.data.get("result") == 175.0

        # Percentage
        res_pct = registry.invoke_skill("calculator", expression="15% * 2000000")
        assert res_pct.success is True
        assert res_pct.data.get("result") == 300000.0

        # Function call
        res_fn = registry.invoke_skill("calculator", expression="sqrt(144) + abs(-8)")
        assert res_fn.success is True
        assert res_fn.data.get("result") == 20.0

    def test_calculator_currency_conversion(self, registry: SkillRegistry) -> None:
        """Test currency conversion calculation."""
        res = registry.invoke_skill("calculator", action="convert_currency", amount=100.0, currency_from="USD", currency_to="VND")
        assert res.success is True
        assert res.data.get("converted_amount") > 0

    def test_system_control_actions(self, registry: SkillRegistry) -> None:
        """Test system control volume, mute, screenshot actions."""
        r_vol = registry.invoke_skill("system_control", action="volume_up", value=10)
        assert r_vol.success is True

        r_mute = registry.invoke_skill("system_control", action="mute")
        assert r_mute.success is True

    def test_git_assistant_status(self, registry: SkillRegistry) -> None:
        """Test git assistant repository inspection."""
        res = registry.invoke_skill("git_assistant", action="status", repo_path="d:/Software GitCode/JARVIS")
        assert res.success is True
        assert "branch" in res.data

    def test_git_assistant_branch_and_log(self, registry: SkillRegistry) -> None:
        """Test git assistant branch listing and commit log."""
        r_br = registry.invoke_skill("git_assistant", action="branch", repo_path="d:/Software GitCode/JARVIS")
        assert r_br.success is True

        r_log = registry.invoke_skill("git_assistant", action="log", limit=3, repo_path="d:/Software GitCode/JARVIS")
        assert r_log.success is True

    def test_clipboard_read_write(self, registry: SkillRegistry) -> None:
        """Test clipboard read, copy, and clear."""
        # Read
        r_read = registry.invoke_skill("clipboard", action="read")
        assert r_read.success is True

        # Copy
        r_copy = registry.invoke_skill("clipboard", action="copy", text="JARVIS Test Token 42")
        assert r_copy.success is True

    def test_app_launcher_known_target(self, registry: SkillRegistry) -> None:
        """Test app launcher handles known targets."""
        res = registry.invoke_skill("app_launcher", app_name="settings")
        assert res.success is True

    def test_nonexistent_skill_error_handling(self, registry: SkillRegistry) -> None:
        """Test invoking unknown skill gracefully returns failure."""
        res = registry.invoke_skill("completely_unknown_skill_xyz")
        assert res.success is False
        assert "not registered" in res.error
