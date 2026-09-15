"""Atomic persistence and fail-closed tests for browser sessions."""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jarvis.browser.session as session_module
from jarvis.browser.driver import MockBrowserDriver
from jarvis.browser.models import BrowserResultStatus
from jarvis.browser.session import BrowserSessionManager


def test_save_session_retries_transient_windows_replace_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    target_path = storage_dir / "example.com.json"
    original_replace = Path.replace
    replace_sources: list[Path] = []

    def flaky_replace(source: Path, target: Path) -> Path:
        if target == target_path:
            replace_sources.append(source)
            if len(replace_sources) == 1:
                raise PermissionError(5, "Access is denied")
            if len(replace_sources) == 2:
                windows_error = OSError("Access is denied")
                windows_error.winerror = 5  # type: ignore[attr-defined]
                raise windows_error
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    assert manager.save_session("example.com", [{"name": "sid", "value": "fresh"}]) is True

    assert len(replace_sources) == 3
    assert len(set(replace_sources)) == 1
    temp_name = replace_sources[0].name
    assert f".tmp.{threading.get_ident()}." in temp_name
    assert temp_name.rsplit(".", 1)[-1].isdigit()
    assert json.loads(target_path.read_text(encoding="utf-8"))["cookies"] == [
        {"name": "sid", "value": "fresh"}
    ]


def test_save_session_fails_closed_when_configured_sqlite_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(
        storage_dir=str(storage_dir),
        db_path=str(tmp_path / "sessions.db"),
    )

    def unavailable_database(*args, **kwargs):
        raise sqlite3.OperationalError("database is unavailable")

    monkeypatch.setattr(session_module.sqlite3, "connect", unavailable_database)

    assert manager.save_session("example.com", [{"name": "sid", "value": "fresh"}]) is False
    assert json.loads((storage_dir / "example.com.json").read_text(encoding="utf-8"))[
        "cookies"
    ] == [{"name": "sid", "value": "fresh"}]


def test_domain_path_traversal_cannot_escape_session_storage(tmp_path: Path) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    cookies = [{"name": "sid", "value": "safe"}]
    outside_path = tmp_path / "escaped.json"

    assert manager.save_session("../escaped", cookies) is True

    assert outside_path.exists() is False
    session_keys = manager.list_sessions()
    assert len(session_keys) == 1
    assert "/" not in session_keys[0]
    assert "\\" not in session_keys[0]
    assert manager.load_session("../escaped")["cookies"] == cookies
    assert all(path.parent == storage_dir for path in storage_dir.iterdir())


def test_normalize_domain_preserves_leading_dot_cookie_domain(tmp_path: Path) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    cookies = [{"name": "sid", "value": "compatible"}]

    assert manager.save_session(".example.com", cookies) is True

    assert manager.list_sessions() == [".example.com"]
    assert manager.load_session(".example.com")["cookies"] == cookies


def test_permanent_replace_failure_preserves_previous_json_and_cleans_temp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    target_path = storage_dir / "example.com.json"
    assert manager.save_session("example.com", [{"name": "sid", "value": "old"}]) is True

    replace_sources: list[Path] = []
    delays: list[float] = []

    def denied_replace(source: Path, target: Path) -> Path:
        replace_sources.append(source)
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(Path, "replace", denied_replace)
    monkeypatch.setattr(session_module.time, "sleep", delays.append)

    assert manager.save_session("example.com", [{"name": "sid", "value": "new"}]) is False

    assert len(replace_sources) == 5
    assert delays == [0.02 * attempt for attempt in range(1, 5)]
    assert json.loads(target_path.read_text(encoding="utf-8"))["cookies"] == [
        {"name": "sid", "value": "old"}
    ]
    assert list(storage_dir.glob("*.tmp.*")) == []


def test_concurrent_saves_for_same_domain_leave_valid_complete_json(tmp_path: Path) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    worker_count = 16
    start = threading.Barrier(worker_count)

    def save(worker_id: int) -> bool:
        start.wait(timeout=5)
        return manager.save_session(
            "example.com",
            [{"name": "sid", "value": f"worker-{worker_id}", "padding": "x" * 20_000}],
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(save, range(worker_count)))

    assert all(results)
    payload = json.loads((storage_dir / "example.com.json").read_text(encoding="utf-8"))
    assert payload["domain"] == "example.com"
    assert payload["cookies"][0]["value"] in {
        f"worker-{worker_id}" for worker_id in range(worker_count)
    }
    assert payload["cookies"][0]["padding"] == "x" * 20_000
    assert list(storage_dir.glob("*.tmp.*")) == []


