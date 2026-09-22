"""Installed app identity through the public discovery and catalog seams."""

import json
from types import SimpleNamespace

import pytest

from jarvis.automation import app_catalog
from jarvis.automation.app_catalog import ApplicationCatalog, InstalledApp


def test_store_and_registry_entries_share_executable_identity_and_aliases(tmp_path):
    executable = str(tmp_path / "Editor.exe")
    store = InstalledApp(
        "Friendly Editor",
        "Vendor.Editor!App",
        "app_id",
        executable=executable,
        app_id="Vendor.Editor!App",
    )
    registry = InstalledApp("editor", executable, "exe")
    catalog = ApplicationCatalog(provider=lambda: [registry, store])

    assert len(catalog.refresh()) == 1
    resolved = catalog.resolve("Friendly Editor")
    assert len(resolved) == 1
    assert resolved[0].target == "Vendor.Editor!App"
    assert resolved[0].executable == executable
    assert catalog.resolve("EDITOR") == resolved


@pytest.fixture
def discover_inventory(monkeypatch):
    def missing_registry(*args):
        raise FileNotFoundError

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        HKEY_LOCAL_MACHINE=2,
        KEY_WOW64_64KEY=4,
        KEY_WOW64_32KEY=8,
        KEY_READ=16,
        OpenKey=missing_registry,
    )
    monkeypatch.setitem(app_catalog.sys.modules, "winreg", registry)
    monkeypatch.setattr(app_catalog.sys, "platform", "win32")
    monkeypatch.setattr(app_catalog.subprocess, "CREATE_NO_WINDOW", 0, raising=False)

    def discover(payload):
        monkeypatch.setattr(
            app_catalog.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
        )
        return tuple(app_catalog.discover_windows_apps())

    return discover


def test_discovery_joins_exact_package_application_and_exposes_executable(
    tmp_path, discover_inventory
):
    executable = tmp_path / "Editor.exe"
    executable.touch()
    payload = {
        "StartApps": [{"Name": "Friendly Editor", "AppID": "Vendor.Editor!Second"}],
        "PackageApps": [
            {
                "AppID": "Vendor.Editor!First",
                "InstallLocation": str(tmp_path),
                "Executable": "Other.exe",
            },
            {
                "AppID": "Vendor.Editor!Second",
                "InstallLocation": str(tmp_path),
                "Executable": "Editor.exe",
            },
        ],
    }

    entries = discover_inventory(payload)
    assert len(entries) == 1
    assert entries[0].app_id == "Vendor.Editor!Second"
    assert entries[0].executable == str(executable)
    catalog = ApplicationCatalog(provider=lambda: entries)
    assert catalog.resolve("editor") == entries


@pytest.mark.parametrize(
    "target",
    [
        "shell:AppsFolder\\Vendor.Editor!App",
        "Vendor.Editor!App;calc",
        "Vendor!One!Two",
        "Vendor.Editor!App\\child",
        "Vendor.Editor!App\x7f",
        "x" * 513,
    ],
)
def test_unsafe_application_ids_are_not_launchable(target):
    catalog = ApplicationCatalog(provider=lambda: [InstalledApp("Editor", target, "app_id")])
    assert catalog.refresh() == ()


@pytest.mark.parametrize("stem", ["unins000", "setup", "Update", "Editor_Updater"])
def test_maintenance_executable_cannot_hide_behind_friendly_name(tmp_path, stem):
    target = str(tmp_path / f"{stem}.exe")
    catalog = ApplicationCatalog(provider=lambda: [InstalledApp("Friendly Editor", target, "exe")])
    assert catalog.refresh() == ()


@pytest.mark.parametrize(
    "target",
    [r"\\server\share\Editor.exe", r"C:\safe\..\Editor.exe", r"C:\safe\Editor.exe:payload.exe"],
)
def test_unsafe_executable_paths_are_not_launchable(target):
    catalog = ApplicationCatalog(provider=lambda: [InstalledApp("Editor", target, "exe")])
    assert catalog.refresh() == ()


def test_distinct_store_ids_sharing_host_executable_remain_ambiguous(tmp_path):
    executable = str(tmp_path / "SharedHost.exe")
    entries = [
        InstalledApp("Editor", "Vendor.Editor!One", "app_id", executable=executable),
        InstalledApp("Editor", "Vendor.Editor!Two", "app_id", executable=executable),
    ]
    catalog = ApplicationCatalog(provider=lambda: entries)
    resolved = catalog.resolve("Editor")
    assert [entry.target for entry in resolved] == ["Vendor.Editor!One", "Vendor.Editor!Two"]
    assert all(entry.executable_shared for entry in resolved)


def test_names_and_executable_stems_do_not_merge_different_paths(tmp_path):
    entries = [
        InstalledApp("Editor", str(tmp_path / "one" / "Editor.exe"), "exe"),
        InstalledApp("Editor", str(tmp_path / "two" / "Editor.exe"), "exe"),
    ]
    catalog = ApplicationCatalog(provider=lambda: entries)
    assert catalog.resolve("Editor") == tuple(entries)


def test_start_app_filesystem_target_is_a_desktop_executable(tmp_path, discover_inventory):
    executable = tmp_path / "Editor.exe"
    executable.touch()
    entries = discover_inventory(
        {
            "StartApps": [{"Name": "Friendly Editor", "AppID": str(executable)}],
            "PackageApps": [],
        }
    )
    assert entries == (
        InstalledApp(
            "Friendly Editor",
            str(executable),
            "exe",
            executable=str(executable),
            aliases=("Editor",),
        ),
    )


