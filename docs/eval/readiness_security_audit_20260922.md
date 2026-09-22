# Kiểm toán và bản vá readiness/security — 2026-09-22

## 1. Phạm vi và kết luận

Kiểm tra trực tiếp workspace bắt đầu từ commit `a11c5e6`, source version
`5.2.1`. Đây là đợt sửa lỗi Core/Safety/Skill và cách kiểm thử; không phải
chứng nhận toàn bộ D-01–D-17, H-tasks hay phát hành Beta.

**Product release: NO-GO.** Không nâng trạng thái dựa trên số unit test.
Các kết luận về API/device/installer thật của những ngày trước là lịch sử,
không được phiên này tái chứng nhận.

## 2. Sửa lại các nhận định trong báo cáo được cung cấp

| Nhận định cũ | Đối chiếu trực tiếp |
|---|---|
| 2.421 tests xanh, 0 P0 | Số test lịch sử không chứng minh cây mã hiện tại. Chưa thực hiện audit toàn bộ để khẳng định 0 P0. Xem số đo phiên này bên dưới. |
| GATE-01 là gate duy nhất | `docs/READINESS_DASHBOARD.md` liệt kê 6 gate mở: 01, 02, 03, 04, 06, 07. Gate 05 đóng theo evidence lịch sử. |
| Self-Coding chưa tồn tại | Có hai đường: template `jarvis/skills/skill_synthesizer/` và `DynamicSkillSynthesizer` trong `jarvis/skills/synthesizer.py`, được app khởi tạo và gọi. Template thiếu backend không đồng nghĩa cả tính năng không tồn tại. |
| 29 modules nên không có god-class | Đếm được 29 thư mục con; không phải phép đo coupling/cohesion. `JarvisApp` và `LLMIntentRouter` đều trên 2.800 dòng. |
| Bốn tầng bảo mật tương đương | Regex/AST/policy và Credential Manager không thay thế ranh giới cách ly OS. Chạy với sandbox compat không chứng minh Low Integrity. |
| Result model hoàn toàn chưa có | `ActionResult` đã tồn tại với 6 trường chính; phiên này phát hiện và sửa một số lỗi chuẩn hóa/truyền trạng thái. Chưa xác nhận mọi backend đã chuyển sang cùng model. |

## 3. Các bản vá thực hiện

| ID | Nguyên nhân gốc | Thay đổi | Giới hạn |
|---|---|---|---|
| A-01 | Token đã confirm không bị kiểm tra TTL lúc thực thi | Kiểm tra hết hạn cả token CONFIRMED ở interceptor | Không tuyên bố cơ chế token là HMAC hoặc đã kiểm toán mật mã |
| A-02 | Pending payload dùng chung tham chiếu với caller | Deep-copy payload khi gate/intercept | Không chứng nhận mọi bên giữ tham chiếu nội bộ đều không thể thay đổi state |
| A-03 | Hậu tố `_status`/`_read` cho phép né phân loại lệnh nguy hiểm | Thay miễn trừ hậu tố rộng bằng danh sách tên read-only cụ thể | Cần rà tiếp toàn bộ action registration và alias |
| A-04 | Tên skill không được kiểm tra trước khi xóa, thiếu metadata vẫn được xóa | Kiểm tra tên/path, cấm symlink/outside-root, yêu cầu `synthesized is True` | Không coi kiểm tra path này là sandbox chống mọi race của process ngoài |
| A-05 | Create có thể ghi đè built-in | Từ chối target đã tồn tại, parse mã trước khi tạo thư mục | Chưa có transaction đa tệp khi disk-write thất bại |
| A-06 | Update dynamic skill xóa bản cũ trước validation | Không xóa thư mục trước validation/dry-run; overwrite cần explicit; chặn child symlink/hardlink; lock và atomic replace từng tệp, retry 5 lần khi Windows khóa file, cleanup finally | Chưa bảo đảm atomic commit của cả package khi mất điện/lỗi ghi |
| A-07 | Template chưa triển khai hoặc lỗi vẫn giữ `success=True` | NOT_IMPLEMENTED trả false; fetch/checker lỗi trả false; bỏ metrics 0 giả | Không tự nhận đã triển khai notifier/calculator/sender/converter/file-reader |
| A-08 | Nội dung mô tả được chèn thẳng vào mã | Dùng Python string literal an toàn cho docstring | Không chứng nhận mã do LLM cung cấp là an toàn tuyệt đối |
| A-09 | BLOCKED/UNAVAILABLE/NOT_CONFIGURED không được enum và dispatcher nhận diện | Bổ sung trạng thái và mã lỗi mặc định, không chuẩn hóa thành thành công; giữ metadata của ActionResult và retryable/message của dict | Vẫn còn trạng thái legacy FAILED/RATE_LIMITED/LABS_DISABLED; chưa hoàn tất migration toàn bộ backend |
| A-10 | Test thường có thể gọi network/account thật | Chặn TCP/DNS Python ra ngoài trong test process theo mặc định; cho phép loopback; live cần marker và opt-in | Không phải firewall: không chặn UDP sendto, child process, native transport hoặc code tự thay socket |
| A-11 | Live infra probe tự load .env, tự opt-in IMAP, ghi đè evidence | Skip module trước khi load .env nếu chưa opt-in infra | Không chạy lại probe để lấy runtime evidence trong phiên này |

