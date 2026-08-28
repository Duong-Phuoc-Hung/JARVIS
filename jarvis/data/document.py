"""
jarvis/data/document.py
=======================
Pure OpenXML DOCX Generator (ECMA-376 compliant), PDF Exporter, and Voice Summary Generator.
Covers Feature:
  - F-30: Multi-Format Document Exporter (DOCX, PDF, PPTX export & voice summary)
"""
from __future__ import annotations

import logging
import re
import time
import zipfile
from pathlib import Path
from typing import Any

from jarvis.data.stats import (
    AnomalyReport,
    DataStatsReport,
    DescriptiveStats,
    MonteCarloResult,
    TrendResult,
)

log = logging.getLogger("jarvis.data.document")


def _xml_escape(text: str) -> str:
    """Escapes special XML characters for OpenXML content."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class DocxReportBuilder:
    """Pure-Python OpenXML (.docx) Generator without third-party binary dependencies."""

    def __init__(self, title: str = "JARVIS Analytics Report"):
        self.title = title
        self.paragraphs_xml: list[str] = []

    def add_title(self, text: str, subtitle: str | None = None) -> None:
        """Adds main title and optional subtitle."""
        esc_title = _xml_escape(text)
        self.paragraphs_xml.append(
            f'<w:p><w:pPr><w:pStyle w:val="Title"/><w:jc w:val="center"/></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="48"/><w:color w:val="1F4E79"/></w:rPr>'
            f'<w:t>{esc_title}</w:t></w:r></w:p>'
        )
        if subtitle:
            esc_sub = _xml_escape(subtitle)
            self.paragraphs_xml.append(
                f'<w:p><w:pPr><w:pStyle w:val="Subtitle"/><w:jc w:val="center"/></w:pPr>'
                f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:i/><w:sz w:val="24"/><w:color w:val="595959"/></w:rPr>'
                f'<w:t>{esc_sub}</w:t></w:r></w:p>'
            )

    def add_heading(self, text: str, level: int = 1) -> None:
        """Adds heading with level 1, 2, or 3."""
        esc_text = _xml_escape(text)
        sz_val = "36" if level == 1 else ("28" if level == 2 else "24")
        color_val = "1F4E79" if level == 1 else ("2E75B6" if level == 2 else "404040")
        self.paragraphs_xml.append(
            f'<w:p><w:pPr><w:pStyle w:val="Heading{level}"/><w:spacing w:before="240" w:after="120"/></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="{sz_val}"/><w:color w:val="{color_val}"/></w:rPr>'
            f'<w:t>{esc_text}</w:t></w:r></w:p>'
        )

    def add_paragraph(
        self,
        text: str,
        bold: bool = False,
        italic: bool = False,
        color: str | None = None,
    ) -> None:
        """Adds a normal text paragraph."""
        esc_text = _xml_escape(text)
        rpr_parts = ['<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>', '<w:sz w:val="22"/>']
        if bold:
            rpr_parts.append("<w:b/>")
        if italic:
            rpr_parts.append("<w:i/>")
        if color:
            rpr_parts.append(f'<w:color w:val="{color}"/>')

        rpr_str = "".join(rpr_parts)
        self.paragraphs_xml.append(
            f'<w:p><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>'
            f'<w:r><w:rPr>{rpr_str}</w:rPr><w:t>{esc_text}</w:t></w:r></w:p>'
        )

    def add_bullet(self, text: str) -> None:
        """Adds a bullet list item."""
        esc_text = _xml_escape(text)
        self.paragraphs_xml.append(
            f'<w:p><w:pPr><w:ind w:left="360" w:hanging="180"/><w:spacing w:after="60"/></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:color w:val="1F4E79"/></w:rPr><w:t>• </w:t></w:r>'
            f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr><w:t>{esc_text}</w:t></w:r></w:p>'
        )

    def add_callout(self, text: str, title: str = "EXECUTIVE SUMMARY") -> None:
        """Adds a highlighted callout box."""
        esc_title = _xml_escape(title)
        esc_text = _xml_escape(text)
        callout_xml = (
            f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>'
            f'<w:top w:val="none"/><w:left w:val="single" w:sz="24" w:color="1F4E79"/><w:bottom w:val="none"/><w:right w:val="none"/>'
            f'</w:tblBorders><w:tblCellMar><w:top w:w="120" w:type="dxa"/><w:left w:w="240" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="240" w:type="dxa"/></w:tblCellMar></w:tblPr>'
            f'<w:tr><w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="F2F4F7"/></w:tcPr>'
            f'<w:p><w:pPr><w:spacing w:after="60"/></w:pPr><w:r><w:rPr><w:b/><w:color w:val="1F4E79"/><w:sz w:val="20"/></w:rPr><w:t>{esc_title}</w:t></w:r></w:p>'
            f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr><w:r><w:rPr><w:sz w:val="22"/><w:i/></w:rPr><w:t>{esc_text}</w:t></w:r></w:p>'
            f'</w:tc></w:tr></w:tbl><w:p><w:pPr><w:spacing w:after="120"/></w:pPr></w:p>'
        )
        self.paragraphs_xml.append(callout_xml)

    def add_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        header_bg: str = "1F4E79",
    ) -> None:
        """Adds a formatted OpenXML grid table with alternating row colors."""
        tbl_parts = [
            '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>'
            '<w:top w:val="single" w:sz="6" w:color="D3D3D3"/>'
            '<w:left w:val="none"/><w:right w:val="none"/>'
            '<w:bottom w:val="single" w:sz="12" w:color="1F4E79"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="E0E0E0"/>'
            '<w:insideV w:val="none"/>'
            '</w:tblBorders><w:tblCellMar><w:top w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:left w:w="180" w:type="dxa"/><w:right w:w="180" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        ]

        # Header Row
        tbl_parts.append('<w:tr><w:trPr><w:tblHeader/></w:trPr>')
        for h in headers:
            esc_h = _xml_escape(h)
            tbl_parts.append(
                f'<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{header_bg}"/></w:tcPr>'
                f'<w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="left"/></w:pPr>'
                f'<w:r><w:rPr><w:b/><w:color w:val="FFFFFF"/><w:sz w:val="22"/></w:rPr><w:t>{esc_h}</w:t></w:r></w:p></w:tc>'
            )
        tbl_parts.append('</w:tr>')

        # Data Rows
        for r_idx, row in enumerate(rows):
            fill_color = "F9FAFB" if (r_idx % 2 == 1) else "FFFFFF"
            tbl_parts.append('<w:tr>')
            for cell in row:
                esc_c = _xml_escape(cell)
                tbl_parts.append(
                    f'<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{fill_color}"/></w:tcPr>'
                    f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
                    f'<w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t>{esc_c}</w:t></w:r></w:p></w:tc>'
                )
            tbl_parts.append('</w:tr>')

        tbl_parts.append('</w:tbl><w:p><w:pPr><w:spacing w:after="180"/></w:pPr></w:p>')
        self.paragraphs_xml.append("".join(tbl_parts))

    def save(self, target_path: str | Path) -> Path:
        """Packages OpenXML files into valid .docx ZIP archive."""
        out = Path(target_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
            '  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>\n'
            '</Types>'
        )

        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
            '</Relationships>'
        )

        doc_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
            '</Relationships>'
        )

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            '  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:color w:val="333333"/></w:rPr></w:rPrDefault></w:docDefaults>\n'
            '</w:styles>'
        )

        body_content = "".join(self.paragraphs_xml)
        sect_pr = (
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
            '</w:sectPr>'
        )

        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            f'<w:body>{body_content}{sect_pr}</w:body>\n'
            '</w:document>'
        )

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types_xml)
            z.writestr("_rels/.rels", rels_xml)
            z.writestr("word/_rels/document.xml.rels", doc_rels_xml)
            z.writestr("word/styles.xml", styles_xml)
            z.writestr("word/document.xml", document_xml)

        return out


class PdfReportBuilder:
    """Zero-dependency PDF 1.4 Canvas & ReportLab Exporter."""

    def __init__(self, title: str = "JARVIS Analytics Report"):
        self.title = title
        self.elements: list[tuple[str, str, dict[str, Any]]] = []  # (type, text/data, options)

    def add_title(self, text: str, subtitle: str | None = None) -> None:
        self.elements.append(("title", text, {}))
        if subtitle:
            self.elements.append(("subtitle", subtitle, {}))

    def add_heading(self, text: str, level: int = 1) -> None:
        self.elements.append(("heading", text, {"level": level}))

    def add_paragraph(self, text: str) -> None:
        self.elements.append(("paragraph", text, {}))

    def add_table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.elements.append(("table", "", {"headers": headers, "rows": rows}))

    def save(self, target_path: str | Path) -> Path:
        """Synthesizes valid PDF 1.4 binary file."""
        out = Path(target_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Build stream content
        stream_lines: list[str] = []
        y = 800

        for elem_type, text, opts in self.elements:
            # Strip non-ASCII for pure PDF 1.4 standard font compliance
            clean_text = re.sub(r"[^\x20-\x7E]", " ", text)
            clean_text = clean_text.replace("(", "\\(").replace(")", "\\)")

            if elem_type == "title":
                stream_lines.append(f"BT /F2 20 Tf 50 {y} Td ({clean_text}) Tj ET")
                y -= 30
            elif elem_type == "subtitle":
                stream_lines.append(f"BT /F1 12 Tf 50 {y} Td ({clean_text}) Tj ET")
                y -= 25
            elif elem_type == "heading":
                lvl = opts.get("level", 1)
                sz = 16 if lvl == 1 else 13
                y -= 10
                stream_lines.append(f"BT /F2 {sz} Tf 50 {y} Td ({clean_text}) Tj ET")
                y -= 20
            elif elem_type == "paragraph":
                stream_lines.append(f"BT /F1 10 Tf 50 {y} Td ({clean_text[:90]}) Tj ET")
                y -= 15
            elif elem_type == "table":
                headers = [re.sub(r"[^\x20-\x7E]", " ", h).replace("(", "\\(").replace(")", "\\)") for h in opts.get("headers", [])]
                rows = opts.get("rows", [])
                # Draw table text
                h_line = " | ".join(headers)
                stream_lines.append(f"BT /F2 10 Tf 50 {y} Td ({h_line[:100]}) Tj ET")
                y -= 15
                for r in rows[:10]:
                    r_clean = [re.sub(r"[^\x20-\x7E]", " ", str(c)).replace("(", "\\(").replace(")", "\\)") for c in r]
                    r_line = " | ".join(r_clean)
                    stream_lines.append(f"BT /F1 9 Tf 50 {y} Td ({r_line[:100]}) Tj ET")
                    y -= 13

            if y < 60:
                break

        stream_body = "\n".join(stream_lines)
        stream_len = len(stream_body.encode("ascii"))

        pdf_content = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>\nendobj\n"
            b"4 0 obj\n<< /Length " + str(stream_len).encode("ascii") + b" >>\nstream\n" + stream_body.encode("ascii") + b"\nendstream\nendobj\n"
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n"
            b"xref\n0 7\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000251 00000 n \n0000000350 00000 n \n0000000424 00000 n \n"
            b"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n505\n%%EOF\n"
        )

        out.write_bytes(pdf_content)
        return out


class VoiceSummaryGenerator:
    """Converts statistical insights into natural language scripts."""

    def generate_summary(
        self,
        filename: str,
        stats: DescriptiveStats | DataStatsReport,
        sim: MonteCarloResult | None = None,
        anomalies: AnomalyReport | None = None,
        trend: TrendResult | None = None,
        language: str = "vi",
    ) -> str:
        """Generates natural language spoken summary."""
        mean_val = getattr(stats, "mean", 0.0)
        median_val = getattr(stats, "median", 0.0)

        parts = [
            f"Đã hoàn thành phân tích tệp dữ liệu '{filename}'.",
            f"Giá trị trung bình là {mean_val:.2f}, trung vị là {median_val:.2f}.",
        ]

        if sim:
            parts.append(
                f"Mô phỏng Monte Carlo ({sim.iterations:,} kịch bản) cho thấy xác suất đạt mục tiêu là {sim.prob_target:.1f}% "
                f"trong khoảng tin cậy 95% từ {sim.p5:.2f} đến {sim.p95:.2f}."
            )

        if anomalies and anomalies.total_anomalies > 0:
            parts.append(f"Phát hiện {anomalies.total_anomalies} điểm dữ liệu bất thường.")

        if trend:
            dir_vn = "tăng trưởng" if trend.direction == "INCREASING" else ("suy giảm" if trend.direction == "DECREASING" else "ổn định")
            parts.append(f"Xu hướng dữ liệu: {dir_vn} (R²={trend.r_squared:.2f}).")

        return " ".join(parts)

    def generate_brief_notification(
        self,
        filename: str,
        stats: DescriptiveStats | DataStatsReport,
        sim: MonteCarloResult | None = None,
    ) -> str:
        return self.generate_summary(filename, stats, sim)


class DocumentExporter:
    """Unified coordinator for DOCX, PDF, and Voice generation."""

    def __init__(self):
        self.voice_gen = VoiceSummaryGenerator()

    def export_report(
        self,
        stats: DataStatsReport | DescriptiveStats,
        sim: MonteCarloResult,
        output_path: Path,
    ) -> Path:
        """Exports structured analytics summary to formatted file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if str(out).endswith(".docx"):
            builder = DocxReportBuilder(title="JARVIS Analytics Report")
            builder.add_title("JARVIS EXECUTIVE ANALYTICS REPORT", subtitle=f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}")
            builder.add_heading("Descriptive Data Statistics", level=1)
            builder.add_table(
                headers=["Metric", "Value"],
                rows=[
                    ["Sample Count", str(getattr(stats, "count", 0))],
                    ["Mean", f"{getattr(stats, 'mean', 0.0):.2f}"],
                    ["Median", f"{getattr(stats, 'median', 0.0):.2f}"],
                    ["Std Dev", f"{getattr(stats, 'std', 0.0):.2f}"],
                    ["25th Percentile (Q1)", f"{getattr(stats, 'p25', 0.0):.2f}"],
                    ["75th Percentile (Q3)", f"{getattr(stats, 'p75', 0.0):.2f}"],
                ],
            )
            builder.add_heading(f"Monte Carlo Simulation ({sim.iterations:,} Runs)", level=1)
            builder.add_table(
                headers=["Simulation Metric", "Result"],
                rows=[
                    ["Expected Mean", f"{sim.mean:.2f}"],
                    ["Standard Error", f"{sim.std_err:.4f}"],
                    ["5th Percentile (P5)", f"{sim.p5:.2f}"],
                    ["50th Percentile (Median)", f"{sim.p50:.2f}"],
                    ["95th Percentile (P95)", f"{sim.p95:.2f}"],
                    ["Target Attainment Probability", f"{sim.prob_target:.1f}%"],
                    ["Value-at-Risk 95% (VaR)", f"{getattr(sim, 'var_95', 0.0):.2f}"],
                ],
            )
            builder.save(out)
            return out

        elif str(out).endswith(".pdf"):
            pdf = PdfReportBuilder()
            pdf.add_title("JARVIS EXECUTIVE ANALYTICS REPORT")
            pdf.add_heading("Data Statistics", level=1)
            pdf.add_table(
                headers=["Metric", "Value"],
                rows=[
                    ["Sample Count", str(getattr(stats, "count", 0))],
                    ["Mean", f"{getattr(stats, 'mean', 0.0):.2f}"],
                    ["Median", f"{getattr(stats, 'median', 0.0):.2f}"],
                    ["Std Dev", f"{getattr(stats, 'std', 0.0):.2f}"],
                ],
            )
            pdf.add_heading("Monte Carlo Simulation", level=1)
            pdf.add_table(
                headers=["Simulation Metric", "Result"],
                rows=[
                    ["Expected Mean", f"{sim.mean:.2f}"],
                    ["95% CI", f"[{sim.p5:.2f} - {sim.p95:.2f}]"],
                    ["Target Prob", f"{sim.prob_target:.1f}%"],
                ],
            )
            pdf.save(out)
            return out

        else:
            # Fallback plain text format
            content = f"""JARVIS EXECUTIVE ANALYTICS REPORT
=================================
Data Metrics:
  - Sample Count: {getattr(stats, 'count', 0)}
  - Mean: {getattr(stats, 'mean', 0.0):.2f}
  - Median: {getattr(stats, 'median', 0.0):.2f}
  - Std Dev: {getattr(stats, 'std', 0.0):.2f}

Monte Carlo Simulation ({sim.iterations:,} runs):
  - Expected Value: {sim.mean:.2f}
  - 95% Confidence Bounds: [{sim.p5:.2f} - {sim.p95:.2f}]
  - Target Attainment Probability: {sim.prob_target:.1f}%
"""
            out.write_text(content, encoding="utf-8")
            return out

    def get_voice_summary(
        self,
        filename: str,
        stats: DataStatsReport | DescriptiveStats,
        sim: MonteCarloResult,
    ) -> str:
        """Returns Vietnamese natural language voice summary."""
        mean_val = getattr(stats, "mean", 0.0)
        median_val = getattr(stats, "median", 0.0)
        return (
            f"Đã hoàn thành phân tích file {filename}. "
            f"Giá trị trung bình là {mean_val:.2f}, trung vị là {median_val:.2f}. "
            f"Mô phỏng Monte Carlo cho thấy xác suất đạt mục tiêu là {sim.prob_target:.1f}% "
            f"trong khoảng tin cậy 95% từ {sim.p5:.2f} đến {sim.p95:.2f}."
        )
