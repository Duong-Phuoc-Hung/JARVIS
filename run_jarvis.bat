@echo off
title JARVIS AI Assistant
chcp 65001 >nul
cls

echo ===================================================================
echo                  JARVIS AI DESKTOP ASSISTANT
echo ===================================================================
echo  Khoi dong JARVIS Standalone System...
echo  - Voice Recognition & Wake Word ("Hey JARVIS")
echo  - ReAct Autonomous Planner & Sub-Agent Pool
echo  - Always-On Holographic Overlay HUD (Ctrl+Shift+J)
echo  - System Tray Controller (Goc duoi ben phai Taskbar)
echo ===================================================================

cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python chua duoc them vao PATH. Vui long cai dat Python 3.10+.
    pause
    exit /b 1
)

python -m jarvis run %*

if %errorlevel% neq 0 (
    echo.
    echo [JARVIS bi dung dot ngot voi ma loi: %errorlevel%]
    pause
)
