from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from traffic_crash_notebook import __version__
from traffic_crash_notebook.repository import CaseRepository


def _run_self_test() -> int:
    destination = None
    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        if index + 1 < len(sys.argv) and not sys.argv[index + 1].startswith("--"):
            destination = Path(sys.argv[index + 1])
    if destination is None:
        destination = Path(tempfile.gettempdir()) / "TrafficCrashNotebook-SelfTest"
    try:
        from traffic_crash_notebook.self_test import run_self_test

        run_self_test(destination)
        return 0
    except Exception:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "portable_self_test.txt").write_text(
            "FAIL\n\n" + traceback.format_exc(), encoding="utf-8"
        )
        return 1


def main() -> int:
    if "--self-test" in sys.argv:
        return _run_self_test()
    if "--data-dir" in sys.argv:
        index = sys.argv.index("--data-dir")
        if index + 1 >= len(sys.argv) or sys.argv[index + 1].startswith("--"):
            print("--data-dir requires a folder path", file=sys.stderr)
            return 2
        os.environ["TCN_DATA_DIR"] = str(Path(sys.argv[index + 1]).resolve())
        del sys.argv[index:index + 2]
    try:
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication, QMessageBox
        from traffic_crash_notebook.ui.main_window import run
        from traffic_crash_notebook.ui.storage_setup import ensure_startup_storage
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print("PySide6 is required. Run: python -m pip install -r requirements.txt", file=sys.stderr)
            return 2
        raise
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Traffic Crash Notebook")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("TrafficCrashNotebook")
    app.setFont(QFont("Segoe UI", 9))
    try:
        storage = ensure_startup_storage()
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Traffic Crash Notebook could not start",
            f"The data storage location could not be prepared.\n\n{exc}",
        )
        return 1
    if storage is None:
        return 0
    repository = CaseRepository(storage.database_path)
    return run(repository)


if __name__ == "__main__":
    raise SystemExit(main())
