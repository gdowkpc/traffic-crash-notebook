from __future__ import annotations

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .. import __version__
from ..resources import app_icon_path


def configure_application(application: QApplication) -> bool:
    """Apply stable application metadata and the bundled TIU window icon."""
    application.setApplicationName("Traffic Crash Notebook")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("TrafficCrashNotebook")
    application.setFont(QFont("Segoe UI", 9))

    icon = QIcon(str(app_icon_path()))
    if icon.isNull():
        return False
    application.setWindowIcon(icon)
    return True


def configure_exchange_application(application: QApplication) -> bool:
    """Apply metadata for the disposable standalone exchange-report tool."""

    application.setApplicationName("CrashX Idaho")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("CrashX")
    application.setFont(QFont("Segoe UI", 9))

    icon = QIcon(str(app_icon_path()))
    if icon.isNull():
        return False
    application.setWindowIcon(icon)
    return True
