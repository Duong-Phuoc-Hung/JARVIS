import json, sys, re, xml.etree.ElementTree as E
from pathlib import Path
out=Path("reports/evidence/T02-T04")
name=sys.argv[1]
root=E.parse(out/(name+".xml")).getroot()
prior=json.loads((out/"base-failure-reference.json").read_text(encoding="utf-8"))["tests"]
def normalized(node):
    node = re.sub(r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2}))", lambda m: chr(int(m.group(1) or m.group(2),16)), node)
    return re.sub(r"[\\/]+", "/", node)
by_node={normalized(x["node"]):x for x in prior}
rows=[]
for case in root.iter("testcase"):
    failure=case.find("failure")
    if failure is None: failure=case.find("error")
    if failure is None:continue
    parts=case.attrib["classname"].split(".")
    node=case.attrib["classname"]+"::"+case.attrib["name"]
    for i in range(len(parts),0,-1):
        file="/".join(parts[:i])+".py"
        if Path(file).is_file():
            node=file+"::"+"::".join(parts[i:]+[case.attrib["name"]]);break
    old=by_node.get(normalized(node))
    rows.append({"node":node,"current_failure":failure.attrib.get("message","")[:1600],"matches_base_failure":bool(old),"category":old["category"] if old else "NEEDS_TRIAGE","baseline_note":old["note"] if old else "", "scope":"Existing failure at unchanged base test; outside T-02/T-03/T-04" if old else "Requires inspection"})
(out/(name+"-failures.json")).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"failures":len(rows),"matched":sum(x["matches_base_failure"] for x in rows),"new":[x for x in rows if not x["matches_base_failure"]]},ensure_ascii=False))
