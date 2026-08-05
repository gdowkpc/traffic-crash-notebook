from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from traffic_crash_notebook.build_info import format_about_text, load_build_info


class BuildInfoTest(unittest.TestCase):
    def test_portable_build_info_is_parsed_for_about_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "BUILD_INFO.txt"
            path.write_text(
                "\n".join((
                    "Traffic Crash Notebook 0.4.7",
                    "Portable Windows x64 build",
                    "Build ID: 0.4.7-20260805-153000",
                    "Built: 08/05/2026 15:30:00 -07:00",
                    "Build runtime: Python 3.12.10",
                )),
                encoding="utf-8-sig",
            )

            info = load_build_info(path)

            self.assertEqual(info.version, "0.4.7")
            self.assertEqual(info.build_id, "0.4.7-20260805-153000")
            self.assertEqual(info.built_at, "08/05/2026 15:30:00 -07:00")
            self.assertEqual(info.edition, "Portable Windows x64 build")
            self.assertEqual(info.runtime, "Python 3.12.10")
            about = format_about_text(info, 14)
            self.assertIn("Version: 0.4.7", about)
            self.assertIn("Build date: 08/05/2026 15:30:00 -07:00", about)
            self.assertIn("Database schema: 14", about)


if __name__ == "__main__":
    unittest.main()
