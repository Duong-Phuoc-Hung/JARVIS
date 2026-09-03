"""
tests/unit/test_terminal_app.py
==================================
TerminalApp integration tests. Real JarvisApp is NEVER constructed here --
`start_jarvis` is always an injected fake, verified by call-count assertions
rather than by trusting a mock wasn't secretly real.

Generic navigation/global-key/batch/save mechanics are exercised against
small synthetic MenuScreen fixtures (dependency injection, per the task's
own testing guidance) rather than the real, slower product-module
adapters -- those get their own truthfulness-focused tests in
tests/unit/test_terminal_modules.py.
"""
from __future__ import annotations

import pytest

from jarvis import __version__ as JARVIS_VERSION
from jarvis.core.config import ConfigManager
from jarvis.ui.terminal.app import TerminalApp
from jarvis.ui.terminal.console import TerminalConsole
from jarvis.ui.terminal.models import ActionOutcome, MenuAction, MenuScreen
from jarvis.ui.terminal.navigator import TerminalNavigator
from jarvis.ui.terminal.theme import StatusLevel, TerminalTheme


def _cfg() -> ConfigManager:
    cfg = ConfigManager()
    cfg.load()
    return cfg


def _make_app(keys, lines=None, line_source=None, start_jarvis=None) -> tuple[TerminalApp, list[str]]:
    captured: list[str] = []
    key_iter = iter(keys)

    def key_source():
        try:
            return next(key_iter)
        except StopIteration:
            return None

    theme = TerminalTheme(color_enabled=False)
    console = TerminalConsole(theme=theme, key_source=key_source, line_source=line_source, out=captured.append)
    app = TerminalApp(config=_cfg(), console=console, theme=theme,
                       start_jarvis=start_jarvis or (lambda: False))
    return app, captured


def _synthetic_screens(counter: dict | None = None, extra_actions=None):
    """A small 2-level synthetic screen tree: root -> module -> detail."""
    calls = counter if counter is not None else {"resolve": 0}

    def make_module_action():
        def handler():
            return ActionOutcome(status=StatusLevel.PASS, title="Do Thing", fields=[("X", "1")], duration_s=0.01)
        return MenuAction(id="do_thing", key="1", label="Do Thing", handler=handler, safe_for_batch=True)

    def build_root(ctx) -> MenuScreen:
        return MenuScreen(id="root", title="MAIN", breadcrumb=["MAIN"], actions=[
            MenuAction(id="to_module", key="1", label="Module", is_submenu=True, submenu_id="module"),
        ])

    def build_module(ctx) -> MenuScreen:
        calls["resolve"] += 1
        actions = [make_module_action()]
        if extra_actions:
            actions.extend(extra_actions())
        actions.append(MenuAction(id="to_detail", key="9", label="Detail", is_submenu=True, submenu_id="detail"))
        return MenuScreen(id="module", title="MODULE", breadcrumb=["MAIN", "MODULE"], actions=actions,
                           batch_label="Run All")

    def build_detail(ctx) -> MenuScreen:
        return MenuScreen(id="detail", title="DETAIL", breadcrumb=["MAIN", "MODULE", "DETAIL"], actions=[])

    resolvers = {"root": build_root, "module": build_module, "detail": build_detail}

    def resolve(ctx, sid):
        return resolvers[sid](ctx)

    return resolve, calls


def _install_synthetic_navigator(app: TerminalApp, resolve, root="root"):
    app.navigator = TerminalNavigator(resolve=lambda sid: resolve(app.ctx, sid), root_id=root)


# -- Main menu rendering (real main menu) --------------------------------

def test_main_menu_shows_logo_all_module_keys_and_global_keys():
    app, lines = _make_app(keys=["0"])
    app.run()
    text = "\n".join(lines)
    assert "J.A.R.V.I.S" in text
    for n in "123456789":
        assert f"[{n}]" in text
    assert "[J]" in text and "[R]" in text and "[H]" in text and "[0]" in text
    assert "[B]" not in text  # never shown at root


