"""
jarvis/core/handlers/service_handlers.py
========================================
Smart home, infosec, healing watchdog, and web intelligence handlers for JarvisApp.
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Any

from jarvis.core.labs import require_labs

log = logging.getLogger("jarvis.core.handlers.service")


class ServiceHandlersMixin:
    """Mixin providing smart home, infosec, healing, and web intelligence handlers for JarvisApp."""

    @require_labs("tshark_capture")
    def _handle_tshark_capture(
        self,
        interface: str = "eth0",
        count: int = 50,
        duration_s: float | None = None,
        bpf_filter: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Executes live packet capture via TShark (Labs feature)."""
        from jarvis.security.scanner import PacketCapture
        pc = PacketCapture(config=self.config)
        result = pc.capture_packets(
            interface=interface,
            count=count,
            duration_s=duration_s,
            bpf_filter=bpf_filter,
            **kwargs,
        )
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return dict(result)


    def _handle_healing_watchdog_heal(self, **kwargs) -> dict[str, Any]:
        """Performs system RAM optimization, process inspection, and self-healing."""
        import gc
        gc.collect()

        try:
            if sys.platform == "win32":
                import ctypes
                try:
                    k32 = ctypes.windll.kernel32
                    psapi = ctypes.windll.psapi
                    h_proc = k32.GetCurrentProcess()
                    psapi.EmptyWorkingSet(h_proc)
                except Exception:
                    pass
        except Exception:
            pass

        hung_apps: list[dict[str, Any]] = []
        healed_reports: list[dict[str, Any]] = []
        auto_kill = bool(kwargs.get("auto_kill", False))

        try:
            from jarvis.healing.terminator import HealingEngine
            engine = HealingEngine(
                hardware_provider=getattr(self, "hardware_reporter", None),
                auto_kill=auto_kill,
            )
            found = engine.find_hung_windows()
            for app in found:
                hung_apps.append(app.to_dict() if hasattr(app, "to_dict") else dict(app))

            if auto_kill and found:
                healed_reports = engine.run_auto_recovery_cycle()
        except Exception as exc:
            log.debug("Healing watchdog hung probe encountered: %s", exc)
            return {"success": False, "status": "ERROR", "code": "HEALING_PROBE_FAILED",
                    "message": "Không kiểm tra được tiến trình; chưa xác minh kết quả tối ưu bộ nhớ."}

        if any(not report.get("success") for report in healed_reports):
            return {"success": False, "status": "ERROR", "code": "HEALING_RECOVERY_FAILED",
                    "message": "Một hoặc nhiều tiến trình chưa được xử lý thành công.",
                    "data": {"healed_reports": healed_reports}}

        if hung_apps and not auto_kill:
            names = ", ".join(sorted(list(set(str(a.get("process_name", "Unknown")) for a in hung_apps[:3]))))
            msg = f"Đã kiểm tra tiến trình. Phát hiện {len(hung_apps)} ứng dụng bị treo ({names}); chưa đóng ứng dụng."
        elif healed_reports:
            msg = f"Đã xử lý {len(healed_reports)} tiến trình bị treo; chưa xác minh tổng RAM giải phóng."
        else:
            msg = "Đã kiểm tra tiến trình và yêu cầu thu gom bộ nhớ JARVIS; chưa xác minh lượng RAM giải phóng."

        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)

        return {
            "success": True,
            "status": "SUCCESS",
            "code": "OK",
            "message": msg,
            "data": {
                "hung_apps_detected": len(hung_apps),
                "hung_apps": hung_apps,
                "healed_reports": healed_reports,
            },
        }


    def _handle_security_nmap_scan(self, target: str = "192.168.1.0/24", **kwargs) -> dict[str, Any]:
        """Performs network and subnet security scan via Nmap."""
        from jarvis.security.scanner import NetworkScanner
        target_str = kwargs.get("target") or target or "192.168.1.0/24"
        scanner = NetworkScanner(timeout_s=float(kwargs.get("timeout_s", 30.0)))
        if "/" in str(target_str):
            report = scanner.scan_subnet(str(target_str))
        else:
            report = scanner.scan_host(str(target_str))

        res_dict = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        status_ok = (report.status == "SUCCESS")
        return {
            "success": status_ok,
            "status": report.status,
            "code": "OK" if status_ok else report.status,
            "message": f"Quét an ninh mạng cho {target_str}: {report.status} ({report.total_hosts} hosts)",
            "data": res_dict,
        }


    def _handle_home_assistant_call(self, **kwargs) -> dict[str, Any]:
        """Dispatches an authoritative service call to Home Assistant."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        domain = kwargs.get("domain", "light")
        service = kwargs.get("service", "turn_on")
        entity_id = kwargs.get("entity_id") or kwargs.get("entity")
        service_data = dict(kwargs.get("service_data", {}))
        if entity_id and "entity_id" not in service_data:
            service_data["entity_id"] = entity_id
        for k in ("brightness", "temperature"):
            if k in kwargs and k not in service_data:
                service_data[k] = kwargs[k]
        return self.ha_client.call_service(domain, service, service_data)


    def _handle_smart_home_turn_on(self, **kwargs) -> dict[str, Any]:
        """Turns on an authorized smart home entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "light.living_room")
        brightness = kwargs.get("brightness")
        return self.ha_client.turn_on(entity, brightness=brightness)


    def _handle_smart_home_turn_off(self, **kwargs) -> dict[str, Any]:
        """Turns off an authorized smart home entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "light.living_room")
        return self.ha_client.turn_off(entity)


    def _handle_smart_home_set_temp(self, **kwargs) -> dict[str, Any]:
        """Sets temperature for an authorized thermostat/climate entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "climate.ac_unit")
        temp = float(kwargs.get("temperature", 24.0))
        return self.ha_client.set_temperature(entity, temp)


    def _handle_smart_home_get_state(self, **kwargs) -> dict[str, Any]:
        """Queries the current state of an authorized entity."""
        if not getattr(self, "ha_client", None):
            return {"success": False, "error": "NOT_CONFIGURED: Home Assistant client unavailable"}
        entity = kwargs.get("entity") or kwargs.get("entity_id", "")
        state = self.ha_client.get_state(entity)
        if state is None:
            return {"success": False, "error": f"Entity '{entity}' not found or unreachable"}
        return {"success": True, "state": state}


    def _handle_tts_welcome(self, **kwargs) -> dict[str, Any]:
        """Dispatches welcome speech via TTSManager."""
        if self.tts_manager:
            delay = float(self.config.get("tts.welcome.delay_after_song_s", 1.0))
            self.tts_manager.speak_welcome(delay_s=delay)
            return {"status": "welcome_spoken"}
        return {"status": "tts_unavailable"}


    def _handle_show_overlay(self, **kwargs) -> dict[str, Any]:
        """Shows the JARVIS chat overlay window."""
        if self.overlay:
            self.overlay.show_listening()
            return {"status": "overlay_shown"}
        return {"status": "overlay_unavailable"}


    def _handle_toggle_sidebar(self, **kwargs) -> dict[str, Any]:
        """Toggles overlay sidebar mode."""
        if self.overlay:
            self.overlay.toggle_sidebar()
            return {"status": "sidebar_toggled", "mode": self.overlay.mode.value}
        return {"status": "overlay_unavailable"}


    def _handle_collapse_sidebar(self, **kwargs) -> dict[str, Any]:
        """Collapses sidebar to 40px ribbon."""
        if self.overlay:
            self.overlay.collapse_sidebar()
            return {"status": "sidebar_collapsed"}
        return {"status": "overlay_unavailable"}


    def _handle_expand_sidebar(self, **kwargs) -> dict[str, Any]:
        """Expands sidebar back to full width."""
        if self.overlay:
            self.overlay.expand_sidebar()
            return {"status": "sidebar_expanded"}
        return {"status": "overlay_unavailable"}


    def _handle_screen_capture(self, filepath: str | None = None, **kwargs) -> dict[str, Any]:
        """Captures screen and saves to file."""
        if self.vision_manager:
            try:
                saved_path = self.vision_manager.save_screenshot(filepath=filepath)
                msg = f"Đã chụp ảnh màn hình và lưu tại {saved_path}, thưa Ngài."
                return {"status": "success", "filepath": saved_path, "message": msg}
            except Exception as e:
                return {"status": "failed", "error": str(e), "message": f"Không thể chụp màn hình: {e}"}
        return {"status": "failed", "message": "Vision subsystem unavailable"}


    def _handle_screen_analyze(self, query: str = "Mô tả những gì đang hiển thị trên màn hình", **kwargs) -> dict[str, Any]:
        """Performs visual analysis of the screen."""
        if self.vision_manager:
            res = self.vision_manager.analyze_screen(query=query)
            return {"status": "success", "analysis": res, "message": res}
        return {"status": "failed", "message": "Tôi chưa thể nhìn thấy màn hình do chưa cấu hình Vision API key, thưa Ngài."}


    def _handle_screen_explain_error(self, **kwargs) -> dict[str, Any]:
        """Scans for error dialog and explains remediation."""
        if self.vision_manager:
            res = self.vision_manager.explain_error_on_screen()
            return {"status": "success", "explanation": res, "message": res}
        return {"status": "failed", "message": "Vision subsystem unavailable"}


    def _handle_screen_summarize(self, **kwargs) -> dict[str, Any]:
        """Summarizes open document on screen."""
        if self.vision_manager:
            res = self.vision_manager.summarize_document_on_screen()
            return {"status": "success", "summary": res, "message": res}
        return {"status": "failed", "message": "Vision subsystem unavailable"}


    def _handle_dialog_resolve(self, auto_dismiss: bool = True, action: str = "ok", **kwargs) -> dict[str, Any]:
        """Scans for active error dialogs and dismisses them safely."""
        from jarvis.vision.dialog_detector import ErrorDialogDetector
        detector = ErrorDialogDetector()
        results = detector.resolve_error_dialogs(auto_dismiss=auto_dismiss, preferred_action=action)
        if not results:
            msg = "Không phát hiện hộp thoại lỗi nào trên màn hình, thưa Ngài."
        else:
            dismissed_cnt = sum(1 for r in results if r.get("dismissed"))
            titles = ", ".join(str(r.get("title", "")) for r in results[:2])
            msg = f"Đã phát hiện và đóng {dismissed_cnt} hộp thoại lỗi ({titles}), thưa Ngài." if dismissed_cnt else f"Phát hiện {len(results)} hộp thoại lỗi: {titles}."

        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)
        success = not auto_dismiss or all(r.get("dismissed") for r in results)
        return {"status": "SUCCESS" if success else "ERROR", "success": success,
                "code": "OK" if success else "DIALOG_DISMISS_FAILED", "dialogs": results, "message": msg}


    def _handle_web_search(self, query: str, **kwargs) -> dict[str, Any]:
        """Searches the web and returns summary."""
        if self.web_hub:
            res = self.web_hub.search(query=query)
            return {"status": "success", "result": res, "message": res}
        return {"status": "failed", "message": "Web intelligence hub unavailable"}


    def _handle_weather_query(self, city: str = "Hanoi", location: str | None = None, **kwargs) -> dict[str, Any]:
        """Fetches weather forecast."""
        target_city = location or city
        if self.web_hub:
            res = self.web_hub.get_weather(city=target_city)
            return {"status": "success", "weather": res, "message": res}
        return {"status": "failed", "message": "Weather service unavailable"}


    def _handle_news_headlines(self, limit: int = 3, **kwargs) -> dict[str, Any]:
        """Fetches top technology news headlines."""
        if self.web_hub:
            headlines = self.web_hub.get_top_news(limit=limit)
            msg = "Điểm tin công nghệ nổi bật: " + "; ".join(headlines) + ", thưa Ngài."
            return {"status": "success", "news": headlines, "message": msg}
        return {"status": "failed", "message": "News aggregator unavailable"}


    def _handle_crypto_rates(self, **kwargs) -> dict[str, Any]:
        """Fetches crypto and foreign currency rates."""
        if not self.web_hub:
            return {"status": "failed", "success": False, "message": "Financial tracker unavailable"}

        curr = kwargs.get("currency") or kwargs.get("pair") or kwargs.get("symbol")
        if curr and str(curr).upper() in ("USD", "EUR", "JPY", "GBP", "FOREX"):
            base_curr = "EUR" if str(curr).upper() == "EUR" else ("JPY" if str(curr).upper() == "JPY" else "USD")
            summary = self.web_hub.finance.get_forex_summary(currency=base_curr)
            rate = self.web_hub.finance.get_exchange_rate(base_curr, "VND")
            if self.tts_manager:
                self.tts_manager.speak(summary, wait=False)
            return {"status": "success", "success": True, "currency": base_curr, "rate": rate, "message": summary}

        rates = self.web_hub.get_crypto_rates()
        summary = self.web_hub.finance.get_crypto_summary()
        if self.tts_manager:
            self.tts_manager.speak(summary, wait=False)
        return {"status": "success", "success": True, "rates": rates, "message": summary}


    def _handle_deep_research(self, topic: str = "", query: str = "", **kwargs) -> dict[str, Any]:
        """Conducts deep web research and saves executive report to Desktop."""
        target_topic = topic or query or kwargs.get("text") or "trí tuệ nhân tạo"
        if not self.web_hub:
            return {"status": "failed", "success": False, "message": "Web intelligence hub unavailable"}

        res = self.web_hub.conduct_deep_research(target_topic)
        if not res.get("success"):
            return {"status": "ERROR", "success": False, "code": "RESEARCH_FAILED",
                    "message": res.get("spoken_summary", "Không thể hoàn tất nghiên cứu."), "data": res}
        msg = res.get("spoken_summary", f"Đã hoàn tất nghiên cứu về {target_topic}.")
        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)
        if self.overlay and hasattr(self.overlay, "show_response") and "report_markdown" in res:
            self.overlay.show_response(f"Nghiên Cứu: {target_topic}", res["report_markdown"][:1000])

        return {"status": "success", "success": True, "message": msg, "data": res}


    def _handle_morning_briefing(self, city: str | None = None, **kwargs) -> dict[str, Any]:
        """Generates comprehensive morning briefing."""
        if self.web_hub:
            briefing = self.web_hub.generate_morning_briefing(city=city)
            if self.overlay and "overlay_bullets" in briefing:
                self.overlay.show_response("Morning Briefing", "\n".join(briefing["overlay_bullets"]))
            return {
                "status": "ERROR" if briefing.get("success") is False else "SUCCESS",
                "success": briefing.get("success") is not False,
                "code": "BRIEFING_PARTIAL" if briefing.get("success") is False else "OK",
                "briefing": briefing,
                "message": briefing.get("spoken_summary", "Chào buổi sáng thưa Ngài."),
            }
        return {"status": "failed", "message": "Web intelligence hub unavailable"}


    def _handle_proactive_reminder(
        self,
        message: str = "",
        delay_seconds: float | None = None,
        delay_minutes: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Schedules timed reminder with robust fallback for parameter alias keys."""
        msg = message or kwargs.get("text") or kwargs.get("action") or "nhắc nhở chung"
        if delay_seconds is None and "delay_s" in kwargs:
            delay_seconds = float(kwargs["delay_s"])

        if delay_seconds is not None:
            sec = float(delay_seconds)
        elif delay_minutes is not None:
            sec = float(delay_minutes) * 60.0
        else:
            sec = 300.0

        if self.proactive_engine:
            r_id = self.proactive_engine.add_reminder(text=str(msg), delay_seconds=sec)
            resp_msg = f"Đã đặt lời nhắc '{msg}' sau {int(sec)} giây cho Ngài."
            return {"status": "success", "reminder_id": r_id, "message": resp_msg}
        return {"status": "failed", "message": "Proactive engine unavailable"}


    def _handle_routine_schedule(
        self,
        text: str = "",
        action_name: str | None = None,
        interval_seconds: float | None = None,
        delay_seconds: float = 0.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Schedules automated routines in the ProactiveEngine."""
        act_name = action_name or kwargs.get("action")
        repeat_s = float(interval_seconds) if interval_seconds else None
        delay_s = float(delay_seconds) if delay_seconds else (repeat_s or 60.0)
        desc = text or f"Tác vụ tự động: {act_name}"

        def _routine_callback(reminder):
            if act_name:
                log.info("Executing scheduled routine: %s", act_name)
                try:
                    self.dispatcher.dispatch_action(act_name, payload=kwargs.get("payload", {}))
                except Exception as exc:
                    log.error("Routine action '%s' failed: %s", act_name, exc)

        if self.proactive_engine and hasattr(self.proactive_engine, "reminders"):
            r_id = self.proactive_engine.reminders.schedule_routine(
                text=desc,
                delay_seconds=delay_s,
                action_name=act_name,
                action_payload=kwargs.get("payload"),
                repeat_interval_s=repeat_s,
                callback=_routine_callback,
            )
            msg = f"Đã lên lịch tác vụ '{desc}' thành công, chu kỳ {repeat_s:.0f} giây, thưa Ngài." if repeat_s else f"Đã lên lịch tác vụ '{desc}' sau {delay_s:.0f} giây, thưa Ngài."
            if self.tts_manager:
                self.tts_manager.speak(msg, wait=False)
            return {"status": "success", "success": True, "routine_id": r_id, "message": msg}

        return {"status": "UNAVAILABLE", "success": False, "code": "SCHEDULER_UNAVAILABLE",
                "message": "Không thể tạo lịch: bộ lập lịch chưa sẵn sàng."}


    def _handle_workflow_preset(self, preset: str = "work", **kwargs) -> dict[str, Any]:
        """Executes curated multi-action productivity workflows."""
        p = (preset or "work").lower().strip()
        executed_steps = []

        if p in ("work", "lam_viec", "focus") and (
            not self.proactive_engine or not self.computer_controller
        ):
            return {"success": False, "status": "UNAVAILABLE", "code": "WORKFLOW_BACKEND_UNAVAILABLE",
                    "message": "Thiếu backend để bật chế độ làm việc.", "steps": []}
        if p in ("relax", "nghi_ngoi", "thu_gian") and not self.computer_controller:
            return {"success": False, "status": "UNAVAILABLE", "code": "WORKFLOW_BACKEND_UNAVAILABLE",
                    "message": "Thiếu backend điều khiển màn hình.", "steps": []}

        if p in ("work", "lam_viec", "focus"):
            if self.proactive_engine:
                self.proactive_engine.start_pomodoro(work_minutes=25.0)
                executed_steps.append("Started 25m Focus Pomodoro")
            if self.computer_controller:
                if self.computer_controller.set_volume(40) is None:
                    return {"success": False, "status": "ERROR", "code": "VOLUME_SET_FAILED",
                            "message": "Không chỉnh được âm lượng; phiên tập trung có thể đã bắt đầu.", "steps": executed_steps}
                executed_steps.append("Volume set to 40%")
            msg = "Đã kích hoạt chế độ làm việc tập trung. Chúc Ngài làm việc hiệu quả."
        elif p in ("relax", "nghi_ngoi", "thu_gian"):
            if self.computer_controller:
                if self.computer_controller.change_brightness(-15) is None:
                    return {"success": False, "status": "ERROR", "code": "BRIGHTNESS_SET_FAILED",
                            "message": "Không chỉnh được độ sáng.", "steps": executed_steps}
                executed_steps.append("Brightness dimmed")
            msg = "Đã kích hoạt chế độ nghỉ ngơi. Ngài hãy thư giãn nhé."
        elif p in ("clean", "don_dep", "toi_uu"):
            healing = self._handle_healing_watchdog_heal()
            if not healing.get("success"):
                return healing
            executed_steps.append("Process inspection completed")
            msg = healing["message"]
        else:
            msg = f"Kịch bản '{p}' không được hỗ trợ."
            return {"status": "failed", "success": False, "message": msg}

        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)
        return {"status": "success", "success": True, "preset": p, "steps": executed_steps, "message": msg}


    def _handle_proactive_pomodoro_start(self, work_minutes: float = 25.0, break_minutes: float = 5.0, **kwargs) -> dict[str, Any]:
        """Starts Pomodoro timer."""
        if self.proactive_engine:
            res = self.proactive_engine.start_pomodoro(work_minutes=work_minutes, break_minutes=break_minutes)
            msg = f"Đã bắt đầu phiên tập trung Focus Mode {work_minutes} phút, thưa Ngài."
            return {"status": "success", "message": msg}
        return {"status": "failed", "message": "Proactive engine unavailable"}


    def _handle_proactive_pomodoro_stop(self, **kwargs) -> dict[str, Any]:
        """Stops Pomodoro timer."""
        if self.proactive_engine:
            self.proactive_engine.stop_pomodoro()
            return {"status": "success", "message": "Đã dừng phiên tập trung Focus Mode, thưa Ngài."}
        return {"status": "failed", "message": "Proactive engine unavailable"}


    def _handle_memory_save_fact(self, key: str | None = None, value: str | None = None, text: str | None = None, **kwargs) -> dict[str, Any]:
        """Saves persistent fact."""
        if self.memory_manager:
            res: Any
            if text:
                res = self.memory_manager.handle_remember_command(text)
            elif key and value:
                self.memory_manager.store_fact(key=key, value=value)
                res = {"success": True, "message": f"Tôi đã ghi nhớ thông tin này, thưa Ngài: {key} = {value}."}
            else:
                res = {"success": False, "message": "Thiếu dữ liệu cần ghi nhớ."}
            if self.overlay:
                facts = self.memory_manager.list_facts(limit=3)
                if facts:
                    self.overlay.set_memory_facts([f"{f.get('key')}: {f.get('value')}" for f in facts])
            return {"status": "success" if res.get("success") else "failed", "message": res.get("message", "")}
        return {"status": "failed", "message": "Memory manager unavailable"}


    def _handle_memory_summarize_daily(self, text: str = "", **kwargs) -> dict[str, Any]:
        """Summarizes today's episodic memory logs."""
        if self.memory_manager:
            res = self.memory_manager.handle_today_summary(text)
            return {"status": "success", "summary": res, "message": res.get("message", "")}
        return {"status": "failed", "message": "Memory manager unavailable"}


    def _handle_note_add(self, content: str = "", tag: str = "general", **kwargs) -> dict[str, Any]:
        """Adds a voice or text note using note_taker skill and speaks confirmation."""
        text_content = content or kwargs.get("text") or kwargs.get("message") or ""
        if not text_content.strip():
            msg = "Nội dung ghi chú trống, vui lòng cho biết nội dung ghi chú."
            return {"status": "failed", "success": False, "message": msg}

        if self.skill_registry:
            res = self.skill_registry.invoke_skill("note_taker", action="add", content=text_content.strip(), tag=tag)
            data_dict = res.data if isinstance(res.data, dict) else {}
            if not res.success or data_dict.get("success") is False:
                return {"success": False, "status": "ERROR", "code": "NOTE_SAVE_FAILED",
                        "message": "Không lưu được ghi chú.", "data": data_dict}
            msg = f"Đã lưu ghi chú cho Ngài: {text_content.strip()}"
            if self.tts_manager:
                self.tts_manager.speak(msg, wait=False)
            data_dict = res.data if hasattr(res, "data") and isinstance(res.data, dict) else {}
            return {"status": "success", "success": True, "message": msg, "data": data_dict}

        return {"success": False, "status": "UNAVAILABLE", "code": "NOTE_BACKEND_UNAVAILABLE",
                "message": "Không lưu được ghi chú: bộ lưu trữ chưa sẵn sàng."}


    def _handle_note_list(self, **kwargs) -> dict[str, Any]:
        """Lists and reads recent notes."""
        if self.skill_registry:
            res = self.skill_registry.invoke_skill("note_taker", action="list")
            data_dict = res.data if hasattr(res, "data") and isinstance(res.data, dict) else {}
            if not res.success or data_dict.get("success") is False:
                return {"success": False, "status": "ERROR", "code": "NOTE_READ_FAILED",
                        "message": "Không đọc được danh sách ghi chú."}
            notes = data_dict.get("notes", [])
            if not notes:
                msg = "Ngài chưa có ghi chú nào được lưu."
            else:
                latest = notes[-1]
                msg = f"Ngài có {len(notes)} ghi chú. Ghi chú gần nhất là: {latest.get('content')}"
            if self.tts_manager:
                self.tts_manager.speak(msg, wait=False)
            return {"status": "success", "success": True, "notes": notes, "message": msg}
        return {"status": "failed", "success": False, "message": "Skill registry unavailable"}

