"""
tests/test_audit_adversarial_probes.py
======================================
Adversarial Probing & Runtime Boundary Testing Suite for JARVIS Independent Audit (Requirement R3).
Evaluates real production classes from `jarvis` across the 4 technical axes defined in AUDIT_FRAMEWORK.md.

Probe Matrix:
  - Probe 1: ZaloBotController.send_message() Silent Fallback with missing access token.
  - Probe 2: DiscordBotController._poll_loop Ghost Process verification.
  - Probe 3: TelegramBotController command handlers (/exec, /note, /calc) Silent Fallback when dispatcher=None.
  - Probe 4: ComputerController.set_volume() Silent Fallback and exception swallowing on hardware failure.
  - Probe 5: PacketCapture._parse_tshark_protocols() and line 769 packet_count fallback defect.
  - Probe 6: SecretsManager fail-closed behavior on nonexistent secret names.
  - Probe 7: CodeInterpreterSandbox Windows Job Object (ActiveProcessLimit=1) and MIC Low Integrity Hard Boundaries.
  - Probe 8: SemanticVectorStore concurrency, atomic file persistence, and transient lock retry loop.
"""
from __future__ import annotations

import concurrent.futures
import inspect
import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Production imports
from jarvis.comms.zalo import ZaloBotController, ZaloConfig, ZaloSendResult
from jarvis.comms.discord import DiscordBotController, DiscordConfig
from jarvis.comms.telegram import TelegramBotController
from jarvis.automation.control import ComputerController
from jarvis.security.scanner import PacketCapture, PacketCaptureResult, _parse_tshark_protocols
from jarvis.security.secrets import get_secret
from jarvis.security import secrets as SecretsManager
from jarvis.sandbox.interpreter import CodeInterpreterSandbox
from jarvis.sandbox.validator import ASTCodeValidator, ValidationResult
from jarvis.memory.vector_store import SemanticVectorStore, VectorStoreConfig


# ==============================================================================
# PROBE 1: Zalo Silent Fallback (Axis 2: Truthfulness)
# ==============================================================================

class TestProbe1ZaloSilentFallback:
    """
    Probe 1: Test ZaloBotController.send_message() with empty access_token.
    AUDIT_FRAMEWORK.md Pitfall #15: Silent Fallback returns success=True as default.
    AGENTS.md: Fail-closed is strictly required.

    Production Location: jarvis/comms/zalo.py:297-299:
        if self.is_mock or not self.config.access_token:
            log.info("Mock send to %s: %s", user_id, text[:60])
            return ZaloSendResult(success=True, message_id="mock_msg_id")
    """

    def test_zalo_send_message_empty_token_returns_silent_fallback_success(self):
        """
        Empirically verify that when is_mock=False but access_token is empty,
        production ZaloBotController silently falls back to returning success=True
        with a fabricated message_id='mock_msg_id'.
        """
        config = ZaloConfig(access_token="", oa_id="test_app", webhook_secret="test_sec")
        controller = ZaloBotController(config=config, is_mock=False)

        # Execute send with missing token
        result = controller.send_message(user_id="zalo_user_001", text="Adversarial probe ping")

        # ASSERT CURRENT BEHAVIOR: Returns success=True with mock_msg_id (SILENT FALLBACK)
        assert result.success is True, (
            "Observation: ZaloBotController.send_message() returns success=True when access_token is empty. "
            "This confirms Silent Fallback defect."
        )
        assert result.message_id == "mock_msg_id", (
            f"Expected 'mock_msg_id', got {result.message_id}"
        )
        assert not result.error

        # Document the fail-closed contract violation:
        # Under fail-closed (AUDIT_FRAMEWORK.md), an unauthenticated send must return success=False
        # with error_code="NOT_CONFIGURED" or "MISSING_TOKEN".


# ==============================================================================
# PROBE 2: Discord Ghost Process (Axis 2: Truthfulness)
# ==============================================================================

