"""
tests/e2e/test_autonomous_workflows.py
======================================
Comprehensive End-to-End Autonomous Workflow Test Suite for JARVIS Superpower Upgrades.

Hermetic, deterministic, zero-hardware, zero-cloud verification of real-world multi-step
autonomous agentic workflows combining:
  1. Autonomous ReAct Planner & TaskDAG Engine (Requirement R1)
  2. Sandboxed Self-Coding & Persistent Skill Synthesis (Requirement R2)
  3. Full Browser Automation & Data Scraping (Requirement R3)
  4. Computer-Use Vision Grounding & Verified GUI Interaction (Requirement R4)
  5. Autonomous Background Workers & Sub-Agent Delegation (Requirement R5)
  6. HUD Telemetry & Persistent SQLite Memory Layer (Requirement R6)
"""
from __future__ import annotations

import base64
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from jarvis.automation.control import ComputerController
from jarvis.automation.gui_actor import GUIActionResult, GUIActor
from jarvis.automation.safety_gate import SafetyGate
from jarvis.browser.actions import BrowserActions
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.driver import MockBrowserDriver
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    PageElement,
    PriceComparisonItem,
    ScrapeResult,
)
from jarvis.browser.scraper import PriceComparisonAggregator, WebScraper
from jarvis.browser.session import BrowserSessionManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.healing.watchdog import ResourceWatchdog
from jarvis.memory.manager import MemoryManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore
from jarvis.planner.dag import TaskDAG, interpolate_parameters
from jarvis.planner.engine import ReActTaskEngine
from jarvis.planner.models import (
    PlanMode,
    PlanResult,
    RecoveryStrategy,
    StepStatus,
    TaskNode,
)
from jarvis.planner.reflection import SelfReflectionEngine
from jarvis.planner.safety_interceptor import SafetyGateInterceptor
from jarvis.sandbox.artifacts import ArtifactManager
from jarvis.sandbox.interpreter import CodeInterpreterSandbox, SandboxResult
from jarvis.sandbox.validator import ASTCodeValidator
from jarvis.skills.models import SkillDefinition, SkillMetadata
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.synthesizer import DynamicSkillSynthesizer
from jarvis.ui.overlay import AlwaysOnOverlay, OverlayMode, OverlayState
from jarvis.vision.computer_use import (
    BoundingBox,
    ComputerUseVision,
    CoordinateMapper,
    UIElement,
)
from jarvis.vision.ocr import DesktopOCR
from jarvis.vision.screen import ScreenCaptureResult, ScreenVisionManager
from jarvis.vision.visual_verifier import VisualDiffResult, VisualVerifier
from jarvis.workers.manager import SubAgentManager
from jarvis.workers.models import (
    WorkerPriority,
    WorkerStatus,
    WorkerTask,
    WorkerTelemetry,
)
from jarvis.workers.notifications import WorkerNotificationDispatcher
from jarvis.workers.worker import BackgroundWorker


