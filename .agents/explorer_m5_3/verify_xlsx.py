import zipfile
import io
import xml.etree.ElementTree as ET

def create_sample_xlsx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        ct = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""
        zf.writestr("[Content_Types].xml", ct.encode("utf-8"))

        # _rels/.rels
        rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
        zf.writestr("_rels/.rels", rels.encode("utf-8"))

        # xl/_rels/workbook.xml.rels
        wb_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels.encode("utf-8"))

        # xl/workbook.xml
        wb = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="DataSheet" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
        zf.writestr("xl/workbook.xml", wb.encode("utf-8"))

        # xl/sharedStrings.xml
        sst = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
  <si><t>MetricName</t></si>
  <si><t>Score</t></si>
</sst>"""
        zf.writestr("xl/sharedStrings.xml", sst.encode("utf-8"))

        # xl/worksheets/sheet1.xml
        sheet = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
    </row>
    <row r="2">
      <c r="A2"><v>101</v></c>
      <c r="B2"><v>88.5</v></c>
    </row>
    <row r="3">
      <c r="A3"><v>102</v></c>
      <c r="B3"><v>92.3</v></c>
    </row>
  </sheetData>
</worksheet>"""
        zf.writestr("xl/worksheets/sheet1.xml", sheet.encode("utf-8"))

    buf.seek(0)
    return buf

def parse_xlsx(buf):
    with zipfile.ZipFile(buf, "r") as zf:
        # 1. Parse shared strings if present
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in tree.findall("ns:si", ns):
                t = si.find("ns:t", ns)
                shared_strings.append(t.text if t is not None and t.text else "")

        # 2. Parse sheet1.xml
        sheet_data = []
        if "xl/worksheets/sheet1.xml" in zf.namelist():
            tree = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
            ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for row in tree.findall(".//ns:row", ns):
                row_vals = []
                for c in row.findall("ns:c", ns):
                    t_attr = c.attrib.get("t")
                    v_elem = c.find("ns:v", ns)
                    val = v_elem.text if v_elem is not None and v_elem.text else ""
                    if t_attr == "s":
                        val = shared_strings[int(val)] if int(val) < len(shared_strings) else ""
                    row_vals.append(val)
                sheet_data.append(row_vals)
        return sheet_data

if __name__ == "__main__":
    b = create_sample_xlsx()
    data = parse_xlsx(b)
    print("Parsed XLSX rows:", data)
