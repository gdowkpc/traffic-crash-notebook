from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TCN_DISABLE_UPDATE_CHECK", "1")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from traffic_crash_notebook.models import CASE_STATUSES, Vehicle
from traffic_crash_notebook.repository import CaseRepository
from traffic_crash_notebook.ui.case_dashboard import CaseDashboardDialog
from traffic_crash_notebook.ui.main_window import MainWindow


class CaseDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = CaseRepository(Path(self.temp.name) / "dashboard.sqlite3")

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            if isinstance(widget, MainWindow):
                widget.loading = True
                widget.autosave_timer.stop()
                widget.periodic_autosave_timer.stop()
            widget.close()
        self.app.processEvents()
        self.temp.cleanup()

    def case(self, status):
        case = self.repository.create_case("", "Test Investigator")
        case.status = status
        return self.repository.save_case(case)

    def test_counts_include_each_case_once_exclude_archived_and_keep_zero_statuses(self):
        active = self.case("Active")
        self.case("Active")
        self.case("Review")
        self.case("Inactive")
        self.case("Closed")
        for number in range(3):
            self.repository.save_vehicle(Vehicle(id="", case_id=active.id, vehicle_number=str(number)))
        counts = self.repository.case_status_counts()
        self.assertEqual(counts, {
            "Active": 2, "Waiting for Records": 0, "Analysis": 0,
            "Review": 1, "Inactive": 1,
        })
        self.assertEqual(sum(counts.values()), 4)

    def test_status_changes_archiving_reopening_and_deletion_update_totals(self):
        case = self.case("Active")
        dialog = CaseDashboardDialog(self.repository)
        self.assertEqual(dialog.total_label.text(), "1 case")
        case.status = "Analysis"
        self.repository.save_case(case)
        dialog.refresh_button.click()
        self.assertEqual((dialog.counts["Active"], dialog.counts["Analysis"]), (0, 1))
        self.assertEqual(dialog.table.cellWidget(2, 2).format(), "100.0%")
        case.status = "Closed"
        self.repository.save_case(case)
        dialog.refresh()
        self.assertEqual(dialog.total_label.text(), "0 cases")
        self.assertNotIn("Closed", dialog.counts)
        case.status = "Review"
        self.repository.save_case(case)
        dialog.refresh()
        self.assertEqual((dialog.total_label.text(), dialog.counts["Review"]), ("1 case", 1))
        self.repository.delete_case(case.id)
        dialog.refresh()
        self.assertEqual(sum(dialog.counts.values()), 0)

    def test_empty_and_legacy_statuses_do_not_hide_cases(self):
        dialog = CaseDashboardDialog(self.repository)
        self.assertEqual(dialog.total_label.text(), "0 cases")
        self.assertEqual(dialog.table.rowCount(), len(CASE_STATUSES) - 1)
        for row in range(dialog.table.rowCount()):
            self.assertEqual(dialog.table.cellWidget(row, 2).format(), "0.0%")
        self.case("")
        self.case("Legacy follow-up")
        dialog.refresh()
        self.assertEqual(dialog.total_label.text(), "2 cases")
        self.assertEqual(dialog.counts[""], 1)
        self.assertEqual(dialog.counts["Legacy follow-up"], 1)
        self.assertIn("No status entered", [dialog.table.item(r, 0).text() for r in range(dialog.table.rowCount())])

    def test_unavailable_storage_clears_stale_counts_and_refresh_recovers(self):
        self.case("Active")
        dialog = CaseDashboardDialog(self.repository)
        with patch.object(self.repository, "case_status_counts", side_effect=sqlite3.OperationalError("Drive unavailable")), patch("traffic_crash_notebook.ui.case_dashboard.QMessageBox.critical") as error:
            dialog.refresh()
        error.assert_called_once()
        self.assertEqual(dialog.counts, {})
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertEqual(dialog.total_label.text(), "Cases unavailable")
        dialog.refresh()
        self.assertEqual(dialog.total_label.text(), "1 case")

    def test_dashboard_saves_pending_status_and_ignores_case_search(self):
        active = self.case("Active")
        self.case("Waiting for Records")
        self.case("Closed")
        window = MainWindow(self.repository)
        window.load_case(active)
        window.case_search.setText("No matching cases")
        window.status.setCurrentText("Review")
        errors = []

        def inspect():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsInstance(dialog, CaseDashboardDialog)
                self.assertEqual(dialog.total_label.text(), "2 cases")
                self.assertEqual(dialog.counts["Review"], 1)
                self.assertEqual(dialog.counts["Active"], 0)
                self.assertEqual(dialog.counts["Waiting for Records"], 1)
            except BaseException as error:
                errors.append(error)
            finally:
                if dialog:
                    dialog.reject()

        QTimer.singleShot(0, inspect)
        window.case_dashboard_action.trigger()
        if errors:
            raise errors[0]
        self.assertEqual(self.repository.get_case(active.id).status, "Review")
        self.assertEqual(window.case_search.text(), "No matching cases")

    def test_dashboard_available_without_cases_but_save_failure_blocks_opening(self):
        window = MainWindow(self.repository)
        self.assertTrue(window.case_dashboard_button.isEnabled())
        self.assertIn("Dashboard", [a.text().replace("&", "") for a in window.menuBar().actions()])
        with patch("traffic_crash_notebook.ui.main_window.CaseDashboardDialog") as dashboard:
            window.case_dashboard_button.click()
            dashboard.assert_called_once_with(self.repository, window)
        with patch.object(window, "save_overview", return_value=False), patch("traffic_crash_notebook.ui.main_window.CaseDashboardDialog") as dashboard:
            window.show_case_dashboard()
            dashboard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
