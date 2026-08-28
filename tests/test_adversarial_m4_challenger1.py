import concurrent.futures
import ctypes
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.hardware.monitor import (
    DiskSmartMetrics,
    HardwareMetrics,
    HardwareMonitor,
)
from jarvis.hardware.reporter import HardwareReporter
from jarvis.healing.terminator import (
    PROTECTED_PROCESS_WHITELIST,
    AutonomousTerminator,
    HealingEngine,
    HealingMode,
    HealingReport,
)
from jarvis.healing.watchdog import (
    HungProcessInfo,
    ResourceWatchdog,
    UnresponsiveAppDetector,
)
from jarvis.security.report import (
    SecurityPrivilegeGate,
    SecurityReportGenerator,
)
from jarvis.security.scanner import (
    HostScanResult,
    NetworkScanner,
    PacketCapture,
    PacketCaptureResult,
    ScanReport,
)


def test_hardware_monitor_corrupted_thermal_cim_json_resilience():
    monitor = HardwareMonitor(provider=None)
    corrupt_payloads = [
        '',
        '   \n  \t  ',
        '{corrupted: json!@#}',
        '[]',
        'null',
        '123',
        '-500',
        '[null, false,  unknown]',
        json.dumps({'OtherProp': 42}),
        json.dumps([2732]),
        json.dumps([3732]),
    ]
    for payload in corrupt_payloads:
        def mock_subprocess_run(*args, payload=payload, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = payload
            mock_proc.stderr = ''
            return mock_proc

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            monitor._cached_cim_temp = None
            monitor._cached_cim_temp_ts = 0.0
            temp = monitor._probe_cpu_temperature()
            if payload == json.dumps([3732]):
                assert temp == 100.0
            else:
                assert temp is None or isinstance(temp, (int, float))


def test_hardware_monitor_subprocess_failure_and_timeout():
    monitor = HardwareMonitor(provider=None)
    with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='powershell', timeout=1.5)):
        monitor._cached_cim_temp = None
        monitor._cached_cim_temp_ts = 0.0
        assert monitor._probe_cpu_temperature() is None

    with patch('subprocess.run', side_effect=FileNotFoundError('powershell.exe not found')):
        monitor._cached_cim_temp = None
        monitor._cached_cim_temp_ts = 0.0
        assert monitor._probe_cpu_temperature() is None

    mock_fail_proc = MagicMock(returncode=1, stdout='', stderr='Access Denied')
    with patch('subprocess.run', return_value=mock_fail_proc):
        monitor._cached_cim_temp = None
        monitor._cached_cim_temp_ts = 0.0
        assert monitor._probe_cpu_temperature() is None


def test_hardware_monitor_nvidia_smi_malformed_outputs():
    monitor = HardwareMonitor(provider=None)
    monitor._nvidia_smi_path = 'nvidia-smi'
    malformed_lines = [
        '',
        '[N/A], [N/A], [N/A], [N/A], [N/A]',
        'ERR!, ERR!, ERR!, ERR!, ERR!',
        '50, 75',
        'abc, def, ghi, jkl, mno',
        '0.0, 45.0, 8192.0, 2048.0, 30',
        '100.0, 92.0, 16384.0, 15000.0, 99',
        '  , , , , ',
    ]
    for line in malformed_lines:
        mock_proc = MagicMock(returncode=0, stdout=line + '\n', stderr='')
        with patch('subprocess.run', return_value=mock_proc):
            gpu_pct, gpu_temp, vram_used, vram_tot, fan_rpm, fan_pct = monitor._probe_gpu()
            if '8192.0' in line:
                assert gpu_pct == 0.0
                assert gpu_temp == 45.0
                assert vram_tot == 8.0
                assert vram_used == 2.0
                assert fan_pct == 30
            elif '16384.0' in line:
                assert gpu_pct == 100.0
                assert gpu_temp == 92.0
                assert vram_tot == 16.0
                assert fan_pct == 99
            else:
                assert isinstance(gpu_pct, (float, type(None)))
                assert isinstance(gpu_temp, (float, type(None)))


def test_hardware_monitor_smart_disk_failure_propagation():
    monitor = HardwareMonitor(provider=None)
    smart_json = json.dumps([{'InstanceName': 'SCSI_Disk_0', 'Active': True, 'PredictFailure': True}])
    mock_proc = MagicMock(returncode=0, stdout=smart_json, stderr='')
    with patch('subprocess.run', return_value=mock_proc):
        disks = monitor.get_disk_smart_status(use_cache=False)
        assert len(disks) >= 1
        assert any(d.status == 'FAILING' for d in disks.values())
        assert monitor._aggregate_smart_status(disks) == 'FAILING'


