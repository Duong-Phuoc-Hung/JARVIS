# Software Requirements Specification (SRS)

## JARVIS — Trợ lý AI cá nhân tự trị cho Windows

**Phiên bản tài liệu:** 1.0  
**Ngày:** 23/09/2026  
**Trạng thái:** Baseline hiện trạng — chưa phải Product Release GO  
**Phạm vi đánh giá:** Repository JARVIS tại revision làm việc ngày 23/09/2026

## 1. Mục đích và phạm vi

Tài liệu này mô tả hệ thống JARVIS hiện có trên Windows, các chức năng đã triển khai, giao diện nội bộ, yêu cầu an toàn, bằng chứng kiểm thử và các giới hạn chưa đủ điều kiện phát hành. Tài liệu không coi các tính năng chỉ có trong tài liệu cũ, stub hoặc trạng thái fail-closed là runtime success.

### 1.1 Mục tiêu sản phẩm

JARVIS nhận lệnh bằng giọng nói/văn bản, phân tích intent, áp dụng safety ở core/dispatcher, thực thi tác vụ Windows hoặc backend tích hợp, rồi trả kết quả có trạng thái trung thực cho người dùng.

### 1.2 Ngoài phạm vi của baseline

- Xác nhận credential thật cho Telegram/Zalo/Discord/email/Home Assistant.
- Nghiệm thu installer/update/rollback trên máy sạch.
- Xác nhận microphone, TShark/Npcap, WMI brightness hoặc thiết bị Home Assistant trên mọi máy.
- Cho phép Labs/experimental hoạt động mặc định.

## 2. Bối cảnh và người dùng

| Nhóm | Nhu cầu |
|---|---|
| Người dùng Windows | Mở ứng dụng đã cài, mở website, tìm kiếm, phát nhạc, âm lượng, thời tiết, timer, reminder, note, screenshot và truy vấn trạng thái máy. |
| Core/dispatcher | Chuẩn hóa request, safety gate, gọi đúng handler và không trả success giả. |
| Connector/backend | Giao tiếp email, Telegram, Discord, Zalo, Home Assistant và dịch vụ web khi đã cấu hình. |
| Maintainer/release | Chạy test, scanner, tạo evidence, phân biệt engineering/fail-closed/runtime/release. |

## 3. Kiến trúc logic hiện tại

```text
Input (voice/text/UI/connector)
        |
        v
STT / LLM Router / rule fallback
        |
        v
IntentResult + parameters
        |
        v
Core Dispatcher -> SafetyInterceptor / confirmation / rate limits
        |
        +--> Windows automation (app catalog, browser, volume, brightness, screenshot)
        +--> Web intelligence (weather, news, finance, briefing)
        +--> Communications (Telegram, Discord, IMAP, Zalo)
        +--> Labs / optional backends (TShark, Home Assistant, experimental skills)
        |
        v
Normalized outcome -> UI overlay / TTS / connector response / evidence log
```

### 3.1 Nguyên tắc thiết kế bắt buộc

1. **Fail-closed:** thiếu cấu hình, binary, thiết bị hoặc dependency phải trả lỗi có mã/trạng thái; không được trả `success=True` ngầm định.
2. **Safety ở core:** UI/voice chỉ gửi request và hiển thị kết quả; không bypass confirmation.
3. **Không bịa bằng chứng:** số liệu phần cứng, packet capture, RAM reclaim và runtime success phải xuất phát từ backend thật hoặc được đánh dấu mock/test.
4. **Catalog-first:** mở ứng dụng phải tra danh mục cài đặt/định danh thật, xử lý ambiguity và xác minh launch; không đoán bằng substring tùy ý.

## 4. Yêu cầu chức năng

### FR-01 — Nhận và định tuyến lệnh

Hệ thống phải nhận text hoặc transcript, chuẩn hóa tiếng Việt có/không dấu, định tuyến sang action cụ thể và trả `IntentResult` có `action_name`, `parameters`, `source`, `response_text`.

### FR-02 — Mở ứng dụng Windows

Hệ thống phải khám phá ứng dụng cục bộ, hỗ trợ alias an toàn, từ chối app không tìm thấy hoặc nhiều kết quả, focus/reuse cửa sổ khi có thể và không báo thành công nếu launch/window verification thất bại.

### FR-03 — Website và tìm kiếm

Hệ thống phải mở URL/query với encoding đúng, dùng browser backend được phép, và trả lỗi khi browser từ chối hoặc target không hợp lệ.

