const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  HeadingLevel,
  PageBreak,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} = require('docx');
const fs = require('fs');

const out = 'docs/SRS_JARVIS_Current_System_2026-09-23.docx';
const blue = '1F4E79';
const lightBlue = 'D9EAF7';
const gray = 'F2F2F2';

function p(text = '', opts = {}) {
  return new Paragraph({
    spacing: { after: 100, line: 276 },
    ...opts,
    children: [new TextRun({ text, ...opts.run })],
  });
}

function heading(text, level = HeadingLevel.HEADING_1) {
  return new Paragraph({
    heading: level,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, bold: true })],
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: 'bullets', level },
    spacing: { after: 60 },
    children: [new TextRun(text)],
  });
}

function cell(text, opts = {}) {
  return new TableCell({
    width: { size: opts.width || 2400, type: WidthType.DXA },
    shading: opts.header ? { fill: blue, type: ShadingType.CLEAR } : undefined,
    margins: { top: 90, bottom: 90, left: 100, right: 100 },
    children: [new Paragraph({
      spacing: { after: 0 },
      children: [new TextRun({ text, bold: !!opts.header, color: opts.header ? 'FFFFFF' : '000000' })],
    })],
  });
}

function table(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ children: headers.map((h, i) => cell(h, { header: true, width: widths[i] })) }),
      ...rows.map(row => new TableRow({ children: row.map((v, i) => cell(String(v), { width: widths[i] })) })),
    ],
  });
}

const children = [];
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 160 },
  children: [new TextRun({ text: 'SOFTWARE REQUIREMENTS SPECIFICATION', bold: true, size: 34, color: blue })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 100 },
  children: [new TextRun({ text: 'JARVIS — Trợ lý AI cá nhân tự trị cho Windows', bold: true, size: 28 })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 250 },
  children: [new TextRun({ text: 'Baseline hiện trạng • 23/09/2026 • Phiên bản tài liệu 1.0', italics: true, size: 22 })],
}));
children.push(table(['Thuộc tính', 'Giá trị'], [
  ['Phạm vi', 'Repository JARVIS hiện tại trên Windows'],
  ['Trạng thái', 'Baseline hiện trạng — chưa phải Product Release GO'],
  ['Bằng chứng chính', 'E2E 290 passed / 21 skipped; scanner 0 findings'],
  ['Blocker chính', 'Full repository chưa được chứng nhận; còn test legacy ngoài unit và runtime gates chưa đủ'],
], [2200, 7000]));
children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(heading('Mục lục và cách đọc'));
children.push(p('Tài liệu này là SRS hiện trạng, không phải tuyên bố phát hành. “PASS engineering” chỉ xác nhận code/test hoặc fail-closed behavior; “PASS runtime” cần resource thật; “GO” chỉ dùng khi toàn bộ acceptance gate đóng.'));
children.push(p('Các yêu cầu được đánh số FR/NFR để truy vết. Bảng trạng thái cuối tài liệu phân biệt rõ engineering, fail-closed, runtime, internal pilot và product release.'));

children.push(heading('1. Mục đích và phạm vi'));
children.push(p('Tài liệu mô tả hệ thống JARVIS hiện có trên Windows: chức năng, kiến trúc logic, safety, tích hợp, kiểm thử, giới hạn và tiêu chí nghiệm thu. Các tính năng chỉ tồn tại trong tài liệu cũ, stub hoặc trạng thái fallback không được coi là runtime success.'));
children.push(heading('1.1 Mục tiêu sản phẩm', HeadingLevel.HEADING_2));
children.push(p('JARVIS nhận lệnh bằng giọng nói/văn bản, phân tích intent, áp dụng safety ở core/dispatcher, thực thi tác vụ Windows hoặc backend tích hợp, sau đó trả kết quả có trạng thái trung thực cho người dùng.'));
children.push(heading('1.2 Ngoài phạm vi baseline', HeadingLevel.HEADING_2));
['Credential thật cho Telegram/Zalo/Discord/email/Home Assistant.', 'Installer/update/rollback trên máy sạch.', 'Microphone, TShark/Npcap, WMI brightness hoặc thiết bị Home Assistant trên mọi máy.', 'Cho phép Labs/experimental hoạt động mặc định.'].forEach(x => children.push(bullet(x)));

children.push(heading('2. Bối cảnh và người dùng'));
children.push(table(['Nhóm', 'Nhu cầu'], [
  ['Người dùng Windows', 'Mở app, website, tìm kiếm, Spotify, âm lượng, weather, timer, reminder, note, screenshot, truy vấn máy.'],
  ['Core/dispatcher', 'Chuẩn hóa request, safety gate, gọi handler và không trả success giả.'],
  ['Connector/backend', 'Email, Telegram, Discord, Zalo, Home Assistant và dịch vụ web khi đã cấu hình.'],
  ['Maintainer/release', 'Chạy test, scanner, tạo evidence, phân biệt engineering/fail-closed/runtime/release.'],
], [2500, 6700]));

