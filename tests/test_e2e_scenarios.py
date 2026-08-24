"""
tests/test_e2e_scenarios.py
===========================
End-to-End Integration Scenarios and Real-World User Workflows.
Covering:
  - F-31: Workspace VM Orchestrator (VMware & VirtualBox CLI management)
  - F-32: IDE & Terminal Workspace Prep (Cursor/VS Code & Windows Terminal recipes)
  - Tier 3 Cross-Feature Interactions (Pipelines combining Audio, Vision, Hardware, LLM, Comms, IoT)
  - Tier 4 Real-World Application Workflows (Morning Routine, Crisis Healing, Security Audit, Offline Resilience)
"""

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pytest

from jarvis.automation.vm import VMOrchestrator
from jarvis.automation.workspace import WorkspaceRecipeManager
from jarvis.comms.telegram import TelegramBotController
from jarvis.data.document import DocumentExporter
from jarvis.data.stats import DataAnalyticsEngine, DataStatsReport, MonteCarloEngine
from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.vision.biometrics import BiometricPrivilegeGate, BiometricsEngine

from tests.test_audio_dsp import AudioDSPProcessor
from tests.test_gesture_detector import GestureDetector
from tests.test_hardware_monitor import HardwareMonitor
from tests.test_llm_router import LLMClient, LLMIntentRouter, STTEngine
from tests.test_security_scanner import NmapScannerWrapper, SecurityReportGenerator
from tests.test_self_healing import HealingEngine
from tests.test_tts_engine import TTSEngine


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_workspace_vm_orchestrator_tier1():
    """
    [F-31] Validate VM orchestrator executes vmrun / VBoxManage start commands.
    """
    orchestrator = VMOrchestrator()
    res = orchestrator.start_vm("UbuntuDev", hypervisor="vmware")
    assert res["success"] is True
    assert res["state"] == "RUNNING"


def test_workspace_ide_and_terminal_prep_tier1():
    """
    [F-32] Validate workspace recipe manager launches configured IDE and Windows Terminal tabs.
    """
    manager = WorkspaceRecipeManager()
    res = manager.prepare_workspace("ai_development")
    assert res["success"] is True
    assert "cursor.exe" in res["launched_apps"]


# ============================================================================
# TIER 3: CROSS-FEATURE INTERACTION SCENARIOS
# ============================================================================

def test_e2e_tier3_gesture_to_multiaction_and_tts(mock_audio_stream, mock_http_server, tmp_path):
    """
    [Tier 3] Pipeline: Acoustic Double Clap (F-05) -> Triggers Multi-Action Fanout -> ElevenLabs TTS Welcome (F-11, F-12).
    """
    detector = GestureDetector()
    tts = TTSEngine(api_key="valid_eleven_key", cache_dir=tmp_path)

    # 1. Feed synthetic double clap
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15)
    events = detector.process_stream(pcm)
    assert len(events) == 1
    assert events[0].pattern_type == "DOUBLE_CLAP"

    # 2. Trigger TTS Welcome
    spoken = tts.speak("Welcome back, Sir. Initializing morning workspace.", mock_http=mock_http_server)
    assert spoken is True
    assert len(mock_http_server.elevenlabs_calls) == 1


def test_e2e_tier3_voice_command_to_smart_home_with_tts(audio_synthesizer, mock_http_server):
    """
    [Tier 3] Pipeline: Voice STT (F-14) -> LLM Intent (F-15) -> Home Assistant Light (F-26) -> Spoken Confirmation.
    """
    stt = STTEngine()
    llm = LLMIntentRouter(LLMClient(provider="gemini", api_key="test_key"))
    ha = HomeAssistantClient()

    # 1. Transcribe voice
    voice = audio_synthesizer.generate_noise(0.4, rms=0.04)
    text = stt.transcribe(voice)

    # 2. Intent Routing
    intent = llm.parse_intent(text)
    assert intent.action_name == "home_assistant_call"

    # 3. Smart Home Call
    res = ha.call_service(
        intent.parameters["domain"],
        intent.parameters["service"],
        {"entity_id": intent.parameters["entity_id"]},
        mock_http=mock_http_server,
    )
    assert res["success"] is True

    # 4. Verify light turned on
    state = ha.get_state("light.living_room", mock_http=mock_http_server)
    assert state["state"] == "on"


