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

Engineering seam và unit tests đã pass. Confidence thật của 10 lần nói
“Hey JARVIS” và các false wake chưa được thu trong môi trường này, vì vậy
H-06 calibration/runtime vẫn **PENDING** và chưa có cơ sở để tuyên bố recall,
false-positive rate hoặc GO.

Probe ngày 2026-09-24 xác nhận máy hiện chưa có Tier-1 wake-word model được
cấu hình: kết quả `NOT_CONFIGURED / WAKE_CLASSIFIER_NOT_CONFIGURED`, engine
`acoustic_fallback`. Vì vậy chưa thể thu confidence classifier; fallback không
được phép dùng làm bằng chứng calibration.

Desktop production đã được fail-closed: `jarvis/core/app.py` truyền
`allow_acoustic_passive_trigger=False`. Khi chưa có Tier-1 model, người dùng
vẫn có thể dùng PTT/hotkey, nhưng acoustic heuristic không tự mở phiên nghe.
