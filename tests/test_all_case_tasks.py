from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TCN_DISABLE_UPDATE_CHECK", "1")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from traffic_crash_notebook.models import CaseTask
from traffic_crash_notebook.repository import CaseRepository
from traffic_crash_notebook.ui.all_case_tasks import AllCaseTasksDialog
from traffic_crash_notebook.ui.dialogs import TaskDialog
from traffic_crash_notebook.ui.main_window import MainWindow


class AllCaseTasksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = CaseRepository(Path(self.temp.name) / "tasks.sqlite3")
        self.case = self.repository.create_case("26-ONE", "Test Investigator")
        self.other = self.repository.create_case("26-TWO", "Test Investigator")
        self.other.status = "Waiting for Records"
        self.other.location = "Example Road"
        self.repository.save_case(self.other)
        self.closed = self.repository.create_case("26-CLOSED", "Test Investigator")
        self.closed.status = "Closed"
        self.repository.save_case(self.closed)

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            if isinstance(widget, MainWindow):
                widget.loading = True
                widget.autosave_timer.stop()
            widget.close()
        self.app.processEvents()
        self.temp.cleanup()

    def task(self, description, *, case=None, due="", status="Open", category="General", notes=""):
        return self.repository.save_task(CaseTask(
            id="", case_id=(case or self.case).id, description=description,
            due_date=due, status=status, category=category, notes=notes,
        ))

    def descriptions(self, dialog):
        return [entry.task.description for entry in dialog.visible_entries]

    def test_repository_joins_case_identity_and_excludes_finished_tasks(self):
        first = self.task("Open task")
        waiting = self.task("Await records", case=self.other, status="Waiting")
        hidden = self.task("Closed case follow-up", case=self.closed)
        self.task("Finished", status="Completed")
        self.task("Unnecessary", status="Not Needed")
        self.task("Closed finished", case=self.closed, status="Completed")
        entries = self.repository.list_outstanding_tasks()
        self.assertEqual({entry.task.id for entry in entries}, {first.id, waiting.id})
        other = next(entry for entry in entries if entry.task.id == waiting.id)
        self.assertEqual((other.case_number, other.case_status, other.case_location),
                         ("26-TWO", "Waiting for Records", "Example Road"))
        self.assertEqual({entry.task.id for entry in self.repository.list_outstanding_tasks(include_closed=True)},
                         {first.id, waiting.id, hidden.id})
        self.repository.delete_case(self.other.id)
        self.assertEqual([entry.task.id for entry in self.repository.list_outstanding_tasks()], [first.id])
        self.assertIsNone(self.repository.get_task(waiting.id))

    def test_due_order_handles_legacy_dates_today_and_unparseable_dates(self):
        today = date.today()
        self.task("No deadline")
        self.task("Legacy text deadline", due="After records arrive")
        self.task("Later", due=(today + timedelta(days=8)).isoformat())
        self.task("Today", due=today.isoformat())
        self.task("Yesterday", case=self.other, due=(today - timedelta(days=1)).strftime("%m/%d/%Y"), status="Waiting")
        self.task("Oldest", due=(today - timedelta(days=3)).isoformat())
        self.task("Finished overdue", due=(today - timedelta(days=5)).isoformat(), status="Completed")
        dialog = AllCaseTasksDialog(self.repository)
        self.assertEqual(self.descriptions(dialog)[:4], ["Oldest", "Yesterday", "Today", "Later"])
        self.assertEqual(set(self.descriptions(dialog)[4:]), {"No deadline", "Legacy text deadline"})
        self.assertEqual(dialog.summary_label.text(), "6 outstanding  ·  2 overdue  ·  1 waiting")
        self.assertEqual(dialog.table.item(2, 0).text(), "Due today")
        legacy_row = self.descriptions(dialog).index("Legacy text deadline")
        self.assertEqual(dialog.table.item(legacy_row, 0).text(), "Check date")
        self.assertEqual(dialog.table.item(legacy_row, 4).text(), "After records arrive")
        self.assertFalse(dialog.edit_task_button.isEnabled())

    def test_filters_combine_and_summary_tracks_matching_tasks(self):
        today = date.today()
        target = self.task("Request records", case=self.other, category="Medical", status="Waiting",
                           due=(today - timedelta(days=1)).isoformat(), notes="Hospital contact")
        self.task("Medical review", category="Medical")
        self.task("Download video", case=self.other, category="Video")
        self.task("Closed outstanding", case=self.closed)
        dialog = AllCaseTasksDialog(self.repository)
        dialog.case_filter.setCurrentIndex(dialog.case_filter.findData(self.other.id))
        dialog.category_filter.setCurrentIndex(dialog.category_filter.findData("Medical"))
        dialog.status_filter.setCurrentText("Waiting")
        dialog.due_filter.setCurrentText("Overdue")
        dialog.search.setText("HOSPITAL")
        self.assertEqual([entry.task.id for entry in dialog.visible_entries], [target.id])
        self.assertEqual(dialog.summary_label.text(), "1 outstanding  ·  1 overdue  ·  1 waiting")
        dialog.search.setText("Example Road")
        self.assertEqual(self.descriptions(dialog), ["Request records"])
        dialog.search.setText("No matching words")
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertIn("No outstanding tasks match", dialog.result_label.text())
        self.assertFalse(dialog.open_case_button.isEnabled())

    def test_due_window_closed_case_option_and_refresh(self):
        today = date.today()
        self.task("Due today", due=today.isoformat())
        self.task("Due in seven", due=(today + timedelta(days=7)).isoformat())
        self.task("Due in eight", due=(today + timedelta(days=8)).isoformat())
        self.task("Overdue", due=(today - timedelta(days=1)).isoformat())
        self.task("No date")
        self.task("Check date", due="Tomorrow afternoon")
        self.task("Closed outstanding", case=self.closed)
        dialog = AllCaseTasksDialog(self.repository)
        dialog.due_filter.setCurrentText("Due next 7 days")
        self.assertEqual(self.descriptions(dialog), ["Due today", "Due in seven"])
        dialog.due_filter.setCurrentText("No date / check date")
        self.assertEqual(set(self.descriptions(dialog)), {"No date", "Check date"})
        dialog.due_filter.setCurrentText("All due dates")
        dialog.include_closed.setChecked(True)
        self.assertIn("Closed outstanding", self.descriptions(dialog))
        dialog.case_filter.setCurrentIndex(dialog.case_filter.findData(self.closed.id))
        self.assertEqual(self.descriptions(dialog), ["Closed outstanding"])
        dialog.include_closed.setChecked(False)
        self.assertIsNone(dialog.case_filter.currentData())
        self.assertNotIn("Closed outstanding", self.descriptions(dialog))
        self.task("Newly recorded")
        dialog.refresh_button.click()
        self.assertIn("Newly recorded", self.descriptions(dialog))

    def test_edit_updates_original_task_and_both_workspaces(self):
        task = self.task("Call witness")
        window = MainWindow(self.repository)
        window.load_case(self.case)
        dialog = AllCaseTasksDialog(self.repository, window)
        dialog.task_changed.connect(window._refresh_task_summary)
        dialog.table.selectRow(0)
        errors = []

        def complete():
            editor = self.app.activeModalWidget()
            try:
                self.assertIsInstance(editor, TaskDialog)
                editor.description.setText("Witness call completed")
                editor.status.setCurrentText("Completed")
                editor.buttons.button(QDialogButtonBox.StandardButton.Save).click()
            except BaseException as error:
                errors.append(error)
                if editor:
                    editor.reject()

        QTimer.singleShot(0, complete)
        dialog.edit_task_button.click()
        if errors:
            raise errors[0]
        saved = self.repository.get_task(task.id)
        self.assertEqual((saved.description, saved.status), ("Witness call completed", "Completed"))
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertEqual(window.tasks_table.item(0, 0).text(), "Completed")
        self.assertEqual(window.tasks_table.item(0, 2).text(), "Witness call completed")
        self.assertIn("0 open tasks", window.counts_label.text())

    def test_button_double_click_opens_exact_case_and_task_despite_sidebar_filter(self):
        task = self.task("Collect video", case=self.other)
        window = MainWindow(self.repository)
        window.load_case(self.case)
        window.case_search.setText("26-ONE")
        window.summary.setPlainText("Unsaved working note")
        errors = []

        def choose():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsInstance(dialog, AllCaseTasksDialog)
                dialog.table.selectRow(0)
                point = dialog.table.visualItemRect(dialog.table.item(0, 3)).center()
                QTest.mouseClick(dialog.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
                QTest.mouseDClick(dialog.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
                # Keep a failed UI expectation from leaving a modal test waiting.
                self.assertEqual(dialog.selected_task, (self.other.id, task.id))
            except BaseException as error:
                errors.append(error)
                if dialog:
                    dialog.reject()

        QTimer.singleShot(0, choose)
        window.all_case_tasks_button.click()
        if errors:
            raise errors[0]
        self.assertEqual(window.current_case.id, self.other.id)
        self.assertEqual(window.case_search.text(), "")
        self.assertEqual(window.tabs.tabText(window.tabs.currentIndex()), "Tasks")
        self.assertEqual(window.tasks_table.item(window.tasks_table.currentRow(), 0).data(Qt.ItemDataRole.UserRole), task.id)
        self.assertEqual(self.repository.get_case(self.case.id).summary, "Unsaved working note")

    def test_edit_uses_task_identity_across_cases_and_retains_selection_after_reordering(self):
        today = date.today()
        first = self.task("Request records", due=today.isoformat())
        target = self.task("Request records", case=self.other, due=(today + timedelta(days=1)).isoformat())
        dialog = AllCaseTasksDialog(self.repository)
        dialog.table.selectRow(1)
        errors = []

        def complete():
            editor = self.app.activeModalWidget()
            try:
                self.assertIsInstance(editor, TaskDialog)
                self.assertEqual(editor.task.id, target.id)
                editor.notes.setPlainText("Follow up with the hospital")
                editor.due_date.setText((today - timedelta(days=1)).strftime("%m/%d/%Y"))
                editor.buttons.button(QDialogButtonBox.StandardButton.Save).click()
            except BaseException as error:
                errors.append(error)
                if editor:
                    editor.reject()

        QTimer.singleShot(0, complete)
        dialog.edit_task_button.click()
        if errors:
            raise errors[0]
        self.assertEqual(self.repository.get_task(first.id).notes, "")
        self.assertEqual(self.repository.get_task(target.id).notes, "Follow up with the hospital")
        self.assertEqual(dialog.visible_entries[0].task.id, target.id)
        self.assertEqual(dialog._selected_entry().task.id, target.id)
        dialog.category_filter.setCurrentText("All categories")
        dialog.open_case_button.click()
        self.assertEqual(dialog.selected_task, (self.other.id, target.id))

    def test_cancelled_edit_preserves_original_task(self):
        task = self.task("Original task")
        dialog = AllCaseTasksDialog(self.repository)
        dialog.table.selectRow(0)
        errors = []

        def cancel():
            editor = self.app.activeModalWidget()
            try:
                self.assertIsInstance(editor, TaskDialog)
                editor.description.setText("Unsaved edit")
            except BaseException as error:
                errors.append(error)
            finally:
                if editor:
                    editor.reject()

        QTimer.singleShot(0, cancel)
        dialog.edit_task_button.click()
        if errors:
            raise errors[0]
        self.assertEqual(self.repository.get_task(task.id).description, "Original task")
        self.assertEqual(self.descriptions(dialog), ["Original task"])

    def test_failed_overview_save_prevents_opening_dashboard_or_switching_case(self):
        task = self.task("Other case task", case=self.other)
        window = MainWindow(self.repository)
        window.load_case(self.case)
        with patch.object(window, "save_overview", return_value=False), patch(
            "traffic_crash_notebook.ui.main_window.AllCaseTasksDialog"
        ) as dashboard:
            window.show_all_case_tasks()
            dashboard.assert_not_called()
            self.assertFalse(window._open_case_task(self.other.id, task.id))
        self.assertEqual(window.current_case.id, self.case.id)

    def test_missing_task_and_empty_database_leave_actions_disabled(self):
        task = self.task("Temporary task")
        dialog = AllCaseTasksDialog(self.repository)
        dialog.table.selectRow(0)
        self.repository.delete_task(task.id)
        dialog.edit_task_button.click()
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.edit_task_button.isEnabled())
        self.assertFalse(dialog.open_case_button.isEnabled())
        self.assertIn("No outstanding tasks in the included cases", dialog.result_label.text())
        window = MainWindow(self.repository)
        self.assertFalse(window._open_case_task(self.case.id, task.id))

    def test_storage_failure_clears_stale_results(self):
        self.task("Recorded task")
        dialog = AllCaseTasksDialog(self.repository)
        dialog.table.selectRow(0)
        with patch.object(self.repository, "list_outstanding_tasks", side_effect=sqlite3.OperationalError("Unavailable")), patch(
            "traffic_crash_notebook.ui.all_case_tasks.QMessageBox.critical"
        ) as warning:
            dialog.refresh()
        warning.assert_called_once()
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.open_case_button.isEnabled())
        self.assertIn("Tasks could not be loaded", dialog.result_label.text())
        dialog.search.setText("Recorded")
        self.assertEqual(dialog.summary_label.text(), "Tasks unavailable")
        self.assertIn("Tasks could not be loaded", dialog.result_label.text())
        dialog.refresh()
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.summary_label.text(), "1 outstanding  ·  0 overdue  ·  0 waiting")


if __name__ == "__main__":
    unittest.main()