children.push(heading('3. Kiến trúc logic hiện tại'));
children.push(p('Input (voice/text/UI/connector) → STT / LLM Router / rule fallback → IntentResult + parameters → Core Dispatcher → SafetyInterceptor / confirmation / rate limits → Windows automation, Web intelligence, Communications hoặc Labs → normalized outcome → UI overlay / TTS / connector response / evidence log.', { run: { font: 'Consolas', size: 19 } }));
children.push(heading('3.1 Nguyên tắc thiết kế bắt buộc', HeadingLevel.HEADING_2));
['Fail-closed: thiếu cấu hình, binary, thiết bị hoặc dependency phải trả lỗi có mã/trạng thái.', 'Safety nằm ở core; UI/voice không bypass confirmation.', 'Không bịa số liệu phần cứng, packet capture, RAM reclaim hoặc runtime success.', 'Catalog-first cho app Windows: định danh thật, xử lý ambiguity và xác minh launch.'].forEach(x => children.push(bullet(x)));

children.push(heading('4. Yêu cầu chức năng'));
const frRows = [
  ['FR-01', 'Nhận và định tuyến', 'Nhận text/transcript; chuẩn hóa tiếng Việt; trả IntentResult có action, parameters, source, response.'],
  ['FR-02', 'Mở ứng dụng Windows', 'Khám phá catalog, alias an toàn, xử lý not-found/ambiguous, focus/reuse và xác minh launch.'],
  ['FR-03', 'Website/tìm kiếm', 'URL/query encoding đúng; browser refusal hoặc target lỗi phải trả failure.'],
  ['FR-04', 'Tác vụ desktop an toàn', 'Tác vụ an toàn chạy thẳng; shutdown/restart/xóa/uninstall/rollback/gửi ra ngoài/HA cần confirmation.'],
  ['FR-05', 'Telemetry phần cứng', 'CPU/RAM/GPU/disk/battery/status; alias có dấu/không dấu nhất quán; không bịa số liệu.'],
  ['FR-06', 'Web intelligence', 'Weather/news/finance/briefing có fallback/cache đúng trạng thái và làm sạch HTML/XML.'],
  ['FR-07', 'Voice pipeline', 'Phân biệt READY/LIMITED/UNAVAILABLE/ERROR/NOT_CONFIGURED; lỗi mic/STT/TTS không thành success.'],
  ['FR-08', 'Communications', 'Credential, allowlist/admin/safety; trả lỗi NOT_CONFIGURED/AUTH_FAILED/TIMEOUT/UNAVAILABLE.'],
  ['FR-09', 'Labs', 'Opt-in, feature flag, safety không bypass; resource thật mới được coi là runtime.'],
  ['FR-10', 'Logging/evidence', 'Lưu số liệu thực, artifact, trạng thái và giới hạn; không dùng số cũ sau code change lớn.'],
];
children.push(table(['ID', 'Chức năng', 'Yêu cầu'], frRows, [1100, 2200, 5900]));

children.push(heading('5. Mô hình trạng thái và kết quả'));
children.push(p('Result model hiện hành: BackendResult(success, status, code, message, data, retryable) trong jarvis/core/result_model.py; dispatcher đã normalize tương thích ActionResult, connector migration còn theo phase.'));
children.push(table(['Status', 'Ý nghĩa'], [
  ['SUCCESS', 'Hành động hoàn tất thật.'], ['ERROR', 'Đã chạy nhưng lỗi thực tế.'], ['TIMEOUT', 'Quá thời gian.'], ['BLOCKED', 'Safety/policy chặn.'], ['UNAVAILABLE', 'Backend/device/dependency không dùng được.'], ['NOT_CONFIGURED', 'Thiếu account/credential/config.'],
], [2200, 7000]));
children.push(heading('5.1 Health status', HeadingLevel.HEADING_2));
children.push(table(['Health', 'Điều kiện'], [['READY', 'Backend xác nhận chức năng chính hoạt động.'], ['LIMITED', 'Vẫn dùng được nhưng thiếu phần hoặc đang fallback.'], ['UNAVAILABLE', 'Thiếu mic/account/dependency/backend.'], ['ERROR', 'Đã cấu hình đủ nhưng chạy thực tế lỗi.']], [2200, 7000]));
children.push(p('UI chỉ được hiển thị READY khi backend xác nhận; không tự suy đoán từ việc module import thành công.'));

children.push(heading('6. Yêu cầu phi chức năng'));
children.push(table(['ID', 'Yêu cầu'], [
  ['NFR-01', 'Safety check nằm ở dispatcher/core và không bị bypass.'], ['NFR-02', 'Credential không commit; secret thật nằm ngoài repository.'], ['NFR-03', 'Persistence dùng lock, snapshot và atomic replace phù hợp Windows.'], ['NFR-04', 'Router/parser giới hạn kích thước và độ sâu chống ReDoS/DoS.'], ['NFR-05', 'Callback lỗi không làm chết worker/UI.'], ['NFR-06', 'Runtime claim truy nguyên tới command/output/exit code/artifact.'], ['NFR-07', 'Path/subprocess/browser/HTTP dùng allowlist, argument-list và timeout.'], ['NFR-08', 'Headless CI tương thích nhưng mock không phải runtime evidence.'],
], [1500, 7700]));