def test_e2e_tier3_intruder_to_lock_and_telegram(mock_camera_feed, mock_win32_platform, mock_http_server):
    """
    [Tier 3] Pipeline: Unknown Face (F-33, F-35) -> Win32 LockWorkStation (F-35) -> Telegram Photo Alert (F-38).
    """
    biometrics = BiometricsEngine(mock_camera_feed)
    stranger_frame = mock_camera_feed.get_stranger_frame()

    res = biometrics.process_surveillance_frame(stranger_frame, mock_win32_platform, mock_http_server)
    assert res["locked"] is True
    assert mock_win32_platform.lock_workstation_calls == 1
    assert len(mock_http_server.telegram_sent_photos) == 1


def test_e2e_tier3_hardware_overheat_to_voice_alert(mock_hardware_provider):
    """
    [Tier 3] Pipeline: Hardware Overheat (F-20, F-22) -> Threshold Alert Trigger -> Voice Warning Formatting.
    """
    mock_hardware_provider.set_cpu(percent=85.0, temp_c=94.0)
    monitor = HardwareMonitor(mock_hardware_provider, cpu_temp_threshold=85.0)

    alerts = monitor.check_thresholds()
    assert len(alerts) >= 1
    assert "94.0" in alerts[0]["message"]


def test_e2e_tier3_privilege_gated_nmap_scan_flow(mock_camera_feed, monkeypatch, tmp_path):
    """
    [Tier 3] Pipeline: Security Scan Request -> Biometric Face Auth (F-33, F-34) -> Nmap Audit (F-23) -> Report (F-25).
    """
    import shutil
    monkeypatch.setattr(shutil, "which", lambda c: "nmap.exe")

    biometrics = BiometricsEngine(mock_camera_feed)
    gate = BiometricPrivilegeGate(biometrics)
    nmap = NmapScannerWrapper()
    reporter = SecurityReportGenerator()

    # 1. Authenticate with owner face
    ctx = gate.authenticate(mock_camera_feed.get_owner_frame())
    assert gate.is_allowed("nmap_scan", ctx) is True

    # 2. Execute Scan & Generate Report
    scan = nmap.scan_subnet("192.168.1.0/24")
    report = reporter.generate_report(scan, tmp_path)

    assert report["report_path"].exists()
    assert report["total_hosts"] >= 2


def test_e2e_tier3_unresponsive_app_healing_flow(mock_hardware_provider, mock_win32_platform):
    """
    [Tier 3] Pipeline: Hung App Detection (F-42) -> Watchdog Trigger (F-41) -> Autonomous Kill (F-43) -> RAM Drop.
    """
    mock_hardware_provider.set_ram(93.0)
    mock_win32_platform.add_hung_window("frozen_browser.exe", pid=3344)

    engine = HealingEngine(mock_win32_platform, mock_hardware_provider, auto_kill=True)
    hung = engine.find_hung_windows()
    assert len(hung) == 1

    report = engine.heal_hung_process(hung[0].pid, hung[0].process_name)
    assert report["success"] is True
    assert mock_hardware_provider.ram_percent < 80.0


def test_e2e_tier3_data_file_to_docx_and_voice(tmp_path):
    """
    [Tier 3] Pipeline: CSV Ingestion (F-28) -> Monte Carlo Simulation (F-29) -> DOCX Export (F-30) -> Voice Summary.
    """
    import csv
    csv_file = tmp_path / "financial.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "value"])
        for v in [50, 75, 100, 125, 150, 175, 200]:
            writer.writerow([1, v])

    analytics = DataAnalyticsEngine()
    mc = MonteCarloEngine()
    exporter = DocumentExporter()

    stats = analytics.compute_statistics_from_csv(csv_file)
    sim = mc.run_simulation(initial_value=stats.mean, iterations=2000)
    out_file = exporter.export_report(stats, sim, tmp_path / "fin_report.docx")

    assert out_file.exists()
    summary = exporter.get_voice_summary("financial.csv", stats, sim)
    assert "Đã hoàn thành phân tích" in summary


# ============================================================================
# TIER 4: REAL-WORLD APPLICATION WORKFLOWS
# ============================================================================