def test_hardware_monitor_zero_disks_fallback():
    monitor = HardwareMonitor(provider=None)
    with patch('subprocess.run', side_effect=Exception('PowerShell unavailable')):
        disks = monitor.get_disk_smart_status(use_cache=False)
        assert 'C:' in disks
        assert disks['C:'].status in ('PASSED', 'WARNING', 'FAILING')


def test_hardware_alert_rapid_flapping_under_continuous_load(mock_hardware_provider):
    monitor = HardwareMonitor(
        provider=mock_hardware_provider,
        cpu_temp_threshold=85.0,
        alert_cooldown_s=5.0,
    )
    alert_count = 0
    for i in range(100):
        temp = 85.5 if (i % 2 == 0) else 84.0
        mock_hardware_provider.set_cpu(percent=50.0, temp_c=temp)
        alerts = monitor.check_thresholds()
        alert_count += len(alerts)
    assert alert_count == 1, f'Expected 1 alert due to debouncing, got {alert_count}'


def test_hardware_critical_overheat_emergency_alert_escalation(mock_hardware_provider):
    monitor = HardwareMonitor(
        provider=mock_hardware_provider,
        cpu_temp_threshold=85.0,
        alert_cooldown_s=5.0,
    )
    mock_hardware_provider.set_cpu(percent=80.0, temp_c=88.0)
    alerts1 = monitor.check_thresholds()
    assert len(alerts1) == 1
    assert alerts1[0]['level'] == 'WARNING'

    monitor.last_alert_times['cpu'] = time.time() - 1.2
    mock_hardware_provider.set_cpu(percent=95.0, temp_c=98.0)
    alerts2 = monitor.check_thresholds()
    assert len(alerts2) == 1
    assert alerts2[0]['level'] == 'CRITICAL'
    assert '98.0' in alerts2[0]['message']


def test_hardware_multi_component_simultaneous_breach(mock_hardware_provider):
    monitor = HardwareMonitor(
        provider=mock_hardware_provider,
        cpu_temp_threshold=80.0,
        ram_threshold=90.0,
        gpu_temp_threshold=80.0,
        alert_cooldown_s=5.0,
    )
    mock_hardware_provider.set_cpu(percent=90.0, temp_c=88.0)
    mock_hardware_provider.set_ram(96.0)
    mock_hardware_provider.set_gpu(util_percent=95.0, temp_c=89.0, vram_used_gb=10.0)
    mock_hardware_provider.set_smart('C:', 'FAILING', reallocated_sectors=120)

    alerts = monitor.check_thresholds()
    components = [a['component'] for a in alerts]
    assert 'cpu' in components
    assert 'ram' in components
    assert 'gpu' in components
    assert 'disk_smart' in components
    assert len(alerts) == 4


def test_hardware_reporter_adversarial_queries(mock_hardware_provider):
    reporter = HardwareReporter(monitor=HardwareMonitor(provider=mock_hardware_provider))
    test_queries = [
        ('', 'tình trạng hệ thống'),
        ('   ', 'tình trạng hệ thống'),
        ('CPU NHIỆT ĐỘ', 'cpu'),
        ('xung nhịp cpu thế nào', 'cpu'),
        ('RAM CÒN BAO NHIÊU %', 'ram'),
        ('kiểm tra card màn hình và GPU', 'gpu'),
        ('sức khỏe ổ cứng smart disk', 'ổ đĩa'),
        ('thời tiết hôm nay thế nào?', 'tình trạng hệ thống'),
        ('!@#$%^&*()_+', 'tình trạng hệ thống'),
    ]
    for query, expected_sub in test_queries:
        response = reporter.process_voice_query(query, lang='vi')
        assert isinstance(response, str)
        assert len(response) > 5


def test_hardware_reporter_markdown_dashboard_extreme_values(mock_hardware_provider):
    mock_hardware_provider.cpu_temp_c = None
    mock_hardware_provider.cpu_freq_mhz = None
    mock_hardware_provider.set_gpu(util_percent=0.0, temp_c=None, vram_used_gb=0.0)
    mock_hardware_provider.gpu_percent = None
    mock_hardware_provider.gpu_temp_c = None
    mock_hardware_provider.vram_used_gb = None
    mock_hardware_provider.vram_total_gb = None
    mock_hardware_provider.gpu_fan_percent = None

    reporter = HardwareReporter(monitor=HardwareMonitor(provider=mock_hardware_provider))
    md = reporter.format_markdown_report()
    assert 'JARVIS Hardware Diagnostics Report' in md
    assert 'N/A' in md
    assert 'CPU Usage' in md


