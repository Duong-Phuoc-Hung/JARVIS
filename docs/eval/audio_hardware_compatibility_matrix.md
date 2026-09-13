# Ma Trận Tương Thích Phần Cứng Thiết Bị Âm Thanh (Audio Hardware Compatibility Matrix)
**Dự Án**: JARVIS Voice Assistant — Beta v1  
**Mục Tiêu**: Kiểm tra tính tương thích của hệ thống âm thanh (Capture & Playback) trên 10 cấu hình micro & máy khác nhau  
**Tài Liệu Tham Chiếu Gốc**: Backlog H-10 (`ORIGINAL_REQUEST.md` & `ROADMAP.md`)  
**Trạng Thái Nghiệm Thu Hiện Tại**: 🟡 **PARTIAL — 2/10 TIER 1 CONFIRMED**  
**Lần đo cuối**: 2026-09-13 23:21 ICT | Raw JSON: `docs/eval/audio_hardware_compatibility_matrix_results.json`

---

> [!CAUTION]
> **QUY TẮC PHÂN LOẠI BẰNG CHỨNG (TIER 1 VS TIER 2)**:
> - **Tier 2 (Synthetic / Mock)**: Bài test tự động `tests/unit/test_audio_engine.py` (mock list) là **Tier 2** — không chứng minh tương thích phần cứng thật.
> - **Tier 1 (Real Hardware Evidence)**: Mở stream sounddevice thật ở 16kHz, đo peak amplitude thực. Chỉ `peak > 50` mới tính là tín hiệu xác nhận.
> - **TIER1_PASS_SILENT**: Stream mở được nhưng không có tín hiệu thực (app không active) — **không tính** là Tier 1 Pass đầy đủ.

---

## 1. Bảng Đánh Giá 10 Cấu Hình Thiết Bị Phần Cứng Mục Tiêu

| STT | Cấu Hình Thiết Bị Mục Tiêu | Loại Kết Nối | Sample Rate | Trạng Thái | Kết Quả Đo | Ghi Chú |
|:---:|:---|:---|:---:|:---:|:---|:---|
| 1 | **Built-in Mic Array (Realtek)** | Internal Bus | 16,000 Hz | 🟢 **ĐÃ ĐO THẬT (TIER 1)** | peak=5697, rms=803.02 | Device[1] — tín hiệu thật, đo 2026-09-13 |
| 2 | **Realtek HD Audio Mic Array (beamforming)** | Internal Bus | 16,000 Hz | 🟢 **ĐÃ ĐO THẬT (TIER 1)** | peak=5697, rms=803.02 | Device[11] — cùng chip Realtek, confirmed |
| 3 | **Virtual/USB (Camo — iPhone camera app)** | USB Virtual | 16,000 Hz | 🟡 **TIER1_PASS_SILENT** | peak=1, rms=0.48 | Stream mở được nhưng Camo app chưa active — tín hiệu chưa xác nhận |
| 4 | **Bluetooth TWS (AirPods Pro)** | Bluetooth HFP | 16,000 Hz | 🔴 **TIER1_FAIL** | PaErrorCode -9999 | Đang ở A2DP mode — cần switch HFP thủ công trong Windows Settings |
| 5 | **Bluetooth Headset (LY-Z5202)** | Bluetooth HFP | 16,000 Hz | 🔴 **TIER1_FAIL** | PaErrorCode -9999 | Bị blocked — cần switch profile HFP |
| 6 | **USB Audio Interface (8ch Input)** | USB | 48,000 Hz | 🔴 **TIER1_FAIL** | PaErrorCode -9999 | Device[27] bị blocked bởi exclusive mode driver |
| 7 | **Webcam Integrated Mic** | USB | 16,000 Hz | 🔴 **CHƯA CÓ PHẦN CỨNG** | — | Webcam rời chưa kết nối |
| 8 | **Virtual Audio Cable (VB-Audio)** | Virtual Software | 44,100 Hz | 🔴 **CHƯA CÀI PHẦN MỀM** | — | Cần cài VB-Audio Virtual Cable |
| 9 | **Generic USB PnP Dongle** | USB | 44,100 Hz | 🔴 **CHƯA CÓ PHẦN CỨNG** | — | USB sound adapter chưa kết nối |
| 10 | **USB Condenser Mic (Blue Yeti/Rode)** | USB Type-C | 48,000 Hz | 🔴 **CHƯA CÓ PHẦN CỨNG** | — | Thiết bị vật lý chưa có |

---

## 2. Hướng Dẫn Mở Khóa Bluetooth (Configs #4, #5)

Để test AirPods Pro / LY-Z5202, switch profile trước:
```
Windows Settings → Bluetooth & devices → [tên thiết bị] → More options
→ Chọn "Hands-Free Telephony" (HFP) profile
→ Sau đó chạy lại: python tests/eval/wake_word_idle_runner.py
```

---

## 3. Kết Luận Kiểm Toán