class TestProbe2DiscordGhostProcess:
    """
    Probe 2: Inspect DiscordBotController._poll_loop and test runtime execution.
    AUDIT_FRAMEWORK.md Pitfall #16: Ghost Process: thread runs without executing declared function.

    Production Location: jarvis/comms/discord.py:452-459:
        def _poll_loop(self) -> None:
            while self._running:
                try:
                    time.sleep(2.0)  # Poll every 2 seconds
                except Exception as exc:
                    log.error("Discord poll error: %s", exc)
                    time.sleep(5.0)
    """

    def test_discord_poll_loop_static_inspection(self):
        """
        Statically inspect DiscordBotController._poll_loop implementation
        to verify that it executes no Discord API or network calls.
        """
        source = inspect.getsource(DiscordBotController._poll_loop)

        # Verify it contains sleep loop
        assert "time.sleep(2.0)" in source, "Expected 2.0s sleep in _poll_loop"

        # Verify absence of network/API dispatch calls in loop body
        forbidden_calls = ["urlopen", "requests.", "http", "socket", "gateway", "post", "fetch"]
        for call in forbidden_calls:
            assert call not in source.lower(), f"Unexpected network call '{call}' found in _poll_loop"

    def test_discord_poll_loop_runtime_ghost_execution(self):
        """
        Run DiscordBotController polling thread briefly to verify that
        it spawns a live thread but executes zero API calls.
        """
        controller = DiscordBotController(bot_token="test_discord_token_xyz")

        _real_sleep = time.sleep
        sleep_calls = []

        def _mock_sleep(s):
            sleep_calls.append(s)
            _real_sleep(0.005)

        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("time.sleep", side_effect=_mock_sleep):

            controller.start_polling()
            assert controller._running is True
            assert controller._poll_thread is not None
            assert controller._poll_thread.is_alive()

            # Wait briefly for thread to iterate
            _real_sleep(0.05)

            # Stop polling
            controller.stop_polling()
            assert controller._running is False

            # Assert zero network requests were executed by the thread
            assert mock_urlopen.call_count == 0, (
                f"Expected 0 HTTP calls from Discord _poll_loop, but got {mock_urlopen.call_count}"
            )
            # Assert that the loop only called sleep
            assert len(sleep_calls) >= 1, "Expected sleep calls from poll loop"


# ==============================================================================
# PROBE 3: Telegram Dispatcher Silent Fallback (Axis 2: Truthfulness)
# ==============================================================================

class TestProbe3TelegramDispatcherSilentFallback:
    """
    Probe 3: Test TelegramBotController commands when dispatcher=None.
    AUDIT_FRAMEWORK.md Pitfall #15: Silent Fallback returns status 200 "Success".

    Production Location: jarvis/comms/telegram.py:181, 192, 220:
        /note -> returns {"status": 200, "text": f'📝 Đã lưu ghi chú: "{note_content}"'}
        /calc -> returns {"status": 200, "text": f"🔢 Đã tính toán: {calc_expr}"}
        /exec -> returns {"status": 200, "text": f"Đã thực thi lệnh: {cmd}"}
    """

    @pytest.fixture
    def unconfigured_controller(self):
        """TelegramBotController with valid token and authorized user, but NO dispatcher."""
        return TelegramBotController(
            bot_token="123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ",
            allowed_user_ids={1001},
            dispatcher=None,
        )

    def test_telegram_exec_silent_fallback_without_dispatcher(self, unconfigured_controller):
        """
        Empirically verify /exec returns 200 'Đã thực thi lệnh: ...' even though dispatcher is None.
        """
        command = "/exec shutdown /r /t 0"
        res = unconfigured_controller.handle_inbound_message(user_id=1001, text=command)

        assert res["status"] == 200, "Observation: Returns HTTP 200 despite missing dispatcher"
        assert "Đã thực thi lệnh: shutdown /r /t 0" in res["text"], (
            f"Expected execution claim in text, got: {res['text']}"
        )

    def test_telegram_note_silent_fallback_without_dispatcher(self, unconfigured_controller):
        """
        Empirically verify /note returns 200 'Đã lưu ghi chú: ...' even though dispatcher is None.
        """
        command = "/note Báo cáo tài chính quý 3"
        res = unconfigured_controller.handle_inbound_message(user_id=1001, text=command)

        assert res["status"] == 200, "Observation: Returns HTTP 200 despite missing dispatcher"
        assert 'Đã lưu ghi chú: "Báo cáo tài chính quý 3"' in res["text"]

    def test_telegram_calc_silent_fallback_without_dispatcher(self, unconfigured_controller):
        """
        Empirically verify /calc returns 200 'Đã tính toán: ...' even though dispatcher is None.
        """
        command = "/calc 25 * 4"
        res = unconfigured_controller.handle_inbound_message(user_id=1001, text=command)

        assert res["status"] == 200, "Observation: Returns HTTP 200 despite missing dispatcher"
        assert "Đã tính toán: 25 * 4" in res["text"]


