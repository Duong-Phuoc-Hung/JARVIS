"""
tests/unit/test_hud_telemetry_and_memory.py
============================================
Comprehensive Unit & Integration Test Suite for HUD Telemetry & Memory Layer (Requirement R6).
Covers:
- AlwaysOnOverlay HUD state machine (IDLE, LISTENING, THINKING, RESPONSE, HIDDEN).
- AlwaysOnOverlay Sidebar docking, 5-turn history queue, telemetry updates, waveform bars.
- AlwaysOnOverlay Task DAG telemetry (`update_task_dag`), live code streaming (`append_code_log`), visual result cards (`display_visual_result`).
- Headless CI/CD tolerance and thread-safe UI scheduling.
- SQLiteMemoryStore WAL mode (PRAGMA journal_mode = WAL) verification.
- Facts UPSERT, categories, access counting, and deletion.
- Episodic interaction logging and daily activity summaries.
- User habits tracking and frequency aggregation.
- Task DAG execution history (`record_task_execution`, `get_task_history`, `get_task`).
- Browser session persistence (`save_browser_session`, `get_browser_session`, `list_browser_sessions`, `delete_browser_session`).
- Learned reusable workflows (`save_learned_workflow`, `get_learned_workflows`, `increment_workflow_usage`).
- Master MemoryManager orchestration & prompt context injection.
- JarvisApp autonomous subsystem bootstrapping & action dispatcher registration.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch

from jarvis.browser.session import BrowserSessionManager
from jarvis.core.app import JarvisApp
from jarvis.core.models import RequesterContext
from jarvis.memory.manager import MemoryManager
from jarvis.memory.session import ConversationTurn, SessionContextManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore
from jarvis.ui.overlay import (
    AlwaysOnOverlay,
    BREATHING_GRADIENT,
    COLORS,
    OverlayMode,
    OverlayState,
    TurnRecord,
)


class TestAlwaysOnOverlayHUD(unittest.TestCase):
    """Tests covering HUD Overlay state transitions, history, and telemetry."""

    def setUp(self) -> None:
        self.overlay = AlwaysOnOverlay(
            width=380,
            height=680,
            sidebar_mode=True,
            headless=True,
        )
        self.overlay.start()

    def tearDown(self) -> None:
        self.overlay.destroy()

    def test_overlay_initial_state_and_properties(self) -> None:
        self.assertTrue(self.overlay.is_headless)
        self.assertEqual(self.overlay.state, OverlayState.IDLE)
        self.assertEqual(self.overlay.mode, OverlayMode.SIDEBAR)
        self.assertTrue(self.overlay.is_sidebar_mode)
        self.assertFalse(self.overlay.is_collapsed)
        self.assertFalse(self.overlay.is_minimized)

    def test_overlay_state_transitions(self) -> None:
        # Show listening state
        self.overlay.show_listening(hint="Đang lắng nghe...")
        self.assertEqual(self.overlay.state, OverlayState.LISTENING)
        self.assertTrue(self.overlay.is_visible)
        self.assertEqual(self.overlay.hint_text, "Đang lắng nghe...")

        # Show thinking state
        self.overlay.show_thinking(user_text="Thời tiết hôm nay thế nào?")
        self.assertEqual(self.overlay.state, OverlayState.THINKING)
        self.assertEqual(self.overlay.user_text, "Thời tiết hôm nay thế nào?")

        # Show response state
        self.overlay.show_response(
            jarvis_text="Hà Nội hôm nay trời nắng, nhiệt độ 28°C.",
            action="web_weather",
        )
        self.assertEqual(self.overlay.state, OverlayState.RESPONSE)
        self.assertEqual(self.overlay.jarvis_text, "Hà Nội hôm nay trời nắng, nhiệt độ 28°C.")

        # Hide overlay
        self.overlay.hide()
        self.assertEqual(self.overlay.state, OverlayState.HIDDEN)
        self.assertFalse(self.overlay.is_visible)

    def test_overlay_5_turn_history_queue(self) -> None:
        self.overlay.clear_history()
        self.assertEqual(len(self.overlay.get_history()), 0)

        # Add 6 turns -> only last 5 retained
        for i in range(1, 7):
            self.overlay.add_turn(
                user_text=f"Câu hỏi số {i}",
                jarvis_text=f"Câu trả lời số {i}",
                action=f"action_{i}",
            )

        history = self.overlay.get_history()
        self.assertEqual(len(history), 5)
        # Oldest turn 1 evicted, first element is turn 2
        self.assertEqual(history[0]["user_text"], "Câu hỏi số 2")
        self.assertEqual(history[-1]["user_text"], "Câu hỏi số 6")

    def test_overlay_telemetry_and_metrics_probing(self) -> None:
        metrics = self.overlay.update_telemetry(
            cpu_percent=32.5,
            ram_percent=64.0,
            battery_percent=85,
            is_charging=True,
        )
        self.assertEqual(metrics["cpu_percent"], 32.5)
        self.assertEqual(metrics["ram_percent"], 64.0)
        self.assertEqual(metrics["battery_percent"], 85)
        self.assertTrue(metrics["is_charging"])

        self.assertEqual(self.overlay.cpu_percent, 32.5)
        self.assertEqual(self.overlay.ram_percent, 64.0)
        self.assertEqual(self.overlay.battery_percent, 85)
        self.assertTrue(self.overlay.is_charging)

    def test_overlay_memory_facts_preview(self) -> None:
        facts = [
            "Chủ nhân: Hưng",
            "Dự án: JARVIS AI Autonomous Upgrade",
            "Sở thích: Lập trình hệ thống",
            "Thừa thãi: Mục này sẽ bị cắt",
        ]
        self.overlay.set_memory_facts(facts)
        preview = self.overlay.memory_facts
        self.assertEqual(len(preview), 3)
        self.assertEqual(preview[0], "Chủ nhân: Hưng")
        self.assertEqual(preview[1], "Dự án: JARVIS AI Autonomous Upgrade")
        self.assertEqual(preview[2], "Sở thích: Lập trình hệ thống")

    def test_overlay_quick_action_registration_and_trigger(self) -> None:
        executed_action = None

        def sample_action():
            nonlocal executed_action
            executed_action = "focus_mode_activated"
            return True

        self.overlay.register_action_callback("btn_focus", sample_action)
        res = self.overlay.trigger_quick_action("btn_focus")
        self.assertTrue(res)
        self.assertEqual(executed_action, "focus_mode_activated")

    def test_overlay_waveform_spectrum_update(self) -> None:
        self.overlay.update_audio_level(0.75)
        bars = self.overlay.waveform_bars
        self.assertEqual(len(bars), 11)
        self.assertTrue(all(0.0 <= b <= 1.0 for b in bars))

    def test_overlay_task_dag_telemetry(self) -> None:
        """Verify Task DAG telemetry ingestion and accessors."""
        dag_data = {
            "plan_id": "plan_1001",
            "goal": "Tổng hợp báo cáo tài chính",
            "nodes": [
                {"step_id": "s1", "action_name": "file_search", "status": "completed"},
                {"step_id": "s2", "action_name": "sandbox_python_exec", "status": "running"},
            ],
        }
        self.overlay.update_task_dag(dag_data)
        current = self.overlay.current_dag
        self.assertIsNotNone(current)
        self.assertEqual(current["plan_id"], "plan_1001")
        self.assertEqual(current["goal"], "Tổng hợp báo cáo tài chính")
        self.assertEqual(len(current["nodes"]), 2)

    def test_overlay_code_log_streaming(self) -> None:
        """Verify live code log streaming to HUD overlay."""
        self.overlay.clear_code_logs()
        self.assertEqual(len(self.overlay.code_logs), 0)

        self.overlay.append_code_log("import pandas as pd", "stdout")
        self.overlay.append_code_log("Processing 500 rows...", "stdout")
        self.overlay.append_code_log("Warning: Deprecated API", "stderr")

        logs = self.overlay.code_logs
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0]["text"], "import pandas as pd")
        self.assertEqual(logs[0]["stream"], "stdout")
        self.assertEqual(logs[2]["text"], "Warning: Deprecated API")
        self.assertEqual(logs[2]["stream"], "stderr")

    def test_overlay_visual_result_display(self) -> None:
        """Verify visual verification result cards."""
        self.overlay.clear_visual_results()
        self.assertEqual(len(self.overlay.visual_results), 0)

        res_info = {
            "title": "Visual State Check",
            "diff_percent": 12.5,
            "description": "Button clicked and dialog closed.",
        }
        self.overlay.display_visual_result(res_info)
        results = self.overlay.visual_results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Visual State Check")
        self.assertEqual(results[0]["diff_percent"], 12.5)
        self.assertEqual(self.overlay.latest_visual_result["title"], "Visual State Check")


class TestSQLiteMemoryStore(unittest.TestCase):
    """Tests covering SQLiteMemoryStore WAL mode, facts, episodes, habits, tasks, and browser sessions."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.db"
        self.store = SQLiteMemoryStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_sqlite_wal_mode_enabled(self) -> None:
        mode = self.store.get_journal_mode()
        self.assertEqual(mode, "wal")

    def test_facts_upsert_and_access_counting(self) -> None:
        ok = self.store.store_fact(
            key="user_name",
            value="Hưng",
            category="profile",
            confidence=1.0,
        )
        self.assertTrue(ok)

        fact = self.store.get_fact("user_name", category="profile")
        self.assertIsNotNone(fact)
        self.assertEqual(fact["value"], "Hưng")
        self.assertEqual(fact["access_count"], 1)

        fact2 = self.store.get_fact("user_name", category="profile")
        self.assertEqual(fact2["access_count"], 2)

        ok2 = self.store.store_fact(
            key="user_name",
            value="Dương Phước Hưng",
            category="profile",
        )
        self.assertTrue(ok2)

        fact_updated = self.store.get_fact("user_name", category="profile")
        self.assertEqual(fact_updated["value"], "Dương Phước Hưng")

    def test_facts_listing_and_deletion(self) -> None:
        self.store.store_fact("ide", "Cursor IDE", category="preference")
        self.store.store_fact("lang", "Python & Rust", category="preference")
        self.store.store_fact("project", "JARVIS", category="project")

        pref_facts = self.store.list_facts(category="preference")
        self.assertEqual(len(pref_facts), 2)

        all_facts = self.store.list_facts()
        self.assertEqual(len(all_facts), 3)

        deleted = self.store.delete_fact("ide", category="preference")
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_fact("ide", category="preference"))

    def test_episodic_log_and_query(self) -> None:
        ep_id = self.store.log_episode(
            command="mở trình duyệt và tìm tài liệu python",
            intent="web_search",
            outcome="Đã mở trình duyệt và hiển thị tài liệu",
            success=True,
            latency_ms=120.5,
            metadata={"browser": "playwright", "query": "python documentation"},
        )
        self.assertGreater(ep_id, 0)

        episodes = self.store.get_episodes(limit=10)
        self.assertGreaterEqual(len(episodes), 1)
        latest = episodes[0]
        self.assertEqual(latest["command"], "mở trình duyệt và tìm tài liệu python")
        self.assertEqual(latest["intent"], "web_search")
        self.assertEqual(latest["success"], 1)

        today_eps = self.store.get_today_episodes()
        self.assertGreaterEqual(len(today_eps), 1)

    def test_user_habits_recording(self) -> None:
        self.store.record_habit("morning_briefing_request", habit_type="routine", typical_hour=8)
        self.store.record_habit("morning_briefing_request", habit_type="routine", typical_hour=8)

        habits = self.store.get_habits()
        self.assertEqual(len(habits), 1)
        self.assertEqual(habits[0]["habit_key"], "morning_briefing_request")
        self.assertEqual(habits[0]["frequency"], 2)
        self.assertEqual(habits[0]["typical_hour"], 8)

    def test_task_history_storage_and_query(self) -> None:
        """Verify task_history table CRUD and status queries."""
        dag = {
            "plan_id": "plan_99",
            "nodes": [{"step_id": "s1", "action_name": "file_search"}],
        }
        trace = [{"step_id": "s1", "success": True}]
        ok = self.store.record_task_execution(
            task_id="plan_99",
            goal="Tìm tệp cấu hình",
            dag_json=dag,
            execution_trace=trace,
            status="completed",
            duration=1.45,
        )
        self.assertTrue(ok)

        task = self.store.get_task("plan_99")
        self.assertIsNotNone(task)
        self.assertEqual(task["goal"], "Tìm tệp cấu hình")
        self.assertEqual(task["status"], "completed")
        self.assertAlmostEqual(task["duration_seconds"], 1.45, places=2)

        history = self.store.get_task_history(status="completed")
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["task_id"], "plan_99")

    def test_browser_sessions_storage_and_query(self) -> None:
        """Verify browser_sessions table operations."""
        cookies = [{"name": "session_id", "value": "abc123xyz", "domain": "github.com"}]
        storage = {"theme": "dark", "sidebar_pinned": "true"}

        ok = self.store.save_browser_session(
            domain="https://github.com/settings",
            cookies=cookies,
            storage=storage,
            user_agent="JARVIS-Browser/2.0",
        )
        self.assertTrue(ok)

        session = self.store.get_browser_session("github.com")
        self.assertIsNotNone(session)
        self.assertEqual(session["domain"], "github.com")
        self.assertEqual(session["cookies"][0]["name"], "session_id")
        self.assertEqual(session["local_storage"]["theme"], "dark")
        self.assertEqual(session["user_agent"], "JARVIS-Browser/2.0")

        all_domains = self.store.list_browser_sessions()
        self.assertIn("github.com", all_domains)

        deleted = self.store.delete_browser_session("github.com")
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_browser_session("github.com"))

    def test_learned_workflows_storage_and_query(self) -> None:
        """Verify learned_workflows table operations."""
        steps = [
            {"step": 1, "action": "browser_scrape", "url": "https://news.ycombinator.com"},
            {"step": 2, "action": "sandbox_execute_code", "script": "summarize()"},
        ]
        ok = self.store.save_learned_workflow(
            workflow_id="wf_daily_tech_summary",
            name="Daily Tech News Summarizer",
            description="Scrapes HN and summarizes top stories",
            trigger_pattern="tóm tắt tin tức công nghệ hàng ngày",
            steps_template=steps,
        )
        self.assertTrue(ok)

        wf = self.store.get_learned_workflow("wf_daily_tech_summary")
        self.assertIsNotNone(wf)
        self.assertEqual(wf["name"], "Daily Tech News Summarizer")
        self.assertEqual(wf["usage_count"], 1)

        # Increment usage
        inc_ok = self.store.increment_workflow_usage("wf_daily_tech_summary")
        self.assertTrue(inc_ok)
        wf_updated = self.store.get_learned_workflow("wf_daily_tech_summary")
        self.assertEqual(wf_updated["usage_count"], 2)

        workflows = self.store.get_learned_workflows()
        self.assertGreaterEqual(len(workflows), 1)


