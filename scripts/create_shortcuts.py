"""
scripts/create_shortcuts.py
===========================
Generates Windows Desktop and Start Menu shortcuts for JARVIS AI Assistant.
Uses PowerShell / WScript.Shell COM to create valid .lnk files on Windows.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def create_windows_shortcut(
    target_path: Path,
    shortcut_path: Path,
    description: str = "JARVIS AI Desktop Assistant",
    icon_path: Path | None = None,
    working_dir: Path | None = None,
) -> bool:
    """Creates a Windows .lnk shortcut using PowerShell COM automation."""
    if sys.platform != "win32":
        print(f"Skipping shortcut creation on non-Windows platform: {sys.platform}")
        return False

    working_dir = working_dir or target_path.parent
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}')
    $Shortcut.TargetPath = '{str(target_path)}'
    $Shortcut.WorkingDirectory = '{str(working_dir)}'
    $Shortcut.Description = '{description}'
    """
    if icon_path and icon_path.exists():
        ps_script += f"\n    $Shortcut.IconLocation = '{str(icon_path)}'"
    ps_script += "\n    $Shortcut.Save()"

    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            check=True,
            creationflags=_cflags,
        )
        print(f"[+] Shortcut created successfully: {shortcut_path}")
        return True
    except Exception as exc:
        print(f"[-] Failed to create shortcut at {shortcut_path}: {exc}")
        return False


def install_all_shortcuts() -> None:
    """Installs JARVIS shortcuts to Windows Desktop and Start Menu."""
    if sys.platform != "win32":
        print("Shortcut installation is only applicable on Windows.")
        return

    # Target launcher: silent VBS or batch
    vbs_launcher = ROOT_DIR / "run_jarvis_silent.vbs"
    bat_launcher = ROOT_DIR / "run_jarvis.bat"
    target = vbs_launcher if vbs_launcher.exists() else bat_launcher

    # Desktop path
    user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
    desktop_dir = user_profile / "Desktop"
    desktop_shortcut = desktop_dir / "JARVIS AI Assistant.lnk"

    # Start Menu path
    app_data = Path(os.environ.get("APPDATA", user_profile / "AppData" / "Roaming"))
    start_menu_dir = app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "JARVIS"
    start_menu_shortcut = start_menu_dir / "JARVIS Assistant.lnk"

    print("=" * 65)
    print(" Installing JARVIS Windows Shortcuts...")
    print(f" Target Launcher: {target}")
    print("=" * 65)

    create_windows_shortcut(
        target_path=target,
        shortcut_path=desktop_shortcut,
        description="JARVIS Autonomous AI Desktop Assistant",
        working_dir=ROOT_DIR,
    )

    create_windows_shortcut(
        target_path=target,
        shortcut_path=start_menu_shortcut,
        description="JARVIS Autonomous AI Desktop Assistant",
        working_dir=ROOT_DIR,
    )

    print("=" * 65)
    print(" Shortcut installation finished! You can now start JARVIS from:")
    print(f" 1. Desktop Icon: {desktop_shortcut}")
    print(f" 2. Windows Start Menu: Search for 'JARVIS Assistant'")
    print(f" 3. Double-clicking: {bat_launcher}")
    print("=" * 65)


if __name__ == "__main__":
    install_all_shortcuts()
