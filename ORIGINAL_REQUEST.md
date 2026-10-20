# Original User Request

## Initial Request — 2026-10-18T16:17:19Z

# Teamwork Project Prompt — Final Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Full Swarm Team (Argon Sovereign Core + Academic Researcher + Security Auditor + Deep Coder + Seam Tester)

Xây dựng hệ thống tự hành liên tục (Continuous Autonomous Self-Upgrading & Research Engine) cho JARVIS: tự động nghiên cứu các công trình học thuật mới nhất (ArXiv, IEEE, PNAS, ITU-T), mã nguồn mở đỉnh cao (GitHub Trending), và tin tức công nghệ mạng xã hội; đối soát mã nguồn với các tiêu chuẩn công nghiệp; thực thi kiểm thử hồi quy (Seam-First TDD); tự động phát hiện và vá lỗi bằng cơ chế Sandbox Test-Time Compute (TTC); kết hợp lịch trình tự động chạy ngầm hàng ngày (Scheduled Automation Sidecar) để đưa dự án JARVIS đạt trạng thái phần mềm thương mại hoàn chỉnh (Commercial Product Release GO).

Working directory: d:\Software GitCode\JARVIS
Integrity mode: development

## Requirements

### R1. Comprehensive Academic & Industry Tech Radar
Tự động quét, phân tích và trích xuất các kỹ thuật, thuật toán và kiến trúc tiên tiến nhất từ:
- Tài liệu học thuật bình duyệt & preprints: ArXiv CS/AI, IEEE, ACM, PNAS, ITU-T (Voice Biometrics, Streaming STT, On-device Fast Semantic Routing, Low-latency Acoustic Processing).
- Hệ sinh thái mã nguồn mở: GitHub Trending, các dự án AI Desktop Assistant hàng đầu thế giới.
- Mạng xã hội kỹ thuật và blog công nghệ chuyên sâu.
Toàn bộ tri thức thu thập được chuẩn hóa và nạp vào SQLite Continuous Learning Vault / Memory Graph của Argon để phục vụ nâng cấp mã nguồn.

### R2. Codebase Deep Audit & Commercial Feature Upgrades
Đối chiếu toàn bộ codebase JARVIS (`d:\Software GitCode\JARVIS`) với các tri thức mới từ Tech Radar và các tiêu chuẩn khắt khe:
- Windows Atomic Persistence (tuân thủ nghiêm ngặt khóa threading, snapshot in-memory, file tạm `.tmp.<thread_id>.<timestamp_ns>` với retry loop 5 lần xử lý WinError 5).
- Fail-Closed Architecture (trả mã lỗi cụ thể khi thiếu binary, device hoặc credential, tuyệt đối không ghost success).
- Nâng cấp độ trễ phản hồi E2E < 500ms cho 10 workflows cốt lõi, hoàn thiện Voice Pipeline (Acoustic Front-End, Barge-In, Biometrics).

### R3. Test-Time Compute Sandbox & Autonomous Self-Healing Loop
Vận hành vòng lặp tự động sửa lỗi và vá lỗi liên tục:
- Chạy toàn bộ 153 test suites hiện có qua `pytest tests/unit/`.
- Khi phát hiện test fail hoặc lỗi tiềm ẩn, tự động kích hoạt Deliberative CoT / 3-Expert Council để mổ xẻ nguyên nhân gốc rễ (Root Cause), sinh mã vá lỗi tối thiểu theo Seam-First TDD, và chạy kiểm thử lại trong sandbox cô lập cho đến khi đạt 100% test pass.

### R4. Automated Release Packaging & Truthful Documentation
- Xây dựng script đóng gói thương mại độc lập (Windows Standalone Installer / Portable Executable) có thể chạy trên máy sạch Windows 10/11 mà không cần môi trường Python sẵn có.
- Tự động đồng bộ hóa `CHANGELOG.md`, `README.md` và `docs/ROADMAP.md` với số liệu kiểm thử thực tế từ lần chạy hiện tại, tuân thủ Three-Tier Verdict Discipline.