- **Tier 1 Pass (tín hiệu thật)**: `2 / 10` (Configs #1, #2 — Realtek built-in)
- **Stream mở được, tín hiệu chưa xác nhận**: `1 / 10` (Config #3 — Camo)
- **Blocked / Chưa có phần cứng**: `7 / 10`
- **Trạng thái H-10**: `PARTIAL` — cần thêm 8 configs Tier 1 để đóng task
- **Có thể làm ngay**: Switch AirPods/LY-Z5202 → HFP; kích hoạt Camo app; cài VB-Audio Virtual Cable
  

---

> [!CAUTION]
> **QUY TẮC PHÂN LOẠI BẰNG CHỨNG (TIER 1 VS TIER 2)**:
> - **Tier 2 (Synthetic / Mock)**: Bài test tự động `tests/unit/test_audio_engine.py` (kiểm tra chuyển đổi device index khi mock danh sách thiết bị) là **Tier 2**. Bài test này chứng minh logic code không crash, **KHÔNG CHỨNG MINH TÍNH TƯƠNG THÍCH PHẦN CỨNG THẬT**.
> - **Tier 1 (Real Hardware Evidence)**: Cần cắm trực tiếp 10 thiết bị vật lý vào hệ điều hành Windows thật, thu âm và kiểm tra tín hiệu. Trong môi trường phát triển hiện tại, chỉ có 1 microphone vật lý tích hợp (Built-in Audio) hoạt động.
> - **Kết luận**: H-10 giữ nguyên trạng thái `BLOCKED_ON_HARDWARE` cho đến khi thu thập đủ kết quả kiểm thử trên 10 phần cứng vật lý độc lập.

---

## 1. Bảng Đánh Giá 10 Cấu Hình Thiết Bị Phần Cứng Mục Tiêu

| STT | Cấu Hình Thiết Bị Mục Tiêu | Loại Kết Nối | Sample Rate Chuẩn | Endpoint Driver | Trạng Thái Kiểm Thử Vật Lý | Bằng Chứng Thực Tế Hiện Có |
|:---:|:---|:---|:---:|:---|:---:|:---|
| 1 | **Laptop Built-in Microphone** | Internal Bus | 48,000 Hz | Realtek High Definition Audio | 🟢 **ĐÃ ĐO THẬT (TIER 1)** | Thiết bị mặc định trên máy thử nghiệm hiện tại. Đã kiểm chứng thu âm 16kHz trực tiếp tại `H-01`. |
| 2 | **USB Headset Microphone** | USB 2.0/3.0 | 44,100 Hz / 48,000 Hz | USB Audio Class 1.0/2.0 (e.g., Logitech H390) | 🔴 **CHƯA CÓ PHẦN CỨNG** | Chưa cắm thiết bị vật lý. Chỉ mới kiểm thử qua mock list. |
| 3 | **USB Condenser Microphone** | USB Type-C | 48,000 Hz / 96,000 Hz | High-Def Audio (e.g., Blue Yeti, Rode NT-USB) | 🔴 **CHƯA CÓ PHẦN CỨNG** | Chưa cắm thiết bị vật lý. |
| 4 | **Bluetooth TWS Earbuds (HFP/HSP)** | Bluetooth 5.0+ | 16,000 Hz (mSBC) / 8,000 Hz (CVSD)| Hands-Free AG Audio (e.g., AirPods, Galaxy Buds) | 🔴 **CHƯA CÓ PHẦN CỨNG** | Cần kiểm tra độ trễ tráo đổi profile A2DP sang HFP. |
| 5 | **Bluetooth Over-Ear Headphone** | Bluetooth 5.2 | 16,000 Hz | Hands-Free Telephony (e.g., Sony WH-1000XM4/XM5) | 🔴 **CHƯA CÓ PHẦN CỨNG** | Chưa cắm/kết nối thiết bị vật lý. |
| 6 | **USB Professional Audio Interface** | USB Type-C | 48,000 Hz / 192,000 Hz | ASIO / WASAPI Exclusive (e.g., Focusrite Scarlett) | 🔴 **CHƯA CÓ PHẦN CỨNG** | Cần kiểm thử buffer underrun và multi-channel routing. |
| 7 | **Webcam Integrated Microphone** | USB 2.0 | 16,000 Hz / 32,000 Hz | USB Video/Audio Device (e.g., Logitech C920/C922) | 🔴 **CHƯA CÓ PHẦN CỨNG** | Chưa cắm webcam rời. |
| 8 | **Virtual Audio Cable / Cable Output** | Virtual Software | 44,100 Hz / 48,000 Hz | VB-Audio Virtual Cable / VoiceMeeter | 🔴 **CHƯA CÀI PHẦN MỀM** | Cần kiểm tra tương thích ảo hóa âm thanh. |
| 9 | **Generic USB PnP Dongle / Sound Card** | USB 2.0 | 44,100 Hz | Generic C-Media USB Audio | 🔴 **CHƯA CÓ PHẦN CỨNG** | Chưa có adapter USB âm thanh giá rẻ để test noise floor. |
| 10 | **Multi-channel Array Microphone** | Internal Bus | 48,000 Hz (Beamforming) | Intel Smart Sound Technology (SST) Array | 🔴 **CHƯA CÓ PHẦN CỨNG** | Cần kiểm tra phân tách kênh stereo thành mono 1-channel. |

---

## 2. Kết Luận Kiểm Toán
- **Số lượng cấu hình đạt chuẩn Tier 1 (Kiểm chứng phần cứng thật)**: `1 / 10`
- **Số lượng cấu hình đang chờ phần cứng (Blocked on Hardware)**: `9 / 10`
- **Hành động kỹ thuật bắt buộc**: Giữ nguyên trạng thái `BLOCKED_ON_HARDWARE` cho H-10. Không được tự ý đánh dấu "DONE" bằng unit test mock.
