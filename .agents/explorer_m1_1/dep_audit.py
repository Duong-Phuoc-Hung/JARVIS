import ast
import os
import json
import sys
import re

jarvis_dir = r"d:\Software GitCode\JARVIS\jarvis"

# Known third-party / optional libraries
TARGET_DEPS = [
    "vosk", "openwakeword", "pvporcupine", "porcupine", "webrtcvad",
    "cv2", "mediapipe", "face_recognition", "pytesseract", "easyocr",
    "playwright", "winotify", "win32api", "win32con", "win32gui", "win32process", "win32event", "win32service", "winerror",
    "pystray", "keyboard", "mouse", "pyperclip", "psutil", "keyring",
    "elevenlabs", "faster_whisper", "sounddevice", "soundfile",
    "google.generativeai", "openai", "anthropic",
    "telegram", "discord", "requests", "websockets", "urllib3",
    "matplotlib", "sklearn", "numpy", "PIL", "yaml"
]

dep_usage = {}

for root, dirs, files in os.walk(jarvis_dir):
    for f in sorted(files):
        if not f.endswith(".py"):
            continue
        full_path = os.path.join(root, f)
        rel_path = os.path.relpath(full_path, jarvis_dir).replace("\\", "/")
        
        with open(full_path, "r", encoding="utf-8-sig", errors="ignore") as fp:
            content = fp.read()
            
        for dep in TARGET_DEPS:
            mod_pattern = r"\b" + re.escape(dep.split(".")[0]) + r"\b"
            if re.search(mod_pattern, content):
                if dep not in dep_usage:
                    dep_usage[dep] = []
                dep_usage[dep].append(rel_path)

print("=== External/Optional Dependency Usage across jarvis/ ===")
for dep, files in sorted(dep_usage.items()):
    mod_name = dep.split(".")[0]
    
    try:
        __import__(mod_name)
        status = "INSTALLED"
    except ImportError:
        status = "MISSING"
    except Exception as e:
        status = f"ERROR: {e}"
        
    print(f"Dep: {dep:<20} | Status: {status:<10} | Found in {len(files):<2} files: {files[:4]}{'...' if len(files)>4 else ''}")

