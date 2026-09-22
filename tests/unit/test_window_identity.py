"""Read-only Windows property-store identity, including COM ownership."""
from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest


def test_window_identity_api_exists():
    from jarvis.platform import window_identity

    assert callable(window_identity.window_app_id)


@pytest.mark.parametrize("hwnd", [0, -1, None, "123", True])
def test_invalid_window_handle_has_no_identity(hwnd):
    from jarvis.platform.window_identity import window_app_id

    assert window_app_id(hwnd) == ""


def test_non_windows_has_no_identity(monkeypatch):
    from jarvis.platform import window_identity

    monkeypatch.setattr(window_identity.sys, "platform", "linux")
    assert window_identity.window_app_id(123) == ""


class NativeStore:
    """Emulate only the native ABI; exercise production COM cleanup unchanged."""

    def __init__(self, module, *, value="Package_Test!App", variant_type=31,
                 initialize=0, acquire=0, get_value=0):
        self.events = []
        self.keys = []
        self.text = ctypes.create_unicode_buffer(value)
        callback = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
        release_type = callback(ctypes.c_uint32, ctypes.c_void_p)
        get_type = callback(ctypes.c_int32, ctypes.c_void_p,
                            ctypes.POINTER(module._PropertyKey),
                            ctypes.POINTER(module._PropVariant))

        def release(pointer):
            self.events.append("release")
            return 0

        def get(pointer, key, result):
            self.events.append("get")
            self.keys.append((bytes(key.contents.fmtid), key.contents.pid))
            result.contents.vt = variant_type
            result.contents.value.pointer = ctypes.addressof(self.text)
            return get_value

        self.release = release_type(release)
        self.get = get_type(get)
        self.vtable = (ctypes.c_void_p * 8)()
        self.vtable[2] = ctypes.cast(self.release, ctypes.c_void_p).value
        self.vtable[5] = ctypes.cast(self.get, ctypes.c_void_p).value
        self.interface = ctypes.pointer(ctypes.cast(self.vtable, ctypes.POINTER(ctypes.c_void_p)))

        def init(reserved, mode):
            self.events.append("initialize")
            return initialize

        def uninit():
            self.events.append("uninitialize")

        def acquire_store(hwnd, iid, result):
            self.events.append("acquire")
            if acquire >= 0:
                ctypes.cast(result, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.cast(
                    self.interface, ctypes.c_void_p
                )
            return acquire

        def clear(result):
            self.events.append("clear")
            return 0

        self.ole = SimpleNamespace(CoInitializeEx=init, CoUninitialize=uninit,
                                   PropVariantClear=clear)
        self.shell = SimpleNamespace(SHGetPropertyStoreForWindow=acquire_store)

    def install(self, module, monkeypatch):
        monkeypatch.setattr(module.sys, "platform", "win32")
        monkeypatch.setattr(module.ctypes, "WinDLL", lambda name, **kw:
                            self.ole if name == "ole32" else self.shell, raising=False)
        monkeypatch.setattr(module.ctypes, "WINFUNCTYPE",
                            getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE), raising=False)


def test_native_identity_reads_correct_key_and_releases_memory(monkeypatch):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(0x123456789) == "Package_Test!App"
    assert native.keys == [(bytes.fromhex("55284c9f799f394ba8d0e1d42de1d5f3"), 5)]
    assert native.events == ["initialize", "acquire", "get", "clear", "release", "uninitialize"]


@pytest.mark.parametrize("variant_type", [0, 3, 8])
def test_non_lpwstr_property_fails_closed_and_cleans_up(monkeypatch, variant_type):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity, variant_type=variant_type)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(123) == ""
    assert native.events[-3:] == ["clear", "release", "uninitialize"]


def test_failed_get_value_is_not_identity_and_still_cleans_up(monkeypatch):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity, get_value=-2147467259)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(123) == ""
    assert native.events[-3:] == ["clear", "release", "uninitialize"]


def test_failed_property_store_does_not_release_unowned_pointer(monkeypatch):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity, acquire=-2147467259)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(123) == ""
    assert native.events == ["initialize", "acquire", "uninitialize"]


def test_changed_com_apartment_does_not_uninitialize_caller(monkeypatch):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity, initialize=-2147417850)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(123) == "Package_Test!App"
    assert "uninitialize" not in native.events
    assert native.events[-2:] == ["clear", "release"]


def test_existing_same_apartment_is_balanced(monkeypatch):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity, initialize=1)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(123) == "Package_Test!App"
    assert native.events[-1] == "uninitialize"


def test_failed_com_initialization_is_fail_closed(monkeypatch):
    from jarvis.platform import window_identity

    native = NativeStore(window_identity, initialize=-2147467259)
    native.install(window_identity, monkeypatch)
    assert window_identity.window_app_id(123) == ""
    assert native.events == ["initialize"]


def test_missing_native_library_is_fail_closed(monkeypatch):
    from jarvis.platform import window_identity

    monkeypatch.setattr(window_identity.sys, "platform", "win32")

    def missing(*args, **kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(window_identity.ctypes, "WinDLL", missing, raising=False)
    assert window_identity.window_app_id(123) == ""