def test_json_and_sqlite_use_the_same_input_snapshot(tmp_path: Path, monkeypatch) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(
        storage_dir=str(storage_dir),
        db_path=str(tmp_path / "sessions.db"),
    )
    cookies = [{"name": "sid", "value": "before"}]
    local_storage = {"theme": "dark"}
    target_path = storage_dir / "example.com.json"
    original_replace = Path.replace

    def mutate_inputs_after_json_replace(source: Path, target: Path) -> Path:
        replaced = original_replace(source, target)
        if target == target_path:
            cookies[0]["value"] = "after"
            local_storage["theme"] = "light"
        return replaced

    monkeypatch.setattr(Path, "replace", mutate_inputs_after_json_replace)

    assert manager.save_session("example.com", cookies, local_storage) is True
    assert json.loads(target_path.read_text(encoding="utf-8"))["cookies"][0]["value"] == "before"

    target_path.unlink()
    sqlite_payload = manager.load_session("example.com")
    assert sqlite_payload["cookies"][0]["value"] == "before"
    assert sqlite_payload["local_storage"] == {"theme": "dark"}


def test_legacy_sqlite_session_with_unknown_origin_withholds_local_storage(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-sessions.db"
    cookie = {
        "name": "legacy-cookie",
        "value": "still-compatible",
        "domain": "example.test",
        "path": "/",
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE browser_sessions (
                domain TEXT PRIMARY KEY,
                cookies_json TEXT NOT NULL,
                local_storage_json TEXT NOT NULL DEFAULT '{}',
                user_agent TEXT NOT NULL DEFAULT '',
                updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO browser_sessions (
                domain, cookies_json, local_storage_json, user_agent
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "example.test",
                json.dumps([cookie]),
                json.dumps({"legacy-secret": "origin-unknown"}),
                "legacy-agent",
            ),
        )

    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(db_path),
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Target origin</body></html>",
        url="https://example.test/private",
    )
    driver.action_log.clear()

    assert manager.apply_to_driver(driver, "https://example.test/private") is False
    assert driver.get_cookies() == [cookie]
    assert not any(
        entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
        for entry in driver.action_log
    )


def test_apply_session_to_closed_driver_fails_without_mutating_driver(tmp_path: Path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    assert manager.save_session(
        "example.com",
        [{"name": "sid", "value": "stored", "domain": "example.com"}],
    )
    driver = MockBrowserDriver()

    assert manager.apply_to_driver(driver, "https://example.com/private") is False
    assert driver.get_cookies() == []


def test_delete_session_reports_configured_sqlite_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    assert manager.save_session("example.com", []) is True

    def unavailable_database(*args, **kwargs):
        raise sqlite3.OperationalError("database is unavailable")

    monkeypatch.setattr(session_module.sqlite3, "connect", unavailable_database)

    assert manager.delete_session("example.com") is False


def test_capture_session_fails_when_cookie_read_fails(tmp_path: Path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    driver = MockBrowserDriver()
    assert driver.launch() is True

    def fail_cookie_read():
        driver._record_failure(
            BrowserResultStatus.DISCONNECTED,
            "BROWSER_DISCONNECTED",
            "The browser session is disconnected.",
        )
        return []

    driver.get_cookies = fail_cookie_read  # type: ignore[method-assign]

    assert manager.capture_from_driver(driver, "example.com") is False
    assert manager.load_session("example.com") is None


def test_valid_json_with_wrong_session_types_fails_closed(tmp_path: Path) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    (storage_dir / "example.test.json").write_text(
        json.dumps(
            {
                "domain": "example.test",
                "cookies": [],
                "local_storage": ["not", "a", "mapping"],
                "local_storage_origin": "https://example.test:443",
                "user_agent": "test-agent",
            }
        ),
        encoding="utf-8",
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Target</body></html>",
        url="https://example.test/private",
    )

    assert manager.load_session("https://example.test/private") is None
    assert (
        manager.apply_to_driver(
            driver,
            "https://example.test/private",
        )
        is False
    )


def test_persisted_cookie_without_required_identity_fails_closed(tmp_path: Path) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    (storage_dir / "example.test.json").write_text(
        json.dumps(
            {
                "domain": "example.test",
                "cookies": [{}],
                "local_storage": {},
                "local_storage_origin": "",
                "user_agent": "test-agent",
            }
        ),
        encoding="utf-8",
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True

    assert manager.load_session("example.test") is None
    assert manager.apply_to_driver(driver, "example.test") is False
    assert driver.get_cookies() == []


def test_invalid_cookie_payload_is_rejected_before_overwriting_session(
    tmp_path: Path,
) -> None:
    storage_dir = tmp_path / "sessions"
    manager = BrowserSessionManager(storage_dir=str(storage_dir), db_path="")
    valid_cookie = {
        "name": "sid",
        "value": "preserved",
        "domain": "example.test",
        "path": "/",
    }
    assert manager.save_session("example.test", [valid_cookie]) is True
    target = storage_dir / "example.test.json"
    previous = target.read_bytes()

    assert manager.save_session("example.test", [{}]) is False

    assert target.read_bytes() == previous
    assert manager.load_session("example.test")["cookies"] == [valid_cookie]


def test_capture_session_fails_when_local_storage_read_fails(tmp_path: Path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    driver = MockBrowserDriver()
    assert driver.launch() is True

    def fail_local_storage(script: str, *args):
        driver._record_failure(
            BrowserResultStatus.ERROR,
            "BROWSER_STORAGE_READ_FAILED",
            "The browser storage could not be read.",
        )
        return None

    driver.evaluate_script = fail_local_storage  # type: ignore[method-assign]

    assert manager.capture_from_driver(driver, "example.com") is False
    assert manager.load_session("example.com") is None


def test_capture_session_keeps_only_target_and_parent_domain_cookies(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Shop account</body></html>",
        url="https://shop.example.com/account",
    )
    driver.cookies = [
        {"name": "host", "value": "one", "domain": "shop.example.com"},
        {"name": "parent", "value": "two", "domain": ".example.com"},
        {
            "name": "parent-host-only",
            "value": "must-not-reach-child",
            "domain": "example.com",
        },
        {"name": "child", "value": "three", "domain": "deep.shop.example.com"},
        {"name": "unrelated", "value": "four", "domain": "attacker.test"},
        {"name": "unscoped", "value": "five"},
    ]

    assert (
        manager.capture_from_driver(
            driver,
            "https://shop.example.com/account",
        )
        is True
    )

    stored = manager.load_session("shop.example.com")
    assert stored is not None
    assert [cookie["name"] for cookie in stored["cookies"]] == ["host", "parent"]


def test_local_storage_is_not_applied_to_a_different_active_origin(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    assert (
        manager.save_session(
            "example.com",
            [],
            local_storage={"private-token": "must-stay-on-origin"},
        )
        is True
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Different origin</body></html>",
        url="https://attacker.test/",
    )
    driver.action_log.clear()

    applied = manager.apply_to_driver(
        driver,
        "https://example.com/private",
        apply_cookies=False,
    )

    assert applied is False
    assert not any(
        entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
        for entry in driver.action_log
    )


def test_local_storage_is_not_applied_across_scheme_or_port_boundaries(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    assert (
        manager.save_session(
            "example.com",
            [],
            local_storage={"private-token": "must-stay-on-exact-origin"},
        )
        is True
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Same host, different origin</body></html>",
        url="http://example.com:8080/",
    )
    driver.action_log.clear()

    applied = manager.apply_to_driver(
        driver,
        "https://example.com/private",
        apply_cookies=False,
    )

    assert applied is False
    assert not any(
        entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
        for entry in driver.action_log
    )


def test_local_storage_apply_rechecks_origin_inside_atomic_script(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    assert (
        manager.save_session(
            "https://example.test/private",
            [],
            local_storage={"private-token": "must-not-cross-origin"},
        )
        is True
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Source origin</body></html>",
        url="https://example.test/private",
    )
    evaluated: list[tuple[str, tuple[object, ...]]] = []

    def redirect_before_script(script: str, *args: object) -> object:
        evaluated.append((script, args))
        driver._current_url = "https://attacker.test/landing"
        driver._record_success()
        if args:
            return False
        return None

    driver.evaluate_script = redirect_before_script  # type: ignore[method-assign]

    assert (
        manager.apply_to_driver(
            driver,
            "https://example.test/private",
            apply_cookies=False,
        )
        is False
    )
    assert len(evaluated) == 1
    script, args = evaluated[0]
    assert "window.location.origin" in script
    assert "localStorage.setItem" in script
    assert args and args[0]["origin"] == "https://example.test"


def test_local_storage_apply_rolls_back_when_later_write_fails(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    assert (
        manager.save_session(
            "https://example.test/private",
            [],
            local_storage={"first": "new-first", "second": "quota-failure"},
        )
        is True
    )
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Source origin</body></html>",
        url="https://example.test/private",
    )
    simulated_storage = {"first": "original-first"}

    def quota_failure(script: str, *args: object) -> object:
        payload = args[0]
        snapshot = dict(simulated_storage)
        for key, value in payload["entries"]:
            if key == "second":
                if "const rollback" in script and "removeItem" in script:
                    simulated_storage.clear()
                    simulated_storage.update(snapshot)
                driver._record_success()
                return False
            simulated_storage[key] = value
        driver._record_success()
        return True

    driver.evaluate_script = quota_failure  # type: ignore[method-assign]

    assert (
        manager.apply_to_driver(
            driver,
            "https://example.test/private",
            apply_cookies=False,
        )
        is False
    )
    assert simulated_storage == {"first": "original-first"}


def test_local_storage_capture_rejects_atomic_origin_change(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Source origin</body></html>",
        url="https://example.test/private",
    )

    def redirect_during_capture(script: str, *args: object) -> object:
        driver._current_url = "https://attacker.test/landing"
        driver._record_success()
        if args:
            return {
                "origin": "https://attacker.test",
                "storage": {"attacker-state": "must-not-be-mislabeled"},
            }
        return json.dumps({"attacker-state": "must-not-be-mislabeled"})

    driver.evaluate_script = redirect_during_capture  # type: ignore[method-assign]

    assert (
        manager.capture_from_driver(
            driver,
            "https://example.test/private",
        )
        is False
    )
    assert manager.load_session("https://example.test/private") is None


def test_local_storage_capture_rejects_preexisting_origin_mismatch(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_fixture_html(
        "<html><body>Attacker origin</body></html>",
        url="https://attacker.test/landing",
    )
    driver.script_eval_results["JSON.stringify(window.localStorage);"] = json.dumps(
        {"attacker-token": "must-not-be-mislabeled"}
    )

    assert (
        manager.capture_from_driver(
            driver,
            "https://example.test/private",
        )
        is False
    )
    assert manager.load_session("https://example.test/private") is None


def test_persisted_local_storage_is_bound_to_its_captured_origin(
    tmp_path: Path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path / "sessions"), db_path="")
    cookie = {
        "name": "shared-cookie",
        "value": "allowed-across-ports",
        "domain": "example.test",
        "path": "/",
    }
    source = MockBrowserDriver()
    assert source.launch() is True
    source.set_fixture_html(
        "<html><body>Source origin</body></html>",
        url="http://example.test:8080/account",
    )
    source.set_cookies([cookie])
    source.script_eval_results["JSON.stringify(window.localStorage);"] = json.dumps(
        {"private-token": "must-stay-on-source-origin"}
    )

    assert (
        manager.capture_from_driver(
            source,
            "http://example.test:8080/account",
        )
        is True
    )

    for target_url in (
        "https://example.test/account",
        "http://example.test:9090/account",
    ):
        target = MockBrowserDriver()
        assert target.launch() is True
        target.set_fixture_html(
            "<html><body>Different origin</body></html>",
            url=target_url,
        )
        target.action_log.clear()

        assert manager.apply_to_driver(target, target_url) is False
        assert target.get_cookies() == [cookie]
        assert not any(
            entry.get("action") == "evaluate_script"
            and "localStorage.setItem" in entry.get("script", "")
            for entry in target.action_log
        )
