"""
jarvis/plugins/loader.py
==========================
Plugin SDK Loader: hot-load JARVIS plugins từ ~/.jarvis/plugins/ hoặc pip packages.

Plugin format:
  - Folder: ~/.jarvis/plugins/my_plugin/__init__.py + metadata.json
  - Pip: jarvis-plugin-<name> package với jarvis.plugins entry_point

Tự động merge vào SkillRegistry khi start.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.plugins.loader")

_DEFAULT_PLUGIN_DIR = Path.home() / ".jarvis" / "plugins"
_ENTRY_POINT_GROUP = "jarvis.plugins"


class PluginManifest:
    """Describes a loaded plugin."""
    def __init__(self, name: str, version: str, description: str, source: str, execute_fn: Callable) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.source = source       # "folder" | "pip"
        self.execute_fn = execute_fn

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "source": self.source,
        }


class PluginLoader:
    """
    Hot-loads JARVIS plugins from:
    1. ~/.jarvis/plugins/<name>/  (folder plugins, same structure as built-in skills)
    2. pip packages with jarvis.plugins entry_point
    """

    def __init__(
        self,
        plugin_dir: Path | None = None,
        is_mock: bool = False,
    ) -> None:
        self.plugin_dir = plugin_dir or _DEFAULT_PLUGIN_DIR
        self.is_mock = is_mock
        self._plugins: dict[str, PluginManifest] = {}
        self.plugin_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self) -> list[PluginManifest]:
        """Scan plugin_dir and pip entry_points, load all valid plugins."""
        loaded = []
        loaded.extend(self._load_folder_plugins())
        loaded.extend(self._load_pip_plugins())
        log.info("Loaded %d plugins total.", len(loaded))
        return loaded

    def _load_folder_plugins(self) -> list[PluginManifest]:
        """Load plugins from ~/.jarvis/plugins/*/"""
        loaded = []
        if self.is_mock:
            # Return a mock plugin for testing
            def mock_execute(action="run", **kw):
                return {"data": {"text": f"Mock plugin ran: {action}", "success": True}, "output": "ok"}
            manifest = PluginManifest("mock_plugin", "1.0.0", "Mock plugin for testing", "folder", mock_execute)
            self._plugins["mock_plugin"] = manifest
            return [manifest]

        for plugin_path in sorted(self.plugin_dir.iterdir()):
            if not plugin_path.is_dir():
                continue
            init_file = plugin_path / "__init__.py"
            meta_file = plugin_path / "metadata.json"
            if not init_file.exists():
                log.debug("Skipping %s: no __init__.py", plugin_path.name)
                continue
            try:
                meta = {}
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                spec = importlib.util.spec_from_file_location(
                    f"jarvis_plugin_{plugin_path.name}", init_file
                )
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f"jarvis_plugin_{plugin_path.name}"] = mod
                spec.loader.exec_module(mod)
                execute_fn = getattr(mod, "execute", None)
                if execute_fn is None:
                    log.warning("Plugin %s has no execute() function", plugin_path.name)
                    continue
                manifest = PluginManifest(
                    name=meta.get("name", plugin_path.name),
                    version=meta.get("version", "0.1.0"),
                    description=meta.get("description", ""),
                    source="folder",
                    execute_fn=execute_fn,
                )
                self._plugins[manifest.name] = manifest
                loaded.append(manifest)
                log.info("Loaded folder plugin: %s v%s", manifest.name, manifest.version)
            except Exception as exc:
                log.error("Failed to load plugin %s: %s", plugin_path.name, exc)
        return loaded

    def _load_pip_plugins(self) -> list[PluginManifest]:
        """Load plugins installed as pip packages via entry_points."""
        loaded = []
        try:
            from importlib.metadata import entry_points  # Python 3.9+
            eps = entry_points(group=_ENTRY_POINT_GROUP)
            for ep in eps:
                try:
                    execute_fn = ep.load()
                    # pip plugin must export execute() directly or have an execute attribute
                    if callable(execute_fn):
                        manifest = PluginManifest(
                            name=ep.name,
                            version="pip",
                            description=f"pip plugin: {ep.name}",
                            source="pip",
                            execute_fn=execute_fn,
                        )
                    elif hasattr(execute_fn, "execute"):
                        manifest = PluginManifest(
                            name=ep.name,
                            version="pip",
                            description=f"pip plugin: {ep.name}",
                            source="pip",
                            execute_fn=execute_fn.execute,
                        )
                    else:
                        continue
                    self._plugins[manifest.name] = manifest
                    loaded.append(manifest)
                    log.info("Loaded pip plugin: %s", ep.name)
                except Exception as exc:
                    log.error("Failed to load pip plugin %s: %s", ep.name, exc)
        except ImportError:
            pass  # Python < 3.9, skip
        return loaded

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._plugins.values()]

    def get_plugin(self, name: str) -> PluginManifest | None:
        return self._plugins.get(name)

    def call_plugin(self, name: str, **kwargs: Any) -> dict[str, Any]:
        plugin = self._plugins.get(name)
        if not plugin:
            return {"data": {"text": f"Plugin '{name}' không tồn tại.", "success": False}, "output": "not found"}
        try:
            return plugin.execute_fn(**kwargs)
        except Exception as exc:
            log.error("Plugin %s execute error: %s", name, exc)
            return {"data": {"text": f"Lỗi plugin {name}: {exc}", "success": False}, "output": str(exc)}

    def reload_plugin(self, name: str) -> bool:
        """Reload a single plugin from disk."""
        plugin_path = self.plugin_dir / name
        if not plugin_path.exists():
            return False
        try:
            mod_name = f"jarvis_plugin_{name}"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            self._plugins.pop(name, None)
            self._load_folder_plugins()
            return name in self._plugins
        except Exception as exc:
            log.error("Reload plugin %s error: %s", name, exc)
            return False

    def unload_plugin(self, name: str) -> bool:
        if name in self._plugins:
            del self._plugins[name]
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._plugins)


__all__ = ["PluginLoader", "PluginManifest"]
