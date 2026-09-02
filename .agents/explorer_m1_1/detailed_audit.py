import ast
import os
import re
import json

with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_1\audit_raw.json", "r", encoding="utf-8") as fp:
    results = json.load(fp)

print("=== TODOs, NotImplementedError, Pass/Empty Functions ===")
for r in results:
    if r["todos"] or r["not_impl"] or r["pass_funcs"]:
        print(f"File: {r['rel_path']} (lines: {r['lines']})")
        if r["todos"]:
            print(f"  TODOs on lines: {r['todos']}")
        if r["not_impl"]:
            print(f"  NotImplementedError on lines: {r['not_impl']}")
        if r["pass_funcs"]:
            print(f"  Pass/Empty functions: {r['pass_funcs']}")

print("\n=== App.py proactive import inspection ===")
app_path = r"d:\Software GitCode\JARVIS\jarvis\core\app.py"
with open(app_path, "r", encoding="utf-8") as fp:
    app_lines = fp.readlines()
for i, line in enumerate(app_lines):
    if "proactive" in line.lower():
        print(f"app.py:{i+1}: {line.strip()}")

print("\n=== Wake word inspection ===")
ww_path = r"d:\Software GitCode\JARVIS\jarvis\audio\wake_word.py"
with open(ww_path, "r", encoding="utf-8") as fp:
    ww_lines = fp.readlines()
for i, line in enumerate(ww_lines):
    if any(k in line.lower() for k in ["vosk", "porcupine", "model", "fallback", "import", "class"]):
        print(f"wake_word.py:{i+1}: {line.strip()}")

