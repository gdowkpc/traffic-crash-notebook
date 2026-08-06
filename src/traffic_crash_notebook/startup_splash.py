from __future__ import annotations

from types import ModuleType


def _packaged_splash() -> ModuleType | None:
    """Return PyInstaller's splash bridge when running a splash-enabled build."""
    try:
        import pyi_splash  # type: ignore[import-not-found]
    except (ImportError, RuntimeError):
        return None
    return pyi_splash


def close_startup_splash() -> bool:
    """Close the packaged startup splash without affecting source-mode launches."""
    splash = _packaged_splash()
    if splash is None:
        return False
    try:
        if not splash.is_alive():
            return False
        splash.close()
    except (ConnectionError, OSError, RuntimeError):
        return False
    return True
