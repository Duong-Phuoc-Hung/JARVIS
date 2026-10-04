# JARVIS release readiness — 2026-10-04

Source version: 5.2.1, unreleased. Base HEAD: 247307c.
Verdict: **NO-GO product release**. Không có tag/release/installer mới được công bố.

## Phạm vi bản vá

Giữ nguyên các thay đổi có sẵn của người dùng. Bổ sung safety cho healing
auto-kill/dialog auto-dismiss; truyền lỗi backend notes/routines/workflows/research;
không nói thành công khi native API thất bại; không tuyên bố RAM đã giảm khi chưa đo.
Decoder TTS lỗi không trả MP3 giả PCM. Cloud timeout/connection error đi tới
local fallback, local model và endpoint tách biệt cloud; ẩn exception chain
có thể chứa credential. Loại bỏ baseline giá tài chính giả khi API không dùng được.
Khai báo dependency audio và model collection cho PyInstaller.

## Bằng chứng hiện tại

| Kiểm tra | Kết quả | Giới hạn |
|---|---|---|
| Release/safety/wake/LLM/packaging focused | 147 passed, 15 subtests, 42.74s | Trước bản vá finance cuối; đa số mocked |
| Finance offline regression RED | 3 failed trước vá | Chứng minh cả FX/crypto/stock tạo giá giả |
| Finance/web/refinements sau vá | 61 passed, 52.02s | API mocked; không phải live market acceptance |
| Notes persistence + release blockers | 25 passed, 5.30s | File tạm thật; kiểm thử retry/concurrent writes |
| Builtin notes CRUD cô lập | 1 passed, 13 deselected, 0.49s | Registry path, không dùng notebook thật |
| Installer contract/version | 8 passed, 0.64s | Không chạy compiler thật |
| Full repository baseline | 4298 passed, 1 failed, 40 skipped, 268 subtests, 891.68s | H-05 failure, trước vá router/notes/finance cuối |
| H-05 + router/refinements | 59 passed, 43.40s; H-05/router riêng 23 passed, 1.22s | Không phải voice live |
| Finance/briefing/release + E2E tiers 1–4 | 139 passed, 10.84s | Sau vá partial briefing, mocked resources |
| Full candidate follow-up | Dừng sau 4 failures quan sát được | Snapshot cũ: briefing không catch finance unavailable; không có final summary |
| Full post-briefing snapshot | 4321 passed, 3 failed, 40 skipped, 268 subtests, 1 warning, 943.07s | Ba lỗi được phân tích bên dưới; không phải full-green |
| Legacy finance assertions sau cập nhật | 2 passed, 17 deselected, 1.06s | Hai test từng đòi API lỗi vẫn trả giá dương; nay yêu cầu fail-closed |
| Voice notes test isolation | 1 passed, 35 deselected, 8.31s | LOCALAPPDATA và home đều vào tmp_path |
| Final targeted regression | 76 passed, 38.75s | Integration-E2E unit module, challenger2 stress, finance, notes, release, packaging, router; gồm cả 3 ca lỗi đã xử lý |
| Security scanner | 0 findings, 203 files, 68,822 lines, 1.35s | Static rules, không phải pentest toàn diện |
| Build environment check | PASS | Có Python/PyInstaller/Inno Setup; chưa build/chưa clean-machine test |
| Wake two-stage focused | 135 passed / 16.56s | OpenWakeWord + Whisper post-roll; mocked unit/resources |
| Wake synthetic real-model replay | 14/14 đúng | 3 TTS positive, 11 TTS negative; không phải giọng live |
| Wake offline model staging | 72.0 MB model.bin, spec compile pass | Chưa build/cài EXE trên máy sạch |
| Full final tree sau wake fix | 4,612 passed, 40 skipped, 0 failed/errors, 868.002s | Một RuntimeWarning `Server._close` chưa await; không phải runtime-live acceptance |

Artifacts: `reports/evidence/release_focused_20261004.xml`,
`reports/evidence/release_finance_20261004.xml`,
`reports/evidence/release_audit_20261004.xml` (chỉ có sau khi run kết thúc).
Thêm: `release_router_20261004.xml`, `release_briefing_20261004.xml`,
`release_post_briefing_20261004.xml` trong cùng thư mục.
Không cộng các nhóm scoped vì có test trùng.
Final targeted artifact: `reports/evidence/release_final_targeted_20261004.xml`.
Verdict phạm vi đã chạy: **PASS engineering** cho nhóm regression trên,
**PASS fail-closed** cho missing finance/decoder/backend/safety cases đã test.
Không phải verdict toàn repository hoặc **PASS runtime** cho voice/installer.
Không chạy thêm full loop trong đợt này; full-suite trên final tree vẫn là gate
bắt buộc trước commit/push. CHANGELOG/README/ROADMAP đã được sửa ở working tree,
chưa commit/push vì điều kiện full-green chưa đủ.

40 skipped ở baseline gồm: 21 Chromium E2E chưa opt-in, 6 full-pipeline
integration chưa opt-in, 5 thiếu OpenCV, 3 thiếu matplotlib, 3 endpoint live
không truy cập được, 2 collection skipped. Không tính các ca này là runtime pass.

## Gate chưa đóng — thứ tự tiếp theo

