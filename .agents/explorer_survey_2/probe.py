import sys
import os
import platform
import ctypes
import importlib
import subprocess

print("=== SYSTEM INFO ===")
print("Python:", sys.version)
print("Platform:", platform.platform())
print("Machine:", platform.machine())
print("Arch:", platform.architecture())
print("Exec:", sys.executable)

print("\n=== STDLIB CHECKS ===")
std_libs = [
    "tkinter", "sqlite3", "ctypes", "subprocess", "imaplib", "email",
    "asyncio", "winreg", "msvcrt", "winsound", "wave", "threading",
    "queue", "dataclasses", "pathlib", "typing", "json", "unittest",
    "http.server", "urllib.request", "wsgiref"
]
for lib in std_libs:
    try:
        mod = importlib.import_module(lib)
        print(f"STDLIB {lib}: AVAILABLE")
    except Exception as e:
        print(f"STDLIB {lib}: FAILED ({e})")

print("\n=== EXTENSION / OPTIONAL PKG CHECKS ===")
check_pkgs = [
    "numpy", "sounddevice", "elevenlabs", "requests", "pydantic",
    "dotenv", "websockets", "pytest", "psutil", "pywin32",
    "win32gui", "win32con", "win32api", "wmi", "pystray", "PIL",
    "cv2", "mediapipe", "face_recognition", "speech_recognition",
    "whisper", "openai", "anthropic", "google.generativeai",
    "pandas", "docx", "reportlab", "pptx", "paho.mqtt",
    "telegram", "discord", "aiohttp", "pyttsx3", "pyaudio"
]
for pkg in check_pkgs:
    try:
        mod = importlib.import_module(pkg)
        ver = getattr(mod, "__version__", "installed")
        print(f"PKG {pkg}: AVAILABLE ({ver})")
    except Exception as e:
        print(f"PKG {pkg}: NOT INSTALLED ({e.__class__.__name__})")

print("\n=== WINDOWS SYSTEM EXECUTABLES IN PATH ===")
cli_tools = [
    "powershell", "pwsh", "cmd", "wmic", "nmap", "tshark", "wireshark",
    "typeperf", "netsh", "ipconfig", "tasklist", "taskkill", "shutdown",
    "systeminfo", "curl", "tar", "git", "where"
]
for tool in cli_tools:
    found = shutil_which = None
    try:
        import shutil
        found = shutil.which(tool)
        if found:
            print(f"CLI {tool}: FOUND at {found}")
        else:
            print(f"CLI {tool}: NOT FOUND in PATH")
    except Exception as e:
        print(f"CLI {tool}: ERROR ({e})")

print("\n=== CTYPES / WIN32 API TESTS ===")
# Test Windows user32/kernel32 availability
try:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    print("ctypes.windll (user32, kernel32): AVAILABLE")
    # Test screen metrics
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    print(f"Primary screen resolution via ctypes: {w}x{h}")
except Exception as e:
    print(f"ctypes.windll test failed: {e}")

# Test SAPI.SpVoice via win32com or ctypes
try:
    import win32com.client
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    print("SAPI.SpVoice (via win32com): AVAILABLE")
except Exception as e:
    print(f"SAPI.SpVoice (via win32com): {e}")

# Test powershell SAPI TTS fallback
try:
    ps_tts = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName System.Speech; [System.Speech.Synthesis.SpeechSynthesizer]"],
        capture_output=True, text=True, timeout=5
    )
    if ps_tts.returncode == 0:
        print("System.Speech.Synthesis (via PowerShell): AVAILABLE (built-in Windows TTS fallback)")
    else:
        print(f"System.Speech.Synthesis via PowerShell: failed code {ps_tts.returncode}")
except Exception as e:
    print(f"System.Speech.Synthesis via PowerShell: {e}")
