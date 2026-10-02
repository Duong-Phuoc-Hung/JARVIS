# Báo cáo lỗi Wake-word “Hey JARVIS”

Ngày lập: 2026-09-25  
Phạm vi: microphone → wake-word detector → mở phiên nghe lệnh

## 1. Triệu chứng thực tế

Người dùng không nói “Hey JARVIS” nhưng hệ thống vẫn tự kích hoạt, mở phiên
nghe lệnh và STT trả về các chuỗi như “Affair”, “A fifth”, “Life”. Khi tăng
ngưỡng nhận diện, false wake giảm nhưng câu “Hey JARVIS” thật bị bỏ sót (đã
quan sát 10/10 lần không kích hoạt).

Đây là hai lỗi liên quan nhưng không đồng nhất:

```text
false wake → tự mở phiên nghe → STT nghe tiếng nền → văn bản sai
true wake bị bỏ sót → confidence thật thấp hơn threshold hiện tại
```

## 2. Nguyên nhân kỹ thuật đã xác định

### 2.1 Acoustic fallback từng được phép kích hoạt thụ động

Khi không có Tier-1 model, detector rơi xuống `acoustic_fallback`. Đây là
heuristic DSP, không phải classifier wake-word được huấn luyện riêng cho giọng
người dùng. Nếu heuristic vượt ngưỡng, desktop có thể tự mở phiên nghe dù
người dùng không gọi JARVIS.

### 2.2 Threshold bị điều chỉnh khi chưa có phân phối confidence

Việc tăng threshold làm giảm false positive nhưng đồng thời loại bỏ true
positive. Không có cơ sở để chọn giá trị mới nếu chưa ghi confidence của hai
nhóm mẫu trong cùng microphone, cùng khoảng cách và cùng môi trường.

### 2.3 STT không phải nguồn gốc duy nhất

“Affair”, “A fifth”, “Life” có thể là kết quả của STT sau khi false wake đã
xảy ra. Không được dùng các chuỗi STT này để kết luận classifier đã nhận đúng
wake-word hay chưa.

## 3. Những gì đã sửa

### 3.1 Fail-closed production path

`jarvis/core/app.py` truyền mặc định:

```python
allow_acoustic_passive_trigger=False
```

Vì vậy acoustic fallback không được phép tự mở phiên nghe trên desktop. PTT/
hotkey vẫn hoạt động.

### 3.2 Tier-1 OpenWakeWord

- Đã provision `openwakeword>=0.6,<1`.
- Đã tải model `hey_jarvis_v0.1.onnx`.
- App tự phát hiện model đóng gói khi package có mặt.
- Đã sửa matching alias `hey_jarvis_v0.1` thành logical label `hey_jarvis`.

### 3.3 Score telemetry

`WakeWordScoreEvent` ghi:

- engine;
- confidence;
- threshold;
- RMS;
- timestamp;
- detected;
- keyword.

Telemetry observer lỗi không làm thay đổi quyết định nhận diện.

### 3.4 Probe có nhãn

`tools/wake_word_score_probe.py` yêu cầu opt-in rõ ràng
`JARVIS_RUN_LIVE_WAKE_PROBE=1`, tách hai nhãn `true_wake` và `ambient`, và
không tự đề xuất threshold.

## 4. Bằng chứng hiện tại

| Hạng mục | Kết quả | Ý nghĩa |
|---|---:|---|
| H-06 unit tests | 32/32 pass | Engineering PASS |
| Ruff trên file thay đổi | Pass | Engineering PASS |
| Security scanner | 0 findings / 202 files / 67.027 lines | Static security PASS |
| OpenWakeWord ambient probe | 3 giây, 36 score, 0 detection | Runtime ambient sample, chưa đủ để kết luận FP/hr |
| Tier-1 engine | `openwakeword` | Model đã được chọn thật |
| True-wake probe | Chưa thu | Recall chưa xác minh |
| Full unit regression sau bản vá mới | Chạy dở, bị dừng khoảng 61% | Chưa được chứng nhận |

Ambient probe chỉ chứng minh model đang chạy và không kích hoạt trong khoảng
thời gian ngắn đó. Nó không chứng minh 10/10 true wake hoặc false-positive rate
trong điều kiện người dùng thực tế.

## 5. Phần đã giải quyết và phần còn mở

### Đã giải quyết ở cấp mã

- Không còn passive activation từ acoustic fallback trong production mặc định.
- Không còn tự động coi thiếu model là classifier thành công.
- Có score thật để phân tích thay vì threshold đoán mò.
- Có model OpenWakeWord và alias đúng.

### Chưa thể kết luận

- Confidence của câu “Hey JARVIS” thật trên microphone người dùng.
- Recall 10/10 hoặc mục tiêu ≥95%.
- False-positive rate với “Affair”, “A fifth”, “Life” trong cùng setup.
- Threshold tối ưu hoặc cần thay model.
- Full repository regression sau thay đổi mới.

## 6. Điều kiện đóng lỗi

Chạy hai phiên với cùng model/microphone:

```powershell
$env:JARVIS_RUN_LIVE_WAKE_PROBE="1"

python tools/wake_word_score_probe.py --label true_wake --duration 120 `
  --out reports/evidence/wake_word_scores_true_wake.json

python tools/wake_word_score_probe.py --label ambient --duration 120 `
  --out reports/evidence/wake_word_scores_ambient.json
```

Sau đó phân tích min/median/p95 confidence, số detection, recall và vùng
overlap. Chỉ thay `openwakeword_threshold` hoặc classifier khi dữ liệu cho
thấy ngưỡng mới có vùng phân tách rõ ràng.

Acceptance tối thiểu:

- true wake recall ≥95%;
- false wake <1 lần/giờ trong idle soak;
- không mở phiên nghe khi thiếu Tier-1 model;
- không false-success từ STT/LLM;
- full unit/E2E/security regression xanh sau thay đổi.

## 7. Verdict hiện tại

```text
Engineering: PASS
Fail-closed production: PASS
Tier-1 model provision: PASS
Ambient runtime sample: PARTIAL PASS
True-wake calibration: PENDING
Full regression: PENDING
Release/GO: NO-GO
```

Không được ghi “đã sửa hoàn toàn” cho lỗi wake-word cho tới khi có true-wake
evidence và hoàn tất full regression.
