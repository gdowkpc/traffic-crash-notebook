from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from traffic_crash_notebook.models import (
    CaseTask,
    ChargeDisposition,
    ChronologyEntry,
    ContactRelationship,
    DiagramRecord,
    DriverProfile,
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
    RoadConditions,
    CrashDetails,
    RoadwayRecord,
    SurfaceObservation,
    TireInspection,
    Vehicle,
    VehicleInspection,
    VideoSource,
    VRUAnalysis,
    WitnessDetails,
    format_weather_measurement,
    scene_evidence_for_output,
)
from traffic_crash_notebook.pdf_export import (
    export_case_compact_pdf,
    export_case_pdf,
    export_case_summary_pdf,
)
from traffic_crash_notebook.repository import CaseRepository, new_id


class PdfExportTest(unittest.TestCase):
    def test_weather_measurements_add_units_once_and_preserve_descriptions(self):
        self.assertEqual(format_weather_measurement("temperature", "71"), "71 F")
        self.assertEqual(format_weather_measurement("temperature", "71 F"), "71 F")
        self.assertEqual(format_weather_measurement("dew_point", "54"), "54 F")
        self.assertEqual(format_weather_measurement("dew_point", "54 F"), "54 F")
        self.assertEqual(format_weather_measurement("winds", "NW 6"), "NW 6 mph")
        self.assertEqual(format_weather_measurement("winds", "Calm"), "Calm")
        self.assertEqual(format_weather_measurement("humidity", "43"), "43%")
        self.assertEqual(format_weather_measurement("humidity", "43%"), "43%")
        self.assertEqual(format_weather_measurement("pressure", "29.92"), "29.92 inHg")
        self.assertEqual(format_weather_measurement("pressure", "1013 hPa"), "1013 hPa")
        self.assertEqual(format_weather_measurement("precipitation", "0.04"), "0.04 in")
        self.assertEqual(format_weather_measurement("precipitation", "Trace"), "Trace")

    def test_scene_evidence_filters_retired_values_and_derives_surveillance_video(self):
        selected = [
            "Crime Scene Log",
            "Video Taken",
            "Surveillance Video",
            "PED",
            "Trimble",
            "DIMS",
            "Investigator Photos",
            "Uploaded to Axon",
            "FARO",
        ]
        self.assertEqual(
            scene_evidence_for_output(selected, has_video_sources=False),
            ["Investigator Photos", "Uploaded to Axon", "Axon", "FARO"],
        )
        self.assertEqual(
            scene_evidence_for_output(selected, has_video_sources=True),
            [
                "Investigator Photos",
                "Uploaded to Axon",
                "Axon",
                "FARO",
                "Surveillance Video",
            ],
        )
        self.assertEqual(
            scene_evidence_for_output(
                ["Uploaded to Axon"],
                has_video_sources=False,
            ),
            [],
        )

    def test_working_packet_preserves_blank_sections_while_compact_omits_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = CaseRepository(root / "empty.sqlite3")
            case = repository.create_case("26-EMPTY", "Print Mode Test")

            working_reader = PdfReader(
                export_case_pdf(repository, case.id, root / "working.pdf")
            )
            compact_reader = PdfReader(
                export_case_compact_pdf(repository, case.id, root / "compact.pdf")
            )
            working_text = "\n".join(page.extract_text() or "" for page in working_reader.pages)
            compact_text = "\n".join(page.extract_text() or "" for page in compact_reader.pages)

            for reader, mode in (
                (working_reader, "FULL WORKING PACKET"),
                (compact_reader, "COMPACT COMPLETED-CASE PACKET"),
            ):
                cover_text = reader.pages[0].extract_text() or ""
                second_page_text = reader.pages[1].extract_text() or ""
                self.assertIn("TRAFFIC CRASH INVESTIGATION PACKET", cover_text)
                self.assertIn("CASE 26-EMPTY", cover_text)
                self.assertIn(mode, cover_text)
                self.assertIn("ASSIGNED INVESTIGATOR", cover_text)
                self.assertIn("DPSST", cover_text)
                self.assertIn("ASSIGNMENT", cover_text)
                self.assertIn("PEER REVIEW", cover_text)
                self.assertIn("MCT SERGEANT REVIEW", cover_text)
                self.assertIn("SUBMITTED TO DA", cover_text)
                self.assertNotIn("Key questions", cover_text)
                self.assertNotIn("unresolved issues", cover_text.lower())
                self.assertNotIn("Investigative packet", cover_text)
                self.assertIn("Investigative packet", second_page_text)

            self.assertGreater(len(working_reader.pages), len(compact_reader.pages))
            self.assertIn("FULL WORKING PACKET", working_text)
            self.assertIn("Participant and driver details", working_text)
            self.assertIn("Witness interviews and contacts", working_text)
            self.assertIn("Vulnerable road user analysis", working_text)
            self.assertIn("Investigative journal", working_text)
            self.assertIn("No journal entries.", working_text)
            self.assertNotIn("Investigative chronology", working_text)
            self.assertNotIn("Handwritten sketch / diagram continuation", working_text)
            self.assertIn("GENERAL HANDWRITTEN CONTINUATION", working_text)
            self.assertIn("COMPACT COMPLETED-CASE PACKET", compact_text)
            self.assertNotIn("Participant and driver details", compact_text)
            self.assertNotIn("Witness interviews and contacts", compact_text)
            self.assertNotIn("GENERAL HANDWRITTEN CONTINUATION", compact_text)
            self.assertNotIn("Hit & Run Investigation", working_text)
            self.assertNotIn("Hit & Run Investigation", compact_text)

    def test_hit_run_section_is_conditional_complete_and_has_working_space(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = CaseRepository(root / "hit-run.sqlite3")
            case = repository.create_case("26-HITRUN", "Hit Run Test")
            person = repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Morgan",
                last_name="Confirmed",
                roles=["Suspect"],
            ))
            vehicle = repository.save_vehicle(Vehicle(
                id="",
                case_id=case.id,
                vehicle_number="V-1",
                year="2021",
                make="Example",
                model="SUV",
            ))
            repository.save_hit_run_overview(HitRunOverview(
                case_id=case.id,
                is_hit_and_run=True,
                investigation_status="Vehicle Lead Developed",
                narrative="The possible vehicle left the collision scene.",
                last_known_location="Example Street at First Avenue",
                last_seen_date="2026-08-04",
                last_seen_time="21:15",
                direction_of_travel="Northbound",
                initial_source="Surveillance video",
                follow_up_notes="Complete the neighborhood canvass.",
            ))
            vehicle_lead = repository.save_hit_run_vehicle_lead(HitRunVehicleLead(
                id="",
                case_id=case.id,
                lead_number="HRV-1",
                status="Investigating",
                confidence="High",
                year_range="2020-2022",
                make="Example",
                model="SUV",
                body_style="Four-door SUV",
                color="Dark blue",
                plate="ABC123",
                plate_state="OR",
                distinguishing_features="Roof rack and rear decal",
                observed_damage="Right-front damage",
                missing_parts="Passenger mirror cover",
                last_seen_date="2026-08-04",
                information_source="Surveillance video",
                linked_vehicle_id=vehicle.id,
            ))
            repository.save_hit_run_evidence_item(HitRunEvidenceItem(
                id="",
                case_id=case.id,
                evidence_number="HRE-1",
                evidence_type="Recovered vehicle part",
                part_number="PART-321",
                part_description="Mirror cover fragment",
                manufacturer_markings="EXAMPLE MARK",
                recovery_location="East shoulder",
                recovery_date="2026-08-05",
                lab_status="Comparison pending",
                vehicle_lead_id=vehicle_lead.id,
            ))
            repository.save_hit_run_person_lead(HitRunPersonLead(
                id="",
                case_id=case.id,
                lead_number="HRP-1",
                status="Investigating",
                first_name="Morgan",
                last_name="Possible",
                alias="Mo",
                reason_for_lead="Registered owner of possible vehicle",
                information_source="DMV records",
                vehicle_lead_id=vehicle_lead.id,
                linked_person_id=person.id,
            ))

            working = PdfReader(export_case_pdf(repository, case.id, root / "working.pdf"))
            compact = PdfReader(
                export_case_compact_pdf(repository, case.id, root / "compact.pdf")
            )
            summary = PdfReader(
                export_case_summary_pdf(repository, case.id, root / "summary.pdf")
            )
            working_text = "\n".join(page.extract_text() or "" for page in working.pages)
            compact_text = "\n".join(page.extract_text() or "" for page in compact.pages)
            summary_text = "\n".join(page.extract_text() or "" for page in summary.pages)

            for text in (working_text, compact_text, summary_text):
                self.assertIn("Hit & Run Investigation", text)
                self.assertIn("HRV-1", text)
                self.assertIn("HRE-1", text)
                self.assertIn("PART-321", text)
                self.assertIn("HRP-1", text)
                self.assertIn("Morgan Possible (aka Mo)", text)
                self.assertIn("08/04/2026", text)
                self.assertIn("08/05/2026", text)
            self.assertIn(
                "HIT-AND-RUN ADDITIONS / LEAD DEVELOPMENT",
                working_text,
            )
            self.assertNotIn(
                "HIT-AND-RUN ADDITIONS / LEAD DEVELOPMENT",
                compact_text,
            )

    def test_export_contains_case_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = CaseRepository(root / "test.sqlite3")
            case = repository.create_case("26-123456", "Garrett Dow")
            case.crash_date = "2026-08-04"
            case.location = "North Example Street"
            case.assigned_officer_dpsst = "123456"
            case.assignment = "Traffic Investigations Unit"
            case.summary = "A detailed but unofficial investigative working summary."
            repository.save_case(case)
            person = Person(
                id=new_id(), case_id=case.id, first_name="Morgan", last_name="Lee",
                roles=["Driver"], notes="Interview completed.", cell_phone="503-555-0101",
                home_phone="503-555-0102", work_phone="503-555-0103",
                address="123 Example Street", city="Portland", state="OR",
                zip_code="97201", occupation="Engineer", dob="1985-01-02",
                sex="M", race="White",
                business_address="100 Example Avenue",
            )
            repository.save_person(person)
            repository.save_person(Person(
                id=new_id(), case_id=case.id, first_name="Legacy", last_name="Primary",
                roles=["Other"], phone="LEGACY PERSON PRIMARY PHONE",
            ))
            vehicle = Vehicle(
                id=new_id(), case_id=case.id, vehicle_number="V-1", year="2024",
                make="Toyota", model="Camry", driver_person_id=person.id,
                insurance_company="Example Mutual",
                insurance_policy_number="POL-24680",
                towed=True,
                tow_information="Central Evidence Tow Yard",
                warrant_obtained=True,
                vehicle_inspection_completed=True,
                nhtsa_recalls_checked=True,
                cdr_equipped=True,
                cdr_imaged=True,
                cdr_report_uploaded=True,
                released=True,
                release_date="2026-08-05",
                release_information="Released to registered owner with receipt",
                edr_status="Imaging completed without error",
            )
            repository.save_vehicle(vehicle)
            repository.save_road_conditions(RoadConditions(
                case_id=case.id, temperature="71", dew_point="54",
                winds="NW 6", humidity="43", pressure="29.92",
                precipitation="0.04",
                surface_condition="LEGACY SINGLE SURFACE VALUE",
                weather_station="KPDX ASOS", weather_time="14:35 PDT",
                lighting_conditions="Daylight", speed_limit="35",
                sunrise="05:59", sunset="20:31",
                civil_twilight_morning="05:27", civil_twilight_evening="21:03",
                moonrise="22:44", moonset="11:28", moon_phase="Waxing gibbous",
                streetlight_notes="LED luminaire at northeast corner",
                area_classifications="Business; Residential; Interstate",
            ))
            repository.save_surface_observation(SurfaceObservation(
                id="", case_id=case.id, location="Northbound lane",
                composition="Asphalt", condition="Wet", friction_value="0.48",
            ))
            repository.save_roadway_record(RoadwayRecord(
                id="", case_id=case.id,
                roadway_tag="North Example Street - northbound",
                speed_limit="35", speed_limit_posted="Yes",
                speed_limit_location="Northbound approach sign",
                roadway_characteristics="Three northbound travel lanes",
                traffic_controls="Traffic signal and marked crosswalk",
            ))
            repository.save_roadway_record(RoadwayRecord(
                id="", case_id=case.id,
                roadway_tag="Example Avenue - westbound",
                speed_limit="25", speed_limit_posted="Yes",
                curve_radius="420", chord="110", middle_ordinate="6.4",
                critical_speed="31",
                roadway_characteristics="Single westbound through lane",
                traffic_controls="Stop line at the intersection",
            ))
            repository.save_investigative_checklist(InvestigativeChecklist(
                case_id=case.id,
                completed_items=[
                    "Participant Interviews",
                    "Toxicology",
                    "FARO Scan Processing",
                    "DIMS CD Ordered",
                    "Axon Shared to DA",
                    "Report Peer Reviewed",
                    "Report Sgt Reviewed",
                    "Submitted to DA",
                    "Crash Diagram Completed",
                ],
                peer_review_date="2026-08-06",
                sergeant_review_date="2026-08-07",
                submitted_to_da_date="2026-08-08",
                assigned_dda="Taylor Example",
                da_case_number="DA-26-100",
            ))
            repository.save_charge_disposition(ChargeDisposition(
                id="", case_id=case.id, charge="Reckless Driving", disposition="Issued",
            ))
            repository.save_crash_details(CrashDetails(
                case_id=case.id, nearest_city="Portland", county="Multnomah",
                road_name="North Example Street", intersection_road="Example Avenue",
                outside_city_feet="LEGACY OUTSIDE CITY VALUE",
                outside_city_miles="LEGACY OUTSIDE MILES VALUE",
                outside_city_direction="East",
                non_intersection_feet="250", non_intersection_direction="North",
                non_intersection_reference="LEGACY REFERENCE VALUE",
                sergeant="Taylor Example", medical_examiner_on_scene="Morgan Example",
                criminalist_on_scene="LEGACY CRIMINALIST VALUE",
                road_jurisdiction="City", team_notified_date="2026-08-04",
                team_notified_time="13:02",
                investigator_arrival="13:20", scene_evidence=[
                    "Crime Scene Log", "Video Taken", "Surveillance Video", "PED",
                    "Trimble", "FARO", "Investigator Photos", "Uploaded to Axon",
                ],
            ))
            repository.save_video_source(VideoSource(
                id="", case_id=case.id, source="North intersection camera",
                address="100 North Example Street, Portland, OR 97201",
                axon_status="Yes", notes="Requested from traffic operations",
            ))
            repository.save_participant_details(ParticipantDetails(
                person_id=person.id, vehicle_id=vehicle.id, injury_status="Injured",
                transported="Yes", transported_to="Example Hospital", hospital="OHSU",
                height="70 in", weight="180 lb", ejected="No", extracted="Yes",
                injury_codes="1 - Laceration",
                evidence_items="Blood; Clothing",
                date_of_death="2026-08-09",
            ))
            repository.save_driver_profile(DriverProfile(
                person_id=person.id, trip_from="Home", trip_to="Work",
                hours_asleep="7 hours", license_status="Valid",
                physical_condition_types="Vision", testing_methods="SFST",
                license_restricted="Yes", license_restriction_explanation="Corrective lenses",
                endorsements="Passenger; Tank",
            ))
            repository.save_witness_details(WitnessDetails(
                person_id=person.id, interviewed="Yes", interview_date="2026-08-05",
                statement_summary="The signal was visible from the north sidewalk.",
            ))
            repository.save_contact(ContactRelationship(
                id="", case_id=case.id, contact_type="Family / Contact",
                subject_person_id=person.id, contact_name="Alex Lee", phone="503-555-0199",
                cell_phone="503-555-0198", home_phone="503-555-0197",
                work_phone="503-555-0196", city="Gresham", state="OR",
            ))
            repository.save_contact(ContactRelationship(
                id="", case_id=case.id, contact_type="Legacy",
                subject_person_id=person.id,
                contact_name="Legacy Primary Only",
                phone="LEGACY CONTACT PRIMARY PHONE",
            ))
            repository.save_vru_analysis(VRUAnalysis(
                id="", case_id=case.id, person_id=person.id, vehicle_id=vehicle.id,
                roadway_position="North crosswalk", light_meter_used=True,
                light_board_used=True, projection_classifications="Roof Vault",
                night_test_parameters="RETIRED NIGHT TEST VALUE",
                detection_distance="RETIRED DETECTION VALUE",
                prt_total="RETIRED PRT VALUE",
                prt_justification="RETIRED PRT JUSTIFICATION",
            ))
            repository.save_file_reference(FileReference(
                id="", case_id=case.id, category="Legacy",
                title="LEGACY FILE REFERENCE TITLE",
                file_path="C:/Demo/legacy-file-reference.bin", status="Reviewed",
            ))
            repository.save_diagram(DiagramRecord(
                id="", case_id=case.id, title="LEGACY DIAGRAM RECORD TITLE",
                diagram_type="Vehicle",
                template_name="car", vehicle_id=vehicle.id,
                annotations_json='[{"type":"arrow","start":[100,100],"end":[220,180],"color":"#D32F2F","width":4}]',
                notes="LEGACY DIAGRAM RECORD NOTES",
            ))
            repository.save_vehicle_inspection(VehicleInspection(
                vehicle_id=vehicle.id, mileage="12,345", brake_system="ABS",
                tire_contribution="Yes", tire_contribution_explanation="RF tread separation",
                headlights_equipped="Yes", headlights_operable="No",
                ignition_position="On", device_observations="Mounted GPS illuminated",
            ))
            repository.save_motorcycle_inspection(MotorcycleInspection(
                vehicle_id=vehicle.id, frame_number="FRAME-1", engine_number="ENGINE-1",
                inspection_date="2026-08-05", officer="Test Officer", dpsst="12345",
                items=[MotorcycleInspectionItem(
                    item_number=8, rating="2 - Damaged", measurement="20 psi",
                    comments="Below manufacturer specification",
                )],
            ))
            repository.replace_tires(vehicle.id, [TireInspection(
                id=new_id(), vehicle_id=vehicle.id, position="RF", make="Example Tire",
                size="225/45R18", pressure="34 psi", tread_middle="7/32",
                condition="Serviceable",
            )])
            repository.save_chronology(ChronologyEntry(
                id=new_id(), case_id=case.id, event_date="2026-08-04", event_time="13:20",
                summary="Scene scan completed", details="FARO scan captured before the roadway reopened.",
            ))
            repository.save_task(CaseTask(
                id=new_id(), case_id=case.id, category="Video",
                description="Review surveillance video", status="Open",
                due_date="2026-08-10", completed_date="2026-08-11",
            ))
            pdf_path = export_case_pdf(repository, case.id, root / "case.pdf")
            reader = PdfReader(pdf_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            normalized_text = " ".join(text.split())
            cover_text = reader.pages[0].extract_text() or ""
            normalized_cover_text = " ".join(cover_text.split())
            self.assertGreaterEqual(len(reader.pages), 3)
            self.assertIn("TRAFFIC CRASH INVESTIGATION PACKET", cover_text)
            self.assertIn("CASE 26-123456", cover_text)
            self.assertIn("123456", cover_text)
            self.assertIn("Traffic Investigations Unit", cover_text)
            self.assertIn("Complete - 08/06/2026", normalized_cover_text)
            self.assertIn("Complete - 08/07/2026", normalized_cover_text)
            self.assertIn("Complete - 08/08/2026", normalized_cover_text)
            self.assertIn("Taylor Example", cover_text)
            self.assertIn("DA-26-100", cover_text)
            self.assertNotIn("Key questions", cover_text)
            self.assertNotIn("unresolved issues", cover_text.lower())
            self.assertNotIn("Investigative packet", cover_text)
            self.assertIn(
                "Investigative packet",
                reader.pages[1].extract_text() or "",
            )
            self.assertIn("26-123456", text)
            self.assertIn("Morgan Lee", text)
            people_page_text = next(
                page.extract_text() or ""
                for page in reader.pages
                if "People" in (page.extract_text() or "")
                and "Morgan Lee" in (page.extract_text() or "")
            )
            self.assertRegex(
                people_page_text,
                r"M / White\s+DOB: 01/02/1985",
            )
            self.assertNotIn("01/02/1985 / M / White", people_page_text)
            self.assertIn("123 Example Street, Portland, OR 97201", normalized_text)
            self.assertIn("2024 Toyota Camry", text)
            self.assertIn("Vehicle-specific checklist", normalized_text)
            self.assertIn("WARRANT", normalized_text)
            self.assertIn("VEHICLE INSPECTION", normalized_text)
            self.assertIn("NHTSA RECALLS CHECKED", normalized_text)
            self.assertIn("TOWED / TO", normalized_text)
            self.assertIn("Yes - Central Evidence Tow Yard", normalized_text)
            self.assertIn("CDR EQUIPPED", normalized_text)
            self.assertIn("CDR IMAGED", normalized_text)
            self.assertIn("CDR REPORT UPLOADED", normalized_text)
            self.assertIn("RELEASED", normalized_text)
            self.assertIn("RELEASE DATE", normalized_text)
            self.assertIn("08/05/2026", normalized_text)
            self.assertIn(
                "Released to registered owner with receipt",
                normalized_text,
            )
            self.assertIn("INSURANCE COMPANY", normalized_text)
            self.assertIn("POLICY NUMBER", normalized_text)
            self.assertIn("Example Mutual", normalized_text)
            self.assertIn("POL-24680", normalized_text)
            self.assertIn("Imaging completed without error", normalized_text)
            self.assertIn("Scene scan completed", text)
            self.assertIn("Investigative journal", text)
            self.assertIn("JOURNAL ENTRIES", normalized_text)
            self.assertIn("JOURNAL CONTINUATION", normalized_text)
            self.assertNotIn("Investigative chronology", text)
            self.assertNotIn("CHRONOLOGY CONTINUATION", normalized_text)
            self.assertIn("Review surveillance video", text)
            self.assertIn("Road and weather conditions", text)
            self.assertIn("WEATHER STATION", normalized_text)
            self.assertIn("TIME OF READING", normalized_text)
            self.assertIn("71 F", normalized_text)
            self.assertIn("54 F", normalized_text)
            self.assertIn("NW 6 mph", normalized_text)
            self.assertIn("43%", normalized_text)
            self.assertIn("29.92 inHg", normalized_text)
            self.assertIn("0.04 in", normalized_text)
            self.assertIn("KPDX ASOS", text)
            self.assertIn("14:35 PDT", text)
            self.assertIn("MORNING CIVIL TWILIGHT", normalized_text)
            self.assertIn("EVENING CIVIL TWILIGHT", normalized_text)
            self.assertIn("05:27", text)
            self.assertIn("21:03", text)
            self.assertIn("MOONRISE", normalized_text)
            self.assertIn("MOONSET", normalized_text)
            self.assertIn("MOON PHASE", normalized_text)
            self.assertIn("22:44", text)
            self.assertIn("11:28", text)
            self.assertIn("Waxing gibbous", text)
            self.assertIn("Interstate", text)
            self.assertIn("Roadways", text)
            self.assertIn("ROADWAY", text)
            self.assertNotIn("ROADWAY / TAG", text)
            self.assertIn("North Example Street - northbound", normalized_text)
            self.assertIn("Example Avenue - westbound", normalized_text)
            self.assertIn("Northbound approach sign", normalized_text)
            self.assertIn("Three northbound travel lanes", normalized_text)
            self.assertIn("Stop line at the intersection", normalized_text)
            self.assertIn("Investigative checklist", text)
            self.assertIn("Toxicology", text)
            self.assertIn("Axon Shared to DA", text)
            self.assertIn("Report Peer Reviewed", text)
            self.assertIn("Report Sgt Reviewed", text)
            self.assertIn("Submitted to DA", text)
            self.assertIn("08/06/2026", text)
            self.assertIn("08/07/2026", text)
            self.assertIn("08/08/2026", text)
            self.assertIn("08/04/2026", text)
            self.assertIn("01/02/1985", text)
            self.assertIn("08/05/2026", text)
            self.assertIn("08/09/2026", text)
            self.assertIn("08/10/2026", text)
            for storage_date in (
                "2026-08-04",
                "2026-08-05",
                "2026-08-06",
                "2026-08-07",
                "2026-08-08",
                "2026-08-09",
                "2026-08-10",
                "1985-01-02",
            ):
                self.assertNotIn(storage_date, text)
            self.assertNotIn("DIMS", text)
            self.assertIn("Taylor Example", text)
            self.assertIn("Reckless Driving", text)
            self.assertIn("North intersection camera", text)
            self.assertIn(
                "100 North Example Street, Portland, OR 97201",
                normalized_text,
            )
            self.assertIn("UPLOADED TO AXON", text)
            self.assertIn("North Example Street / Example Avenue", normalized_text)
            self.assertIn("NOT AT INTERSECTION", normalized_text)
            self.assertIn("250 ft North of intersection", normalized_text)
            self.assertIn("MCT Sergeant: Taylor Example", normalized_text)
            self.assertIn("MDI: Morgan Example", normalized_text)
            self.assertNotIn("LEGACY CRIMINALIST VALUE", normalized_text)
            self.assertIn(
                "Investigator Photos, Uploaded to Axon, FARO, Surveillance Video",
                normalized_text,
            )
            self.assertNotIn("Crime Scene Log", normalized_text)
            self.assertNotIn("Video Taken", normalized_text)
            self.assertNotRegex(normalized_text, r"\bPED\b")
            self.assertNotIn("Trimble", normalized_text)
            self.assertNotIn("OUTSIDE CITY", text)
            self.assertNotIn("LEGACY OUTSIDE CITY VALUE", text)
            self.assertNotIn("LEGACY OUTSIDE MILES VALUE", text)
            self.assertNotIn("LEGACY REFERENCE VALUE", text)
            self.assertIn("Surface observations", text)
            self.assertIn("0.48", text)
            self.assertNotIn("LEGACY SINGLE SURFACE VALUE", text)
            self.assertIn("Corrective lenses", text)
            participant_block = normalized_text.split(
                "Participant and driver details",
                1,
            )[1].split("Vehicles", 1)[0]
            self.assertIn("GENDER / RACE M / White DOB 01/02/1985", participant_block)
            self.assertLess(
                participant_block.index("HEIGHT / WEIGHT"),
                participant_block.index("TRANSPORT"),
            )
            self.assertIn("ENDORSEMENTS Passenger; Tank", participant_block)
            self.assertIn("PHYSICAL CONDITIONS Vision", participant_block)
            self.assertLess(
                participant_block.index("IMPAIRMENT"),
                participant_block.index("PHYSICAL CONDITIONS"),
            )
            self.assertLess(
                participant_block.index("PHYSICAL CONDITIONS"),
                participant_block.index("SLEEP / AWAKE"),
            )
            self.assertNotIn("Physical condition selections", participant_block)
            self.assertIn("Roof Vault", text)
            self.assertIn("RF tread separation", text)
            self.assertIn("Motorcycle information and 44-item inspection", text)
            self.assertIn("FRAME-1", text)
            self.assertIn("20 psi", text)
            self.assertIn("Example Hospital", text)
            self.assertIn("EJECTED / EXTRACTED", normalized_text)
            self.assertIn("Ejected No; extracted Yes", normalized_text)
            self.assertIn("12,345", text)
            self.assertIn("225/45R18", text)
            self.assertIn("Witness interviews and contacts", text)
            self.assertIn("PERSON", normalized_text)
            self.assertIn("The signal was visible", text)
            self.assertNotIn("LEGACY PERSON PRIMARY PHONE", text)
            self.assertNotIn("LEGACY CONTACT PRIMARY PHONE", text)
            self.assertIn("Vulnerable road user analysis", text)
            self.assertIn("LIGHT METER USED", normalized_text)
            self.assertIn("LIGHT BOARD USED", normalized_text)
            self.assertNotIn("PERCEPTION / RESPONSE", normalized_text)
            self.assertNotIn("RETIRED NIGHT TEST VALUE", text)
            self.assertNotIn("RETIRED DETECTION VALUE", text)
            self.assertNotIn("RETIRED PRT VALUE", text)
            self.assertNotIn("RETIRED PRT JUSTIFICATION", text)
            self.assertNotIn("Related files and records", text)
            self.assertNotIn("ADDITIONAL FILES / EVIDENCE REFERENCES", text)
            self.assertNotIn("LEGACY FILE REFERENCE TITLE", text)
            self.assertNotIn("legacy-file-reference.bin", text)
            self.assertNotIn("Annotated diagram", text)
            self.assertNotIn("Handwritten sketch / diagram continuation", text)
            self.assertNotIn("Diagram notes / added markings", text)
            self.assertNotIn("LEGACY DIAGRAM RECORD TITLE", text)
            self.assertNotIn("LEGACY DIAGRAM RECORD NOTES", text)
            self.assertIn("Crash Diagram Completed", text)
            self.assertIn("not an official report", text)
            self.assertIn("FULL WORKING PACKET", text)
            self.assertIn("COVER NOTES / ROUTING UPDATES", text)
            self.assertIn(f"Page 1 of {len(reader.pages)}", text)
            self.assertTrue(all("CASE 26-123456" in (page.extract_text() or "") for page in reader.pages))

            compact_path = export_case_compact_pdf(repository, case.id, root / "compact.pdf")
            compact_reader = PdfReader(compact_path)
            compact_text = "\n".join(page.extract_text() or "" for page in compact_reader.pages)
            self.assertLess(len(compact_reader.pages), len(reader.pages))
            self.assertIn("COMPACT COMPLETED-CASE PACKET", compact_text)
            self.assertNotIn("COVER NOTES / ROUTING UPDATES", compact_text)
            self.assertIn("Morgan Lee", compact_text)
            self.assertIn("KPDX ASOS", compact_text)
            self.assertIn("71 F", compact_text)
            self.assertIn("NW 6 mph", compact_text)
            self.assertIn("29.92 inHg", compact_text)
            self.assertIn("Waxing gibbous", compact_text)
            normalized_compact_text = " ".join(compact_text.split())
            self.assertIn("TOWED / TO", normalized_compact_text)
            self.assertIn(
                "Yes - Central Evidence Tow Yard",
                normalized_compact_text,
            )
            self.assertNotIn("ROADWAY / TAG", normalized_compact_text)
            self.assertIn("North Example Street - northbound", normalized_compact_text)
            self.assertIn("Example Avenue - westbound", normalized_compact_text)
            self.assertIn("Motorcycle information and 44-item inspection", compact_text)
            self.assertGreaterEqual(compact_text.count("MOTORCYCLE INSPECTION"), 2)
            self.assertNotIn("Related files and records", compact_text)
            self.assertNotIn("LEGACY FILE REFERENCE TITLE", compact_text)
            self.assertNotIn("Annotated diagram", compact_text)
            self.assertNotIn("LEGACY DIAGRAM RECORD TITLE", compact_text)
            self.assertIn(f"Page 1 of {len(compact_reader.pages)}", compact_text)
            self.assertTrue(
                all("CASE 26-123456" in (page.extract_text() or "") for page in compact_reader.pages)
            )

            summary_path = export_case_summary_pdf(repository, case.id, root / "summary.pdf")
            summary_reader = PdfReader(summary_path)
            summary_text = "\n".join(page.extract_text() or "" for page in summary_reader.pages)
            self.assertLess(len(summary_reader.pages), len(reader.pages))
            self.assertIn("26-123456", summary_text)
            self.assertIn("Scene scan completed", summary_text)
            self.assertIn("Quick review", summary_text)
            self.assertNotIn("Key questions", summary_text)
            self.assertNotIn("unresolved issues", summary_text.lower())
            self.assertIn(f"Page 1 of {len(summary_reader.pages)}", summary_text)


if __name__ == "__main__":
    unittest.main()