1. **Engineering**: full local final-tree đã xanh. Còn chạy Main CI trên commit
   chứa bản vá và điều tra `Server._close` warning; không biến local pass thành
   CI pass trước khi workflow thực sự hoàn tất.
2. **Data safety**: đã sửa atomic replace (flush/fsync), retry PermissionError
   tối đa 5 lần, cleanup file tạm; lock read-modify-write trong một module instance;
   dữ liệu JSON hỏng bị từ chối, không ghi đè. RED concurrency từng chỉ giữ 3/12
   notes, GREEN giữ đủ 12. Chưa chứng nhận multi-process/multiple independently
   loaded registries; cần single-instance enforcement hoặc shared file lock.
3. **Voice**: engineering cascade đã sửa và synthetic replay chặn “Affair”,
   “A fifth”, “Life”, “Hey Travis”, “Hey Charlie” (14/14 toàn tập). Vẫn phải
   thu true_wake do người dùng gán nhãn và long-idle ambient; đo false wakes/hour
   và recall trên holdout. Không suy diễn TTS thành live acceptance. Xem
   `docs/eval/wake_word_fix_report_20261004.md`.
4. **10 workflow**: real OS >=95% tổng và từng workflow >=90%; output phải
   chứng minh tác vụ thật, không chỉ intent routing/process submission.
5. **Voice acceptance**: 50 ca live >=95%, với tài liệu denominator rõ ràng.
6. **Packaging**: tạo candidate, đo kích thước và checksum, kiểm tra import/model
   trong executable; cài/update/rollback trên máy sạch, kiểm chứng signing/trust.
7. **Security/release**: kiểm tra support bundle không chứa secret, credential
   ownership/CI separation; Main CI xanh, 0 P0, P1 có issue/workaround/accepted risk.

Chỉ sau khi đủ evidence mới cân nhắc internal pilot, rồi beta 10–30 người trong
hai tuần. Không nâng PASS fail-closed thành PASS runtime hay GO.

## Sự cố test isolation cần ghi nhận

`test_builtin_skills.py::test_note_taker_crud_lifecycle` trước bản vá không
chuyển LOCALAPPDATA/Path.home sang thư mục tạm nhưng gọi add và clear.
Test đã nằm trong lượt full-run trước khi phát hiện. Vì không có snapshot notebook
trước lượt chạy, không xác định được dữ liệu thật đã mất hay notebook vốn trống.
Không tuyên bố dữ liệu không bị ảnh hưởng hoặc có thể phục hồi. Đã vá test dùng
tmp_path và kiểm tra lại; không tiếp tục chạy CRUD vào notebook thật.

Build tool cũng đã sửa exit status: full build chỉ thành công khi cả executable
và installer thành công, không dùng executable pass để che installer fail.

## Hồi quy và sửa tiếp

- H-05: “man hinh nghi ngoi” bị rule workflow thư giãn bắt nhầm; đã ưu tiên
  ý định screen-off. “ghi chú lại/tạo ghi chú mới” không còn lưu các từ đệm như
  nội dung. Thêm action notebook thực `note_add` vào taxonomy evaluator.
- Sau khi bỏ giá giả, morning briefing phát sinh RuntimeError khi finance
  unavailable. Hub hiện giữ phần còn dùng được, ghi `LIMITED`, `success=False`,
  empty crypto/None FX; app trả `BRIEFING_PARTIAL`, không ghost success.
- Hai legacy tests trong `tests/test_challenger2_stress.py` đòi quote dương
  khi JSON/API lỗi đã được sửa theo contract fail-closed sau khi tái hiện RED.
  Full post-briefing đã collect phiên bản test cũ, nên không thể lấy
  các lượt scoped mới để đổi final summary của full run thành xanh.
- Test thứ ba: `tests/unit/test_integration_e2e.py::test_web_intelligence_hub_briefing_dispatch`
  đòi success khi không có nguồn finance trong môi trường network bị chặn.
  Đã tái hiện riêng (BRIEFING_PARTIAL), bổ sung provider fixtures xác định cho
  success path và assert đúng giá fixture; failure path có regression riêng.
- Full run có `RuntimeWarning: coroutine 'Server._close' was never awaited`
  được ghi nhận tại `test_sim_13_3s_debounce_cooldown_enforcement`; chưa xác định
  nơi tạo coroutine hoặc vá. Không coi đây là clean shutdown đã được chứng nhận.
- Builtin skill `briefing` độc lập vẫn có placeholder weather/crypto/news;
  chưa được vá trong đợt này. Đây là blocker trung thực dữ liệu còn lại,
  không dùng verdict của web hub để tuyên bố toàn bộ briefing hoàn tất.
- Môi trường hiện tại: `python -m pip check` báo googletrans 4.0.0rc1 cần
  httpx==0.13.3, nhưng đã cài httpx 0.28.1. Không tự downgrade thư viện dùng chung.
  Cần môi trường build sạch/isolated dependency resolution trước đóng gói.
- CI release hiện dùng self-signed certificate và chấp nhận Authenticode
  `UnknownError`; không tương đương publisher trust trên máy sạch. Không dùng
  báo cáo artifact v5.2.0 để xác nhận production trust cho source 5.2.1 này.
