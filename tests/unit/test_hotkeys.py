"""
tests/unit/test_hotkeys.py
==========================
Unit tests for JARVIS Global Keyboard Hotkeys manager and keybinding parser.
"""
import pytest

from jarvis.platform.hotkeys import (
    GlobalHotkeyManager,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
)


class TestGlobalHotkeyManager:
    """Test suite for keyboard shortcut combinations, registry, and triggers."""

    @pytest.fixture
    def manager(self) -> GlobalHotkeyManager:
        # Use mock mode to run deterministically in CI/test environments
        mgr = GlobalHotkeyManager(is_mock=True)
        return mgr

    def test_parse_simple_alphanumeric_combinations(self, manager: GlobalHotkeyManager) -> None:
        """Test parsing Ctrl+Shift+J combination."""
        mods, vk = manager.parse_combination("Ctrl+Shift+J")
        assert (mods & MOD_CONTROL) != 0
        assert (mods & MOD_SHIFT) != 0
        assert (mods & MOD_NOREPEAT) != 0
        assert vk == ord("J")

    def test_parse_alt_win_combinations(self, manager: GlobalHotkeyManager) -> None:
        """Test parsing Alt+Win+F5 combination."""
        mods, vk = manager.parse_combination("Alt+Win+F5")
        assert (mods & MOD_ALT) != 0
        assert (mods & MOD_WIN) != 0
        assert vk == 0x74  # VK_F5

    def test_parse_special_keys(self, manager: GlobalHotkeyManager) -> None:
        """Test parsing special keys like Space, Enter, Escape."""
        _, vk_space = manager.parse_combination("Ctrl+Space")
        assert vk_space == 0x20

        _, vk_esc = manager.parse_combination("Alt+Escape")
        assert vk_esc == 0x1B

    def test_parse_invalid_combination_raises_value_error(self, manager: GlobalHotkeyManager) -> None:
        """Test invalid key combination raises ValueError."""
        with pytest.raises(ValueError):
            manager.parse_combination("Ctrl+Shift+UnknownNonExistentKey123")

    def test_register_and_trigger_callback(self, manager: GlobalHotkeyManager) -> None:
        """Test registering a hotkey and successfully triggering its callback."""
        called = False

        def _test_cb():
            nonlocal called
            called = True

        hotkey_id = manager.register("Ctrl+Shift+J", _test_cb, "Toggle HUD Overlay")
        assert hotkey_id > 0

        # Trigger
        triggered = manager.trigger("Ctrl+Shift+J")
        assert triggered is True
        assert called is True

    def test_unregister_hotkey(self, manager: GlobalHotkeyManager) -> None:
        """Test unregistering a specific hotkey."""
        called = False
        hid = manager.register("Ctrl+Shift+M", lambda: None, "Mute")
        assert len(manager.list_hotkeys()) == 1

        res = manager.unregister(hid)
        assert res is True
        assert len(manager.list_hotkeys()) == 0

    def test_unregister_all_hotkeys(self, manager: GlobalHotkeyManager) -> None:
        """Test bulk unregistering of all shortcuts."""
        manager.register("Ctrl+Shift+A", lambda: None)
        manager.register("Ctrl+Shift+B", lambda: None)
        manager.register("Ctrl+Shift+C", lambda: None)
        assert len(manager.list_hotkeys()) == 3

        manager.unregister_all()
        assert len(manager.list_hotkeys()) == 0

    def test_lifecycle_start_stop(self, manager: GlobalHotkeyManager) -> None:
        """Test starting and stopping manager lifecycle."""
        manager.start()
        assert manager._running is True

        manager.stop()
        assert manager._running is False
