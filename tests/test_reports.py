from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TCN_DISABLE_UPDATE_CHECK", "1")

from pypdf import PdfReader
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from traffic_crash_notebook.models import Vehicle
from traffic_crash_notebook.repository import SCHEMA_VERSION, CaseRepository
from traffic_crash_notebook.reports import export_rivergate_report_pdf
from traffic_crash_notebook.ui.main_window import MainWindow
from traffic_crash_notebook.ui.dialogs import VehicleDialog
from traffic_crash_notebook.ui.reports import RivergateReportDialog


class ReportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = CaseRepository(self.root / "reports.sqlite3")
        self.case = self.repository.create_case("26-REPORT", "Test Investigator")
        self.case.crash_date = "2026-10-01"
        self.repository.save_case(self.case)
        self.closed = self.repository.create_case("26-ARCHIVED", "Other Investigator")
        self.closed.status = "Closed"
        self.repository.save_case(self.closed)

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            if isinstance(widget, MainWindow):
                widget.loading = True
                widget.autosave_timer.stop()
                widget.periodic_autosave_timer.stop()
            widget.close()
        self.app.processEvents()
        self.temp.cleanup()

    def vehicle(self, *, case=None, **values):
        defaults = dict(vehicle_number="1", year="2020", make="Example", model="Sedan",
                        plate="TEST123", plate_state="OR", vin="TESTVIN12345678901",
                        towed=True, tow_information="Rivergate")
        defaults.update(values)
        return self.repository.save_vehicle(Vehicle(id="", case_id=(case or self.case).id, **defaults))

    def test_report_requires_towed_rivergate_and_unreleased_including_archived(self):
        active = self.vehicle(tow_information="  rIvErGaTe Evidence Storage  ")
        archived = self.vehicle(case=self.closed)
        self.vehicle(released=True)
        self.vehicle(towed=False)
        self.vehicle(tow_information="Other Yard")
        self.vehicle(tow_information="")
        entries = self.repository.list_unreleased_towed_vehicles()
        self.assertEqual({e.vehicle.id for e in entries}, {active.id, archived.id})
        entry = next(e for e in entries if e.vehicle.id == active.id)
        self.assertEqual((entry.case_number, entry.investigator, entry.crash_date),
                         ("26-REPORT", "Test Investigator", "2026-10-01"))
        self.assertIs(entry.vehicle.released, False)
        self.assertEqual([e.vehicle.id for e in self.repository.list_unreleased_towed_vehicles(include_closed=False)], [active.id])
        active.released = True
        self.repository.save_vehicle(active)
        self.assertEqual([e.vehicle.id for e in self.repository.list_unreleased_towed_vehicles()], [archived.id])
        self.repository.delete_case(self.closed.id)
        self.assertEqual(self.repository.list_unreleased_towed_vehicles(), [])

    def test_destination_query_treats_wildcards_as_literal_text(self):
        self.vehicle()
        for destination in ("%", "_", "Rivergate' OR 1=1 --"):
            self.assertEqual(self.repository.list_unreleased_towed_vehicles(destination), [])
        with self.assertRaises(ValueError):
            self.repository.list_unreleased_towed_vehicles(" ")

    def test_schema_36_migration_preserves_vehicle_and_adds_blank_tow_number(self):
        original = self.vehicle(notes="Preserve this vehicle and its tow details")
        with self.repository._connect() as connection:
            connection.execute("ALTER TABLE vehicles DROP COLUMN tow_number")
            connection.execute("PRAGMA user_version = 36")
        migrated = CaseRepository(self.repository.database_path)
        loaded = migrated.get_vehicle(original.id)
        self.assertEqual(loaded.tow_number, "")
        self.assertEqual(loaded.notes, original.notes)
        self.assertTrue(loaded.towed)
        self.assertEqual(loaded.tow_information, "Rivergate")
        loaded.tow_number = "000123-RG/26"
        migrated.save_vehicle(loaded)
        reopened = CaseRepository(self.repository.database_path)
        self.assertEqual(reopened.get_vehicle(original.id).tow_number, "000123-RG/26")
        self.assertEqual(reopened.list_unreleased_towed_vehicles()[0].vehicle.tow_number, "000123-RG/26")
        with reopened._connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_tow_number_round_trip_edit_search_and_release_history(self):
        vehicle = self.vehicle(tow_number="000123-RG/26")
        editor = VehicleDialog(self.case.id, [], vehicle)
        self.assertEqual(editor.tow_number.text(), "000123-RG/26")
        editor.tow_number.setText("  000456-RG/26  ")
        self.repository.save_vehicle(editor.result_record())
        window = MainWindow(self.repository)
        window.load_case(self.case)
        self.assertIn("Tow number: 000456-RG/26", window.vehicles_table.item(0, 5).text())
        self.vehicle(tow_number="OTHER")
        dialog = RivergateReportDialog(self.repository)
        dialog.search.setText("000456-rg/26")
        self.assertEqual([entry.vehicle.id for entry in dialog.visible_entries], [vehicle.id])
        column = next(i for i in range(dialog.table.columnCount()) if dialog.table.horizontalHeaderItem(i).text() == "Tow number")
        self.assertEqual(dialog.table.item(0, column).text(), "000456-RG/26")
        output = self.root / "tow-number.pdf"
        dialog._write_pdf(output)
        text = PdfReader(output).pages[0].extract_text()
        self.assertIn("Tow number", text)
        self.assertIn("000456-RG/26", text)
        self.assertNotIn("OTHER", text)
        editor = VehicleDialog(self.case.id, [], self.repository.get_vehicle(vehicle.id))
        editor.vehicle_workflow_boxes["released"].setChecked(True)
        self.repository.save_vehicle(editor.result_record())
        self.assertEqual(self.repository.get_vehicle(vehicle.id).tow_number, "000456-RG/26")
        dialog.refresh()
        self.assertEqual(dialog.table.rowCount(), 0)

    def test_dialog_filters_refreshes_and_keeps_vehicle_identity(self):
        active = self.vehicle(plate="ACTIVE")
        archived = self.vehicle(case=self.closed, plate="ARCHIVED")
        dialog = RivergateReportDialog(self.repository)
        self.assertTrue(dialog.include_closed.isChecked())
        self.assertEqual(dialog.table.rowCount(), 2)
        dialog.search.setText("active")
        self.assertEqual([e.vehicle.id for e in dialog.visible_entries], [active.id])
        dialog.table.selectRow(0)
        dialog.refresh()
        self.assertEqual(dialog._selected_identity(), (active.case_id, active.id))
        dialog.search.clear()
        dialog.include_closed.setChecked(False)
        self.assertEqual([e.vehicle.id for e in dialog.visible_entries], [active.id])
        dialog.include_closed.setChecked(True)
        dialog.search.setText("ARCHIVED")
        dialog.table.selectRow(0)
        dialog.open_vehicle_button.click()
        self.assertEqual(dialog.selected_vehicle, (archived.case_id, archived.id))

    def test_storage_failure_clears_results_and_blocks_export_then_recovers(self):
        self.vehicle()
        dialog = RivergateReportDialog(self.repository)
        dialog.table.selectRow(0)
        with patch.object(self.repository, "list_unreleased_towed_vehicles", side_effect=sqlite3.OperationalError("Drive unavailable")), patch("traffic_crash_notebook.ui.reports.QMessageBox.critical"), patch("traffic_crash_notebook.ui.reports.QFileDialog.getSaveFileName") as chooser:
            dialog.save_pdf()
            chooser.assert_not_called()
        self.assertEqual(dialog.table.rowCount(), 0)
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertFalse(dialog.print_button.isEnabled())
        self.assertFalse(dialog.open_vehicle_button.isEnabled())
        self.assertEqual(dialog.summary_label.text(), "Report unavailable")
        dialog.refresh()
        self.assertTrue(dialog.export_button.isEnabled())
        self.assertEqual(dialog.table.rowCount(), 1)

    def test_save_pdf_refreshes_status_and_exports_only_search_results(self):
        released_later = self.vehicle(plate="LATER")
        self.vehicle(plate="INCLUDED")
        self.vehicle(case=self.closed, plate="EXCLUDED")
        dialog = RivergateReportDialog(self.repository)
        released_later.released = True
        self.repository.save_vehicle(released_later)
        dialog.search.setText("INCLUDED")
        output = self.root / "report.pdf"
        with patch("traffic_crash_notebook.ui.reports.QFileDialog.getSaveFileName", return_value=(str(output), "PDF")) as chooser, patch("traffic_crash_notebook.ui.reports.QDesktopServices.openUrl"):
            dialog.save_pdf()
        self.assertEqual(Path(chooser.call_args.args[2]).parent, self.root / "Reports")
        text = "\n".join(p.extract_text() for p in PdfReader(output).pages)
        self.assertIn("INCLUDED", text)
        self.assertIn("Search filter: INCLUDED", text)
        self.assertIn("including archived", text)
        self.assertNotIn("EXCLUDED", text)
        self.assertNotIn("LATER", text)
        self.assertEqual(len(dialog.entries), 2)

    def test_pdf_empty_long_and_multiple_pages_repeat_headers(self):
        output = self.root / "report.pdf"
        export_rivergate_report_pdf([], output, include_closed=False)
        text = PdfReader(output).pages[0].extract_text()
        self.assertIn("No unreleased vehicles", text)
        self.assertIn("archived cases excluded", text)
        for number in range(55):
            self.vehicle(vehicle_number=str(number), tow_information="Rivergate <Evidence> & Storage\n" + "Long destination details " * 8)
        export_rivergate_report_pdf(self.repository.list_unreleased_towed_vehicles(), output)
        pages = PdfReader(output).pages
        self.assertGreater(len(pages), 1)
        for number, page in enumerate(pages, 1):
            text = page.extract_text()
            self.assertIn("Investigator", text)
            self.assertIn("Tow number", text)
            self.assertIn(f"Page {number}", text)
        self.assertIn("Rivergate <Evidence> & Storage", " ".join(pages[0].extract_text().split()))

    def test_failed_pdf_preserves_previous_file_and_removes_temporary_file(self):
        output = self.root / "report.pdf"
        output.write_bytes(b"previous report")
        with patch("traffic_crash_notebook.reports.SimpleDocTemplate.build", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                export_rivergate_report_pdf([], output)
        self.assertEqual(output.read_bytes(), b"previous report")
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_print_uses_generated_pdf_and_honors_cancel(self):
        self.vehicle()
        dialog = RivergateReportDialog(self.repository)
        for result in (QDialog.DialogCode.Rejected, QDialog.DialogCode.Accepted):
            with patch("traffic_crash_notebook.ui.reports.QPrintDialog.exec", return_value=result), patch("traffic_crash_notebook.ui.reports.print_pdf_document") as printer, patch("traffic_crash_notebook.ui.reports.QMessageBox.critical") as error:
                dialog.print_report()
                error.assert_not_called()
                self.assertEqual(printer.call_count, int(result == QDialog.DialogCode.Accepted))

    def test_reports_menu_saves_case_and_opens_exact_archived_vehicle(self):
        self.vehicle()  # Same vehicle number as the archived target.
        target = self.vehicle(case=self.closed)
        window = MainWindow(self.repository)
        window.load_case(self.case)
        window.summary.setPlainText("Working note before report")
        window.case_search.setText("26-REPORT")
        self.assertIn("Reports", [a.text().replace("&", "") for a in window.menuBar().actions()])
        errors = []

        def choose():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsInstance(dialog, RivergateReportDialog)
                dialog.search.setText("26-ARCHIVED")
                dialog.table.selectRow(0)
                dialog.open_vehicle_button.click()
            except BaseException as error:
                errors.append(error)
                if dialog:
                    dialog.reject()

        QTimer.singleShot(0, choose)
        window.rivergate_report_action.trigger()
        if errors:
            raise errors[0]
        self.assertEqual(window.current_case.id, self.closed.id)
        self.assertEqual(window.case_view.currentData(), "archived")
        self.assertEqual(window.case_search.text(), "")
        self.assertEqual(window.tabs.currentWidget(), window.vehicles_table.parentWidget())
        row = window.vehicles_table.currentRow()
        self.assertEqual(window.vehicles_table.item(row, 0).data(Qt.ItemDataRole.UserRole), target.id)
        self.assertEqual(self.repository.get_case(self.case.id).summary, "Working note before report")
        self.assertEqual(self.repository.get_case(self.closed.id).status, "Closed")

    def test_failed_case_save_prevents_reports_and_navigation(self):
        target = self.vehicle(case=self.closed)
        window = MainWindow(self.repository)
        with patch.object(window, "save_overview", return_value=False), patch("traffic_crash_notebook.ui.main_window.RivergateReportDialog") as report:
            window.show_rivergate_report()
            report.assert_not_called()
            self.assertFalse(window._open_report_vehicle(self.closed.id, target.id))
        self.assertFalse(window._open_report_vehicle(self.case.id, target.id))


if __name__ == "__main__":
    unittest.main()