children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(heading('7. Bằng chứng kiểm thử hiện tại'));
children.push(table(['Phạm vi', 'Kết quả', 'Verdict'], [
  ['E2E', '290 passed, 21 skipped, 0 failed, 23.72s', 'PASS engineering; runtime tùy resource'],
  ['Unit', '3.002 passed, 3 skipped, 0 failed, 334.31s', 'PASS engineering'],
  ['Security subset', '66 passed, 0 skipped, 0 failed, 8.40s', 'PASS engineering'],
  ['Voice/app/release scoped', '240 passed, 0 skipped, 0 failed, 8.00s', 'PASS engineering'],
  ['10-workflow routing', '10/10 intent routes đúng; chưa phải runtime', 'PASS engineering'],
  ['Ruff', 'All changed files pass', 'PASS engineering'],
  ['Security scanner', '0 findings / 202 files / 66.922 lines', 'PASS engineering, static scope'],
  ['Full repository', 'Chưa chứng nhận; dừng lặp test legacy theo yêu cầu', 'NO-GO'],
], [2300, 4200, 2700]));
children.push(heading('7.1 Blocker và giới hạn', HeadingLevel.HEADING_2));
children.push(p('Healing E2E đã được sửa theo telemetry-only: production không tự giảm ram_percent và không khai báo reclaimed_ram nếu backend không quan sát được delta. Full repository còn test legacy mâu thuẫn safety/telemetry; không dùng partial run làm full-green.'));
['Scanner tĩnh không chứng minh mọi runtime path an toàn.', 'TOOL_NOT_FOUND, LABS_DISABLED, PENDING_CREDENTIALS là fail-closed pass, không phải runtime pass.', 'Chưa có clean-machine installer/update/rollback evidence.', 'Chưa có 50 ca voice live, authenticated Spotify playback, connector account, TShark/Npcap hoặc Home Assistant evidence trong baseline.', '10 workflow mới có routing evidence; runtime app probe chỉ phủ Calculator/Notepad trên một host.'].forEach(x => children.push(bullet(x)));

children.push(heading('8. Tiêu chí nghiệm thu Beta'));
['Main CI xanh 100%; 0 P0; không crash/runaway/data-loss đã biết.', '10 workflow Beta đạt tối thiểu 95% tổng thể và không workflow nào dưới 90%.', '50 ca voice live đạt tối thiểu 95%.', 'Không false-success; installer/update/rollback pass trên máy sạch.', 'P1 còn lại có issue, workaround và accepted risk.', 'Credential/connector/device runtime evidence độc lập với mock/CI.'].forEach(x => children.push(bullet(x)));

children.push(heading('9. Ma trận trạng thái hiện tại'));
children.push(table(['Tầng', 'Trạng thái'], [
  ['Engineering/unit', 'PASS engineering — unit/E2E/security xanh; full repository chưa được chứng nhận.'],
  ['Fail-closed', 'PASS cho các đường dẫn đã kiểm tra.'],
  ['Runtime thật', 'PENDING/PARTIAL — E2E host pass, resource thật chưa phủ hết.'],
  ['Internal pilot', 'NOT AUTHORIZED — chưa đóng full suite/runtime gates.'],
  ['Product release', 'NO-GO — chưa đạt Beta GO.'],
], [2600, 6600]));

children.push(heading('10. Tham chiếu'));
['docs/eval/runtime_fix_verification_20260923.md', 'docs/eval/workflow_10_windows_runtime_20260923.md', 'reports/evidence/system_completion_voice_apps_release_20260923.xml', 'reports/evidence/system_completion_healing_20260923.xml', 'reports/evidence/fixes_scanner_final_20260923.json', 'docs/ROADMAP.md', 'CHANGELOG.md'].forEach(x => children.push(bullet(x)));

const doc = new Document({
  creator: 'JARVIS Engineering',
  title: 'JARVIS Software Requirements Specification — Current System',
  subject: 'Current-system SRS baseline and verification evidence',
  sections: [{
    properties: { page: { margin: { top: 900, right: 900, bottom: 900, left: 900 } } },
    headers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'JARVIS SRS • 23/09/2026', size: 16, color: '666666' })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Confidential — Current-system baseline', size: 16, color: '666666' })] })] }) },
    children,
  }],
  numbering: { config: [{ reference: 'bullets', levels: [{ level: 0, format: 'bullet', text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 180 } } } }] }] },
  styles: { default: { document: { run: { font: 'Aptos', size: 21 } } } },
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(out, buf);
  console.log(`Wrote ${out}`);
});