class TestMemoryManagerAndPromptInjection(unittest.TestCase):
    """Tests covering master MemoryManager, conversation turns, and system prompt injection."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.db"
        self.manager = MemoryManager(db_path=self.db_path, max_session_turns=5)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_session_sliding_buffer_and_formatting(self) -> None:
        self.manager.add_session_turn("user", "Xin chào JARVIS")
        self.manager.add_session_turn("assistant", "Chào Ngài Hưng, tôi có thể giúp gì cho Ngài?")
        self.manager.add_session_turn("user", "Tôi muốn lập kế hoạch tự trị")

        history = self.manager.get_session_history()
        self.assertEqual(len(history), 3)

        context_str = self.manager.get_session_context()
        self.assertIn("user: Xin chào JARVIS", context_str)
        self.assertIn("assistant: Chào Ngài Hưng", context_str)
        self.assertIn("user: Tôi muốn lập kế hoạch tự trị", context_str)

    def test_handle_vietnamese_remember_command(self) -> None:
        resp = self.manager.handle_remember_command("nhớ rằng tôi rất thích uống cà phê đen không đường")
        self.assertIn("đã ghi nhớ", resp.lower())

        fact = self.manager.store.get_fact("sở thích cà phê", category="preference") or self.manager.store.list_facts()
        self.assertGreater(len(fact), 0)

    def test_handle_today_activity_summary(self) -> None:
        self.manager.store.log_episode(
            command="chạy phân tích dữ liệu doanh thu",
            intent="sandbox_code",
            outcome="Đã tạo file revenue_report.xlsx",
            success=True,
        )
        summary = self.manager.handle_today_summary()
        self.assertIn("hôm nay", summary.lower())
        self.assertIn("chạy phân tích dữ liệu doanh thu", summary)

    def test_system_prompt_memory_context_injection(self) -> None:
        self.manager.store_fact("owner_name", "Dương Phước Hưng", category="profile")
        self.manager.store_fact("current_goal", "JARVIS Autonomous Superpower", category="project")
        self.manager.add_session_turn("user", "Bắt đầu bài kiểm tra hệ thống")

        prompt_context = self.manager.get_system_prompt_context()
        self.assertIn("Dương Phước Hưng", prompt_context)
        self.assertIn("JARVIS Autonomous Superpower", prompt_context)
        self.assertIn("Bắt đầu bài kiểm tra hệ thống", prompt_context)


class TestJarvisAppAutonomousIntegration(unittest.TestCase):
    """Tests covering JarvisApp initialization of all 6 autonomous subsystems and action routing."""

    def setUp(self) -> None:
        self.app = JarvisApp(headless=True, no_hot_reload=True)
        self.app.initialize()

    def tearDown(self) -> None:
        self.app.stop()

    def test_app_initializes_all_autonomous_subsystems(self) -> None:
        """Verify all new subsystems are bootstrapped in JarvisApp."""
        self.assertIsNotNone(self.app.planner_engine)
        self.assertIsNotNone(self.app.sandbox)
        self.assertIsNotNone(self.app.skill_registry)
        self.assertIsNotNone(self.app.skill_synthesizer)
        self.assertIsNotNone(self.app.browser_agent)
        self.assertIsNotNone(self.app.computer_use_vision)
        self.assertIsNotNone(self.app.gui_actor)
        self.assertIsNotNone(self.app.subagent_manager)

    def test_app_registers_autonomous_actions(self) -> None:
        """Verify all required autonomous actions are registered in ActionDispatcher."""
        actions = self.app.dispatcher.list_actions()
        expected_actions = [
            "planner_execute_task",
            "subagent_spawn",
            "subagent_cancel",
            "subagent_status",
            "sandbox_execute_code",
            "skill_synthesize",
            "browser_navigate",
            "browser_scrape",
            "browser_fill_form",
            "vision_click_ui",
            "vision_type_ui",
            "vision_verify_state",
        ]
        for act in expected_actions:
            self.assertIn(act, actions, f"Action {act} must be registered in ActionDispatcher")

    def test_app_sandbox_action_dispatch(self) -> None:
        """Verify sandbox_execute_code action runs Python and returns stdout/data."""
        res = self.app.dispatcher.dispatch_action(
            action_name="sandbox_execute_code",
            payload={"code": "x = 40 + 2\nprint(f'ANSWER:{x}')", "language": "python"},
        )
        self.assertTrue(res.success)
        self.assertIn("ANSWER:42", res.data["stdout"])

    def test_app_planner_action_dispatch(self) -> None:
        """Verify planner_execute_task action creates and executes plan."""
        res = self.app.dispatcher.dispatch_action(
            action_name="planner_execute_task",
            payload={"goal": "Kiểm tra hệ thống tự trị", "mode": "fully_autonomous"},
        )
        self.assertTrue(res.success)
        self.assertIn("plan_id", res.data)
        self.assertTrue(res.data["success"])


if __name__ == "__main__":
    unittest.main()
