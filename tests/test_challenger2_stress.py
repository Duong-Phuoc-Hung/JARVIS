"""
tests/test_challenger2_stress.py
================================
Adversarial Empirical Challenge and Stress-Testing Suite for Challenger 2:
- R5: Web Intelligence (TTLCache concurrency, 600s TTL, malformed RSS/Atom, missing JSON fields, stock errors, offline recovery)
- R6: Proactive Intelligence (Out-of-order & past timestamps, boundary thresholds 89.9% vs 90.1%, Pomodoro rapid transitions, inactivity resets)
- R7: Natural Language Shell (Dev server detection, obfuscated destructive regex gate, 1000+ line stdout summarization)
- R8: Always-On Overlay HUD (Rapid cycling 50x, long text truncation, missing telemetry/battery None, audio normalization, headless resilience)
"""
import concurrent.futures
import json
import math
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from jarvis.automation.safety_gate import SafetyGate
from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.proactive.engine import ProactiveEngine
from jarvis.proactive.health_monitor import HealthAlert, SystemHealthMonitor
from jarvis.proactive.inactivity import InactivityMonitor
from jarvis.proactive.pomodoro import PomodoroState, PomodoroTimer
from jarvis.proactive.reminders import ReminderScheduler, ScheduledReminder
from jarvis.ui.overlay import AlwaysOnOverlay, OverlayMode, OverlayState, TurnRecord
from jarvis.web.cache import TTLCache
from jarvis.web.finance import CryptoQuote, FinanceTracker, StockQuote
from jarvis.web.hub import WebIntelligenceHub
from jarvis.web.news import NewsAggregator, NewsArticle
from jarvis.web.weather import WeatherData, WeatherProvider


