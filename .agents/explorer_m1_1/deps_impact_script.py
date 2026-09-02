# Missing optional dependencies impact analysis
missing_deps_analysis = [
    {
        "dep": "vosk",
        "install_command": "pip install vosk",
        "installed": False,
        "affected_modules": ["jarvis/audio/wake_word.py"],
        "purpose": "Lightweight offline Vietnamese wake word acoustic keyword recognition (<0.2s latency, zero cloud).",
        "current_fallback": "Degrades to AcousticSpectralDetector (pure DSP spectral flatness and zero-crossing heuristics), which is prone to false triggers in noisy environments.",
        "impact_severity": "🔴 P0 Critical",
        "operational_impact": "Cannot reliably detect 'Hey JARVIS' / 'JARVIS' offline with high phonetic precision; fallback DSP produces false positives / misses in live ambient noise."
    },
    {
        "dep": "pvporcupine",
        "install_command": "pip install pvporcupine",
        "installed": False,
        "affected_modules": ["jarvis/audio/wake_word.py"],
        "purpose": "Commercial offline wake word engine (Picovoice Porcupine).",
        "current_fallback": "Falls back to Vosk or Tier-2 AcousticSpectralDetector.",
        "impact_severity": "🟢 P3 Low",
        "operational_impact": "Requires proprietary access key; non-essential when Vosk Vietnamese model is available."
    },
    {
        "dep": "cv2 (opencv-python)",
        "install_command": "pip install opencv-python",
        "installed": False,
        "affected_modules": [
            "jarvis/gesture/detector.py",
            "jarvis/gesture/hand_tracker.py",
            "jarvis/vision/biometrics.py",
            "jarvis/vision/hands.py"
        ],
        "purpose": "Camera video stream capture, frame manipulation, color space conversion, and computer vision operations.",
        "current_fallback": "Gesture detection and camera biometrics are disabled with warning logs; screen capture falls back to Pillow/mss.",
        "impact_severity": "🟡 P2 Medium",
        "operational_impact": "Disables webcam gesture controls (clap, wave, peace) and facial biometrics authentication; screen-based computer use remains functional."
    },
    {
        "dep": "mediapipe",
        "install_command": "pip install mediapipe",
        "installed": False,
        "affected_modules": [
            "jarvis/gesture/hand_models.py",
            "jarvis/gesture/hand_tracker.py",
            "jarvis/vision/hands.py"
        ],
        "purpose": "21-point 3D hand landmark tracking and gesture recognition.",
        "current_fallback": "Hand gesture detector is disabled; mock hand trackers used in unit tests.",
        "impact_severity": "🟡 P2 Medium",
        "operational_impact": "Real-time hand gesture interactions (swipe, wave, point) are non-functional."
    },
    {
        "dep": "face_recognition",
        "install_command": "pip install face_recognition",
        "installed": False,
        "affected_modules": ["jarvis/vision/biometrics.py"],
        "purpose": "128-d face embeddings for user identification and biometric unlocking.",
        "current_fallback": "Disables facial recognition login; falls back to Windows PIN / password / bypass.",
        "impact_severity": "🟢 P3 Low",
        "operational_impact": "No automatic face-based owner recognition upon camera activation."
    },
    {
        "dep": "winotify",
        "install_command": "pip install winotify",
        "installed": False,
        "affected_modules": ["jarvis/workers/notification_hub.py"],
        "purpose": "Native Windows 10/11 Action Center Toast Notifications.",
        "current_fallback": "Falls back to custom Tkinter/Win32 HUD overlay and console log alerts.",
        "impact_severity": "🟢 P3 Low",
        "operational_impact": "Notifications appear on HUD overlay rather than Windows Notification Action Center."
    },
    {
        "dep": "playwright",
        "install_command": "pip install playwright && playwright install chromium",
        "installed": False,
        "affected_modules": ["jarvis/browser/driver.py", "jarvis/browser/cdp_controller.py"],
        "purpose": "High-level headless/headful browser automation.",
        "current_fallback": "Falls back to direct Chrome DevTools Protocol (CDP) WebSocket connections via `cdp_controller.py`.",
        "impact_severity": "🟡 P2 Medium",
        "operational_impact": "CDP fallback handles standard browsing, but complex DOM interactions and multi-tab orchestration are limited."
    },
    {
        "dep": "pystray",
        "install_command": "pip install pystray",
        "installed": False,
        "affected_modules": ["jarvis/ui/tray.py"],
        "purpose": "Windows System Tray icon with right-click context menu.",
        "current_fallback": "System runs in headless console mode or launches Tkinter overlay directly.",
        "impact_severity": "🟠 P1 High",
        "operational_impact": "No background taskbar notification tray icon for user control."
    },
    {
        "dep": "keyboard & mouse",
        "install_command": "pip install keyboard mouse",
        "installed": False,
        "affected_modules": ["jarvis/automation/control.py", "jarvis/platform/hotkeys.py"],
        "purpose": "Low-level OS global hotkeys and mouse event hooks.",
        "current_fallback": "Uses ctypes `user32.dll` SendInput and Windows API ctypes calls.",
        "impact_severity": "🟡 P2 Medium",
        "operational_impact": "Global hotkey shortcuts (e.g. Ctrl+Shift+J) require active window or ctypes message loop."
    },
    {
        "dep": "python-telegram-bot & discord.py",
        "install_command": "pip install python-telegram-bot discord.py",
        "installed": False,
        "affected_modules": ["jarvis/comms/telegram.py", "jarvis/comms/discord.py"],
        "purpose": "Remote messaging bot interfaces for Telegram and Discord.",
        "current_fallback": "Telegram and Discord bridge gateways remain idle / disabled.",
        "impact_severity": "🟡 P2 Medium",
        "operational_impact": "Cannot send/receive commands remotely via Telegram or Discord."
    },
    {
        "dep": "scikit-learn & matplotlib",
        "install_command": "pip install scikit-learn matplotlib",
        "installed": False,
        "affected_modules": ["jarvis/memory/vector_store.py", "jarvis/data/analysis_service.py"],
        "purpose": "TF-IDF vector store cosine similarity and telemetry data chart plotting.",
        "current_fallback": "VectorStore falls back to keyword matching; AnalysisService outputs tabular ASCII text reports.",
        "impact_severity": "🟢 P3 Low",
        "operational_impact": "Reduced semantic ranking precision for long-term memory queries; no visual chart rendering."
    }
]

import json
with open(r"d:\Software GitCode\JARVIS\.agents\explorer_m1_1\deps_impact.json", "w", encoding="utf-8") as fp:
    json.dump(missing_deps_analysis, fp, indent=2, ensure_ascii=False)
print("Saved deps_impact.json")