Đã khôi phục ba tài liệu evidence bị lượt probe ban đầu ghi đè về nội dung
trước khi chạy; không dùng kết quả đó để thay trạng thái nghiệm thu.

## 4. Kiểm thử và khả năng tái lập

Không cộng số test của các lượt chạy chồng lặp để tạo tổng.

| Phạm vi | Kết quả | Thời gian | Đọc đúng bằng chứng |
|---|---|---|---|
| 6 file test tập trung sau review và guard singleton | 125 passed, 34 subtests passed | 13,51s | PASS engineering / PASS fail-closed trong phạm vi test |
| Unit trước hai sửa đổi cuối từ review | 2.453 passed, 4 skipped, 268 subtests passed | 417,88s | Checkpoint trước sửa code mặc định/hardlink; không thay kết quả cuối |
| Unit sau bản vá production cuối | 2.458 passed, 4 skipped, 268 subtests passed | 411,72s | Exit 0; PASS engineering cho unit scope, không phải runtime hardware |
| Tests mở rộng, `--maxfail=20` | 1.031 passed, 20 failed, 35 skipped | 281,86s | Exit 1; dừng ở 20 failures, không chạy hết suite, không suy ra tổng số lỗi |
| Live infra mặc định không opt-in | 1 module skipped | 0,06s | PASS cơ chế opt-in, không phải PASS runtime |

Artifacts pytest nằm trong `reports/evidence/readiness_security_{scoped,unit,full}_20260922.xml`.
Summary máy đọc được, danh sách 20 failures và SHA-256 của source/artifacts:
`reports/evidence/readiness_security_summary_20260922.json`.
JUnit có thể tính subtests vào số testcase: không đồng nhất tổng XML với
số `passed` của pytest console.

Unit và lượt fail-fast bắt đầu trước thay đổi nhỏ cuối cùng để tái sử dụng guard
qua nhiều `pytest.main()`; production code không đổi. Guard singleton cuối được
kiểm tra bằng lượt scoped 125 tests và harness hai phiên pytest dùng DNS giả.
4 skipped của unit là 3 ca matplotlib/chart và 1 ca khám phá Vosk model path;
không tính chúng là pass. AST parse 197 tệp production và `git diff --check` đều đạt.
Chưa chạy ruff (không có trong venv); chưa kiểm tra CI remote cho revision này.

- Regression mới nằm trong `tests/unit/test_readiness_security_regressions.py`.
- Tái hiện RED trước sửa: token/path/template; dynamic update mất bản cũ;
  docstring/metrics; 9 ca trạng thái unavailable; 4 ca metadata dispatcher.
- Những lượt test rộng ban đầu đã xuất hiện failures và Telegram HTTP 409, bị dừng
  vì có network thật; không có tổng pass/fail hợp lệ cho các lượt bị dừng.
  Guard function-scoped để lại khoảng trống giữa tests cho thread polling rò rỉ;
  guard cuối giữ suốt process, singleton qua nhiều lần gọi `pytest.main()`.
  Đã kiểm tra hai phiên `pytest.main()` liên tiếp: mỗi phiên 2 policy tests pass,
  guard còn chặn sau teardown, quyền phiên hiện tại được dùng (DNS giả, không gọi mạng thật).
