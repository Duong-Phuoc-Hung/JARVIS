"""Local Windows application inventory. Never executes caller-supplied shell text."""

from __future__ import annotations

import json
import ntpath
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path, PureWindowsPath
from typing import Callable, Iterable

MAX_INVENTORY_ENTRIES = 4096
MAX_PACKAGE_ENTRIES = 8192
MAX_INVENTORY_JSON_BYTES = 8 * 1024 * 1024


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass(frozen=True)
class InstalledApp:
    name: str
    target: str
    kind: str  # exe or app_id
    executable: str = ""
    app_id: str = ""
    aliases: tuple[str, ...] = ()
    executable_shared: bool = False


def _merge_entries(first: InstalledApp, second: InstalledApp) -> InstalledApp:
    preferred = first
    if second.kind == "app_id" and (
        first.kind != "app_id" or (second.executable and not first.executable)
    ):
        preferred = second
    aliases = tuple(dict.fromkeys((first.name, second.name, *first.aliases, *second.aliases)))
    if len(aliases) > 64:
        raise ValueError("Application alias limit exceeded")
    return replace(preferred, aliases=aliases)


def _coalesce(entries: Iterable[InstalledApp]) -> tuple[InstalledApp, ...]:
    unique: dict[tuple[str, str], InstalledApp] = {}
    for index, entry in enumerate(entries):
        if index >= MAX_INVENTORY_ENTRIES:
            raise ValueError("Application inventory limit exceeded")
        if not _allowed(entry):
            continue
        target = ntpath.normcase(entry.target) if entry.kind == "exe" else entry.target
        identity = (entry.kind, target)
        previous = unique.get(identity)
        if previous is None:
            unique[identity] = entry
        elif previous != entry:
            unique[identity] = _merge_entries(previous, entry)
    stores_by_executable: dict[str, list[tuple[str, str]]] = {}
    for identity, entry in unique.items():
        if entry.kind == "app_id" and entry.executable:
            stores_by_executable.setdefault(ntpath.normcase(entry.executable), []).append(identity)
    for identity, entry in tuple(unique.items()):
        if entry.kind != "exe":
            continue
        stores = stores_by_executable.get(ntpath.normcase(entry.target), [])
        # Two AUMIDs may deliberately use the same host executable. Do not
        # collapse distinct packaged apps merely because their host is shared.
        if len(stores) == 1:
            store_identity = stores[0]
            unique[store_identity] = _merge_entries(unique[store_identity], entry)
            del unique[identity]
    return tuple(
        replace(entry, executable_shared=True)
        if len(
            stores_by_executable.get(
                ntpath.normcase(entry.executable or (entry.target if entry.kind == "exe" else "")),
                [],
            )
        )
        > 1
        else entry
        for entry in unique.values()
    )


def _maintenance_name(value: str) -> bool:
    words = re.sub(r"[_\-.]", " ", normalize_name(value))
    return bool(
        re.search(
            r"\b(unins\w*|updat(?:e|er)\w*|setup\w*|installer\w*|maintenancetool)\b|gỡ cài đặt",
            words,
        )
    )


def _safe_executable(value: str) -> bool:
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or any(c in value for c in '"<>|*?'):
        return False
    if value.startswith(("\\\\", "//")) or not value.lower().endswith(".exe"):
        return False
    windows_path = PureWindowsPath(value)
    if ".." in windows_path.parts or ":" in value[2:]:
        return False
    return Path(value).is_absolute() or bool(re.match(r"^[A-Za-z]:[\\/]", value))


def _safe_app_id(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 512:
        return False
    return bool(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._{}()-]*", value)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._{}-]*![A-Za-z0-9][A-Za-z0-9._-]*", value)
    )


def _safe_desktop_id(value: str, executable: str) -> bool:
    if not executable or not isinstance(value, str) or len(value) > 512:
        return False
    # Shell exposes some desktop app IDs relative to a known-folder GUID.
    # Accept this form only with an independently discovered executable.
    match = re.fullmatch(r"\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}\\(.+)", value)
    if not match:
        return False
    relative = match.group(1)
    return not PureWindowsPath(relative).anchor and _safe_executable("C:\\" + relative)


