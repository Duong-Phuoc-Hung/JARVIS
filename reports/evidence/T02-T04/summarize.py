from pathlib import Path
import json,re,xml.etree.ElementTree as E,collections,hashlib
out=Path('reports/evidence/T02-T04')
names=['unit-final-acceptance','browser-acceptance','full-handoff']
rows=[]
for name in names:
    meta=json.loads((out/(name+'.json')).read_text())
    lines=(out/(name+'.txt')).read_text(encoding='utf-8').splitlines()
    summary=next(line for line in reversed(lines) if re.search(r'\d+ passed',line) and re.search(r'in [\d.]+s',line))
    def count(word):
        found=re.search(r'(\d+) '+word+r'\b',summary)
        return int(found.group(1)) if found else 0
    rows.append({'run':name,'passed':count('passed'),'failed':count('failed'),'skipped':count('skipped'),'pytest_seconds':float(re.search(r'in ([\d.]+)s',summary).group(1)),'wall_seconds':meta['wall_seconds'],'exit_code':meta['exit_code'],'summary':summary})
(out/'acceptance-summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
root=E.parse(out/'full-handoff.xml').getroot()
skips=collections.Counter((x.find('skipped').attrib.get('message','') or '').splitlines()[0] for x in root.iter('testcase') if x.find('skipped') is not None)
(out/'skip-reasons.json').write_text(json.dumps(skips,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