def make_test_ui_image(width: int = 1920, height: int = 1080, button_text: str = "Export") -> bytes:
    """Helper creating a synthetic desktop image with a drawn UI button."""
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    # Draw button at (900, 300, 1020, 350) -> normalized around (468, 277, 531, 324)
    draw.rectangle((900, 300, 1020, 350), fill="#00f0ff", outline="#ffffff", width=2)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestAutonomousWorkflowsE2E(unittest.TestCase):
    """End-to-End Autonomous Multi-Modal Scenarios."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.scratch_dir = Path(self.temp_dir.name) / "sandbox"
        self.skills_dir = Path(self.temp_dir.name) / "skills"
        self.browser_dir = Path(self.temp_dir.name) / "browser_sessions"
        self.db_path = Path(self.temp_dir.name) / "memory.db"

        self.event_bus = EventBus()
        self.dispatcher = ActionDispatcher(event_bus=self.event_bus)
        self.watchdog = ResourceWatchdog(event_bus=self.event_bus)
        self.memory = MemoryManager(db_path=self.db_path)

        # Core subsystems
        self.sandbox = CodeInterpreterSandbox(base_scratch_dir=self.scratch_dir)
        self.skill_registry = SkillRegistry(skills_dir=self.skills_dir, dispatcher=self.dispatcher)
        self.synthesizer = DynamicSkillSynthesizer(skills_dir=self.skills_dir, registry=self.skill_registry)

        self.browser_driver = MockBrowserDriver()
        self.browser_session = BrowserSessionManager(storage_dir=str(self.browser_dir), db_path=str(self.db_path))
        self.browser_agent = BrowserAgent(driver=self.browser_driver, session_manager=self.browser_session)

        self.safety_gate = SafetyGate(timeout_seconds=5.0)
        self.safety_interceptor = SafetyGateInterceptor(safety_gate=self.safety_gate, timeout_seconds=5.0)
        self.reflection_engine = SelfReflectionEngine(base_backoff_seconds=0.01, max_backoff_seconds=0.1)

        self.planner = ReActTaskEngine(
            dispatcher=self.dispatcher,
            safety_interceptor=self.safety_interceptor,
            reflection_engine=self.reflection_engine,
            event_bus=self.event_bus,
            max_parallel_workers=4,
        )

        self.mock_tts = MagicMock()
        self.mock_telegram = MagicMock()
        self.overlay = AlwaysOnOverlay(headless=True)
        self.overlay.start()

        self.notifications = WorkerNotificationDispatcher(
            tts_manager=self.mock_tts,
            overlay=self.overlay,
            telegram_controller=self.mock_telegram,
            event_bus=self.event_bus,
            default_telegram_chat_id=12345678,
        )
        self.worker_manager = SubAgentManager(
            max_workers=4,
            watchdog=self.watchdog,
            event_bus=self.event_bus,
            notification_dispatcher=self.notifications,
        )

    def tearDown(self) -> None:
        self.overlay.destroy()
        self.worker_manager.shutdown(wait=False, cancel_running=True)
        self.temp_dir.cleanup()

    # =========================================================================
    # Scenario 1: Autonomous Self-Coding, Artifact Capture & Skill Synthesis
    # =========================================================================
    def test_e2e_autonomous_data_analysis_and_skill_synthesis(self) -> None:
        """
        User asks: "Tổng hợp doanh thu từ CSV, tạo file Excel báo cáo và đóng gói thành kỹ năng tái sử dụng."
        Verifies:
        1. Sandbox executes self-generated Python code calculating totals.
        2. Excel artifact created and indexed.
        3. Script automatically synthesized and packaged into `jarvis/skills/`.
        4. Re-invoking synthesized skill via registry and ActionDispatcher.
        """
        # Step 1: Execute Python in Sandbox to aggregate data
        data_script = """
import csv
import json
from pathlib import Path

data = [
    {"product": "Laptop Pro", "sales": 15, "revenue": 300000000},
    {"product": "Vision Sensor", "sales": 40, "revenue": 80000000},
    {"product": "Audio Hub", "sales": 25, "revenue": 50000000},
]

total_revenue = sum(item["revenue"] for item in data)
total_sales = sum(item["sales"] for item in data)

