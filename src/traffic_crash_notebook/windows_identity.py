from __future__ import annotations

import ctypes
import sys


# Keep the taskbar identity stable when a portable folder or version changes.
WINDOWS_APP_USER_MODEL_ID = "TrafficCrashNotebook.Desktop"


def set_windows_app_id() -> bool:
    """Identify this process to Windows before creating the application UI."""
    if sys.platform != "win32":
        return False
    try:
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        setter = shell.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        return setter(WINDOWS_APP_USER_MODEL_ID) == 0
    except (AttributeError, OSError):
        # An unavailable shell API must not prevent access to saved cases.
        return False


def get_windows_app_id() -> str | None:
    """Read back the process identity for Windows build qualification."""
    if sys.platform != "win32":
        return None
    try:
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        ole = ctypes.WinDLL("ole32", use_last_error=True)
        getter = shell.GetCurrentProcessExplicitAppUserModelID
        getter.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        getter.restype = ctypes.c_long
        free = ole.CoTaskMemFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = None
        value = ctypes.c_void_p()
        if getter(ctypes.byref(value)) != 0 or not value.value:
            return None
        try:
            return ctypes.wstring_at(value)
        finally:
            free(value)
    except (AttributeError, OSError):
        return None
