"""Read a window's explicit AppUserModelID without changing window properties.

Hosted Store applications may detach their content child when minimized. A host
window may still expose its System.AppUserModel.ID property. Absence
or errors return no identity; titles and executable names are never substituted.
"""
from __future__ import annotations

import ctypes
import sys
import uuid


class _Guid(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_uint8 * 8)]


class _PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", _Guid), ("pid", ctypes.c_uint32)]


class _CountedPointer(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("pointer", ctypes.c_void_p)]


class _VariantValue(ctypes.Union):
    # The counted pointer fixes the union size/alignment on both 32- and 64-bit.
    _fields_ = [("pointer", ctypes.c_void_p), ("integer", ctypes.c_uint64),
                ("counted", _CountedPointer)]


class _PropVariant(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_uint16), ("reserved1", ctypes.c_uint16),
                ("reserved2", ctypes.c_uint16), ("reserved3", ctypes.c_uint16),
                ("value", _VariantValue)]


_STORE_IID = _Guid.from_buffer_copy(uuid.UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)
_APP_ID_KEY = _PropertyKey(
    _Guid.from_buffer_copy(uuid.UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le), 5
)
_RPC_E_CHANGED_MODE = -2147417850


def window_app_id(hwnd: int) -> str:
    """Return explicit window AppUserModelID, or ``""`` when not observable.

    References: SHGetPropertyStoreForWindow, IPropertyStore::GetValue and
    System.AppUserModel.ID in the Microsoft Windows SDK. This is application
    identity metadata, not an authorization/security boundary.
    """
    if sys.platform != "win32" or not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd <= 0:
        return ""
    if hwnd > (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1:
        return ""
    try:
        ole = ctypes.WinDLL("ole32")
        shell = ctypes.WinDLL("shell32")
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        ole.CoInitializeEx.restype = ctypes.c_int32
        ole.CoUninitialize.argtypes = []
        ole.CoUninitialize.restype = None
        ole.PropVariantClear.argtypes = [ctypes.POINTER(_PropVariant)]
        ole.PropVariantClear.restype = ctypes.c_int32
        shell.SHGetPropertyStoreForWindow.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)
        ]
        shell.SHGetPropertyStoreForWindow.restype = ctypes.c_int32
        initialized = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
        if initialized < 0 and initialized != _RPC_E_CHANGED_MODE:
            return ""
        try:
            return _read_app_id(shell, ole, hwnd)
        finally:
            # S_OK and S_FALSE both increment this thread's COM reference count.
            if initialized >= 0:
                ole.CoUninitialize()
    except (OSError, AttributeError, ValueError, ctypes.ArgumentError):
        return ""


def _read_app_id(shell, ole, hwnd: int) -> str:
    store = ctypes.c_void_p()
    status = shell.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(_STORE_IID), ctypes.byref(store))
    if status < 0 or not store.value:
        return ""
    vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)(vtable[2])
    try:
        get_value = ctypes.WINFUNCTYPE(
            ctypes.c_int32, ctypes.c_void_p,
            ctypes.POINTER(_PropertyKey), ctypes.POINTER(_PropVariant)
        )(vtable[5])
        variant = _PropVariant()
        try:
            status = get_value(store, ctypes.byref(_APP_ID_KEY), ctypes.byref(variant))
            if status < 0 or variant.vt != 31 or not variant.value.pointer:  # VT_LPWSTR
                return ""
            value = ctypes.wstring_at(variant.value.pointer)
            # AppUserModelIDs have a maximum length of 128 characters.
            return value if 0 < len(value) <= 128 else ""
        finally:
            ole.PropVariantClear(ctypes.byref(variant))
    finally:
        release(store)
