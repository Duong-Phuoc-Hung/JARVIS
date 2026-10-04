# Design Specification: Closed-Loop Hardening Matrix & Official Production Release

- **Date:** 2026-10-04
- **Target Version:** 5.2.1
- **Status:** Approved for Implementation

---

## 1. Mục tiêu & Bối cảnh

Dự án J.A.R.V.I.S. đang hoàn thiện các bản vá an toàn và sẵn sàng cho phát hành chính thức. Mục tiêu của đặc tả này là thiết lập **Closed-Loop Hardening Matrix** (Ma trận kiểm định và tự vá lỗi khép kín liên tục) nhằm:
1. Đào sâu phát hiện và loại bỏ triệt để các lỗi logic, race condition, và lỗ hổng fail-closed trên từng module.
2. Đảm bảo toàn bộ 4369+ bài kiểm thử trong kho mã đạt tỷ lệ đạt 100% (không có test thất bại).
3. Đóng gói ứng dụng thành file thực thi độc lập (`dist/JARVIS.exe`) và bộ cài Inno Setup cho Windows.
4. Chuẩn hóa metadata, tài liệu phát hành (CHANGELOG, README) và tạo git tag release chính thức.

---

## 2. Ma trận kiểm định định lượng 5 Vòng (Verification Matrix)

Hệ thống chỉ được phép chuyển sang pha tiếp theo khi vượt qua 100% tiêu chí định lượng của pha trước:

```
[V1: Static Check] ──> [V2: Core Logic Fixes] ──> [V3: Stress/Adversarial] ──> [V4: E2E Suite] ──> [V5: Packaging & Release]
       │                         │                           │                       │                      │
       └──── Nếu lỗi: Vá ngay ───┴───── Tái kiểm tra ────────┴──── Tối ưu hóa ───────┴── Triệt tiêu lỗi ───┘
```

### Vòng 1: Phân tích tĩnh & Chuẩn mã nguồn (Static Verification)
- **Hạng mục:** Cú pháp, kiểu dữ liệu, các import không sử dụng, định dạng code.
- **Tiêu chí định lượng PASS:**
  - `python -m ruff check jarvis/ tests/ scripts/`: **0 error, 0 warning**.
  - `python -m py_compile` trên toàn bộ module cốt lõi: **100% OK**.

### Vòng 2: Sửa lỗi logic & Đảm bảo tính toàn vẹn (Core Logic Hardening)
- **Hạng mục chi tiết:**
  1. **TTS WAV Cache Validation (`jarvis/tts/cache.py`):**
     - Di chuyển kiểm tra tính hợp lệ của WAV container (`wave.open()`, đọc frames, kiểm tra channel, bit depth, sample rate) lên **trước** cờ `JARVIS_MOCK_AUDIO=1`.
     - Nếu file bị hỏng (corrupted binary, 0-byte, truncated): `play_wav()` bắt buộc trả về `False` và kích hoạt tái tạo âm thanh (self-healing), không bao giờ trả về `True` giả mạo.
  2. **Atomic Persistence (`jarvis/skills/note_taker/`, `jarvis/memory/`):**
     - Đảm bảo ghi an toàn qua file tạm `.tmp`, gọi `flush()` và `os.fsync()` trước khi `os.replace`.
     - Bổ sung cơ chế thử lại (exponential backoff retry tối đa 5 lần) xử lý `PermissionError` trên Windows do antivirus hoặc indexing lock.
  3. **Fail-Closed External Communications (`jarvis/comms/`, `jarvis/web/`):**
     - Khi mất mạng hoặc token chưa cấu hình: không trả về kết quả giả thành công, ghi log cảnh báo rõ ràng.
     - Finance module: loại bỏ giá baseline giả khi API lỗi.
  4. **Process Cleanup & Resource Safety (`jarvis/platform/windows.py`):**
     - Thu dọn toàn bộ cây tiến trình con (descendant process tree) bằng Job Object / taskkill khi subprocess timeout.
- **Tiêu chí định lượng PASS:**
  - `tests/unit/`: **2820/2820 PASS (100%)**.
  - Không có exception bị nuốt im lặng (`bare except: pass`).

### Vòng 3: Kiểm thử nghịch đảo & Chịu tải cao (Stress & Adversarial Testing)
- **Hạng mục chi tiết:**
  - Dữ liệu binary rác 200 bytes, header WAV giả mạo, file rỗng 0 bytes.
  - Ghi đồng thời từ 12-50 luồng vào hệ thống ghi chú và bộ nhớ véc-tơ.
  - Tải xung đột rate-limiter và token-bucket đồng thời.
- **Tiêu chí định lượng PASS:**
  - `tests/test_empirical_challenger_m2.py`: **21/21 PASS (100%)**.
  - `tests/test_adversarial_*.py`: **100% PASS**.
  - Dữ liệu sau kiểm thử đồng thời không bị mất mát hay suy hao.

### Vòng 4: Kiểm thử liên thông End-to-End toàn kho mã
- **Hạng mục chi tiết:**
  - Chạy toàn bộ test suite `tests/` (bao gồm `unit/`, `e2e/`, `integration/`, `eval/`, `benchmarks/`).
- **Tiêu chí định lượng PASS:**
  - Toàn bộ các ca kiểm thử không phụ thuộc phần cứng rời (OpenCV webcam, mic vật lý, live external cloud): **0 FAILED**.
  - Tối thiểu **4328+ test passed**, 0 test failed.

### Vòng 5: Đóng gói bản phát hành chính thức (Packaging & Distribution)
- **Hạng mục chi tiết:**
  - Build standalone Windows executable: `python scripts/build_installer.py --exe-only` -> tạo `dist/JARVIS.exe`.
  - Build bộ cài đặt Inno Setup Windows: `python scripts/build_installer.py` -> tạo bộ cài `dist/JARVIS_v5.2.1_Setup.exe`.
  - Khởi động thử `dist/JARVIS.exe --version` và kiểm tra load thư viện ngầm.
  - Cập nhật CHANGELOG.md, README.md, và tạo Git release tag `v5.2.1`.
- **Tiêu chí định lượng PASS:**
  - `dist/JARVIS.exe` sinh ra đầy đủ, kích thước hợp lý, checksum SHA256 được ghi nhận.
  - `dist/JARVIS.exe --version` trả về đúng `5.2.1`.
  - Bộ cài Inno Setup sinh ra thành công.

---

## 3. Kế hoạch triển khai kỹ thuật

1. **Bước 1:** Áp dụng bản vá `jarvis/tts/cache.py` giải quyết dứt điểm lỗi WAV validation khi mock audio.
2. **Bước 2:** Chạy kiểm tra tĩnh ruff/py_compile.
3. **Bước 3:** Chạy ma trận Vòng 2 & 3: kiểm thử unit và kiểm thử nghịch đảo stress.
4. **Bước 4:** Chạy toàn bộ test suite (Vòng 4) xác nhận 0 lỗi.
5. **Bước 5:** Thực thi build executable và installer (Vòng 5).
6. **Bước 6:** Kiểm tra executable đã build, tạo commit và git tag release hoàn chỉnh.
