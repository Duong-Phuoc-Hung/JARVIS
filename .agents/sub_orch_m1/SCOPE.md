# Scope: Milestone 1 — Core Framework & Foundations

## Architecture & Responsibilities
Milestone 1 builds the operational foundation for JARVIS:
- **CLI & Package Entrypoint**: `python -m jarvis` CLI commands with argparse, versioning, health check, autostart management.
- **Config Management (`jarvis/core/config.py`)**: `ConfigManager` supporting `.env`, `YAML`, and `JSON` format hierarchy, default values from `config/default_config.yaml`, thread-safe hot reloading (polling / watchdog within 5s).
- **Structured Logging (`jarvis/core/logger.py`)**: Rotating file logger (`logs/jarvis.log`) and console output with colorized formatting, configurable log levels, structured contextual logging.
- **Dynamic Event Bus & Dispatcher (`jarvis/core/dispatcher.py`)**: Publish/subscribe event bus and action dispatcher with error isolation (one failing subscriber doesn't crash others), privilege interception (security checks for high-privilege actions like system shutdown, volume, window control), async & sync support.
- **Plugin Architecture (`jarvis/core/plugin.py`)**: `BasePlugin` abstract class, metadata schema validation, dynamic plugin loader/registry, lifecycle management (`initialize`, `start`, `stop`, `health_check`).
- **Platform Windows Layer (`jarvis/platform/windows.py`)**: Windows-specific low-level helpers via `ctypes` (`user32`, `kernel32`, `shell32`, `dwmapi`): monitor boundaries/DPI awareness, window enumeration/focus/positioning/minimization, key & mouse injection (`SendInput`), and registry autostart (`winreg` HKCU Run key).
- **Default Config**: `config/default_config.yaml`.

## Feature Inventory
| # | Feature ID | Name | Description | Source | Status |
|---|------------|------|-------------|--------|--------|
| 1 | F-01 | Modular Package & CLI | `python -m jarvis` CLI entry point, versioning, diagnostics | PROJECT.md / Survey | DONE |
| 2 | F-08 | Action Dispatcher & Event Bus | Event bus, priority dispatching, privilege interceptor, error isolation | PROJECT.md / Survey | DONE |
| 3 | F-09 | Base Plugin Architecture | BasePlugin, dynamic plugin discovery, metadata schema validation | PROJECT.md / Survey | DONE |
| 4 | F-10 | ConfigManager & Hot Reload | Multi-source config (.env, YAML, JSON), thread-safe hot-reload (<=5s) | PROJECT.md / Survey | DONE |
| 5 | F-18 | Structured Rotating Logging | Rotating file logger (`logs/jarvis.log`), context formatting | PROJECT.md / Survey | DONE |
| 6 | F-19 | Windows Auto-Start Manager | `install-autostart`, `uninstall-autostart`, `autostart-status` via winreg | PROJECT.md / Survey | DONE |
| 7 | F-WIN | Windows Platform Ctypes Helper | ctypes-based window management, monitor geometry, focus, SendInput | PROJECT.md / Survey | DONE |
| 8 | F-CFG | Default Configuration File | Complete `config/default_config.yaml` with schema for all modules | PROJECT.md / Survey | DONE |

## Interface Contracts
### `jarvis.core.config.ConfigManager`
- `get(key: str, default: Any = None) -> Any` (supports dot notation, e.g. `get("audio.sample_rate", 16000)`)
- `set(key: str, value: Any) -> None`
- `load_config(path: str | Path) -> dict[str, Any]`
- `reload() -> None`
- `on_change(callback: Callable[[dict[str, Any]], None]) -> None`
- `start_watcher(interval_seconds: float = 2.0) -> None`
- `stop_watcher() -> None`

### `jarvis.core.dispatcher.EventDispatcher` / `EventBus`
- `subscribe(event_name: str, handler: Callable[..., Any], priority: int = 0) -> str` (returns subscription_id)
- `unsubscribe(subscription_id: str) -> None`
- `publish(event_name: str, **payload) -> None` (isolated error handling, non-blocking / sync options)
- `publish_async(event_name: str, **payload) -> asyncio.Future`
- `dispatch_action(action_name: str, payload: dict, requester: str = "user") -> ActionResult`
- `register_action(action_name: str, handler: Callable, required_privilege: PrivilegeLevel = PrivilegeLevel.NORMAL)`
- `set_privilege_interceptor(interceptor: Callable[[str, dict, str], bool]) -> None`

### `jarvis.core.plugin.BasePlugin` & `PluginRegistry`
- `BasePlugin` abstract methods: `name`, `version`, `initialize(config, dispatcher)`, `start()`, `stop()`, `health_check() -> PluginHealth`
- `PluginRegistry.discover_and_register(plugin_dir: Path | str) -> list[BasePlugin]`
- `PluginRegistry.get_plugin(name: str) -> BasePlugin | None`
- `PluginRegistry.start_all()` / `stop_all()`

### `jarvis.platform.windows`
- `get_monitors() -> list[MonitorInfo]` (rect, dpi, is_primary)
- `get_active_window() -> WindowInfo` (hwnd, title, class_name, rect, pid)
- `list_windows(visible_only: bool = True) -> list[WindowInfo]`
- `set_window_pos(hwnd: int, x: int, y: int, width: int, height: int) -> bool`
- `focus_window(hwnd: int) -> bool`
- `minimize_window(hwnd: int) -> bool`
- `maximize_window(hwnd: int) -> bool`
- `restore_window(hwnd: int) -> bool`
- `send_keystrokes(keys: list[str] | str) -> bool` (via SendInput)
- `set_autostart(app_name: str, app_path: str, enabled: bool) -> bool`
- `get_autostart_status(app_name: str) -> bool`

## Code Layout
- `jarvis/__init__.py`
- `jarvis/__main__.py`
- `jarvis/cli.py`
- `jarvis/core/__init__.py`
- `jarvis/core/config.py`
- `jarvis/core/logger.py`
- `jarvis/core/dispatcher.py`
- `jarvis/core/plugin.py`
- `jarvis/core/models.py`
- `jarvis/platform/__init__.py`
- `jarvis/platform/windows.py`
- `jarvis/platform/autostart.py`
- `config/default_config.yaml`
- `tests/test_config.py`
- `tests/test_dispatcher.py`
- `tests/test_plugins.py`
- `tests/test_windows_platform.py`
- `tests/test_cli.py`
- `tests/test_logger.py`
- `tests/test_adversarial_m1.py`
- `tests/test_empirical_challenger_m1.py`
