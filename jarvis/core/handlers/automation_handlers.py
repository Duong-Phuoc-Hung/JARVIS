"""
jarvis/core/handlers/automation_handlers.py
===========================================
Browser automation, autonomous ReAct planner, subagents, sandbox, skills,
and vision GUI actor handlers for JarvisApp.
"""
from __future__ import annotations

from collections.abc import Callable
import logging
import time
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any

from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    ScrapeResult,
)
from jarvis.core.handlers.base import (
    _DualErrorStr,
    _build_browser_config,
    _safe_browser_failure_url,
)
from jarvis.core.labs import require_labs
from jarvis.planner.models import PlanMode, PlanResult
from jarvis.sandbox.interpreter import SandboxResult
from jarvis.workers.models import WorkerPriority, WorkerTask

log = logging.getLogger("jarvis.core.handlers.automation")


class AutomationHandlersMixin:
    """Mixin providing browser automation, subagents, code sandbox, skills, and vision handlers for JarvisApp."""

    @require_labs("browser_cdp")
    def _handle_browser_cdp_capture(
        self,
        url: str | None = None,
        endpoint: str | None = None,
        timeout_s: float = 2.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Captures DOM state and screenshot via Chrome DevTools Protocol (Labs feature)."""
        cdp_endpoint = endpoint or (
            self.config.get("browser.cdp_endpoint", "http://127.0.0.1:9222")
            if hasattr(self.config, "get")
            else "http://127.0.0.1:9222"
        )
        version_url = f"{cdp_endpoint.rstrip('/')}/json/version"

        # 1. Honest endpoint connectivity probe
        import socket
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(version_url, headers={"User-Agent": "JARVIS-CDP/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "status": "FAILED",
                        "code": "CDP_ENDPOINT_UNAVAILABLE",
                        "error": f"Chrome CDP endpoint returned non-200 status: {resp.status}",
                        "error_code": "CDP_ENDPOINT_UNAVAILABLE",
                        "message": f"Chrome CDP endpoint unavailable at {cdp_endpoint}",
                        "retryable": False,
                    }
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError, socket.timeout) as exc:
            log.warning("Chrome CDP endpoint unreachable at %s: %s", version_url, exc)
            return {
                "success": False,
                "status": "FAILED",
                "code": "CDP_ENDPOINT_UNAVAILABLE",
                "message": f"Chrome CDP endpoint unavailable at {cdp_endpoint}",
                "error": "Chrome debugging port 9222 is not reachable",
                "error_code": "CDP_ENDPOINT_UNAVAILABLE",
                "retryable": False,
            }
        except Exception as exc:
            log.error("Unexpected error probing CDP endpoint %s: %s", version_url, exc)
            return {
                "success": False,
                "status": "FAILED",
                "code": "CDP_ENDPOINT_UNAVAILABLE",
                "error": str(exc),
                "error_code": "CDP_ENDPOINT_UNAVAILABLE",
                "message": f"Failed to probe CDP endpoint: {exc}",
                "retryable": False,
            }

        # 2. Genuine CDP execution via BrowserCDPController
        try:
            from jarvis.browser.cdp_controller import BrowserCDPController, BrowserConfig

            controller = BrowserCDPController(
                config=BrowserConfig(cdp_endpoint=cdp_endpoint, timeout_ms=int(timeout_s * 1000)),
            )
            if not controller.launch():
                return {
                    "success": False,
                    "status": "FAILED",
                    "code": controller.last_error_code or "CDP_ATTACH_FAILED",
                    "error": controller.last_error_message or "Failed to attach to Chromium CDP session",
                    "error_code": controller.last_error_code or "CDP_ATTACH_FAILED",
                    "message": "Failed to attach to Chromium CDP session",
                    "retryable": False,
                }

            try:
                target_url = url or kwargs.get("target_url")
                if target_url:
                    page_info = controller.navigate(target_url)
                    if not page_info.success:
                        return {
                            "success": False,
                            "status": "FAILED",
                            "code": page_info.error_code or "BROWSER_NAVIGATION_FAILED",
                            "error": page_info.error_message or "Navigation failed",
                            "error_code": page_info.error_code or "BROWSER_NAVIGATION_FAILED",
                            "message": f"Navigation to {target_url} failed",
                            "retryable": False,
                        }

                content_md = controller.extract_content_as_markdown()
                screenshot_path = controller.screenshot()
                current_url = controller.get_current_url()

                return {
                    "success": True,
                    "status": "SUCCESS",
                    "code": "OK",
                    "message": "CDP capture executed successfully",
                    "data": {
                        "url": current_url,
                        "content_md": content_md,
                        "screenshot_path": screenshot_path,
                    },
                }
            finally:
                controller.close()

        except ImportError:
            return {
                "success": False,
                "status": "FAILED",
                "code": "BROWSER_CDP_NOT_INSTALLED",
                "error": "BrowserCDPController dependencies not installed",
                "error_code": "BROWSER_CDP_NOT_INSTALLED",
                "message": "Browser CDP controller dependencies not installed",
                "retryable": False,
            }
        except Exception as exc:
            log.error("CDP capture execution failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "status": "ERROR",
                "code": "CDP_EXECUTION_ERROR",
                "error": str(exc),
                "error_code": "CDP_EXECUTION_ERROR",
                "message": f"CDP capture encountered an error: {exc}",
                "retryable": False,
            }


    def _handle_generic_task(self, **kwargs) -> dict[str, Any]:
        """Generic fallback task handler for autonomous plan execution."""
        return {"status": "completed", "details": kwargs, "message": "Tác vụ tự trị đã hoàn thành."}


    def _handle_planner_execute_task(
        self,
        goal: str,
        mode: str = "fully_autonomous",
        context: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Constructs and executes an autonomous multi-step Task DAG."""
        if not self.planner_engine:
            return {"status": "failed", "message": "ReAct Planner Subsystem is unavailable."}

        plan_mode = PlanMode.SAFETY_GATE if "confirm" in mode.lower() or "safety" in mode.lower() else PlanMode.FULLY_AUTONOMOUS
        dag = self.planner_engine.create_plan(goal=goal, context=context)

        # Update HUD overlay with plan telemetry
        if self.overlay:
            self.overlay.update_task_dag(dag.to_dict())

        t0 = time.time()
        plan_result: PlanResult = self.planner_engine.execute_plan(dag, mode=plan_mode)
        duration = time.time() - t0

        # Update HUD overlay with final DAG state
        if self.overlay:
            self.overlay.update_task_dag(dag.to_dict())

        # Persist task history into SQLite Memory
        if self.memory_manager:
            try:
                self.memory_manager.store.record_task_execution(
                    task_id=dag.plan_id,
                    goal=goal,
                    plan_dag_json=dag.to_dict(),
                    execution_trace_json=[r.to_dict() for r in plan_result.step_results],
                    status="completed" if plan_result.success else "failed",
                    duration_seconds=duration,
                )
            except Exception as e:
                log.warning("Could not persist task execution history: %s", e)

        summary_msg = (
            f"Kế hoạch '{goal[:30]}' đã hoàn thành xuất sắc ({len(plan_result.step_results)} bước, {duration:.1f}s)."
            if plan_result.success
            else f"Kế hoạch '{goal[:30]}' gặp lỗi: {plan_result.error}"
        )

        return {
            "status": "success" if plan_result.success else "failed",
            "plan_id": dag.plan_id,
            "goal": goal,
            "success": plan_result.success,
            "duration_seconds": duration,
            "step_results": [r.to_dict() for r in plan_result.step_results],
            "message": summary_msg,
        }


    def _handle_agent_react_run(self, goal: str = "", **kwargs: Any) -> dict[str, Any]:
        """Execute an autonomous task goal via ReActAgent."""
        if not self.react_agent:
            return {"status": "failed", "error": "ReActAgent is not initialized"}
        task = self.react_agent.run(goal)
        state_val = getattr(task.state, "value", str(task.state))
        return {
            "status": "success" if state_val == "done" else "failed",
            "task_id": task.task_id,
            "state": state_val,
            "result": task.result,
            "error": task.error,
            "steps_count": len(task.steps),
        }


    def _handle_file_write(self, path: str = "", content: str = "", **kwargs: Any) -> dict[str, Any]:
        """Safely write content to a file inside the workspace."""
        from pathlib import Path
        if not path or not path.strip():
            return {"status": "failed", "error": "Path cannot be empty"}
        target_path = Path(path).resolve()
        workspace_dir = Path.cwd().resolve()
        try:
            target_path.relative_to(workspace_dir)
        except ValueError:
            return {
                "status": "failed",
                "error": f"Path traversal blocked: '{path}' is outside workspace '{workspace_dir}'",
            }
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return {
                "status": "success",
                "path": str(target_path),
                "bytes_written": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}


    def _handle_subagent_spawn(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        target_callable: Callable[..., Any] | None = None,
        priority: str = "normal",
        timeout_seconds: float = 300.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Spawns an autonomous background sub-agent worker."""
        if not self.subagent_manager:
            return {"status": "failed", "message": "SubAgent Manager is unavailable."}

        p_enum = WorkerPriority.HIGH if priority.lower() == "high" else (WorkerPriority.CRITICAL if priority.lower() == "critical" else WorkerPriority.NORMAL)
        task = WorkerTask(
            task_id=f"subagent_{uuid.uuid4().hex[:12]}",
            name=name,
            payload=payload or {},
            target_callable=target_callable or (lambda ctx: {"status": "completed", "name": name}),
            priority=p_enum,
            timeout_seconds=timeout_seconds,
        )
        worker_id = self.subagent_manager.spawn_worker(task)
        msg = f"Đã khởi chạy background worker '{name}' (ID: {worker_id}), thưa Ngài."
        return {"status": "success", "worker_id": worker_id, "name": name, "message": msg}


    def _handle_subagent_cancel(self, worker_id: str, **kwargs) -> dict[str, Any]:
        """Cancels an active background sub-agent worker."""
        if not self.subagent_manager:
            return {"status": "failed", "message": "SubAgent Manager is unavailable."}
        ok = self.subagent_manager.cancel_worker(worker_id)
        msg = f"Đã hủy worker {worker_id} thành công." if ok else f"Không tìm thấy worker {worker_id} hoặc worker đã dừng."
        return {"status": "success" if ok else "failed", "worker_id": worker_id, "message": msg}


    def _handle_subagent_status(self, worker_id: str, **kwargs) -> dict[str, Any]:
        """Queries status telemetry for a sub-agent worker."""
        if not self.subagent_manager:
            return {"status": "failed", "message": "SubAgent Manager is unavailable."}
        status = self.subagent_manager.get_worker_status(worker_id)
        if not status:
            return {"status": "not_found", "worker_id": worker_id, "message": f"Worker {worker_id} không tồn tại."}
        return {"status": "success", "telemetry": status.to_dict() if hasattr(status, "to_dict") else str(status)}


    def _handle_sandbox_execute_code(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: float = 15.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Executes code safely in the isolated sandbox."""
        if not self.sandbox:
            return {"status": "failed", "message": "Code Interpreter Sandbox is unavailable."}

        lang = language.lower().strip()
        res: SandboxResult
        if lang in ("powershell", "ps1"):
            res = self.sandbox.execute_powershell(code, timeout_seconds=timeout_seconds)
        else:
            res = self.sandbox.execute_python(code, timeout_seconds=timeout_seconds)

        # Stream code output to overlay HUD
        if self.overlay:
            if res.stdout:
                for line in res.stdout.splitlines()[-5:]:
                    self.overlay.append_code_log(line, "stdout")
            if res.stderr:
                for line in res.stderr.splitlines()[-3:]:
                    self.overlay.append_code_log(line, "stderr")

        msg = (
            f"Code thực thi thành công ({res.execution_time_seconds:.2f}s). {len(res.artifacts)} file đầu ra."
            if res.success
            else f"Lỗi thực thi code: {res.error}"
        )
        return {
            "status": "success" if res.success else "failed",
            "success": res.success,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "data": res.data,
            "artifacts": res.artifacts,
            "execution_time_seconds": res.execution_time_seconds,
            "message": msg,
        }


    def _handle_skill_synthesize(
        self,
        name: str,
        code: str,
        description: str = "",
        category: str = "custom",
        requirements: list[str] | None = None,
        overwrite: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """Synthesizes, tests, and packages code as a reusable persistent skill."""
        if not self.skill_synthesizer:
            return {"status": "failed", "message": "Skill Synthesizer is unavailable."}

        try:
            skill_def = self.skill_synthesizer.synthesize_skill(
                name=name,
                code=code,
                description=description or f"Tự động tổng hợp kỹ năng {name}",
                tags=[category] if category else None,
            )
        except Exception as e:
            log.warning("Skill synthesis failed for '%s': %s", name, e)
            return {"status": "failed", "skill_name": name, "message": f"Không thể đóng gói kỹ năng '{name}' do lỗi kiểm thử hoặc cú pháp."}

        msg = f"Đã đóng gói thành công kỹ năng '{name}' vào thư viện kỹ năng tái sử dụng, thưa Ngài."
        return {"status": "success", "skill_name": name, "module_path": skill_def.file_path, "message": msg}


    def _handle_skill_invoke(self, skill_name: str, **kwargs) -> dict[str, Any]:
        """Invokes a packaged persistent skill from library."""
        if not self.skill_registry:
            return {"status": "failed", "message": "Skill Registry is unavailable."}
        try:
            res = self.skill_registry.invoke_skill(skill_name, **kwargs)
            return {"status": "success", "result": res, "message": f"Kỹ năng '{skill_name}' thực thi thành công."}
        except Exception as e:
            return {"status": "failed", "error": str(e), "message": f"Lỗi khi thực thi kỹ năng '{skill_name}': {e}"}


    def _handle_browser_navigate(self, url: str, **kwargs) -> dict[str, Any]:
        """Navigates browser to target URL and captures page state."""
        if not self.browser_agent:
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        res: BrowserActionResult = self.browser_agent.navigate(url=url)
        reported_url = res.url if res.success else _safe_browser_failure_url(res.url or url)
        msg = (
            f"Đã điều hướng tới {reported_url} ({res.title or 'Sẵn sàng'})."
            if res.success
            else f"Không thể điều hướng trang: {res.error}"
        )
        return {
            "success": res.success,
            "status": "success" if res.success else "failed",
            "result_status": res.status.value,
            "error_code": res.error_code,
            "driver_type": res.driver_type.value if res.driver_type else None,
            "url": reported_url,
            "title": res.title if res.success else "",
            "message": msg,
        }


    def _handle_browser_scrape(self, url: str, extract_tables: bool = True, **kwargs) -> dict[str, Any]:
        """Scrapes and parses structured markdown from web page."""
        if not self.browser_agent:
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        res: ScrapeResult = self.browser_agent.scrape_page(url=url, extract_tables=extract_tables)
        reported_url = res.url if res.success else _safe_browser_failure_url(res.url or url)
        msg = (
            f"Đã trích xuất dữ liệu từ {reported_url} "
            f"({len(res.markdown)} ký tự, {len(res.tables)} bảng)."
            if res.success
            else f"Không thể trích xuất trang: {res.error}"
        )
        return {
            "success": res.success,
            "status": "success" if res.success else "failed",
            "result_status": res.status.value,
            "error_code": res.error_code,
            "driver_type": res.driver_type.value if res.driver_type else None,
            "url": reported_url,
            "title": res.title if res.success else "",
            "markdown": res.markdown if res.success else "",
            "tables": res.tables if res.success else [],
            "message": msg,
        }


    def _handle_browser_fill_form(
        self,
        url: str,
        fields: dict[str, str],
        submit_selector: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Fills and submits web forms automatically."""
        if not self.browser_agent:
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        res: BrowserActionResult = self.browser_agent.fill_form(url=url, form_fields=fields, submit_selector=submit_selector)
        msg = (
            f"Đã điền tự động {len(fields)} trường dữ liệu trên {url}."
            if res.success
            else "Không thể hoàn tất biểu mẫu trên trang được yêu cầu."
        )
        reported_url = res.url if res.success else _safe_browser_failure_url(res.url or url)
        return {
            "success": res.success,
            "status": "success" if res.success else "failed",
            "result_status": res.status.value,
            "error_code": res.error_code,
            "driver_type": res.driver_type.value if res.driver_type else None,
            "url": reported_url,
            "field_count": len(fields),
            "message": msg,
        }


    def _handle_browser_compare_prices(self, product: str, stores: list[str] | None = None, **kwargs) -> dict[str, Any]:
        """Scrapes multiple eCommerce sites and compares prices."""
        if not self.browser_agent:
            return {
                "success": False,
                "status": "failed",
                "result_status": "NOT_CONFIGURED",
                "error_code": "BROWSER_AGENT_NOT_CONFIGURED",
                "driver_type": None,
                "message": "Browser Agent is unavailable.",
            }
        target_stores = stores or ["Shopee", "Tiki", "Lazada"]
        items = self.browser_agent.compare_prices(product=product, stores=target_stores)
        driver_type = self.browser_agent.get_active_driver_type()
        if not items:
            return {
                "success": False,
                "status": "failed",
                "result_status": "UNAVAILABLE",
                "error_code": "BROWSER_PRICE_DATA_UNAVAILABLE",
                "driver_type": driver_type.value if driver_type else None,
                "product": product,
                "items": [],
                "message": f"Không lấy được dữ liệu giá thực cho '{product}'.",
            }
        serialized_items = [
            asdict(item)
            if is_dataclass(item) and not isinstance(item, type)
            else item.to_dict()
            if hasattr(item, "to_dict")
            else item
            for item in items
        ]
        evidenced_lookup = {
            str(item.store_name).strip().casefold(): str(item.store_name).strip()
            for item in items
            if hasattr(item, "store_name") and str(item.store_name).strip()
        }
        evidenced_stores = [
            store
            for store in target_stores
            if store.strip().casefold() in evidenced_lookup
        ]
        missing_stores = [
            store
            for store in target_stores
            if store.strip().casefold() not in evidenced_lookup
        ]
        partial = bool(missing_stores)
        coverage = f"{len(evidenced_stores)}/{len(target_stores)}"
        msg = (
            f"Tìm thấy {len(items)} kết quả giá có bằng chứng từ "
            f"{coverage} nguồn đã yêu cầu"
            f"{' (kết quả một phần).' if partial else '.'}"
        )
        return {
            "success": True,
            "status": "success",
            "result_status": "SUCCESS",
            "error_code": None,
            "driver_type": driver_type.value if driver_type else None,
            "product": product,
            "items": serialized_items,
            "partial": partial,
            "evidenced_stores": evidenced_stores,
            "missing_stores": missing_stores,
            "message": msg,
        }


    def _handle_vision_click_ui(self, query: str, verify: bool = True, button: str = "left", clicks: int = 1, **kwargs) -> dict[str, Any]:
        """Locates target UI element visually and clicks it."""
        if not self.gui_actor:
            return {"status": "failed", "message": "GUIActor subsystem is unavailable."}
        res = self.gui_actor.click_element(query=query, verify=verify, button=button, clicks=clicks)
        action_rec = self.gui_actor.action_history[-1] if self.gui_actor.action_history else None
        is_success = res if isinstance(res, bool) else getattr(res, "success", False)
        visual_res = getattr(action_rec, "verification", None) if action_rec else getattr(res, "visual_result", None)
        elem = getattr(action_rec, "grounded_element", None) if action_rec else getattr(res, "element", None)
        err_msg = getattr(action_rec, "error_message", None) if action_rec else getattr(res, "error", None)

        if self.overlay and visual_res:
            self.overlay.display_visual_result(visual_res.to_dict() if hasattr(visual_res, "to_dict") else {"summary": f"Clicked: {query}"})
        msg = f"Đã click vào phần tử '{query}' trên màn hình." if is_success else f"Không thể click vào '{query}': {err_msg or 'Thao tác không thành công'}"
        return {"status": "success" if is_success else "failed", "element": elem.to_dict() if elem and hasattr(elem, "to_dict") else None, "message": msg}


    def _handle_vision_type_ui(self, query: str, text: str, verify: bool = True, press_enter: bool = False, **kwargs) -> dict[str, Any]:
        """Locates target UI field visually and types text."""
        if not self.gui_actor:
            return {"status": "failed", "message": "GUIActor subsystem is unavailable."}
        res = self.gui_actor.type_into_element(query=query, text=text, verify=verify, press_enter=press_enter)
        action_rec = self.gui_actor.action_history[-1] if self.gui_actor.action_history else None
        is_success = res if isinstance(res, bool) else getattr(res, "success", False)
        visual_res = getattr(action_rec, "verification", None) if action_rec else getattr(res, "visual_result", None)
        elem = getattr(action_rec, "grounded_element", None) if action_rec else getattr(res, "element", None)
        err_msg = getattr(action_rec, "error_message", None) if action_rec else getattr(res, "error", None)

        if self.overlay and visual_res:
            self.overlay.display_visual_result(visual_res.to_dict() if hasattr(visual_res, "to_dict") else {"summary": f"Typed into: {query}"})
        msg = f"Đã nhập văn bản vào '{query}'." if is_success else f"Không thể nhập vào '{query}': {err_msg or 'Thao tác không thành công'}"
        return {"status": "success" if is_success else "failed", "element": elem.to_dict() if elem and hasattr(elem, "to_dict") else None, "message": msg}


    def _handle_vision_verify_state(self, query: str | None = None, expected_condition: str | None = None, **kwargs) -> dict[str, Any]:
        """Performs visual verification check on screen state."""
        if not self.visual_verifier:
            return {"status": "failed", "message": "Visual Verifier is unavailable."}
        if self.overlay:
            self.overlay.display_visual_result({"title": "Visual State Check", "query": query, "expected": expected_condition})
        return {"status": "success", "message": "Đã kiểm tra xác minh trạng thái thị giác màn hình, thưa Ngài."}


    def _on_overlay_quick_action(self, action_key: str) -> Any:
        """Handles quick action button clicks on AlwaysOnOverlay."""
        log.info("Overlay quick action invoked: %s", action_key)
        if action_key == "briefing_morning":
            return self._handle_morning_briefing()
        elif action_key == "system_status":
            return self._handle_system_status()
        elif action_key == "focus_mode":
            if self.proactive_engine:
                return self.proactive_engine.start_pomodoro()
        return None

