# Closed-Loop Hardening Matrix & Official Production Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triệt tiêu hoàn toàn lỗi logic trong hệ thống (bắt đầu từ WAV container validation trong TTS cache), chạy ma trận kiểm thử tự động khép kín đến khi 100% GREEN, đóng gói standalone `JARVIS.exe` và installer cho Windows, sẵn sàng phát hành chính thức v5.2.1.

**Architecture:** Áp dụng mô hình Closed-Loop Hardening: phân tích tĩnh (V1) -> sửa lỗi logic & fail-closed (V2) -> kiểm thử nghịch đảo & stress concurrency (V3) -> toàn bộ test suite E2E (V4) -> build packaging & release tag (V5).

**Tech Stack:** Python 3.13, Pytest, Sounddevice/Wave, PyInstaller, Inno Setup, Git.

**Spec:** `docs/superpowers/specs/2026-10-04-production-release-continuous-hardening-matrix.md`

## Global Constraints
- Target Version: `5.2.1` (`jarvis/__init__.py`).
- Zero Regression: Toàn bộ 4328+ unit/e2e tests non-skipped phải PASS 100% (0 failed).
- Fail-Closed: Không bao giờ nuốt ngoại lệ hoặc trả về kết quả giả thành công khi dữ liệu hỏng hoặc mất mạng.
- Production Artifact: Sinh ra `dist/JARVIS.exe` và bộ cài đặt Inno Setup `dist/JARVIS_v5.2.1_Setup.exe`.

## Review Focus
1. `corrupt_garbage_binary_200b` trong TTS cache: Khi `JARVIS_MOCK_AUDIO=1`, file rác vẫn phải bị từ chối (`play_wav` trả về False) để kích hoạt self-healing.
2. Atomic write trong `note_taker`: Đảm bảo `PermissionError` trên Windows được retry và dữ liệu không bị ghi đè rỗng.
3. Subprocess process tree cleanup: Không để lại zombie process khi shell assistant timeout.
4. PyInstaller hidden imports: Đảm bảo sounddevice, piper-tts, và token-bucket không bị thiếu trong bản phân phối đóng gói.
5. Version metadata: `jarvis.__version__`, `pyproject.toml`, và installer version đồng bộ chính xác `5.2.1`.

---

### Task 1: Vá lỗi logic WAV container validation trong TTS Cache (`jarvis/tts/cache.py`)

**Files:**
- Modify: `jarvis/tts/cache.py:184-210`
- Test: `tests/test_empirical_challenger_m2.py`
- Test: `tests/unit/test_tts_cache.py`

**Interfaces:**
- Consumes: `Path(path)`
- Produces: `play_wav(path: str | Path, wait: bool = True) -> bool`

- [ ] **Step 1: Viết test xác nhận lỗi logic**
Chạy test với cờ `JARVIS_MOCK_AUDIO=1` để tái hiện lỗi:
`JARVIS_MOCK_AUDIO=1 python -m pytest tests/test_empirical_challenger_m2.py -k test_stress_cache_corruption_resilience_matrix`
Kỳ vọng: FAIL tại `assert res_play is False` (vì mock trả về True ngay cả khi file rác).

- [ ] **Step 2: Sửa `jarvis/tts/cache.py`**
Chuyển khối xác thực WAV container (`wave.open`) lên trước khi kiểm tra `JARVIS_MOCK_AUDIO=1`:
```python
        # Validate the container before trying platform fallbacks or mock bypass.
        try:
            with wave.open(str(wav_path), "rb") as wf:
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                rate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
        except Exception as e:
            log.debug("Invalid WAV cache entry (%s): %s", wav_path, e)
            return False

        if os.environ.get("JARVIS_MOCK_AUDIO") == "1":
            log.debug("JARVIS_MOCK_AUDIO=1: skipping physical playback for %s", wav_path)
            return True
```

- [ ] **Step 3: Chạy lại test xác nhận PASS**
`JARVIS_MOCK_AUDIO=1 python -m pytest tests/test_empirical_challenger_m2.py -k test_stress_cache_corruption_resilience_matrix`
Kỳ vọng: 4 passed in 1.0s.

- [ ] **Step 4: Chạy regression `tests/unit/test_tts_cache.py`**
`python -m pytest tests/unit/test_tts_cache.py`
Kỳ vọng: 6 passed in 0.5s.

- [ ] **Step 5: Commit thay đổi**
```bash
git add jarvis/tts/cache.py
git commit -m "fix(tts): validate WAV container before mock audio bypass"
```

---

### Task 2: Kiểm tra phân tích tĩnh và chuẩn cú pháp (Vòng 1)

**Files:**
- Check: `jarvis/`, `tests/`, `scripts/`

- [ ] **Step 1: Chạy ruff lint**
`python -m ruff check jarvis/ tests/ scripts/`
Kỳ vọng: 0 errors.

- [ ] **Step 2: Chạy py_compile trên các module lõi**
Kiểm tra cú pháp Python 3.13 không có lỗi AST.

---

### Task 3: Kiểm thử Unit & Stress Concurrency (Vòng 2 & 3)

**Files:**
- Test: `tests/unit/`
- Test: `tests/test_empirical_challenger_m2.py`
- Test: `tests/unit/test_note_persistence_release.py`

- [ ] **Step 1: Chạy toàn bộ 2820 test unit**
`python -m pytest tests/unit/ -q --timeout=60`
Kỳ vọng: 2820 passed, 0 failed.

- [ ] **Step 2: Chạy test stress concurrency note persistence**
`python -m pytest tests/unit/test_note_persistence_release.py`
Kỳ vọng: 6 passed (chứng minh 12/12 ghi chú an toàn dưới tải đồng thời).

- [ ] **Step 3: Chạy test empirical challenger m2**
`python -m pytest tests/test_empirical_challenger_m2.py`
Kỳ vọng: 21 passed.

---

### Task 4: Chạy toàn bộ Test Suite End-to-End toàn repo (Vòng 4)

**Files:**
- Test: `tests/`

- [ ] **Step 1: Chạy pytest toàn bộ 4369 tests**
`python -m pytest tests/ --tb=short -ra`
Kỳ vọng: 4328+ passed, 0 failed, 41 skipped.

---

### Task 5: Đóng gói bản phát hành chính thức (Vòng 5)

**Files:**
- Execute: `scripts/build_installer.py`
- Output: `dist/JARVIS.exe`, `dist/JARVIS_v5.2.1_Setup.exe`

- [ ] **Step 1: Build standalone JARVIS.exe**
`python scripts/build_installer.py --exe-only`
Kỳ vọng: File `dist/JARVIS.exe` được tạo, kiểm tra `dist/JARVIS.exe --help` hoặc `--version`.

- [ ] **Step 2: Build Inno Setup Installer**
`python scripts/build_installer.py`
Kỳ vọng: File `dist/Output/JARVIS_v5.2.1_Setup.exe` hoặc tương đương được tạo.

---

### Task 6: Đồng bộ tài liệu phát hành, Git Commit & Release Tag

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `docs/PROJECT_STATE.md`

- [ ] **Step 1: Cập nhật CHANGELOG.md với bản v5.2.1**
- [ ] **Step 2: Git commit và tạo tag `v5.2.1`**
```bash
git add .
git commit -m "release: JARVIS v5.2.1 - Production Release & Closed-Loop Hardened"
git tag -a v5.2.1 -m "JARVIS v5.2.1 - Official Production Release"
```
