"""
tests/unit/test_windows_atomic_persistence.py
=============================================
Unit tests verifying strict Section 3 AGENTS.md Windows Atomic Persistence standards:
1. Thread serialization via `_save_lock = threading.Lock()`.
2. Fast in-memory RAM snapshot under lock.
3. Unique temporary file named `.tmp.<thread_id>.<timestamp_ns>`.
4. Atomic file replace (`tmp_path.replace(path)`).
5. 5-retry loop for `PermissionError` / `WinError 5` with exponential backoff (`time.sleep(0.02 * attempt)`).
6. Guaranteed temp file cleanup in `finally:`.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis.utils.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
)


def test_atomic_write_json_basic(tmp_path: Path) -> None:
    target_file = tmp_path / "test_data.json"
    data = {"status": "ok", "items": [1, 2, 3], "timestamp": 12345678}
    
    atomic_write_json(target_file, data)
    
    assert target_file.exists()
    loaded = json.loads(target_file.read_text(encoding="utf-8"))
    assert loaded == data
    
    # Confirm no temp files remain
    tmp_files = list(tmp_path.glob(".tmp.*"))
    assert len(tmp_files) == 0


def test_atomic_write_bytes_basic(tmp_path: Path) -> None:
    target_file = tmp_path / "test_binary.bin"
    raw_data = b"\x00\x01\x02\xFF\xFE\xFD"
    
    atomic_write_bytes(target_file, raw_data)
    
    assert target_file.exists()
    assert target_file.read_bytes() == raw_data
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_atomic_write_text_basic(tmp_path: Path) -> None:
    target_file = tmp_path / "test_report.md"
    content = "# Morning Report\nTask completed successfully.\n"
    
    atomic_write_text(target_file, content)
    
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == content
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_concurrent_multi_threaded_writes(tmp_path: Path) -> None:
    """
    Test 15 concurrent threads writing to the exact same file.
    Verifies that no corruption occurs, no WinError 5 leaks,
    and the final file contains valid JSON with no leftover .tmp files.
    """
    target_file = tmp_path / "shared_state.json"
    save_lock = threading.Lock()
    num_threads = 15
    errors: list[Exception] = []

    def _worker(thread_idx: int) -> None:
        try:
            for iteration in range(5):
                payload = {
                    "thread_idx": thread_idx,
                    "iteration": iteration,
                    "timestamp": time.time_ns(),
                    "payload": f"worker_{thread_idx}_data_{iteration}" * 50,
                }
                atomic_write_json(target_file, payload, lock=save_lock)
                time.sleep(0.005)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Concurrent writes encountered errors: {errors}"
    assert target_file.exists()
    
    # Confirm contents are valid JSON and not corrupted/truncated
    content = json.loads(target_file.read_text(encoding="utf-8"))
    assert "thread_idx" in content
    assert "iteration" in content
    assert "payload" in content

    # Verify all temporary files were unlinked
    temp_files = list(tmp_path.glob(".tmp.*"))
    assert len(temp_files) == 0, f"Leftover temp files found: {temp_files}"


def test_recovery_from_simulated_lock_contention(tmp_path: Path) -> None:
    """
    Simulate Windows file lock contention (PermissionError / WinError 5)
    failing on attempts 1 and 2, but succeeding on attempt 3.
    Verifies retry loop executes with backoff and succeeds without error.
    """
    target_file = tmp_path / "contended.json"
    payload = {"resilient": True}

    original_replace = Path.replace
    call_count = 0

    def mock_replace(self: Path, target: Path) -> Path:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Simulate WinError 5 Access is denied
            raise PermissionError(13, "Permission denied / WinError 5: Access is denied")
        return original_replace(self, target)

    with patch.object(Path, "replace", mock_replace):
        atomic_write_json(target_file, payload)

    assert call_count == 3
    assert target_file.exists()
    assert json.loads(target_file.read_text(encoding="utf-8")) == payload
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_cleanup_temp_file_on_exhausted_retries(tmp_path: Path) -> None:
    """
    Simulate persistent PermissionError on all 5 attempts.
    Verifies that the exception is raised and the temp file is cleaned up in finally:.
    """
    target_file = tmp_path / "fail_target.json"
    payload = {"will_fail": True}

    call_count = 0

    def mock_replace_always_fail(self: Path, target: Path) -> Path:
        nonlocal call_count
        call_count += 1
        raise PermissionError(13, "Permanent Access is denied")

    with patch.object(Path, "replace", mock_replace_always_fail):
        with pytest.raises(PermissionError):
            atomic_write_json(target_file, payload)

    assert call_count == 5
    assert not target_file.exists()
    # Temp file must have been unlinked in finally:
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_quick_ram_snapshot_under_lock(tmp_path: Path) -> None:
    """
    Verify recommended pattern:
    Quick snapshot of in-memory structure under RAM lock,
    followed by persistence under _save_lock.
    """
    store_file = tmp_path / "store.json"
    mem_lock = threading.Lock()
    save_lock = threading.Lock()
    in_memory_state: dict[str, str] = {"key1": "val1", "key2": "val2"}

    # Simulate fast snapshot
    with mem_lock:
        snapshot = dict(in_memory_state)
    
    atomic_write_json(store_file, snapshot, lock=save_lock)

    assert json.loads(store_file.read_text(encoding="utf-8")) == in_memory_state
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_face_embedding_storage_atomic_save(tmp_path: Path) -> None:
    import numpy as np

    from jarvis.vision.biometrics import FaceEmbeddingStorage

    storage_path = tmp_path / "faces.json"
    storage = FaceEmbeddingStorage(storage_path=storage_path)
    embedding = np.ones(128, dtype=np.float64)
    
    assert storage.add_face("test_owner", embedding) is True
    assert storage_path.exists()
    
    # Reload and verify
    storage2 = FaceEmbeddingStorage(storage_path=storage_path)
    assert "test_owner" in storage2.enrolled_faces
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_skill_telemetry_store_atomic_save(tmp_path: Path) -> None:
    from jarvis.skills.telemetry import SkillTelemetryStore

    store_path = tmp_path / "telemetry.json"
    store = SkillTelemetryStore(store_path=store_path)
    res = store.record_invocation("calc", success=True, latency_ms=12.5)
    
    assert res["invocation_count"] == 1
    assert store_path.exists()
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_macro_recorder_atomic_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import jarvis.skills.macro_recorder as mr

    macros_file = tmp_path / "macros.json"
    monkeypatch.setattr(mr, "_MACROS_FILE", macros_file)

    res = mr.execute(action="record", macro_name="m1", steps=[{"type": "wait", "params": {"seconds": 0.1}}])
    assert res["data"]["success"] is True
    assert macros_file.exists()

    res_list = mr.execute(action="list")
    assert "m1" in res_list["data"]["macros"]
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_smart_home_discovery_atomic_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import jarvis.smart_home.discovery as disc

    devices_file = tmp_path / "devices.json"
    monkeypatch.setattr(disc, "_REGISTRY_FILE", devices_file)

    sh = disc.SmartHomeDiscovery(is_mock=True)
    device = disc.DiscoveredDevice(
        device_id="lamp_01",
        name="Desk Lamp",
        ip="192.168.1.100",
        port=80,
        protocol="generic_http",
    )
    sh.register_devices([device])
    
    assert devices_file.exists()
    sh2 = disc.SmartHomeDiscovery(is_mock=True)
    assert len(sh2.get_registered_devices()) == 1
    assert sh2.get_registered_devices()[0].device_id == "lamp_01"
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_skill_registry_atomic_save(tmp_path: Path) -> None:
    from jarvis.skills.models import SkillDefinition, SkillMetadata
    from jarvis.skills.registry import SkillRegistry

    skills_dir = tmp_path / "skills"
    reg = SkillRegistry(skills_dir=skills_dir, auto_discover=False)
    meta = SkillMetadata(name="atomic_test_skill", description="Testing atomic persistence")
    skill_def = SkillDefinition(
        metadata=meta,
        entrypoint_code="def execute(**kw):\n    return {'success': True}\n",
    )

    success = reg.register_skill(skill_def)
    assert success is True
    assert (skills_dir / "atomic_test_skill" / "__init__.py").exists()
    assert (skills_dir / "atomic_test_skill" / "metadata.json").exists()
    assert len(list(skills_dir.glob("**/.tmp.*"))) == 0


def test_night_shift_tasks_atomic_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import jarvis.workers.night_shift as ns

    tasks_file = tmp_path / "tasks.json"
    monkeypatch.setattr(ns, "_TASKS_FILE", tasks_file)

    worker = ns.NightShiftWorker(is_mock=True)
    task = worker.add_task(title="Night Backup", description="backup files to archive", scheduled_time="03:00")
    
    assert tasks_file.exists()
    assert task.task_id in worker._tasks
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_mobile_bridge_log_atomic_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import jarvis.comms.mobile_bridge as mb
    from jarvis.comms.mobile_bridge import MobileFileBridge

    log_path = tmp_path / "mobile_transfers.json"
    monkeypatch.setattr(mb, "_get_transfer_log_path", lambda: log_path)

    bridge = MobileFileBridge(save_directory=str(tmp_path / "recv"))
    res = bridge.receive_file(b"test document content", "doc.txt")
    
    assert res.success is True
    assert log_path.exists()
    history = bridge.get_file_transfer_history()
    assert len(history) == 1
    assert history[0]["source"] == "doc.txt"
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_setup_wizard_config_atomic_save(tmp_path: Path) -> None:
    from jarvis.ui.setup_wizard import SetupWizard

    cfg_file = tmp_path / "config.json"
    wizard = SetupWizard(interactive=False, config_path=cfg_file)
    wizard.selected_settings = {"mode": "offline", "sample_rate": 16000}
    saved = wizard._step_save()

    assert saved is True
    assert cfg_file.exists()
    loaded = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert loaded["mode"] == "offline"
    assert len(list(tmp_path.glob(".tmp.*"))) == 0


def test_tts_cache_save_wav_atomic(tmp_path: Path) -> None:
    import wave

    import numpy as np

    from jarvis.tts.cache import TTSAudioCache, save_wav_atomic

    cache = TTSAudioCache(cache_dir=tmp_path)
    dest_wav = tmp_path / "greeting.wav"
    pcm = np.zeros(12000, dtype=np.int16).tobytes()

    res_path = cache.save_wav_atomic(dest_wav, pcm, sample_rate=24000)
    assert res_path.exists()
    with wave.open(str(res_path), "rb") as wf:
        assert wf.getframerate() == 24000
        assert wf.getnchannels() == 1

    # Also test standalone module-level function
    dest_wav2 = tmp_path / "greeting2.wav"
    save_wav_atomic(dest_wav2, pcm, sample_rate=16000)
    assert dest_wav2.exists()
    assert len(list(tmp_path.glob(".tmp.*"))) == 0