- Unit và toàn bộ `tests/` dùng network guard, timeout 60s.
- Không xem skipped, opt-in chưa bật, missing credential hoặc compat sandbox
  là PASS runtime.

Lệnh kiểm thử (PowerShell, Python trong `.venv`):

```powershell
$env:JARVIS_HEADLESS='1'
$env:JARVIS_MOCK_AUDIO='1'
$env:JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK='1'
.venv\Scripts\python -m pytest tests/unit -o addopts='' -q --tb=short --timeout=60 --junitxml=reports/evidence/readiness_security_unit_20260922.xml
.venv\Scripts\python -m pytest tests -o addopts='' -q --tb=short --timeout=60 --maxfail=20 --junitxml=reports/evidence/readiness_security_full_20260922.xml
```

Môi trường phát hiện pytest 9.1.1, trong khi pyproject khai báo `pytest>=8,<9`.
Đã cài dependency dev bị thiếu `pytest-timeout` 2.4.0 để chặn treo test.
Không gọi môi trường này là clean-env CI parity.

Live infrastructure chỉ chạy khi người vận hành chủ động bật cả
`JARVIS_RUN_LIVE_INFRA_TESTS=1` và `JARVIS_RUN_LIVE_NETWORK_TESTS=1`.
Không bật các cờ đó cho unit/regression thường ngày.

### Phân nhóm 20 failure đầu tiên (chưa phải 20 root causes đã xác nhận)

| Nhóm | Số ca | Triệu chứng quan sát được |
|---|---:|---|
| Screenshot/computer-use | 2 | JPEG ROI rỗng; kết quả tọa độ khác kỳ vọng khi screen dimension không hợp lệ |
| Intent router | 2 | Chuỗi rất dài vẫn thành system_volume; câu "kiểm tra bộ nhớ" không vào hardware_telemetry |
| Scanner/safety | 7 | LABS_DISABLED khác PERMISSION_DENIED; capture không gọi process như test kỳ vọng; ActionResult không có packet_count |
| Voice/audio/TTS | 2 | Queue chỉ xử lý 1/50; fallback audio mất khoảng 5 giây thay vì <0,1 giây |
| Web/RSS/briefing | 2 | RSS còn HTML; payload briefing không có speech_text như test kỳ vọng |
| Overlay UI | 1 | Test kỳ vọng toàn văn nhưng nhận text đã truncate |
| Telegram/photo | 1 | Kết quả gửi ảnh false, test kỳ vọng true |
| Healing | 2 | Mock RAM không giảm về ngưỡng kỳ vọng |
| Cache performance | 1 | 2,450ms so với ngưỡng <2ms |

Hai suite chạy đồng thời nên failure timing chưa phải benchmark độc lập;
phải đo lại riêng trước khi quy kết hồi quy hiệu năng. Các ca LABS_DISABLED
vẫn là từ chối thực thi, không tự động chứng minh bypass. Chưa sửa test để
nới ngưỡng, bỏ safety hoặc giả side-effect làm xanh bộ suite.

Danh sách đầy đủ từng node nằm trong artifact JUnit và summary JSON cùng thư mục evidence.

## 5. Cấu trúc và nâng cấp còn lại

Đếm cây mã sau bản vá: **29 thư mục con trực tiếp, 197 tệp Python, 64.813
dòng vật lý** (bao gồm blank/comment/docstring; không phải số module logic).
AST parse thành công cho toàn bộ 197 tệp. Đo AST cho thấy các lớp lớn: `JarvisApp` 2.901 dòng,
`LLMIntentRouter` 2.828, `AlwaysOnOverlay` 1.620,
`PlaywrightBrowserDriver` 1.057, `BrowserSessionManager` 924.
Đây là tín hiệu để rà soát trách nhiệm và dependency; không tự động kết luận
mọi lớp dài đều là god-class. Không refactor diện rộng cùng đợt vá safety.