### FR-04 — Tác vụ desktop an toàn

Weather/search/open app/volume/timer/note/screenshot được chạy theo đường dẫn an toàn; shutdown/restart/xóa/uninstall/rollback/gửi message/email/Home Assistant action phải qua confirmation/safety policy phù hợp.

### FR-05 — Quan sát phần cứng

Hệ thống phải định tuyến truy vấn CPU/RAM/GPU/disk/battery và status hệ thống; alias có dấu và không dấu phải cho cùng component. Không được tạo số liệu giả khi backend không khả dụng.

### FR-06 — Web intelligence và briefing

Weather/news/finance/briefing phải có offline/cache fallback được đánh dấu đúng, làm sạch HTML/XML đầu vào và cung cấp dữ liệu speech/UI tương thích.

### FR-07 — Voice pipeline

Onboarding và runtime phải phân biệt `READY`, `LIMITED`, `UNAVAILABLE`, `ERROR`, `NOT_CONFIGURED`; microphone/STT/TTS thiếu hoặc lỗi không được biến thành success giả.

### FR-08 — Communications

Telegram/Discord/Zalo/email phải kiểm tra credential, allowlist/admin/safety và trả lỗi `NOT_CONFIGURED`, `AUTH_FAILED`, `TIMEOUT`, `UNAVAILABLE` hoặc mã tương ứng khi chưa thể gửi/đọc thật.

### FR-09 — Labs

Labs là experimental, opt-in, bị feature flag và không được bypass safety. TShark/Npcap, Home Assistant và connector experimental chỉ được công nhận runtime khi có resource thật.

### FR-10 — Logging/evidence

Mỗi kiểm thử/release phải lưu số liệu thực, artifact, trạng thái và giới hạn; không dùng số liệu từ lần chạy cũ sau thay đổi lớn.

## 5. Mô hình trạng thái và kết quả

### 5.1 Result model hiện hành

Dispatcher hiện đã có seam chuẩn hóa dùng cho backend mới:

`BackendResult(success, status, code, message, data, retryable)` trong
`jarvis/core/result_model.py`. Handler cũ vẫn được chuyển đổi tương thích qua
`ActionResult`; migration toàn bộ connector chưa hoàn tất.

Các trạng thái chuẩn:

| Status | Ý nghĩa |
|---|---|
| `SUCCESS` | Hành động đã hoàn tất thật. |
| `ERROR` | Đã chạy nhưng lỗi thực tế. |
| `TIMEOUT` | Quá thời gian cho phép. |
| `BLOCKED` | Safety/policy chặn. |
| `UNAVAILABLE` | Backend/device/dependency không dùng được. |
| `NOT_CONFIGURED` | Chưa có account/credential/config cần thiết. |

### 5.2 Health status

| Health | Điều kiện |
|---|---|
| `READY` | Chức năng chính đã được backend xác nhận hoạt động. |
| `LIMITED` | Vẫn dùng được nhưng thiếu một phần hoặc đang fallback. |
| `UNAVAILABLE` | Thiếu mic/account/dependency/backend. |
| `ERROR` | Đã cấu hình đủ nhưng chạy thực tế lỗi. |

UI chỉ được hiển thị `READY` khi backend xác nhận; không tự suy đoán từ việc module import thành công.

## 6. Yêu cầu phi chức năng

| ID | Yêu cầu |
|---|---|
| NFR-01 | Safety check phải nằm ở dispatcher/core và không bị bypass bởi UI/voice. |
| NFR-02 | Credential không commit; secret thật nằm ngoài repository và tách khỏi tài khoản Beta. |
| NFR-03 | Mọi write persistence cần atomic replace, lock và retry phù hợp trên Windows. |
| NFR-04 | Router và parser phải có giới hạn kích thước/đệ quy để chống ReDoS/DoS. |
| NFR-05 | Tác vụ UI không được làm treo worker; callback exception phải được cô lập. |
| NFR-06 | Mọi claim runtime phải truy nguyên tới command/output/exit code hoặc artifact. |
| NFR-07 | Windows path, subprocess, browser và HTTP phải dùng allowlist/argument-list/timeout. |
| NFR-08 | Hệ thống phải giữ tương thích headless cho CI nhưng không coi headless mock là runtime evidence. |

## 7. Bằng chứng kiểm thử hiện tại

### 7.1 Kết quả mới nhất