def _allowed(entry: InstalledApp) -> bool:
    if (
        not isinstance(entry, InstalledApp)
        or not isinstance(entry.name, str)
        or len(entry.name) > 256
    ):
        return False
    name = normalize_name(entry.name)
    if not name or _maintenance_name(name):
        return False
    if entry.kind not in {"exe", "app_id"} or not isinstance(entry.target, str):
        return False
    if entry.executable and (
        not _safe_executable(entry.executable)
        or _maintenance_name(PureWindowsPath(entry.executable).stem)
    ):
        return False
    if entry.app_id and (
        not (_safe_app_id(entry.app_id) or _safe_desktop_id(entry.app_id, entry.executable))
        or (entry.kind == "app_id" and entry.app_id != entry.target)
    ):
        return False
    if (
        not isinstance(entry.aliases, tuple)
        or len(entry.aliases) > 64
        or any(not isinstance(alias, str) or len(alias) > 256 for alias in entry.aliases)
    ):
        return False
    if entry.kind == "exe":
        return (
            _safe_executable(entry.target)
            and not _maintenance_name(PureWindowsPath(entry.target).stem)
            and (
                not entry.executable
                or ntpath.normcase(entry.executable) == ntpath.normcase(entry.target)
            )
        )
    return _safe_app_id(entry.target) or _safe_desktop_id(entry.target, entry.executable)


def _manifest_executable(location: str, relative: str) -> str:
    root = Path(location)
    relative_path = PureWindowsPath(relative)
    if relative_path.anchor or ".." in relative_path.parts:
        return ""
    executable = root.joinpath(*relative_path.parts)
    if not _safe_executable(str(executable)):
        return ""
    try:
        if executable.is_file():
            executable.resolve().relative_to(root.resolve())
            return str(executable)
    except (OSError, ValueError):
        pass
    return ""


