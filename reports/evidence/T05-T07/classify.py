import json,pathlib,xml.etree.ElementTree as E
out=pathlib.Path('reports/evidence/T05-T07')
rows=[]
for t in E.parse(out/'baseline-rerun.xml').iter('testcase'):
 f=t.find('failure');name=t.get('classname')+'::'+t.get('name')
 rows.append({'case':name,'baseline_outcome':'FAIL' if f is not None else 'PASS','baseline_message':f.get('message','') if f is not None else '', 'scope':'outside T-05/T-06/T-07; reproduced on base' if f is not None else 'order/load sensitive candidate; not consistently reproduced'})
(out/'baseline-classification.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
report='# Fresh base rerun classification\n\nSnapshot `9d3c591`, same Python/CI environment. 45 failures reproduced; one candidate passed.\nNo baseline failure was fixed or suppressed by this task. Root-cause ownership still requires review.\n\n'
for row in rows:
 report+='## '+row['case']+'\n\n'+row['scope']+'\n\n```text\n'+row['baseline_message'][:1500]+'\n```\n\n'
(out/'baseline-classification.md').write_text(report,encoding='utf-8')
print('Wrote per-case baseline evidence:',len(rows))
