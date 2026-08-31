# 📝 JARVIS - Nhật Ký Cập Nhật & Bản Ghi Phát Triển (Changelog)

---

## 🚀 Chưa phát hành (2026-08-31) — Biometrics Hardening: Embedding Validation, Storage Atomicity & Face-Count Ambiguity

> Nhánh làm việc: `feat/biometrics-hardening`, dựa trên `main` tại commit `e4bcd6d` (không có phân kỳ với `main` khi bắt đầu). Chỉ sửa `jarvis/vision/biometrics.py` (sản xuất) và thêm một file test mới `tests/test_biometrics_hardening.py`. Không đụng `jarvis/llm/router.py`, `jarvis/core/app.py`, `jarvis/agent/**`, `jarvis/sandbox/**`, `jarvis/comms/**`, `jarvis/security/**`, `jarvis/skills/**`, hay bất kỳ hành vi `SafetyGate`/`ActionDispatcher`/workstation-lock/Telegram nào.

**Tham chiếu kiến trúc**: `ageitgey/face_recognition` (MIT, upstream) được dùng **chỉ để tham chiếu API/kiến trúc** — `face_locations()`/`face_encodings()`/`face_distance()`/`compare_faces()`, embedding 128 chiều, khoảng cách Euclid, ngữ nghĩa `tolerance` (mặc định upstream 0.6 — chỉ là mặc định thư viện, không phải bảo đảm an ninh). **Không sao chép mã nguồn upstream**, không vendor repo, không thêm `dlib`/`face_recognition` thành dependency bắt buộc, không tải model/dữ liệu khuôn mặt thật.

### Rà soát trước khi sửa (audit)

Đọc trực tiếp `jarvis/vision/biometrics.py`, `jarvis/vision/__init__.py`, mọi test đang import `BiometricsEngine`/`FaceEmbeddingStorage`/`BiometricPrivilegeGate` (`tests/test_biometrics.py`, `tests/test_adversarial_m5_2.py`, `tests/test_tier5_adversarial_sec_iot_comms_data.py`, `tests/test_e2e_scenarios.py`), và `jarvis/core/paths.py` (chỉ đọc, không sửa). Xác nhận các lỗ hổng thực tế sau bằng cách đọc mã, không suy đoán:

- `enroll_face()`/`verify_frame()`/`process_surveillance_frame()` đều lấy `encodings[0]` vô điều kiện — không kiểm tra số khuôn mặt phát hiện được, nên một khung hình có nhiều khuôn mặt (ví dụ chủ nhà đứng cạnh người lạ) có thể bị phân loại sai một cách không tất định.
- Không có bất kỳ kiểm tra kích thước/kiểu số/giá trị hữu hạn nào cho embedding — một embedding sai chiều, chứa NaN/Infinity, hoặc không phải số có thể khiến `np.linalg.norm(enrolled - cand)` ném lỗi không bắt được hoặc (nếu shape tình cờ broadcast được) tính ra khoảng cách vô nghĩa được tin tưởng ngầm.
- `FaceEmbeddingStorage.save()` ghi trực tiếp không nguyên tử — tiến trình bị ngắt giữa chừng có thể để lại file JSON hỏng/cắt cụt.
- `FaceEmbeddingStorage.add_face()`/`BiometricsEngine.enroll_face()` không bao giờ báo lỗi ghi đĩa cho caller — một lần ghi thất bại vẫn để bộ nhớ trong-tiến-trình coi như đã enroll thành công.
- Enroll lại cùng một label tạo **embedding trùng lặp cũ** trong danh sách khớp trong bộ nhớ (`enrolled_embeddings` cũ là list phẳng, không theo label) dù storage trên đĩa đã ghi đè đúng — cả embedding cũ và mới đều còn khớp được sau khi re-enroll.
- Không có validate label (kiểu, rỗng, ký tự điều khiển, độ dài) hay validate `tolerance` (âm, NaN, Infinity, chuỗi, giá trị phi lý lớn có thể vô tình mở rộng ngưỡng xác thực).
- Nhánh trích xuất từ camera mock (`self.camera.get_face_encodings()`) không được bọc try/except — khác với nhánh `face_recognition`, nên một backend/mock bị lỗi có thể làm crash toàn bộ pipeline gọi nó.
- Test hiện có (`test_adversarial_biometrics_boundary_distances`) xác nhận ranh giới tolerance là **strict `<`** (khoảng cách == tolerance ⇒ không khớp) — đây là hợp đồng bắt buộc phải giữ nguyên chính xác.

### Thay đổi đã triển khai (`jarvis/vision/biometrics.py`)

- **Một ranh giới validate embedding duy nhất** (`_validate_embedding()`, hàm private cấp module): chấp nhận bất kỳ dữ liệu array-like nào, trả về bản sao `float64` shape `(128,)` mới (không bao giờ alias/mutate mảng của caller) khi hợp lệ, hoặc `None` khi không — không bao giờ ném exception. Kiểm tra: đúng 128 chiều, kiểu số, mọi giá trị hữu hạn (không NaN/±Infinity), có kiểm tra độ dài rẻ trước khi ép kiểu để tránh cấp phát mảng khổng lồ từ dữ liệu JSON độc hại. Được tái sử dụng ở **mọi** điểm nhận embedding: candidate lúc verify/enroll/surveillance, embedding tải từ storage, `camera.owner_encoding`.
- **`_validate_label()`**: string không rỗng sau `strip()`, giới hạn 128 ký tự, cấm ký tự điều khiển; label chỉ dùng làm key dict/JSON, không bao giờ dùng làm đường dẫn file.
- **`_validate_tolerance()`**: từ chối NaN/Infinity/âm/không phải số/bool/giá trị vượt ngưỡng hợp lý (`MAX_SANE_TOLERANCE = 10.0`, một giới hạn "sanity" cho tham số cấu hình — không phải tuyên bố về khoảng cách embedding thực tế), fallback về `DEFAULT_TOLERANCE = 0.60` kèm log lỗi thay vì âm thầm cho phép ngưỡng bị nới rộng.
- **`FaceEmbeddingStorage` cứng hóa**: `_load()` — lỗi parse JSON toàn file vẫn rỗng hoàn toàn (giữ đúng hành vi test cũ), root không phải dict cũng rỗng hoàn toàn, nhưng **entry lỗi riêng lẻ trong một JSON hợp lệ giờ bị bỏ qua có chọn lọc** (label/embedding hỏng bị loại, các entry hợp lệ khác được giữ). `save()` giờ ghi nguyên tử (temp file + `os.replace()`) và trả `bool` — nếu ghi thất bại, file gốc trên đĩa không bị đụng tới và trả `False`. `add_face()` cũng trả `bool`, validate label/embedding, và **rollback bộ nhớ trong-tiến-trình về trạng thái trước đó nếu `save()` thất bại** — không bao giờ để bộ nhớ coi một enrollment là thành công khi chưa thực sự ghi được xuống đĩa.
- **`BiometricsEngine` chuyển sang lưu embedding có label theo dict** (`_labeled_embeddings: dict[str, np.ndarray]`, tách khỏi `_unlabeled_embeddings` cho `camera.owner_encoding`) thay vì list phẳng — enroll lại cùng label giờ **thay thế tất định**, không còn để lại embedding cũ trùng lặp trong bộ nhớ. Thuộc tính `enrolled_embeddings` (list phẳng) được giữ lại dạng `@property` tính từ hai cấu trúc trên, cho tương thích ngược (không có code/test nào bên ngoài đọc trực tiếp thuộc tính này ngoài chính file này, đã xác nhận bằng grep).
- **`enroll_face()`**: từ chối tất định khi 0 khuôn mặt hoặc >1 khuôn mặt phát hiện được (yêu cầu đúng chính xác 1), validate label và embedding, chỉ cập nhật bộ nhớ trong-tiến-trình **sau khi** `storage.add_face()` xác nhận đã ghi thành công.
- **`verify_frame()`**: giữ nguyên chính xác `bypass_mode` và kiểm tra khung tối/rỗng/None hiện có; giờ từ chối tất định (fail-closed) khi 0 hoặc >1 khuôn mặt, khi candidate embedding không hợp lệ, hoặc khi không có embedding nào đã enroll. Ranh giới tolerance strict `<` được giữ nguyên bit-for-bit.
- **`process_surveillance_frame()`**: khung hình mơ hồ (nhiều khuôn mặt) hoặc có embedding không hợp lệ giờ trả về trạng thái riêng biệt (`"ambiguous_faces"` / `"invalid_face_data"`, `locked: False`) — **không bao giờ** bị phân loại nhầm thành `"owner_verified"`. Quyết định có chủ đích: các trạng thái mơ hồ này **không** kích hoạt khóa máy/cảnh báo Telegram (khác với `"intruder_locked"` cho trường hợp không khớp rõ ràng), để tránh mở rộng phạm vi sang thiết kế chính sách giám sát mới ngoài yêu cầu, và tránh cảnh báo giả khi dữ liệu khung hình thực sự không rõ ràng.
- **`_extract_encodings()`**: nhánh camera mock giờ được bọc try/except giống nhánh `face_recognition` — một backend/mock ném lỗi không còn làm crash caller.
- Không sửa `BiometricPrivilegeGate` (rà soát không phát hiện lỗi ở đây ngoài những gì kế thừa từ `verify_frame()` đã cứng hóa — hướng thay đổi chỉ làm xác thực khó hơn, không bao giờ dễ hơn).
- `jarvis/vision/__init__.py` **không đổi** — cả 3 tên export (`BiometricsEngine`, `BiometricPrivilegeGate`, `FaceEmbeddingStorage`) giữ nguyên chữ ký công khai (`verify_frame()`/`enroll_face()` vẫn trả `bool`, `process_surveillance_frame()` vẫn trả `dict` có khóa `"status"`).

### Test hồi quy (`tests/test_biometrics_hardening.py`, file mới, 49 test)