# ==============================================================================
# PROBE 4: OS Volume Control Silent Fallback (Axis 2: Truthfulness & Axis 1)
# ==============================================================================

class TestProbe4OSVolumeControlSilentFallback:
    """
    Probe 4: Test ComputerController.set_volume() when audio endpoints fail.
    AUDIT_FRAMEWORK.md Pitfall #15: Silent Fallback swallows exceptions and caches state.

    Production Location: jarvis/automation/control.py:363-381:
        def set_volume(self, level_percent: int) -> int:
            level = max(0, min(100, int(level_percent)))
            self._current_volume = level
            try:
                speakers = AudioUtilities.GetSpeakers()
                ...
            except Exception:
                pass
            return self._current_volume
    """

    def test_set_volume_swallows_endpoint_failure_and_caches_volume(self):
        """
        Verify that ComputerController.set_volume() caches the volume level
        and swallows exceptions when AudioUtilities.GetSpeakers() raises an error.
        """
        controller = ComputerController()
        controller._current_volume = 20

        # Simulate audio hardware endpoint failure
        class MockBrokenAudioUtilities:
            @staticmethod
            def GetSpeakers():
                raise RuntimeError("COM error 0x80070490: Element not found (no audio endpoint)")

        with patch.dict(sys.modules, {
            "comtypes": MagicMock(),
            "pycaw": MagicMock(),
            "pycaw.pycaw": MagicMock(AudioUtilities=MockBrokenAudioUtilities),
        }):
            # Request setting volume to 75
            returned_volume = controller.set_volume(75)

            # Assert that the function swallowed the exception and returned 75
            assert returned_volume == 75, (
                f"Expected cached volume 75, got {returned_volume}"
            )
            assert controller._current_volume == 75, (
                f"Expected _current_volume 75, got {controller._current_volume}"
            )


# ==============================================================================
# PROBE 5: PacketCapture Line 769 Fallback Bug (Axis 2: Truthfulness)
# ==============================================================================

class TestProbe5PacketCaptureFallbackBug:
    """
    Probe 5: Test PacketCapture._parse_tshark_protocols() and line 769 fallback bug.
    AUDIT_FRAMEWORK.md Pitfall #8 & #15: Defect in packet_count fallback logic.

    Production Location: jarvis/security/scanner.py:767-769:
        protocols = _parse_tshark_protocols(raw_stdout)
        status = "SUCCESS" if protocols else "NO_PROTOCOLS_PARSED"
        packet_count = sum(protocols.values()) if protocols else count
    """

    def test_parse_tshark_protocols_with_unparseable_output_returns_empty_dict(self):
        """Verify _parse_tshark_protocols returns {} on unparseable/garbage stdout."""
        garbage_stdout = (
            "Capturing on 'Wi-Fi'\n"
            "tshark: An error occurred while capturing packets.\n"
            "0 packets captured\n"
        )
        parsed = _parse_tshark_protocols(garbage_stdout)
        assert parsed == {}, f"Expected empty dict, got {parsed}"

    def test_packet_capture_line_769_defaults_packet_count_to_requested_count(self):
        """
        Empirically verify the line 769 defect:
        When raw_stdout is non-empty but unparseable, protocols is empty,
        yet packet_count evaluates to `count` (the requested packet count) instead of 0.
        """
        capture = PacketCapture()
        requested_count = 250
        duration = 3.5
        unparseable_stdout = "Error reading packets: unexpected EOF from tshark pipe\n"

        result = capture._build_capture_result(
            interface="Wi-Fi",
            count=requested_count,
            duration=duration,
            raw_stdout=unparseable_stdout,
        )

        # Status correctly identifies failure to parse protocols
        assert result.status == "NO_PROTOCOLS_PARSED"
        assert result.protocols == {}

        # DEFECT CONFIRMATION: packet_count defaulted to requested 250 instead of 0
        assert result.packet_count == requested_count, (
            f"Line 769 defect confirmed: packet_count is {result.packet_count}, "
            f"matching requested count {requested_count} instead of truthful 0"
        )

    def test_packet_capture_empty_stdout_truthfully_returns_zero_count(self):
        """
        Contrast with empty raw_stdout: line 775 truthfully sets packet_count = 0.
        """
        capture = PacketCapture()
        result = capture._build_capture_result(
            interface="Wi-Fi",
            count=250,
            duration=3.5,
            raw_stdout=None,
        )
        assert result.status == "NO_TSHARK_OUTPUT"
        assert result.packet_count == 0


