# Báo cáo sửa lỗi wake word — 2026-10-04

Source version: `5.2.1` (không bump version, chưa phát hành candidate mới).

Verdict hiện tại: **PASS engineering / runtime live PENDING / product NO-GO**.

## 1. Lỗi được báo cáo

- Không nói “Hey JARVIS” nhưng hệ thống tự mở nghe lệnh; STT sau đó nhận các
  từ như “Affair”, “A fifth”, “Life”.
- Ngưỡng cũ quá nhạy gây false wake; tăng ngưỡng lại làm 10/10 lần gọi thật
  không nhận. Việc đổi một threshold không giải quyết được vùng chồng lấn.

## 2. Nguyên nhân xác nhận từ code và replay

| Nguyên nhân | Bằng chứng | Trạng thái |
|---|---|---|
| OpenWakeWord dùng quyết định một tầng ở threshold `0.50` | `Hey Travis` đạt `0.812034` và từng kích hoạt thẳng | Đã sửa |
| Verifier được gọi quá sớm ở frame đầu candidate | Giọng nữ Việt score `0.465219` nhưng transcript rỗng trước post-roll | Đã sửa |
| `double_clap` bật mặc định có thể mở voice interaction độc lập | `config/default_config.yaml` và wiring trong `jarvis/core/app.py` | Đã tắt mặc định |
| Model verifier không nằm trong PyInstaller artifact | Spec cũ chỉ collect OpenWakeWord/Edge TTS | Đã thêm staging/bundle |
| Chưa có phân phối score giọng thật của người dùng | Không có artifact `true_wake` 10 lần | Còn PENDING |

Các từ STT “Affair/A fifth/Life” là nội dung nhận được **sau khi** microphone
đã bị mở; chúng không tự chứng minh chính các từ này đã kích hoạt classifier.
Việc tắt `double_clap` mặc định loại bỏ một đường mở microphone ngoài wake word.

## 3. Thiết kế sau sửa

```text
PCM microphone
  -> OpenWakeWord score >= 0.02 ?
       no  -> reject
       yes -> candidate, KHÔNG mở UI
              -> thu thêm 0.40 giây
              -> Whisper English + hotwords + VAD
              -> no_speech <= 0.60 AND avg_logprob >= -1.25
              -> transcript có alias JARVIS nguyên token ?
                   yes -> wake
                   no  -> reject và disarm đến khi score hạ
```

Ngưỡng `0.50` vẫn được ghi telemetry để so sánh, nhưng không còn là đường
bypass. Nhờ hai điều kiện độc lập, cổng acoustic đầu có thể thấp để giữ giọng
accent mà không tự biến score `0.02` thành một wake event.

## 4. File thay đổi

- `jarvis/audio/wake_word.py`: post-roll state machine, mandatory transcript
  verification, one-shot/rearm, telemetry verdict/transcript, frozen model
  resolver, no-speech/log-probability gates.
- `config/default_config.yaml`: packaged model, candidate `0.02`, post-roll
  `0.40`, verifier bật, acoustic passive trigger và double-clap tắt mặc định.
- `scripts/build_installer.py`: resolve snapshot `Systran/faster-whisper-tiny`,
  dereference cache vào build staging, fail build nếu thiếu model, thêm model
  vào PyInstaller datas.
- `tests/unit/test_wake_word_two_stage_release.py`: regression mới.
- `tests/unit/test_wake_word_p0.py`: cô lập đúng optional engines trong ca
  kiểm tra fallback.

## 5. Bằng chứng chạy trong lượt này

| Kiểm tra | Kết quả | Tầng verdict |
|---|---:|---|
| Wake/gesture/packaging regression | 135 passed / 16.56s | PASS engineering |
| Focused sau hardening cuối | 71 passed / 9.08s | PASS engineering |
| TTS replay qua OpenWakeWord + Whisper thật | 14/14 đúng | PASS engineering replay |
| Security scanner | 0 findings / 203 files / 69,008 lines / 1.21s | PASS static audit |
| Whisper model staging | model.bin 72.0 MB | PASS build resource |
| Generated PyInstaller spec | compile pass | PASS build contract |
| Full repository final tree | 4,612 passed / 40 skipped / 0 failed/errors / 868.002s | PASS engineering |

Tập replay gồm 3 positive: Anh, nữ Việt, nam Việt; và 11 negative: `Affair`,
`A fifth`, `Life`, `Hey Travis`, `Hey Charlie`, browser/service/weather, ba câu
hội thoại Việt. Audio là Edge TTS, không phải microphone người dùng.

## 6. Phần chưa thể gọi là “sửa hoàn toàn”

1. Chưa thu chính giọng người dùng nói “Hey JARVIS” 10 lần trên microphone và
   phòng thực tế; chưa chứng minh recall 10/10.
2. Chưa chạy ambient dài có TV/quạt/đối thoại để đo false-wakes/hour.
3. Chưa hoàn tất bộ 50 ca voice live >=95%.
4. Model đã được staging cho bundle nhưng chưa build/cài/chạy candidate trên
   một máy Windows sạch khác; chưa có acceptance update/rollback/signing.

Vì vậy không ghi “đã sửa hoàn toàn runtime” hoặc “GO”. Code đã sửa đúng cơ chế
và replay đã vượt các câu lỗi, nhưng product gate chỉ đóng sau dữ liệu live.

Ghi chú lịch sử: full run ngày 2026-10-04 từng phát một `RuntimeWarning` tại
teardown. Lỗi lifecycle này đã được sửa và kiểm tra riêng ở thay đổi sau; nó
không phải bằng chứng đóng gate wake-word live.

## 7. Quy trình nghiệm thu live còn lại

Chạy hai phiên có chủ đích theo
`docs/eval/wake_word_score_calibration.md`: `true_wake` gồm ít nhất 10 lần gọi
ở khoảng cách/âm lượng tự nhiên; `ambient` gồm im lặng, quạt/TV và phát lại các
câu negative. Sau đó báo cáo phải nêu denominator, false-wakes/hour, recall,
microphone/device và giữ nguyên artifact JSON. Không thay threshold nếu hai
phân phối chưa được thu.
