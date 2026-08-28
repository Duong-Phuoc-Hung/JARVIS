"""
scripts/build_exe.py
====================
Standalone PyInstaller Build Pipeline for JARVIS Windows Application.
Packages JARVIS into a single-file executable `dist/JARVIS.exe`.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def build_executable(
    onefile: bool = True,
    windowed: bool = False,
    clean: bool = True,
    distpath: str = "dist",
    buildpath: str = "build",
) -> int:
    """Run PyInstaller build for JARVIS."""
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(str(project_root))

    print(f"[*] Building JARVIS from root: {project_root}")

    # Check if pyinstaller is installed
    try:
        import PyInstaller
        print(f"[+] PyInstaller detected (version {PyInstaller.__version__})")
    except ImportError:
        print("[!] PyInstaller is not installed in the current environment.")
        print("[*] Installing PyInstaller via pip...")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=False)
        if res.returncode != 0:
            print("[X] Failed to install PyInstaller.")
            return res.returncode

    if clean:
        print("[*] Cleaning previous build artifacts...")
        shutil.rmtree(buildpath, ignore_errors=True)
        shutil.rmtree(distpath, ignore_errors=True)

    # Data files to include
    datas = [
        ("config", "config"),
        ("jarvis/skills", "jarvis/skills"),
    ]

    # Hidden imports
    hidden_imports = [
        "jarvis",
        "jarvis.cli",
        "jarvis.core.app",
        "jarvis.audio.engine",
        "jarvis.audio.wake_word",
        "jarvis.memory.manager",
        "jarvis.memory.sqlite_store",
        "jarvis.vision.screen",
        "jarvis.vision.computer_use",
        "jarvis.automation.control",
        "jarvis.automation.gui_actor",
        "jarvis.platform.windows",
        "jarvis.platform.hotkeys",
        "jarvis.platform.autostart",
        "jarvis.ui.overlay",
        "jarvis.ui.tray",
        "jarvis.ui.dashboard",
        "jarvis.planner.engine",
        "jarvis.sandbox.interpreter",
        "jarvis.skills.registry",
        "jarvis.browser.agent",
        "jarvis.proactive.engine",
        "sqlite3",
        "ctypes",
        "ctypes.wintypes",
        "tkinter",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=JARVIS",
        f"--distpath={distpath}",
        f"--workpath={buildpath}",
        "--noconfirm",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if windowed:
        cmd.append("--windowed")
    else:
        cmd.append("--console")

    for src, dst in datas:
        src_path = project_root / src
        if src_path.exists():
            cmd.extend(["--add-data", f"{src};{dst}"])

    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    entry_point = project_root / "jarvis" / "__main__.py"
    cmd.append(str(entry_point))

    print("[*] Running command:")
    print(" ".join(cmd))

    proc = subprocess.run(cmd)
    if proc.returncode == 0:
        exe_ext = ".exe" if sys.platform == "win32" else ""
        out_file = Path(distpath) / f"JARVIS{exe_ext}"
        print(f"\n========================================================")
        print(f"[SUCCESS] JARVIS executable created at: {out_file}")
        print(f"========================================================")
    else:
        print(f"\n[ERROR] PyInstaller build failed with returncode {proc.returncode}")

    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Build JARVIS Standalone Executable")
    parser.add_argument("--onefile", action="store_true", default=True, help="Build single-file executable")
    parser.add_argument("--onedir", action="store_false", dest="onefile", help="Build directory bundle")
    parser.add_argument("--windowed", action="store_true", default=False, help="Hide console window on startup")
    parser.add_argument("--no-clean", action="store_false", dest="clean", help="Do not clean build/dist folders")
    args = parser.parse_args()

    return build_executable(
        onefile=args.onefile,
        windowed=args.windowed,
        clean=args.clean,
    )


if __name__ == "__main__":
    sys.exit(main())