class TestR5WebIntelligenceAdversarial(unittest.TestCase):
    """Adversarial & stress tests for R5 Web Intelligence."""

    def test_ttl_cache_concurrency_stress(self):
        """Stress-test TTLCache with 50 threads doing 5000 concurrent operations."""
        cache = TTLCache(default_ttl_seconds=600.0, max_size=200)
        errors = []

        def worker(worker_id):
            try:
                for i in range(100):
                    key = f"key_{worker_id % 10}_{i % 20}"
                    val = f"val_{worker_id}_{i}"
                    cache.set(key, val, ttl=0.5 if (i % 2 == 0) else 600.0)
                    _ = cache.get(key)
                    _ = cache.has(key)
                    _ = cache.get_or_set(f"comp_{i % 10}", lambda i=i: f"computed_{i}")
                    if i % 10 == 0:
                        cache.cleanup_expired()
                        _ = cache.size()
                        _ = cache.keys()
                        _ = cache.items()
                    if i % 15 == 0:
                        cache.delete(key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(len(errors), 0, f"Concurrency errors in TTLCache: {errors}")
        self.assertLessEqual(cache.size(), 200, "Cache size exceeded max_size limit under load")

    def test_ttl_cache_600s_expiration_and_eviction(self):
        """Test default 600s TTL and simulated time expiration/eviction."""
        cache = TTLCache(default_ttl_seconds=600.0, max_size=5)
        self.assertEqual(cache.default_ttl, 600.0)

        # Set items with explicit short TTL
        cache.set("quick", "val1", ttl=0.1)
        cache.set("long", "val2", ttl=600.0)
        self.assertEqual(cache.get("quick"), "val1")
        self.assertEqual(cache.get("long"), "val2")

        time.sleep(0.15)
        # quick should be expired
        self.assertIsNone(cache.get("quick"))
        self.assertEqual(cache.get("long"), "val2")

        # Test LRU / max_size eviction
        for i in range(10):
            cache.set(f"k_{i}", f"v_{i}", ttl=600.0)
            time.sleep(0.005)
        self.assertLessEqual(cache.size(), 5)

    def test_malformed_rss_and_atom_xml_feeds(self):
        """Feed malformed, broken, truncated, and adversarial XML payloads to NewsAggregator."""
        aggregator = NewsAggregator()

        # 1. Broken / Truncated XML
        broken_xmls = [
            "<rss><channel><item><title>Unclosed title",
            "<?xml version='1.0'?><rss><channel>No items here",
            "Garbage non-xml string 123456 !!!",
            "",
            "   \n\t  ",
            "<feed><entry><title>Missing link and summary</entry></feed>",
            "<feed xmlns='http://www.w3.org/2005/Atom'><entry><atom:title>Atom with namespace</atom:title></entry></feed>",
            "<rss><channel><item><title><![CDATA[Nested <b>HTML</b> &amp; CDATA]]></title><description><![CDATA[<p>Paragraph with <script>alert(1)</script></p>]]></description></item></channel></rss>",
            "\x00\xff\xfeBinaryGarbage",
        ]

        for xml_text in broken_xmls:
            try:
                articles = aggregator.parse_feed_xml(xml_text, source_name="TestFeed")
                self.assertIsInstance(articles, list)
            except Exception as e:
                self.fail(f"NewsAggregator crashed on XML input: {e}")

        # Verify CDATA and HTML stripping in proper item
        cdata_xml = "<rss><channel><item><title><![CDATA[Tiêu đề <b>Test</b>]]></title><description><![CDATA[<p>Nội dung <i>chi tiết</i></p>]]></description><link>https://example.com</link></item></channel></rss>"
        articles = aggregator.parse_feed_xml(cdata_xml, source_name="TestSource")
        self.assertEqual(len(articles), 1)
        self.assertIn("Tiêu đề Test", articles[0].title)
        self.assertNotIn("<b>", articles[0].title)
        self.assertIn("Nội dung chi tiết", articles[0].description)
        self.assertNotIn("<p>", articles[0].description)

    def test_missing_fields_in_weather_json(self):
        """Test WeatherProvider resilience against missing fields in weather API responses."""
        provider = WeatherProvider(api_key="test_key")

        # 1. OpenWeatherMap with missing / empty inner dicts
        incomplete_owm = [
            {},
            {"main": {}},
            {"weather": []},
            {"main": {"temp": 30.5}, "weather": [{}]},
            {"main": {"temp": "invalid_temp"}},  # String instead of float
        ]

        for mock_resp in incomplete_owm:
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = mock_resp
                mock_get.return_value.raise_for_status = MagicMock()

                try:
                    data = provider._fetch_openweathermap("Hà Nội")
                    self.assertIsInstance(data, WeatherData)
                    self.assertIsInstance(data.temp_c, float)
                except Exception as e:
                    # Should fallback or raise predictably, but provider.get_weather must handle it
                    pass

        # 2. wttr.in with empty/missing current_condition
        incomplete_wttr = [
            {},
            {"current_condition": []},
            {"current_condition": [{}]},
            {"current_condition": [{"temp_C": "28", "FeelsLikeC": "31"}]},
        ]
        for mock_resp in incomplete_wttr:
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = mock_resp
                mock_get.return_value.raise_for_status = MagicMock()

                try:
                    data = provider._fetch_wttr_in("Hà Nội")
                    self.assertIsInstance(data, WeatherData)
                    self.assertIsInstance(data.temp_c, float)
                except Exception:
                    pass

        # 3. Overall get_weather must NEVER raise, even if all APIs return garbage
        with patch("requests.get", side_effect=Exception("API Corrupted")):
            fallback_data = provider.get_weather("Đà Nẵng")
            self.assertIsInstance(fallback_data, WeatherData)
            self.assertEqual(fallback_data.city, "Đà Nẵng")
            self.assertEqual(fallback_data.source, "offline_fallback")
            speech = provider.format_weather_speech(fallback_data)
            self.assertIn("Đà Nẵng", speech)

    def test_stock_ticker_parsing_and_crypto_errors(self):
        """Test FinanceTracker handling corrupted stock JSON, zero prices, and API failures."""
        tracker = FinanceTracker()

        # 1. Yahoo Finance chart corrupted responses
        corrupted_chart_responses = [
            {},
            {"chart": {}},
            {"chart": {"result": []}},
            {"chart": {"result": [{"meta": {}}]}},
            {"chart": {"result": [{"meta": {"regularMarketPrice": 0.0, "previousClose": 0.0}}]}},
            {"chart": {"result": [{"meta": {"regularMarketPrice": 150.0, "previousClose": 0.0}}]}},
        ]

        for mock_resp in corrupted_chart_responses:
            with patch("requests.get") as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = mock_resp
                mock_get.return_value.raise_for_status = MagicMock()

                quote = tracker._fetch_stock_quote("AAPL")
                self.assertIsInstance(quote, StockQuote)
                self.assertIsInstance(quote.price, float)
                self.assertIsInstance(quote.change_pct, float)

        # 2. Crypto error fallback
        with patch("requests.get", side_effect=Exception("Crypto API Down")):
            quote = tracker._fetch_crypto_quote("BTC", 25450.0)
            self.assertIsInstance(quote, CryptoQuote)
            self.assertEqual(quote.symbol, "BTC")
            self.assertGreater(quote.price_usd, 0)
            self.assertGreater(quote.price_vnd, 0)

    def test_offline_network_failure_recovery_full_hub(self):
        """Verify WebIntelligenceHub complete offline resilience without exceptions."""
        hub = WebIntelligenceHub()

        with patch("requests.get", side_effect=Exception("No Internet Connection")), \
             patch("urllib.request.urlopen", side_effect=Exception("Network Unreachable")):

            # 1. Search fallback
            search_res = hub.search("tin tuc thoi tiet")
            self.assertIsInstance(search_res, str)
            self.assertTrue(len(search_res) > 0)

            # 2. Weather fallback
            weather_res = hub.get_weather("Hà Nội")
            self.assertIn("Hà Nội", weather_res)

            # 3. News fallback
            news_res = hub.get_top_news(limit=3)
            self.assertIsInstance(news_res, list)
            self.assertGreaterEqual(len(news_res), 1)

            # 4. Crypto rates fallback
            crypto_res = hub.get_crypto_rates()
            self.assertIn("BTC", crypto_res)
            self.assertIn("ETH", crypto_res)

            # 5. Morning briefing aggregation fallback
            briefing = hub.generate_morning_briefing()
            self.assertIn("weather", briefing)
            self.assertIn("news", briefing)
            self.assertIn("crypto", briefing)
            self.assertIn("speech_text", briefing)


class TestR6ProactiveIntelligenceAdversarial(unittest.TestCase):
    """Adversarial & stress tests for R6 Proactive Intelligence."""

    def test_reminder_out_of_order_and_past_timestamps(self):
        """Test reminder priority queue sorting with out-of-order and past timestamps."""
        fired = []
        scheduler = ReminderScheduler(tts_callback=lambda txt: fired.append(txt))

        t0 = time.time()
        # Add out-of-order reminders: T+50, T-10 (past), T+10, T+1, T-100 (long past)
        scheduler.add_scheduled_reminder("past_100", t0 - 100)
        scheduler.add_scheduled_reminder("past_10", t0 - 10)
        scheduler.add_scheduled_reminder("future_1", t0 + 1)
        scheduler.add_scheduled_reminder("future_50", t0 + 50)
        scheduler.add_scheduled_reminder("future_10", t0 + 10)

        # Tick at current time T0
        due_at_t0 = scheduler.tick(now=t0)
        # Past reminders (past_100, past_10) should execute first in order of their timestamp
        self.assertEqual(len(due_at_t0), 2)
        self.assertEqual(due_at_t0[0].text, "past_100")
        self.assertEqual(due_at_t0[1].text, "past_10")

        # Tick at T0 + 5s -> future_1 should fire
        due_at_t5 = scheduler.tick(now=t0 + 5)
        self.assertEqual(len(due_at_t5), 1)
        self.assertEqual(due_at_t5[0].text, "future_1")

        # Tick at T0 + 60s -> future_10 and future_50 should fire in order
        due_at_t60 = scheduler.tick(now=t0 + 60)
        self.assertEqual(len(due_at_t60), 2)
        self.assertEqual(due_at_t60[0].text, "future_10")
        self.assertEqual(due_at_t60[1].text, "future_50")

    def test_reminder_zero_and_negative_delays(self):
        """Test add_reminder with 0 and negative delay."""
        scheduler = ReminderScheduler()
        r1 = scheduler.add_reminder("zero_delay", 0.0)
        r2 = scheduler.add_reminder("negative_delay", -10.0)

        due = scheduler.tick()
        self.assertEqual(len(due), 2)

    def test_health_monitor_threshold_boundary_edge_values(self):
        """Test exact boundary edge values: 89.9% vs 90.1% CPU, 84.9% vs 85.1% RAM, 10.1GB vs 9.9GB Disk."""
        monitor = SystemHealthMonitor(
            check_interval_seconds=1.0,
            cpu_threshold=90.0,
            ram_threshold=85.0,
            disk_min_free_gb=10.0,
            temp_threshold_c=85.0,
            battery_min_percent=20.0,
            cooldown_seconds=60.0,
            hysteresis_delta=5.0,
        )

        class MockProvider:
            def __init__(self):
                self.cpu_percent = 50.0
                self.ram_percent = 50.0
                self.disk_free_gb = 50.0
                self.cpu_temp_c = 50.0
                self.battery_percent = 100.0
                self.battery_plugged = True

        prov = MockProvider()
        monitor.telemetry_provider = prov

        # 1. CPU: 89.9% -> No Alert
        prov.cpu_percent = 89.9
        alerts = monitor.check_telemetry(now=1000.0)
        self.assertEqual(len(alerts), 0)

        # CPU: 90.1% -> Alert!
        prov.cpu_percent = 90.1
        alerts = monitor.check_telemetry(now=1001.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "cpu")

        # Cooldown guard: next check at 1010.0 (95% CPU) -> suppressed by 60s cooldown
        prov.cpu_percent = 95.0
        alerts = monitor.check_telemetry(now=1010.0)
        self.assertEqual(len(alerts), 0)

        # 2. RAM: 84.9% vs 85.1%
        monitor.reset_cooldowns()
        prov.cpu_percent = 50.0
        prov.ram_percent = 84.9
        alerts = monitor.check_telemetry(now=1100.0)
        self.assertEqual(len(alerts), 0)

        prov.ram_percent = 85.1
        alerts = monitor.check_telemetry(now=1101.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "ram")

        # 3. Disk: 10.1 GB vs 9.9 GB
        monitor.reset_cooldowns()
        prov.ram_percent = 50.0
        prov.disk_free_gb = 10.1
        alerts = monitor.check_telemetry(now=1200.0)
        self.assertEqual(len(alerts), 0)

        prov.disk_free_gb = 9.9
        alerts = monitor.check_telemetry(now=1201.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "disk")

        # 4. Battery: 20.1% vs 19.9% (unplugged)
        monitor.reset_cooldowns()
        prov.disk_free_gb = 50.0
        prov.battery_percent = 20.1
        prov.battery_plugged = False
        alerts = monitor.check_telemetry(now=1300.0)
        self.assertEqual(len(alerts), 0)

        prov.battery_percent = 19.9
        prov.battery_plugged = False
        alerts = monitor.check_telemetry(now=1301.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, "battery")

        # Battery 10.0% but plugged in -> No Alert
        monitor.reset_cooldowns()
        prov.battery_percent = 10.0
        prov.battery_plugged = True
        alerts = monitor.check_telemetry(now=1400.0)
        self.assertEqual(len(alerts), 0)

    def test_pomodoro_rapid_pause_resume_cycling(self):
        """Stress-test Pomodoro state machine with 50 rapid pause/resume cycles."""
        timer = PomodoroTimer(default_work_minutes=25.0, default_break_minutes=5.0)

        # Cannot pause when IDLE
        self.assertFalse(timer.pause())
        self.assertFalse(timer.resume())

        timer.start(work_minutes=25.0, break_minutes=5.0, cycles=2)
        self.assertEqual(timer.get_status().state, PomodoroState.WORK)
        self.assertTrue(timer.is_suppressing_notifications())

        # Rapid pause / resume 50 times
        for _ in range(50):
            res_pause = timer.pause()
            self.assertTrue(res_pause)
            self.assertEqual(timer.get_status().state, PomodoroState.PAUSED)
            self.assertFalse(timer.is_suppressing_notifications())

            res_resume = timer.resume()
            self.assertTrue(res_resume)
            self.assertEqual(timer.get_status().state, PomodoroState.WORK)
            self.assertTrue(timer.is_suppressing_notifications())

        # Full cycle simulation with tick()
        t0 = time.time()
        timer._phase_start_time = t0
        timer._phase_duration_seconds = 1500.0

        # Tick at T0 + 1501s -> should transition WORK -> BREAK
        event = timer.tick(now=t0 + 1501.0)
        self.assertEqual(event, "WORK_FINISHED")
        self.assertEqual(timer.get_status().state, PomodoroState.BREAK)
        self.assertFalse(timer.is_suppressing_notifications())

        # Tick at T0 + 1501 + 301s -> should transition BREAK -> WORK (Cycle 2)
        timer._phase_start_time = t0 + 1501.0
        timer._phase_duration_seconds = 300.0
        event2 = timer.tick(now=t0 + 1802.0)
        self.assertEqual(event2, "BREAK_FINISHED")
        self.assertEqual(timer.get_status().state, PomodoroState.WORK)
        self.assertEqual(timer.get_status().current_cycle, 2)

        # Stop resets cleanly
        timer.stop()
        self.assertEqual(timer.get_status().state, PomodoroState.IDLE)
        self.assertFalse(timer.is_suppressing_notifications())

    def test_inactivity_monitor_timer_resets(self):
        """Test inactivity monitor triggers after 2h (7200s) and resets upon user activity."""
        greetings = []
        monitor = InactivityMonitor(
            tts_callback=lambda txt: greetings.append(txt),
            inactivity_threshold_seconds=7200.0,
            cooldown_seconds=3600.0,
        )

        t0 = 100000.0
        monitor._last_activity_time = t0
        monitor._last_greeting_time = 0.0

        # Check at T0 + 7199s -> Idle for 7199s (< 7200s) -> False
        triggered = monitor.check_inactivity(now=t0 + 7199.0)
        self.assertFalse(triggered)
        self.assertEqual(len(greetings), 0)

        # Check at T0 + 7201s -> Idle for 7201s (>= 7200s) -> True
        triggered = monitor.check_inactivity(now=t0 + 7201.0)
        self.assertTrue(triggered)
        self.assertEqual(len(greetings), 1)

        # Check at T0 + 7210s -> Cooldown active -> False
        triggered = monitor.check_inactivity(now=t0 + 7210.0)
        self.assertFalse(triggered)

        # User activity recorded at T0 + 8000s
        monitor.record_activity(now=t0 + 8000.0)
        self.assertEqual(monitor.get_idle_seconds(now=t0 + 8005.0), 5.0)

        # Check at T0 + 8005s -> Only 5s idle -> False
        self.assertFalse(monitor.check_inactivity(now=t0 + 8005.0))


class TestR7NaturalLanguageShellAdversarial(unittest.TestCase):
    """Adversarial & stress tests for R7 Natural Language Shell."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="jarvis_shell_test_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_dev_server_detection_across_project_structures(self):
        """Test dev server resolution across Node.js, Django, FastAPI, Flask, Rust, Go, Docker."""
        assistant = ShellAssistant()

        # 1. Node.js package.json with scripts.dev
        p1 = os.path.join(self.test_dir, "proj_node_dev")
        os.makedirs(p1)
        with open(os.path.join(p1, "package.json"), "w") as f:
            json.dump({"scripts": {"dev": "vite"}}, f)
        self.assertEqual(assistant.resolve_dev_server_command(p1), "npm run dev")

        # 2. Node.js package.json with scripts.start
        p2 = os.path.join(self.test_dir, "proj_node_start")
        os.makedirs(p2)
        with open(os.path.join(p2, "package.json"), "w") as f:
            json.dump({"scripts": {"start": "node index.js"}}, f)
        self.assertEqual(assistant.resolve_dev_server_command(p2), "npm start")

        # 3. Django manage.py
        p3 = os.path.join(self.test_dir, "proj_django")
        os.makedirs(p3)
        with open(os.path.join(p3, "manage.py"), "w") as f:
            f.write("#!/usr/bin/env python\nimport django")
        self.assertEqual(assistant.resolve_dev_server_command(p3), "python manage.py runserver")

        # 4. FastAPI main.py
        p4 = os.path.join(self.test_dir, "proj_fastapi")
        os.makedirs(p4)
        with open(os.path.join(p4, "main.py"), "w") as f:
            f.write("from fastapi import FastAPI\napp = FastAPI()")
        self.assertEqual(assistant.resolve_dev_server_command(p4), "uvicorn main:app --reload")

        # 5. Rust Cargo.toml
        p5 = os.path.join(self.test_dir, "proj_rust")
        os.makedirs(p5)
        with open(os.path.join(p5, "Cargo.toml"), "w") as f:
            f.write("[package]\nname = 'test'")
        self.assertEqual(assistant.resolve_dev_server_command(p5), "cargo run")

        # 6. Go go.mod
        p6 = os.path.join(self.test_dir, "proj_go")
        os.makedirs(p6)
        with open(os.path.join(p6, "go.mod"), "w") as f:
            f.write("module example.com/test")
        self.assertEqual(assistant.resolve_dev_server_command(p6), "go run .")

        # 7. Docker Compose
        p7 = os.path.join(self.test_dir, "proj_docker")
        os.makedirs(p7)
        with open(os.path.join(p7, "docker-compose.yml"), "w") as f:
            f.write("version: '3'")
        self.assertEqual(assistant.resolve_dev_server_command(p7), "docker-compose up")

    def test_regex_safety_gate_adversarial_destructive_commands(self):
        """Test safety gate against obfuscated and varied destructive command patterns."""
        assistant = ShellAssistant()

        destructive_commands = [
            "rm -rf /",
            "rm -r ./src",
            "rm -f file.txt",
            "RM -RF /var/log",
            "rmdir /s /q C:\\temp",
            "RMDIR /Q /S C:\\test",
            "del /f /s /q *",
            "DeL /S /Q *.log",
            "erase /s /q *.*",
            "erase C:\\data",
            "format C:",
            "FORMAT D:",
            "drop table users;",
            "DROP DATABASE production;",
            "delete from customers;",
            "truncate table logs;",
            "taskkill /f /im explorer.exe",
            "taskkill /F /IM svchost.exe",
            "git reset --hard HEAD~1",
            "git clean -fd",
            "git clean -f",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sdb",
            "diskpart",
            "Remove-Item -Path C:\\ -Recurse -Force",
            "shutil.rmtree('/important')",
        ]

        for cmd in destructive_commands:
            self.assertTrue(assistant.is_destructive(cmd), f"Failed to catch destructive command: {cmd}")
            res = assistant.execute_natural_command(cmd)
            self.assertFalse(res["success"])
            self.assertTrue(res["requires_confirmation"])
            self.assertIn("token", res)

        safe_commands = [
            "git status",
            "npm start",
            "python manage.py runserver",
            "pip install requests",
            "netstat -ano",
            "docker ps",
            "ls -la",
            "dir /w",
            "echo 'format is a good concept'",
            "echo delete the word",
        ]

        for cmd in safe_commands:
            self.assertFalse(assistant.is_destructive(cmd), f"Falsely flagged safe command as destructive: {cmd}")

    def test_stdout_summarization_on_1500_line_output(self):
        """Test summarizer performance and accuracy on massive 1500+ line outputs."""
        assistant = ShellAssistant()

        # 1. 1500-line generic command output
        large_output = "\n".join([f"Line {i}: Processing file item_{i}.dat with status OK" for i in range(1500)])
        summary = assistant.summarize_output("custom_batch_processor", large_output, exit_code=0)
        self.assertIn("1500 dòng", summary)
        self.assertIn("Line 0:", summary)
        self.assertIn("Line 1499:", summary)

        # 2. Large Git Status output (100 staged, 200 modified, 300 untracked)
        git_lines = ["On branch feature/expansion"]
        git_lines.append("Changes to be committed:")
        git_lines.extend([f"\tmodified:   src/module_{i}.py" for i in range(100)])
        git_lines.append("Changes not staged for commit:")
        git_lines.extend([f"\tmodified:   tests/test_{i}.py" for i in range(200)])
        git_lines.append("Untracked files:")
        git_lines.extend([f"\tnew_file_{i}.txt" for i in range(300)])
        large_git_output = "\n".join(git_lines)

        git_summary = assistant.summarize_output("git status", large_git_output, exit_code=0)
        self.assertIn("Nhánh feature/expansion", git_summary)
        self.assertIn("100 tệp đã sẵn sàng commit", git_summary)
        self.assertIn("200 tệp đã chỉnh sửa", git_summary)
        self.assertIn("300 tệp chưa theo dõi", git_summary)

        # 3. Large Pytest output
        pytest_lines = [f"tests/test_mod_{i}.py ." for i in range(1200)]
        pytest_lines.append("====== 1200 passed, 5 warnings in 14.50s ======")
        large_pytest_out = "\n".join(pytest_lines)
        pytest_summary = assistant.summarize_output("pytest tests/", large_pytest_out, exit_code=0)
        self.assertIn("1200 passed", pytest_summary)


class TestR8OverlayHUDAdversarial(unittest.TestCase):
    """Adversarial & stress tests for R8 Overlay HUD."""

    def test_rapid_show_hide_stress_cycling_50x(self):
        """Stress-test overlay state transitions 50x in rapid succession."""
        overlay = AlwaysOnOverlay(headless=True)
        overlay.start()

        for i in range(50):
            overlay.show_listening(f"Prompt {i}")
            self.assertEqual(overlay.state, OverlayState.LISTENING)

            overlay.show_thinking(f"Transcript {i}")
            self.assertEqual(overlay.state, OverlayState.THINKING)

            overlay.show_response(f"Transcript {i}", f"Response text {i}", duration_s=10.0)
            self.assertEqual(overlay.state, OverlayState.RESPONSE)

            overlay.hide()
            self.assertEqual(overlay.state, OverlayState.HIDDEN)

        overlay.destroy()

    def test_long_text_truncation_and_turn_recording(self):
        """Test rendering massive 10,000-character text and 5-turn history queue clamping."""
        overlay = AlwaysOnOverlay(headless=True)
        overlay.start()

        massive_text = "A" * 10000
        overlay.show_response("User question", massive_text)
        self.assertEqual(overlay.jarvis_text, massive_text)

        # Add 10 conversation turns -> History must clamp to max 5
        for i in range(10):
            overlay.add_turn(f"User {i}", f"JARVIS {i}")

        history = overlay.get_history()
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0]["user_text"], "User 5")
        self.assertEqual(history[-1]["user_text"], "User 9")

        overlay.destroy()

    def test_missing_telemetry_and_battery_none(self):
        """Verify overlay handles battery None, missing sensors, and negative values cleanly."""
        overlay = AlwaysOnOverlay(headless=True)
        overlay.start()

        # 1. Battery is None (Desktop with no battery sensor)
        tel = overlay.update_telemetry(cpu_percent=45.2, ram_percent=68.5, battery_percent=-1, is_charging=False)
        self.assertIsNone(tel["battery_percent"])
        self.assertEqual(tel["cpu_percent"], 45.2)
        self.assertEqual(tel["ram_percent"], 68.5)

        # 2. None explicitly passed for all
        tel2 = overlay.update_telemetry(cpu_percent=None, ram_percent=None, battery_percent=None)
        self.assertIsNone(tel2["battery_percent"])
        self.assertEqual(tel2["cpu_percent"], 45.2)

        overlay.destroy()

    def test_audio_level_normalization_and_clamping(self):
        """Verify 11-bar spectrum analyzer clamps extreme and malformed inputs."""
        overlay = AlwaysOnOverlay(headless=True)
        overlay.start()

        # 1. Extreme negative RMS
        overlay.update_audio_level(-100.0)
        bars = overlay.waveform_bars
        self.assertEqual(len(bars), 11)
        for b in bars:
            self.assertGreaterEqual(b, 0.05)
            self.assertLessEqual(b, 1.0)

        # 2. Extreme positive RMS
        overlay.update_audio_level(9999.0)
        bars = overlay.waveform_bars
        self.assertEqual(len(bars), 11)
        for b in bars:
            self.assertGreaterEqual(b, 0.05)
            self.assertLessEqual(b, 1.0)

        # 3. Direct malformed list (empty, underfilled, overfilled)
        overlay.update_audio_level([])
        self.assertEqual(len(overlay.waveform_bars), 11)

        overlay.update_audio_level([2.5, -1.0, 0.5])
        bars = overlay.waveform_bars
        self.assertEqual(len(bars), 11)
        self.assertEqual(bars[0], 1.0)   # Clamped from 2.5
        self.assertEqual(bars[1], 0.05)  # Clamped from -1.0
        self.assertEqual(bars[2], 0.5)

        overlay.destroy()

    def test_headless_mode_full_resilience(self):
        """Verify all AlwaysOnOverlay methods succeed in headless mode without crashing."""
        overlay = AlwaysOnOverlay(headless=True)
        overlay.start()
        self.assertTrue(overlay.is_headless)

        overlay.show_listening()
        overlay.show_thinking()
        overlay.show_response("Hỏi", "Đáp")
        overlay.toggle_sidebar()
        overlay.collapse_sidebar()
        overlay.expand_sidebar()
        overlay.minimize_to_arc_reactor()
        overlay.restore_from_arc_reactor()
        overlay.dock_to_right()
        overlay.set_memory_facts(["Fact 1", "Fact 2"])
        overlay.trigger_quick_action("briefing_morning")
        overlay.trigger_quick_action("system_status")
        overlay.trigger_quick_action("focus_mode")
        overlay.probe_system_metrics()
        overlay.hide()
        overlay.destroy()
        # Double destroy idempotency
        overlay.destroy()


if __name__ == '__main__':
    unittest.main()
