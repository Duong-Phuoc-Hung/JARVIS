#!/usr/bin/env python3
"""
scripts/build_installer.py
============================
Build JARVIS thành .EXE + Windows Installer một lần duy nhất.

Chạy:
  python scripts/build_installer.py            # Build .exe + installer
  python scripts/build_installer.py --exe-only # Chỉ build .exe
  python scripts/build_installer.py --check    # Kiểm tra môi trường

Sau khi build:
  dist/JARVIS.exe                     ← File chạy trực tiếp
  dist/installer/JARVIS_Setup_*.exe  ← File cài đặt (nếu có Inno Setup)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC_FILE = ROOT / "JARVIS.spec"
ICON_FILE = ROOT / "assets" / "jarvis_icon.ico"
INNO_EXE_PATHS = [
    Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    Path("C:/Program Files (x86)/Inno Setup 5/ISCC.exe"),
]


def check_environment() -> bool:
    """Check all build requirements."""
    print("🔍 Kiểm tra môi trường build...")
    ok = True

    # Python
    ver = sys.version_info
    if ver >= (3, 10):
        print(f"  ✅ Python {ver.major}.{ver.minor}.{ver.micro}")
    else:
        print(f"  ❌ Python {ver.major}.{ver.minor} — cần >= 3.10")
        ok = False

    # PyInstaller
    try:
        import PyInstaller  # type: ignore[import]  # noqa: F401
        print(f"  ✅ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  ❌ PyInstaller không tìm thấy — chạy: pip install pyinstaller")
        ok = False

    # Assets
    if ICON_FILE.exists():
        print(f"  ✅ Icon: {ICON_FILE.name}")
    else:
        print(f"  ⚠️  Icon không tìm thấy: {ICON_FILE} (sẽ dùng icon mặc định)")

    # Inno Setup
    inno = _find_inno()
    if inno:
        print(f"  ✅ Inno Setup: {inno}")
    else:
        print("  ⚠️  Inno Setup không tìm thấy — installer sẽ không được tạo")
        print("     Tải tại: https://jrsoftware.org/isdl.php")

    return ok


def _find_inno() -> Path | None:
    for p in INNO_EXE_PATHS:
        if p.exists():
            return p
    return None


def _get_canonical_version() -> str:
    """
    Read the canonical JARVIS version (jarvis.__version__) without importing
    the jarvis package -- this is a build-tool script and should not need
    jarvis's own runtime dependencies installed just to read a version
    string. Mirrors the same raw-text-scan pattern already used by
    jarvis/workers/auto_updater.py::get_current_version() and
    scripts/health_check_report.py::get_version() for the same reason.
    """
    init_path = ROOT / "jarvis" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("__version__") and "=" in stripped:
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"Could not locate a __version__ literal in {init_path}")


def build_exe(clean: bool = True) -> bool:
    """Build JARVIS.exe using PyInstaller."""
    print("\n🏗️  Building JARVIS.exe...")

    if clean and BUILD.exists():
        shutil.rmtree(BUILD)
        print("  🧹 Build cache cleared")

    # Always regenerate the spec file so a stale entry point or data path
    # (e.g. from a cached checkout or an older version of this script) can
    # never silently linger across builds.
    _generate_spec_file()

    _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC_FILE), "--noconfirm"],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=_cflags,
    )
    if result.returncode != 0:
        print("  ❌ PyInstaller thất bại!")
        return False

    exe = DIST / "JARVIS.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"  ✅ JARVIS.exe tạo thành công ({size_mb:.1f} MB)")
        return True
    print("  ❌ JARVIS.exe không tìm thấy sau khi build")
    return False


def _generate_spec_file() -> None:
    """
    (Re)generate JARVIS.spec, always overwriting any existing file so a stale
    entry point or data path can never silently linger across builds.
    """
    entry_point = ROOT / "jarvis" / "__main__.py"
    if not entry_point.exists():
        raise FileNotFoundError(
            f"JARVIS entry point not found: {entry_point} "
            "(expected the package's __main__.py, matching pyproject.toml's "
            "[project.scripts] jarvis = \"jarvis.__main__:main\")"
        )

    icon_arg = repr(str(ICON_FILE)) if ICON_FILE.exists() else "None"

    # Data files are collected by absolute path so the spec behaves
    # identically regardless of the working directory it's invoked from.
    # "assets/" is optional — only reference it if it actually exists,
    # since PyInstaller raises a fatal SystemExit for any non-glob datas
    # source path that doesn't exist on disk.
    datas: list[str] = [
        f"({repr(str(ROOT / 'jarvis' / 'skills' / '*' / 'metadata.json'))}, 'jarvis/skills')",
    ]
    if (ROOT / "assets").is_dir():
        datas.append(f"({repr(str(ROOT / 'assets'))}, 'assets')")
    datas_block = ",\n        ".join(datas)

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# JARVIS.spec — PyInstaller Spec File (tự sinh bởi build_installer.py)
# Regenerated on every build — do not hand-edit, changes will be overwritten.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = (
    collect_submodules("jarvis") +
    collect_submodules("jarvis.skills") +
    collect_submodules("jarvis.comms") +
    collect_submodules("jarvis.audio") +
    collect_submodules("jarvis.memory") +
    collect_submodules("jarvis.workers") +
    collect_submodules("jarvis.browser") +
    collect_submodules("jarvis.plugins") +
    collect_submodules("jarvis.agent") +
    ["pystray", "PIL", "win32api", "win32con", "win32gui",
     "ctypes", "json", "sqlite3", "threading", "pathlib"]
)

a = Analysis(
    [{repr(str(entry_point))}],
    pathex=[{repr(str(ROOT))}],
    binaries=[],
    datas=[
        {datas_block}
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    # NOTE: tkinter must NOT be excluded — jarvis.ui.overlay and
    # jarvis.skills.clipboard import it unconditionally at module level,
    # so excluding it produces an exe that crashes with ModuleNotFoundError
    # as soon as either module loads.
    excludes=["matplotlib", "scipy", "numpy.testing"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # No console window — chạy ngầm!
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_arg},
    version_file=None,
)
'''
    SPEC_FILE.write_text(spec_content, encoding="utf-8")
    print("  📄 JARVIS.spec generated")


def build_installer() -> bool:
    """Build Windows Setup .exe using Inno Setup."""
    inno = _find_inno()
    if not inno:
        print("\n⚠️  Inno Setup không tìm thấy — bỏ qua bước tạo installer")
        print("   Tải tại: https://jrsoftware.org/isdl.php")
        return False

    setup_iss = ROOT / "installer" / "setup.iss"
    if not setup_iss.exists():
        print(f"  ❌ {setup_iss} không tồn tại")
        return False

    version = _get_canonical_version()
    print(f"\n📦 Building Windows Installer (AppVersion={version})...")
    _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [str(inno), f"/DAppVersion={version}", str(setup_iss)],
        cwd=ROOT,
        creationflags=_cflags,
    )
    if result.returncode != 0:
        print("  ❌ Inno Setup thất bại!")
        return False

    installers = list((DIST / "installer").glob("JARVIS_Setup_*.exe"))
    if installers:
        f = installers[-1]
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"  ✅ Installer: {f.name} ({size_mb:.1f} MB)")
        return True

    print("  ❌ Installer không tìm thấy")
    return False


def run_tests() -> bool:
    """Run test suite before building."""
    print("\n🧪 Chạy test suite trước khi build...")
    _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/unit/", "-q", "--tb=no", "--no-header", "-rN"],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "JARVIS_MOCK_AUDIO": "1"},
        creationflags=_cflags,
    )
    if result.returncode == 0:
        print("  ✅ Tất cả tests pass!")
        return True
    print("  ❌ Tests thất bại — dừng build!")
    return False


def print_summary(exe_ok: bool, installer_ok: bool) -> None:
    print("\n" + "=" * 55)
    print("📊 KẾT QUẢ BUILD JARVIS")
    print("=" * 55)
    print(f"  JARVIS.exe:      {'✅ OK' if exe_ok else '❌ FAILED'}")
    print(f"  Windows Setup:   {'✅ OK' if installer_ok else '⚠️  Skipped/Failed'}")
    if exe_ok:
        exe = DIST / "JARVIS.exe"
        print(f"\n  📂 File exe: {exe}")
        print(f"  💡 Chạy thử: {exe} --tray")
    print("=" * 55)


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS Build Tool")
    parser.add_argument("--exe-only", action="store_true", help="Chỉ build .exe, không tạo installer")
    parser.add_argument("--installer-only", action="store_true", help="Chỉ build installer")
    parser.add_argument("--check", action="store_true", help="Kiểm tra môi trường build")
    parser.add_argument("--skip-tests", action="store_true", help="Bỏ qua test suite")
    parser.add_argument("--no-clean", action="store_true", help="Không xóa build cache")
    args = parser.parse_args()

    print("🤖 JARVIS Build Tool — Windows Standalone Package")
    print("=" * 55)

    if args.check:
        ok = check_environment()
        sys.exit(0 if ok else 1)

    if not args.skip_tests:
        if not run_tests():
            sys.exit(1)

    exe_ok = False
    installer_ok = False

    if not args.installer_only:
        exe_ok = build_exe(clean=not args.no_clean)

    if not args.exe_only:
        installer_ok = build_installer()

    print_summary(exe_ok, installer_ok)
    sys.exit(0 if exe_ok else 1)


if __name__ == "__main__":
    main()
