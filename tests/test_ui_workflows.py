from __future__ import annotations

import os
import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TCN_DISABLE_UPDATE_CHECK", "1")

from pypdf import PdfReader
from PySide6.QtCore import QDir, Qt, QTimer
from PySide6.QtGui import QPageSize, QPalette
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolBar,
)

from traffic_crash_notebook import __version__
from traffic_crash_notebook.models import (
    CaseTask,
    ChronologyEntry,
    ContactRelationship,
    DriverProfile,
    HitRunPersonLead,
    HitRunVehicleLead,
    MotorcycleInspection,
    ParticipantDetails,
    Person,
    PropertyReceipt,
    Vehicle,
    WitnessDetails,
)
from traffic_crash_notebook.repository import SCHEMA_VERSION, CaseRepository, new_id
from traffic_crash_notebook.updates import PortableRelease, UpdateManifest
from traffic_crash_notebook.ui.dialogs import (
    ChargeDispositionDialog,
    ChronologyDialog,
    ContactRelationshipDialog,
    DriverProfileDialog,
    HitRunEvidenceDialog,
    HitRunPersonLeadDialog,
    HitRunVehicleLeadDialog,
    MotorcycleInspectionDialog,
    ParticipantDetailsDialog,
    PersonDialog,
    PropertyReceiptDialog,
    PropertyReceiptItemDialog,
    RoadwayDialog,
    SurfaceObservationDialog,
    TaskDialog,
    VehicleDialog,
    VehicleInspectionDialog,
    VideoSourceDialog,
    VRUAnalysisDialog,
    WitnessDetailsDialog,
)
from traffic_crash_notebook.ui.main_window import ApplicationSettingsDialog, MainWindow
from traffic_crash_notebook.ui.spellcheck_text_edit import (
    SpellCheckedLineEdit,
    SpellCheckedTextEdit,
)


class AddRecordWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = CaseRepository(Path(self.temp.name) / "ui-test.sqlite3")
        self.case = self.repository.create_case("UI-TEST", "Automated Test")
        self.window = MainWindow(self.repository)
        self.window.show()
        self.app.processEvents()
        if self.window.current_case is None:
            self.window.case_list.setCurrentRow(0)
            self.app.processEvents()
        self.assertEqual(self.window.current_case.id, self.case.id)

    def test_preview_workspaces_use_the_system_temp_folder(self):
        expected_parent = Path(QDir.tempPath()).resolve()
        self.assertEqual(
            Path(self.window.packet_preview_directory.path()).resolve().parent,
            expected_parent,
        )
        self.assertEqual(
            Path(self.window.exchange_preview_directory.path()).resolve().parent,
            expected_parent,
        )

    def test_selected_case_uses_readable_text_with_or_without_focus(self):
        self.window.case_list.setCurrentRow(0)
        self.app.processEvents()

        palette = self.window.case_list.palette()
        for color_group in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
        ):
            self.assertEqual(
                palette.color(color_group, QPalette.ColorRole.Highlight).name().lower(),
                "#2e6f95",
            )
            self.assertEqual(
                palette.color(
                    color_group,
                    QPalette.ColorRole.HighlightedText,
                ).name().lower(),
                "#ffffff",
            )

        style_sheet = self.window.styleSheet()
        self.assertIn("QListWidget::item:selected:!active", style_sheet)
        self.assertIn("background: #2e6f95; color: #ffffff", style_sheet)

    def test_case_picker_displays_incident_location_before_date_and_status(self):
        case = self.window.current_case
        self.assertIsNotNone(case)
        case.crash_date = "2026-08-05"
        case.location = "East Burnside Street / 122nd Avenue"
        self.repository.save_case(case)
        self.window._update_case_item(case)

        item = next(
            self.window.case_list.item(index)
            for index in range(self.window.case_list.count())
            if self.window.case_list.item(index).data(Qt.ItemDataRole.UserRole)
            == self.case.id
        )
        self.assertEqual(
            item.text(),
            "UI-TEST\nEast Burnside Street / 122nd Avenue  |  08/05/2026  -  Active",
        )

    def tearDown(self):
        self.window.loading = True
        self.window.autosave_timer.stop()
        for widget in self.app.topLevelWidgets():
            widget.close()
        self.app.processEvents()
        self.window.autosave_timer.stop()
        self.temp.cleanup()

    def _complete_modal_dialog(self, action, dialog_type, configure) -> None:
        errors: list[BaseException] = []

        def complete() -> None:
            dialog = self.app.activeModalWidget()
            try:
                if not isinstance(dialog, dialog_type):
                    raise AssertionError(
                        f"Expected {dialog_type.__name__}, got {type(dialog).__name__}"
                    )
                configure(dialog)
                save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
                save.click()
            except BaseException as exc:
                errors.append(exc)
                if isinstance(dialog, QDialog):
                    dialog.reject()

        QTimer.singleShot(0, complete)
        action()
        if errors:
            raise errors[0]

    def test_add_person_persists_and_refreshes_table(self):
        def configure(dialog: PersonDialog) -> None:
            form = dialog.root.itemAt(0).layout()
            self.assertIsInstance(form, QFormLayout)
            ordered_fields = (
                dialog.address,
                dialog.city,
                dialog.state,
                dialog.zip_code,
                dialog.cell_phone,
                dialog.home_phone,
                dialog.work_phone,
                dialog.email,
            )
            rows = [form.getWidgetPosition(field)[0] for field in ordered_fields]
            self.assertEqual(rows, list(range(rows[0], rows[0] + len(rows))))
            dialog.first_name.setText("Alex")
            dialog.last_name.setText("Tester")
            dialog.dob.setText("08/05/1985")
            dialog.address.setPlainText("123 Example Street")
            dialog.city.setText("Portland")
            dialog.state.setText("OR")
            dialog.zip_code.setText("97201-1234")
            dialog.role_boxes["Driver"].setChecked(True)
            self.assertIn("Motorcyclist", dialog.role_boxes)
            dialog.role_boxes["Motorcyclist"].setChecked(True)

        self._complete_modal_dialog(self.window.add_person, PersonDialog, configure)

        people = self.repository.list_people(self.case.id)
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0].display_name, "Alex Tester")
        self.assertEqual(people[0].roles, ["Driver", "Motorcyclist"])
        self.assertEqual(people[0].dob, "1985-08-05")
        self.assertEqual(people[0].address, "123 Example Street")
        self.assertEqual(people[0].zip_code, "97201-1234")
        self.assertEqual(self.window.people_table.rowCount(), 1)
        self.assertEqual(self.window.people_table.item(0, 2).text(), "08/05/1985")

    def test_add_vehicle_persists_and_refreshes_table(self):
        driver = self.repository.save_person(Person(
            id=new_id(), case_id=self.case.id, first_name="Dana", last_name="Driver",
            roles=["Driver"],
        ))
        self.window.refresh_case_tables()

        def configure(dialog: VehicleDialog) -> None:
            dialog.vehicle_number.setText("V-1")
            dialog.year.setText("2025")
            dialog.make.setText("Example")
            dialog.model.setText("Sedan")
            dialog.body_style.setText("Four-door sedan")
            dialog.driver.setCurrentIndex(dialog.driver.findData(driver.id))
            dialog.insurance_company.setText("Example Mutual")
            dialog.insurance_policy_number.setText("POL-13579")
            dialog.insurance_claim_number.setText("CLM-24680")
            dialog.insurance_adjuster_name.setText("Riley Adjuster")
            dialog.insurance_adjuster_phone.setText("503-555-0124")
            dialog.insurance_adjuster_email.setText(
                "riley.adjuster@example.com"
            )
            self.assertFalse(dialog.towed.isChecked())
            self.assertFalse(dialog.towed_to.isEnabled())
            dialog.towed.setChecked(True)
            self.assertTrue(dialog.towed_to.isEnabled())
            dialog.towed_to.setText("Central Evidence Tow Yard")
            dialog.release_date.setText("08/05/2026")
            dialog.release_information.setPlainText(
                "Released to registered owner with receipt"
            )
            dialog.property_damage.setPlainText("None")
            for checkbox in dialog.vehicle_workflow_boxes.values():
                checkbox.setChecked(True)

        self._complete_modal_dialog(self.window.add_vehicle, VehicleDialog, configure)

        vehicles = self.repository.list_vehicles(self.case.id)
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0].vehicle_number, "V-1")
        self.assertEqual(vehicles[0].description, "2025 Example Sedan")
        self.assertEqual(vehicles[0].driver_person_id, driver.id)
        self.assertEqual(vehicles[0].insurance_company, "Example Mutual")
        self.assertEqual(vehicles[0].insurance_policy_number, "POL-13579")
        self.assertEqual(vehicles[0].insurance_claim_number, "CLM-24680")
        self.assertEqual(vehicles[0].insurance_adjuster_name, "Riley Adjuster")
        self.assertEqual(vehicles[0].insurance_adjuster_phone, "503-555-0124")
        self.assertEqual(
            vehicles[0].insurance_adjuster_email,
            "riley.adjuster@example.com",
        )
        self.assertEqual(vehicles[0].body_style, "Four-door sedan")
        self.assertEqual(vehicles[0].property_damage, "None")
        self.assertTrue(vehicles[0].towed)
        self.assertEqual(
            vehicles[0].tow_information,
            "Central Evidence Tow Yard",
        )
        self.assertTrue(vehicles[0].warrant_obtained)
        self.assertTrue(vehicles[0].vehicle_inspection_completed)
        self.assertTrue(vehicles[0].nhtsa_recalls_checked)
        self.assertTrue(vehicles[0].cdr_equipped)
        self.assertTrue(vehicles[0].cdr_imaged)
        self.assertTrue(vehicles[0].cdr_report_uploaded)
        self.assertTrue(vehicles[0].released)
        self.assertEqual(vehicles[0].release_date, "2026-08-05")
        self.assertEqual(
            vehicles[0].release_information,
            "Released to registered owner with receipt",
        )
        self.assertEqual(self.window.vehicles_table.rowCount(), 1)
        self.assertEqual(
            self.window.vehicles_table.horizontalHeaderItem(4).text(),
            "Vehicle Checklist",
        )
        self.assertEqual(
            self.window.vehicles_table.horizontalHeaderItem(7).text(),
            "Insurance / Claim",
        )
        insurance_summary = self.window.vehicles_table.item(0, 7).text()
        self.assertIn("Example Mutual / POL-13579", insurance_summary)
        self.assertIn("Claim: CLM-24680", insurance_summary)
        self.assertIn("Adjuster: Riley Adjuster", insurance_summary)
        self.assertIn("Adjuster phone: 503-555-0124", insurance_summary)
        self.assertIn(
            "Adjuster email: riley.adjuster@example.com",
            insurance_summary,
        )
        self.assertIn(
            "NHTSA Recalls Checked",
            self.window.vehicles_table.item(0, 4).text(),
        )
        self.assertIn(
            "CDR Report Uploaded",
            self.window.vehicles_table.item(0, 4).text(),
        )
        self.assertIn(
            "Yes - Central Evidence Tow Yard",
            self.window.vehicles_table.item(0, 5).text(),
        )
        self.assertIn(
            "Released - 08/05/2026 - Released to registered owner with receipt",
            self.window.vehicles_table.item(0, 6).text(),
        )
        edit_dialog = VehicleDialog(
            self.case.id,
            [driver],
            vehicles[0],
            parent=self.window,
        )
        self.assertEqual(edit_dialog.insurance_claim_number.text(), "CLM-24680")
        self.assertEqual(edit_dialog.insurance_adjuster_name.text(), "Riley Adjuster")
        self.assertEqual(edit_dialog.insurance_adjuster_phone.text(), "503-555-0124")
        self.assertEqual(
            edit_dialog.insurance_adjuster_email.text(),
            "riley.adjuster@example.com",
        )
        edit_dialog.reject()

        saved_vehicle_id = vehicles[0].id
        self.window.loading = True
        self.window.close()
        self.app.processEvents()
        self.window = MainWindow(self.repository)
        self.window.show()
        self.app.processEvents()
        reopened_vehicle = self.repository.get_vehicle(saved_vehicle_id)
        self.assertIsNotNone(reopened_vehicle)
        self.assertEqual(reopened_vehicle.vehicle_number, "V-1")
        self.assertEqual(self.window.vehicles_table.rowCount(), 1)

    def test_overview_autosaves_on_top_level_nested_and_periodic_triggers(self):
        self.assertTrue(self.window.periodic_autosave_timer.isActive())
        self.assertEqual(self.window.periodic_autosave_timer.interval(), 30_000)

        self.window.general_notes.setPlainText("Saved when leaving Overview")
        self.window.autosave_timer.stop()
        self.assertTrue(self.window.overview_dirty)
        people_index = next(
            index
            for index in range(self.window.tabs.count())
            if self.window.tabs.tabText(index) == "People"
        )
        self.window.tabs.setCurrentIndex(people_index)
        self.app.processEvents()
        self.assertEqual(
            self.repository.get_case(self.case.id).notes,
            "Saved when leaving Overview",
        )
        self.assertFalse(self.window.overview_dirty)

        self.window.first_harmful_event.setText("Vehicle one struck a curb.")
        self.window.autosave_timer.stop()
        self.assertTrue(self.window.overview_dirty)
        self.window._autosave_if_dirty()
        self.assertEqual(
            self.repository.get_case(self.case.id).first_harmful_event,
            "Vehicle one struck a curb.",
        )
        self.assertFalse(self.window.overview_dirty)

        road_weather_index = next(
            index
            for index in range(self.window.tabs.count())
            if self.window.tabs.tabText(index) == "Road / Weather"
        )
        self.window.tabs.setCurrentIndex(road_weather_index)
        self.app.processEvents()
        road_weather_tabs = self.window.tabs.widget(road_weather_index).findChild(
            QTabWidget
        )
        self.assertIsNotNone(road_weather_tabs)
        self.window.condition_widgets["temperature"].setText("72")
        self.window.autosave_timer.stop()
        self.assertTrue(self.window.overview_dirty)
        road_weather_tabs.setCurrentIndex(
            (road_weather_tabs.currentIndex() + 1) % road_weather_tabs.count()
        )
        self.app.processEvents()
        self.assertEqual(
            self.repository.get_road_conditions(self.case.id).temperature,
            "72",
        )
        self.assertFalse(self.window.overview_dirty)

        self.window.summary.setPlainText("Saved by periodic safety timer")
        self.window.autosave_timer.stop()
        self.assertTrue(self.window.overview_dirty)
        self.window._autosave_if_dirty()
        self.assertEqual(
            self.repository.get_case(self.case.id).summary,
            "Saved by periodic safety timer",
        )
        self.assertFalse(self.window.overview_dirty)

    def test_vehicle_dialog_warns_before_discarding_unsaved_changes(self):
        dialog = VehicleDialog(self.case.id, [], parent=self.window)
        dialog.show()
        dialog.vehicle_number.setFocus()
        QTest.keyClicks(dialog.vehicle_number, "V-9")
        self.app.processEvents()
        self.assertTrue(dialog.record_dirty)

        with patch(
            "traffic_crash_notebook.ui.dialogs.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            dialog.reject()
        question.assert_called_once()
        self.assertTrue(dialog.isVisible())

        with patch(
            "traffic_crash_notebook.ui.dialogs.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            dialog.reject()
        self.assertFalse(dialog.isVisible())

    def test_vehicle_driver_selector_only_includes_people_marked_driver(self):
        driver = Person(
            id="driver",
            case_id=self.case.id,
            first_name="Dana",
            last_name="Driver",
            roles=["Driver"],
        )
        passenger = Person(
            id="passenger",
            case_id=self.case.id,
            first_name="Pat",
            last_name="Passenger",
            roles=["Passenger"],
        )
        dialog = VehicleDialog(self.case.id, [driver, passenger], parent=self.window)
        self.assertEqual(
            [dialog.driver.itemData(index) for index in range(dialog.driver.count())],
            [None, "driver"],
        )
        self.assertEqual(
            [dialog.owner.itemData(index) for index in range(dialog.owner.count())],
            [None, "driver", "passenger"],
        )
        dialog.reject()

        legacy_vehicle = Vehicle(
            id="vehicle",
            case_id=self.case.id,
            driver_person_id="passenger",
        )
        legacy_dialog = VehicleDialog(
            self.case.id,
            [driver, passenger],
            legacy_vehicle,
            parent=self.window,
        )
        self.assertEqual(legacy_dialog.driver.currentData(), "passenger")
        self.assertIn("legacy; not marked Driver", legacy_dialog.driver.currentText())
        legacy_dialog.reject()

    def test_vehicle_dialog_validates_optional_vin_as_17_characters(self):
        dialog = VehicleDialog(self.case.id, [], parent=self.window)
        dialog.vehicle_number.setText("V-1")
        dialog.vin.setText("1HGCM82633A00435")
        with patch(
            "traffic_crash_notebook.ui.dialogs.QMessageBox.warning"
        ) as warning:
            dialog._validate_and_accept()
        warning.assert_called_once()
        self.assertIn("17", warning.call_args.args[2])
        dialog.reject()

        invalid_character_dialog = VehicleDialog(
            self.case.id,
            [],
            parent=self.window,
        )
        invalid_character_dialog.vehicle_number.setText("V-2")
        invalid_character_dialog.vin.setText("1HGCM82633A00435I")
        with patch(
            "traffic_crash_notebook.ui.dialogs.QMessageBox.warning"
        ) as warning:
            invalid_character_dialog._validate_and_accept()
        warning.assert_called_once()
        self.assertIn("I, O, and Q", warning.call_args.args[2])
        invalid_character_dialog.reject()

        valid_dialog = VehicleDialog(self.case.id, [], parent=self.window)
        valid_dialog.vehicle_number.setText("V-3")
        valid_dialog.vin.setText("1hgcm82633a004352")
        valid_dialog._validate_and_accept()
        self.assertEqual(valid_dialog.vin.text(), "1HGCM82633A004352")
        self.assertEqual(valid_dialog.result(), QDialog.DialogCode.Accepted)
        valid_dialog.close()

    def test_identifier_fields_normalize_to_uppercase(self):
        vehicle_dialog = VehicleDialog(self.case.id, [], parent=self.window)
        vehicle_dialog.vin.setText("1hgcm82633a004352")
        vehicle_dialog.plate.setText("abc123")
        vehicle_dialog.plate_state.setText("or")
        vehicle_dialog.insurance_policy_number.setText("ab-123-cd")
        self.assertEqual(vehicle_dialog.vin.text(), "1HGCM82633A004352")
        self.assertEqual(vehicle_dialog.plate.text(), "ABC123")
        self.assertEqual(vehicle_dialog.plate_state.text(), "OR")
        self.assertEqual(vehicle_dialog.insurance_policy_number.text(), "AB-123-CD")
        vehicle_dialog.close()

        person = Person(id="person-1", case_id=self.case.id, last_name="Driver")
        driver_dialog = DriverProfileDialog(
            person,
            DriverProfile(person_id=person.id),
            parent=self.window,
        )
        driver_dialog.license_number.setText("or-a1b2c3")
        driver_dialog.license_state.setText("or")
        self.assertEqual(driver_dialog.license_number.text(), "OR-A1B2C3")
        self.assertEqual(driver_dialog.license_state.text(), "OR")
        driver_dialog.close()

        vehicle_lead_dialog = HitRunVehicleLeadDialog(
            self.case.id,
            [],
            parent=self.window,
        )
        vehicle_lead_dialog.vin.setText("1hgcm82633a004352")
        vehicle_lead_dialog.plate.setText("xyz789")
        vehicle_lead_dialog.plate_state.setText("wa")
        self.assertEqual(vehicle_lead_dialog.vin.text(), "1HGCM82633A004352")
        self.assertEqual(vehicle_lead_dialog.plate.text(), "XYZ789")
        self.assertEqual(vehicle_lead_dialog.plate_state.text(), "WA")
        vehicle_lead_dialog.close()

        person_lead_dialog = HitRunPersonLeadDialog(
            self.case.id,
            [],
            [],
            parent=self.window,
        )
        person_lead_dialog.driver_license_number.setText("or-a1b2c3")
        person_lead_dialog.driver_license_state.setText("or")
        self.assertEqual(
            person_lead_dialog.driver_license_number.text(),
            "OR-A1B2C3",
        )
        self.assertEqual(person_lead_dialog.driver_license_state.text(), "OR")
        person_lead_dialog.close()

    def test_vehicle_save_failure_is_visible_and_keeps_the_draft(self):
        vehicle = Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-DRAFT",
            make="Unsaved",
        )
        with (
            patch.object(
                self.repository,
                "save_vehicle",
                side_effect=sqlite3.OperationalError("storage unavailable"),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QMessageBox.critical"
            ) as critical,
        ):
            self.assertFalse(self.window._save_vehicle_record(vehicle))
        self.assertEqual(vehicle.vehicle_number, "V-DRAFT")
        self.assertEqual(vehicle.make, "Unsaved")
        self.assertIn("storage unavailable", critical.call_args.args[2])

    def test_journal_supports_guided_add_edit_remove_workflow(self):
        tab_labels = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertIn("Journal", tab_labels)
        self.assertNotIn("Chronology", tab_labels)
        journal_tab = self.window.tabs.widget(tab_labels.index("Journal"))
        self.assertEqual(journal_tab.objectName(), "journal_tab")
        self.assertEqual(self.window.chronology_table.objectName(), "journal_table")

        guidance = journal_tab.findChild(QLabel, "journal_guidance")
        self.assertIsNotNone(guidance)
        self.assertIn("investigative actions", guidance.text())
        button_labels = {
            button.text() for button in journal_tab.findChildren(QPushButton)
        }
        self.assertTrue({
            "Add Journal Entry",
            "Edit Journal Entry",
            "Remove Journal Entry",
        }.issubset(button_labels))

        def configure_add(dialog: ChronologyDialog) -> None:
            self.assertEqual(dialog.windowTitle(), "Add Journal Entry")
            self.assertIn("investigative action", dialog.summary.placeholderText())
            self.assertIn("journal details", dialog.details.placeholderText())
            dialog.event_date.setText("08/05/2026")
            dialog.event_time.setText("13:20")
            dialog.category.setCurrentText("Evidence")
            dialog.summary.setText("Surveillance video obtained")
            dialog.details.setPlainText(
                "Original video was uploaded to the approved evidence system."
            )

        self._complete_modal_dialog(
            self.window.add_chronology,
            ChronologyDialog,
            configure_add,
        )

        entries = self.repository.list_chronology(self.case.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].event_date, "2026-08-05")
        self.assertEqual(entries[0].category, "Evidence")
        self.assertEqual(self.window.chronology_table.rowCount(), 1)
        self.assertEqual(
            self.window.chronology_table.item(0, 3).text(),
            "Surveillance video obtained",
        )
        self.assertIn("1 journal entry", self.window.counts_label.text())

        self.window.chronology_table.setCurrentCell(0, 0)

        def configure_edit(dialog: ChronologyDialog) -> None:
            self.assertEqual(dialog.windowTitle(), "Edit Journal Entry")
            self.assertEqual(dialog.summary.text(), "Surveillance video obtained")
            dialog.summary.setText("Surveillance video reviewed")
            dialog.details.setPlainText("Timing points documented for follow-up.")

        self._complete_modal_dialog(
            self.window.edit_chronology,
            ChronologyDialog,
            configure_edit,
        )
        edited = self.repository.list_chronology(self.case.id)[0]
        self.assertEqual(edited.summary, "Surveillance video reviewed")
        self.assertEqual(edited.details, "Timing points documented for follow-up.")

        self.window.chronology_table.setCurrentCell(0, 0)
        with patch.object(self.window, "_confirm_remove", return_value=True) as confirm:
            self.window.delete_chronology()
        confirm.assert_called_once_with("Remove this journal entry?")
        self.assertEqual(self.repository.list_chronology(self.case.id), [])
        self.assertEqual(self.window.chronology_table.rowCount(), 0)
        self.assertIn("0 journal entries", self.window.counts_label.text())

    def test_evidence_tasks_and_journal_are_separate_ordered_tabs(self):
        tab_labels = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        evidence_index = tab_labels.index("Evidence")
        self.assertEqual(
            tab_labels[evidence_index:evidence_index + 3],
            ["Evidence", "Tasks", "Journal"],
        )
        self.assertNotIn("Tasks / Evidence", tab_labels)
        self.assertEqual(
            self.window.tasks_table.horizontalHeaderItem(2).text(),
            "Task",
        )

        evidence_tab = self.window.tabs.widget(evidence_index)
        guidance = evidence_tab.findChild(QLabel, "evidence_guidance")
        self.assertIsNotNone(guidance)
        self.assertIn("property receipt", guidance.text().lower())
        button_labels = {
            button.text() for button in evidence_tab.findChildren(QPushButton)
        }
        self.assertTrue({
            "Add Property Receipt",
            "Edit Property Receipt",
            "Remove Property Receipt",
            "Add Item",
            "Edit Item",
            "Remove Item",
        }.issubset(button_labels))
        self.assertFalse(self.window.add_property_receipt_item_button.isEnabled())
        owner = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Jordan",
            last_name="Property Owner",
        ))
        self.window.refresh_people()

        def configure_receipt(dialog: PropertyReceiptDialog) -> None:
            self.assertEqual(
                [
                    dialog.lodging_type.itemText(index)
                    for index in range(dialog.lodging_type.count())
                ],
                [
                    "Evidence",
                    "Found Property",
                    "Prison Property",
                    "Safe Keeping",
                ],
            )
            self.assertEqual(
                [
                    dialog.property_owner.itemText(index)
                    for index in range(dialog.property_owner.count())
                ],
                ["No property owner selected", owner.display_name],
            )
            dialog.receipt_number.setText("PR-13579")
            dialog.property_owner.setCurrentText(owner.display_name)
            dialog.lodging_type.setCurrentText("Safe Keeping")
            dialog.lodged_location.setText("Central Property Room")
            dialog.lodged_date.setText("08/06/2026")

        self._complete_modal_dialog(
            self.window.add_property_receipt,
            PropertyReceiptDialog,
            configure_receipt,
        )
        receipts = self.repository.list_property_receipts(self.case.id)
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        self.assertEqual(receipt.receipt_number, "PR-13579")
        self.assertEqual(receipt.property_owner, owner.display_name)
        self.assertEqual(receipt.lodging_type, "Safe Keeping")
        self.assertEqual(receipt.lodged_location, "Central Property Room")
        self.assertEqual(receipt.lodged_date, "2026-08-06")
        self.assertEqual(self.window.property_receipts_table.rowCount(), 1)
        self.assertEqual(
            self.window.property_receipts_table.item(0, 4).text(),
            "08/06/2026",
        )
        self.assertTrue(self.window.add_property_receipt_item_button.isEnabled())

        def add_item(expected_number: int, description: str) -> None:
            def configure_item(dialog: PropertyReceiptItemDialog) -> None:
                self.assertEqual(dialog.item_number.value(), expected_number)
                dialog.description.setPlainText(description)

            self._complete_modal_dialog(
                self.window.add_property_receipt_item,
                PropertyReceiptItemDialog,
                configure_item,
            )

        add_item(1, "Black passenger-side mirror housing")
        add_item(2, "Blue paint transfer sample")
        items = self.repository.list_property_receipt_items(receipt.id)
        self.assertEqual(
            [(item.item_number, item.description) for item in items],
            [
                (1, "Black passenger-side mirror housing"),
                (2, "Blue paint transfer sample"),
            ],
        )
        self.assertEqual(self.window.property_receipt_items_table.rowCount(), 2)

        self.window.property_receipts_table.setCurrentCell(0, 0)
        with patch.object(self.window, "_confirm_remove", return_value=True) as confirm:
            self.window.delete_property_receipt()
        confirm.assert_called_once_with(
            "Remove this property receipt and all of its items?"
        )
        self.assertEqual(self.repository.list_property_receipts(self.case.id), [])
        self.assertEqual(
            self.repository.list_property_receipt_items(receipt.id),
            [],
        )
        self.assertFalse(self.window.add_property_receipt_item_button.isEnabled())

    def test_case_packet_workspace_previews_prints_and_exports_both_packet_types(self):
        tab_labels = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertNotIn("Packet Preview", tab_labels)
        toolbar = self.window.findChild(QToolBar)
        toolbar_actions = [action.text() for action in toolbar.actions()]
        self.assertEqual(
            toolbar_actions,
            [
                "New Case",
                "Save",
                "Export Full Working Packet",
                "Export Compact Packet",
                "Packet Preview",
                "Export Quick Review",
                "Back Up",
                "Data Folder",
            ],
        )

        self.window.show_packet_preview()
        self.app.processEvents()
        self.assertTrue(self.window.packet_preview_dialog.isVisible())
        self.assertTrue(self.window.packet_preview_dialog.isWindow())
        self.assertTrue(self.window.packet_preview_dialog.isSizeGripEnabled())
        button_labels = {
            button.text()
            for button in self.window.packet_preview_dialog.findChildren(QPushButton)
        }
        self.assertEqual(
            button_labels,
            {"Refresh Preview", "Print Packet...", "Export Preview to PDF"},
        )
        self.assertEqual(
            [
                self.window.packet_preview_mode.itemText(index)
                for index in range(self.window.packet_preview_mode.count())
            ],
            ["Full Working Packet", "Compact Packet"],
        )

        full_preview_path = self.window.packet_preview_path
        self.assertTrue(full_preview_path.is_file())
        full_page_count = self.window.packet_pdf_document.pageCount()
        self.assertGreater(full_page_count, 1)
        self.assertTrue(self.window.packet_pdf_view.isVisible())
        self.assertIs(
            self.window.packet_pdf_view.document(),
            self.window.packet_pdf_document,
        )
        full_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(full_preview_path).pages
        )
        self.assertNotIn("FULL WORKING PACKET", full_text)
        self.assertIn(
            "Preview ready - Full Working Packet",
            self.window.packet_preview_status.text(),
        )

        self.window.packet_preview_mode.setCurrentIndex(1)
        self.app.processEvents()
        compact_preview_path = self.window.packet_preview_path
        self.assertNotEqual(compact_preview_path, full_preview_path)
        self.assertTrue(compact_preview_path.is_file())
        compact_page_count = self.window.packet_pdf_document.pageCount()
        self.assertLess(compact_page_count, full_page_count)
        compact_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(compact_preview_path).pages
        )
        self.assertIn("COMPACT COMPLETED-CASE PACKET", compact_text)
        self.assertIn(
            "Preview ready - Compact Packet",
            self.window.packet_preview_status.text(),
        )

        locked_preview_path = self.window.packet_preview_path
        original_unlink = Path.unlink

        def refuse_locked_preview(path: Path, *args, **kwargs):
            if path == locked_preview_path:
                raise PermissionError(
                    32,
                    "The process cannot access the file because it is being used "
                    "by another process",
                    str(path),
                )
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", refuse_locked_preview):
            self.window.preview_case_packet()
            refreshed_preview_path = self.window.packet_preview_path
            self.assertNotEqual(refreshed_preview_path, locked_preview_path)
            self.assertTrue(refreshed_preview_path.is_file())
            self.assertTrue(locked_preview_path.is_file())
            self.assertIn(
                "Preview ready",
                self.window.packet_preview_status.text(),
            )
            self.window._cleanup_stale_packet_previews()
            self.assertIn(
                locked_preview_path,
                self.window.packet_stale_preview_paths,
            )

        self.app.processEvents()
        self.window._cleanup_stale_packet_previews()
        self.assertFalse(locked_preview_path.exists())

        printed_preview = Path(self.temp.name) / "compact-packet-preview-printed.pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(printed_preview))
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        with (
            patch.object(
                self.window,
                "_create_packet_printer",
                return_value=printer,
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QPrintDialog.exec",
                return_value=QDialog.DialogCode.Accepted,
            ),
        ):
            self.window.print_case_packet()
        self.assertTrue(printed_preview.is_file())
        self.assertEqual(
            len(PdfReader(printed_preview).pages),
            self.window.packet_pdf_document.pageCount(),
        )

        exported_preview = Path(self.temp.name) / "compact-packet-preview-export.pdf"
        with (
            patch(
                "traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName",
                return_value=(str(exported_preview), "PDF files (*.pdf)"),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QDesktopServices.openUrl"
            ),
        ):
            self.window.export_case_packet_preview()
        self.assertEqual(
            exported_preview.read_bytes(),
            self.window.packet_preview_path.read_bytes(),
        )

    def test_exchange_report_workspace_is_read_only_and_previews_existing_data(self):
        tab_labels = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertIn("Exchange Report", tab_labels)
        self.assertEqual(tab_labels[-1], "Exchange Report")
        self.assertEqual(
            self.window.exchange_report_tab_index,
            self.window.tabs.count() - 1,
        )
        toolbar = self.window.findChild(QToolBar)
        self.assertNotIn(
            "Export Exchange Report",
            [action.text() for action in toolbar.actions()],
        )

        driver = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Taylor",
            last_name="Driver",
            address="123 Driver Street",
            city="Portland",
            state="OR",
            zip_code="97201",
            cell_phone="503-555-0101",
            roles=["Driver"],
        ))
        self.repository.save_driver_profile(DriverProfile(
            person_id=driver.id,
            license_number="DL-EXCHANGE",
            license_state="OR",
        ))
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-1",
            year="2025",
            make="Example",
            model="Sedan",
            body_style="Four-door sedan",
            color="Blue",
            plate="ABC123",
            plate_state="OR",
            driver_person_id=driver.id,
            insurance_company="Example Mutual",
            insurance_policy_number="POL-EXCHANGE",
            property_damage="None",
        ))
        passenger = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Parker",
            last_name="Passenger",
            address="456 Passenger Avenue",
            city="Portland",
            state="OR",
            zip_code="97202",
            home_phone="503-555-0202",
            roles=["Passenger"],
        ))
        self.repository.save_participant_details(ParticipantDetails(
            person_id=passenger.id,
            vehicle_id=vehicle.id,
        ))
        pedestrian = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Pat",
            last_name="Pedestrian",
            address="789 Walking Lane",
            city="Portland",
            state="OR",
            zip_code="97203",
            cell_phone="503-555-0303",
            roles=["Pedestrian"],
        ))
        self.window.investigator.setText("Officer Assigned")
        self.window.assigned_officer_dpsst.setText("54321")
        self.window.assignment.setText("Traffic Division")
        self.window.crash_date.setText("08/05/2026")
        self.window.crash_time.setText("02:35 PM")
        self.window.tabs.setCurrentIndex(tab_labels.index("Exchange Report"))
        self.app.processEvents()

        loaded_case = self.repository.get_case(self.case.id)
        self.assertEqual(loaded_case.investigator, "Officer Assigned")
        self.assertEqual(loaded_case.assigned_officer_dpsst, "54321")
        self.assertEqual(loaded_case.assignment, "Traffic Division")
        self.assertEqual(loaded_case.crash_time, "14:35")
        self.assertTrue(self.window.assigned_officer_dpsst.hasAcceptableInput())

        exchange_tab_index = tab_labels.index("Exchange Report")
        exchange_tab = self.window.tabs.widget(exchange_tab_index)
        self.assertEqual(exchange_tab.findChildren(QLineEdit), [])
        button_labels = {
            button.text() for button in exchange_tab.findChildren(QPushButton)
        }
        self.assertEqual(
            button_labels,
            {
                "Refresh Preview",
                "Print Exchange Report...",
                "Export Preview to PDF",
            },
        )
        self.assertTrue(self.window.exchange_preview_path.is_file())
        self.assertEqual(self.window.exchange_pdf_document.pageCount(), 2)
        self.assertIn("1 vehicle(s)", self.window.exchange_readiness_label.text())
        self.assertIn("2 additional person(s)", self.window.exchange_readiness_label.text())
        self.assertIn("1 pedestrian", self.window.exchange_readiness_label.text())
        self.assertIn("unused record blocks are not printed", self.window.exchange_readiness_label.text())
        preview_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(self.window.exchange_preview_path).pages
        )
        self.assertIn("08/05/2026 02:35 PM", preview_text)
        self.assertIn("Officer Assigned", preview_text)
        self.assertIn("54321", preview_text)
        self.assertIn("Traffic Division", preview_text)
        self.assertIn(pedestrian.last_name, preview_text)

        locked_preview_path = self.window.exchange_preview_path
        original_unlink = Path.unlink

        def refuse_locked_preview(path: Path, *args, **kwargs):
            if path == locked_preview_path:
                raise PermissionError(
                    32,
                    "The process cannot access the file because it is being used "
                    "by another process",
                    str(path),
                )
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", refuse_locked_preview):
            self.window.preview_exchange_report()
            refreshed_preview_path = self.window.exchange_preview_path
            self.assertNotEqual(refreshed_preview_path, locked_preview_path)
            self.assertTrue(refreshed_preview_path.is_file())
            self.assertTrue(locked_preview_path.is_file())
            self.assertIn(
                "Preview ready",
                self.window.exchange_preview_status.text(),
            )
            self.assertEqual(self.window.exchange_pdf_document.pageCount(), 2)
            self.window._cleanup_stale_exchange_previews()
            self.assertIn(
                locked_preview_path,
                self.window.exchange_stale_preview_paths,
            )

        self.app.processEvents()
        self.window._cleanup_stale_exchange_previews()
        self.assertFalse(locked_preview_path.exists())

        printed_preview = Path(self.temp.name) / "exchange-preview-printed.pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(printed_preview))
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        with (
            patch.object(
                self.window,
                "_create_exchange_printer",
                return_value=printer,
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QPrintDialog.exec",
                return_value=QDialog.DialogCode.Accepted,
            ),
        ):
            self.window.print_exchange_report()
        self.assertTrue(printed_preview.is_file())
        self.assertEqual(len(PdfReader(printed_preview).pages), 2)

        exported_preview = Path(self.temp.name) / "exchange-preview-export.pdf"
        with (
            patch(
                "traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName",
                return_value=(str(exported_preview), "PDF files (*.pdf)"),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QDesktopServices.openUrl"
            ),
        ):
            self.window.export_exchange_report()
        exported_reader = PdfReader(exported_preview)
        exported_text = "\n".join(
            page.extract_text() or "" for page in exported_reader.pages
        )
        current_preview_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(self.window.exchange_preview_path).pages
        )
        self.assertEqual(len(exported_reader.pages), 2)
        self.assertEqual(exported_text, current_preview_text)

    def test_exchange_report_never_reuses_prior_case_preview_after_case_switch(self):
        tab_labels = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.window.tabs.setCurrentIndex(tab_labels.index("Exchange Report"))
        self.app.processEvents()

        prior_preview_path = self.window.exchange_preview_path
        prior_preview_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(prior_preview_path).pages
        )
        self.assertIn("UI-TEST", prior_preview_text)
        self.assertEqual(self.window.exchange_preview_case_id, self.case.id)

        next_case = self.repository.create_case(
            "UI-SECOND",
            "Second Case Investigator",
        )
        self.window.refresh_cases()
        next_case_row = next(
            row
            for row in range(self.window.case_list.count())
            if self.window.case_list.item(row).data(Qt.ItemDataRole.UserRole)
            == next_case.id
        )
        attempted_destination = (
            Path(self.temp.name) / "UI-SECOND_Exchange_Report.pdf"
        )

        with (
            patch(
                "traffic_crash_notebook.ui.main_window.export_exchange_report_pdf",
                side_effect=RuntimeError("synthetic current-case generation failure"),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName",
                return_value=(str(attempted_destination), "PDF files (*.pdf)"),
            ) as save_dialog,
            patch(
                "traffic_crash_notebook.ui.main_window.QPrintDialog.exec"
            ) as print_dialog,
            patch(
                "traffic_crash_notebook.ui.main_window.QDesktopServices.openUrl"
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QMessageBox.critical"
            ) as critical,
        ):
            self.window.case_list.setCurrentRow(next_case_row)
            self.app.processEvents()
            self.assertEqual(self.window.current_case.id, next_case.id)
            self.assertIsNone(self.window.exchange_preview_case_id)
            self.assertTrue(self.window.exchange_pdf_view.isHidden())
            self.assertIn(
                "Preview failed for UI-SECOND",
                self.window.exchange_preview_status.text(),
            )

            self.window.export_exchange_report()
            self.window.print_exchange_report()

        self.assertFalse(attempted_destination.exists())
        save_dialog.assert_called_once()
        print_dialog.assert_not_called()
        self.assertEqual(critical.call_count, 2)
        self.assertIn(
            "synthetic current-case generation failure",
            critical.call_args_list[0].args[2],
        )
        self.assertIn("verified preview", critical.call_args_list[1].args[2])

        with (
            patch(
                "traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName",
                return_value=(str(attempted_destination), "PDF files (*.pdf)"),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QDesktopServices.openUrl"
            ),
        ):
            self.window.export_exchange_report()

        self.assertTrue(attempted_destination.is_file())
        current_preview_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(attempted_destination).pages
        )
        self.assertIn("UI-SECOND", current_preview_text)
        self.assertNotIn("UI-TEST", current_preview_text)
        self.assertEqual(self.window.exchange_preview_case_id, next_case.id)
        self.assertFalse(self.window.exchange_pdf_view.isHidden())
        self.assertIn("Case: UI-SECOND", self.window.exchange_preview_status.text())

        preview_independent_destination = (
            Path(self.temp.name) / "UI-SECOND_Exchange_Report_No_Preview.pdf"
        )
        with (
            patch.object(
                self.window,
                "refresh_exchange_report",
                side_effect=lambda *_args, **_kwargs: self.window._invalidate_exchange_preview(
                    "Preview renderer unavailable for test."
                ),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName",
                return_value=(
                    str(preview_independent_destination),
                    "PDF files (*.pdf)",
                ),
            ),
            patch(
                "traffic_crash_notebook.ui.main_window.QDesktopServices.openUrl"
            ),
        ):
            self.window.export_exchange_report()
        preview_independent_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(preview_independent_destination).pages
        )
        self.assertIn("UI-SECOND", preview_independent_text)
        self.assertNotIn("UI-TEST", preview_independent_text)

    def test_about_identifies_exact_build_and_running_location(self):
        self.assertIn(__version__, self.window.windowTitle())
        self.assertEqual(
            self.window.about_action.text(),
            "About Traffic Crash Notebook",
        )
        self.assertEqual(
            self.window.about_button.text(),
            f"About v{__version__}",
        )
        about = self.window.about_text()
        self.assertIn(f"Version: {__version__}", about)
        self.assertIn("Build ID:", about)
        self.assertIn("Build date:", about)
        self.assertIn(f"Database schema: {SCHEMA_VERSION}", about)
        self.assertIn("Running from:", about)
        self.assertIn(
            f"Case data folder: {self.repository.database_path.parent}",
            about,
        )
        self.assertEqual(
            self.window.storage_location_action.text(),
            "Data Storage Location...",
        )
        self.assertEqual(
            self.window._reports_directory(),
            self.repository.database_path.parent / "Reports",
        )
        self.assertEqual(
            self.window._backups_directory(),
            self.repository.database_path.parent / "Backups",
        )

    def test_settings_defaults_are_stored_with_data_and_prefill_new_cases(self):
        self.assertEqual(self.window.settings_button.text(), "Settings")
        self.assertEqual(
            self.window.application_settings_action.text(),
            "Application Settings...",
        )
        self.assertEqual(
            self.window.check_updates_action.text(),
            "Check for Updates...",
        )

        def configure(dialog: ApplicationSettingsDialog) -> None:
            self.assertEqual(
                dialog.data_directory_label.text(),
                str(self.repository.database_path.parent),
            )
            self.assertEqual(
                dialog.change_storage_button.text(),
                "Change data location...",
            )
            dialog.user_name_edit.setText("Officer Defaults")
            dialog.dpsst_edit.setText("654321")
            dialog.assignment_edit.setText("Traffic Investigations Unit")
            dialog.auto_check_updates_checkbox.setChecked(False)

        self._complete_modal_dialog(
            self.window.show_settings,
            ApplicationSettingsDialog,
            configure,
        )

        defaults = self.repository.get_user_defaults()
        self.assertEqual(defaults.user_name, "Officer Defaults")
        self.assertEqual(defaults.dpsst, "654321")
        self.assertEqual(defaults.assignment, "Traffic Investigations Unit")
        self.assertFalse(defaults.auto_check_updates)
        self.assertEqual(
            self.repository.get_case(self.case.id).investigator,
            "Automated Test",
        )

        with patch(
            "traffic_crash_notebook.ui.main_window.QInputDialog.getText",
            return_value=("UI-DEFAULTS", True),
        ):
            self.window.new_case()

        created = next(
            case
            for case in self.repository.list_cases()
            if case.case_number == "UI-DEFAULTS"
        )
        self.assertEqual(created.investigator, "Officer Defaults")
        self.assertEqual(created.assigned_officer_dpsst, "654321")
        self.assertEqual(created.assignment, "Traffic Investigations Unit")

    def test_manual_update_results_are_reported_and_success_is_timestamped(self):
        portable = PortableRelease(
            filename=f"TrafficCrashNotebook-{__version__}-Windows-Portable.zip",
            download_url=(
                "https://github.com/gdowkpc/traffic-crash-notebook/releases/download/"
                f"v{__version__}/TrafficCrashNotebook-{__version__}-Windows-Portable.zip"
            ),
            sha256="a" * 64,
            size_bytes=1,
            build_id="ui-test",
        )
        current = UpdateManifest(
            version=__version__,
            release_tag=f"v{__version__}",
            published_at="2026-08-05T21:00:00Z",
            release_page_url=(
                "https://github.com/gdowkpc/traffic-crash-notebook/releases/tag/"
                f"v{__version__}"
            ),
            release_notes="Current release",
            minimum_supported_version="0.4.8",
            portable=portable,
        )
        self.window.update_check_was_manual = True
        with patch(
            "traffic_crash_notebook.ui.main_window.QMessageBox.information"
        ) as information:
            self.window._update_manifest_received(current)
        information.assert_called_once()
        self.assertTrue(self.repository.get_user_defaults().last_update_check)

        newer = UpdateManifest(
            version="99.0.0",
            release_tag="v99.0.0",
            published_at="2026-08-05T21:00:00Z",
            release_page_url=(
                "https://github.com/gdowkpc/traffic-crash-notebook/releases/tag/v99.0.0"
            ),
            release_notes="New release",
            minimum_supported_version="0.4.8",
            portable=portable,
        )
        with patch.object(self.window, "_show_update_available") as available:
            self.window._update_manifest_received(newer)
        available.assert_called_once_with(newer)

    def test_reports_and_backups_default_to_the_configured_case_folder(self):
        with patch(
            "traffic_crash_notebook.ui.main_window.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ) as chooser:
            self.window.export_exchange_report()
            exchange_default = Path(chooser.call_args.args[2])
            self.assertEqual(
                exchange_default.parent,
                self.repository.database_path.parent / "Reports",
            )

            self.window.backup_database()
            backup_default = Path(chooser.call_args.args[2])
            self.assertEqual(
                backup_default.parent,
                self.repository.database_path.parent / "Backups",
            )

    def test_surface_subtab_supports_multiple_add_edit_remove_records(self):
        subtab_names = [
            self.window.conditions_tabs.tabText(index)
            for index in range(self.window.conditions_tabs.count())
        ]
        self.assertEqual(
            subtab_names,
            ["Roadways", "Surface", "Visibility", "Weather", "Scene Analysis"],
        )
        self.assertNotIn("Weather / Surface", subtab_names)
        self.assertNotIn("Multiple Surfaces", subtab_names)
        for retired_field in (
            "surface_composition",
            "surface_condition",
            "friction_value",
        ):
            self.assertNotIn(retired_field, self.window.condition_widgets)

        surface_index = subtab_names.index("Surface")
        self.window.conditions_tabs.setCurrentIndex(surface_index)
        surface_tab = self.window.conditions_tabs.currentWidget()
        button_labels = {
            button.text() for button in surface_tab.findChildren(QPushButton)
        }
        self.assertTrue({
            "Add Surface",
            "Edit Surface",
            "Remove Surface",
        }.issubset(button_labels))

        def configure_lane(dialog: SurfaceObservationDialog) -> None:
            self.assertEqual(dialog.windowTitle(), "Add Surface")
            dialog.location.setText("Northbound lane")
            dialog.composition.setText("Asphalt")
            dialog.condition.setText("Wet")
            dialog.friction_value.setText("0.48")
            dialog.notes.setPlainText("Drag sled measurement")

        self._complete_modal_dialog(
            self.window.add_surface_observation,
            SurfaceObservationDialog,
            configure_lane,
        )

        def configure_crosswalk(dialog: SurfaceObservationDialog) -> None:
            dialog.location.setText("East crosswalk marking")
            dialog.composition.setText("Thermoplastic over asphalt")
            dialog.condition.setText("Dry")

        self._complete_modal_dialog(
            self.window.add_surface_observation,
            SurfaceObservationDialog,
            configure_crosswalk,
        )
        self.assertEqual(self.window.surface_observations_table.rowCount(), 2)
        self.assertEqual(len(self.repository.list_surface_observations(self.case.id)), 2)

        lane_row = next(
            row
            for row in range(self.window.surface_observations_table.rowCount())
            if self.window.surface_observations_table.item(row, 0).text()
            == "Northbound lane"
        )
        self.window.surface_observations_table.setCurrentCell(lane_row, 0)

        def edit_lane(dialog: SurfaceObservationDialog) -> None:
            self.assertEqual(dialog.windowTitle(), "Edit Surface")
            dialog.condition.setText("Damp after rain")

        self._complete_modal_dialog(
            self.window.edit_surface_observation,
            SurfaceObservationDialog,
            edit_lane,
        )
        edited = next(
            surface
            for surface in self.repository.list_surface_observations(self.case.id)
            if surface.location == "Northbound lane"
        )
        self.assertEqual(edited.condition, "Damp after rain")

        crosswalk_row = next(
            row
            for row in range(self.window.surface_observations_table.rowCount())
            if self.window.surface_observations_table.item(row, 0).text()
            == "East crosswalk marking"
        )
        self.window.surface_observations_table.setCurrentCell(crosswalk_row, 0)
        with patch.object(self.window, "_confirm_remove", return_value=True):
            self.window.delete_surface_observation()
        remaining = self.repository.list_surface_observations(self.case.id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].location, "Northbound lane")
        self.assertEqual(self.window.surface_observations_table.rowCount(), 1)

    def test_save_failure_reports_unavailable_storage_without_switching_database(self):
        original_database = self.repository.database_path
        with patch.object(
            self.repository,
            "save_road_conditions",
            side_effect=sqlite3.OperationalError("network drive unavailable"),
        ), patch(
            "traffic_crash_notebook.ui.main_window.QMessageBox.critical"
        ) as error_dialog:
            self.assertFalse(self.window.save_overview())

        self.assertEqual(self.repository.database_path, original_database)
        self.assertTrue(self.window.storage_error_active)
        error_dialog.assert_called_once()
        self.assertIn(
            str(original_database),
            error_dialog.call_args.args[2],
        )

    def test_hit_run_workspace_round_trip_adds_all_lead_types(self):
        tab_labels = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertIn("Hit & Run", tab_labels)
        self.window.hit_run_enabled.setChecked(True)
        self.window.hit_run_status.setCurrentText("Vehicle Lead Developed")
        self.window.hit_run_last_known_location.setText("Example Street at First Avenue")
        self.window.hit_run_last_seen_date.setText("08/04/2026")
        self.window.hit_run_last_seen_time.setText("21:15")
        self.window.hit_run_direction.setText("Northbound")
        self.window.hit_run_initial_source.setText("Witness and surveillance video")
        self.window.hit_run_narrative.setPlainText("Vehicle left the scene.")
        self.window.hit_run_follow_up.setPlainText("Complete neighborhood canvass.")
        self.window.save_overview()

        overview = self.repository.get_hit_run_overview(self.case.id)
        self.assertTrue(overview.is_hit_and_run)
        self.assertEqual(overview.last_seen_date, "2026-08-04")
        self.assertEqual(overview.direction_of_travel, "Northbound")

        def configure_vehicle_lead(dialog: HitRunVehicleLeadDialog) -> None:
            self.assertEqual(dialog.lead_number.text(), "HRV-1")
            dialog.status.setCurrentText("Investigating")
            dialog.year_range.setText("2019-2022")
            dialog.make.setText("Example")
            dialog.model.setText("SUV")
            dialog.color.setText("Dark blue")
            dialog.plate.setText("ABC123")
            dialog.plate_state.setText("OR")
            dialog.last_seen_date.setText("08/04/2026")
            dialog.observed_damage.setPlainText("Right-front damage")
            dialog.missing_parts.setPlainText("Passenger mirror cover")

        self._complete_modal_dialog(
            self.window.add_hit_run_vehicle_lead,
            HitRunVehicleLeadDialog,
            configure_vehicle_lead,
        )
        vehicle_lead = self.repository.list_hit_run_vehicle_leads(self.case.id)[0]
        self.assertEqual(vehicle_lead.last_seen_date, "2026-08-04")
        self.assertEqual(self.window.hit_run_vehicle_leads_table.rowCount(), 1)

        def configure_evidence(dialog: HitRunEvidenceDialog) -> None:
            self.assertEqual(dialog.evidence_number.text(), "HRE-1")
            dialog.evidence_type.setText("Recovered vehicle part")
            dialog.part_number.setText("PART-321")
            dialog.part_description.setPlainText("Mirror cover fragment")
            dialog.recovery_date.setText("08/05/2026")
            dialog.vehicle_lead.setCurrentIndex(
                dialog.vehicle_lead.findData(vehicle_lead.id)
            )

        self._complete_modal_dialog(
            self.window.add_hit_run_evidence,
            HitRunEvidenceDialog,
            configure_evidence,
        )
        evidence = self.repository.list_hit_run_evidence_items(self.case.id)[0]
        self.assertEqual(evidence.part_number, "PART-321")
        self.assertEqual(evidence.recovery_date, "2026-08-05")
        self.assertEqual(evidence.vehicle_lead_id, vehicle_lead.id)
        self.assertEqual(self.window.hit_run_evidence_table.rowCount(), 1)

        def configure_person_lead(dialog: HitRunPersonLeadDialog) -> None:
            self.assertEqual(dialog.lead_number.text(), "HRP-1")
            self.assertTrue(callable(dialog.height))
            dialog.first_name.setText("Morgan")
            dialog.last_name.setText("Possible")
            dialog.alias.setText("Mo")
            dialog.height_value.setText("6 ft 1 in")
            dialog.reason_for_lead.setPlainText("Registered owner of possible vehicle")
            dialog.vehicle_lead.setCurrentIndex(
                dialog.vehicle_lead.findData(vehicle_lead.id)
            )

        self._complete_modal_dialog(
            self.window.add_hit_run_person_lead,
            HitRunPersonLeadDialog,
            configure_person_lead,
        )
        person_lead = self.repository.list_hit_run_person_leads(self.case.id)[0]
        self.assertEqual(person_lead.display_name, "Morgan Possible (aka Mo)")
        self.assertEqual(person_lead.height, "6 ft 1 in")
        self.assertEqual(person_lead.vehicle_lead_id, vehicle_lead.id)
        self.assertEqual(self.window.hit_run_person_leads_table.rowCount(), 1)

    def test_hit_run_leads_promote_into_confirmed_records(self):
        vehicle_lead = self.repository.save_hit_run_vehicle_lead(HitRunVehicleLead(
            id="",
            case_id=self.case.id,
            lead_number="HRV-1",
            year_range="2020-2022",
            make="Example",
            model="Pickup",
            color="White",
            observed_damage="Left-front damage",
        ))
        person_lead = self.repository.save_hit_run_person_lead(HitRunPersonLead(
            id="",
            case_id=self.case.id,
            lead_number="HRP-1",
            first_name="Casey",
            last_name="Possible",
            reason_for_lead="Seen leaving the vehicle",
            vehicle_lead_id=vehicle_lead.id,
        ))
        self.window.refresh_case_tables()

        self.window.hit_run_vehicle_leads_table.selectRow(0)

        def configure_vehicle(dialog: VehicleDialog) -> None:
            self.assertEqual(dialog.vehicle_number.text(), "V-1")
            self.assertEqual(dialog.make.text(), "Example")
            self.assertEqual(dialog.model.text(), "Pickup")

        self._complete_modal_dialog(
            self.window.promote_hit_run_vehicle_lead,
            VehicleDialog,
            configure_vehicle,
        )
        confirmed_vehicle = self.repository.list_vehicles(self.case.id)[0]
        promoted_vehicle_lead = self.repository.get_hit_run_vehicle_lead(vehicle_lead.id)
        self.assertEqual(promoted_vehicle_lead.status, "Confirmed")
        self.assertEqual(promoted_vehicle_lead.linked_vehicle_id, confirmed_vehicle.id)

        self.window.hit_run_person_leads_table.selectRow(0)

        def configure_person(dialog: PersonDialog) -> None:
            self.assertEqual(dialog.first_name.text(), "Casey")
            self.assertTrue(dialog.role_boxes["Suspect"].isChecked())

        self._complete_modal_dialog(
            self.window.promote_hit_run_person_lead,
            PersonDialog,
            configure_person,
        )
        confirmed_person = self.repository.list_people(self.case.id)[0]
        promoted_person_lead = self.repository.get_hit_run_person_lead(person_lead.id)
        self.assertIn("Suspect", confirmed_person.roles)
        self.assertEqual(promoted_person_lead.status, "Confirmed")
        self.assertEqual(promoted_person_lead.linked_person_id, confirmed_person.id)

    def test_packet_case_fields_round_trip(self):
        self.assertEqual(self.window.crash_date.placeholderText(), "MM/DD/YYYY")
        self.assertEqual(
            self.window.packet_widgets["team_notified_date"].placeholderText(),
            "MM/DD/YYYY",
        )
        self.window.crash_date.setText("08/04/2026")
        self.window.checklist_boxes["Participant Interviews"].setChecked(True)
        self.window.checklist_widgets["assigned_dda"].setText("Taylor Example")
        self.window.checklist_widgets["da_case_number"].setText("DA-26-100")
        self.window.checklist_widgets["court_case_number"].setText("COURT-26-200")
        self.window.packet_widgets["nearest_city"].setText("Gresham")
        self.window.packet_widgets["road_name"].setText("SE Stark Street")
        self.window.packet_widgets["intersection_road"].setText("SE 182nd Avenue")
        self.window.packet_widgets["team_notified_time"].setText("14:05")
        self.window.packet_widgets["team_notified_date"].setText("08/04/2026")
        self.window.scene_evidence_boxes["FARO"].setChecked(True)
        self.window.save_overview()

        checklist = self.repository.get_investigative_checklist(self.case.id)
        details = self.repository.get_crash_details(self.case.id)
        self.assertIn("Participant Interviews", checklist.completed_items)
        self.assertEqual(checklist.assigned_dda, "Taylor Example")
        self.assertEqual(checklist.da_case_number, "DA-26-100")
        self.assertEqual(checklist.court_case_number, "COURT-26-200")
        self.assertEqual(details.nearest_city, "Gresham")
        self.assertEqual(details.road_name, "SE Stark Street")
        self.assertEqual(details.intersection_road, "SE 182nd Avenue")
        self.assertEqual(details.team_notified_time, "14:05")
        self.assertEqual(details.team_notified_date, "2026-08-04")
        self.assertEqual(
            self.repository.get_case(self.case.id).crash_date,
            "2026-08-04",
        )
        self.assertEqual(details.scene_evidence, ["FARO"])
        self.assertEqual(
            self.repository.get_case(self.case.id).location,
            "SE Stark Street / SE 182nd Avenue",
        )
        self.assertEqual(
            self.window.location.text(),
            "SE Stark Street / SE 182nd Avenue",
        )
        self.assertTrue(self.window.location.isReadOnly())

        self.window.load_case(self.repository.get_case(self.case.id))
        self.assertEqual(self.window.crash_date.text(), "08/04/2026")
        self.assertEqual(
            self.window.packet_widgets["team_notified_date"].text(),
            "08/04/2026",
        )
        self.assertTrue(self.window.checklist_boxes["Participant Interviews"].isChecked())
        self.assertEqual(
            self.window.checklist_widgets["court_case_number"].text(),
            "COURT-26-200",
        )
        self.assertEqual(self.window.packet_widgets["nearest_city"].text(), "Gresham")
        self.assertTrue(self.window.scene_evidence_boxes["FARO"].isChecked())

    def test_date_and_time_fields_add_separators_while_typing(self):
        self.window.crash_date.setFocus()
        QTest.keyClicks(self.window.crash_date, "08042026")
        self.assertEqual(self.window.crash_date.text(), "08/04/2026")

        self.window.crash_time.setFocus()
        QTest.keyClicks(self.window.crash_time, "1435")
        self.assertEqual(self.window.crash_time.text(), "14:35")

        self.window.condition_widgets["weather_time"].setFocus()
        QTest.keyClicks(self.window.condition_widgets["weather_time"], "0830 PDT")
        self.assertEqual(self.window.condition_widgets["weather_time"].text(), "08:30 PDT")

    def test_reporting_checklist_uses_routing_statuses_and_completion_dates(self):
        self.assertNotIn("DIMS CD Ordered", self.window.checklist_boxes)
        self.assertIn("Toxicology", self.window.checklist_boxes)
        for retired_vehicle_item in (
            "Warrant",
            "Vehicle Inspection",
            "CDR Download",
            "CDR Downloaded",
            "CDR Download - Attach to RegJIN",
            "Insurance",
        ):
            self.assertNotIn(retired_vehicle_item, self.window.checklist_boxes)
        self.assertIn("Insurance - Exchange Report", self.window.checklist_boxes)
        self.assertNotIn("Release", self.window.checklist_boxes)
        self.assertIn("Crash Diagram Completed", self.window.checklist_boxes)
        self.assertIn("Axon Shared to DA", self.window.checklist_boxes)
        for item in (
            "Report Peer Reviewed",
            "Report Sgt Reviewed",
            "Submitted to DA",
        ):
            self.assertNotIn(item, self.window.checklist_boxes)
            self.assertIn(item, self.window.checklist_status_widgets)
        self.assertEqual(
            list(self.window.checklist_status_widgets)[-1],
            "Submitted to DA",
        )
        self.assertNotIn("submitted_to_da_date", self.window.checklist_widgets)

        routing_items = (
            "Report Peer Reviewed",
            "Report Sgt Reviewed",
            "Submitted to DA",
        )
        self.window.checklist_boxes["Crash Diagram Completed"].setChecked(True)
        self.window.checklist_boxes["Axon Shared to DA"].setChecked(True)
        for item in routing_items:
            status_widget = self.window.checklist_status_widgets[item]
            date_widget = self.window.checklist_date_widgets[item]
            self.assertEqual(
                [
                    status_widget.itemText(index)
                    for index in range(status_widget.count())
                ],
                ["Not Started", "Pending", "Complete"],
            )
            self.assertEqual(status_widget.currentText(), "Not Started")
            self.assertFalse(date_widget.isEnabled())
            self.assertEqual(date_widget.placeholderText(), "MM/DD/YYYY")
            status_widget.setCurrentText("Pending")
            self.assertFalse(date_widget.isEnabled())

        self.window.checklist_status_widgets["Report Peer Reviewed"].setCurrentText(
            "Complete"
        )
        peer_review_date = self.window.checklist_date_widgets["Report Peer Reviewed"]
        self.assertTrue(peer_review_date.isEnabled())
        peer_review_date.setText("08/01/2026")
        self.window.checklist_status_widgets["Submitted to DA"].setCurrentText(
            "Complete"
        )
        submitted_date = self.window.checklist_date_widgets["Submitted to DA"]
        self.assertTrue(submitted_date.isEnabled())
        submitted_date.setText("08/03/2026")
        self.window.checklist_status_widgets["Submitted to DA"].setCurrentText(
            "Not Started"
        )
        self.assertFalse(submitted_date.isEnabled())
        self.assertEqual(submitted_date.text(), "")

        self.window.save_overview()
        checklist = self.repository.get_investigative_checklist(self.case.id)
        self.assertIn("Crash Diagram Completed", checklist.completed_items)
        self.assertIn("Axon Shared to DA", checklist.completed_items)
        self.assertIn("Report Peer Reviewed", checklist.completed_items)
        self.assertNotIn("Report Sgt Reviewed", checklist.completed_items)
        self.assertNotIn("Submitted to DA", checklist.completed_items)
        self.assertEqual(checklist.peer_review_status, "Complete")
        self.assertEqual(checklist.sergeant_review_status, "Pending")
        self.assertEqual(checklist.submitted_to_da_status, "Not Started")
        self.assertEqual(checklist.peer_review_date, "2026-08-01")
        self.assertEqual(checklist.sergeant_review_date, "")
        self.assertEqual(checklist.submitted_to_da_date, "")

        self.window.load_case(self.repository.get_case(self.case.id))
        self.assertTrue(
            self.window.checklist_boxes["Crash Diagram Completed"].isChecked()
        )
        self.assertEqual(
            self.window.checklist_status_widgets["Report Peer Reviewed"].currentText(),
            "Complete",
        )
        self.assertEqual(peer_review_date.text(), "08/01/2026")
        self.assertTrue(peer_review_date.isEnabled())
        self.assertEqual(
            self.window.checklist_status_widgets["Report Sgt Reviewed"].currentText(),
            "Pending",
        )
        self.assertFalse(
            self.window.checklist_date_widgets["Report Sgt Reviewed"].isEnabled()
        )
        self.assertEqual(
            self.window.checklist_status_widgets["Submitted to DA"].currentText(),
            "Not Started",
        )
        self.assertFalse(submitted_date.isEnabled())

    def test_all_record_date_editors_display_us_dates_and_store_iso(self):
        person = Person(
            id=new_id(), case_id=self.case.id, first_name="Date", last_name="Test",
            dob="1985-01-02",
        )
        vehicle = Vehicle(id=new_id(), case_id=self.case.id, vehicle_number="V-1")

        person_dialog = PersonDialog(self.case.id, person)
        chronology_dialog = ChronologyDialog(
            self.case.id,
            ChronologyEntry(
                id=new_id(), case_id=self.case.id, event_date="2026-02-03",
            ),
        )
        task_dialog = TaskDialog(
            self.case.id,
            CaseTask(
                id=new_id(), case_id=self.case.id, due_date="2026-03-04",
                completed_date="2026-03-05",
            ),
        )
        property_receipt_dialog = PropertyReceiptDialog(
            self.case.id,
            PropertyReceipt(
                id=new_id(),
                case_id=self.case.id,
                lodged_date="2026-03-06",
            ),
        )
        driver_profile_dialog = DriverProfileDialog(
            person,
            DriverProfile(
                person_id=person.id,
                license_issued_date="2024-03-07",
                license_expiration_date="2032-03-08",
            ),
        )
        motorcycle_dialog = MotorcycleInspectionDialog(
            vehicle,
            MotorcycleInspection(vehicle_id=vehicle.id, inspection_date="2026-04-05"),
        )
        participant_dialog = ParticipantDetailsDialog(
            person,
            [vehicle],
            ParticipantDetails(person_id=person.id, date_of_death="2026-05-06"),
        )
        witness_dialog = WitnessDetailsDialog(
            person,
            WitnessDetails(person_id=person.id, interview_date="2026-06-07"),
        )

        expected_display_values = (
            (person_dialog.dob, "01/02/1985"),
            (chronology_dialog.event_date, "02/03/2026"),
            (task_dialog.due_date, "03/04/2026"),
            (task_dialog.completed_date, "03/05/2026"),
            (property_receipt_dialog.lodged_date, "03/06/2026"),
            (driver_profile_dialog.license_issued_date, "03/07/2024"),
            (driver_profile_dialog.license_expiration_date, "03/08/2032"),
            (motorcycle_dialog.inspection_date, "04/05/2026"),
            (participant_dialog.date_of_death, "05/06/2026"),
            (witness_dialog.interview_date, "06/07/2026"),
        )
        for widget, expected in expected_display_values:
            self.assertEqual(widget.text(), expected)
            self.assertEqual(widget.placeholderText(), "MM/DD/YYYY")

        person_dialog.dob.setText("01/12/1985")
        chronology_dialog.event_date.setText("02/13/2026")
        task_dialog.due_date.setText("03/14/2026")
        task_dialog.completed_date.setText("03/15/2026")
        property_receipt_dialog.lodged_date.setText("03/16/2026")
        driver_profile_dialog.license_issued_date.setText("03/17/2024")
        driver_profile_dialog.license_expiration_date.setText("03/18/2032")
        motorcycle_dialog.inspection_date.setText("04/16/2026")
        participant_dialog.date_of_death.setText("05/17/2026")
        witness_dialog.interview_date.setText("06/18/2026")

        self.assertEqual(person_dialog.result_record().dob, "1985-01-12")
        chronology_record = chronology_dialog.result_record()
        self.assertEqual(chronology_record.event_date, "2026-02-13")
        task_record = task_dialog.result_record()
        self.assertEqual(task_record.due_date, "2026-03-14")
        self.assertEqual(task_record.completed_date, "2026-03-15")
        self.assertEqual(
            property_receipt_dialog.result_record().lodged_date,
            "2026-03-16",
        )
        driver_profile_record = driver_profile_dialog.result_record()
        self.assertEqual(
            driver_profile_record.license_issued_date,
            "2024-03-17",
        )
        self.assertEqual(
            driver_profile_record.license_expiration_date,
            "2032-03-18",
        )
        self.assertEqual(
            motorcycle_dialog.result_record().inspection_date,
            "2026-04-16",
        )
        self.assertEqual(
            participant_dialog.result_record().date_of_death,
            "2026-05-17",
        )
        self.assertEqual(
            witness_dialog.result_record().interview_date,
            "2026-06-18",
        )

        chronology_record.summary = "Date format test"
        task_record.description = "Date format test"
        self.repository.save_chronology(chronology_record)
        self.repository.save_task(task_record)
        self.window.refresh_chronology()
        self.window.refresh_tasks()
        self.assertEqual(self.window.chronology_table.item(0, 0).text(), "02/13/2026")
        self.assertEqual(self.window.tasks_table.item(0, 3).text(), "03/14/2026")

    def test_property_receipt_owner_selector_uses_people_and_preserves_legacy_owner(self):
        owner = Person(
            id="person-owner",
            case_id=self.case.id,
            first_name="Alex",
            last_name="Example",
        )
        receipt = PropertyReceipt(
            id="receipt-legacy-owner",
            case_id=self.case.id,
            receipt_number="PR-LEGACY",
            property_owner="Legacy Property Owner",
        )

        dialog = PropertyReceiptDialog(
            self.case.id,
            receipt,
            people=[owner],
        )

        self.assertFalse(dialog.property_owner.isEditable())
        self.assertEqual(
            [
                dialog.property_owner.itemText(index)
                for index in range(dialog.property_owner.count())
            ],
            [
                "No property owner selected",
                owner.display_name,
                "Legacy owner: Legacy Property Owner",
            ],
        )
        self.assertEqual(
            dialog.property_owner.currentData(),
            "Legacy Property Owner",
        )
        self.assertEqual(
            dialog.result_record().property_owner,
            "Legacy Property Owner",
        )
        dialog.property_owner.setCurrentText(owner.display_name)
        self.assertEqual(
            dialog.result_record().property_owner,
            owner.display_name,
        )

    def test_weather_subtab_links_to_wunderground_history(self):
        weather_history_url = "https://www.wunderground.com/history"
        weather_history_link = self.window.findChild(
            QLabel,
            "weather_history_link",
        )
        self.assertIsNotNone(weather_history_link)
        self.assertIn(
            f'href="{weather_history_url}"',
            weather_history_link.text(),
        )
        self.assertIn(
            "Open Weather Underground History",
            weather_history_link.text(),
        )
        self.assertFalse(weather_history_link.openExternalLinks())
        with patch(
            "traffic_crash_notebook.ui.main_window.QDesktopServices.openUrl",
            return_value=True,
        ) as open_url:
            weather_history_link.linkActivated.emit(weather_history_url)
        open_url.assert_called_once()
        self.assertEqual(
            open_url.call_args.args[0].toString(),
            weather_history_url,
        )

    def test_weather_visibility_station_time_and_celestial_lighting_fields_persist(self):
        expected_values = {
            "temperature": "71",
            "dew_point": "54",
            "winds": "NW 6",
            "humidity": "43",
            "pressure": "29.92",
            "precipitation": "0.04",
            "visibility": "0.5",
            "weather_station": "KPDX ASOS",
            "weather_time": "14:35 PDT",
            "sunrise": "05:59",
            "sunset": "20:31",
            "civil_twilight_morning": "05:27",
            "civil_twilight_evening": "21:03",
            "moonrise": "22:44",
            "moonset": "11:28",
            "moon_phase": "Waxing gibbous",
        }
        labels = {label.text() for label in self.window.findChildren(QLabel)}
        self.assertIn("Weather station", labels)
        self.assertIn("Time of reading", labels)
        self.assertIn("Temperature (F)", labels)
        self.assertIn("Dew point (F)", labels)
        self.assertIn("Winds (mph)", labels)
        self.assertIn("Humidity (%)", labels)
        self.assertIn("Pressure (inHg)", labels)
        self.assertIn("Precipitation (in)", labels)
        self.assertIn("Visibility (mi)", labels)
        self.assertEqual(self.window.weather_fields_grid.rowCount(), 5)
        self.assertEqual(self.window.weather_fields_grid.verticalSpacing(), 5)
        self.assertEqual(self.window.weather_fields_grid.horizontalSpacing(), 10)
        self.assertEqual(
            self.window.weather_fields_grid.itemAtPosition(0, 0).widget().text(),
            "Weather station",
        )
        self.assertIs(
            self.window.weather_fields_grid.itemAtPosition(0, 1).widget(),
            self.window.condition_widgets["weather_station"],
        )
        self.assertEqual(
            self.window.weather_fields_grid.itemAtPosition(0, 2).widget().text(),
            "Time of reading",
        )
        self.assertIs(
            self.window.weather_fields_grid.itemAtPosition(0, 3).widget(),
            self.window.condition_widgets["weather_time"],
        )
        self.assertNotIn("Observation time", labels)
        self.assertIn("Civil twilight - morning", labels)
        self.assertIn("Civil twilight - evening", labels)
        self.assertIn("Moonrise", labels)
        self.assertIn("Moonset", labels)
        self.assertIn("Moon phase", labels)
        self.assertIn("Interstate", self.window.area_type_boxes)

        for name, value in expected_values.items():
            self.window.condition_widgets[name].setText(value)
        self.window.area_type_boxes["Interstate"].setChecked(True)
        self.window.save_overview()

        conditions = self.repository.get_road_conditions(self.case.id)
        for name, value in expected_values.items():
            self.assertEqual(getattr(conditions, name), value)
        self.assertEqual(conditions.area_classifications, "Interstate")

        self.window.load_case(self.repository.get_case(self.case.id))
        for name, value in expected_values.items():
            self.assertEqual(self.window.condition_widgets[name].text(), value)
        self.assertTrue(self.window.area_type_boxes["Interstate"].isChecked())

    def test_multiple_roadways_can_be_added_and_edited(self):
        retired_single_roadway_fields = {
            "speed_limit",
            "speed_limit_posted",
            "speed_limit_location",
            "curve_radius",
            "chord",
            "middle_ordinate",
            "critical_speed",
            "roadway_characteristics",
            "traffic_controls",
        }
        self.assertTrue(
            retired_single_roadway_fields.isdisjoint(self.window.condition_widgets)
        )
        self.assertEqual(
            self.window.roadways_table.horizontalHeaderItem(0).text(),
            "Roadway",
        )

        def add_roadway(
            roadway_name: str,
            speed_limit: str,
            characteristics: str,
            controls: str,
        ) -> None:
            def configure(dialog: RoadwayDialog) -> None:
                labels = {label.text() for label in dialog.findChildren(QLabel)}
                self.assertIn("Roadway", labels)
                self.assertNotIn("Roadway / tag", labels)
                dialog.roadway_tag.setText(roadway_name)
                dialog.speed_limit.setText(speed_limit)
                dialog.speed_limit_posted.setCurrentText("Yes")
                dialog.speed_limit_location.setText("Approach sign")
                dialog.roadway_characteristics.setPlainText(characteristics)
                dialog.traffic_controls.setPlainText(controls)

            self._complete_modal_dialog(
                self.window.add_roadway,
                RoadwayDialog,
                configure,
            )

        add_roadway(
            "North Main Street - northbound",
            "35",
            "Two northbound lanes",
            "Traffic signal",
        )
        add_roadway(
            "Cross Avenue - eastbound",
            "25",
            "Single eastbound lane",
            "Marked stop line",
        )

        roadways = self.repository.list_roadway_records(self.case.id)
        self.assertEqual(len(roadways), 2)
        self.assertEqual(self.window.roadways_table.rowCount(), 2)
        self.assertCountEqual(
            [record.roadway_tag for record in roadways],
            [
                "North Main Street - northbound",
                "Cross Avenue - eastbound",
            ],
        )

        north_row = next(
            row
            for row in range(self.window.roadways_table.rowCount())
            if self.window.roadways_table.item(row, 0).text()
            == "North Main Street - northbound"
        )
        self.window.roadways_table.setCurrentCell(north_row, 0)

        def configure_edit(dialog: RoadwayDialog) -> None:
            self.assertEqual(dialog.roadway_tag.text(), "North Main Street - northbound")
            dialog.speed_limit.setText("30")
            dialog.traffic_controls.setPlainText("Traffic signal and marked crosswalk")

        self._complete_modal_dialog(
            self.window.edit_roadway,
            RoadwayDialog,
            configure_edit,
        )
        updated = {
            record.roadway_tag: record
            for record in self.repository.list_roadway_records(self.case.id)
        }
        self.assertEqual(updated["North Main Street - northbound"].speed_limit, "30")
        self.assertIn(
            "marked crosswalk",
            updated["North Main Street - northbound"].traffic_controls,
        )

    def test_primary_phone_is_removed_while_legacy_values_are_preserved(self):
        person = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Legacy",
            last_name="Person",
            phone="LEGACY-PERSON-PRIMARY",
            cell_phone="503-555-0101",
        ))
        contact = self.repository.save_contact(ContactRelationship(
            id="",
            case_id=self.case.id,
            subject_person_id=person.id,
            contact_name="Legacy Contact",
            phone="LEGACY-CONTACT-PRIMARY",
            cell_phone="503-555-0102",
        ))

        person_dialog = PersonDialog(self.case.id, person, self.window)
        contact_dialog = ContactRelationshipDialog(
            self.case.id,
            [person],
            contact,
            self.window,
        )
        self.assertFalse(hasattr(person_dialog, "phone"))
        self.assertFalse(hasattr(contact_dialog, "phone"))
        self.assertNotIn(
            "Primary phone",
            {label.text() for label in person_dialog.findChildren(QLabel)},
        )
        self.assertNotIn(
            "Primary phone",
            {label.text() for label in contact_dialog.findChildren(QLabel)},
        )
        self.assertIn(
            "ZIP code",
            {label.text() for label in person_dialog.findChildren(QLabel)},
        )

        person_dialog.cell_phone.setText("503-555-0111")
        contact_dialog.cell_phone.setText("503-555-0112")
        updated_person = person_dialog.result_record()
        updated_contact = contact_dialog.result_record()
        self.assertEqual(updated_person.phone, "LEGACY-PERSON-PRIMARY")
        self.assertEqual(updated_contact.phone, "LEGACY-CONTACT-PRIMARY")
        self.repository.save_person(updated_person)
        self.repository.save_contact(updated_contact)
        self.window.refresh_people()
        self.window.refresh_contacts()
        self.assertEqual(self.window.people_table.horizontalHeaderItem(3).text(), "Cell")
        self.assertEqual(self.window.people_table.item(0, 3).text(), "503-555-0111")
        self.assertEqual(self.window.contacts_table.item(0, 3).text(), "503-555-0112")
        person_dialog.close()
        contact_dialog.close()

    def test_crash_location_form_omits_retired_fields_and_uses_city_label(self):
        retired_fields = {
            "outside_city_feet",
            "outside_city_miles",
            "outside_city_direction",
            "non_intersection_reference",
        }
        self.assertTrue(retired_fields.isdisjoint(self.window.packet_widgets))

        labels = {label.text() for label in self.window.findChildren(QLabel)}
        self.assertIn("City", labels)
        self.assertNotIn("Nearest city", labels)
        self.assertNotIn("Outside city - feet", labels)
        self.assertNotIn("Outside city - miles", labels)
        self.assertNotIn("Outside city - direction", labels)
        self.assertNotIn("Not at intersection - reference", labels)

    def test_files_section_is_not_available_in_the_workspace(self):
        tab_names = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertNotIn("Files", tab_names)
        self.assertFalse(hasattr(self.window, "files_table"))

    def test_contacts_are_nested_under_people_and_require_a_person(self):
        top_level_tabs = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertNotIn("Contacts", top_level_tabs)
        self.assertIn("People", top_level_tabs)
        self.assertEqual(
            [
                self.window.people_tabs.tabText(index)
                for index in range(self.window.people_tabs.count())
            ],
            ["People", "Contacts"],
        )

        person = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Contact",
            last_name="Subject",
        ))
        dialog = ContactRelationshipDialog(
            self.case.id,
            [person],
            parent=self.window,
        )
        self.assertFalse(hasattr(dialog, "vehicle"))
        dialog.contact_name.setText("Related person")
        with patch(
            "traffic_crash_notebook.ui.dialogs.QMessageBox.warning"
        ) as warning:
            dialog._validate_and_accept()
        warning.assert_called_once()
        self.assertIn("person", warning.call_args.args[2].lower())
        dialog.close()

    def test_diagrams_workspace_is_removed_but_completion_checkbox_remains(self):
        tab_names = [
            self.window.tabs.tabText(index)
            for index in range(self.window.tabs.count())
        ]
        self.assertNotIn("Diagrams", tab_names)
        self.assertFalse(hasattr(self.window, "diagrams_table"))
        self.assertIn("Crash Diagram Completed", self.window.checklist_boxes)

    def test_response_evidence_uses_revised_personnel_and_evidence_fields(self):
        labels = {label.text() for label in self.window.findChildren(QLabel)}
        self.assertIn("MCT Sergeant", labels)
        self.assertIn("MDI", labels)
        self.assertNotIn("Sergeant", labels)
        self.assertNotIn("Medical examiner on scene", labels)
        self.assertNotIn("Criminalist on scene", labels)
        self.assertNotIn("criminalist_on_scene", self.window.packet_widgets)
        self.assertNotIn("Crime Scene Log", self.window.checklist_boxes)

        self.assertEqual(
            set(self.window.scene_evidence_boxes),
            {
                "FED Photos",
                "Investigator Photos",
                "Uploaded to Axon",
                "UAS",
                "Axon",
                "FARO",
            },
        )
        self.assertNotIn("Video Taken", self.window.scene_evidence_boxes)
        self.assertNotIn("Surveillance Video", self.window.scene_evidence_boxes)
        self.assertNotIn("PED", self.window.scene_evidence_boxes)
        self.assertNotIn("Trimble", self.window.scene_evidence_boxes)
        self.assertEqual(
            [
                self.window.video_sources_table.horizontalHeaderItem(index).text()
                for index in range(self.window.video_sources_table.columnCount())
            ],
            ["Video source", "Address", "Uploaded to Axon", "Notes"],
        )
        video_dialog = VideoSourceDialog(self.case.id, parent=self.window)
        video_labels = {
            label.text() for label in video_dialog.findChildren(QLabel)
        }
        self.assertIn("Address", video_labels)
        self.assertIn("Uploaded to Axon", video_labels)
        self.assertNotIn("Entered in DIMS", video_labels)
        video_dialog.source.setText("Business camera")
        with patch(
            "traffic_crash_notebook.ui.dialogs.QMessageBox.warning"
        ) as warning:
            video_dialog._validate_and_accept()
        warning.assert_called_once()
        self.assertIn("address", warning.call_args.args[2].lower())
        video_dialog.close()

    def test_axon_upload_requires_investigator_photos(self):
        photos = self.window.scene_evidence_boxes["Investigator Photos"]
        axon = self.window.scene_evidence_boxes["Uploaded to Axon"]
        self.assertFalse(axon.isEnabled())
        self.assertFalse(axon.isChecked())

        photos.setChecked(True)
        self.assertTrue(axon.isEnabled())
        axon.setChecked(True)
        self.window.save_overview()
        self.assertEqual(
            self.repository.get_crash_details(self.case.id).scene_evidence,
            ["Investigator Photos", "Uploaded to Axon"],
        )

        photos.setChecked(False)
        self.assertFalse(axon.isEnabled())
        self.assertFalse(axon.isChecked())

    def test_legacy_overview_location_is_adopted_by_crash_location_fields(self):
        self.case.location = "Legacy Road / Legacy Avenue"
        self.repository.save_case(self.case)

        self.window.load_case(self.repository.get_case(self.case.id))

        self.assertEqual(self.window.packet_widgets["road_name"].text(), "Legacy Road")
        self.assertEqual(
            self.window.packet_widgets["intersection_road"].text(),
            "Legacy Avenue",
        )
        self.assertEqual(self.window.location.text(), "Legacy Road / Legacy Avenue")

    def test_narrative_fields_use_offline_spell_check(self):
        self.assertIsInstance(self.window.summary, SpellCheckedTextEdit)
        self.assertIsInstance(self.window.general_notes, SpellCheckedTextEdit)
        self.assertFalse(hasattr(self.window, "key_questions"))
        self.assertNotIn(
            "Key questions / unresolved issues",
            {label.text() for label in self.window.findChildren(QLabel)},
        )

        dialog = PersonDialog(self.case.id, parent=self.window)
        try:
            self.assertIsInstance(dialog.address, SpellCheckedLineEdit)
            self.assertIsInstance(dialog.notes, SpellCheckedTextEdit)
        finally:
            dialog.close()

        toolbar = self.window.findChild(QToolBar)
        self.assertIsNotNone(toolbar)
        self.assertNotIn("Spell Check", [action.text() for action in toolbar.actions()])
        self.assertFalse(hasattr(self.window, "spell_check_action"))

    def test_person_street_address_is_single_line_and_tabs_to_city(self):
        dialog = PersonDialog(self.case.id, parent=self.window)
        try:
            dialog.show()
            self.app.processEvents()
            self.assertIn(
                "Street address",
                {label.text() for label in dialog.findChildren(QLabel)},
            )
            dialog.address.setPlainText("123 Example Street\nApartment 4")
            self.assertEqual(dialog.address.text(), "123 Example Street Apartment 4")
            dialog.address.setFocus()
            QTest.keyClick(dialog.address, Qt.Key.Key_Tab)
            self.app.processEvents()
            self.assertTrue(dialog.city.hasFocus())
        finally:
            dialog.close()

    def test_add_charge_and_video_source_refresh_packet_tables(self):
        def configure_charge(dialog: ChargeDispositionDialog) -> None:
            dialog.charge.setText("Reckless Driving")
            dialog.disposition.setText("Issued")

        self._complete_modal_dialog(
            self.window.add_charge_disposition,
            ChargeDispositionDialog,
            configure_charge,
        )

        def configure_video(dialog: VideoSourceDialog) -> None:
            dialog.source.setText("North intersection camera")
            dialog.address.setText("100 North Example Street, Portland, OR 97201")
            dialog.axon_status.setCurrentText("Yes")
            dialog.notes.setPlainText("Requested from city traffic operations")

        self._complete_modal_dialog(
            self.window.add_video_source,
            VideoSourceDialog,
            configure_video,
        )

        self.assertEqual(len(self.repository.list_charge_dispositions(self.case.id)), 1)
        self.assertEqual(self.window.charges_table.rowCount(), 1)
        self.assertEqual(len(self.repository.list_video_sources(self.case.id)), 1)
        self.assertEqual(self.window.video_sources_table.rowCount(), 1)
        self.assertEqual(
            self.window.video_sources_table.item(0, 1).text(),
            "100 North Example Street, Portland, OR 97201",
        )
        self.assertEqual(self.window.video_sources_table.item(0, 2).text(), "Yes")
        self.assertTrue(self.window.surveillance_video_indicator.isChecked())
        self.assertFalse(self.window.surveillance_video_indicator.isEnabled())
        self.assertNotIn(
            "Surveillance Video",
            self.repository.get_crash_details(self.case.id).scene_evidence,
        )

        video_source = self.repository.list_video_sources(self.case.id)[0]
        self.assertEqual(
            video_source.address,
            "100 North Example Street, Portland, OR 97201",
        )
        self.assertEqual(video_source.axon_status, "Yes")
        self.repository.delete_video_source(video_source.id)
        self.window.refresh_video_sources()
        self.assertFalse(self.window.surveillance_video_indicator.isChecked())

    def test_expanded_packet_dialogs_persist_structured_data(self):
        person = self.repository.save_person(Person(
            id="", case_id=self.case.id, first_name="Riley", last_name="Example",
            roles=["Driver", "Pedestrian", "Witness"],
        ))
        vehicle = self.repository.save_vehicle(Vehicle(
            id="", case_id=self.case.id, vehicle_number="V-1", make="Example",
            model="Motorcycle", driver_person_id=person.id,
        ))
        self.window.refresh_case_tables()

        self.window.people_table.setCurrentCell(0, 0)

        def configure_participant(dialog: ParticipantDetailsDialog) -> None:
            dialog.height_value.setText("70 in")
            dialog.weight_value.setText("180 lb")
            dialog.hospital.setText("OHSU")
            participant_form = dialog.findChild(QTabWidget).widget(0).layout()
            self.assertEqual(
                participant_form.labelForField(dialog.helmet).text(),
                "Helmet",
            )
            self.assertEqual(
                participant_form.getWidgetPosition(dialog.helmet)[0],
                participant_form.getWidgetPosition(dialog.airbag_deployed)[0] + 1,
            )
            self.assertEqual(
                [dialog.helmet.itemText(index) for index in range(dialog.helmet.count())],
                ["Yes", "No", "Non-Standard", "Not Applicable"],
            )
            self.assertEqual(dialog.helmet.currentText(), "Not Applicable")
            dialog.helmet.setCurrentText("Non-Standard")
            dialog.ejected.setCurrentText("No")
            dialog.extracted.setCurrentText("Yes")
            dialog.injury_code_boxes["1 - Laceration"].setChecked(True)
            dialog.evidence_item_boxes["Blood"].setChecked(True)

        self._complete_modal_dialog(
            self.window.edit_participant_details,
            ParticipantDetailsDialog,
            configure_participant,
        )

        def configure_driver(dialog: DriverProfileDialog) -> None:
            tabs = dialog.findChild(QTabWidget)
            self.assertEqual(tabs.tabText(0), "License")
            license_form = tabs.widget(0).layout()
            license_fields = (
                dialog.license_number,
                dialog.license_state,
                dialog.license_class,
                dialog.license_status,
                dialog.license_issued_date,
                dialog.license_expiration_date,
                dialog.endorsements,
                dialog.license_restrictions,
                dialog.license_restriction_explanation,
                dialog.driving_history,
            )
            self.assertEqual(
                [license_form.labelForField(field).text() for field in license_fields],
                [
                    "License Number",
                    "License State",
                    "Class",
                    "Status",
                    "Issued",
                    "Expiration",
                    "Endorsements",
                    "Restrictions",
                    "Restrictions Explained",
                    "Driving History",
                ],
            )
            self.assertFalse(hasattr(dialog, "license_restricted"))
            self.assertFalse(hasattr(dialog, "driver_notes"))
            dialog.physical_condition_boxes["Vision"].setChecked(True)
            dialog.testing_method_boxes["SFST"].setChecked(True)
            dialog.license_number.setText("DL-24680")
            dialog.license_state.setText("OR")
            dialog.license_class.setText("C")
            dialog.license_status.setText("Valid")
            dialog.license_issued_date.setText("07/01/2024")
            dialog.license_expiration_date.setText("07/01/2032")
            dialog.license_restrictions.setText("Restriction B")
            dialog.license_restriction_explanation.setText("Corrective lenses")
            dialog.endorsements.setText("Passenger; Tank")
            dialog.driving_history.setPlainText(
                "No preventable collisions documented."
            )

        self._complete_modal_dialog(
            self.window.edit_driver_profile,
            DriverProfileDialog,
            configure_driver,
        )

        def configure_contact(dialog: ContactRelationshipDialog) -> None:
            self.assertEqual(dialog.subject_person.currentData(), person.id)
            self.assertFalse(hasattr(dialog, "vehicle"))
            dialog.contact_name.setText("Morgan Example")
            dialog.cell_phone.setText("503-555-0101")
            dialog.home_phone.setText("503-555-0102")
            dialog.work_phone.setText("503-555-0103")
            dialog.city.setText("Portland")
            dialog.state.setText("OR")

        self._complete_modal_dialog(
            self.window.add_contact,
            ContactRelationshipDialog,
            configure_contact,
        )

        def configure_vru(dialog: VRUAnalysisDialog) -> None:
            subject_form = dialog.findChild(QTabWidget).widget(0).layout()
            self.assertEqual(
                subject_form.labelForField(dialog.person_id).text(),
                "Vulnerable road user",
            )
            dialog.person_id.setCurrentIndex(dialog.person_id.findData(person.id))
            dialog.projection_boxes["Roof Vault"].setChecked(True)
            dialog.light_meter_used.setChecked(True)
            dialog.light_board_used.setChecked(True)
            tabs = dialog.findChild(QTabWidget)
            tab_names = [tabs.tabText(index) for index in range(tabs.count())]
            self.assertIn("Night Visibility", tab_names)
            self.assertIn("Notes", tab_names)
            self.assertNotIn("Perception / Response", tab_names)
            for retired_attribute in (
                "night_test_parameters", "detection_distance", "distance_adjustment",
                "result_67_percent", "result_15_percentile", "prt_base", "prt_total",
                "prt_justification", "prt_factor_boxes",
            ):
                self.assertFalse(hasattr(dialog, retired_attribute))

        self._complete_modal_dialog(
            self.window.add_vru_analysis,
            VRUAnalysisDialog,
            configure_vru,
        )

        def configure_surface(dialog: SurfaceObservationDialog) -> None:
            dialog.location.setText("Northbound lane")
            dialog.composition.setText("Asphalt")
            dialog.condition.setText("Wet")
            dialog.friction_value.setText("0.48")

        self._complete_modal_dialog(
            self.window.add_surface_observation,
            SurfaceObservationDialog,
            configure_surface,
        )

        self.window.vehicles_table.setCurrentCell(0, 0)

        def configure_vehicle_inspection(dialog: VehicleInspectionDialog) -> None:
            equipped, operable = dialog.system_check_widgets["headlights"]
            equipped.setCurrentText("Yes")
            operable.setCurrentText("No")
            dialog.tire_contribution.setCurrentText("Yes")
            dialog.tire_contribution_explanation.setPlainText("RF tread separation")

        self._complete_modal_dialog(
            self.window.edit_vehicle_inspection,
            VehicleInspectionDialog,
            configure_vehicle_inspection,
        )

        def configure_motorcycle(dialog: MotorcycleInspectionDialog) -> None:
            dialog.frame_number.setText("FRAME-1")
            dialog.item_rating_widgets[8].setCurrentText("2 - Damaged")
            dialog.item_table.item(7, 3).setText("20 psi")

        self._complete_modal_dialog(
            self.window.edit_motorcycle_inspection,
            MotorcycleInspectionDialog,
            configure_motorcycle,
        )

        details = self.repository.get_participant_details(person.id)
        self.assertEqual(details.height, "70 in")
        self.assertEqual(details.ejected, "No")
        self.assertEqual(details.extracted, "Yes")
        self.assertEqual(details.helmet, "Non-Standard")
        self.assertIn("Laceration", details.injury_codes)
        profile = self.repository.get_driver_profile(person.id)
        self.assertEqual(profile.license_restricted, "Yes")
        self.assertEqual(profile.license_number, "DL-24680")
        self.assertEqual(profile.license_state, "OR")
        self.assertEqual(profile.license_class, "C")
        self.assertEqual(profile.license_status, "Valid")
        self.assertEqual(profile.license_issued_date, "2024-07-01")
        self.assertEqual(profile.license_expiration_date, "2032-07-01")
        self.assertEqual(profile.license_restrictions, "Restriction B")
        self.assertEqual(
            profile.license_restriction_explanation,
            "Corrective lenses",
        )
        self.assertEqual(profile.endorsements, "Passenger; Tank")
        self.assertEqual(
            profile.notes,
            "No preventable collisions documented.",
        )
        self.assertIn("SFST", profile.testing_methods)
        contact = self.repository.list_contacts(self.case.id)[0]
        self.assertEqual(contact.work_phone, "503-555-0103")
        analysis = self.repository.list_vru_analyses(self.case.id)[0]
        self.assertEqual(analysis.projection_classifications, "Roof Vault")
        self.assertTrue(analysis.light_meter_used)
        self.assertTrue(analysis.light_board_used)
        self.assertEqual(self.window.vru_table.item(0, 3).text(), "Light meter, Light board")
        self.assertEqual(
            self.window.vru_table.horizontalHeaderItem(0).text(),
            "Vulnerable Road User",
        )
        self.assertEqual(
            self.repository.list_surface_observations(self.case.id)[0].friction_value,
            "0.48",
        )
        inspection = self.repository.get_vehicle_inspection(vehicle.id)
        self.assertEqual(inspection.headlights_operable, "No")
        self.assertEqual(inspection.tire_contribution_explanation, "RF tread separation")
        motorcycle = self.repository.get_motorcycle_inspection(vehicle.id)
        self.assertEqual(motorcycle.frame_number, "FRAME-1")
        self.assertEqual(motorcycle.items[0].measurement, "20 psi")

    def test_person_dialog_keeps_save_visible_in_a_compact_window(self):
        dialog = PersonDialog(self.case.id, parent=self.window)
        dialog.resize(600, 420)
        dialog.show()
        self.app.processEvents()

        save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.assertTrue(save.isVisible())
        self.assertLessEqual(dialog.height(), 420)
        self.assertLessEqual(
            dialog.buttons.geometry().bottom(),
            dialog.rect().bottom(),
        )
        self.assertGreater(dialog.scroll_area.verticalScrollBar().maximum(), 0)

    def test_vehicle_dialog_keeps_save_visible_in_a_compact_window(self):
        dialog = VehicleDialog(self.case.id, [], parent=self.window)
        dialog.resize(600, 420)
        dialog.show()
        self.app.processEvents()

        save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.assertTrue(save.isVisible())
        self.assertLessEqual(dialog.height(), 420)
        self.assertLessEqual(
            dialog.buttons.geometry().bottom(),
            dialog.rect().bottom(),
        )
        self.assertGreater(dialog.scroll_area.verticalScrollBar().maximum(), 0)

    def test_packet_forms_scroll_in_compact_main_window(self):
        self.window.resize(900, 560)
        self.app.processEvents()
        toolbar = self.window.findChild(QToolBar)
        self.assertIn(
            "Packet Preview",
            [action.text() for action in toolbar.actions()],
        )
        self.window.tabs.setCurrentIndex(1)
        packet_tab = self.window.tabs.currentWidget()
        nested_tabs = packet_tab.findChild(QTabWidget)
        self.assertIsNotNone(nested_tabs)
        nested_tabs.setCurrentIndex(2)
        self.app.processEvents()
        scroll_area = nested_tabs.currentWidget()
        self.assertIsInstance(scroll_area, QScrollArea)
        self.assertGreater(scroll_area.verticalScrollBar().maximum(), 0)


if __name__ == "__main__":
    unittest.main()