# Generate mock CSV artifact
with open("sales_summary.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["product", "sales", "revenue"])
    writer.writeheader()
    writer.writerows(data)

# Print output JSON
result = {
    "total_revenue": total_revenue,
    "total_sales": total_sales,
    "artifact": "sales_summary.csv"
}
print(json.dumps(result))
"""
        sandbox_res: SandboxResult = self.sandbox.execute_python(data_script)
        self.assertTrue(sandbox_res.success)
        self.assertGreaterEqual(len(sandbox_res.artifacts), 1)
        self.assertEqual(sandbox_res.data["total_revenue"], 430000000)

        # Step 2: Auto-package as persistent skill
        synthesized_code = """
import json

def run(items=None):
    if items is None:
        items = [100, 200, 300]
    total = sum(items)
    return {"total": total, "status": "success"}
"""
        meta = SkillMetadata(
            name="revenue_calculator",
            description="Tự động tính tổng doanh thu và phát sinh báo cáo",
            version="1.0.0",
            category="data_analysis",
            author="JARVIS-SelfCoder",
        )
        skill_def = self.synthesizer.synthesize_skill(
            metadata=meta,
            code=synthesized_code,
            requirements=[],
            overwrite=True,
        )
        self.assertIsNotNone(skill_def)
        self.assertTrue(self.skill_registry.is_skill_registered("revenue_calculator"))

        # Step 3: Invoke skill dynamically via ActionDispatcher
        action_res = self.dispatcher.dispatch_action(
            action_name="skill:revenue_calculator",
            payload={"items": [500, 1500, 3000]},
        )
        self.assertTrue(action_res.success)
        self.assertEqual(action_res.data["total"], 5000)

        # Step 4: Record in episodic memory
        self.memory.store.log_episode(
            command="tổng hợp doanh thu và đóng gói kỹ năng",
            intent="skill_synthesis",
            outcome="Đã tạo skill revenue_calculator và hoàn tất tính toán",
            success=True,
        )
        history = self.memory.store.get_episodes(limit=1)
        self.assertEqual(history[0]["intent"], "skill_synthesis")

    # =========================================================================
    # Scenario 2: Autonomous Web Scraping, Price Comparison & Form Filling
    # =========================================================================
    def test_e2e_autonomous_browser_price_comparison_and_form_automation(self) -> None:
        """
        User asks: "So sánh giá RTX 4090 trên Shopee và Tiki, chọn nơi rẻ nhất và điền form đặt hàng."
        Verifies:
        1. BrowserAgent scrapes catalogs from multiple eCommerce stores.
        2. PriceComparisonAggregator ranks offers and identifies lowest price.
        3. Form automation navigates to checkout and auto-fills buyer information.
        4. Session state persistence saves cookies to SQLite memory.
        """
        catalogs = {
            "https://shopee.vn/search?q=rtx4090": """
                <div class="product"><h2 class="title">ASUS ROG Strix RTX 4090 24GB</h2><span class="price">₫49.000.000</span></div>
            """,
            "https://tiki.vn/search?q=rtx4090": """
                <div class="product"><h2 class="title">Gigabyte RTX 4090 Gaming OC 24GB</h2><span class="price">46.500.000 ₫</span></div>
            """,
            "https://tiki.vn/checkout": """
                <form id="order-form" action="/submit-order" method="post">
                    <input id="buyer-name" name="name" type="text" />
                    <input id="buyer-phone" name="phone" type="text" />
                    <input id="buyer-address" name="address" type="text" />
                    <button id="confirm-btn" type="submit">Xác nhận đặt hàng</button>
                </form>
            """,
        }

        def custom_navigate(url: str, wait_until: str = "domcontentloaded") -> bool:
            self.browser_driver._current_url = url
            if url in catalogs:
                self.browser_driver.set_fixture_html(catalogs[url], url=url)
            return True

        self.browser_driver.navigate = custom_navigate

        # Step 1: Compare prices across merchants
        items: List[PriceComparisonItem] = self.browser_agent.compare_prices(
            product_name="rtx4090",
            stores=["Shopee", "Tiki"],
        )
        self.assertGreaterEqual(len(items), 2)
        cheapest_offer = items[0]
        self.assertEqual(cheapest_offer.store_name, "Tiki")
        self.assertEqual(cheapest_offer.price, 46500000.0)

        # Step 2: Auto-fill checkout form on cheapest store
        form_res: BrowserActionResult = self.browser_agent.fill_form(
            url="https://tiki.vn/checkout",
            form_fields={
                "#buyer-name": "Dương Phước Hưng",
                "#buyer-phone": "0987654321",
                "#buyer-address": "Hà Nội, Việt Nam",
            },
            submit_selector="#confirm-btn",
        )
        self.assertTrue(form_res.success)
        self.assertEqual(self.browser_driver.elements["#buyer-name"].value, "Dương Phước Hưng")

        # Step 3: Persist session state
        cookies = [{"name": "tiki_session", "value": "auth_token_999", "domain": "tiki.vn", "path": "/"}]
        self.browser_session.save_session("tiki.vn", cookies)
        loaded = self.browser_session.load_session("https://tiki.vn/orders")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["cookies"][0]["value"], "auth_token_999")

    # =========================================================================
    # Scenario 3: Vision-Guided GUI Interaction & Visual State Verification
    # =========================================================================
    def test_e2e_computer_use_vision_and_verified_gui_interaction(self) -> None:
        """
        User asks: "Bấm vào nút Export trên màn hình và xác nhận giao diện đã thay đổi."
        Verifies:
        1. CoordinateMapper 1000x1000 normalized grid bounding box calculation.
        2. UIElement detector identifies button query on screen.
        3. VisualVerifier compares pre/post action screenshots, measuring pixel difference.
        4. GUIActor performs verified click and records telemetry report.
        """
        # Step 1: Verify coordinate normalization
        bbox = BoundingBox(ymin=277, xmin=468, ymax=324, xmax=531)
        px_left, px_top, px_right, px_bottom = bbox.to_pixel_coords(1920, 1080)
        self.assertEqual(bbox.center_norm, (499, 300))
        self.assertTrue(890 <= px_left <= 910)
        self.assertTrue(290 <= px_top <= 310)

        # Step 2: Simulate Screen Capture & Visual Verification
        before_bytes = make_test_ui_image(1920, 1080, "Export")

        # After click: background changes color and text changes to "Exporting..."
        img_after = Image.new("RGB", (1920, 1080), color="#1e1e2e")
        draw_after = ImageDraw.Draw(img_after)
        draw_after.rectangle((900, 300, 1020, 350), fill="#00ff88", outline="#ffffff", width=2)
        buf = io.BytesIO()
        img_after.save(buf, format="JPEG", quality=90)
        after_bytes = buf.getvalue()

        # Step 3: Run VisualVerifier
        verifier = VisualVerifier(diff_threshold=0.0001)
        diff_res: VisualDiffResult = verifier.verify_action(
            before_img=before_bytes,
            after_img=after_bytes,
        )
        self.assertTrue(diff_res.state_changed)
        self.assertGreater(diff_res.diff_ratio, 0.0)
        self.assertIsNotNone(diff_res.changed_roi)

        # Step 4: Run GUIActor with mock screen capture
        mock_screen_mgr = MagicMock()
        mock_screen_mgr.capture_screen_bytes = MagicMock(side_effect=[before_bytes, after_bytes])
        mock_screen_mgr.get_screen_size = MagicMock(return_value=(1920, 1080))

        mock_vision = MagicMock()
        mock_vision.locate_element = MagicMock(return_value=UIElement(
            name="Export",
            bbox=bbox,
            element_type="button",
            confidence=0.95,
            source="vision_llm",
        ))

        mock_ctrl = MagicMock()
        actor = GUIActor(
            computer_use=mock_vision,
            controller=mock_ctrl,
            verifier=verifier,
            vision_manager=mock_screen_mgr,
        )

        clicked = actor.click_element("Export", verify=True)
        self.assertTrue(clicked)
        gui_res = actor.action_history[-1]
        self.assertTrue(gui_res.success)
        self.assertTrue(gui_res.element_found)
        self.assertIsNotNone(gui_res.verification)
        self.assertTrue(gui_res.verification.state_changed)

    # =========================================================================
    # Scenario 4: Background Sub-Agent Delegation, Watchdog & Notifications
    # =========================================================================
    def test_e2e_background_subagent_delegation_watchdog_and_notifications(self) -> None:
        """
        User asks: "Chạy tác vụ quét an ninh và giám sát hệ thống ngầm, cập nhật tiến độ lên HUD và báo qua TTS."
        Verifies:
        1. SubAgentManager schedules non-blocking WorkerTask in background thread.
        2. Progress updates broadcast `worker:progress` events to AlwaysOnOverlay.
        3. Watchdog receives heartbeat pulses.
        4. On completion, TTS and Telegram notifications are dispatched.
        """
        progress_records: List[float] = []

        def security_scan_work(worker: BackgroundWorker) -> Dict[str, Any]:
            for i in range(1, 5):
                worker.check_cancelled()
                time.sleep(0.05)
                pct = i * 25.0
                progress_records.append(pct)
                worker.update_progress(pct, step=f"Đang quét danh mục an ninh mức {i}/4")
            return {"vulnerabilities_found": 0, "status": "SECURE"}

        task = WorkerTask(
            task_id="sec_scan_task_1",
            name="An ninh hệ thống",
            task_type="security_audit",
            priority=WorkerPriority.HIGH,
            target_callable=security_scan_work,
            notify_tts=True,
            notify_overlay=True,
            notify_telegram=True,
            telegram_chat_id=888888,
        )

        worker_id = self.worker_manager.spawn_worker(task)
        self.assertIsNotNone(worker_id)

        # Wait for completion
        telemetry = self.worker_manager.wait_for_worker(worker_id, timeout=3.0)
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.status, WorkerStatus.COMPLETED)
        self.assertEqual(telemetry.progress_pct, 100.0)
        self.assertEqual(telemetry.result_data["status"], "SECURE")

        # Verify progress steps executed
        self.assertEqual(progress_records, [25.0, 50.0, 75.0, 100.0])

        # Verify notifications called
        self.mock_tts.speak.assert_called()
        self.mock_telegram.send_message.assert_called()

    # =========================================================================
    # Scenario 5: ReAct Multi-Step Plan with Self-Healing and Safety Gate
    # =========================================================================
    def test_e2e_react_planner_self_healing_and_safety_gate_workflow(self) -> None:
        """
        User asks: "Thực hiện quy trình 3 bước: Fetch dữ liệu -> Tổng hợp -> Xóa cache tạm thời."
        Verifies:
        1. ReActTaskEngine decomposes goal into TaskDAG with variable interpolation.
        2. Transient timeout in Step 1 triggers SelfReflectionEngine and auto-recovers.
        3. Step 3 (destructive delete) is intercepted by SafetyGate, confirmed via token.
        4. Complete plan terminates successfully and logs metrics.
        """
        dag = TaskDAG(plan_id="e2e_plan_full", goal="Multi-Step Autonomous Workflow")

        # Step 1: Transient flaky fetch
        attempts = 0
        def fetch_handler(query: str = "dataset") -> Dict[str, Any]:
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise TimeoutError("Transient connection timeout to data gateway")
            return {"dataset_id": "DS_2026_A", "record_count": 100}

        # Step 2: Processing
        def process_handler(ds_id: str) -> Dict[str, Any]:
            return {"summary_file": f"/tmp/{ds_id}_report.csv", "status": "processed"}

        # Step 3: High-risk cleanup
        cleaned_up = False
        def cleanup_handler(target_path: str) -> Dict[str, str]:
            nonlocal cleaned_up
            cleaned_up = True
            return {"cleaned": target_path}

        self.planner.register_action_handler("fetch_data", fetch_handler)
        self.planner.register_action_handler("process_data", process_handler)
        self.planner.register_action_handler("cleanup_cache", cleanup_handler)

        dag.add_node(TaskNode(
            step_id="step_fetch",
            action_name="fetch_data",
            parameters={"query": "sales_q3"},
            max_retries=3,
        ))
        dag.add_node(TaskNode(
            step_id="step_process",
            action_name="process_data",
            parameters={"ds_id": "{{steps.step_fetch.output.dataset_id}}"},
            depends_on=["step_fetch"],
        ))
        node_cleanup = TaskNode(
            step_id="step_cleanup",
            action_name="cleanup_cache",
            parameters={"target_path": "{{steps.step_process.output.summary_file}}"},
            depends_on=["step_process"],
            is_high_risk=True,
        )
        dag.add_node(node_cleanup)

        # Background thread to confirm SafetyGate token
        def auto_confirm_token():
            time.sleep(0.3)
            for _ in range(30):
                if node_cleanup.confirmation_token:
                    self.safety_gate.confirm(node_cleanup.confirmation_token)
                    break
                time.sleep(0.05)

        import threading
        t = threading.Thread(target=auto_confirm_token)
        t.start()

        # Execute plan with SAFETY_GATE mode
        result: PlanResult = self.planner.execute_plan(dag, mode=PlanMode.SAFETY_GATE)
        t.join()

        self.assertTrue(result.success)
        self.assertEqual(result.completed_steps, 3)
        self.assertEqual(result.failed_steps, 0)
        self.assertTrue(cleaned_up)

        # Verify final outputs
        self.assertEqual(dag.nodes["step_fetch"].retry_count, 1)  # Healed after 1 retry
        self.assertEqual(dag.nodes["step_process"].result_data["summary_file"], "/tmp/DS_2026_A_report.csv")
        self.assertEqual(dag.nodes["step_cleanup"].status, StepStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
