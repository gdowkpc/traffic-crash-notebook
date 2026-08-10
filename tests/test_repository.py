from __future__ import annotations

import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from traffic_crash_notebook.models import (
    CaseTask,
    ChargeDisposition,
    ChronologyEntry,
    ContactRelationship,
    CrashDetails,
    DiagramRecord,
    DriverProfile,
    ExchangeReportDetails,
    FileReference,
    HitRunEvidenceItem,
    HitRunOverview,
    HitRunPersonLead,
    HitRunVehicleLead,
    InvestigativeChecklist,
    MotorcycleInspection,
    MotorcycleInspectionItem,
    ParticipantDetails,
    Person,
    PropertyReceipt,
    PropertyReceiptItem,
    RoadConditions,
    RoadwayRecord,
    SurfaceObservation,
    TireInspection,
    UserDefaults,
    Vehicle,
    VehicleInspection,
    VideoSource,
    VRUAnalysis,
    WitnessDetails,
)
from traffic_crash_notebook.repository import SCHEMA_VERSION, CaseRepository, new_id


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "case-notes.sqlite3"
        self.repository = CaseRepository(self.database)
        self.case = self.repository.create_case("26-000001", "Test Investigator")

    def tearDown(self):
        self.temp.cleanup()

    def test_user_defaults_round_trip_with_case_database(self):
        saved = self.repository.save_user_defaults(UserDefaults(
            user_name="Officer Taylor",
            dpsst="012345",
            assignment="Traffic Investigations Unit",
            auto_check_updates=False,
            last_update_check="2026-08-05T21:00:00+00:00",
        ))
        self.assertTrue(saved.updated_at)

        reopened = CaseRepository(self.database)
        defaults = reopened.get_user_defaults()
        self.assertEqual(defaults.user_name, "Officer Taylor")
        self.assertEqual(defaults.dpsst, "012345")
        self.assertEqual(defaults.assignment, "Traffic Investigations Unit")
        self.assertFalse(defaults.auto_check_updates)
        self.assertEqual(defaults.last_update_check, "2026-08-05T21:00:00+00:00")

        new_case = reopened.create_case(
            "26-DEFAULTS",
            defaults.user_name,
            defaults.dpsst,
            defaults.assignment,
        )
        self.assertEqual(new_case.investigator, "Officer Taylor")
        self.assertEqual(new_case.assigned_officer_dpsst, "012345")
        self.assertEqual(new_case.assignment, "Traffic Investigations Unit")

    def test_case_round_trip_and_counts(self):
        self.case.location = "Test Road at Example Avenue"
        self.case.assigned_officer_dpsst = "54321"
        self.case.assignment = "Traffic Division"
        self.case.summary = "Working summary"
        self.repository.save_case(self.case)

        person = Person(
            id=new_id(), case_id=self.case.id, first_name="Alex", last_name="Smith",
            roles=["Driver", "Victim"],
        )
        self.repository.save_person(person)
        self.repository.save_vehicle(Vehicle(
            id=new_id(), case_id=self.case.id, vehicle_number="V-1", make="Ford",
            model="Explorer", driver_person_id=person.id, owner_person_id=person.id,
        ))
        self.repository.save_chronology(ChronologyEntry(
            id=new_id(), case_id=self.case.id, event_date="2026-01-02",
            summary="Scene documented",
        ))
        self.repository.save_task(CaseTask(
            id=new_id(), case_id=self.case.id, description="Obtain medical records", status="Open",
        ))

        loaded = self.repository.get_case(self.case.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.location, "Test Road at Example Avenue")
        self.assertEqual(loaded.assigned_officer_dpsst, "54321")
        self.assertEqual(loaded.assignment, "Traffic Division")
        self.assertEqual(self.repository.get_person(person.id).roles, ["Driver", "Vehicle Owner", "Victim"])
        self.assertEqual(self.repository.case_counts(self.case.id), {
            "people": 1, "vehicles": 1, "chronology": 1, "open_tasks": 1,
            "injured": 0, "fatal": 0, "vru": 0,
        })
        self.repository.save_participant_details(ParticipantDetails(
            person_id=person.id,
            injury_status="Deceased",
        ))
        counts = self.repository.case_counts(self.case.id)
        self.assertEqual(counts["injured"], 0)
        self.assertEqual(counts["fatal"], 1)

    def test_property_receipts_own_numbered_items_and_cascade_on_delete(self):
        receipt = self.repository.save_property_receipt(PropertyReceipt(
            id="",
            case_id=self.case.id,
            receipt_number="PR-24680",
            property_owner="Alex Smith",
            lodging_type="Evidence",
            lodged_location="Central Property Room",
            lodged_date="2026-08-06",
        ))
        first = self.repository.save_property_receipt_item(PropertyReceiptItem(
            id="",
            receipt_id=receipt.id,
            item_number=1,
            description="Black plastic mirror housing",
        ))
        second = self.repository.save_property_receipt_item(PropertyReceiptItem(
            id="",
            receipt_id=receipt.id,
            item_number=2,
            description="Paint transfer sample",
        ))

        loaded_receipt = self.repository.get_property_receipt(receipt.id)
        self.assertEqual(loaded_receipt.receipt_number, "PR-24680")
        self.assertEqual(loaded_receipt.property_owner, "Alex Smith")
        self.assertEqual(loaded_receipt.lodging_type, "Evidence")
        self.assertEqual(loaded_receipt.lodged_location, "Central Property Room")
        self.assertEqual(loaded_receipt.lodged_date, "2026-08-06")
        self.assertEqual(
            [item.item_number for item in self.repository.list_property_receipt_items(receipt.id)],
            [1, 2],
        )
        self.assertEqual(
            self.repository.next_property_receipt_item_number(receipt.id),
            3,
        )

        second.description = "Blue paint transfer sample"
        self.repository.save_property_receipt_item(second)
        self.assertEqual(
            self.repository.get_property_receipt_item(second.id).description,
            "Blue paint transfer sample",
        )
        with self.assertRaisesRegex(ValueError, "Item 1 already exists"):
            self.repository.save_property_receipt_item(PropertyReceiptItem(
                id="",
                receipt_id=receipt.id,
                item_number=1,
                description="Duplicate item number",
            ))

        self.repository.delete_property_receipt_item(first.id)
        self.assertEqual(
            [item.item_number for item in self.repository.list_property_receipt_items(receipt.id)],
            [2],
        )
        self.repository.delete_property_receipt(receipt.id)
        self.assertIsNone(self.repository.get_property_receipt(receipt.id))
        self.assertEqual(self.repository.list_property_receipt_items(receipt.id), [])

    def test_schema_26_database_adds_property_receipt_tables(self):
        with self.repository._connect() as connection:
            connection.execute("DROP TABLE property_receipt_items")
            connection.execute("DROP TABLE property_receipts")
            connection.execute("PRAGMA user_version = 26")

        migrated = CaseRepository(self.database)
        receipt = migrated.save_property_receipt(PropertyReceipt(
            id="",
            case_id=self.case.id,
            receipt_number="MIGRATED-PR",
        ))
        migrated.save_property_receipt_item(PropertyReceiptItem(
            id="",
            receipt_id=receipt.id,
            item_number=1,
            description="Preserved case can use the new evidence tables.",
        ))
        self.assertEqual(
            migrated.list_property_receipt_items(receipt.id)[0].description,
            "Preserved case can use the new evidence tables.",
        )
        with migrated._connect() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_27_driver_profiles_receive_license_dates_without_data_loss(self):
        person = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Legacy",
            last_name="License Holder",
            roles=["Driver"],
        ))
        self.repository.save_driver_profile(DriverProfile(
            person_id=person.id,
            license_number="LEGACY-DL-27",
            license_state="OR",
            endorsements="Tank",
            notes="Preserve this driving history.",
        ))
        with self.repository._connect() as connection:
            connection.execute(
                "ALTER TABLE driver_profiles DROP COLUMN license_issued_date"
            )
            connection.execute(
                "ALTER TABLE driver_profiles DROP COLUMN license_expiration_date"
            )
            connection.execute("PRAGMA user_version = 27")

        migrated = CaseRepository(self.database)
        profile = migrated.get_driver_profile(person.id)
        self.assertEqual(profile.license_number, "LEGACY-DL-27")
        self.assertEqual(profile.license_state, "OR")
        self.assertEqual(profile.endorsements, "Tank")
        self.assertEqual(profile.notes, "Preserve this driving history.")
        self.assertEqual(profile.license_issued_date, "")
        self.assertEqual(profile.license_expiration_date, "")
        profile.license_issued_date = "2020-01-02"
        profile.license_expiration_date = "2028-01-02"
        migrated.save_driver_profile(profile)
        reloaded = migrated.get_driver_profile(person.id)
        self.assertEqual(reloaded.license_issued_date, "2020-01-02")
        self.assertEqual(reloaded.license_expiration_date, "2028-01-02")
        with migrated._connect() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_28_participant_receives_helmet_without_data_loss(self):
        person = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Legacy",
            last_name="Participant",
            roles=["Passenger"],
        ))
        self.repository.save_participant_details(ParticipantDetails(
            person_id=person.id,
            airbag_deployed="No",
            ejected="No",
            notes="Preserve this participant record.",
        ))
        with self.repository._connect() as connection:
            connection.execute("ALTER TABLE participant_details DROP COLUMN helmet")
            connection.execute("PRAGMA user_version = 28")

        migrated = CaseRepository(self.database)
        details = migrated.get_participant_details(person.id)
        self.assertEqual(details.airbag_deployed, "No")
        self.assertEqual(details.ejected, "No")
        self.assertEqual(details.notes, "Preserve this participant record.")
        self.assertEqual(details.helmet, "Not Applicable")
        details.helmet = "Yes"
        migrated.save_participant_details(details)
        self.assertEqual(
            migrated.get_participant_details(person.id).helmet,
            "Yes",
        )
        with migrated._connect() as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(participant_details)"
                ).fetchall()
            }
            self.assertIn("helmet", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_29_checklist_receives_routing_statuses_without_data_loss(self):
        self.repository.save_investigative_checklist(InvestigativeChecklist(
            case_id=self.case.id,
            completed_items=["Report Peer Reviewed", "Report Sgt Reviewed"],
            peer_review_date="2026-08-01",
            assigned_dda="Preserved DDA",
        ))
        with self.repository._connect() as connection:
            connection.execute(
                "ALTER TABLE investigative_checklists DROP COLUMN peer_review_status"
            )
            connection.execute(
                "ALTER TABLE investigative_checklists DROP COLUMN sergeant_review_status"
            )
            connection.execute(
                "ALTER TABLE investigative_checklists DROP COLUMN submitted_to_da_status"
            )
            connection.execute("PRAGMA user_version = 29")

        migrated = CaseRepository(self.database)
        checklist = migrated.get_investigative_checklist(self.case.id)
        self.assertEqual(checklist.peer_review_status, "Complete")
        self.assertEqual(checklist.sergeant_review_status, "Complete")
        self.assertEqual(checklist.submitted_to_da_status, "Not Started")
        self.assertEqual(checklist.peer_review_date, "2026-08-01")
        self.assertEqual(checklist.assigned_dda, "Preserved DDA")

        checklist.completed_items = ["Submitted to DA"]
        checklist.peer_review_status = "Pending"
        checklist.sergeant_review_status = "Not Started"
        checklist.submitted_to_da_status = "Complete"
        checklist.peer_review_date = ""
        checklist.submitted_to_da_date = "2026-08-02"
        migrated.save_investigative_checklist(checklist)
        reloaded = migrated.get_investigative_checklist(self.case.id)
        self.assertEqual(reloaded.peer_review_status, "Pending")
        self.assertEqual(reloaded.sergeant_review_status, "Not Started")
        self.assertEqual(reloaded.submitted_to_da_status, "Complete")
        self.assertEqual(reloaded.submitted_to_da_date, "2026-08-02")
        with migrated._connect() as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(investigative_checklists)"
                ).fetchall()
            }
            self.assertTrue({
                "peer_review_status",
                "sergeant_review_status",
                "submitted_to_da_status",
            }.issubset(columns))
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_legacy_dims_scene_evidence_is_normalized_to_axon(self):
        self.repository.save_crash_details(CrashDetails(case_id=self.case.id))
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE crash_details SET scene_evidence_json=? WHERE case_id=?",
                ('["DIMS", "FARO", "Axon"]', self.case.id),
            )
            connection.commit()

        details = self.repository.get_crash_details(self.case.id)
        self.assertEqual(details.scene_evidence, ["Axon", "FARO"])
        self.repository.save_crash_details(details)

        with closing(sqlite3.connect(self.database)) as connection:
            stored = connection.execute(
                "SELECT scene_evidence_json FROM crash_details WHERE case_id=?",
                (self.case.id,),
            ).fetchone()[0]
        self.assertNotIn("DIMS", stored)
        self.assertIn("Axon", stored)

    def test_vehicle_workflow_and_insurance_round_trip(self):
        vehicle = self.repository.save_vehicle(Vehicle(
            id=new_id(),
            case_id=self.case.id,
            vehicle_number="V-1",
            insurance_company="Example Mutual",
            insurance_policy_number="POL-24680",
            insurance_claim_number="CLM-86420",
            insurance_adjuster_name="Casey Adjuster",
            insurance_adjuster_phone="503-555-0160",
            insurance_adjuster_email="casey.adjuster@example.com",
            body_style="Four-door SUV",
            property_damage="None",
            towed=True,
            tow_information="Central Tow Yard",
            warrant_obtained=True,
            vehicle_inspection_completed=True,
            nhtsa_recalls_checked=True,
            cdr_equipped=True,
            cdr_imaged=True,
            cdr_report_uploaded=True,
            released=True,
            release_date="2026-08-05",
            release_information="Released to registered owner with receipt",
        ))

        loaded = self.repository.get_vehicle(vehicle.id)
        self.assertEqual(loaded.insurance, "Example Mutual")
        self.assertEqual(loaded.insurance_company, "Example Mutual")
        self.assertEqual(loaded.insurance_policy_number, "POL-24680")
        self.assertEqual(loaded.insurance_claim_number, "CLM-86420")
        self.assertEqual(loaded.insurance_adjuster_name, "Casey Adjuster")
        self.assertEqual(loaded.insurance_adjuster_phone, "503-555-0160")
        self.assertEqual(
            loaded.insurance_adjuster_email,
            "casey.adjuster@example.com",
        )
        self.assertEqual(loaded.body_style, "Four-door SUV")
        self.assertEqual(loaded.property_damage, "None")
        self.assertTrue(loaded.towed)
        self.assertEqual(loaded.tow_information, "Central Tow Yard")
        self.assertTrue(loaded.warrant_obtained)
        self.assertTrue(loaded.vehicle_inspection_completed)
        self.assertTrue(loaded.nhtsa_recalls_checked)
        self.assertTrue(loaded.cdr_equipped)
        self.assertTrue(loaded.cdr_imaged)
        self.assertTrue(loaded.cdr_report_uploaded)
        self.assertTrue(loaded.released)
        self.assertEqual(loaded.release_date, "2026-08-05")
        self.assertEqual(
            loaded.release_information,
            "Released to registered owner with receipt",
        )

        listed = self.repository.list_vehicles(self.case.id)[0]
        self.assertIsInstance(listed.cdr_equipped, bool)
        self.assertIsInstance(listed.towed, bool)
        self.assertTrue(listed.towed)
        self.assertIsInstance(listed.nhtsa_recalls_checked, bool)
        self.assertTrue(listed.nhtsa_recalls_checked)
        self.assertTrue(listed.cdr_report_uploaded)
        self.assertIsInstance(listed.released, bool)
        self.assertTrue(listed.released)

    def test_exchange_report_details_round_trip(self):
        details = self.repository.save_exchange_report_details(
            ExchangeReportDetails(
                case_id=self.case.id,
                assisting_officer="Officer Example",
                precinct="East",
            )
        )
        self.assertEqual(details.assisting_officer, "Officer Example")
        loaded = self.repository.get_exchange_report_details(self.case.id)
        self.assertEqual(loaded.assisting_officer, "Officer Example")
        self.assertEqual(loaded.precinct, "East")

    def test_schema_13_exchange_settings_migrate_to_case_officer_fields(self):
        self.repository.save_exchange_report_details(ExchangeReportDetails(
            case_id=self.case.id,
            assisting_officer="Legacy Assigned Officer",
            precinct="Legacy Traffic Assignment",
        ))
        with self.repository._connect() as connection:
            connection.execute(
                "UPDATE cases SET investigator='' WHERE id=?",
                (self.case.id,),
            )
            connection.execute("ALTER TABLE cases DROP COLUMN assigned_officer_dpsst")
            connection.execute("ALTER TABLE cases DROP COLUMN assignment")
            connection.execute("PRAGMA user_version = 13")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_case(self.case.id)
        self.assertEqual(loaded.investigator, "Legacy Assigned Officer")
        self.assertEqual(loaded.assigned_officer_dpsst, "")
        self.assertEqual(loaded.assignment, "Legacy Traffic Assignment")
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_19_video_source_status_migrates_to_axon_with_address_field(self):
        video = self.repository.save_video_source(VideoSource(
            id="",
            case_id=self.case.id,
            source="Legacy business camera",
            address="",
            axon_status="Yes",
            notes="Preserve this record",
        ))
        with self.repository._connect() as connection:
            connection.execute("ALTER TABLE video_sources DROP COLUMN address")
            connection.execute(
                "ALTER TABLE video_sources RENAME COLUMN axon_status TO dims_status"
            )
            connection.execute("PRAGMA user_version = 19")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_video_source(video.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.source, "Legacy business camera")
        self.assertEqual(loaded.address, "")
        self.assertEqual(loaded.axon_status, "Yes")
        self.assertEqual(loaded.notes, "Preserve this record")
        with closing(sqlite3.connect(self.database)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(video_sources)").fetchall()
            }
            self.assertIn("address", columns)
            self.assertIn("axon_status", columns)
            self.assertNotIn("dims_status", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_20_key_questions_field_is_removed_without_losing_case(self):
        with self.repository._connect() as connection:
            connection.execute(
                "ALTER TABLE cases ADD COLUMN key_questions TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                """
                UPDATE cases
                SET summary = ?, key_questions = ?, notes = ?
                WHERE id = ?
                """,
                (
                    "Summary retained after migration",
                    "Retired legacy content",
                    "Notes retained after migration",
                    self.case.id,
                ),
            )
            connection.execute("PRAGMA user_version = 20")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_case(self.case.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.summary, "Summary retained after migration")
        self.assertEqual(loaded.notes, "Notes retained after migration")
        self.assertFalse(hasattr(loaded, "key_questions"))
        with closing(sqlite3.connect(self.database)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(cases)").fetchall()
            }
            self.assertNotIn("key_questions", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_21_driver_profiles_receive_endorsements_without_data_loss(self):
        person = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Legacy",
            last_name="Driver",
            roles=["Driver"],
        ))
        self.repository.save_driver_profile(DriverProfile(
            person_id=person.id,
            license_number="LEGACY-DL",
            license_state="OR",
            license_class="C",
            license_status="Valid",
            license_restrictions="Corrective lenses",
        ))
        with self.repository._connect() as connection:
            connection.execute("ALTER TABLE driver_profiles DROP COLUMN endorsements")
            connection.execute("PRAGMA user_version = 21")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_driver_profile(person.id)
        self.assertEqual(loaded.license_number, "LEGACY-DL")
        self.assertEqual(loaded.license_class, "C")
        self.assertEqual(loaded.license_status, "Valid")
        self.assertEqual(loaded.license_restrictions, "Corrective lenses")
        self.assertEqual(loaded.endorsements, "")
        with closing(sqlite3.connect(self.database)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(driver_profiles)").fetchall()
            }
            self.assertIn("endorsements", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_22_vehicles_receive_nhtsa_recall_check_without_data_loss(self):
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-22",
            insurance_company="Legacy Mutual",
            vehicle_inspection_completed=True,
            notes="Preserve schema 22 vehicle",
        ))
        with self.repository._connect() as connection:
            connection.execute(
                "ALTER TABLE vehicles DROP COLUMN nhtsa_recalls_checked"
            )
            connection.execute("PRAGMA user_version = 22")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_vehicle(vehicle.id)
        self.assertEqual(loaded.insurance_company, "Legacy Mutual")
        self.assertTrue(loaded.vehicle_inspection_completed)
        self.assertEqual(loaded.notes, "Preserve schema 22 vehicle")
        self.assertIs(loaded.nhtsa_recalls_checked, False)
        with closing(sqlite3.connect(self.database)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(vehicles)").fetchall()
            }
            self.assertIn("nhtsa_recalls_checked", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_23_tow_destination_migrates_to_explicit_towed_status(self):
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-23",
            towed=True,
            tow_information="Legacy Evidence Tow Yard",
            notes="Preserve schema 23 vehicle",
        ))
        with self.repository._connect() as connection:
            connection.execute("ALTER TABLE vehicles DROP COLUMN towed")
            connection.execute("PRAGMA user_version = 23")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_vehicle(vehicle.id)
        self.assertTrue(loaded.towed)
        self.assertEqual(
            loaded.tow_information,
            "Legacy Evidence Tow Yard",
        )
        self.assertEqual(loaded.notes, "Preserve schema 23 vehicle")
        with closing(sqlite3.connect(self.database)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(vehicles)").fetchall()
            }
            self.assertIn("towed", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_24_checklist_receives_court_case_number_without_data_loss(self):
        self.repository.save_investigative_checklist(InvestigativeChecklist(
            case_id=self.case.id,
            assigned_dda="Legacy DDA",
            da_case_number="DA-24-100",
        ))
        with self.repository._connect() as connection:
            connection.execute(
                "ALTER TABLE investigative_checklists DROP COLUMN court_case_number"
            )
            connection.execute("PRAGMA user_version = 24")

        migrated = CaseRepository(self.database)
        checklist = migrated.get_investigative_checklist(self.case.id)
        self.assertEqual(checklist.assigned_dda, "Legacy DDA")
        self.assertEqual(checklist.da_case_number, "DA-24-100")
        self.assertEqual(checklist.court_case_number, "")
        checklist.court_case_number = "COURT-24-200"
        migrated.save_investigative_checklist(checklist)
        self.assertEqual(
            migrated.get_investigative_checklist(self.case.id).court_case_number,
            "COURT-24-200",
        )
        with closing(sqlite3.connect(self.database)) as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(investigative_checklists)"
                ).fetchall()
            }
            self.assertIn("court_case_number", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_17_vru_data_survives_schema_26_migrations(self):
        analysis = self.repository.save_vru_analysis(VRUAnalysis(
            id="",
            case_id=self.case.id,
            roadway_position="Legacy crosswalk",
            night_test_parameters="Legacy night data",
            prt_total="1.50",
        ))
        with self.repository._connect() as connection:
            connection.execute("ALTER TABLE vru_analyses DROP COLUMN light_meter_used")
            connection.execute("ALTER TABLE vru_analyses DROP COLUMN light_board_used")
            connection.execute("PRAGMA user_version = 17")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_vru_analysis(analysis.id)
        self.assertEqual(loaded.roadway_position, "Legacy crosswalk")
        self.assertEqual(loaded.night_test_parameters, "Legacy night data")
        self.assertEqual(loaded.prt_total, "1.50")
        self.assertIs(loaded.light_meter_used, False)
        self.assertIs(loaded.light_board_used, False)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_18_single_surface_values_migrate_to_schema_19_records(self):
        crash_details = self.repository.get_crash_details(self.case.id)
        crash_details.road_name = "Legacy Boulevard"
        self.repository.save_crash_details(crash_details)
        self.repository.save_road_conditions(RoadConditions(
            case_id=self.case.id,
            temperature="61 F",
            surface_composition="Asphalt",
            surface_condition="Wet",
            friction_value="0.48",
        ))
        existing = self.repository.save_surface_observation(SurfaceObservation(
            id="",
            case_id=self.case.id,
            location="South shoulder",
            composition="Gravel",
            condition="Dry",
            notes="Preserve existing multi-surface record",
        ))
        with self.repository._connect() as connection:
            connection.execute("PRAGMA user_version = 18")

        migrated = CaseRepository(self.database)
        surfaces = migrated.list_surface_observations(self.case.id)
        self.assertEqual(len(surfaces), 2)
        self.assertEqual(migrated.get_surface_observation(existing.id).notes, "Preserve existing multi-surface record")
        legacy_surface = next(
            surface for surface in surfaces if surface.composition == "Asphalt"
        )
        self.assertEqual(legacy_surface.location, "Legacy Boulevard")
        self.assertEqual(legacy_surface.condition, "Wet")
        self.assertEqual(legacy_surface.friction_value, "0.48")
        migrated_conditions = migrated.get_road_conditions(self.case.id)
        self.assertEqual(migrated_conditions.temperature, "61 F")
        self.assertEqual(migrated_conditions.surface_composition, "")
        self.assertEqual(migrated_conditions.surface_condition, "")
        self.assertEqual(migrated_conditions.friction_value, "")

        reopened = CaseRepository(self.database)
        self.assertEqual(len(reopened.list_surface_observations(self.case.id)), 2)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_12_data_survives_schema_26_exchange_report_migration(self):
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-12",
            notes="Preserve schema 12 vehicle",
        ))
        with self.repository._connect() as connection:
            connection.execute("DROP TABLE exchange_report_details")
            connection.execute("ALTER TABLE vehicles DROP COLUMN body_style")
            connection.execute("ALTER TABLE vehicles DROP COLUMN property_damage")
            connection.execute("PRAGMA user_version = 12")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_vehicle(vehicle.id)
        self.assertEqual(loaded.notes, "Preserve schema 12 vehicle")
        self.assertEqual(loaded.body_style, "")
        self.assertEqual(loaded.property_damage, "")
        loaded.body_style = "Pickup"
        loaded.property_damage = "Fence"
        migrated.save_vehicle(loaded)
        migrated.save_exchange_report_details(ExchangeReportDetails(
            case_id=self.case.id,
            assisting_officer="Migration Officer",
            precinct="North",
        ))
        self.assertEqual(migrated.get_vehicle(vehicle.id).body_style, "Pickup")
        self.assertEqual(
            migrated.get_exchange_report_details(self.case.id).precinct,
            "North",
        )
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_hit_run_records_round_trip_and_links_clear_safely(self):
        person = self.repository.save_person(Person(
            id="",
            case_id=self.case.id,
            first_name="Jordan",
            last_name="Lead",
            roles=["Suspect"],
        ))
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-1",
            year="2021",
            make="Example",
            model="SUV",
        ))
        overview = self.repository.save_hit_run_overview(HitRunOverview(
            case_id=self.case.id,
            is_hit_and_run=True,
            investigation_status="Vehicle Lead Developed",
            narrative="Vehicle left the scene before officers arrived.",
            last_seen_date="2026-08-01",
            direction_of_travel="Northbound",
        ))
        vehicle_lead = self.repository.save_hit_run_vehicle_lead(HitRunVehicleLead(
            id="",
            case_id=self.case.id,
            lead_number="HRV-1",
            status="Investigating",
            year_range="2020-2022",
            make="Example",
            model="SUV",
            observed_damage="Right-front damage",
            linked_vehicle_id=vehicle.id,
        ))
        evidence = self.repository.save_hit_run_evidence_item(HitRunEvidenceItem(
            id="",
            case_id=self.case.id,
            evidence_number="HRE-1",
            evidence_type="Vehicle part",
            part_number="PART-100",
            recovery_date="2026-08-02",
            vehicle_lead_id=vehicle_lead.id,
        ))
        person_lead = self.repository.save_hit_run_person_lead(HitRunPersonLead(
            id="",
            case_id=self.case.id,
            lead_number="HRP-1",
            first_name="Jordan",
            last_name="Lead",
            reason_for_lead="Registered owner",
            confidence="High",
            vehicle_lead_id=vehicle_lead.id,
            linked_person_id=person.id,
        ))

        loaded_overview = self.repository.get_hit_run_overview(self.case.id)
        self.assertIsInstance(loaded_overview.is_hit_and_run, bool)
        self.assertTrue(loaded_overview.is_hit_and_run)
        self.assertEqual(loaded_overview.last_seen_date, "2026-08-01")
        self.assertEqual(
            self.repository.get_hit_run_vehicle_lead(vehicle_lead.id).linked_vehicle_id,
            vehicle.id,
        )
        self.assertEqual(
            self.repository.get_hit_run_evidence_item(evidence.id).part_number,
            "PART-100",
        )
        self.assertEqual(
            self.repository.get_hit_run_person_lead(person_lead.id).linked_person_id,
            person.id,
        )

        self.repository.delete_vehicle(vehicle.id)
        self.repository.delete_person(person.id)
        self.assertIsNone(
            self.repository.get_hit_run_vehicle_lead(vehicle_lead.id).linked_vehicle_id
        )
        self.assertIsNone(
            self.repository.get_hit_run_person_lead(person_lead.id).linked_person_id
        )

        self.repository.delete_hit_run_vehicle_lead(vehicle_lead.id)
        self.assertIsNone(
            self.repository.get_hit_run_evidence_item(evidence.id).vehicle_lead_id
        )
        self.assertIsNone(
            self.repository.get_hit_run_person_lead(person_lead.id).vehicle_lead_id
        )

    def test_schema_11_data_survives_schema_26_migration(self):
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-LEGACY",
            notes="Preserve schema 11 vehicle",
        ))
        with self.repository._connect() as connection:
            connection.execute("DROP TABLE hit_run_evidence_items")
            connection.execute("DROP TABLE hit_run_person_leads")
            connection.execute("DROP TABLE hit_run_overviews")
            connection.execute("DROP TABLE hit_run_vehicle_leads")
            connection.execute("PRAGMA user_version = 11")

        migrated = CaseRepository(self.database)
        self.assertEqual(
            migrated.get_vehicle(vehicle.id).notes,
            "Preserve schema 11 vehicle",
        )
        migrated.save_hit_run_overview(HitRunOverview(
            case_id=self.case.id,
            is_hit_and_run=True,
        ))
        self.assertTrue(migrated.get_hit_run_overview(self.case.id).is_hit_and_run)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_person_delete_clears_vehicle_links(self):
        person = Person(id=new_id(), case_id=self.case.id, first_name="Sam", roles=["Driver"])
        self.repository.save_person(person)
        vehicle = Vehicle(
            id=new_id(), case_id=self.case.id, vehicle_number="V-1",
            driver_person_id=person.id, owner_person_id=person.id,
        )
        self.repository.save_vehicle(vehicle)
        self.repository.delete_person(person.id)
        loaded = self.repository.get_vehicle(vehicle.id)
        self.assertIsNone(loaded.driver_person_id)
        self.assertIsNone(loaded.owner_person_id)

    def test_backup_is_readable(self):
        backup = Path(self.temp.name) / "backup.sqlite3"
        self.repository.backup_to(backup)
        second_repository = CaseRepository(backup)
        self.assertEqual(second_repository.get_case(self.case.id).case_number, "26-000001")

    def test_extended_records_round_trip(self):
        person = Person(id=new_id(), case_id=self.case.id, first_name="Jamie", roles=["Driver"])
        self.repository.save_person(person)
        vehicle = Vehicle(id=new_id(), case_id=self.case.id, vehicle_number="V-1")
        self.repository.save_vehicle(vehicle)

        conditions = RoadConditions(
            case_id=self.case.id, temperature="72 F", weather_condition="Clear",
            weather_station="KPDX ASOS", weather_time="14:35 PDT",
            lighting_conditions="Daylight", speed_limit="35", chord="82.67",
            sunrise="05:59", sunset="20:31",
            civil_twilight_morning="05:27", civil_twilight_evening="21:03",
            moonrise="22:44", moonset="11:28", moon_phase="Waxing gibbous",
        )
        participant = ParticipantDetails(
            person_id=person.id, vehicle_id=vehicle.id, occupant_position="Driver",
            injury_status="Injured", transported="Yes", transported_to="Example Hospital",
            helmet="Non-Standard",
        )
        driver = DriverProfile(
            person_id=person.id, trip_from="Home", trip_to="Work",
            hours_asleep="7.5", familiar_with_road="Yes", license_state="OR",
            license_number="DL-13579", license_class="C", license_status="Valid",
            license_issued_date="2024-07-01",
            license_expiration_date="2032-07-01",
            endorsements="Passenger; Tank", license_restrictions="Restriction B",
            license_restriction_explanation="Corrective lenses",
            notes="No preventable collisions documented.",
        )
        inspection = VehicleInspection(
            vehicle_id=vehicle.id, mileage="24,300", transmission="Automatic",
            front_brakes="Serviceable", tire_contribution="No",
        )
        tires = [TireInspection(
            id=new_id(), vehicle_id=vehicle.id, position="RF", make="Example",
            size="225/45R18", pressure="34", tread_inside="7", tread_middle="7",
            tread_outside="6", condition="Serviceable",
        )]
        self.repository.save_road_conditions(conditions)
        self.repository.save_participant_details(participant)
        self.repository.save_driver_profile(driver)
        self.repository.save_vehicle_inspection(inspection)
        self.repository.replace_tires(vehicle.id, tires)

        loaded_conditions = self.repository.get_road_conditions(self.case.id)
        self.assertEqual(loaded_conditions.chord, "82.67")
        self.assertEqual(loaded_conditions.weather_station, "KPDX ASOS")
        self.assertEqual(loaded_conditions.weather_time, "14:35 PDT")
        self.assertEqual(loaded_conditions.sunrise, "05:59")
        self.assertEqual(loaded_conditions.sunset, "20:31")
        self.assertEqual(loaded_conditions.civil_twilight_morning, "05:27")
        self.assertEqual(loaded_conditions.civil_twilight_evening, "21:03")
        self.assertEqual(loaded_conditions.moonrise, "22:44")
        self.assertEqual(loaded_conditions.moonset, "11:28")
        self.assertEqual(loaded_conditions.moon_phase, "Waxing gibbous")
        self.assertEqual(self.repository.get_participant_details(person.id).transported_to, "Example Hospital")
        self.assertEqual(
            self.repository.get_participant_details(person.id).helmet,
            "Non-Standard",
        )
        self.assertEqual(self.repository.get_driver_profile(person.id).hours_asleep, "7.5")
        self.assertEqual(
            self.repository.get_driver_profile(person.id).endorsements,
            "Passenger; Tank",
        )
        loaded_driver = self.repository.get_driver_profile(person.id)
        self.assertEqual(loaded_driver.license_number, "DL-13579")
        self.assertEqual(loaded_driver.license_issued_date, "2024-07-01")
        self.assertEqual(loaded_driver.license_expiration_date, "2032-07-01")
        self.assertEqual(loaded_driver.license_restrictions, "Restriction B")
        self.assertEqual(loaded_driver.notes, "No preventable collisions documented.")
        self.assertEqual(self.repository.get_vehicle_inspection(vehicle.id).mileage, "24,300")
        self.assertEqual(self.repository.list_tires(vehicle.id)[0].position, "RF")
        self.assertEqual(self.repository.case_counts(self.case.id)["injured"], 1)

    def test_existing_database_receives_additive_schema(self):
        with self.repository._connect() as connection:
            connection.execute("DROP TABLE diagram_records")
            connection.execute("DROP TABLE file_references")
            connection.execute("DROP TABLE vru_analyses")
            connection.execute("DROP TABLE contact_relationships")
            connection.execute("DROP TABLE witness_details")
            connection.execute("DROP TABLE road_conditions")
            connection.execute("DROP TABLE participant_details")
            connection.execute("DROP TABLE driver_profiles")
            connection.execute("DROP TABLE tire_inspections")
            connection.execute("DROP TABLE vehicle_inspections")
            connection.execute("PRAGMA user_version = 2")
        reopened = CaseRepository(self.database)
        reopened.save_road_conditions(RoadConditions(case_id=self.case.id, temperature="60 F"))
        self.assertEqual(reopened.get_road_conditions(self.case.id).temperature, "60 F")
        self.assertEqual(reopened.get_witness_details("missing").interviewed, "Unknown")

    def test_schema_25_vehicle_receives_insurance_claim_fields(self):
        vehicle = self.repository.save_vehicle(Vehicle(
            id="",
            case_id=self.case.id,
            vehicle_number="V-25",
            insurance_company="Existing Insurance",
            insurance_policy_number="EXISTING-POLICY",
            notes="Preserve the existing vehicle",
        ))
        with closing(sqlite3.connect(self.database)) as connection:
            for column in (
                "insurance_claim_number",
                "insurance_adjuster_name",
                "insurance_adjuster_phone",
                "insurance_adjuster_email",
            ):
                connection.execute(f"ALTER TABLE vehicles DROP COLUMN {column}")
            connection.execute("PRAGMA user_version = 25")

        migrated = CaseRepository(self.database)
        loaded = migrated.get_vehicle(vehicle.id)
        self.assertEqual(loaded.insurance_company, "Existing Insurance")
        self.assertEqual(loaded.insurance_policy_number, "EXISTING-POLICY")
        self.assertEqual(loaded.notes, "Preserve the existing vehicle")
        self.assertEqual(loaded.insurance_claim_number, "")
        self.assertEqual(loaded.insurance_adjuster_name, "")
        self.assertEqual(loaded.insurance_adjuster_phone, "")
        self.assertEqual(loaded.insurance_adjuster_email, "")

        loaded.insurance_claim_number = "MIGRATED-CLAIM"
        loaded.insurance_adjuster_name = "Morgan Adjuster"
        loaded.insurance_adjuster_phone = "503-555-0188"
        loaded.insurance_adjuster_email = "morgan.adjuster@example.com"
        migrated.save_vehicle(loaded)
        reloaded = migrated.get_vehicle(vehicle.id)
        self.assertEqual(reloaded.insurance_claim_number, "MIGRATED-CLAIM")
        self.assertEqual(reloaded.insurance_adjuster_name, "Morgan Adjuster")
        self.assertEqual(reloaded.insurance_adjuster_phone, "503-555-0188")
        self.assertEqual(
            reloaded.insurance_adjuster_email,
            "morgan.adjuster@example.com",
        )
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_10_vehicle_data_survives_schema_26_migration(self):
        legacy_database = Path(self.temp.name) / "legacy-vehicle.sqlite3"
        with closing(sqlite3.connect(legacy_database)) as connection:
            connection.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE cases (
                    id TEXT PRIMARY KEY, case_number TEXT NOT NULL DEFAULT '',
                    crash_date TEXT NOT NULL DEFAULT '', crash_time TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '', investigator TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Active', summary TEXT NOT NULL DEFAULT '',
                    key_questions TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE vehicles (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    vehicle_number TEXT NOT NULL DEFAULT '', year TEXT NOT NULL DEFAULT '',
                    make TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '', vin TEXT NOT NULL DEFAULT '',
                    plate TEXT NOT NULL DEFAULT '', plate_state TEXT NOT NULL DEFAULT '',
                    owner_person_id TEXT, driver_person_id TEXT,
                    insurance TEXT NOT NULL DEFAULT '', tow_information TEXT NOT NULL DEFAULT '',
                    edr_status TEXT NOT NULL DEFAULT '', damage_notes TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO cases VALUES (
                    'legacy-case', 'LEGACY-VEHICLE', '', '', '', 'Legacy Investigator',
                    'Active', '', '', '', '2025-01-01', '2025-01-01'
                );
                INSERT INTO vehicles VALUES (
                    'legacy-vehicle', 'legacy-case', 'V-1', '2020', 'Example', 'Sedan',
                    '', '', '', '', NULL, NULL, 'Legacy Insurance Text', '',
                    'Downloaded', '', 'Preserve vehicle notes', '2025-01-01', '2025-01-01'
                );
                PRAGMA user_version = 10;
            """)

        migrated = CaseRepository(legacy_database)
        vehicle = migrated.get_vehicle("legacy-vehicle")
        self.assertEqual(vehicle.insurance, "Legacy Insurance Text")
        self.assertEqual(vehicle.insurance_company, "Legacy Insurance Text")
        self.assertEqual(vehicle.insurance_policy_number, "")
        self.assertEqual(vehicle.edr_status, "Downloaded")
        self.assertEqual(vehicle.notes, "Preserve vehicle notes")
        self.assertFalse(vehicle.towed)
        self.assertFalse(vehicle.warrant_obtained)
        self.assertFalse(vehicle.vehicle_inspection_completed)
        self.assertFalse(vehicle.cdr_equipped)
        self.assertFalse(vehicle.cdr_imaged)
        self.assertFalse(vehicle.cdr_report_uploaded)
        self.assertFalse(vehicle.released)
        self.assertEqual(vehicle.release_date, "")
        self.assertEqual(vehicle.release_information, "")

        vehicle.insurance_company = "Migrated Insurance Co."
        vehicle.insurance_policy_number = "MIGRATED-123"
        vehicle.cdr_imaged = True
        migrated.save_vehicle(vehicle)
        reloaded = migrated.get_vehicle(vehicle.id)
        self.assertEqual(reloaded.insurance_company, "Migrated Insurance Co.")
        self.assertEqual(reloaded.insurance_policy_number, "MIGRATED-123")
        self.assertTrue(reloaded.cdr_imaged)
        with closing(sqlite3.connect(legacy_database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_3_person_data_survives_schema_26_column_migration(self):
        legacy_database = Path(self.temp.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_database)) as connection:
            connection.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE cases (
                    id TEXT PRIMARY KEY, case_number TEXT NOT NULL DEFAULT '',
                    crash_date TEXT NOT NULL DEFAULT '', crash_time TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '', investigator TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Active', summary TEXT NOT NULL DEFAULT '',
                    key_questions TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE people (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    first_name TEXT NOT NULL DEFAULT '', middle_name TEXT NOT NULL DEFAULT '',
                    last_name TEXT NOT NULL DEFAULT '', dob TEXT NOT NULL DEFAULT '',
                    sex TEXT NOT NULL DEFAULT '', race TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                INSERT INTO cases VALUES (
                    'legacy-case', 'LEGACY-1', '', '', 'Legacy Road', 'Legacy Investigator',
                    'Active', '', '', '', '2025-01-01', '2025-01-01'
                );
                INSERT INTO people VALUES (
                    'legacy-person', 'legacy-case', 'Legacy', '', 'Person', '', '', '',
                    '503-555-0100', '', 'Old Address', 'Preserve me',
                    '2025-01-01', '2025-01-01'
                );
                PRAGMA user_version = 3;
            """)

        migrated = CaseRepository(legacy_database)
        person = migrated.get_person("legacy-person")
        self.assertEqual(person.display_name, "Legacy Person")
        self.assertEqual(person.phone, "503-555-0100")
        self.assertEqual(person.cell_phone, "")
        self.assertEqual(person.address, "Old Address")
        self.assertEqual(person.zip_code, "")
        person.cell_phone = "503-555-0101"
        person.zip_code = "97201-1234"
        migrated.save_person(person)
        self.assertEqual(migrated.get_person(person.id).cell_phone, "503-555-0101")
        self.assertEqual(migrated.get_person(person.id).zip_code, "97201-1234")
        with closing(sqlite3.connect(legacy_database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_9_participant_receives_extracted_without_data_loss(self):
        legacy_database = Path(self.temp.name) / "legacy-participant.sqlite3"
        legacy_repository = CaseRepository(legacy_database)
        legacy_case = legacy_repository.create_case(
            "LEGACY-PARTICIPANT", "Legacy Investigator"
        )
        person = legacy_repository.save_person(Person(
            id="", case_id=legacy_case.id, first_name="Legacy", last_name="Participant",
        ))
        legacy_repository.save_participant_details(ParticipantDetails(
            person_id=person.id,
            injury_status="Injured",
            ejected="Yes",
            notes="Preserve participant details",
        ))
        with closing(sqlite3.connect(legacy_database)) as connection:
            connection.execute("ALTER TABLE participant_details DROP COLUMN extracted")
            connection.execute("PRAGMA user_version = 9")

        migrated = CaseRepository(legacy_database)
        details = migrated.get_participant_details(person.id)
        self.assertEqual(details.injury_status, "Injured")
        self.assertEqual(details.ejected, "Yes")
        self.assertEqual(details.extracted, "Unknown")
        self.assertEqual(details.notes, "Preserve participant details")
        details.extracted = "Yes"
        migrated.save_participant_details(details)
        self.assertEqual(
            migrated.get_participant_details(person.id).extracted,
            "Yes",
        )
        with closing(sqlite3.connect(legacy_database)) as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(participant_details)"
                ).fetchall()
            }
            self.assertIn("extracted", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_5_checklist_receives_review_date_columns_without_data_loss(self):
        legacy_database = Path(self.temp.name) / "legacy-checklist.sqlite3"
        with closing(sqlite3.connect(legacy_database)) as connection:
            connection.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE cases (
                    id TEXT PRIMARY KEY, case_number TEXT NOT NULL DEFAULT '',
                    crash_date TEXT NOT NULL DEFAULT '', crash_time TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '', investigator TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Active', summary TEXT NOT NULL DEFAULT '',
                    key_questions TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE investigative_checklists (
                    case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
                    completed_items_json TEXT NOT NULL DEFAULT '[]',
                    submitted_to_da_date TEXT NOT NULL DEFAULT '',
                    assigned_dda TEXT NOT NULL DEFAULT '',
                    da_case_number TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                INSERT INTO cases VALUES (
                    'legacy-case', 'LEGACY-CHECKLIST', '', '', '', 'Legacy Investigator',
                    'Active', '', '', '', '2025-01-01', '2025-01-01'
                );
                INSERT INTO investigative_checklists VALUES (
                    'legacy-case', '["DIMS CD Ordered"]', '2025-01-15',
                    'Legacy DDA', 'DA-LEGACY', '2025-01-15'
                );
                PRAGMA user_version = 5;
            """)

        migrated = CaseRepository(legacy_database)
        checklist = migrated.get_investigative_checklist("legacy-case")
        self.assertEqual(checklist.completed_items, ["DIMS CD Ordered"])
        self.assertNotIn("Axon Shared to DA", checklist.completed_items)
        self.assertEqual(checklist.submitted_to_da_date, "2025-01-15")
        self.assertEqual(checklist.peer_review_date, "")
        self.assertEqual(checklist.sergeant_review_date, "")
        self.assertEqual(checklist.court_case_number, "")
        with closing(sqlite3.connect(legacy_database)) as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(investigative_checklists)"
                ).fetchall()
            }
            self.assertIn("peer_review_date", columns)
            self.assertIn("sergeant_review_date", columns)
            self.assertIn("court_case_number", columns)
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_6_conditions_receive_celestial_and_station_columns_without_data_loss(self):
        legacy_database = Path(self.temp.name) / "legacy-conditions.sqlite3"
        legacy_repository = CaseRepository(legacy_database)
        legacy_case = legacy_repository.create_case("LEGACY-CONDITIONS", "Legacy Investigator")
        legacy_repository.save_road_conditions(RoadConditions(
            case_id=legacy_case.id,
            temperature="61 F",
            weather_time="06:42",
            sunrise="07:10",
        ))
        new_columns = (
            "weather_station",
            "civil_twilight_morning",
            "civil_twilight_evening",
            "moonrise",
            "moonset",
            "moon_phase",
        )
        with closing(sqlite3.connect(legacy_database)) as connection:
            for column in new_columns:
                connection.execute(f"ALTER TABLE road_conditions DROP COLUMN {column}")
            connection.execute("PRAGMA user_version = 6")

        migrated = CaseRepository(legacy_database)
        conditions = migrated.get_road_conditions(legacy_case.id)
        self.assertEqual(conditions.temperature, "61 F")
        self.assertEqual(conditions.weather_time, "06:42")
        self.assertEqual(conditions.sunrise, "07:10")
        self.assertEqual(conditions.weather_station, "")
        self.assertEqual(conditions.moon_phase, "")

        conditions.weather_station = "KLEG"
        conditions.civil_twilight_morning = "06:38"
        conditions.civil_twilight_evening = "17:42"
        conditions.moonrise = "19:15"
        conditions.moonset = "08:22"
        conditions.moon_phase = "Full"
        migrated.save_road_conditions(conditions)
        reloaded = migrated.get_road_conditions(legacy_case.id)
        self.assertEqual(reloaded.weather_station, "KLEG")
        self.assertEqual(reloaded.civil_twilight_morning, "06:38")
        self.assertEqual(reloaded.civil_twilight_evening, "17:42")
        self.assertEqual(reloaded.moonrise, "19:15")
        self.assertEqual(reloaded.moonset, "08:22")
        self.assertEqual(reloaded.moon_phase, "Full")
        with closing(sqlite3.connect(legacy_database)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(road_conditions)").fetchall()
            }
            self.assertTrue(set(new_columns).issubset(columns))
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

    def test_schema_7_single_roadway_is_migrated_once_without_data_loss(self):
        legacy_database = Path(self.temp.name) / "legacy-roadway.sqlite3"
        legacy_repository = CaseRepository(legacy_database)
        legacy_case = legacy_repository.create_case(
            "LEGACY-ROADWAY",
            "Legacy Investigator",
        )
        crash_details = legacy_repository.get_crash_details(legacy_case.id)
        crash_details.road_name = "Legacy Boulevard"
        legacy_repository.save_crash_details(crash_details)
        legacy_repository.save_road_conditions(RoadConditions(
            case_id=legacy_case.id,
            speed_limit="45",
            speed_limit_posted="Yes",
            speed_limit_location="West approach sign",
            curve_radius="510",
            chord="120",
            middle_ordinate="7.1",
            critical_speed="38",
            roadway_characteristics="Two travel lanes with a 2 percent grade",
            traffic_controls="Flashing beacon",
        ))
        with closing(sqlite3.connect(legacy_database)) as connection:
            connection.execute("DROP TABLE roadway_records")
            connection.execute("PRAGMA user_version = 7")

        migrated = CaseRepository(legacy_database)
        roadways = migrated.list_roadway_records(legacy_case.id)
        self.assertEqual(len(roadways), 1)
        roadway = roadways[0]
        self.assertEqual(roadway.roadway_tag, "Legacy Boulevard")
        self.assertEqual(roadway.speed_limit, "45")
        self.assertEqual(roadway.speed_limit_posted, "Yes")
        self.assertEqual(roadway.speed_limit_location, "West approach sign")
        self.assertEqual(roadway.curve_radius, "510")
        self.assertEqual(roadway.chord, "120")
        self.assertEqual(roadway.middle_ordinate, "7.1")
        self.assertEqual(roadway.critical_speed, "38")
        self.assertIn("2 percent grade", roadway.roadway_characteristics)
        self.assertEqual(roadway.traffic_controls, "Flashing beacon")
        self.assertEqual(
            migrated.get_road_conditions(legacy_case.id).speed_limit,
            "45",
        )
        with closing(sqlite3.connect(legacy_database)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )

        reopened = CaseRepository(legacy_database)
        self.assertEqual(len(reopened.list_roadway_records(legacy_case.id)), 1)

    def test_multiple_tagged_roadway_records_round_trip(self):
        first = self.repository.save_roadway_record(RoadwayRecord(
            id="",
            case_id=self.case.id,
            roadway_tag="North Main Street - northbound",
            speed_limit="35",
            speed_limit_posted="Yes",
            speed_limit_location="South approach sign",
            roadway_characteristics="Two northbound lanes",
            traffic_controls="Traffic signal",
        ))
        second = self.repository.save_roadway_record(RoadwayRecord(
            id="",
            case_id=self.case.id,
            roadway_tag="Cross Avenue - eastbound",
            speed_limit="25",
            speed_limit_posted="No",
            curve_radius="420",
            critical_speed="31",
            roadway_characteristics="Single eastbound lane",
            traffic_controls="Marked stop line",
        ))

        records = {
            record.roadway_tag: record
            for record in self.repository.list_roadway_records(self.case.id)
        }
        self.assertEqual(len(records), 2)
        self.assertEqual(records[first.roadway_tag].speed_limit, "35")
        self.assertEqual(records[second.roadway_tag].curve_radius, "420")

        first.speed_limit = "30"
        self.repository.save_roadway_record(first)
        self.assertEqual(self.repository.get_roadway_record(first.id).speed_limit, "30")
        self.repository.delete_roadway_record(second.id)
        self.assertEqual(
            [record.roadway_tag for record in self.repository.list_roadway_records(self.case.id)],
            ["North Main Street - northbound"],
        )

    def test_investigation_records_round_trip(self):
        person = Person(id=new_id(), case_id=self.case.id, first_name="Avery", roles=["Witness"])
        self.repository.save_person(person)
        vehicle = Vehicle(id=new_id(), case_id=self.case.id, vehicle_number="V-1")
        self.repository.save_vehicle(vehicle)
        self.repository.save_witness_details(WitnessDetails(
            person_id=person.id, interviewed="Yes", statement_summary="Observed the signal phase.",
        ))
        contact = self.repository.save_contact(ContactRelationship(
            id="", case_id=self.case.id, contact_type="Family / Contact", contact_name="Casey",
            subject_person_id=person.id, vehicle_id=vehicle.id, phone="503-555-0100",
        ))
        analysis = self.repository.save_vru_analysis(VRUAnalysis(
            id="", case_id=self.case.id, person_id=person.id, vehicle_id=vehicle.id,
            roadway_position="Marked crosswalk", light_meter_used=True,
            light_board_used=True, prt_total="1.50",
        ))
        reference = self.repository.save_file_reference(FileReference(
            id="", case_id=self.case.id, category="Video", title="Intersection camera",
            person_id=person.id, file_path="C:/Case/Video.mp4",
        ))
        diagram = self.repository.save_diagram(DiagramRecord(
            id="", case_id=self.case.id, title="Body injury diagram", person_id=person.id,
            annotations_json='[{"type":"text","position":[40,40],"text":"A"}]',
        ))

        self.assertEqual(self.repository.get_witness_details(person.id).statement_summary, "Observed the signal phase.")
        self.assertEqual(self.repository.get_contact(contact.id).phone, "503-555-0100")
        self.assertIsNone(self.repository.get_contact(contact.id).vehicle_id)
        loaded_analysis = self.repository.get_vru_analysis(analysis.id)
        self.assertEqual(loaded_analysis.prt_total, "1.50")
        self.assertIs(loaded_analysis.light_meter_used, True)
        self.assertIs(loaded_analysis.light_board_used, True)
        listed_analysis = self.repository.list_vru_analyses(self.case.id)[0]
        self.assertIsInstance(listed_analysis.light_meter_used, bool)
        self.assertTrue(listed_analysis.light_board_used)
        self.assertEqual(self.repository.get_file_reference(reference.id).title, "Intersection camera")
        self.assertEqual(self.repository.get_diagram(diagram.id).template_name, "body")

        with self.assertRaisesRegex(ValueError, "assigned to a person"):
            self.repository.save_contact(ContactRelationship(
                id="", case_id=self.case.id, contact_name="Unassigned contact",
            ))

    def test_packet_case_records_round_trip(self):
        checklist = self.repository.save_investigative_checklist(InvestigativeChecklist(
            case_id=self.case.id,
            completed_items=[
                "Participant Interviews",
                "Weather Obtained",
                "Axon Shared to DA",
                "Report Peer Reviewed",
                "Submitted to DA",
            ],
            peer_review_status="Complete",
            sergeant_review_status="Pending",
            submitted_to_da_status="Complete",
            peer_review_date="2026-08-02",
            submitted_to_da_date="2026-08-04",
            assigned_dda="Example DDA",
            da_case_number="DA-123",
            court_case_number="COURT-456",
        ))
        charge = self.repository.save_charge_disposition(ChargeDisposition(
            id="", case_id=self.case.id, charge="Reckless driving", disposition="Pending",
        ))
        details = self.repository.save_crash_details(CrashDetails(
            case_id=self.case.id,
            nearest_city="Portland",
            county="Multnomah",
            road_name="North Example Street",
            intersection_road="Example Avenue",
            latitude="45.5152",
            longitude="-122.6784",
            scene_evidence=["Crime Scene Log", "FARO"],
        ))
        video = self.repository.save_video_source(VideoSource(
            id="", case_id=self.case.id, source="Intersection camera",
            address="100 Example Avenue, Portland, OR 97201",
            axon_status="Yes", notes="Requested from owner",
        ))

        loaded_checklist = self.repository.get_investigative_checklist(self.case.id)
        self.assertEqual(loaded_checklist.completed_items, checklist.completed_items)
        self.assertEqual(loaded_checklist.peer_review_date, "2026-08-02")
        self.assertEqual(loaded_checklist.peer_review_status, "Complete")
        self.assertEqual(loaded_checklist.sergeant_review_status, "Pending")
        self.assertEqual(loaded_checklist.submitted_to_da_status, "Complete")
        self.assertEqual(loaded_checklist.sergeant_review_date, "")
        self.assertEqual(loaded_checklist.submitted_to_da_date, "2026-08-04")
        self.assertEqual(loaded_checklist.da_case_number, "DA-123")
        self.assertEqual(loaded_checklist.court_case_number, "COURT-456")
        self.assertEqual(
            self.repository.get_charge_disposition(charge.id).disposition, "Pending"
        )
        loaded_details = self.repository.get_crash_details(self.case.id)
        self.assertEqual(loaded_details.scene_evidence, details.scene_evidence)
        self.assertEqual(loaded_details.intersection_road, "Example Avenue")
        loaded_video = self.repository.get_video_source(video.id)
        self.assertEqual(loaded_video.address, "100 Example Avenue, Portland, OR 97201")
        self.assertEqual(loaded_video.axon_status, "Yes")

    def test_packet_expansion_records_round_trip(self):
        person = self.repository.save_person(Person(
            id="", case_id=self.case.id, first_name="Robin", last_name="Example",
            roles=["Driver", "Witness"], cell_phone="503-555-0101",
            home_phone="503-555-0102", work_phone="503-555-0103",
            address="200 Example Street", city="Portland", state="OR",
            zip_code="97201", occupation="Mechanic",
            business_address="100 Example Avenue",
        ))
        participant = self.repository.save_participant_details(ParticipantDetails(
            person_id=person.id, height="70 in", weight="180 lb", hospital="OHSU",
            helmet="No", ejected="No", extracted="Yes",
            injury_codes="1 - Laceration; 3 - Contusion",
            evidence_items="Blood; Clothing",
        ))
        profile = self.repository.save_driver_profile(DriverProfile(
            person_id=person.id,
            physical_condition_types="Diabetes; Vision",
            testing_methods="SFST; BAC - Blood",
            license_restricted="Yes",
            license_restriction_explanation="Corrective lenses",
            endorsements="Passenger; Tank",
        ))
        contact = self.repository.save_contact(ContactRelationship(
            id="", case_id=self.case.id, contact_name="Morgan Example",
            subject_person_id=person.id,
            cell_phone="503-555-0110", home_phone="503-555-0111",
            work_phone="503-555-0112", city="Gresham", state="OR",
        ))
        surface = self.repository.save_surface_observation(SurfaceObservation(
            id="", case_id=self.case.id, location="Northbound lane",
            composition="Asphalt", condition="Wet", friction_value="0.48",
        ))
        vehicle = self.repository.save_vehicle(Vehicle(
            id="", case_id=self.case.id, vehicle_number="V-1", make="Example",
            model="Motorcycle",
        ))
        inspection = self.repository.save_vehicle_inspection(VehicleInspection(
            vehicle_id=vehicle.id, headlights_equipped="Yes", headlights_operable="No",
            ignition_position="On", device_observations="Mounted GPS illuminated",
            tire_contribution="Yes", tire_contribution_explanation="RF tread separation",
        ))
        motorcycle = self.repository.save_motorcycle_inspection(MotorcycleInspection(
            vehicle_id=vehicle.id, frame_number="FRAME-1", inspection_date="2026-08-04",
            officer="Test Officer", dpsst="12345",
            items=[
                MotorcycleInspectionItem(
                    item_number=8, rating="2 - Damaged", measurement="20 psi",
                    comments="Below manufacturer specification",
                ),
                MotorcycleInspectionItem(item_number=44, rating="1 - Not damaged"),
            ],
        ))

        loaded_person = self.repository.get_person(person.id)
        self.assertEqual(loaded_person.cell_phone, "503-555-0101")
        self.assertEqual(loaded_person.zip_code, "97201")
        self.assertEqual(loaded_person.occupation, "Mechanic")
        self.assertEqual(
            self.repository.get_participant_details(person.id).injury_codes,
            participant.injury_codes,
        )
        self.assertEqual(
            self.repository.get_participant_details(person.id).extracted,
            "Yes",
        )
        self.assertEqual(
            self.repository.get_participant_details(person.id).helmet,
            "No",
        )
        self.assertEqual(
            self.repository.get_driver_profile(person.id).license_restriction_explanation,
            profile.license_restriction_explanation,
        )
        self.assertEqual(
            self.repository.get_driver_profile(person.id).endorsements,
            profile.endorsements,
        )
        self.assertEqual(self.repository.get_contact(contact.id).work_phone, "503-555-0112")
        self.assertEqual(self.repository.get_surface_observation(surface.id).friction_value, "0.48")
        self.assertEqual(
            self.repository.get_vehicle_inspection(vehicle.id).headlights_operable,
            inspection.headlights_operable,
        )
        loaded_motorcycle = self.repository.get_motorcycle_inspection(vehicle.id)
        self.assertEqual(loaded_motorcycle.frame_number, motorcycle.frame_number)
        self.assertEqual(len(loaded_motorcycle.items), 2)
        self.assertEqual(loaded_motorcycle.items[0].measurement, "20 psi")


if __name__ == "__main__":
    unittest.main()
