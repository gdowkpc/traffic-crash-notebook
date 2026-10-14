from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TCN_DISABLE_UPDATE_CHECK", "1")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from traffic_crash_notebook.models import CASE_STATUSES, CaseTask, ChronologyEntry, Person, Vehicle
from traffic_crash_notebook.repository import CaseRepository
from traffic_crash_notebook.ui.main_window import MainWindow


class CaseArchiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = CaseRepository(Path(self.temp.name) / "archive-test.sqlite3")
        self.case = self.repository.create_case("ARCHIVE-TEST", "Test Investigator")
        self.window = MainWindow(self.repository)

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            if isinstance(widget, MainWindow):
                widget.loading = True
                widget.autosave_timer.stop()
            widget.close()
        self.app.processEvents()
        self.temp.cleanup()

    def visible_ids(self):
        return {
            self.window.case_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.window.case_list.count())
        }

    def show_archive(self):
        self.window.case_view.setCurrentIndex(self.window.case_view.findData("archived"))

    def test_default_view_excludes_only_closed_and_finds_legacy_closed_cases(self):
        cases = {}
        for status in CASE_STATUSES:
            case = self.repository.create_case("CASE-" + status, "Test Investigator")
            case.status = status
            self.repository.save_case(case)
            cases[status] = case.id
        self.window.refresh_cases()
        self.assertEqual(self.window.case_view.currentData(), "open")
        self.assertEqual(self.visible_ids(), {self.case.id, *(v for k, v in cases.items() if k != "Closed")})
        self.show_archive()
        self.assertEqual(self.visible_ids(), {cases["Closed"]})
        self.assertEqual(self.window.current_case.id, cases["Closed"])
        self.assertTrue(self.window.reopen_case_button.isEnabled())
        self.assertFalse(self.window.archive_case_button.isEnabled())
        self.window.case_search.setText("no-match")
        self.assertEqual(self.visible_ids(), set())
        self.window.case_search.setText("CASE-Closed")
        self.assertEqual(self.visible_ids(), {cases["Closed"]})

    def test_archive_saves_pending_entries_preserves_records_and_survives_restart(self):
        person = self.repository.save_person(Person(id="", case_id=self.case.id, first_name="Taylor"))
        vehicle = self.repository.save_vehicle(Vehicle(id="", case_id=self.case.id, make="Example"))
        task = self.repository.save_task(CaseTask(id="", case_id=self.case.id, description="Follow up"))
        journal = self.repository.save_chronology(ChronologyEntry(id="", case_id=self.case.id, summary="Test note"))
        self.window.summary.setPlainText("Pending summary to retain")
        self.window.packet_widgets["road_name"].setText("Example Road")
        self.window.archive_case_button.click()
        self.assertEqual(self.repository.get_case(self.case.id).status, "Closed")
        self.assertEqual(self.repository.get_case(self.case.id).summary, "Pending summary to retain")
        self.assertEqual(self.repository.get_crash_details(self.case.id).road_name, "Example Road")
        self.assertEqual(self.repository.list_people(self.case.id), [person])
        self.assertEqual(self.repository.list_vehicles(self.case.id), [vehicle])
        self.assertEqual(self.repository.list_tasks(self.case.id), [task])
        self.assertEqual(self.repository.list_chronology(self.case.id), [journal])
        self.assertEqual(self.repository.list_outstanding_tasks(), [])
        self.assertEqual(self.repository.list_outstanding_tasks(include_closed=True)[0].task.id, task.id)
        backup_path = self.repository.backup_to(Path(self.temp.name) / "archived-backup.sqlite3")
        backup = CaseRepository(backup_path)
        self.assertEqual(backup.get_case(self.case.id).status, "Closed")
        self.assertEqual(backup.list_people(self.case.id), [person])
        self.assertEqual(backup.list_vehicles(self.case.id), [vehicle])
        self.assertEqual(backup.list_tasks(self.case.id), [task])
        self.assertEqual(backup.list_chronology(self.case.id), [journal])
        self.assertIsNone(self.window.current_case)
        self.assertTrue(self.window.tabs.isHidden())
        self.assertEqual(self.visible_ids(), set())
        self.assertFalse(self.window.archive_case_button.isEnabled())
        restarted = MainWindow(CaseRepository(self.repository.database_path))
        self.assertEqual(restarted.case_view.currentData(), "open")
        self.assertEqual(restarted.case_list.count(), 0)
        self.show_archive()
        self.assertEqual(self.window.current_case.id, self.case.id)
        self.assertFalse(self.window.tabs.isHidden())
        self.assertEqual(self.window.summary.toPlainText(), "Pending summary to retain")
        self.window.reopen_case_button.click()
        self.assertEqual(self.window.case_view.currentData(), "open")
        self.assertEqual(self.window.current_case.id, self.case.id)
        self.assertEqual(self.repository.get_case(self.case.id).status, "Active")
        self.assertEqual(self.repository.list_tasks(self.case.id), [task])

    def test_archiving_selects_next_open_case(self):
        other = self.repository.create_case("NEXT-OPEN", "Test Investigator")
        self.window.archive_current_case()
        self.assertEqual(self.visible_ids(), {other.id})
        self.assertEqual(self.window.current_case.id, other.id)

    def test_save_failure_leaves_case_open_and_preserves_pending_entries(self):
        self.window.summary.setPlainText("Keep this unsaved note")
        with (
            patch.object(self.repository, "save_case", side_effect=sqlite3.OperationalError("Test write failure")),
            patch("traffic_crash_notebook.ui.main_window.QMessageBox.critical") as error,
        ):
            self.window.archive_current_case()
        error.assert_called_once()
        self.assertEqual(self.repository.get_case(self.case.id).status, "Active")
        self.assertEqual(self.window.current_case.status, "Active")
        self.assertEqual(self.window.status.currentText(), "Active")
        self.assertEqual(self.visible_ids(), {self.case.id})
        self.assertEqual(self.window.summary.toPlainText(), "Keep this unsaved note")
        self.assertTrue(self.window.overview_dirty)

    def test_view_switch_saves_pending_changes_and_stays_put_if_saving_fails(self):
        self.window.summary.setPlainText("Save before switching")
        with (
            patch.object(self.repository, "save_case", side_effect=sqlite3.OperationalError("Test write failure")),
            patch("traffic_crash_notebook.ui.main_window.QMessageBox.critical"),
        ):
            self.show_archive()
        self.assertEqual(self.window.case_view.currentData(), "open")
        self.assertEqual(self.window.current_case.id, self.case.id)
        self.assertEqual(self.window.summary.toPlainText(), "Save before switching")
        self.show_archive()
        self.assertEqual(self.repository.get_case(self.case.id).summary, "Save before switching")
        self.assertIsNone(self.window.current_case)

    def test_overview_status_archives_and_reopens_including_retry_after_failure(self):
        self.window.status.setCurrentText("Closed")
        with (
            patch.object(self.repository, "save_case", side_effect=sqlite3.OperationalError("Test write failure")),
            patch("traffic_crash_notebook.ui.main_window.QMessageBox.critical"),
        ):
            self.assertFalse(self.window.save_overview())
        self.assertTrue(self.window.save_overview())
        self.assertEqual(self.visible_ids(), set())
        self.assertIsNone(self.window.current_case)
        self.show_archive()
        self.window.status.setCurrentText("Review")
        self.assertTrue(self.window.save_overview())
        self.assertEqual(self.visible_ids(), set())
        self.window.case_view.setCurrentIndex(self.window.case_view.findData("open"))
        self.assertEqual(self.window.current_case.id, self.case.id)
        self.assertEqual(self.window.status.currentText(), "Review")

    def test_task_navigation_opens_archived_case_without_reopening_it(self):
        closed = self.repository.create_case("OLD-CLOSED", "Test Investigator")
        closed.status = "Closed"
        self.repository.save_case(closed)
        task = self.repository.save_task(CaseTask(id="", case_id=closed.id, description="Old follow-up"))
        self.window.summary.setPlainText("Current working note")
        self.assertTrue(self.window._open_case_task(closed.id, task.id))
        self.assertEqual(self.window.case_view.currentData(), "archived")
        self.assertEqual(self.window.current_case.id, closed.id)
        self.assertEqual(self.repository.get_case(closed.id).status, "Closed")
        self.assertEqual(self.repository.get_case(self.case.id).summary, "Current working note")
        self.assertEqual(self.window.tabs.tabText(self.window.tabs.currentIndex()), "Tasks")

    def test_new_case_from_archive_returns_to_open_view(self):
        self.window.archive_current_case()
        self.show_archive()
        with patch("traffic_crash_notebook.ui.main_window.QInputDialog.getText", return_value=("NEW-OPEN", True)):
            self.window.new_case()
        self.assertEqual(self.window.case_view.currentData(), "open")
        self.assertEqual(self.window.current_case.case_number, "NEW-OPEN")
        self.assertEqual(self.repository.get_case(self.case.id).status, "Closed")

    def test_search_refresh_keeps_unsaved_entries(self):
        self.window.summary.setPlainText("Unsaved search note")
        self.window.case_search.setText("ARCHIVE")
        self.assertEqual(self.window.summary.toPlainText(), "Unsaved search note")
        self.assertTrue(self.window.overview_dirty)

    def test_selecting_another_case_while_closing_keeps_selection_consistent(self):
        other = self.repository.create_case("NEXT-OPEN", "Test Investigator")
        self.window.refresh_cases()
        self.window.status.setCurrentText("Closed")
        for index in range(self.window.case_list.count()):
            item = self.window.case_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == other.id:
                self.window.case_list.setCurrentItem(item)
                break
        self.assertEqual(self.window.current_case.id, other.id)
        self.assertEqual(self.window.case_list.currentItem().data(Qt.ItemDataRole.UserRole), other.id)
        self.assertEqual(self.repository.get_case(self.case.id).status, "Closed")

    def test_export_after_changing_status_keeps_the_original_case(self):
        self.repository.create_case("OTHER-OPEN", "Test Investigator")
        self.window.case_search.setText("OTHER-OPEN")
        self.window.status.setCurrentText("Closed")
        destination = Path(self.temp.name) / "archived-report.pdf"
        with patch("traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
            self.window.export_pdf()
        from pypdf import PdfReader

        self.assertTrue(destination.is_file())
        self.assertIn("ARCHIVE-TEST", PdfReader(destination).pages[0].extract_text())
        self.assertEqual(self.window.current_case.id, self.case.id)
        self.assertEqual(self.window.case_view.currentData(), "archived")
        self.assertEqual(self.repository.get_case(self.case.id).status, "Closed")

    def test_failed_reopen_keeps_case_archived(self):
        self.window.archive_current_case()
        self.show_archive()
        with (
            patch.object(self.repository, "save_case", side_effect=sqlite3.OperationalError("Test write failure")),
            patch("traffic_crash_notebook.ui.main_window.QMessageBox.critical"),
        ):
            self.window.reopen_current_case()
        self.assertEqual(self.repository.get_case(self.case.id).status, "Closed")
        self.assertEqual(self.window.status.currentText(), "Closed")
        self.assertEqual(self.window.case_view.currentData(), "archived")
        self.assertEqual(self.window.current_case.id, self.case.id)


if __name__ == "__main__":
    unittest.main()