Failure đã tái hiện độc lập ngoài nhóm bản vá:
`tests/e2e/test_tiers_1_to_4.py::test_r2_r3_vision_zero_size_roi_or_corrupt_bytes`
gây `ValueError: cannot write empty image` tại JPEG encoding trong
`jarvis/vision/screen.py`. Lượt `-x` file này: 52 passed, 1 failed trong 5,93s.
Chưa sửa lỗi này, và chưa xác nhận mọi failure còn lại có cùng nguyên nhân.

Review độc lập phát hiện vấn đề child-link overwrite và mã lỗi mặc định OK;
cả hai được tái hiện bằng 6 ca RED, sửa và review lại. Không còn finding từ
lượt review giới hạn đó; đây không phải audit bảo mật toàn hệ thống.

| Thứ tự | Việc tiếp theo | Điều kiện hoàn thành |
|---|---|---|
| 1 | Phân loại từng failure của suite an toàn; pin lại môi trường đúng pyproject | Không có failure chưa giải thích; re-run có artifact, exit code và thời gian |
| 2 | Hoàn tất contract Result ở mọi backend, bao gồm bool/None/nested payload và status legacy | Contract tests sync/async; không thất lạc status/code/message/data/retryable; không success khi chưa thực thi |
| 3 | Rà Health model/backend → UI | READY từ probe authoritative; phân biệt LIMITED/UNAVAILABLE/ERROR; test không false READY |
| 4 | Hoàn thiện safety action inventory và package persistence | Mọi lệnh nguy hiểm qua dispatcher; test alias/replay/concurrency; cập nhật skill atomic và có phục hồi |
| 5 | Sandbox compat trong bản phân phối | Build production không vô tình bật fallback; bằng chứng Low Integrity thật, không chỉ env flag |
| 6 | Labs/Core và template thiếu backend | Chức năng chưa đủ E2E đặt Labs opt-in; không khai báo tính năng chưa chạy; Labs vẫn bị safety chặn |
| 7 | Regression browser đối kháng và dữ liệu 10 workflow | Chạy protocol, lưu từng trial/output; không gộp mock thành OS evidence |
| 8 | Installer/update/rollback/support bundle | Máy sạch khác máy dev; checksum/trust/update/rollback; kiểm tra secret-redaction thực tế |
| 9 | Tổng hợp release gates | CI đúng revision xanh; risk register có accepted risks; đủ runtime evidence rồi mới xét GO |

Các điểm cần phối hợp Hòa/Thái: voice/wake/STT và UI health/onboarding.
Không chuyển phần Hòa thành công việc đã hoàn thành của Hưng.

## 6. Các gate không được đóng bởi bản vá này

- GATE-01: 200 trials real voice → real STT → real OS. Protocol hiện hành
  yêu cầu >=19/20 mỗi workflow và >=190/200 tổng; không hạ xuống ngưỡng khác.
- GATE-02: thu âm/wake-word theo protocol, đủ cỡ mẫu và điều kiện đo.
- GATE-03: 50 ca voice người thật sau thay đổi; >=48/50 (96%, mức nguyên
  nhỏ nhất đáp ứng >=95%).
- GATE-04: Zalo OA approval và send/receive thật.
- GATE-06: Home Assistant write path thật với hub sẵn sàng.
- GATE-07: capture thật với Npcap/TShark khả dụng.
- Clean-machine install/update/rollback và production signing/trust vẫn
  cần evidence riêng, dù không được liệt kê thành gate riêng trong bảng 7 gate.

Không xác nhận GO, 0 P0, "hoàn thành tất cả" hoặc tỷ lệ hoàn thành phần trăm
khi chưa có mẫu số trách nhiệm và acceptance evidence tương ứng.

## 7. Trạng thái bàn giao

Code, test, README, CHANGELOG, ROADMAP và báo cáo đã được chỉnh trong workspace.
**Chưa commit/push**: điều kiện full-suite xanh của AGENTS.md chưa đạt. Không
publish release hoặc ghi đè gate status trong dashboard để làm dự án có vẻ hoàn tất.

Ưu tiên kế tiếp là triage 20 failure đã ghi nhận, trước hết phân biệt lỗi thực
thi với test contract lỗi thời; tiếp theo chạy lại toàn bộ suite trong môi trường
đúng dependency pin. Chỉ sau đó mới tiếp tục đóng runtime/installer gates bằng
bằng chứng thiết bị, tài khoản và máy sạch thật.