Bao phủ: validate embedding (128D hợp lệ/127D/129D/rỗng/NaN/Infinity/phi số/nested lỗi/không mutate mảng caller), storage corruption (JSON hỏng toàn file → rỗng, root sai kiểu, entry lẫn lộn hợp lệ+hỏng chỉ giữ entry hợp lệ, ghi nguyên tử bảo toàn file cũ khi ghi thất bại, sống sót qua khởi động lại registry, không ghi file vào cây repo mặc định), validate label (rỗng/sai kiểu/ký tự điều khiển/quá dài/duplicate thay thế tất định), số lượng khuôn mặt khi enroll (0/nhiều/đúng 1/rollback khi persist thất bại/không còn duplicate khi re-enroll), số lượng khuôn mặt khi verify (0/nhiều/candidate hỏng/không có embedding nào đã enroll/embedding lưu trữ hỏng không xác thực được), ngữ nghĩa khớp & tolerance (gần khớp, xa không khớp, ranh giới strict `<`, tolerance không hợp lệ không thể nới rộng xác thực — tham số hóa NaN/Infinity/âm/chuỗi/1e9/bool), optional dependency (vắng `face_recognition`/`cv2` không crash, camera mock vẫn hoạt động, backend ném lỗi không crash), privilege session (chỉ bắt đầu sau xác thực hợp lệ, hết hạn đúng TTL), surveillance (khung nhiều khuôn mặt không bao giờ là `"owner_verified"`), và tương thích API công khai.

**Kết quả xác nhận thực tế (chạy cục bộ, Windows)**:
```text
python -m pytest tests/test_biometrics_hardening.py -v --timeout=60 --tb=short
49 passed in 0.54s
```
Toàn bộ file test cũ liên quan biometrics (`tests/test_biometrics.py`, `tests/test_adversarial_m5_2.py`, `tests/test_tier5_adversarial_sec_iot_comms_data.py`, `tests/test_e2e_scenarios.py`) được chạy lại và **so sánh bit-for-bit với baseline** (`git stash` rồi chạy lại) — xác nhận các lỗi/error hiện có (6 `ModuleNotFoundError: cv2` trong `test_biometrics.py`, 3 tương tự trong `test_e2e_scenarios.py`, 2 lỗi CLI nmap/tshark + 1 `AttributeError` Discord trong `test_tier5_...`) đã tồn tại **y hệt trước khi sửa** — môi trường này không có `cv2`/`face_recognition` cài đặt thật, đây là khoảng trống môi trường có sẵn, không phải hồi quy.

`tests/unit/` đầy đủ:
```text
python -m pytest tests/unit/ -q --timeout=60 --tb=short
```
Kết quả: đúng 9 lỗi đã biết trước đó (8 `tests/unit/test_mobile_bridge.py`, 1 `tests/unit/test_proactive_engine.py::test_health_monitor_multiple_simultaneous_breaches`) — **0 lỗi mới**. Không có test nào trong `tests/unit/` đụng tới `jarvis/vision/biometrics.py`.

Static analysis:
```text
ruff check jarvis/vision/biometrics.py tests/test_biometrics_hardening.py
All checks passed!

mypy jarvis
```
`jarvis/vision/biometrics.py` không có lỗi mypy nào. `ruff check jarvis tests scripts/build_installer.py` và `mypy jarvis` trên toàn repo báo lỗi **giống hệt baseline** (xác nhận bằng `git stash`): 9 lỗi Ruff (import-sort trong `tests/unit/test_zalo_bot.py` + các file khác đã biết từ trước) và 28 lỗi mypy trong 8 file không liên quan (`night_shift.py`, `macro_recorder`, `auto_updater.py`, `smart_home/discovery.py`, `mobile_bridge.py`, `tray.py`, `gui_actor.py`, `cli.py`) — không file nào trong số này thuộc phạm vi sửa đổi của nhánh này.

`py_compile jarvis/vision/biometrics.py tests/test_biometrics_hardening.py`: exit 0. `git diff --check`: exit 0.

### Giới hạn đã biết / không tuyên bố

- **Không** tuyên bố nhận diện khuôn mặt an toàn trước giả mạo (spoofing), **không** có liveness detection hay anti-spoofing, ngưỡng tolerance 0.6 (mặc định upstream) **không** phải bảo đảm định danh, hỗ trợ `face_recognition` trên Windows **không** được xác nhận chính thức trong sprint này, và JARVIS **chưa** có xác thực sinh trắc học cấp sản xuất.
- `jarvis/skills/*/metadata.json` (9 file) bị đổi do chạy `tests/unit/`/test suite trong phiên này (telemetry số lần gọi/timestamp của skill registry) — lệnh khôi phục (`git checkout --`) bị chặn bởi bộ phân loại an toàn của công cụ (thao tác hủy thay đổi working tree); người dùng cần tự khôi phục nếu muốn, không thuộc bộ thay đổi này.
- CI chưa được chạy cho nhánh này; chưa commit/push/PR.
- Không sửa `jarvis/core/paths.py` — logic resolve `%LOCALAPPDATA%/JARVIS/cache/biometrics/faces.json` trong `FaceEmbeddingStorage.__init__` vẫn giữ nguyên cách tự resolve riêng (không dùng `data_path()`), vì việc hợp nhất quy ước path nằm ngoài phạm vi sprint cứng hóa embedding/storage/enrollment này.

---

## 🚀 Chưa phát hành (2026-08-30) — Central Safety-Layer Hardening (Phase 2)

> Nhánh làm việc: `feat/safety-layer-hardening`, dựa trên `main` sau khi cả PR #8 (Wake Word Phase 1) và PR #9 (Sandbox CI Compatibility Fix) đã được merge (`35713b9`). Nhánh này **độc lập** với hai PR trên — không đụng `jarvis/sandbox/*` hay `jarvis/audio/wake_word.py`.

Rà soát kiến trúc an toàn hiện có (không phải audit lại từ đầu) xác nhận: JARVIS đã có 4 cơ chế xác nhận/rủi ro **độc lập, không liên kết** — `SafetyGate` (nguyên thủy token 2 pha), `SafetyGateInterceptor` (bộ phân loại rủi ro dùng cho planner, chỉ kích hoạt khi `PlanMode.SAFETY_GATE`), `ShellAssistant.is_destructive()` (bộ phân loại riêng, trùng lặp logic), và `IntentResult.requires_confirmation` (cờ do LLM router tính cho shutdown/reboot/sleep). Điểm hội tụ thực sự — `ActionDispatcher.dispatch_action()`/`dispatch_action_async()`, nơi hầu hết lệnh thoại/text/Telegram/GUIActor thực sự được thực thi — **không có bất kỳ nhận biết rủi ro nào**, chỉ kiểm tra RBAC. Nghiêm trọng nhất: `IntentResult.requires_confirmation`/`confirmation_prompt` mà router tính cho lệnh tắt máy/khởi động lại/ngủ **không được bất kỳ nơi nào trong `jarvis/` đọc lại** — xác nhận bằng grep toàn bộ cây mã nguồn.

### Thiết kế cuối cùng

- **Bộ phân loại dùng chung, tất định** (`SafetyGateInterceptor.is_high_risk(action_name, parameters, explicit_flag=...)`): tổng quát hóa từ `is_high_risk_node()` cũ (vẫn giữ nguyên hành vi làm wrapper mỏng), bổ sung nhận diện tất định cho `system_power`/`power_action` với sub-action `shutdown`/`restart`/`reboot`/`sleep`/`poweroff`/`hibernate` (không bao gồm `lock`) — **không phụ thuộc** vào cờ `IntentResult.requires_confirmation` của LLM router cho quyết định an toàn.
- **Lớp ràng buộc token mới** (`SafetyGateInterceptor.gate()`/`.verify()`, hoàn toàn nội bộ, không sửa `SafetyGate`): một token xác nhận giờ bị khóa chặt vào đúng cặp `(action_name, parameters)` đã được duyệt tại thời điểm cấp — sai action hoặc payload đã sửa đổi đều bị từ chối — và **dùng một lần**: sau khi `verify()` thành công một lần, token đó không bao giờ dùng lại được (chặn replay), kể cả khi vẫn còn hạn và vẫn ở trạng thái CONFIRMED trên `SafetyGate`.
- **`ActionDispatcher` là điểm thực thi an toàn trung tâm** cho cả `dispatch_action()` (đồng bộ) lẫn `dispatch_action_async()` (bất đồng bộ), qua một helper `_evaluate_safety_gate()` dùng chung: chạy sau bước kiểm tra RBAC, trước khi handler thực thi. Hành động benign hoàn toàn không đổi. `ActionDispatcher.bypass_security=True` **không** ảnh hưởng đến lớp an toàn mới này — cờ đó vẫn chỉ chi phối RBAC như trước.
- **Planner (`ReActTaskEngine.execute_plan()`)**: điều kiện chặn node rủi ro cao giờ áp dụng **bất kể `PlanMode`** (trước đây chỉ áp dụng khi gọi tường minh `PlanMode.SAFETY_GATE` — nhưng caller sản xuất thực tế, `_handle_planner_execute_task`, luôn dùng `PlanMode.FULLY_AUTONOMOUS` mặc định, khiến cơ chế chặn gần như chết trong production). Nội suy tham số (`interpolate_node_params`) được dời lên chạy trước bước kiểm tra rủi ro (thay vì ngay trước khi dispatch), để token được cấp gắn đúng với tham số cuối cùng sẽ thực thi. `execute_step()` chuyển `node.confirmation_token` vào `dispatcher.dispatch_action()` để không bị chặn lần hai một cách vô ích. Vì việc chặn giờ xảy ra trước khi chọn nhánh thực thi, đường vòng qua handler tùy chỉnh (`register_action_handler()`, hiện không dùng trong production nhưng vẫn khả dụng) cũng được bảo vệ mà không cần patch riêng.
- **`GUIActor`: không sửa gì.** Hai điểm gọi duy nhất của nó, `vision_click_ui`/`vision_type_ui`, đã là action đăng ký trên `ActionDispatcher` — nên đã được chặn tự động tại đúng ranh giới ngữ nghĩa (chuỗi `query`/`text` được quét qua cùng `DANGEROUS_PATTERNS` đã có), không cần phát minh heuristic tọa độ/phím bấm mới cho GUIActor.
- **`SelfReflectionEngine`**: bổ sung nhỏ để lỗi có mã `CONFIRMATION_*` (hoặc chuỗi tiếng Việt "xác nhận") dẫn đến `ABORT` thay vì `RETRY` mù quáng — tránh việc planner spam yêu cầu xác nhận mới liên tục.
- Không sửa `SafetyGate`, hành vi `ShellAssistant.is_destructive()`, hay bất kỳ bảo đảm bảo mật nào của `jarvis/sandbox/*`/`jarvis/audio/wake_word.py`.

### Test hồi quy (`tests/unit/test_action_dispatcher_safety.py`, file mới)