def test_main_menu_displays_real_project_version():
    app, lines = _make_app(keys=["0"])
    app.run()
    assert any(JARVIS_VERSION in line for line in lines)


def test_main_menu_never_displays_secret_looking_values():
    app, lines = _make_app(keys=["0"])
    app.run()
    text = "\n".join(lines).lower()
    assert "bot_token" not in text or "<redacted>" in text
    assert "api_key=" not in text


# -- Navigation -----------------------------------------------------------

def test_navigation_main_to_module_and_back_to_main():
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    rc = app.run()
    assert rc == 0
    assert "MODULE" in "\n".join(lines)


def test_navigation_three_levels_deep_then_back_twice():
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "9", "b", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    text = "\n".join(lines)
    assert "PATH // MAIN > MODULE > DETAIL" in text


def test_back_pops_exactly_one_level():
    resolve, _ = _synthetic_screens()
    app, _ = _make_app(keys=["1", "9", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    # after one 'b' from detail, we should be back at module (not root) --
    # verified indirectly: pressing '0' next exits cleanly with no crash,
    # and the navigator's own unit tests already prove pop() is single-level.
    assert app.navigator.stack_ids == ["root", "module"]


def test_zero_exits_from_a_deep_level_directly():
    resolve, _ = _synthetic_screens()
    app, _ = _make_app(keys=["1", "9", "0"])
    _install_synthetic_navigator(app, resolve)
    rc = app.run()
    assert rc == 0


def test_invalid_input_stays_at_current_screen():
    resolve, calls = _synthetic_screens()
    app, lines = _make_app(keys=["z", "z", "0"])
    _install_synthetic_navigator(app, resolve)
    rc = app.run()
    assert rc == 0
    # 'module' is only ever resolved by navigating into it via a valid '1' --
    # two invalid 'z' keypresses must never trigger that navigation.
    assert calls["resolve"] == 0
    assert app.navigator.current_id == "root"


def test_ctrl_c_is_handled_gracefully_no_traceback():
    def key_source():
        raise KeyboardInterrupt

    theme = TerminalTheme(color_enabled=False)
    console = TerminalConsole(theme=theme, key_source=key_source, out=lambda t: None)
    app = TerminalApp(config=_cfg(), console=console, theme=theme, start_jarvis=lambda: False)
    rc = app.run()
    assert rc == 0


def test_eof_is_handled_gracefully_no_traceback():
    app, _ = _make_app(keys=[])  # key_source immediately returns None -> EOFError
    rc = app.run()
    assert rc == 0


def test_breadcrumb_reflects_navigation_stack():
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    assert "PATH // MAIN > MODULE" in "\n".join(lines)


# -- [J] ---------------------------------------------------------------------

def test_j_confirmation_declined_does_not_start_jarvis():
    calls = {"n": 0}

    def fake_start():
        calls["n"] += 1
        return True

    app, _ = _make_app(keys=["j", "n", "0"], start_jarvis=fake_start)
    app.run()
    assert calls["n"] == 0


def test_j_confirmed_calls_start_exactly_once_and_exits():
    calls = {"n": 0}

    def fake_start():
        calls["n"] += 1
        return True

    app, _ = _make_app(keys=["j", "y"], start_jarvis=fake_start)
    rc = app.run()
    assert calls["n"] == 1
    assert rc == 0


def test_j_lowercase_key_is_accepted():
    calls = {"n": 0}

    def fake_start():
        calls["n"] += 1
        return True

    app, _ = _make_app(keys=["j", "y"], start_jarvis=fake_start)
    app.run()
    assert calls["n"] == 1


def test_j_is_available_from_a_nested_screen():
    resolve, _ = _synthetic_screens()
    calls = {"n": 0}

    def fake_start():
        calls["n"] += 1
        return True

    app, _ = _make_app(keys=["1", "j", "y"], start_jarvis=fake_start)
    _install_synthetic_navigator(app, resolve)
    app.run()
    assert calls["n"] == 1


def test_r_does_not_start_jarvis():
    calls = {"n": 0}

    def fake_start():
        calls["n"] += 1
        return True

    app, _ = _make_app(keys=["r", "0"], start_jarvis=fake_start)
    app.run()
    assert calls["n"] == 0


# -- [R] refresh ----------------------------------------------------------

def test_refresh_rebuilds_current_screen_exactly_once_and_stays():
    resolve, calls = _synthetic_screens()
    app, lines = _make_app(keys=["1", "r", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    # 'module' screen is resolved once on initial navigation + once more on
    # refresh (render happens once per loop iteration).
    assert calls["resolve"] == 2
    assert app.navigator.current_id == "module"


def test_refresh_shows_freshly_read_live_data_not_a_stale_cache():
    """Concrete changing-provider proof: a fake live data source reports
    CPU=10 on the first render. Only AFTER that first render does the
    provider's live value change to 20 (simulating real state drifting
    between renders) -- pressing [R] must then display CPU=20, proving
    the screen genuinely re-reads live state on refresh rather than
    repainting whatever was captured at the first render."""
    live_cpu = {"value": 10}
    captured: list[str] = []

    def build_root(ctx):
        return MenuScreen(id="root", title="MAIN", breadcrumb=["MAIN"], actions=[
            MenuAction(id="probe", key="1", label=f"CPU={live_cpu['value']}",
                       handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x")),
        ])

    # First key request happens right after the FIRST render (CPU=10 already
    # captured in `captured`). Only then does the live value change to 20,
    # right before returning "r" -- exactly modelling state drifting between
    # a first render and a later refresh.
    remaining_keys = iter(["r", "0"])

    def key_source():
        if live_cpu["value"] == 10:
            live_cpu["value"] = 20
        try:
            return next(remaining_keys)
        except StopIteration:
            return None

    theme = TerminalTheme(color_enabled=False)
    console = TerminalConsole(theme=theme, key_source=key_source, out=captured.append)
    app = TerminalApp(config=_cfg(), console=console, theme=theme, start_jarvis=lambda: False)
    app.navigator = TerminalNavigator(resolve=lambda sid: build_root(app.ctx), root_id="root")
    app.run()

    # `captured` accumulates line-by-line; key_source() (and thus the live
    # value mutation) only runs AFTER a render's lines are already appended,
    # so "CPU=10" appearing at all proves the first render used the old
    # value, and its presence strictly before the last "CPU=20" line proves
    # the second (post-refresh) render used the new one -- not a rerun of
    # a cached first render.
    cpu10_index = next(i for i, line in enumerate(captured) if "CPU=10" in line)
    cpu20_index = next(i for i, line in enumerate(captured) if "CPU=20" in line)
    assert cpu10_index < cpu20_index


def test_refresh_never_invokes_an_action_handler():
    calls = {"n": 0}

    def build_root(ctx):
        def handler():
            calls["n"] += 1
            return ActionOutcome(status=StatusLevel.PASS, title="x")
        return MenuScreen(id="root", title="MAIN", breadcrumb=["MAIN"], actions=[
            MenuAction(id="probe", key="1", label="Probe", handler=handler),
        ])

    app, _ = _make_app(keys=["r", "r", "0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: build_root(app.ctx), root_id="root")
    app.run()
    assert calls["n"] == 0


# -- [A] batch --------------------------------------------------------------

def test_a_key_not_offered_when_no_batch_eligible_actions():
    app, lines = _make_app(keys=["0"])
    app.run()
    # Root/main menu links are all is_submenu -- none are safe_for_batch.
    assert "[A]" not in "\n".join(lines)


def test_a_not_offered_with_zero_eligible_actions():
    """Canonical rule: [A] requires >= 2 currently meaningful safe-batch
    actions. Zero eligible -> no [A]."""
    def build_module(ctx):
        return MenuScreen(id="module", title="MODULE", breadcrumb=["MAIN", "MODULE"], actions=[
            MenuAction(id="readonly", key="1", label="Status Only",
                       handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"),
                       safe_for_batch=False),
        ])

    resolve = {"module": build_module, "root": lambda ctx: MenuScreen(
        id="root", title="MAIN", breadcrumb=["MAIN"],
        actions=[MenuAction(id="to_module", key="1", label="Module", is_submenu=True, submenu_id="module")])}
    app, lines = _make_app(keys=["1", "0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: resolve[sid](app.ctx), root_id="root")
    app.run()
    assert "[A]" not in "\n".join(lines)


def test_a_not_offered_with_exactly_one_eligible_action():
    """One eligible action alone does not warrant a separate [A] batch
    affordance -- the user can just select that one action directly."""
    def build_module(ctx):
        return MenuScreen(id="module", title="MODULE", breadcrumb=["MAIN", "MODULE"], actions=[
            MenuAction(id="only_one", key="1", label="Only Safe Action",
                       handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"),
                       safe_for_batch=True),
        ])

    resolve = {"module": build_module, "root": lambda ctx: MenuScreen(
        id="root", title="MAIN", breadcrumb=["MAIN"],
        actions=[MenuAction(id="to_module", key="1", label="Module", is_submenu=True, submenu_id="module")])}
    app, lines = _make_app(keys=["1", "0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: resolve[sid](app.ctx), root_id="root")
    app.run()
    assert "[A]" not in "\n".join(lines)


def test_a_offered_with_exactly_two_eligible_actions():
    def build_module(ctx):
        return MenuScreen(id="module", title="MODULE", breadcrumb=["MAIN", "MODULE"], actions=[
            MenuAction(id="a1", key="1", label="First",
                       handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"), safe_for_batch=True),
            MenuAction(id="a2", key="2", label="Second",
                       handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"), safe_for_batch=True),
        ], batch_label="Run Both")

    resolve = {"module": build_module, "root": lambda ctx: MenuScreen(
        id="root", title="MAIN", breadcrumb=["MAIN"],
        actions=[MenuAction(id="to_module", key="1", label="Module", is_submenu=True, submenu_id="module")])}
    app, lines = _make_app(keys=["1", "0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: resolve[sid](app.ctx), root_id="root")
    app.run()
    assert "[A]" in "\n".join(lines)


def test_a_offered_with_three_or_more_eligible_actions():
    resolve, _ = _synthetic_screens(extra_actions=lambda: [
        MenuAction(id="extra1", key="2", label="Extra1",
                   handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"), safe_for_batch=True),
        MenuAction(id="extra2", key="3", label="Extra2",
                   handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"), safe_for_batch=True),
    ])
    app, lines = _make_app(keys=["1", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    # base 'do_thing' + extra1 + extra2 = 3 eligible actions.
    assert "[A]" in "\n".join(lines)


def test_a_runs_each_eligible_action_exactly_once():
    call_counts = {"safe": 0, "unsafe": 0}

    def extra():
        def safe_handler():
            call_counts["safe"] += 1
            return ActionOutcome(status=StatusLevel.PASS, title="Safe")

        def unsafe_handler():
            call_counts["unsafe"] += 1
            return ActionOutcome(status=StatusLevel.PASS, title="Unsafe")

        return [
            MenuAction(id="safe2", key="2", label="Safe Two", handler=safe_handler, safe_for_batch=True),
            MenuAction(id="unsafe", key="3", label="Send Message", handler=unsafe_handler,
                       safe_for_batch=False, requires_confirmation=True, side_effect_level="external_send"),
        ]

    resolve, _ = _synthetic_screens(extra_actions=extra)
    app, lines = _make_app(keys=["1", "a", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    assert call_counts["safe"] == 1
    assert call_counts["unsafe"] == 0  # excluded from batch


def test_batch_aggregates_mixed_statuses_truthfully():
    def extra():
        return [
            MenuAction(id="limited", key="2", label="Limited One",
                       handler=lambda: ActionOutcome(status=StatusLevel.LIMITED, title="L"), safe_for_batch=True),
            MenuAction(id="skipped", key="3", label="Skipped One",
                       handler=lambda: ActionOutcome(status=StatusLevel.SKIPPED, title="S"), safe_for_batch=True),
            MenuAction(id="failed", key="4", label="Failed One",
                       handler=lambda: ActionOutcome(status=StatusLevel.FAILED, title="F"), safe_for_batch=True),
        ]

    resolve, _ = _synthetic_screens(extra_actions=extra)
    app, lines = _make_app(keys=["1", "a", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    text = "\n".join(lines)
    assert "PASS      : 1" in text
    assert "LIMITED   : 1" in text
    assert "SKIPPED   : 1" in text
    assert "FAILED    : 1" in text


def test_empty_batch_handled_gracefully():
    def build_empty_root(ctx):
        return MenuScreen(id="root", title="MAIN", breadcrumb=["MAIN"], actions=[])

    app, _ = _make_app(keys=["0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: build_empty_root(app.ctx), root_id="root")
    rc = app.run()
    assert rc == 0


# -- [S] save ---------------------------------------------------------------

def test_s_not_offered_before_anything_has_run():
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    assert "[S]" not in "\n".join(lines)


def test_s_saves_current_result(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "1", "s", "b", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    saved_files = list((tmp_path / "reports" / "cli").glob("*.txt"))
    assert len(saved_files) == 1


def test_s_save_module_session(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "1", "b", "s", "2", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    saved = list((tmp_path / "reports" / "cli").glob("*session*.txt"))
    assert len(saved) == 1


def test_s_save_full_cli_session(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    resolve, _ = _synthetic_screens()
    app, lines = _make_app(keys=["1", "1", "b", "s", "3", "b", "0"])
    _install_synthetic_navigator(app, resolve)
    app.run()
    saved = list((tmp_path / "reports" / "cli").glob("jarvis_session_full_*.txt"))
    assert len(saved) == 1


# -- Dynamic menus ------------------------------------------------------------

def test_dynamic_menu_zero_items():
    items: list[str] = []

    def build_root(ctx):
        actions = [MenuAction(id=f"item_{i}", key=str(i + 1), label=i, handler=lambda: ActionOutcome(status=StatusLevel.PASS, title="x"))
                   for i, i in enumerate(items)]
        return MenuScreen(id="root", title="MAIN", breadcrumb=["MAIN"], actions=actions)

    app, _ = _make_app(keys=["0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: build_root(app.ctx), root_id="root")
    rc = app.run()
    assert rc == 0


def test_dynamic_menu_one_then_many_then_disappearing():
    items = ["Drive C"]

    def build_root(ctx):
        actions = [MenuAction(id=f"d{i}", key=str(i + 1), label=lbl,
                               handler=lambda lbl=lbl: ActionOutcome(status=StatusLevel.PASS, title=lbl))
                   for i, lbl in enumerate(items)]
        return MenuScreen(id="root", title="MAIN", breadcrumb=["MAIN"], actions=actions)

    app, lines = _make_app(keys=["0"])
    app.navigator = TerminalNavigator(resolve=lambda sid: build_root(app.ctx), root_id="root")
    app.run()
    assert "Drive C" in "\n".join(lines)

    items.append("Drive D")
    lines.clear()
    app2, lines2 = _make_app(keys=["0"])
    app2.navigator = TerminalNavigator(resolve=lambda sid: build_root(app2.ctx), root_id="root")
    app2.run()
    assert "Drive C" in "\n".join(lines2) and "Drive D" in "\n".join(lines2)

    items.pop(0)  # drive disappears
    app3, lines3 = _make_app(keys=["0"])
    app3.navigator = TerminalNavigator(resolve=lambda sid: build_root(app3.ctx), root_id="root")
    rc = app3.run()
    assert rc == 0
    assert "Drive C" not in "\n".join(lines3)
