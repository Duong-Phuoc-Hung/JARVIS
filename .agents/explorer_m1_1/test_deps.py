import sys

modules_to_test = [
    ("vosk", "vosk"),
    ("pvporcupine", "pvporcupine"),
    ("openwakeword", "openwakeword"),
    ("webrtcvad", "webrtcvad"),
    ("cv2", "cv2 (OpenCV)"),
    ("mediapipe", "mediapipe"),
    ("face_recognition", "face_recognition"),
    ("pytesseract", "pytesseract"),
    ("easyocr", "easyocr"),
    ("playwright", "playwright"),
    ("winotify", "winotify"),
    ("win32api", "pywin32 (win32api)"),
    ("win32gui", "pywin32 (win32gui)"),
    ("win32con", "pywin32 (win32con)"),
    ("pystray", "pystray"),
    ("keyboard", "keyboard"),
    ("mouse", "mouse"),
    ("pyperclip", "pyperclip"),
    ("psutil", "psutil"),
    ("keyring", "keyring"),
    ("elevenlabs", "elevenlabs"),
    ("faster_whisper", "faster_whisper"),
    ("sounddevice", "sounddevice"),
    ("soundfile", "soundfile"),
    ("google.generativeai", "google-generativeai"),
    ("openai", "openai"),
    ("anthropic", "anthropic"),
    ("telegram", "python-telegram-bot"),
    ("discord", "discord.py"),
    ("requests", "requests"),
    ("websockets", "websockets"),
    ("urllib3", "urllib3"),
    ("matplotlib", "matplotlib"),
    ("sklearn", "scikit-learn"),
    ("numpy", "numpy"),
    ("PIL", "Pillow (PIL)"),
    ("yaml", "PyYAML"),
]

print(f"{'Package / Import':<25} | {'Installed?':<12} | {'Notes / Version'}")
print("-" * 65)

for mod_name, label in modules_to_test:
    try:
        mod = __import__(mod_name)
        ver = getattr(mod, "__version__", "installed")
        print(f"{label:<25} | {'YES':<12} | {ver}")
    except ImportError as e:
        print(f"{label:<25} | {'NO (MISSING)':<12} | {e}")
    except Exception as e:
        print(f"{label:<25} | {'ERROR':<12} | {e}")