@pytest.mark.parametrize("relative", ["..\\Outside.exe", "missing.exe"])
def test_untrusted_manifest_paths_never_become_launch_identity(
    tmp_path, discover_inventory, relative
):
    package = tmp_path / "package"
    package.mkdir()
    (tmp_path / "Outside.exe").touch()
    entries = discover_inventory(
        {
            "StartApps": [{"Name": "Editor", "AppID": "Vendor.Editor!App"}],
            "PackageApps": [
                {
                    "AppID": "Vendor.Editor!App",
                    "InstallLocation": str(package),
                    "Executable": relative,
                }
            ],
        }
    )
    assert len(entries) == 1
    assert entries[0].executable == ""
    assert entries[0].app_id == "Vendor.Editor!App"


def test_unavailable_optional_metadata_keeps_known_aumid_without_inventing_executable(
    discover_inventory,
):
    entries = discover_inventory(
        {
            "StartApps": [{"Name": "Editor", "AppID": "Vendor.Editor!App"}],
            "PackageApps": [],
            "MetadataErrors": 1,
        }
    )
    assert entries == (
        InstalledApp("Editor", "Vendor.Editor!App", "app_id", app_id="Vendor.Editor!App"),
    )


def test_conflicting_manifest_identity_does_not_guess_executable(tmp_path, discover_inventory):
    for name in ("One.exe", "Two.exe"):
        (tmp_path / name).touch()
    entries = discover_inventory(
        {
            "StartApps": [{"Name": "Editor", "AppID": "Vendor.Editor!App"}],
            "PackageApps": [
                {"AppID": "Vendor.Editor!App", "InstallLocation": str(tmp_path), "Executable": name}
                for name in ("One.exe", "Two.exe")
            ],
        }
    )
    assert entries[0].executable == ""


def test_inventory_limit_fails_closed_instead_of_silently_truncating():
    entry = InstalledApp("Editor", "Vendor.Editor!App", "app_id")
    catalog = ApplicationCatalog(provider=lambda: (entry for _ in range(5000)))
    assert catalog.refresh() == ()
    assert catalog.errors == ("ValueError",)


def test_required_discovery_source_failure_discards_partial_inventory(
    monkeypatch, discover_inventory
):
    def denied(*args):
        raise PermissionError("Registry unavailable")

    monkeypatch.setattr(app_catalog.sys.modules["winreg"], "OpenKey", denied)
    catalog = ApplicationCatalog(
        provider=lambda: discover_inventory(
            {
                "StartApps": [{"Name": "Editor", "AppID": "Vendor.Editor!App"}],
                "PackageApps": [],
            }
        )
    )
    assert catalog.refresh() == ()
    assert catalog.errors == ("PermissionError",)


def test_catalog_rejects_mismatched_executable_identity(tmp_path):
    catalog = ApplicationCatalog(
        provider=lambda: [
            InstalledApp(
                "Editor",
                str(tmp_path / "Editor.exe"),
                "exe",
                executable=str(tmp_path / "Other.exe"),
            )
        ]
    )
    assert catalog.refresh() == ()


def test_desktop_shell_metadata_preserves_launch_identity_and_exact_executable(
    tmp_path, discover_inventory
):
    executable = tmp_path / "Editor.exe"
    executable.touch()
    app_id = r"{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}\Vendor Editor\Editor.exe"
    entries = discover_inventory(
        {
            "StartApps": [{"Name": "Friendly Editor", "AppID": app_id}],
            "DesktopApps": [{"AppID": app_id, "Executable": str(executable)}],
            "PackageApps": [],
        }
    )
    assert len(entries) == 1
    assert entries[0].kind == "app_id"
    assert entries[0].target == app_id
    assert entries[0].app_id == app_id
    assert entries[0].executable == str(executable)


def test_desktop_shell_metadata_never_matches_by_display_name(tmp_path, discover_inventory):
    executable = tmp_path / "Editor.exe"
    executable.touch()
    entries = discover_inventory(
        {
            "StartApps": [{"Name": "Editor", "AppID": "Vendor.Editor.One"}],
            "DesktopApps": [
                {"Name": "Editor", "AppID": "Vendor.Editor.Two", "Executable": str(executable)}
            ],
            "PackageApps": [],
        }
    )
    assert entries[0].executable == ""


def test_plain_desktop_app_ids_can_include_spaces():
    entry = InstalledApp("Video Meeting", "Vendor Video Meetings", "app_id")
    catalog = ApplicationCatalog(provider=lambda: [entry])
    assert catalog.resolve("Video Meeting") == (entry,)


def test_desktop_profile_and_registry_entries_with_shared_executable_cannot_verify_by_path(
    tmp_path,
):
    executable = str(tmp_path / "Browser.exe")
    entries = [
        InstalledApp("Personal Browser", "Browser.Personal", "app_id", executable=executable),
        InstalledApp("Work Browser", "Browser.Work", "app_id", executable=executable),
        InstalledApp("Browser", executable, "exe"),
    ]
    catalog = ApplicationCatalog(provider=lambda: entries)
    resolved = catalog.refresh()
    assert len(resolved) == 3
    assert all(entry.executable_shared for entry in resolved)
