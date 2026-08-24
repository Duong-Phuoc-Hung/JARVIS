import sys
import os
import ctypes
from ctypes import wintypes
import subprocess
import json
import zipfile
import io
import socket
import imaplib
import http.server
import threading
import time

print("=== 1. TOML / JSON CONFIG TEST ===")
try:
    import tomllib
    toml_data = tomllib.loads("""
    [general]
    name = "JARVIS"
    version = "2.0.0"
    [gestures]
    double_clap = "spotify_welcome"
    """)
    print("tomllib: AVAILABLE, parsed test config successfully")
except Exception as e:
    print("tomllib error:", e)

print("\n=== 2. ZERO-DEP DOCX REPORT GENERATION TEST ===")
def generate_minimal_docx(title: str, text: str) -> bytes:
    # A DOCX is a zip archive containing specific XML files
    content_types = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    rels = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    doc_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:rPr><w:b/><w:sz w:val="48"/></w:rPr><w:t>{title}</w:t></w:r></w:p>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>""".encode('utf-8')
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('word/document.xml', doc_xml)
    return buf.getvalue()

docx_bytes = generate_minimal_docx("JARVIS System Report", "All modules operational.")
print(f"Zero-dep DOCX generated size: {len(docx_bytes)} bytes")

print("\n=== 3. ZERO-DEP RAW SOCKET PORT SCANNER ===")
def probe_port(host="127.0.0.1", port=80, timeout=0.2):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        res = s.connect_ex((host, port))
        s.close()
        return res == 0
    except Exception:
        return False

print("Probe localhost port 80:", probe_port("127.0.0.1", 80))

print("\n=== 4. HTTP EMBEDDED DASHBOARD TEST ===")
class MiniHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"JARVIS Online"}')
    def log_message(self, format, *args):
        pass

server = http.server.HTTPServer(("127.0.0.1", 19876), MiniHandler)
th = threading.Thread(target=server.serve_forever, daemon=True)
th.start()

import urllib.request
with urllib.request.urlopen("http://127.0.0.1:19876/") as resp:
    body = resp.read().decode('utf-8')
    print("Embedded HTTP Dashboard response:", body)
server.shutdown()

print("\n=== 5. WINDOWS REGISTRY AUTO-START CHECK ===")
try:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
    print("winreg HKCU Run key opened successfully for read access")
    winreg.CloseKey(key)
except Exception as e:
    print("winreg test error:", e)

print("\n=== 6. POWERSHELL ASYNC SAPI TTS ENGINE TEST ===")
# Test non-blocking background speech synthesis script
ps_tts_code = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SpeakAsync("JARVIS system online.") | Out-Null
Start-Sleep -Milliseconds 200
"""
p = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_tts_code])
print(f"Launched async PowerShell TTS, PID={p.pid}")
p.wait(timeout=5)
print("Async PowerShell TTS completed successfully.")
