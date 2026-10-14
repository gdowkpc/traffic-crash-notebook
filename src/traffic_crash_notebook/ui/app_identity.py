from __future__ import annotations

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .. import __version__
from ..resources import app_icon_path, windows_executable_icon_path
from ..windows_identity import set_windows_app_id


def application_icon() -> QIcon:
    """Use the same multi-size TIU icon for Windows and the application UI."""
    icon = QIcon(str(windows_executable_icon_path()))
    if icon.isNull():
        icon = QIcon(str(app_icon_path()))
    return icon


def configure_application(application: QApplication) -> bool:
    """Apply stable application metadata and the bundled TIU window icon."""
    set_windows_app_id()
    application.setApplicationName("Traffic Crash Notebook")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("TrafficCrashNotebook")
    application.setFont(QFont("Segoe UI", 9))

    icon = application_icon()
    if icon.isNull():
        return False
    application.setWindowIcon(icon)
    return True
