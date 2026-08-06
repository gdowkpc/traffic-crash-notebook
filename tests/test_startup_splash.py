from __future__ import annotations

import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

from traffic_crash_notebook.startup_splash import close_startup_splash


class StartupSplashTest(unittest.TestCase):
    def test_source_mode_without_pyinstaller_splash_is_a_safe_noop(self):
        with patch.dict(sys.modules, {"pyi_splash": None}):
            self.assertFalse(close_startup_splash())

    def test_live_packaged_splash_is_closed(self):
        splash = ModuleType("pyi_splash")
        splash.is_alive = Mock(return_value=True)
        splash.close = Mock()

        with patch.dict(sys.modules, {"pyi_splash": splash}):
            self.assertTrue(close_startup_splash())

        splash.is_alive.assert_called_once_with()
        splash.close.assert_called_once_with()

    def test_inactive_or_broken_splash_does_not_block_startup(self):
        inactive = ModuleType("pyi_splash")
        inactive.is_alive = Mock(return_value=False)
        inactive.close = Mock()
        with patch.dict(sys.modules, {"pyi_splash": inactive}):
            self.assertFalse(close_startup_splash())
        inactive.close.assert_not_called()

        broken = ModuleType("pyi_splash")
        broken.is_alive = Mock(side_effect=ConnectionError("splash unavailable"))
        broken.close = Mock()
        with patch.dict(sys.modules, {"pyi_splash": broken}):
            self.assertFalse(close_startup_splash())


if __name__ == "__main__":
    unittest.main()