def test_e2e_tier4_full_morning_workspace_automation_workflow(mock_audio_stream, mock_http_server, tmp_path):
    """
    [Tier 4] Full Morning Automation: Double clap acoustic trigger -> Launches Spotify -> Snaps Chrome Claude
    and Binance -> Speaks ElevenLabs welcome message -> Boots developer VM -> Opens Windows Terminal.
    """
    detector = GestureDetector()
    tts = TTSEngine(api_key="eleven_key", cache_dir=tmp_path)
    vm = VMOrchestrator()
    workspace = WorkspaceRecipeManager()

    # Step 1: Acoustic trigger
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15)
    events = detector.process_stream(pcm)
    assert len(events) == 1

    # Step 2: Spoken welcome greeting
    spoken = tts.speak("Chào buổi sáng. Đang chuẩn bị không gian làm việc.", mock_http=mock_http_server)
    assert spoken is True

    # Step 3: Boot developer VM & Launch workspaces
    vm_res = vm.start_vm("UbuntuDev")
    assert vm_res["success"] is True

    ws_res = workspace.prepare_workspace("ai_development")
    assert ws_res["success"] is True
    assert "cursor.exe" in ws_res["launched_apps"]


def test_e2e_tier4_system_crisis_self_healing_workflow(mock_hardware_provider, mock_win32_platform):
    """
    [Tier 4] Crisis Self-Healing: RAM reaches 95% + Chrome hung window -> Watchdog safely kills hung worker
    -> Reclaims RAM below 75% -> Announces vocal healing status.
    """
    mock_hardware_provider.set_ram(96.0)
    mock_win32_platform.add_hung_window("chrome.exe", pid=6677)

    engine = HealingEngine(mock_win32_platform, mock_hardware_provider, auto_kill=True)
    assert engine.is_ram_critical() is True

    hung_apps = engine.find_hung_windows()
    assert len(hung_apps) == 1

    report = engine.heal_hung_process(hung_apps[0].pid, hung_apps[0].process_name)
    assert report["success"] is True
    assert mock_hardware_provider.ram_percent < 75.0
    assert "Hệ thống bị quá tải. Đã xử lý: chrome.exe" in report["spoken_message"]


def test_e2e_tier4_security_audit_and_incident_workflow(mock_camera_feed, mock_win32_platform, mock_http_server, tmp_path, monkeypatch):
    """
    [Tier 4] Remote Security Audit: Telegram remote /exec command -> Biometric challenge token verification
    -> Nmap subnet scan -> Markdown report generated -> Spoken risk summary returned.
    """
    import shutil
    monkeypatch.setattr(shutil, "which", lambda c: "nmap.exe")

    bot = TelegramBotController(allowed_user_ids={12345}, win32_platform=mock_win32_platform)
    gate = BiometricPrivilegeGate(BiometricsEngine(mock_camera_feed))
    nmap = NmapScannerWrapper()
    reporter = SecurityReportGenerator()

    # Step 1: Telegram command
    cmd_res = bot.handle_inbound_message(user_id=12345, text="/exec scan_subnet")
    assert cmd_res["status"] == 200

    # Step 2: Biometric check
    auth = gate.authenticate(mock_camera_feed.get_owner_frame())
    assert gate.is_allowed("nmap_scan", auth) is True

    # Step 3: Run scan and build report
    scan = nmap.scan_subnet("192.168.1.0/24")
    report = reporter.generate_report(scan, tmp_path)
    assert report["report_path"].exists()
    assert "hoàn thành" in report["voice_summary"]


def test_e2e_tier4_offline_resilience_and_graceful_degradation_workflow(mock_audio_stream, tmp_path):
    """
    [Tier 4] Offline Resilience: Complete Internet disconnection simulated -> Double clap trigger occurs
    -> Local SAPI5 fallback speaks greeting -> Local rule engine handles commands -> Zero crashes.
    """
    detector = GestureDetector()
    # Offline TTS (no API key, mock_http=None)
    tts = TTSEngine(api_key="", cache_dir=tmp_path)
    llm = LLMIntentRouter(LLMClient(provider="openai", api_key=""))

    # Step 1: Trigger gesture
    events = detector.process_stream(mock_audio_stream.generate_double_clap())
    assert len(events) == 1

    # Step 2: Speak via offline fallback SAPI5
    spoken = tts.speak("Offline fallback active.", mock_http=None)
    assert spoken is True
    assert "Offline fallback active." in tts.offline_calls

    # Step 3: Local rule engine parses intent without cloud LLM
    intent = llm.parse_intent("tình trạng hệ thống")
    assert intent.action_name == "hardware_status_query"
    assert intent.source == "rule_fallback"