def discover_windows_apps() -> Iterable[InstalledApp]:
    """Read current-user Start applications and per-user/machine App Paths.

    Start apps and registry are required sources. Package manifests supply
    optional executable identity: missing metadata never invents an identity
    or removes the app's known AUMID. No inventory leaves this process.
    """
    if sys.platform != "win32":
        raise OSError("Windows application discovery unavailable")
    import winreg

    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    script = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "$startApps=@(Get-StartApps | Select-Object -First 4097 Name,AppID); "
        "if ($startApps.Count -gt 4096) { throw 'Start app inventory limit exceeded' }; "
        "$packageApps=[System.Collections.Generic.List[object]]::new(); $metadataErrors=0; "
        "try { $packages=@(Get-AppxPackage | Select-Object -First 4097); "
        "if ($packages.Count -gt 4096) { throw 'Package inventory limit exceeded' }; "
        "foreach ($package in $packages) { try { "
        "$manifest=Get-AppxPackageManifest -Package $package; "
        "foreach ($application in @($manifest.Package.Applications.Application)) { "
        "if ($application.Id -and $application.Executable) { "
        "if ($packageApps.Count -ge 8192) { throw 'Package app inventory limit exceeded' }; "
        "$packageApps.Add([pscustomobject]@{ "
        "AppID=([string]$package.PackageFamilyName+'!'+[string]$application.Id); "
        "InstallLocation=[string]$package.InstallLocation; "
        "Executable=[string]$application.Executable }) } } "
        "} catch { $metadataErrors++ } } } catch { $metadataErrors++ }; "
        "$desktopApps=[System.Collections.Generic.List[object]]::new(); "
        "try { $shell=New-Object -ComObject Shell.Application; "
        "$folder=$shell.NameSpace('shell:AppsFolder'); "
        "$items=@($folder.Items() | Select-Object -First 4097); "
        "if ($items.Count -gt 4096) { throw 'Shell app inventory limit exceeded' }; "
        "foreach ($item in $items) { try { "
        "$desktopApps.Add([pscustomobject]@{ "
        "AppID=[string]$item.ExtendedProperty('System.AppUserModel.ID'); "
        "Executable=[string]$item.ExtendedProperty('System.Link.TargetParsingPath') }); "
        "} catch { $metadataErrors++ } } } catch { $metadataErrors++ }; "
        "ConvertTo-Json -Depth 5 -Compress -InputObject @{ "
        "StartApps=$startApps; PackageApps=$packageApps; DesktopApps=$desktopApps; MetadataErrors=$metadataErrors }"
    )
    completed = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
        creationflags=subprocess.CREATE_NO_WINDOW,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )
    if len(completed.stdout.encode("utf-8")) > MAX_INVENTORY_JSON_BYTES:
        raise ValueError("Application inventory output limit exceeded")
    inventory = json.loads(completed.stdout.lstrip("\ufeff"))
    if not isinstance(inventory, dict):
        raise ValueError("Invalid application inventory")
    rows = inventory.get("StartApps")
    if not isinstance(rows, list) or len(rows) > MAX_INVENTORY_ENTRIES:
        raise ValueError("Invalid Start application inventory")
    executable_by_app_id: dict[str, dict[str, str]] = {}
    package_rows = inventory.get("PackageApps", [])
    if not isinstance(package_rows, list) or len(package_rows) > MAX_PACKAGE_ENTRIES:
        raise ValueError("Invalid package application inventory")
    for row in package_rows:
        if not isinstance(row, dict):
            continue
        app_id, location, relative = (
            row.get(key) for key in ("AppID", "InstallLocation", "Executable")
        )
        if not all(isinstance(value, str) and value for value in (app_id, location, relative)):
            continue
        if not _safe_app_id(app_id):
            continue
        executable = _manifest_executable(location, relative)
        if executable:
            executable_by_app_id.setdefault(app_id, {})[ntpath.normcase(executable)] = executable
    desktop_rows = inventory.get("DesktopApps", [])
    if not isinstance(desktop_rows, list) or len(desktop_rows) > MAX_INVENTORY_ENTRIES:
        raise ValueError("Invalid desktop application inventory")
    for row in desktop_rows:
        if not isinstance(row, dict):
            continue
        app_id, executable = row.get("AppID"), row.get("Executable")
        if not _safe_executable(executable):
            continue
        if not (_safe_app_id(app_id) or _safe_desktop_id(app_id, executable)):
            continue
        try:
            if Path(executable).is_file():
                executable_by_app_id.setdefault(app_id, {})[ntpath.normcase(executable)] = (
                    executable
                )
        except OSError:
            continue
    for row in rows:
        if (
            isinstance(row, dict)
            and isinstance(row.get("Name"), str)
            and isinstance(row.get("AppID"), str)
        ):
            app_id = row["AppID"]
            if _safe_executable(app_id):
                if Path(app_id).is_file():
                    entry = InstalledApp(
                        row["Name"], app_id, "exe", executable=app_id, aliases=(Path(app_id).stem,)
                    )
                    if _allowed(entry):
                        yield entry
                continue
            candidates = executable_by_app_id.get(app_id, {})
            executable = next(iter(candidates.values())) if len(candidates) == 1 else ""
            entry = InstalledApp(
                row["Name"],
                app_id,
                "app_id",
                executable=executable,
                app_id=app_id,
                aliases=(Path(executable).stem,) if executable else (),
            )
            if _allowed(entry):
                yield entry

    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                root = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view)
            except FileNotFoundError:
                continue
            with root:
                count = winreg.QueryInfoKey(root)[0]
                if count > MAX_INVENTORY_ENTRIES:
                    raise ValueError("Registry app inventory limit exceeded")
                for index in range(count):
                    key_name = winreg.EnumKey(root, index)
                    try:
                        with winreg.OpenKey(root, key_name) as child:
                            value, value_type = winreg.QueryValueEx(child, "")
                    except FileNotFoundError:
                        continue
                    if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(
                        value, str
                    ):
                        continue
                    target = os.path.expandvars(value).strip().strip('"')
                    entry = InstalledApp(Path(key_name).stem, target, "exe", executable=target)
                    if _allowed(entry) and Path(target).is_file():
                        yield entry


class ApplicationCatalog:
    """Thread-safe TTL cache; exact matches only, ambiguity is never guessed."""

    def __init__(
        self, provider: Callable[[], Iterable[InstalledApp]] | None = None, ttl: float = 300
    ) -> None:
        self._provider = provider or discover_windows_apps
        self._ttl = ttl
        self._lock = threading.RLock()
        self._updated: float | None = None
        self._entries: tuple[InstalledApp, ...] = ()
        self.errors: tuple[str, ...] = ()

    def refresh(self) -> tuple[InstalledApp, ...]:
        with self._lock:
            try:
                self._entries = _coalesce(self._provider())
                self.errors = ()
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                self._entries = ()
                self.errors = (type(exc).__name__,)
            self._updated = time.monotonic()
            return self._entries

    def resolve(self, name: str) -> tuple[InstalledApp, ...]:
        with self._lock:
            if self._updated is None or time.monotonic() - self._updated >= self._ttl:
                self.refresh()
            query = normalize_name(name)
            return tuple(
                entry
                for entry in self._entries
                if query in {normalize_name(value) for value in (entry.name, *entry.aliases)}
            )
