"""
Base Plugin Architecture and Dynamic Plugin Registry for JARVIS.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import (
    PluginHealth,
    PluginMetadata,
    PluginStatus,
    PrivilegeLevel,
)

logger = logging.getLogger("jarvis.core.plugin")


class BasePlugin(ABC):
    """
    Abstract Base Class for all JARVIS plugins.
    """

    def __init__(self, metadata: PluginMetadata | None = None, dispatcher: ActionDispatcher | None = None) -> None:
        self.metadata = metadata or self._define_metadata()
        self.config: dict[str, Any] = {}
        self.dispatcher: ActionDispatcher | None = dispatcher
        self.status: PluginStatus = PluginStatus.UNINITIALIZED
        self.error_message: str | None = None
        self._registered_actions: list[str] = []
        self._registered_subscriptions: list[str] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        orig_init = getattr(cls, "initialize", None)
        if orig_init and callable(orig_init):
            def wrapped_initialize(self, config: dict[str, Any], dispatcher: ActionDispatcher):
                self.config = config
                self.dispatcher = dispatcher
                return orig_init(self, config, dispatcher)
            cls.initialize = wrapped_initialize

    @abstractmethod
    def _define_metadata(self) -> PluginMetadata:
        """Define static metadata for the plugin."""
        pass

    @abstractmethod
    def initialize(self, config: dict[str, Any], dispatcher: ActionDispatcher) -> None:
        """
        Lifecycle Hook 1: Initialize plugin with system/plugin config and dispatcher.
        Register actions and subscribe to events here.
        """
        self.config = config
        self.dispatcher = dispatcher

    def start(self) -> None:
        """
        Lifecycle Hook 2: Start background workers, listeners, or timers.
        """
        self.status = PluginStatus.RUNNING

    def stop(self) -> None:
        """
        Lifecycle Hook 3: Stop background tasks, release resources, unregister actions.
        """
        if self.dispatcher:
            for action_name in list(self._registered_actions):
                self.dispatcher.unregister_action(action_name)
            for sub_id in list(self._registered_subscriptions):
                self.dispatcher.event_bus.unsubscribe(sub_id)
        self._registered_actions.clear()
        self._registered_subscriptions.clear()
        self.status = PluginStatus.STOPPED

    def health_check(self) -> PluginHealth:
        """
        Lifecycle Hook 4: Probe internal health state and diagnostic metrics.
        """
        return PluginHealth(
            plugin_name=self.metadata.name,
            status=self.status,
            is_healthy=(self.status in [PluginStatus.RUNNING, PluginStatus.INITIALIZED]),
            message=self.error_message or "Operating normally",
            last_check_timestamp=time.time(),
            metrics={}
        )

    def register_action(
        self,
        name: str,
        handler: Callable[..., Any],
        required_privilege: PrivilegeLevel = PrivilegeLevel.NORMAL,
        description: str = "",
        schema: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        dispatcher: ActionDispatcher | None = None,
    ) -> None:
        """Helper to register action associated with this plugin."""
        disp = dispatcher or self.dispatcher
        if not disp:
            raise RuntimeError(f"Cannot register action: Plugin '{self.metadata.name}' not initialized with dispatcher.")
        self.dispatcher = disp
        disp.register_action(
            name=name,
            handler=handler,
            required_privilege=required_privilege,
            description=description,
            schema=schema,
            timeout_seconds=timeout_seconds,
            plugin_name=self.metadata.name
        )
        self._registered_actions.append(name)

    def subscribe_event(
        self,
        event_name: str,
        handler: Callable[..., Any],
        priority: int = 0,
        dispatcher: ActionDispatcher | None = None,
    ) -> str:
        """Helper to subscribe to event bus associated with this plugin."""
        disp = dispatcher or self.dispatcher
        if not disp:
            raise RuntimeError(f"Cannot subscribe: Plugin '{self.metadata.name}' not initialized with dispatcher.")
        self.dispatcher = disp
        sub_id = disp.event_bus.subscribe(event_name, handler, priority=priority)
        self._registered_subscriptions.append(sub_id)
        return sub_id


class CircularDependencyError(Exception):
    """Raised when circular dependencies are detected in plugin graph."""
    pass


class PluginRegistry:
    """
    Dynamic Plugin Registry, Loader, and Dependency Resolver.
    """

    def __init__(self, dispatcher: ActionDispatcher) -> None:
        self.dispatcher = dispatcher
        self._plugins: dict[str, BasePlugin] = {}
        self._enabled_plugins: set[str] = set()
        self._plugin_configs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def register_plugin(
        self,
        plugin: BasePlugin | type,
        config: dict[str, Any] | None = None,
        auto_init: bool = True
    ) -> bool:
        """Register a plugin instance or class with dependency resolution and initialization."""
        plugin_inst = plugin() if isinstance(plugin, type) else plugin
        name = plugin_inst.metadata.name
        with self._lock:
            self._plugins[name] = plugin_inst
            self._plugin_configs[name] = config or {}
            plugin_inst.dispatcher = self.dispatcher

            if auto_init:
                try:
                    plugin_inst.initialize(self._plugin_configs[name], self.dispatcher)
                    plugin_inst.status = PluginStatus.INITIALIZED
                    if plugin_inst.metadata.enabled_by_default:
                        plugin_inst.start()
                        self._enabled_plugins.add(name)
                    logger.info("Successfully registered and started plugin '%s' (v%s)", name, plugin_inst.metadata.version)
                    return True
                except Exception as exc:
                    plugin_inst.status = PluginStatus.ERROR
                    plugin_inst.error_message = str(exc)
                    logger.error("Failed to initialize plugin '%s': %s", name, exc, exc_info=True)
                    return False
    def get_plugin(self, name: str) -> BasePlugin | None:
        """Retrieve registered plugin by name."""
        with self._lock:
            return self._plugins.get(name)

    def list_plugins(self) -> list[PluginMetadata]:
        """List metadata for all registered plugins."""
        with self._lock:
            return [p.metadata for p in self._plugins.values()]

    def enable_plugin(self, name: str) -> bool:
        """Enable a registered plugin."""
        with self._lock:
            plugin = self._plugins.get(name)
            if not plugin:
                logger.warning("Cannot enable unknown plugin '%s'", name)
                return False
            if plugin.status == PluginStatus.RUNNING:
                return True
            try:
                plugin.dispatcher = self.dispatcher
                if plugin.status in (PluginStatus.UNINITIALIZED, PluginStatus.STOPPED):
                    plugin.initialize(self._plugin_configs.get(name, {}), self.dispatcher)
                plugin.start()
                self._enabled_plugins.add(name)
                logger.info("Plugin '%s' enabled successfully.", name)
                return True
            except Exception as exc:
                plugin.status = PluginStatus.ERROR
                plugin.error_message = str(exc)
                logger.error("Failed to enable plugin '%s': %s", name, exc, exc_info=True)
                return False

    def disable_plugin(self, name: str) -> bool:
        """Disable an active plugin and unregister its actions."""
        with self._lock:
            plugin = self._plugins.get(name)
            if not plugin:
                return False
            try:
                plugin.stop()
                self._enabled_plugins.discard(name)
                logger.info("Plugin '%s' disabled successfully.", name)
                return True
            except Exception as exc:
                logger.error("Error while disabling plugin '%s': %s", name, exc, exc_info=True)
                return False

    def initialize_all(self, configs: dict[str, Any] | None = None) -> None:
        """Initialize all registered plugins with optional config overrides."""
        configs = configs or {}
        with self._lock:
            for name, plugin in self._plugins.items():
                if name in configs:
                    self._plugin_configs[name] = configs[name]
                if plugin.status == PluginStatus.UNINITIALIZED:
                    try:
                        plugin.initialize(self._plugin_configs.get(name, {}), self.dispatcher)
                        plugin.status = PluginStatus.INITIALIZED
                    except Exception as e:
                        logger.error("Failed to initialize plugin '%s': %s", name, e)

    def stop_all(self) -> None:
        """Stop all active plugins."""
        with self._lock:
            for name in list(self._enabled_plugins):
                self.disable_plugin(name)

    def discover_and_load_plugins(
        self,
        directory: str | Path,
        configs: dict[str, dict[str, Any]] | None = None
    ) -> list[str]:
        """
        Discover and load all BasePlugin subclasses from python files in a directory.
        """
        plugin_dir = Path(directory)
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            logger.warning("Plugin directory '%s' does not exist.", plugin_dir)
            return []

        configs = configs or {}
        discovered_classes: list[type[BasePlugin]] = []

        for file_path in plugin_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue

            module_name = f"jarvis_plugin_{file_path.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            inspect.isclass(attr)
                            and issubclass(attr, BasePlugin)
                            and attr is not BasePlugin
                        ):
                            discovered_classes.append(attr)
            except Exception as exc:
                logger.error("Failed to load plugin file '%s': %s", file_path.name, exc, exc_info=True)

        # Instantiate plugins
        instantiated: dict[str, BasePlugin] = {}
        for cls in discovered_classes:
            try:
                instance = cls(dispatcher=self.dispatcher)
                instantiated[instance.metadata.name] = instance
            except Exception as exc:
                logger.error("Failed to instantiate plugin class '%s': %s", cls.__name__, exc, exc_info=True)

        # Dependency Resolution (Topological Sort)
        sorted_plugins = self._resolve_dependencies(instantiated)

        loaded_names: list[str] = []
        for plugin in sorted_plugins:
            cfg = configs.get(plugin.metadata.name, {})
            if self.register_plugin(plugin, config=cfg, auto_init=True):
                loaded_names.append(plugin.metadata.name)

        return loaded_names

    def _resolve_dependencies(self, plugins: dict[str, BasePlugin]) -> list[BasePlugin]:
        """
        Topologically sort plugins by declared dependencies (Kahn's algorithm).
        """
        in_degree: dict[str, int] = {name: 0 for name in plugins}
        adj_list: dict[str, list[str]] = {name: [] for name in plugins}

        for name, plugin in plugins.items():
            for dep in plugin.metadata.dependencies:
                if dep in plugins:
                    adj_list[dep].append(name)
                    in_degree[name] += 1
                else:
                    logger.warning("Plugin '%s' has unmet optional/external dependency: '%s'", name, dep)

        queue = [name for name, deg in in_degree.items() if deg == 0]
        sorted_names: list[str] = []

        while queue:
            node = queue.pop(0)
            sorted_names.append(node)
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_names) != len(plugins):
            unresolved = set(plugins.keys()) - set(sorted_names)
            logger.error("Circular dependency detected among plugins: %s", unresolved)
            return [plugins[n] for n in sorted_names] + [plugins[n] for n in unresolved]

        return [plugins[n] for n in sorted_names]

    def check_all_health(self) -> dict[str, PluginHealth]:
        """Run health check on all registered plugins."""
        health_reports: dict[str, PluginHealth] = {}
        with self._lock:
            for name, plugin in self._plugins.items():
                try:
                    health_reports[name] = plugin.health_check()
                except Exception as exc:
                    health_reports[name] = PluginHealth(
                        plugin_name=name,
                        status=PluginStatus.ERROR,
                        is_healthy=False,
                        message=f"Health check probe raised exception: {exc}"
                    )
        return health_reports

    def stop_all(self) -> None:
        """Gracefully stop all plugins in reverse dependency order."""
        with self._lock:
            for name in list(self._enabled_plugins):
                self.disable_plugin(name)
