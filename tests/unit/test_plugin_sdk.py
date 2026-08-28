"""
tests/unit/test_plugin_sdk.py
================================
Unit tests for Plugin SDK Loader.
"""
from __future__ import annotations
import json
from pathlib import Path
import pytest

from jarvis.plugins.loader import PluginLoader, PluginManifest


@pytest.fixture
def loader():
    return PluginLoader(is_mock=True)


@pytest.fixture
def folder_loader(tmp_path):
    """Create a real folder loader with a sample plugin in tmp_path."""
    # Create a sample plugin
    plugin_dir = tmp_path / "hello_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.json").write_text(json.dumps({
        "name": "hello_plugin",
        "version": "1.0.0",
        "description": "Test plugin",
    }), encoding="utf-8")
    (plugin_dir / "__init__.py").write_text(
        'def execute(action="run", **kw):\n'
        '    return {"data": {"text": "Hello from plugin!", "success": True}, "output": "ok"}\n',
        encoding="utf-8"
    )
    return PluginLoader(plugin_dir=tmp_path, is_mock=False)


class TestMockLoader:
    def test_load_all_returns_list(self, loader):
        plugins = loader.load_all()
        assert isinstance(plugins, list)
        assert len(plugins) >= 1

    def test_mock_plugin_in_registry(self, loader):
        loader.load_all()
        plugin = loader.get_plugin("mock_plugin")
        assert plugin is not None

    def test_list_plugins_returns_dicts(self, loader):
        loader.load_all()
        listing = loader.list_plugins()
        assert isinstance(listing, list)
        for item in listing:
            assert "name" in item
            assert "version" in item

    def test_call_mock_plugin(self, loader):
        loader.load_all()
        result = loader.call_plugin("mock_plugin", action="run")
        assert result["data"]["success"] is True

    def test_call_nonexistent_plugin_returns_failure(self, loader):
        loader.load_all()
        result = loader.call_plugin("nonexistent_xyz")
        assert result["data"]["success"] is False

    def test_count_increases_after_load(self, loader):
        assert loader.count == 0
        loader.load_all()
        assert loader.count >= 1


class TestFolderLoader:
    def test_loads_sample_plugin(self, folder_loader):
        plugins = folder_loader.load_all()
        assert len(plugins) >= 1

    def test_sample_plugin_execute(self, folder_loader):
        folder_loader.load_all()
        plugin = folder_loader.get_plugin("hello_plugin")
        assert plugin is not None
        result = plugin.execute_fn(action="run")
        assert result["data"]["success"] is True
        assert "Hello" in result["data"]["text"]

    def test_plugin_manifest_fields(self, folder_loader):
        folder_loader.load_all()
        plugin = folder_loader.get_plugin("hello_plugin")
        assert plugin.name == "hello_plugin"
        assert plugin.version == "1.0.0"
        assert plugin.source == "folder"

    def test_unload_plugin(self, folder_loader):
        folder_loader.load_all()
        ok = folder_loader.unload_plugin("hello_plugin")
        assert ok is True
        assert folder_loader.get_plugin("hello_plugin") is None

    def test_unload_nonexistent_returns_false(self, folder_loader):
        ok = folder_loader.unload_plugin("does_not_exist")
        assert ok is False