def test_terminator_whitelist_bypass_casing_variations(mock_win32_platform):
    terminator = AutonomousTerminator(win32_platform=mock_win32_platform)
    casing_attacks = [
        'EXPLORER.EXE',
        'Explorer.Exe',
        'eXpLoReR.eXe',
        'SYSTEM',
        'System',
        'CSRSS.EXE',
        'Csrss.exe',
        'WININIT.EXE',
        'WinInit.exe',
        'SERVICES.EXE',
        'Services.exe',
        'LSASS.EXE',
        'Lsass.exe',
        'SMSS.EXE',
        'Smss.exe',
        'DWM.EXE',
        'Dwm.exe',
        'SVCHOST.EXE',
        'Svchost.exe',
        'PYTHON.EXE',
        'Python.Exe',
        'JARVIS.EXE',
        'Jarvis.exe',
        'RUNTIMEBROKER.EXE',
        'RuntimeBroker.exe',
    ]
    for proc_name in casing_attacks:
        assert terminator.is_protected(proc_name, pid=1000), f'Whitelist bypass successful on {proc_name}!'
        result = terminator.terminate_process(pid=1000, process_name=proc_name)
        assert result is False, f'Terminator executed kill on whitelisted {proc_name}!'
        assert 1000 not in mock_win32_platform.killed_pids


def test_terminator_whitelist_bypass_path_and_whitespace_variations(mock_win32_platform):
    terminator = AutonomousTerminator(win32_platform=mock_win32_platform)
    extensionless = ['explorer', 'system', 'csrss', 'dwm', 'services', 'lsass', 'python', 'jarvis']
    for name in extensionless:
        assert terminator.is_protected(name, pid=2000), f'Failed to protect extensionless name: {name}'

    whitespace_names = ['  explorer.exe  ', '\texplorer.exe\n', ' csrss.exe ']
    for name in whitespace_names:
        assert terminator.is_protected(name, pid=2001), f'Failed to protect whitespace name: {repr(name)}'


def test_terminator_self_pid_protection(mock_win32_platform):
    terminator = AutonomousTerminator(win32_platform=mock_win32_platform)
    self_pid = os.getpid()
    assert terminator.is_protected('malicious_untrusted.exe', pid=self_pid) is True
    res = terminator.terminate_process(pid=self_pid, process_name='malicious_untrusted.exe')
    assert res is False
    assert self_pid not in mock_win32_platform.killed_pids


def test_terminator_custom_whitelist_injection(mock_win32_platform):
    custom = {'my_custom_daemon.exe', 'important_service.exe'}
    terminator = AutonomousTerminator(win32_platform=mock_win32_platform, custom_whitelist=custom)
    assert terminator.is_protected('MY_CUSTOM_DAEMON.EXE') is True
    assert terminator.is_protected('my_custom_daemon') is True
    assert terminator.is_protected('important_service.exe') is True
    assert terminator.is_protected('IMPORTANT_SERVICE') is True
    assert terminator.is_protected('unrelated_app.exe') is False


def test_unresponsive_app_detector_invalid_hwnds():
    detector = UnresponsiveAppDetector(win32_platform=None)
    for invalid_hwnd in [0, -1, 999999999, None]:
        try:
            assert detector.is_window_hung(invalid_hwnd) is False
        except Exception as e:
            pytest.fail(f'is_window_hung crashed on HWND {invalid_hwnd}: {e}')


def test_unresponsive_app_detector_live_window_enumeration():
    detector = UnresponsiveAppDetector()
    hung_windows = detector.find_hung_windows()
    assert isinstance(hung_windows, list)
    for w in hung_windows:
        assert isinstance(w, HungProcessInfo)
        assert isinstance(w.hwnd, int)
        assert isinstance(w.pid, int)


def test_watchdog_high_concurrency_heartbeats():
    watchdog = ResourceWatchdog()
    num_threads = 50
    iterations = 100

    def worker_pulse(worker_id: int):
        t_name = f'worker_{worker_id}'
        for _ in range(iterations):
            watchdog.record_heartbeat(t_name, timeout_s=10.0)
            time.sleep(0.001)

    def health_checker():
        for _ in range(iterations):
            stale = watchdog.check_thread_health()
            assert isinstance(stale, list)
            time.sleep(0.001)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads + 2) as executor:
        futures = [executor.submit(worker_pulse, i) for i in range(num_threads)]
        futures.append(executor.submit(health_checker))
        futures.append(executor.submit(health_checker))
        for f in concurrent.futures.as_completed(futures):
            f.result()

    stale_list = watchdog.check_thread_health()
    assert len(stale_list) == 0


def test_watchdog_thread_hang_detection_simulation():
    watchdog = ResourceWatchdog()
    watchdog.record_heartbeat('live_worker', timeout_s=5.0)
    watchdog.record_heartbeat('hung_network_worker', timeout_s=0.2)
    watchdog.record_heartbeat('hung_tts_worker', timeout_s=0.2)

    time.sleep(0.3)
    watchdog.record_heartbeat('live_worker', timeout_s=5.0)

    stale = watchdog.check_thread_health()
    stale_names = {s['thread_name'] for s in stale}
    assert 'hung_network_worker' in stale_names
    assert 'hung_tts_worker' in stale_names
    assert 'live_worker' not in stale_names

    for s in stale:
        assert s['last_pulse_seconds_ago'] >= 0.2
        assert s['timeout_threshold_s'] == 0.2