# ==============================================================================
# PROBE 6: SecretsManager Fail-Closed (Axis 2: Truthfulness & Axis 4)
# ==============================================================================

class TestProbe6SecretsManagerFailClosed:
    """
    Probe 6: Test SecretsManager.get_secret() on a nonexistent secret name.
    AUDIT_FRAMEWORK.md Pitfall #15 & AGENTS.md: Must fail-closed (return None)
    without crashing or fabricating dummy tokens.
    """

    def test_get_secret_nonexistent_key_returns_none(self):
        """
        Verify that querying a nonexistent secret name returns None.
        """
        nonexistent_name = "JARVIS_AUDIT_NONEXISTENT_KEY_998877"

        # Ensure it is not in os.environ
        os.environ.pop(nonexistent_name, None)

        val = get_secret(nonexistent_name, fallback_env=True)
        assert val is None, f"Expected None for nonexistent secret, got {val}"

    def test_secrets_manager_module_interface_fail_closed(self):
        """
        Verify that accessing get_secret via SecretsManager module interface
        also returns None and does not fabricate keys.
        """
        nonexistent_name = "ANOTHER_NONEXISTENT_SECRET_12345"
        os.environ.pop(nonexistent_name, None)

        assert hasattr(SecretsManager, "get_secret")
        val = SecretsManager.get_secret(nonexistent_name)
        assert val is None


# ==============================================================================
# PROBE 7: CodeInterpreterSandbox Hard Boundary (Axis 3: Boundary Type)
# ==============================================================================

class TestProbe7CodeInterpreterSandboxHardBoundary:
    """
    Probe 7: Test CodeInterpreterSandbox OS-level kernel boundaries.
    AUDIT_FRAMEWORK.md Axis 3: Hard Boundary (Kernel-enforced) vs Risk-Reduction.
    Windows Job Object ActiveProcessLimit=1 & MIC Low Integrity Token.
    """

    class _PermissiveValidator(ASTCodeValidator):
        """Permissive validator to bypass static checks and test OS runtime enforcement."""
        def validate_python(self, code: str) -> ValidationResult:
            return ValidationResult(is_safe=True)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object & MIC require Windows NT")
    def test_job_object_active_process_limit_blocks_grandchild_spawn(self, tmp_path):
        """
        Empirically verify Windows Job Object ActiveProcessLimit=1
        prevents child processes from spawning grandchild processes.
        """
        sandbox = CodeInterpreterSandbox(
            base_scratch_dir=tmp_path / "sandbox_job_test",
            default_timeout=5.0,
            validator=self._PermissiveValidator(),
        )

        code = """
import subprocess, sys
try:
    p = subprocess.run([sys.executable, "-c", "print('grandchild')"], capture_output=True, text=True)
    print("SPAWN_SUCCESS")
except Exception as exc:
    print(f"SPAWN_BLOCKED: {type(exc).__name__}")
"""
        result = sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SPAWN_BLOCKED" in result.stdout, f"Expected process spawn to be blocked, stdout: {result.stdout}"
        assert "SPAWN_SUCCESS" not in result.stdout

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows MIC requires Windows NT")
    def test_mic_low_integrity_denies_medium_integrity_write(self, tmp_path):
        """
        Empirically verify that Windows Kernel SRM blocks Low Integrity child
        from writing to Medium Integrity filesystem directories outside scratch root.
        """
        sandbox = CodeInterpreterSandbox(
            base_scratch_dir=tmp_path / "sandbox_mic_test",
            default_timeout=5.0,
            validator=self._PermissiveValidator(),
        )

        target_file = tmp_path / "medium_integrity_target.txt"
        target_path_str = str(target_file).replace("\\", "/")

        code = f"""
try:
    with open("{target_path_str}", "w") as f:
        f.write("Adversarial payload")
    print("MIC_WRITE_SUCCESS")
except PermissionError as exc:
    print(f"MIC_WRITE_BLOCKED: {{type(exc).__name__}}")
except Exception as exc:
    print(f"MIC_WRITE_OTHER: {{type(exc).__name__}}")
"""
        result = sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "MIC_WRITE_BLOCKED" in result.stdout, f"Expected PermissionError, got stdout: {result.stdout}"
        assert "MIC_WRITE_SUCCESS" not in result.stdout


