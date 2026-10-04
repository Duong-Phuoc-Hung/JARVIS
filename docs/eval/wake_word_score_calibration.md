# Wake-word score calibration (H-06)

## Mục đích

Ngưỡng wake-word không được tăng/giảm theo cảm tính. Detector hiện ghi nhận
confidence thật của classifier cho cả mẫu dưới ngưỡng và mẫu phát hiện qua
`WakeWordScoreEvent`. Probe không tự gán nhãn và không tự đề xuất threshold.

## Cách thu dữ liệu trên máy thật

Mở hai phiên riêng, cùng một microphone và cấu hình. Ở phiên `true_wake`, nói
“Hey JARVIS” theo các mức âm lượng tự nhiên; ở phiên `ambient`, không nói wake
word và tái tạo các nguồn gây false wake đã quan sát ("Affair", "A fifth",
"Life", tiếng TV/quạt).

```powershell
$env:JARVIS_RUN_LIVE_WAKE_PROBE = "1"
python tools/wake_word_score_probe.py --label true_wake --duration 120 `
  --out reports/evidence/wake_word_scores_true_wake.json
python tools/wake_word_score_probe.py --label ambient --duration 120 `
  --out reports/evidence/wake_word_scores_ambient.json
```

Các file là runtime evidence khi lệnh hoàn tất với microphone thật. So sánh
phân phối `confidence` và `detected` giữa hai file; chỉ sau đó mới thay đổi
`openwakeword_threshold` hoặc classifier. Nếu probe trả `BLOCKED`, `UNAVAILABLE`
hoặc `ERROR` thì không được ghi nhận là pass runtime.

## Trạng thái hiện tại

Engineering seam đã được nâng từ một threshold đơn thành cascade hai tầng:

1. OpenWakeWord score `>=0.02` chỉ tạo candidate, không kích hoạt UI.
2. Detector thu thêm `0.40s` để tránh xác minh khi câu chưa nói hết.
3. Faster-Whisper chạy VAD và kiểm tra `no_speech_prob <= 0.60`,
   `avg_logprob >= -1.25`, rồi yêu cầu alias JARVIS nguyên token.
4. Score cao hơn ngưỡng cũ `0.50` vẫn phải qua bước 3; candidate bị từ chối
   không được inference lặp lại cho tới khi score hạ dưới gate.

Replay tổng hợp bằng Edge TTS, decode 16-kHz mono và đưa qua model production
thật đạt **14/14 đúng**: ba positive (`Hey JARVIS` giọng Anh, nữ Việt, nam Việt)
đều kích hoạt; 11 negative đều bị chặn. `Affair`, `A fifth`, `Life` có score tối
đa lần lượt `0.000030`, `0.000015`, `0.000011`. Hai near-negative quan trọng
`Hey Travis` (`0.812034`) và `Hey Charlie` (`0.452293`) vượt/tiệm cận ngưỡng
cũ nhưng bị verifier đọc đúng transcript và từ chối. Đây là bằng chứng replay
tổng hợp qua model thật, **không phải giọng người dùng thật**.

Confidence của 10 lần chính người dùng nói “Hey JARVIS” và long-idle ambient
vẫn chưa được thu. Vì vậy H-06 hiện là **PASS engineering**, còn calibration
runtime vẫn **PENDING**; chưa có cơ sở tuyên bố recall live, false-wakes/hour
hoặc GO.

Probe `NOT_CONFIGURED` ngày 2026-09-24 là evidence lịch sử. Cấu hình sản phẩm
hiện tự dùng packaged `hey_jarvis_v0.1.onnx`; kiểm tra resource ngày 2026-10-04
đã chọn `engine=openwakeword`. Faster-Whisper tiny cũng được build staging thành
model thật 72.0 MB để bundle offline. Chưa build/cài candidate lên máy sạch nên
không nâng kết quả resource này thành clean-machine runtime pass.

Desktop production đã được fail-closed: `jarvis/core/app.py` truyền
`allow_acoustic_passive_trigger=False`. Khi chưa có Tier-1 model, người dùng
vẫn có thể dùng PTT/hotkey, nhưng acoustic heuristic không tự mở phiên nghe.
