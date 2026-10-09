# Audit bằng chứng live wake-word — 2026-10-10

Source version: `5.2.1` (unreleased).

Verdict hiện tại: **PASS engineering / runtime live PENDING / product NO-GO**.

## Phát hiện

Artifact `live_wake_word_acceptance_report.json` ngày 2026-10-09 ghi
`PASS runtime (0 false alarms)`, nhưng dữ liệu gốc chỉ có **2,06 giây** ambient,
31.616 frame, 76 score event và 0 detection. Artifact được giữ nguyên làm audit
trail, nhưng verdict đó bị **vô hiệu hóa** vì thời lượng không đủ để nghiệm thu
false wake và không có phiên `true_wake` của người dùng.

## Bản vá

Harness hiện fail-closed theo các điều kiện sau:

- `true_wake`: ít nhất 10 lần gọi, ngưỡng chấp nhận >=95%, 0 detection luôn FAIL;
- `ambient`: tối thiểu 120 giây, có detection là FAIL;
- cả hai phiên phải có frame microphone và score event thật;
- engine phải là OpenWakeWord và Whisper verifier phải tải được;
- mặc định giữ sensitivity production; override chỉ xảy ra khi truyền CLI rõ ràng;
- lỗi cấu hình, dependency, microphone, detector, stream hoặc evidence trả Result
  thất bại có cấu trúc và process exit code khác 0;
- report cũ không bị ghi đè nếu không truyền `--overwrite`.

## Bằng chứng review hiện tại

| Kiểm tra | Kết quả | Verdict |
|---|---:|---|
| Harness unit regression | 19 passed / 10.57s | PASS engineering |
| Wake/voice regression liên quan | 169 passed + 25 subtests / 14.29s | PASS engineering |
| Ruff + `git diff --check` | pass | PASS static quality |
| Full repository regression | 4.415 passed, 47 skipped, 268 subtests / 15:32 | PASS engineering |
| Security scanner | 210 files, 69.684 lines, 0 findings / 1.44s | PASS static audit |
| Microphone probe máy hiện tại | 25 input devices, default index 1 | PASS engineering |
| Người dùng nói “Hey JARVIS” >=10 lần | chưa chạy | runtime PENDING |
| Ambient/TV/quạt/negative phrases >=120 giây | chưa chạy | runtime PENDING |

Probe thiết bị chỉ chứng minh hệ điều hành nhìn thấy input device. Nó không chứng
minh recall, false-alarm rate hoặc khả năng phát hành.

## Lệnh nghiệm thu còn lại

```powershell
python tools/live_wake_word_acceptance.py --label true_wake --duration 25 `
  --expected-wakes 10 --min-recall 0.95 `
  --out reports/evidence/live_wake_true.json

python tools/live_wake_word_acceptance.py --label ambient --duration 120 `
  --min-ambient-seconds 120 `
  --out reports/evidence/live_wake_ambient.json
```

Trong phiên ambient cần tái tạo đúng điều kiện lỗi: không nói wake word, có
TV/quạt/hội thoại và phát các câu “Affair”, “A fifth”, “Life”. Chỉ đóng gate
runtime khi cả hai report mới đạt `status=SUCCESS` và `success=true`.
