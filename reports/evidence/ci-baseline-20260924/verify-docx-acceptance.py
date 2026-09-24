"""Read-only verification of the DOCX addendum; uses only the Python standard library."""
import hashlib
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

started = time.perf_counter()
evidence = Path(__file__).resolve().parent
repo = evidence.parents[2]
data = json.loads((evidence / 'docx-acceptance.json').read_text(encoding='utf-8'))
docx = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(data['source'])
assert hashlib.sha256(docx.read_bytes()).hexdigest() == data['source_sha256']
with zipfile.ZipFile(docx) as source:
    document = ET.fromstring(source.read('word/document.xml'))
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
for expected in data['assignment_rows'].values():
    matches = []
    for row in document.findall('.//w:tr', ns):
        cells = ['\n'.join(''.join(p.itertext()) for p in c.findall('.//w:p', ns)) for c in row.findall('w:tc', ns)]
        if cells and cells[0] == expected['id']:
            matches.append(cells)
    assert matches == [list(expected.values())], expected['id']
archive = repo / data['immutable_archive']['path']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == data['immutable_archive']['sha256']
with zipfile.ZipFile(archive) as saved:
    assert saved.testzip() is None
    def raw(name):
        matches = [n for n in saved.namelist() if n == name or n.endswith('/' + name)]
        assert len(matches) == 1, (name, matches)
        return saved.read(matches[0])
    for name, expected in data['evidence_sha256'].items():
        assert hashlib.sha256(raw(name)).hexdigest() == expected, name
    manifest = json.loads(raw('source-manifest.json'))
    for name, expected in manifest['files'].items():
        assert hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected, name
    for case in data['verified_junit_cases']:
        matches = [t for t in ET.fromstring(raw(case['junit'])).iter('testcase') if t.get('name') == case['name'] and t.get('classname') == case['classname']]
        assert len(matches) == 1 and not any(c.tag in {'failure', 'error', 'skipped'} for c in matches[0]), case
print(json.dumps({'docx_rows': len(data['assignment_rows']), 'source_hashes': len(manifest['files']), 'junit_cases': len(data['verified_junit_cases']), 'wall_seconds': round(time.perf_counter() - started, 6), 'result': 'PASS evidence integrity; no pytest run'}, ensure_ascii=False))