from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from traffic_crash_notebook import __version__
from traffic_crash_notebook.resources import (
    app_icon_path,
    windows_executable_icon_path,
)
from traffic_crash_notebook.ui.app_identity import application_icon, configure_application
from traffic_crash_notebook.repository import CaseRepository
from traffic_crash_notebook.ui.main_window import MainWindow
from traffic_crash_notebook.windows_identity import (
    WINDOWS_APP_USER_MODEL_ID, get_windows_app_id, set_windows_app_id,
)


class ApplicationIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_tiu_icon_loads_and_is_applied_to_the_application(self):
        self.assertTrue(app_icon_path().is_file())
        self.assertTrue(windows_executable_icon_path().is_file())
        self.assertFalse(QIcon(str(app_icon_path())).isNull())
        executable_icon = QIcon(str(windows_executable_icon_path()))
        self.assertFalse(executable_icon.isNull())
        executable_sizes = {
            (size.width(), size.height())
            for size in executable_icon.availableSizes()
        }
        self.assertIn((16, 16), executable_sizes)
        self.assertIn((256, 256), executable_sizes)

        self.assertTrue(configure_application(self.app))
        self.assertEqual(self.app.applicationName(), "Traffic Crash Notebook")
        self.assertEqual(self.app.applicationVersion(), __version__)
        self.assertEqual(self.app.organizationName(), "TrafficCrashNotebook")
        self.assertFalse(self.app.windowIcon().isNull())
        window = QMainWindow()
        self.assertFalse(window.windowIcon().isNull())
        window.close()
        available_sizes = self.app.windowIcon().availableSizes()
        self.assertTrue(available_sizes)
        self.assertGreaterEqual(max(size.width() for size in available_sizes), 256)

    def test_main_window_has_an_explicit_multi_size_tiu_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(CaseRepository(Path(directory) / "icon-test.sqlite3"))
            try:
                self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_SetWindowIcon))
                expected = QIcon(str(windows_executable_icon_path()))
                for size in (16, 32, 48, 256):
                    self.assertEqual(window.windowIcon().pixmap(size, size).toImage(),
                                     expected.pixmap(size, size).toImage())
            finally:
                window.loading = True
                window.autosave_timer.stop()
                window.periodic_autosave_timer.stop()
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_png_is_a_fallback_when_the_windows_icon_is_unavailable(self):
        with patch("traffic_crash_notebook.ui.app_identity.windows_executable_icon_path",
                   return_value=Path("missing-test-icon.ico")):
            icon = application_icon()
        self.assertFalse(icon.isNull())
        self.assertEqual(icon.pixmap(32, 32).toImage(), QIcon(str(app_icon_path())).pixmap(32, 32).toImage())

    @unittest.skipUnless(sys.platform == "win32", "Windows shell identity check")
    def test_windows_shell_reads_back_the_stable_application_identity(self):
        self.assertTrue(set_windows_app_id())
        self.assertEqual(get_windows_app_id(), WINDOWS_APP_USER_MODEL_ID)

    def test_non_windows_and_unavailable_shell_do_not_block_startup(self):
        with patch("traffic_crash_notebook.windows_identity.sys.platform", "linux"), patch(
            "traffic_crash_notebook.windows_identity.ctypes.WinDLL", create=True
        ) as loader:
            self.assertFalse(set_windows_app_id())
            self.assertIsNone(get_windows_app_id())
            loader.assert_not_called()
        with patch("traffic_crash_notebook.windows_identity.sys.platform", "win32"), patch(
            "traffic_crash_notebook.windows_identity.ctypes.WinDLL", side_effect=OSError("Unavailable"), create=True
        ):
            self.assertFalse(set_windows_app_id())
            self.assertIsNone(get_windows_app_id())

    def test_failed_windows_identity_call_is_not_reported_as_success(self):
        shell = MagicMock()
        shell.SetCurrentProcessExplicitAppUserModelID.return_value = -2147467259
        with patch("traffic_crash_notebook.windows_identity.sys.platform", "win32"), patch(
            "traffic_crash_notebook.windows_identity.ctypes.WinDLL", return_value=shell, create=True
        ):
            self.assertFalse(set_windows_app_id())
        shell.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(WINDOWS_APP_USER_MODEL_ID)

    def test_launcher_sets_windows_identity_before_constructing_qt_application(self):
        import run_app
        events = []
        fake_application = MagicMock()

        def instance():
            events.append("application instance")
            return None

        def create_application(_arguments):
            events.append("application constructed")
            return fake_application

        with patch.object(run_app.sys, "argv", ["run_app.py"]), patch.object(
            run_app, "set_windows_app_id", side_effect=lambda: events.append("windows identity")
        ), patch("PySide6.QtWidgets.QApplication") as application_class, patch(
            "traffic_crash_notebook.ui.app_identity.configure_application"
        ), patch("traffic_crash_notebook.ui.storage_setup.ensure_startup_storage", return_value=None):
            application_class.instance.side_effect = instance
            application_class.side_effect = create_application
            self.assertEqual(run_app.main(), 0)
        self.assertEqual(events, ["windows identity", "application instance", "application constructed"])


if __name__ == "__main__":
    unittest.main()