### R5. Scheduled Automation Sidecar Integration
Tạo cấu hình Sidecar Automation (`sidecar.json`) chạy nền định kỳ mỗi ngày lúc 09:00 sáng (giờ Việt Nam, `Asia/Ho_Chi_Minh`) để hệ thống tiếp tục tự động quét radar, kiểm tra và nâng cấp mà không cần người dùng phải giám sát thủ công.

## Acceptance Criteria

### Test & Code Quality
- [ ] 100% unit tests và regression tests pass (0 failures, 0 errors).
- [ ] Mọi thay đổi code đều có type hints đầy đủ, docstrings giải thích lý do kỹ thuật, và xử lý exception tường minh.
- [ ] Không chứa bất kỳ placeholder nào (`pass`, `TODO`, `...`, `// rest of code`).
- [ ] Không có cảnh báo bảo mật nghiêm trọng nào từ bộ quét `security_scanner`.

### Continuous Research & Knowledge Ingestion
- [ ] Tích lũy tri thức và trích dẫn bài báo khoa học/mã nguồn vào SQLite Memory Vault.
- [ ] Áp dụng ít nhất 1 cải tiến cụ thể từ các nghiên cứu SOTA vào mã nguồn JARVIS.

### Commercial Release & Truthful Gates
- [ ] Bộ cài đặt thương mại độc lập được đóng gói thành công.
- [ ] Cập nhật tài liệu minh bạch, phản ánh trung thực số test thực tế và tầng verdict tương ứng (không tự phong cấp GO khi chưa có runtime evidence).
- [ ] Sidecar automation cấu hình hoàn tất và sẵn sàng kích hoạt trong Dashboard.


## Follow-up — 2026-10-18T16:41:17Z

# Teamwork Project Prompt — Final Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Full Swarm Team (Argon Sovereign Core + Academic Tech Radar Researcher + Security & Systems Auditor + Deep Coder + Seam Tester)

Xây dựng hệ thống tự hành liên tục (Continuous Autonomous Self-Upgrading & Research Engine) cho JARVIS: tự động nghiên cứu các công trình học thuật mới nhất (ArXiv, IEEE, PNAS, ITU-T), mã nguồn mở đỉnh cao (GitHub Trending), và tin tức công nghệ mạng xã hội; đối soát mã nguồn với các tiêu chuẩn công nghiệp; thực thi kiểm thử hồi quy (Seam-First TDD); tự động phát hiện và vá lỗi bằng cơ chế Sandbox Test-Time Compute (TTC); kết hợp lịch trình tự động chạy ngầm hàng ngày (Scheduled Automation Sidecar) để đưa dự án JARVIS đạt trạng thái phần mềm thương mại hoàn chỉnh (Commercial Product Release GO).

Working directory: d:\Software GitCode\JARVIS
Integrity mode: development

## Requirements

### R1. Comprehensive Academic & Industry Tech Radar
Tự động quét, phân tích và trích xuất các kỹ thuật, thuật toán và kiến trúc tiên tiến nhất từ:
- Tài liệu học thuật bình duyệt & preprints: ArXiv CS/AI, IEEE, ACM, PNAS, ITU-T (Voice Biometrics, Streaming STT, On-device Fast Semantic Routing, Low-latency Acoustic Processing).
- Hệ sinh thái mã nguồn mở: GitHub Trending, các dự án AI Desktop Assistant hàng đầu thế giới.
- Mạng xã hội kỹ thuật và blog công nghệ chuyên sâu.
Toàn bộ tri thức thu thập được chuẩn hóa và nạp vào SQLite Continuous Learning Vault / Memory Graph của Argon (`knowledge_nodes`, `knowledge_edges`, `tech_radar_blips`) để phục vụ nâng cấp mã nguồn.

