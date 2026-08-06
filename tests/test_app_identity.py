from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow

from traffic_crash_notebook import __version__
from traffic_crash_notebook.resources import (
    app_icon_path,
    windows_executable_icon_path,
)
from traffic_crash_notebook.ui.app_identity import configure_application


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


if __name__ == "__main__":
    unittest.main()