def test_watchdog_start_stop_rapid_cycling():
    watchdog = ResourceWatchdog(poll_interval_s=0.1)
    for _ in range(30):
        watchdog.start()
        assert watchdog.is_running is True
        time.sleep(0.01)
        watchdog.stop()
        assert watchdog.is_running is False


def test_healing_engine_advisory_mode_zero_terminations(mock_win32_platform, mock_hardware_provider):
    mock_hardware_provider.set_ram(99.0)
    mock_win32_platform.add_hung_window('frozen_heavy_game.exe', pid=9001)

    engine = HealingEngine(
        win32_platform=mock_win32_platform,
        hardware_provider=mock_hardware_provider,
        auto_kill=False,
        mode=HealingMode.ADVISORY,
    )

    report = engine.heal_hung_process(pid=9001, name='frozen_heavy_game.exe')
    assert report['success'] is False
    assert report['reason'] == 'AUTO_KILL_DISABLED'
    assert report['alert_issued'] is True
    assert 9001 not in mock_win32_platform.killed_pids
    assert 'Cảnh báo' in report['spoken_message']


def test_healing_engine_batch_recovery_mixed_whitelist(mock_win32_platform, mock_hardware_provider):
    mock_hardware_provider.set_ram(95.0)
    for i in range(1, 6):
        mock_win32_platform.add_hung_window(f'leaking_process_{i}.exe', pid=8100 + i)

    mock_win32_platform.add_hung_window('explorer.exe', pid=9901)
    mock_win32_platform.add_hung_window('dwm.exe', pid=9902)
    mock_win32_platform.add_hung_window('csrss.exe', pid=9903)

    engine = HealingEngine(
        win32_platform=mock_win32_platform,
        hardware_provider=mock_hardware_provider,
        auto_kill=True,
    )

    reports = engine.run_auto_recovery_cycle()
    assert len(reports) >= 8

    successful_kills = [r.get('pid') for r in reports if r.get('success') is True]
    failed_reports = [r for r in reports if r.get('success') is False]

    for i in range(1, 6):
        assert (8100 + i) in successful_kills
        assert (8100 + i) in mock_win32_platform.killed_pids

    assert 9901 not in mock_win32_platform.killed_pids
    assert 9902 not in mock_win32_platform.killed_pids
    assert 9903 not in mock_win32_platform.killed_pids


def test_healing_report_dict_and_dataclass_compatibility():
    rep = HealingReport(
        success=True,
        pid=1234,
        name='test_app.exe',
        reclaimed_ram=55.0,
        spoken_message='Test speech',
    )
    assert rep.success is True
    assert rep.pid == 1234
    assert rep.spoken_message == 'Test speech'
    assert rep['success'] is True
    assert rep['pid'] == 1234
    assert rep['name'] == 'test_app.exe'
    assert rep['reclaimed_ram'] == 55.0
    assert rep.get('pid') == 1234
    assert rep.get('nonexistent', 'default') == 'default'
    assert 'spoken_message' in rep
    assert 'success' in rep


def test_security_scanner_unauthenticated_biometric_rejection():
    unauth_ctx = RequesterContext(
        requester_id='guest_user',
        granted_privilege=PrivilegeLevel.NORMAL,
        is_authenticated=False,
    )
    scanner = NetworkScanner()
    scan_rep = scanner.scan_subnet('192.168.1.0/24', context=unauth_ctx)
    assert scan_rep.status == 'PERMISSION_DENIED'
    assert scan_rep.total_hosts == 0
    assert 'Biometric' in str(scan_rep.error_message)

    capture = PacketCapture()
    cap_rep = capture.capture_packets(interface='eth0', count=50, context=unauth_ctx)
    assert cap_rep['status'] == 'PERMISSION_DENIED'
    assert cap_rep['packet_count'] == 0
    assert 'Biometric' in str(cap_rep.get('error_message'))


def test_security_privilege_gate_admin_role_enforcement():
    auth_admin = RequesterContext(requester_id='owner', granted_privilege=PrivilegeLevel.ADMIN, is_authenticated=True)
    auth_user = RequesterContext(requester_id='family_member', granted_privilege=PrivilegeLevel.NORMAL, is_authenticated=True)
    unauth_admin = RequesterContext(requester_id='intruder', granted_privilege=PrivilegeLevel.ADMIN, is_authenticated=False)

    assert SecurityPrivilegeGate.verify_privilege(auth_admin) is True
    assert SecurityPrivilegeGate.verify_privilege(auth_user) is False
    assert SecurityPrivilegeGate.verify_privilege(unauth_admin) is False
