# JARVIS Workspace Agent Rules & Engineering Standards

Tài liệu này định nghĩa các quy tắc bắt buộc mà mọi AI Agent hoạt động trong repository JARVIS phải tuân thủ nghiêm ngặt.

---

## 1. Quy Tắc Đồng Bộ Tài Liệu & Git Phát Hành (CHANGELOG & README Invariant)

Mỗi khi hoàn thành một tính năng mới, một pha phát triển (Phase), hoặc một bản sửa lỗi trọng yếu:
1. **Cập nhật `CHANGELOG.md`**:
   - Ghi lại đầy đủ: Mục tiêu, Nguyên nhân gốc rễ (Root Cause), Các chỉnh sửa kỹ thuật chi tiết theo từng file, và Chỉ số kiểm thử thực tế (số lượng test pass, thời gian chạy).
2. **Cập nhật `README.md`**:
   - Cập nhật dòng mô tả phiên bản (`jarvis.__version__`) và nội dung tương ứng trong các mục tính năng để phản ánh trung thực năng lực của hệ thống tại commit hiện tại.
3. **Cập nhật `docs/ROADMAP.md`**:
   - Đánh dấu trạng thái hoàn thành cho các mục công việc liên quan.
4. **Kiểm tra và đẩy lên Git**:
   - Kiểm tra bằng `git status` để đảm bảo các file tài liệu (`CHANGELOG.md`, `README.md`, `ROADMAP.md`) được `git add` và commit cùng với mã nguồn.
   - Đẩy trực tiếp lên nhánh `main` (`git push origin main`) sau khi toàn bộ test suite vượt qua 100%.

> [!IMPORTANT]
> Tuyệt đối không chỉ thông báo qua chat mà quên commit các thay đổi tài liệu vào Git. Người dùng luôn cần thấy bản ghi thay đổi hiển thị trực tiếp trên kho mã nguồn.

---

## 2. Nguyên Tắc Fail-Closed & Chống Giả Mạo Dữ Liệu (Anti-Fabrication Principle)

Tuân thủ nghiêm ngặt chuẩn mực tại `docs/AUDIT_FRAMEWORK.md`:
1. **Fail-Closed Mặc Định**:
   - Nếu một dịch vụ thiếu cấu hình (API key, bot token), thiếu binary (Nmap, TShark), hoặc gặp ngoại lệ mạng/thời gian chờ: hàm **PHẢI** trả về trạng thái thất bại thực chất (`False`, `None`, hoặc error code cụ thể như `NOT_CONFIGURED`, `LIMITED`, `OFFLINE`).
   - Tuyệt đối không trả `{"ok": True}` hoặc `{"success": True}` ngầm định (Silent Fallback) khi hành động chưa thực sự diễn ra thành công.
2. **Không Bịa Số Liệu**:
   - Tuyệt đối không sinh dữ liệu giả lập có công thức cố định (ví dụ: tỷ lệ gói tin 70/20/10) để hiển thị như bằng chứng thực nghiệm. Nếu không có dữ liệu thực, trả về tập rỗng và ghi rõ trạng thái.
3. **Giao Diện Trung Thực**:
   - Các adapter UI (như Terminal Control Center) phải báo cáo `StatusLevel.LIMITED` thay vì giả mạo thành công khi phần cứng chưa được nối dây thực tế.

---

## 3. Chuẩn Ghi Đĩa Nguyên Tử & An Toàn Đa Luồng Trên Windows (Windows Atomic Persistence)

Đối với các module lưu trữ (như VectorStore, ConfigStore, Cache) có hỗ trợ lưu trữ file (`persist_path`):
1. **Tuần tự hóa ghi đĩa**: Sử dụng `_save_lock = threading.Lock()` để đảm bảo tại một thời điểm chỉ có 1 luồng thực hiện ghi và hoán đổi file.
2. **Snapshot nhanh**: Bên trong `_save_lock`, chụp nhanh snapshot dữ liệu bên trong `with self._lock:` rồi nhả lock ngay lập tức để không làm nghẽn các luồng đọc/tra cứu.
3. **Ghi nguyên tử (Atomic Replace)**:
   - Ghi dữ liệu ra file tạm với tên duy nhất: `.tmp.<thread_id>.<timestamp_ns>`.
   - Sử dụng `tmp_path.replace(path)` (tương đương `os.replace` / Windows `MoveFileExW`) để thay thế file đích.
4. **Xử lý khóa file tạm thời trên Windows (`WinError 5: Access is denied`)**:
   - Bọc lệnh `replace` trong vòng lặp thử lại (retry loop 5 lần với backoff `time.sleep(0.02 * attempt)`) để vượt qua các khoảng thời gian Windows OS / Antivirus giữ file handle.
   - Luôn dọn dẹp file tạm trong khối `finally:` nếu thao tác thất bại.

---

## 4. Quy Trình TDD & Kiểm Thử Theo Seam (Seam-First TDD)

1. **Xác định Seam trước khi viết mã**: Thống nhất giao diện công khai (public API) cần kiểm thử.
2. **Chu trình Red-Green-Refactor**:
   - Viết bài test thất bại trước để chứng minh lỗi hoặc yêu cầu tính năng mới.
   - Viết code tối thiểu để test chuyển sang màu xanh (Green).
   - Tối ưu hóa và bảo vệ tính tương thích ngược.
3. **Xác minh không hồi quy**: Luôn chạy kiểm thử hồi quy trên các module liên quan và full test suite trước khi commit.