# ==============================================================================
# PROBE 8: Memory Concurrency & Atomic File Persistence (Axis 1 & Axis 3)
# ==============================================================================

class TestProbe8MemoryConcurrencyAndAtomicPersistence:
    """
    Probe 8: Test SemanticVectorStore atomic persistence, concurrent read/write,
    and the 5-attempt retry loop on Windows file replacement collisions.
    """

    def test_concurrent_writes_and_reads_preserve_disk_integrity(self, tmp_path):
        """
        Stress test SemanticVectorStore under 20 concurrent writer threads
        and 5 continuous reader threads with auto_save=True.
        Verifies:
          - Zero dictionary iteration mutation errors
          - Zero unhandled file lock exceptions
          - Physical file on disk is valid JSON with exactly 20 records.
        """
        persist_file = tmp_path / "vector_store_probe8.json"
        config = VectorStoreConfig(
            persist_path=str(persist_file),
            auto_save=True,
        )
        store = SemanticVectorStore(config=config)

        errors: list[Exception] = []
        num_writers = 20
        num_readers = 5
        stop_readers = threading.Event()

        def writer_worker(idx: int):
            try:
                doc_id = f"doc_{idx:03d}"
                content = f"Tài liệu adversarial số {idx} kiểm toán hệ thống JARVIS bộ nhớ vector"
                ok = store.add_document(doc_id, content, category="audit")
                if not ok:
                    raise ValueError(f"Failed to add document {doc_id}")
            except Exception as e:
                errors.append(e)

        def reader_worker():
            try:
                while not stop_readers.is_set():
                    res = store.search("kiểm toán bộ nhớ", k=3)
                    assert isinstance(res, list)
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_writers + num_readers) as executor:
            reader_futures = [executor.submit(reader_worker) for _ in range(num_readers)]
            writer_futures = [executor.submit(writer_worker, i) for i in range(num_writers)]

            concurrent.futures.wait(writer_futures)
            stop_readers.set()
            concurrent.futures.wait(reader_futures)

        assert not errors, f"Concurrency errors encountered: {errors}"
        assert store.size() == num_writers

        # Verify disk persistence integrity
        assert persist_file.exists()
        content_str = persist_file.read_text(encoding="utf-8")
        data = json.loads(content_str)
        assert len(data.get("documents", {})) == num_writers

    def test_vector_store_save_retry_loop_recovers_from_transient_os_error(self, tmp_path):
        """
        Verify that SemanticVectorStore.save() retry loop (lines 197-204)
        successfully recovers when tmp_path.replace(path) raises OSError on initial attempts.
        """
        persist_file = tmp_path / "vector_store_retry.json"
        config = VectorStoreConfig(
            persist_path=str(persist_file),
            auto_save=False,
        )
        store = SemanticVectorStore(config=config)
        store.add_document("doc_retry", "Nội dung kiểm tra retry loop khi Windows lock file")

        call_count = 0
        original_replace = Path.replace

        def flaky_replace(self_path, target_path):
            nonlocal call_count
            call_count += 1
            # Raise OSError (simulating WinError 5 Access Denied) on attempts 1 and 2
            if call_count < 3:
                raise OSError(5, "Access is denied (transient lock simulation)")
            return original_replace(self_path, target_path)

        with patch.object(Path, "replace", flaky_replace):
            store.save()

        # Assert that retry loop attempted 3 times and succeeded on attempt 3
        assert call_count == 3, f"Expected 3 replace attempts, got {call_count}"
        assert persist_file.exists()
        saved = json.loads(persist_file.read_text(encoding="utf-8"))
        assert "doc_retry" in saved["documents"]