- 15 test tất định: dispatch benign đồng bộ/bất đồng bộ không đổi hành vi; dispatch rủi ro đồng bộ/bất đồng bộ không thực thi trước khi xác nhận; shutdown/restart/reboot/sleep bị chặn tất định (và `lock` không bị chặn nhầm, kiểm tra độ chính xác); hành động đã xác nhận thực thi đúng một lần; replay token thất bại; hành động bị từ chối không bao giờ thực thi; token hết hạn không bao giờ thực thi; token của action A không xác nhận được action B; token của payload X không xác nhận được payload Y đã sửa; `bypass_security=True` không bỏ qua lớp an toàn mới; và 2 test tái hiện đúng kịch bản audit — node rủi ro cao qua đường `register_action_handler()` (bỏ qua `ActionDispatcher`) vẫn bị chặn dù chạy ở `PlanMode.FULLY_AUTONOMOUS` mặc định của production.
- Kết quả xác nhận thực tế (chạy cục bộ): `test_action_dispatcher_safety.py` — **15 passed**. Toàn bộ `tests/unit/` — **736 passed, 0 failed** (baseline nhánh này, sau khi PR #8 + PR #9 đã merge vào `main`, là 721 — cộng đúng 15 test mới).
- Ruff (`jarvis/planner/safety_interceptor.py`, `jarvis/core/dispatcher.py`, `jarvis/planner/engine.py`, `jarvis/planner/reflection.py`, `jarvis/core/app.py`, file test mới): sạch. `ruff check jarvis tests scripts/build_installer.py` báo 3 lỗi — cả 3 đều là lỗi **đã tồn tại từ trước** (`tests/integration/test_sandbox_os_boundaries.py`, `tests/unit/test_zalo_bot.py`), không liên quan đến thay đổi này. `mypy jarvis` — sạch, 157 file nguồn. `py_compile` các file đã sửa — exit 0. `git diff --check` — exit 0.
- **Chưa claim CI đã chạy** — CI cho nhánh này chưa được kích hoạt.

### Giới hạn đã biết / theo dõi tiếp

- Chưa xây dựng luồng UX "nói đồng ý → tự động thực thi lại" đầu-cuối tại tầng thoại/`app.py` — `_handle_safety_gate_confirm()` hiện chỉ chuyển trạng thái `SafetyGate` sang CONFIRMED, không tự re-dispatch hành động gốc; caller (kể cả voice pipeline hiện tại) phải tự gọi lại `dispatch_action(..., confirmation_token=...)`. Đây là giới hạn đã tồn tại từ trước tương tự với `ShellAssistant` (không phải hồi quy do thay đổi này), chưa được yêu cầu giải quyết trong phạm vi Phase 2 này.
- `IntentResult.requires_confirmation`/`confirmation_prompt` vẫn tồn tại nhưng vẫn không được đọc ở đâu — không còn là lỗ hổng an toàn (vì `system_power` giờ được chặn tất định độc lập với cờ này), nhưng vẫn là dữ liệu "mồ côi"; có thể tận dụng làm prompt xác nhận đẹp hơn trong một tác vụ theo sau, không bắt buộc.
- `jarvis/skills/*/metadata.json` (9 file) bị đổi do chạy `tests/unit/` trong phiên này đã được khôi phục (`git checkout --`) trước khi hoàn tất; không thuộc bộ thay đổi này.

---

## 🚀 Chưa phát hành (2026-08-30) — Wake Word Reliability Hardening (Phase 1)

> Nhánh làm việc: `feat/porcupine-wakeword-hardening`, đã được đồng bộ (fast-forward) lên baseline `main` mới nhất — v4.1.0, commit `2455fb6` — bao gồm toàn bộ phần cứng hóa an ninh/sandbox cấp OS Kernel của v4.1.0 được mô tả bên dưới. Mục Phase 1 này **không thay thế, không viết đè** mục v4.1.0; nó mô tả một nhánh tính năng riêng biệt, độc lập, **vẫn chưa commit**, nằm ngoài phạm vi an ninh/sandbox của v4.1.0.

Rà soát độc lập đối chiếu `jarvis/audio/wake_word.py` với API thực tế của Porcupine (tham khảo mã nguồn chính thức tại `.references/porcupine/binding/python/`, phiên bản `pvporcupine==4.0.3`, không sao chép vào repo) đã xác nhận lỗi đã biết: `_init_tier1()` có thể khởi tạo thành công engine Porcupine, nhưng `feed_audio_block()` chỉ có nhánh xử lý Tier 1 thực sự cho Vosk — engine Porcupine (và tương tự OpenWakeWord) được khởi tạo nhưng **không bao giờ được gọi để xử lý audio**. Nội dung dưới đây mô tả hành vi cuối cùng sau nhiều vòng rà soát/sửa lỗi trong cùng phiên làm việc, đã được xác nhận lại (re-validated) trên baseline v4.1.0 hiện tại.

### Sửa lỗi Porcupine không xử lý audio (`jarvis/audio/wake_word.py`)

- Thêm nhánh xử lý Tier 1 thực sự cho `WakeWordEngineType.PORCUPINE` trong `feed_audio_block()`, tôn trọng đúng hợp đồng runtime của Porcupine: `sample_rate`/`frame_length` lấy từ chính instance engine, PCM 16-bit int16 mono, chỉ số keyword `>= 0` là dấu hiệu khớp duy nhất.
- Lớp trợ giúp nội bộ `_PorcupineFrameBuffer` đệm PCM không phụ thuộc kích thước block đầu vào của JARVIS: gom đủ `frame_length` mẫu rồi mới gọi `porcupine.process()`, xử lý tuần tự **mọi** frame trọn vẹn trong một block kể cả khi một frame ở giữa đã phát hiện keyword, giữ lại phần mẫu dư cho lần gọi kế. Đã xác minh trực tiếp bằng test cho đúng đường dẫn sản xuất thực tế: `AudioEngine` mặc định phát khối 1764 mẫu @ 44.1kHz mỗi 40ms → resample đúng thành 640 mẫu @ 16kHz mỗi lần → không có frame dị dạng nào từng được gửi tới `process()`.
- **Cooldown chỉ chặn phát sự kiện, không chặn luồng audio vào Porcupine**: Porcupine là engine streaming — nó phải tiếp tục nhận mọi frame trọn vẹn ngay cả khi đang trong cooldown 1.5s sau một lần phát hiện, nếu không trạng thái nội bộ của engine/frame buffer sẽ lệch khỏi audio thực tế. Hành vi cooldown của Vosk và Tier 2 (bỏ qua xử lý hoàn toàn trong lúc cooldown) được giữ nguyên như trước.
- **Dọn dẹp khởi tạo dở dang**: nếu `pvporcupine.create()` thành công nhưng bước sau đó lỗi (đọc `frame_length`/`sample_rate`, dựng adapter thất bại), engine native vừa tạo được giải phóng ngay tại chỗ thay vì bị rò rỉ.
- **Suy giảm vĩnh viễn khi có lỗi runtime**: một ngoại lệ từ `porcupine.process()` giải phóng engine native đúng một lần, xóa buffer PCM đang chờ, và chuyển hẳn sang `ACOUSTIC_FALLBACK` cho toàn bộ vòng đời còn lại của detector — không gọi lại engine đã lỗi ở các block sau. Tier 2 tiếp tục hoạt động bình thường sau khi suy giảm.
- Bổ sung `WakeWordDetector.shutdown()` giải phóng `porcupine.delete()` đúng một lần, idempotent, dùng chung `RLock` với `feed_audio_block()` nên `delete()` không bao giờ chạy đồng thời với `process()` đang dở dang. `jarvis/core/app.py` gọi phương thức này trong `stop()`, sau khi `AudioEngine.stop_stream()` đã dừng/join luồng audio.
- `WakeWordDetector.reset()` cũng xóa buffer frame nội bộ của Porcupine.
- **Buffer streaming do JARVIS sở hữu được xóa khi bật/tắt** (phạm vi được nêu chính xác, không phóng đại): `set_enabled()` và `toggle_enabled()` dùng chung logic chuyển trạng thái — mỗi lần chuyển trạng thái bật/tắt thực sự sẽ xóa ring buffer và frame Porcupine đang chờ **do JARVIS sở hữu**, để PCM phía caller trước và sau một khoảng thời gian tắt không bị nối lẫn vào nhau. Việc này **không** reset trạng thái nội bộ của chính engine Porcupine native — không có API reset nào được dùng hay tồn tại trong hợp đồng upstream đã đối chiếu ngoài việc khởi tạo lại hoàn toàn (chủ động nằm ngoài phạm vi); lịch sử phát hiện nội bộ mà engine native tự giữ (nếu có) vẫn có thể trải dài qua khoảng thời gian tắt. Đây là giới hạn đảm bảo có chủ đích, hẹp, không phải lỗi đã biết. `_last_trigger_time` (bộ đếm cooldown) **không** bị reset theo — cooldown độc lập với việc bật/tắt, nên bật/tắt nhanh không được dùng để lách cooldown.
- Bổ sung `WakeWordDetector.toggle_enabled()` (thread-safe, trả về trạng thái `enabled` mới) để sửa lỗi không khớp API đã xác nhận: `jarvis/core/app.py` gọi `self.wake_word_detector.toggle_enabled()` từ callback phím tắt toàn cục nhưng phương thức này trước đó **không tồn tại**, nên đường dẫn phím tắt bật/tắt wake word sẽ ném `AttributeError` nếu được gọi.

### Sửa lỗi thứ tự chuẩn hóa PCM int16 stereo (`feed_audio_block()`)

- Phát hiện và sửa một lỗi định dạng đầu vào riêng biệt: với mảng PCM int16 stereo, `np.mean(..., axis=1)` (gộp kênh) chạy **trước** bước kiểm tra `np.issubdtype(arr.dtype, np.integer)` sẽ tự động thăng cấp dữ liệu lên `float64`, khiến bước kiểm tra kiểu nguyên bị bỏ qua và toàn bộ bước chuẩn hóa `/32768.0` không chạy — PCM int16 stereo bị diễn giải ở thang biên độ nguyên thô (~[-32768, 32767]) thay vì `[-1.0, 1.0]` đã chuẩn hóa. Đã sửa bằng cách chuẩn hóa PCM nguyên **trước** khi gộp kênh; hành vi mono int16, mono/stereo float32 giữ nguyên. Không sửa `AudioEngine`.
- Bổ sung 2 test hồi quy xác định (deterministic) với giá trị mẫu tường minh có thể tính tay chính xác: `test_wake_word_int16_mono_normalization_exact`, `test_wake_word_int16_stereo_normalization_exact`.

### Kiểm tra OpenWakeWord (không sửa trong giai đoạn này)

- Xác nhận cùng một dạng lỗi tồn tại với `WakeWordEngineType.OPENWAKEWORD`. **Chưa sửa trong Phase 1**: API khác biệt đáng kể so với Porcupine (buffer nội bộ có trạng thái riêng, `predict()` trả dict điểm số thay vì chỉ số keyword đơn, hành vi tải model mặc định cần xác minh kỹ), không có bản tham khảo mã nguồn nào được staged cho OpenWakeWord. Không tải model, không thêm dependency mới. Ghi nhận trong `docs/PROJECT_STATE.md`.

### Phụ thuộc tùy chọn

- Nhóm optional dependency `wakeword` (`pvporcupine>=4.0.3,<5`) trong `pyproject.toml`, khớp đúng major version 4 đã đối chiếu tại `.references/porcupine/binding/python/setup.py`. `pvporcupine` **không** phải dependency bắt buộc — về mặt thiết kế, JARVIS khởi động và CI không yêu cầu cài đặt gói này, cũng không cần Picovoice access key thật trong CI/test. Lưu ý: đây là mô tả thiết kế/yêu cầu, **không phải** xác nhận CI đã chạy — CI cho Phase 1 **chưa được chạy**; toàn bộ kết quả kiểm thử trong tài liệu này đều là kết quả chạy cục bộ (local).

### Test hồi quy & tính xác định (determinism)

- Toàn bộ test Porcupine mới đều mock `PORCUPINE_AVAILABLE`/`pvporcupine`/`VOSK_AVAILABLE`/`OPENWAKEWORD_AVAILABLE`, dùng PCM xác định (zeros/constants) thay vì audio tổng hợp ngẫu nhiên khi kết quả do mock quyết định; test đồng bộ hóa luồng dùng `threading.Event()` tường minh thay vì `time.sleep()` để đoán thời điểm. Các test trạng thái chung (`toggle_enabled`, cooldown-timer-not-reset, shutdown no-op) cũng ép buộc cả ba cờ backend tùy chọn về `False` để không phụ thuộc vào việc máy phát triển có cài `vosk`/`openwakeword`/`pvporcupine` hay không.
- **Kết quả xác nhận thực tế (chạy lại trên baseline v4.1.0, commit `2455fb6`)**: `tests/unit/test_wake_word.py` — **53 passed**; toàn bộ `tests/unit/` — **681 passed, 46 subtests passed, 0 failed**. Baseline `tests/unit/` tại `main`/v4.1.0 trước khi áp Phase 1 là **651 passed** (23 test wake-word gốc); Phase 1 bổ sung đúng **30 test wake-word mới** (53 − 23 = 30), không có hồi quy nào ở các test khác.
- Ruff (`jarvis/audio/wake_word.py`, `jarvis/core/app.py`, `tests/unit/test_wake_word.py`, `pyproject.toml`) và mypy (`jarvis`) đều sạch. `git diff --check` sạch. Lưu ý: `ruff check jarvis tests scripts/build_installer.py` trên toàn bộ cây hiện báo 3 lỗi lint tiền tồn tại (pre-existing) trong `tests/integration/test_sandbox_os_boundaries.py` và `tests/unit/test_zalo_bot.py` — cả hai đều thuộc công việc an ninh v4.1.0 của người đóng góp khác, **không** do Phase 1 gây ra và **không** được sửa ở đây (ngoài phạm vi).
- **Không** bao gồm kiểm thử micro thật, phát âm "Hey JARVIS" thật, hay Picovoice AccessKey thật — việc này được **chủ động hoãn lại** (intentionally deferred), không phải lỗi/thiếu sót Phase 1.
## 🚀 Chưa phát hành (2026-08-30) — Windows Sandbox CI Compatibility Fix

> Nhánh làm việc: `fix/sandbox-windows-ci-compat`, dựa trên `origin/main` v4.1.0 (commit `2455fb6`). Đây là một nhánh sửa lỗi **riêng biệt, độc lập**, không liên quan đến nhánh Wake Word Phase 1 (`feat/porcupine-wakeword-hardening`) — không đụng tới `jarvis/audio/wake_word.py`, Porcupine, hay PR #8. Mục này đã trải qua một vòng rà soát bảo mật bổ sung sau bản sửa đầu tiên (3 "blocker" bên dưới); nội dung mô tả trạng thái cuối cùng sau vòng đó.

Bisect thủ công lịch sử GitHub Actions xác nhận commit đầu tiên gây lỗi CI (first bad commit) là `adab40d` ("resolve all 4 sandbox bypasses with true OS Restricted Tokens..."), thay thế đường dẫn `subprocess.Popen` đã hoạt động tốt (commit `3039bb4`/`dfa2eaf`, GitHub Actions run #38/#39 SUCCESS) bằng `CreateRestrictedToken` + `CreateProcessAsUserW`. Từ run #40 trở đi, đúng 6 test bắt đầu fail và vẫn còn fail trên v4.1.0/PR #8. Kết quả CI quan sát được: mã thoát `3221225794` (`0xC0000142` — `STATUS_DLL_INIT_FAILED`) — tiến trình con chết trong lúc tự khởi tạo/nạp DLL trước khi bất kỳ mã người dùng nào chạy được **trong đa số trường hợp** — nhưng bản thân mã STATUS_* đó, đứng một mình, **không phải bằng chứng chắc chắn** không có mã người dùng nào đã chạy (xem "Ranh giới sẵn sàng" bên dưới).

### Nguyên nhân gốc

Hợp đồng `CreateProcessAsUser` của Microsoft cho phép lệnh gọi báo thành công **trước khi** tiến trình con hoàn tất khởi tạo của chính nó. `spawn_low_integrity_process()` trước đây coi việc launcher trả về là dấu hiệu thực thi thành công (`spawned_via_token = True`), nên khi tiến trình con chết ngay do `STATUS_DLL_INIT_FAILED`, JARVIS diễn giải nhầm đây là "backend hạn chế đã chạy và trả về mã thoát lạ" thay vì "OS isolation chưa từng được thiết lập."

### Ranh giới sẵn sàng (readiness handshake) — ranh giới an toàn-để-thử-lại THỰC SỰ

Rà soát bảo mật bổ sung chỉ ra: **chỉ riêng mã NTSTATUS không đủ để chứng minh không có mã người dùng nào đã chạy** — một tiến trình con có thể đã bắt đầu chạy preamble bảo mật hoặc thậm chí mã người dùng, rồi mới gặp lỗi native DLL sau đó. `GetExitCodeProcess()` một mình không thể phân biệt "chết trước khi chạy gì cả" với "chạy một lúc rồi crash với mã tình cờ trùng khớp." Sửa bằng một handshake sẵn sàng thực sự:

- Preamble bảo mật được inject (`SANDBOX_BOOTSTRAP_PREAMBLE`) giờ ghi một **sentinel nội bộ** ra stdout (qua writer đã bị giới hạn 1MB) ngay sau khi TẤT CẢ các guard bảo mật đã cài đặt thành công, và ngay TRƯỚC khi mã người dùng được nối vào bắt đầu chạy. Vì Python chạy với `-u` (unbuffered), việc ghi này quan sát được ngay từ phía cha mà không có nhập nhằng buffering.
- `strip_sandbox_ready_sentinel()` gỡ bỏ dòng sentinel này khỏi mọi output trước khi đưa vào `SandboxResult`/hiển thị cho người dùng/parse kết quả có cấu trúc — áp dụng cho cả đường Restricted Token lẫn đường compat Popen (cả hai chạy chung một file script đã inject preamble).
- Ngữ nghĩa chính xác: **mã STATUS_* đã biết + sentinel KHÔNG quan sát được** → xác nhận lỗi bootstrap trước-mã-người-dùng → `RestrictedProcessBootstrapError` → đủ điều kiện cho compat fallback tường minh. **Mã STATUS_* đã biết + sentinel CÓ quan sát được** → tiến trình con đã vượt ranh giới mã người dùng → coi là kết quả thực thi thật (dù bất thường) → **KHÔNG BAO GIỜ** retry qua compat, trả về mã thoát nguyên văn như mọi lần thực thi khác.

### Ngoại lệ chung/không phân loại được KHÔNG BAO GIỜ được retry

- `RestrictedProcessBootstrapError` giờ có thuộc tính `retry_safe` (mặc định `True`, chỉ đúng tại những nơi CHỨNG MINH ĐƯỢC lỗi xảy ra trước khi tiến trình con thực thi bất kỳ lệnh nào). Lỗi từ `WaitForSingleObject`/`GetExitCodeProcess` xảy ra **sau khi** tiến trình con đã được resume — không thể chứng minh là trước-mã-người-dùng — nên raise với `retry_safe=False`.
- Một exception chung/không phân loại (không phải `RestrictedProcessBootstrapError`) từ launcher — **không bao giờ** kích hoạt compat fallback, dù cờ `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1` có bật hay không. Đã cập nhật/thay thế test `test_unexpected_launcher_exception_falls_back_when_explicitly_enabled` (trước đây enforce hành vi KHÔNG an toàn) bằng test xác nhận nó không bao giờ retry.

### Job Object không được fail open + tiến trình con tạo SUSPENDED

- Trình tự khởi chạy giờ là: `CreateProcessAsUserW` với cờ `CREATE_SUSPENDED` (tiến trình con chưa thực thi lệnh nào) → gán Job Object cho tiến trình con **đang suspended** → **chỉ khi** gán thành công mới `ResumeThread`. Điều này đóng race window trước đây (tiến trình con có thể đã chạy trước khi được gán Job Object).
- Nếu gán Job Object thất bại: `TerminateProcess` tiến trình con đang suspended, **không bao giờ gọi `ResumeThread`**, raise `RestrictedProcessBootstrapError(retry_safe=True)` — an toàn để retry vì tiến trình con chưa từng thực thi một lệnh nào (chứng minh được hình thức).
- `ResumeThread`'s giá trị trả về giờ được kiểm tra (`0xFFFFFFFF` = thất bại) — nếu thất bại, tiến trình con **chưa từng được resume**, cũng chứng minh được là trước-mã-người-dùng nên `retry_safe=True`. **Sửa một bug thực sự**: cả `WaitForSingleObject` lẫn `ResumeThread` trước đây thiếu khai báo `restype` tường minh, khiến ctypes mặc định trả về `int` có dấu — biến `0xFFFFFFFF` (sentinel lỗi DWORD) thành `-1`, khiến so sánh `== 0xFFFFFFFF` không bao giờ khớp. Đã thêm `restype = wintypes.DWORD` cho cả hai.
- Đường compat Popen (fallback) cũng không được fail open: nếu `AssignProcessToJobObject` thất bại ở đó, tiến trình bị `kill()` ngay và trả về từ chối — **không** âm thầm tự nhận là "Job-Object + môi trường lọc sạch" khi thực ra Job Object chưa được gán. Có ghi chú tường minh: khác với đường Restricted Token (gán Job Object cho tiến trình còn đang suspended trước khi resume), `subprocess.Popen` không có tương đương `CREATE_SUSPENDED`, nên có một race window ngắn không thể tránh khỏi giữa lúc tạo tiến trình và lúc kiểm tra — đây là đặc tính yếu hơn đã biết, được ghi nhận, của đường compat opt-in này (không xuất hiện ở đường chính).

### Dọn dẹp tài nguyên (không đổi từ bản sửa trước, rà soát lại sau thay đổi CREATE_SUSPENDED)

- Toàn bộ handle Win32 (token, restricted token, process, thread, pipe) và con trỏ SID cấp phát (`LocalFree`) vẫn được giải phóng đúng một lần qua một khối `finally`/`_cleanup()` duy nhất trên mọi đường thoát — bao gồm các đường raise mới quanh CREATE_SUSPENDED/Job Object/ResumeThread. Không double-close.
- Giữ nguyên hoàn toàn: Windows Job Object, `ActiveProcessLimit`, giới hạn bộ nhớ, lọc sạch biến môi trường, chặn `sys.meta_path`/`sys.modules`, allowlist thư mục, chặn COM/win32, mã SACL Low Integrity, mã `TokenIntegrityLevel`, bảo vệ chống introspection, giới hạn stdout, và toàn bộ công việc an ninh Zalo/mobile. Đây vẫn là bản sửa tương thích/phân loại lỗi, **không phải** rollback về an ninh trước v4.1.

### Cấu hình CI (`.github/workflows/ci.yml`)

- Chỉ job **Unit Tests** được bật `JARVIS_SANDBOX_ALLOW_COMPAT_FALLBACK=1` (job-level `env:`), vì GitHub-hosted Windows Server runner đã cho thấy không tương thích với đường launch Restricted Token này. Các job khác (Syntax Check, Import Validation, và mọi workflow release/package/security validation khác) **không** bật cờ này.
- **Điều này không xác nhận Low Integrity đã được kiểm chứng end-to-end trên GitHub-hosted runner** — nó chỉ xác nhận đường Job-Object + môi trường lọc sạch (đã hoạt động tốt trước `adab40d`) chạy được ở đó, và chỉ áp dụng cho lỗi bootstrap CHỨNG MINH ĐƯỢC là trước-mã-người-dùng. Xác nhận runner thực tế đòi hỏi GitHub Actions chạy thật sau khi review/push (chưa thực hiện trong phiên này).

### Test hồi quy (`tests/unit/test_sandbox_compat_fallback.py`)

- File có **40 test hồi quy mocked/xác định** (deterministic, collected — 30 hàm test, trong đó 2 hàm được `@pytest.mark.parametrize` mở rộng thành 12 case), không cần token admin thật hay quyền OS đặc biệt (một vài test yêu cầu `ctypes.windll` tồn tại nên chỉ chạy trên Windows, không yêu cầu privilege đặc biệt). Bao gồm: phân loại `STATUS_DLL_INIT_FAILED`; **`retry_safe` mặc định là `False`** ("unknown state => never retry" — 5 test riêng cho contract này); parsing biến môi trường compat-fallback; fail-closed mặc định; compat fallback chỉ chạy khi bật tường minh VÀ lỗi được xác nhận `retry_safe=True`; `retry_safe=False` không bao giờ retry dù cờ bật; exception chung không bao giờ retry (thay thế test cũ enforce hành vi sai); mã thoát khác 0 hợp lệ và timeout không bao giờ bị retry; test thuần cho `strip_sandbox_ready_sentinel()`; test mô phỏng tiến trình con phát sentinel RỒI thoát với `STATUS_DLL_INIT_FAILED` — xác nhận `subprocess.Popen` KHÔNG được gọi dù cờ compat bật; 3 test cho trình tự CREATE_SUSPENDED/Job Object/ResumeThread (gán thất bại → terminate, không resume; gán thành công → resume đúng một lần; ResumeThread thất bại → terminate, retry_safe=True); test Job Object fail-closed ở đường compat Popen; và test `SetTokenInformation` thất bại.
- Kết quả xác nhận thực tế (chạy cục bộ, chưa chạy trên GitHub Actions): 6 test lịch sử fail trên CI — **đều pass cục bộ** (như dự kiến, máy Windows dev thường không tái hiện được `STATUS_DLL_INIT_FAILED` của GitHub-hosted runner). Các file sandbox liên quan cùng chạy — **100 passed, 46 subtests passed**. Toàn bộ `tests/unit/` — **691 passed, 46 subtests passed, 0 failed** (baseline v4.1.0 thực đo là 651 — không phải 647 như một số tài liệu cũ ghi — cộng 40 test mới của bản sửa này).
- Ruff (`jarvis/sandbox`, file test sandbox liên quan) và mypy (`jarvis`) đều sạch. `git diff --check` sạch.
- **Không** claim CI đã chạy xanh — CI cho nhánh này **chưa được chạy**. Xác nhận cuối cùng đòi hỏi GitHub Actions thật sau khi review/push.

---

## 🛡️ Phiên Bản 4.1.0 (2026-08-30) — OS-Level Kernel Isolation & Master Technical Audit Hardening

Sau 13 vòng kiểm toán đối kháng (Adversarial Technical Audit), phiên bản 4.1.0 mang đến cuộc đại tu kiến trúc an ninh lớn nhất từ trước đến nay cho JARVIS, chuyển đổi ranh giới bảo mật từ monkey-patching tầng ứng dụng sang **Ranh giới Cấp Kernel Hệ Điều Hành (OS Kernel Boundaries)** trên Windows x64.

### 🔒 1. Cách Ly An Ninh Cấp OS Kernel (OS-Level Sandboxing)
* **Windows Mandatory Integrity Control (MIC):**
  - Chuyển tiến trình con thực thi mã động sang `TokenIntegrityLevel = LOW` (`S-1-16-4096`) qua `SetTokenInformation`.
  - Khắc phục lỗi kiểu dữ liệu 64-bit `wintypes.HANDLE` trong chữ ký `ctypes` để gọi thành công `advapi32.SetNamedSecurityInfoW` với SACL `S:(ML;OICI;NW;;;LW)` dưới quyền người dùng phổ thông (Non-Elevated Standard User).
  - Windows Kernel SRM chặn đứng mọi hành vi ghi file trái phép ra ngoài thư mục sandbox với `[Errno 13] Permission denied` trực tiếp từ kernel.
* **Windows Job Object Resource & Process Hardening:**
  - Thiết lập `ActiveProcessLimit = 1`, `JobMemoryLimit = 256MB` và `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
  - Chặn đứng 100% việc tạo tiến trình con (`cmd.exe`, `powershell.exe`, `subprocess.Popen`) với mã lỗi kernel `WinError 1816`.
* **Environment Block Sanitization:**
  - Tự động làm sạch toàn bộ biến môi trường nhạy cảm (API Keys, Token) trước khi truyền qua `CreateProcessAsUserW`.

### 🛡️ 2. Phòng Thủ Đa Tầng Tầng Ứng Dụng (In-Process Runtime Defense-in-Depth)
* **Khắc Phục Lỗ Hổng `__closure__` & `__globals__` Introspection:**
  - Thay thế các wrapper hàm bằng Slot-based Guard Classes (`__slots__ = ()`) ghi đè `__getattribute__` để chặn trích xuất hàm gốc.
* **Prefix Wildcard Matcher & Hai Tầng Đầu Độc Cache:**
  - Nâng cấp cơ chế chặn module cấm sang kiểm tra tiền tố họ module (`win32*`, `_win32*`, `pywin*`, `comtypes*`, `pythoncom*`, `pywintypes*`, `wmi*`, `clr*`, `ctypes`, `socket`, `ssl`).
  - Đầu độc toàn bộ cache `sys.modules` và chèn `_BlockedMetaPathFinder` vào `sys.meta_path[0]`, đồng thời loại bỏ đường dẫn thư mục dự án khỏi `sys.path`.

### 📱 3. An Ninh Cầu Nối Di Động & Webhook
* **Zalo Bot Webhook:**
  - Sửa lỗi xác thực HMAC-SHA256: hỗ trợ constant-time so sánh (`hmac.compare_digest`) cho cả chuỗi Hex 64 ký tự lẫn Base64 44 ký tự.
  - Ràng buộc địa chỉ lắng nghe an toàn trên `127.0.0.1`.
* **Mobile Bridge File Uploads:**
  - Chuyển từ cơ chế blocklist sang **Strict Explicit Allowlist** (`.txt`, `.pdf`, `.png`, `.jpg`, `.csv`, `.json`).
  - Bổ sung kiểm tra đệ quy double-extension (`path.suffixes`) ngăn chặn hoàn toàn kịch bản tấn công tệp thực thi đội lốt tài liệu (`invoice.exe.pdf`).

### ⚡ 4. Bộ Đo Đạc Phần Cứng & Khắc Phục Lỗi STT
* **Sửa Lỗi Xử Lý Đệm Âm Thanh STT:** Sửa ngoại lệ `ValueError: The truth value of an array with more than one element is ambiguous` trong `jarvis/stt/faster_whisper.py` khi nhận mảng `np.ndarray`.
* **Bộ Benchmark Phần Cứng Độc Lập (`scripts/benchmark_hardware.py`):**
  - Đo đạc thực nghiệm số liệu thật trên CPU Intel Core i7-10750H (AST Validator p50: 0.03-0.21ms, OS Sandbox Overhead p50: 170-195ms, SAPI5 PCM Speech Synthesis: 22-141ms).
  - Tách bạch rõ ràng số liệu phần cứng thật khỏi số liệu pipeline adapter giả lập.
* **Tài Liệu Kiểm Toán & Kiến Trúc:**
  - Bổ sung [`docs/SECURITY_ARCHITECTURE.md`](file:///d:/Software%20GitCode/JARVIS/docs/SECURITY_ARCHITECTURE.md) và [`docs/TECHNICAL_AUDIT_REPORT.md`](file:///d:/Software%20GitCode/JARVIS/docs/TECHNICAL_AUDIT_REPORT.md).
* **Test Suite:**
  - Bổ sung 15 Adversarial Integration Tests trong [`tests/integration/test_sandbox_os_boundaries.py`](file:///d:/Software%20GitCode/JARVIS/tests/integration/test_sandbox_os_boundaries.py). Toàn bộ 662 tests pass 100%.

---

## 🚀 Phiên Bản 4.0.1 (2026-08-29) — Stability, CA/CI & Runtime Fixes

Quá trình rà soát bằng phân tích tĩnh (Ruff, mypy) và pipeline CI đã phát hiện một số lỗi tiềm ẩn trước đây bị che khuất bởi các khối `except` quá rộng hoặc đơn giản là chưa từng được bộ test kiểm tra. Các lỗi bên dưới đã được sửa và đều được xác nhận dựa trên hành vi thực tế khi chạy chương trình, không chỉ đơn thuần là làm cho lỗi type-checking biến mất.

### Build & thư viện phụ thuộc

- Sửa một dòng bị lỗi trong `requirements.txt` khiến lệnh `pip install -r requirements.txt` không thể chạy được.
- Sửa `build-backend` không hợp lệ trong `pyproject.toml` (`setuptools.backends.legacy:build` không tồn tại), vốn làm hỏng mọi quy trình build theo chuẩn PEP 517 như `pip install .` và `python -m build`.

### Lỗi khi chạy chương trình

- Sửa tích hợp Telegram bị lỗi (`jarvis/agent/graph.py`, `jarvis/workers/notification_hub.py`) — mã nguồn tham chiếu đến class `TelegramController` không tồn tại và sử dụng sai chữ ký của hàm `send_message`.
- Sửa các lời gọi định tuyến intent bằng LLM (`jarvis/agent/graph.py`, `jarvis/comms/zalo.py`) — mã nguồn tham chiếu đến class `IntentRouter` không tồn tại.
- Bổ sung chức năng tự khởi động cùng Windows (`jarvis/platform/windows.py`) — `set_autostart` và `get_autostart_status` đã được CLI sử dụng nhưng trước đó chưa hề được định nghĩa.
- Sửa chức năng điều khiển âm lượng Windows (`jarvis/automation/control.py`) — sử dụng sai nguồn của hằng số `CLSCTX_ALL`, khiến các thao tác lấy âm lượng, đặt âm lượng và tắt tiếng đều âm thầm thất bại.
- Sửa nhiều lỗi không khớp API/chữ ký hàm trong `jarvis/core/app.py` như sử dụng sai thành viên enum, thiếu đối số bắt buộc, chữ ký cũ của chức năng sinh skill và điền form, cũng như các thao tác tra cứu bị lặp.
- Sửa đăng ký plugin (`jarvis/core/plugin.py`) — có hai định nghĩa `stop_all()` khiến định nghĩa sau ghi đè định nghĩa trước, đồng thời `register_plugin()` có thể trả về `None` thay vì giá trị `bool` đúng chuẩn.
- Sửa các lệnh liệt kê skill trên Discord/Zalo (`jarvis/comms/discord.py`, `jarvis/comms/zalo.py`) — `SkillMetadata` trước đó bị truy cập như một `dict` thay vì một `dataclass`.
- Sửa chức năng lấy giá tiền mã hóa trong skill bản tin buổi sáng (`jarvis/skills/briefing`) — mã nguồn gọi đến một phương thức không tồn tại.
- Sửa bộ xác minh hình ảnh (`jarvis/vision/visual_verifier.py`) — trước đó kết quả được tạo từ dữ liệu ảnh `None` chưa được xử lý thay vì sử dụng các giá trị fallback đã được tính sẵn.
- Bổ sung phương thức `show()` còn thiếu cho overlay luôn hiển thị (`jarvis/ui/overlay.py`) — hàm `toggle()` có gọi đến phương thức này nhưng trước đó nó không tồn tại.
- Sửa dữ liệu pin không hợp lệ trên hệ thống headless/VM (`jarvis/ui/overlay.py`) — `_safe_probe_battery()` giờ coi phần trăm pin sentinel không hợp lệ (ví dụ `-1` do psutil trả về khi hệ thống không có pin thực) là không khả dụng (`None`) thay vì trả trực tiếp giá trị sai, đồng thời vẫn giữ đúng trạng thái đang cắm nguồn AC; bổ sung 3 regression test cho phần trăm hợp lệ, sentinel không hợp lệ và trường hợp không có pin.
- Dữ liệu pin trên Windows giờ hoạt động ổn định giữa các phiên bản Python và xử lý an toàn cả hai giá trị sentinel `-1` và `255` từ `GetSystemPowerStatus`. Nguyên nhân là `ctypes.wintypes.BYTE` đã thay đổi từ kiểu signed sang unsigned giữa Python 3.11 và 3.12, khiến giá trị `-1` trước đây có thể lọt qua bước kiểm tra phạm vi.

### Chất lượng mã nguồn

- Dọn dẹp toàn bộ cảnh báo Ruff + mypy trong `jarvis/` và `tests/` như thứ tự import, binding biến trong closure, thu hẹp kiểu `Optional`, v.v. — không làm thay đổi chức năng.
- Sửa TTS ở chế độ headless/mock trên GitHub Actions — `JARVIS_MOCK_AUDIO=1` giờ bỏ qua việc phát âm thanh vật lý nhưng vẫn giữ nguyên quá trình kiểm tra tổng hợp giọng nói và bộ nhớ đệm.
- Bộ unit test của CI (`tests/unit/`) đã được xác nhận chạy thành công: **647 test passed**.
- GitHub Actions đã được xác nhận hoạt động thành công trên Python 3.13: **Syntax Check, Unit Tests, Import Validation và Pipeline Summary đều passed**.
- Workflow phát hành hiện sử dụng Python 3.13, đồng bộ với pipeline CI chính.

> **Lưu ý:** Điều này **không có nghĩa toàn bộ cây `tests/` đều đang xanh**. Các bộ test mở rộng không thuộc CI như adversarial/challenger stress test, biometrics và các kịch bản e2e vẫn còn một số lỗi tồn tại từ trước, không liên quan đến đợt rà soát này. Một số test yêu cầu các thư viện tùy chọn không được cài trong CI (ví dụ `cv2`), trong khi một số khác kiểm tra những tính năng vốn chưa từng được triển khai.
---

## 🚀 Phiên Bản 4.0.0 (2026-08-28) — Full Autonomous ReAct Agent

JARVIS v4.0.0 là bước nhảy vọt lớn nhất: JARVIS không chỉ thực thi lệnh mà giờ có thể **tự lập kế hoạch và thực thi mục tiêu phức tạp** thông qua vòng lặp Think → Act → Observe → Reflect.

### 🧠 1. LangGraph ReAct Agent (`jarvis/agent/graph.py`)
* Vòng lặp tự trị: **Think → Act → Observe → Reflect → Done**
* 12 built-in tools: web_search, take_note, read_file, write_file, run_python, browser, screenshot, calculator, memory_search, send_telegram, list_dir, git_status
* Heuristic fallback khi LLM không khả dụng
* Giới hạn iterations tránh vòng lặp vô hạn
* Lịch sử đầy đủ từng bước (task_id, steps, result, timestamps)

### 🔔 2. Notification Hub Đa Kênh (`jarvis/workers/notification_hub.py`)
* Gửi đồng thời đến: **Telegram, Discord, Zalo, Windows Toast, Sound, TTS**
* Scheduling: nhắc nhở theo `HH:MM` hoặc ISO datetime, lặp daily/hourly
* Alert Rules: thêm điều kiện tùy chỉnh với cooldown chống spam
* Lịch sử 100 thông báo gần nhất

### 📦 3. Windows Standalone Installer
* `JARVIS.spec` — PyInstaller spec tự sinh
* `installer/setup.iss` — Inno Setup script tạo JARVIS_Setup_v*.exe
* `scripts/build_installer.py` — One-command build: tests → exe → installer
* Hỗ trợ: Desktop shortcut, Start Menu, Autostart Windows, Uninstall

### 🧪 4. Tests (+51 mới, tổng 633)
* `test_zalo_bot.py` — 15 tests
* `test_notification_hub.py` — 17 tests
* `test_react_agent.py` — 19 tests

---

## 🚀 Phiên Bản 3.2.0 (2026-08-28) — Zalo Bot 2-Way Control

### 📱 1. Zalo Bot Controller (`jarvis/comms/zalo.py`)
* Tích hợp Zalo Official Account API — điều khiển JARVIS từ ứng dụng Zalo
* Lệnh: `/status`, `/briefing`, `/note`, `/calc`, `/weather`, `/screenshot`, `/skills`, `/help`
* Ngôn ngữ tự nhiên tiếng Việt → IntentRouter
* Whitelist bảo mật + HMAC-SHA256 signature verification
* Webhook HTTP server nhúng (port 8765, không cần Flask)
* Broadcast đến tất cả user trong whitelist

---

## 🚀 Phiên Bản 3.1.0 (2026-08-28) — Browser Control, Auto-Update & Plugin SDK


Bản nâng cấp v3.1.0 mở rộng JARVIS với khả năng **điều khiển Chrome bằng giọng nói**, **tự cập nhật từ GitHub Releases**, **hệ sinh thái plugin bên thứ 3**, và **pipeline CI/CD tự động build .EXE**.

### 🌐 1. Browser CDP Controller (`jarvis/browser/cdp_controller.py`)
* Điều khiển Chrome/Edge bằng giọng nói qua Playwright (CDP)
* Lệnh: *"Mở YouTube", "Tìm kiếm tin tức", "Click vào nút Đăng nhập", "Chụp ảnh trang web"*
* 9 hành động: `open`, `navigate`, `search`, `click`, `type`, `screenshot`, `extract`, `scroll`, `close`
* Quick URL shortcuts: youtube, gmail, github, shopee, lazada, vnexpress, dantri, tgdd...
* Skill `browser_control` tích hợp trực tiếp vào voice pipeline

### 🔄 2. Auto-Update Daemon (`jarvis/workers/auto_updater.py`)
* Tự động kiểm tra GitHub Releases mỗi 6 giờ
* So sánh semver thông minh: `v3.1.0 > v3.0.0`
* Tự áp dụng bản mới qua `git pull` + `pip install -r requirements.txt`
* Backup marker trước khi cập nhật, rollback về bản trước nếu lỗi
* Lịch sử 30 lần kiểm tra gần nhất tại `logs/update_history.json`
* Skill `auto_updater`: check, update, rollback, history, status

### 🧩 3. Plugin SDK (`jarvis/plugins/loader.py`)
* Hot-load kỹ năng từ `~/.jarvis/plugins/<name>/` — không cần khởi động lại
* Cài từ pip: `pip install jarvis-plugin-<name>` (entry_point: `jarvis.plugins`)
* API: `PluginLoader.load_all()`, `call_plugin()`, `reload_plugin()`, `unload_plugin()`
* Tự động merge vào SkillRegistry khi start JARVIS

### ⚙️ 4. Release CI/CD Pipeline (`.github/workflows/release.yml`)
* Tự động build `JARVIS_v*.*.*.exe` khi push tag `v*.*.*`
* Jobs: tests → build .exe (PyInstaller) → zip → publish GitHub Release
* Sinh `reports/version_status.json` đính kèm vào release
* Support prerelease flag cho `beta`/`rc` tags

### 🧪 5. Tests (+46 mới, tổng 582)
* `tests/unit/test_browser_control.py` — 15 tests (navigation, click, screenshot, extract)
* `tests/unit/test_auto_updater.py` — 16 tests (version compare, fetch, check, apply, rollback, history)
* `tests/unit/test_plugin_sdk.py` — 15 tests (mock loader, folder loader, manifest, unload)

---

## 🚀 Phiên Bản 3.0.0 (2026-08-28) — Self-Coding AI, Semantic Memory RAG & Night Shift Worker


Bản nâng cấp thế hệ thứ ba đưa JARVIS v3.0.0 có khả năng **TỰ TIẾN HÓA**: tự sinh kỹ năng mới từ mô tả tiếng Việt, tìm kiếm ký ức theo ngữ nghĩa (Semantic RAG), và làm việc xuyên đêm tự trị không cần giám sát.

### 🧬 1. Self-Coding Skill Synthesizer (`jarvis/skills/skill_synthesizer/`)
* Tự sinh kỹ năng mới từ mô tả tiếng Việt — *"JARVIS, tạo kỹ năng theo dõi giá vàng"*
* Tự tạo `metadata.json`, mã nguồn `execute()` với 9 template type và đăng ký vào `SkillRegistry` ngay lập tức
* Rollback tự động nếu sinh code thất bại hoặc `ast.parse()` báo lỗi cú pháp
* Hành động: `create`, `preview`, `list`, `delete`

### 🔍 2. Semantic Memory RAG (`jarvis/memory/vector_store.py`)
* Semantic Vector Store với TF-IDF cosine similarity thuần Python — không cần GPU, không cần numpy
* BM25-style IDF formula: `log((N+1)/(df+0.5))` — cho kết quả đúng ngay cả khi dataset nhỏ
* Optional FAISS integration khi có sẵn để tăng tốc 10x
* Lệnh thoại: *"JARVIS, tháng trước tôi đã note gì về dự án X?"*
* Bổ sung vào `MemoryManager`: `semantic_search()`, `build_rag_context()`, `index_fact_to_vectors()`
* Skill `rag_search`: hành động search, index, stats, clear

### 🌙 3. Night Shift Autonomous Worker (`jarvis/workers/night_shift.py`)
* Nhận nhiệm vụ lớn trước khi ngủ, tự thực hiện theo lịch lúc 23:00
* Tự phân rã nhiệm vụ thành các bước (9 keyword categories)
* Tạo báo cáo Markdown tổng hợp, lưu `logs/night_report_*.md`
* Skill `night_planner`: hành động add, list, cancel, report, run_now

---

## 🚀 Phiên Bản 2.3.0 (2026-08-28) — Điều Khiển Đa Kênh & Smart Home

### 📱 1. Discord Bot Controller đầy đủ (`jarvis/comms/discord.py`)
* Điều khiển JARVIS qua Discord server: `!status`, `!briefing`, `!skills`, `!note`, `!calc`, `!screenshot`, `!macro`, `!exec`, `!help`
* Security whitelist theo Discord User ID — chặn người không có quyền
* Rich Embed Discord: bảng màu, fields, icon
* Gửi ảnh chụp màn hình về Discord channel, chuyển file
* Backward compatible alias: `DiscordBotClient = DiscordBotController`

### 🔗 2. Mobile File Bridge (`jarvis/comms/mobile_bridge.py`)
* Nhận file/ảnh từ điện thoại qua Telegram → tự lưu vào `downloads/`
* Validation: extension whitelist (14 loại), giới hạn 50MB
* Gửi clipboard và ảnh màn hình về điện thoại trong < 2 giây
* Transfer history log: `logs/mobile_transfers.json`

### 🏠 3. Smart Home Auto-Discovery (`jarvis/smart_home/discovery.py`)
* Tự quét mạng LAN bằng socket ping + port scan (không cần external deps)
* Nhận dạng 3 loại thiết bị: Home Assistant (port 8123), Tasmota (`/cm?cmnd=Status`), generic HTTP smart device
* Auto-register vào entity registry, persist: `logs/smart_home_devices.json`
* Background scan thread với `discovery_interval_s=3600`
* Skill `smart_home_discovery`: hành động scan, list, probe, status

---

## 🚀 Phiên Bản 2.2.0 (2026-08-28) — Nhìn Thấy Màn Hình & Tự Ghi Nhớ Thao Tác

### 👁️ 1. Context-Aware Screen Assistant (`jarvis/skills/screen_context/`)
* Nhấn `Ctrl+Shift+Space` → JARVIS chụp và phân tích nội dung màn hình hiện tại
* 5 modes: `summarize` (tóm tắt bài báo), `explain_error` (giải thích lỗi terminal), `translate` (dịch văn bản), `describe` (mô tả), `analyze` (phân tích code/dữ liệu)
* Vision LLM integration (Gemini 1.5 Flash) với graceful fallback
* Support cả mss và PIL.ImageGrab

### 📹 2. Voice Macro Recorder (`jarvis/skills/macro_recorder/`)
* Lưu, phát lại và xóa quy trình thao tác bằng giọng nói
* 5 loại bước: `click`, `type`, `key`, `wait`, `open`
* Playback qua pyautogui (optional) hoặc clipboard fallback
* Persist: `logs/macros.json`, hành động: record, play, list, delete

### 🔊 3. Sound Board (`jarvis/skills/sound_board/`)
* Phát âm thanh phản hồi điện ảnh Stark UI tổng hợp bằng numpy sine wave
* 5 preset: activation (3-tone ↑), completion (2-tone ↓), error (200Hz buzz), thinking (330Hz pulse ×3), alert (880Hz burst)
* Fallback im lặng khi sounddevice không khả dụng

---

## 🚀 Phiên Bản 2.1.0 (2026-08-28) — Đàm Thoại Thời Gian Thực & AI Offline

### 🎙️ 1. Voice Activity Detection & Barge-in (`jarvis/audio/vad.py`, `jarvis/audio/fullduplex.py`)
* `VoiceActivityDetector`: phát hiện speech vs silence bằng RMS energy (pure Python) + optional webrtcvad
* `FullDuplexVoiceManager`: ngắt lời JARVIS bất kỳ lúc nào với barge-in state machine
* State machine: IDLE → LISTENING → SPEAKING → INTERRUPTED
* `listen_for_speech()` với pre-speech buffer 200ms và silence timeout configurable

### 🔊 2. Piper TTS Offline (`jarvis/tts/piper.py`)
* Giọng đọc tiếng Việt siêu nhanh (< 80ms) chạy hoàn toàn offline qua ONNX Runtime
* Lazy model loading, Vietnamese phoneme support
* Fallback chain: Piper Offline → ElevenLabs → SAPI5
* Hướng dẫn cài model: `models/piper/vi_VN-vivos-medium.onnx`

### 🎤 3. Faster-Whisper STT Offline (`jarvis/stt/faster_whisper.py`)
* Nhận diện giọng nói tiếng Việt cục bộ với độ trễ < 200ms (model `base`, `int8`)
* Lazy model loading, VAD filter built-in, auto language detection
* `TranscriptionResult` dataclass: text, language, confidence, duration_ms, segments
* Fallback chain: Faster-Whisper Local → Whisper API

### 🎵 4. Stark UI Sound Effects (`jarvis/audio/sound_effects.py`)
* `SoundEffectsPlayer`: tổng hợp tone bằng numpy sine wave — không cần file audio
* 5 preset: activation, completion, error, thinking, alert + custom tone
* Async playback thread để không block JARVIS response

---

## 🔄 CI/CD Pipeline (2026-08-28)

### ⚙️ GitHub Actions (`/.github/workflows/ci.yml`)
* Chạy tự động trên `push` và `pull_request` vào branch `main`
* Job `test`: `python -m pytest tests/unit/ -q --tb=short` trên `windows-latest`
* Job `lint`: `python -m py_compile` cho 15+ module mới
* Cache pip dependencies, upload artifacts `reports/`

### 📊 Health Check Report (`scripts/health_check_report.py`)
* Sinh `reports/health_YYYYMMDD_HHMMSS.md` với bảng trạng thái từng module
* Sinh `reports/version_status.json` với metadata phiên bản
* Kiểm tra import 17 module mới (core + skills)

---

## 🚀 Phiên Bản 2.0.0 (2026-08-27) - Nâng Cấp Toàn Diện: Built-in Skills, Global Hotkeys, Memory Scoring & Standalone Packaging


Bản nâng cấp toàn diện đưa **JARVIS v2.0.0** trở thành một trợ lý cá nhân hoàn thiện với kho kỹ năng đóng gói sẵn, phím tắt toàn hệ thống, cơ chế xếp hạng ký ức thông minh, pipeline đóng gói `.exe` độc lập và giao diện điều khiển đa phương thức.

---

### 🧩 1. Thư Viện 9 Built-in Skills Đóng Gói Sẵn (`jarvis/skills/`)
* **Briefing Sáng (`briefing`)**: Tự động tổng hợp thời tiết thực tế, tin tức công nghệ nóng, tỷ giá thị trường Crypto (BTC, ETH) và lịch trình trong ngày; định dạng báo cáo song ngữ và đọc qua giọng nói TTS.
* **Quản Lý File & Thư Mục (`file_manager`)**: Tìm kiếm file theo tên/phần mở rộng, liệt kê nội dung và mở các thư mục người dùng quen thuộc (Downloads, Documents, Desktop, Workspace).
* **Ghi Chú Nhanh Bằng Giọng Nói (`note_taker`)**: Lưu, phân loại nhãn (tag), tìm kiếm và quản lý ghi chú cá nhân tức thì lưu trữ bền vững trong SQLite/JSON.
* **Chế Độ Tập Trung Pomodoro (`pomodoro`)**: Quản lý các chu kỳ tập trung 25 phút làm việc / 5 phút nghỉ ngơi, tự động tắt thông báo không cần thiết.
* **Điều Khiển Hệ Thống Windows (`system_control`)**: Điều chỉnh âm lượng, độ sáng, chụp ảnh màn hình ra Desktop, khóa máy tính trạm, thu nhỏ toàn bộ cửa sổ về Desktop.
* **Trợ Lý Git Thông Minh (`git_assistant`)**: Báo cáo nhanh trạng thái Git repository (branch hiện tại, file thay đổi, commit gần đây) bằng tiếng Việt tự nhiên.
* **Máy Tính & Quy Đổi Tiền Tệ (`calculator`)**: Phân tích cú pháp cây AST toán học an toàn (hỗ trợ hàm căn bậc hai, phần trăm, lượng giác) và quy đổi tỷ giá tiền tệ tự động (USD, VND, EUR, JPY, GBP).
* **Quản Lý Clipboard (`clipboard`)**: Đọc nhanh nội dung trong bộ nhớ đệm và sao chép văn bản mới bằng Win32 API.
* **Trình Khởi Chạy Ứng Dụng (`app_launcher`)**: Khởi chạy trực tiếp các phần mềm phổ biến (Chrome, VS Code, Spotify, Notepad, Terminal, Settings).

---

### 🧠 2. Cơ Chế Xếp Hạng Ký Ức & Inject System Prompt Thông Minh (`jarvis/memory/`)
* Bổ sung thuật toán tính điểm mức độ liên quan `get_relevant_facts_for_prompt(query, limit)` dựa trên đối sánh từ khóa câu lệnh với hồ sơ người dùng, thói quen và dự án.
* Tự động ưu tiên danh tính người dùng (`user_name`, `email`, `current_project`) và chèn ngữ cảnh vào System Prompt của LLM Intent Router.

---

### ⌨️ 3. Phím Tắt Toàn Cầu Zero-Dependency (`jarvis/platform/hotkeys.py`)
* Xây dựng `GlobalHotkeyManager` dựa trên nền tảng Win32 `RegisterHotKey` và vòng lặp `GetMessageW` chạy trên luồng nền riêng biệt.
* Phím tắt mặc định toàn hệ thống:
  * `Ctrl + Shift + J`: Bật/tắt HUD Holographic Overlay
  * `Ctrl + Shift + L`: Kích hoạt ghi âm giọng nói tức thì (Push-To-Talk)
  * `Ctrl + Shift + M`: Bật/tắt lắng nghe Wake Word ("Hey JARVIS")
  * `Ctrl + Shift + B`: Phát báo cáo tổng hợp buổi sáng
  * `Ctrl + Shift + S`: Kiểm tra tình trạng phần cứng hệ thống

---

### 📦 4. Đóng Gói Ứng Dụng Độc Lập PyInstaller (`build.py` & `scripts/build_exe.py`)
* Xây dựng pipeline đóng gói 1-click tạo tệp thực thi `dist/JARVIS.exe`.
* Tự động bundle cấu hình, thư viện skills, icons và cấu hình đầy đủ hidden imports.

---

### 🌐 5. Nâng Cấp Web Dashboard REST API & Điều Khiển Telegram 2-Chiều
* **Web Dashboard**: Bổ sung các REST endpoint `/api/skills`, `/api/skills/invoke`, `/api/memory`, `/api/hotkeys`.
* **Telegram Bot Controller**: Bổ sung bộ lệnh điều khiển từ xa `/briefing`, `/skills`, `/note <text>`, `/calc <expr>` bên cạnh `/status`, `/lock`, `/exec`.

---

## 🚀 Phiên Bản 1.0.0 (2026-08-25) - Bản Phát Hành Độc Lập Toàn Diện

Phiên bản hoàn thiện đưa **JARVIS** trở thành một **Trợ lý AI Cá nhân Toàn Năng (Autonomous AI Desktop Assistant)**, có khả năng vận hành độc lập như một ứng dụng cài đặt trên Windows, chạy ngầm dưới khay hệ thống, tự khởi động cùng máy và thao tác mọi tác vụ theo yêu cầu bằng giọng nói hoặc phím tắt.

---

### 🌟 1. Tính Năng Ứng Dụng Độc Lập & Khay Hệ Thống (Standalone Desktop Daemon)
* **Khởi chạy không cần VS Code**:
  * `run_jarvis.bat`: Bộ khởi động 1-click có giao diện điều khiển dòng lệnh trực quan.
  * `run_jarvis_silent.vbs`: Khởi chạy ngầm 100% trong nền (không hiện cửa sổ CMD đen).
  * `scripts/create_shortcuts.py`: Tự động tạo Shortcut trên Màn hình chính (`Desktop\JARVIS AI Assistant.lnk`) và Windows Start Menu (`JARVIS Assistant.lnk`).
* **System Tray Controller (Khay Hệ Thống Windows)**:
  * Biểu tượng **Arc Reactor** động phát sáng hiển thị trạng thái thực tế: `ACTIVE` (Cyan), `LISTENING` (Vàng), `MUTED` (Đỏ), `DISABLED` (Xám).
  * Menu ngữ cảnh chuột phải:
    * 🌟 **Mở HUD Hologram** (`Ctrl + Shift + J`)
    * 🎤 **Bật / Tắt Nhận Diện Giọng Nói ("Hey JARVIS")**
    * 🔇 **Tắt / Bật Microphone**
    * 🌐 **Mở Web Dashboard Điều Khiển**
    * ⚙️ **Quản lý Tự Khởi Động cùng Windows**
    * 🔄 **Tải lại Cấu hình (Hot-Reload)**
    * ❌ **Thoát Hoàn Toàn & Giải phóng Tài nguyên**
* **Global Hotkey**: Nhấn `Ctrl + Shift + J` từ bất kỳ ứng dụng, game hoặc trình duyệt nào để bật/tắt Holographic Overlay HUD ngay lập tức.

---

### ⚡ 2. Quản Lý Khởi Động & Tiết Kiệm Tài Nguyên (Zero-Idle Resource Management)
* **Windows Registry Autostart Manager**:
  * Tích hợp trực tiếp vào khóa Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
  * Hỗ trợ bộ lệnh CLI:
    * `python -m jarvis install-autostart`: Cài đặt tự khởi động cùng Windows.
    * `python -m jarvis uninstall-autostart`: Gỡ bỏ tự khởi động.
    * `python -m jarvis autostart-status`: Kiểm tra trạng thái kích hoạt.
* **Tiết Kiệm Năng Lượng Khi Chờ (Zero-Idle Sleep Mode)**:
  * Mức tiêu thụ CPU ở trạng thái chờ cực thấp (**< 0.05% CPU**).
  * Giải phóng bộ nhớ và dừng toàn bộ thread nền ngay lập tức khi người dùng chọn Thoát (Exit).

---

### 🛡️ 3. Vá Toàn Bộ Lỗi Logic & Đạt 100% Test Suite Pass (405/405 Tests)
* **ReAct Planner & Self-Reflection (`jarvis/planner/`)**:
  * Khắc phục lỗi interceptor vô hạn trên các bước đã được người dùng xác nhận an toàn (`confirmation_token`).
  * Sửa cơ chế DAG Dynamic Replanning (`is_successful`) cho phép thay thế tác vụ lỗi bằng đồ thị con thành công.
  * Tự động điều chỉnh chữ ký tham số (`url` -> `query`) khi phản tư chuyển sang tìm kiếm trực tiếp.
* **Computer-Use Vision & GUI Actor (`jarvis/vision/`)**:
  * Khắc phục lỗi `AttributeError: gemini_api_key` với mock spec, hỗ trợ thuộc tính cấp lớp và `getattr` an toàn.
  * Tối ưu hóa chu trình locate 4 tầng (Vision LLM -> OCR -> Win32 UIA -> Heuristics) và cơ chế Self-Healing Retry.
* **Code Interpreter Sandbox & AST Validator (`jarvis/sandbox/`)**:
  * Bổ sung thuộc tính `execution_time_seconds` cho kết quả sandbox.
  * Tăng cường bộ lọc AST và Regex chặn toàn bộ các biến thể nguy hiểm của lệnh PowerShell `Remove-Item` và các lệnh phá hoại ổ đĩa/hệ thống bất kể thứ tự flag.
* **Persistent Memory & Session Context (`jarvis/memory/`)**:
  * Cung cấp đối tượng `MemoryCommandResult` đa năng (vừa là chuỗi tự nhiên vừa hỗ trợ truy xuất dict).
  * Chuẩn hóa định dạng hội thoại nhiều lượt `- User:` / `- JARVIS:` cho System Prompt Injection.
* **Browser Automation (`jarvis/browser/`)**:
  * Sửa lỗi thẻ code block Markdown `<pre><code class="language-python">`.
  * Bổ sung tính năng xuất Cookie chuẩn Netscape ghi trực tiếp vào tệp đích.
  * Sửa bộ điều hướng so sánh giá trực tiếp trên các sàn TMĐT (Shopee, Tiki, Lazada, CellphoneS, GearVN).
* **Sub-Agent Worker Pool (`jarvis/workers/`)**:
  * Đảm bảo kiểm tra tín hiệu hủy (`check_cancelled`) sau khi hoàn thành tác vụ và khi thoát khỏi trạng thái `PAUSED`.

---

### 📊 4. Tổng Kết 17 Subsystems Hoạt Động Hoàn Hảo
1. `Platform & OS`: Win32 API Native Integration
2. `Audio Subsystem`: Virtual/Hardware Audio Stream
3. `Wake Word Engine`: Acoustic Spectral & Vosk ("Hey JARVIS")
4. `Persistent Memory`: SQLite WAL Long-term Facts & Episodic Log
5. `Screen Vision`: Real-time Desktop Capture & Error Dialog Detector
6. `Web Intelligence Hub`: Weather, RSS News, Crypto & Financial Tracker
7. `OS Automation & Shell`: Multi-monitor, Window Focus & Safety Gate
8. `Proactive Intelligence`: Reminders, Health Watchdog, Pomodoro & Briefings
9. `Always-On Overlay HUD`: Waveform Spectrum Analyzer & Task DAG Monitor
10. `Autonomous ReAct Planner`: Dynamic DAG & Self-Reflection Loop
11. `Code Interpreter Sandbox`: AST Safety Validator & Artifact Manager
12. `Persistent Skill Library`: Dynamic Skill Synthesis & Packaging
13. `Browser Automation Agent`: Headless/Visible Browser & Cookie Persistence
14. `Computer-Use Vision & GUI Actor`: 1000x1000 Grounding & Verification
15. `Sub-Agent Worker Pool`: Multi-threaded Autonomous Worker Engine
16. `Speech Services`: Whisper STT & ElevenLabs/SAPI5 TTS
17. `System Tray & Autostart`: Zero-idle Background Daemon & Registry Autostart