### R2. Codebase Deep Audit & Commercial Feature Upgrades
Đối chiếu toàn bộ codebase JARVIS (`d:\Software GitCode\JARVIS`) với các tri thức mới từ Tech Radar và các tiêu chuẩn khắt khe:
- Windows Atomic Persistence (tuân thủ nghiêm ngặt 4 bước AGENTS.md Section 3: khóa threading, snapshot in-memory, file tạm `.tmp.<thread_id>.<timestamp_ns>` với retry loop 5 lần xử lý WinError 5).
- Fail-Closed Architecture (trả mã lỗi cụ thể khi thiếu binary, device hoặc credential, tuyệt đối không ghost success).
- Nâng cấp độ trễ phản hồi E2E < 500ms cho 10 workflows cốt lõi, hoàn thiện Voice Pipeline (Acoustic Front-End, Barge-In, Biometrics).

### R3. Test-Time Compute Sandbox & Autonomous Self-Healing Loop
Vận hành vòng lặp tự động sửa lỗi và vá lỗi liên tục:
- Chạy toàn bộ 156 test suites hiện có qua `pytest tests/unit/`.
- Khi phát hiện test fail hoặc lỗi tiềm ẩn, tự động kích hoạt Deliberative CoT / 3-Expert Council để mổ xẻ nguyên nhân gốc rễ (Root Cause), sinh mã vá lỗi tối thiểu theo Seam-First TDD, và chạy kiểm thử lại trong sandbox cô lập cho đến khi đạt 100% test pass (3,072 unit tests).

### R4. Automated Release Packaging & Truthful Documentation
- Sửa lỗi entrypoint `main_tray` trong `jarvis/__main__.py` và cờ `--tray` trong `jarvis/cli.py`.
- Xây dựng script đóng gói thương mại độc lập (Windows Standalone Installer / Portable Executable) có thể chạy trên máy sạch Windows 10/11 mà không cần môi trường Python sẵn có.
- Tự động đồng bộ hóa `CHANGELOG.md`, `README.md` và `docs/ROADMAP.md` với số liệu kiểm thử thực tế từ lần chạy hiện tại, tuân thủ Three-Tier / Five-Tier Verdict Discipline.

### R5. Scheduled Automation Sidecar Integration
Tạo cấu hình Sidecar Automation (`sidecar.json`) chạy nền định kỳ mỗi ngày lúc 09:00 sáng (giờ Việt Nam, `Asia/Ho_Chi_Minh`) để hệ thống tiếp tục tự động quét radar, kiểm tra và nâng cấp mà không cần người dùng phải giám sát thủ công.

---

## Acceptance Criteria

### Test & Code Quality
- [ ] 100% unit tests và regression tests pass (156 test files, 3,072 tests, 0 failures, 0 errors).
- [ ] Mọi thay đổi code đều có type hints đầy đủ, docstrings giải thích lý do kỹ thuật, và xử lý exception tường minh.
- [ ] Không chứa bất kỳ placeholder nào (`pass`, `TODO`, `...`, `// rest of code`).
- [ ] Không có cảnh báo bảo mật nghiêm trọng nào từ bộ quét `security_scanner`.

### Continuous Research & Knowledge Ingestion
- [ ] Tích lũy tri thức và trích dẫn bài báo khoa học/mã nguồn vào SQLite Memory Vault (`knowledge_nodes`, `knowledge_edges`, `tech_radar_blips`).
- [ ] Áp dụng ít nhất 1 cải tiến cụ thể từ các nghiên cứu SOTA vào mã nguồn JARVIS (Real-Time Voice Barge-In & Sub-2ms Hybrid Router).

### Commercial Release & Truthful Gates
- [ ] Bộ cài đặt thương mại độc lập được đóng gói thành công (`scripts/build_standalone_package.py`).
- [ ] Cập nhật tài liệu minh bạch, phản ánh trung thực số test thực tế và tầng verdict tương ứng (không tự phong cấp GO khi chưa có runtime evidence).
- [ ] Sidecar automation cấu hình hoàn tất (`sidecar.json`) và sẵn sàng kích hoạt trong Dashboard.