| Phạm vi | Kết quả | Phân loại |
|---|---:|---|
| E2E | 290 passed, 21 skipped, 0 failed, 23.72s | `PASS engineering` cho E2E; runtime thật còn tùy resource |
| Unit | 3.002 passed, 3 skipped, 0 failed, 334.31s | `PASS engineering` |
| Full repository | Chưa chứng nhận: các lần chạy dừng ở test legacy ngoài unit (safety/telemetry/voice simulation); không dùng số partial làm full-green | `NO-GO` |
| Security subset | 66 passed, 0 skipped, 0 failed, 8.40s | `PASS engineering` |
| Voice/app/release scoped | 240 passed, 0 skipped, 0 failed, 8.00s | `PASS engineering` |
| 10-workflow routing matrix | 10/10 intent route đúng (100%), chưa phải runtime | `PASS engineering` |
| Ruff file đã sửa | Pass | `PASS engineering` |
| Security scanner | 0 findings, 202 files, 66.922 dòng | `PASS engineering`, scope static giới hạn |

### 7.2 Blocker còn lại

Các assertion healing E2E cũ đã được sửa để phản ánh telemetry-only: production không tự giảm
`ram_percent` và không khai báo `reclaimed_ram` nếu backend không quan sát được delta.
Full repository còn các test legacy cần cập nhật theo safety/telemetry contract; theo yêu cầu không tiếp tục lặp full-suite khi cùng nhóm lỗi chưa được phân loại riêng.

### 7.3 Giới hạn bằng chứng

- Scanner tĩnh không chứng minh mọi runtime path an toàn.
- `TOOL_NOT_FOUND`, `LABS_DISABLED`, `PENDING_CREDENTIALS` là fail-closed pass, không phải runtime pass.
- Chưa có clean-machine installer/update/rollback evidence.
- Chưa có 50 ca voice live và chưa có authenticated Spotify playback evidence.
- 10 workflow mới có routing evidence; runtime evidence chỉ có Calculator/Notepad trong probe riêng.
- Wake-word calibration chưa có runtime evidence: detector đã phát score telemetry và có probe opt-in tại `tools/wake_word_score_probe.py`, nhưng chưa thu đủ phiên `true_wake`/`ambient` trên microphone thật.
- Chưa có live microphone, account connector, TShark/Npcap hoặc Home Assistant evidence trong baseline này.

## 8. Tiêu chí nghiệm thu Beta

Beta chỉ được `GO` khi đồng thời thỏa:

1. Main CI xanh 100%; 0 P0; không crash/runaway/data-loss đã biết.
2. 10 workflow Beta đạt tối thiểu 95% tổng thể và không workflow nào dưới 90%.
3. 50 ca voice live đạt tối thiểu 95%.
4. Không có false-success; installer/update/rollback pass trên máy sạch.
5. P1 còn lại có issue, workaround và accepted risk rõ ràng.
6. Credential/connector/device runtime evidence được thu thập độc lập với mock/CI.

## 9. Ma trận trạng thái hiện tại

| Tầng | Trạng thái |
|---|---|
| Engineering/unit | **PASS engineering** — unit 3.002/3 skipped, E2E 290/21 skipped, security 66, scanner 0 findings; full repository chưa được chứng nhận. |
| Fail-closed | **PASS** cho các đường dẫn đã kiểm tra. |
| Runtime thật | **PENDING/PARTIAL** — E2E host pass, resource thật chưa phủ hết. |
| Internal pilot | **NOT AUTHORIZED** — chưa đóng full suite và runtime gates. |
| Product release | **NO-GO** — chưa đạt điều kiện Beta GO. |

## 10. Tài liệu và artifact tham chiếu

- `docs/eval/runtime_fix_verification_20260923.md`
- `docs/eval/workflow_10_windows_runtime_20260923.md`
- `docs/eval/wake_word_score_calibration.md`
- `reports/evidence/fixes_e2e_latest_20260923.xml`
- `reports/evidence/system_completion_voice_apps_release_20260923.xml`
- `reports/evidence/system_completion_healing_20260923.xml`
- `reports/evidence/system_completion_unit_final_20260923.xml`
- `reports/evidence/system_completion_e2e_final_20260923.xml`
- `reports/evidence/system_completion_security_final_20260923.xml`
- `reports/evidence/system_completion_scanner_final_20260923.json`
- `reports/evidence/system_completion_targeted_final_20260923.xml`
- `reports/evidence/fixes_unit_lastfailed_20260923.xml`
- `reports/evidence/fixes_scanner_final_20260923.json`
- `docs/ROADMAP.md`
- `CHANGELOG.md`
