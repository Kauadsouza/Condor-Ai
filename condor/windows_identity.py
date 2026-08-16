"""Identidade explicita do Condor para agrupamento e relance na taskbar."""

from __future__ import annotations

import ctypes
import os
import time
import uuid
from ctypes import wintypes
from pathlib import Path

APP_ID = "ARTX.Condor.Local"
PROPERTY_FORMAT_ID = "9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"
IID_PROPERTY_STORE = "886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"


class Guid(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    ]


class PropertyKey(ctypes.Structure):
    _fields_ = [("format_id", Guid), ("property_id", wintypes.DWORD)]


class PropVariant(ctypes.Structure):
    _fields_ = [
        ("value_type", wintypes.USHORT),
        ("reserved1", wintypes.USHORT),
        ("reserved2", wintypes.USHORT),
        ("reserved3", wintypes.USHORT),
        ("string_value", wintypes.LPWSTR),
    ]


def _guid(value: str) -> Guid:
    parsed = uuid.UUID(value)
    return Guid(
        parsed.time_low,
        parsed.time_mid,
        parsed.time_hi_version,
        (ctypes.c_ubyte * 8)(*parsed.bytes[8:]),
    )


def prepare_process() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def apply_window(title: str, root: str | Path) -> bool:
    if os.name != "nt":
        return False
    try:
        return _apply_window(title, Path(root))
    except Exception:
        return False


def _apply_window(title: str, root: Path) -> bool:
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    ole32.CoInitializeEx(None, 0x2)
    try:
        user32.FindWindowW.restype = wintypes.HWND
        window = None
        for _ in range(50):
            window = user32.FindWindowW(None, title)
            if window:
                break
            time.sleep(0.1)
        if not window:
            return False

        pointer = ctypes.c_void_p()
        iid = _guid(IID_PROPERTY_STORE)
        shell32.SHGetPropertyStoreForWindow.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(Guid),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        result = shell32.SHGetPropertyStoreForWindow(
            window, ctypes.byref(iid), ctypes.byref(pointer)
        )
        if result != 0 or not pointer.value:
            return False

        query_interface = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p)
        )
        add_ref = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        get_count = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))
        get_at = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PropertyKey)
        )
        get_value = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PropertyKey), ctypes.POINTER(PropVariant)
        )
        set_value = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PropertyKey), ctypes.POINTER(PropVariant)
        )
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)

        class PropertyStoreVTable(ctypes.Structure):
            _fields_ = [
                ("query_interface", query_interface),
                ("add_ref", add_ref),
                ("release", release),
                ("get_count", get_count),
                ("get_at", get_at),
                ("get_value", get_value),
                ("set_value", set_value),
                ("commit", commit),
            ]

        vtable_pointer = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(PropertyStoreVTable)))
        vtable = vtable_pointer.contents.contents
        format_id = _guid(PROPERTY_FORMAT_ID)
        icon = root / "condor" / "ui" / "assets" / "condor-logo.ico"
        launcher = root / "Condor.exe"
        properties = (
            (2, f'"{launcher}"'),
            (3, f"{icon},0"),
            (5, APP_ID),
        )
        for property_id, value in properties:
            key = PropertyKey(format_id, property_id)
            buffer = ctypes.create_unicode_buffer(value)
            variant = PropVariant(31, 0, 0, 0, ctypes.cast(buffer, wintypes.LPWSTR))
            if vtable.set_value(pointer, ctypes.byref(key), ctypes.byref(variant)) != 0:
                return False
        return vtable.commit(pointer) == 0
    finally:
        if "vtable" in locals() and "pointer" in locals() and pointer.value:
            vtable.release(pointer)
        ole32.CoUninitialize()
