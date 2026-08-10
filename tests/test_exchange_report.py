from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from traffic_crash_notebook.exchange_report import export_exchange_report_pdf
from traffic_crash_notebook.models import (
    CrashDetails,
    DriverProfile,
    ParticipantDetails,
    Person,
    Vehicle,
)
from traffic_crash_notebook.repository import CaseRepository


class ExchangeReportPdfTest(unittest.TestCase):
    def test_empty_case_omits_unused_blocks_and_appends_information_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = CaseRepository(root / "empty.sqlite3")
            case = repository.create_case("26-EMPTY-EXCHANGE", "Officer Empty")
            path = export_exchange_report_pdf(
                repository,
                case.id,
                root / "empty-exchange.pdf",
            )
            reader = PdfReader(path)
            self.assertEqual(len(reader.pages), 2)
            text = reader.pages[0].extract_text() or ""
            self.assertIn("TRAFFIC CRASH EXCHANGE REPORT", text)
            self.assertIn("CRASH DATE / TIME", text)
            self.assertNotIn("INSURANCE POLICY NUMBER", text)
            self.assertNotIn("PERSON NAME", text)
            self.assertIn("Officer Empty", text)
            self.assertIn("1 / 1", text)
            information_text = reader.pages[-1].extract_text() or ""
            self.assertIn("INFORMATION / YOUR RESPONSIBILITIES", information_text)
            self.assertIn("PORTLAND POLICE BUREAU POLICY STATEMENT", information_text)
            self.assertIn("TRAFFIC CRASH REPORTING REQUIREMENTS", information_text)
            self.assertIn("Damage to your vehicle is over $2500", information_text)
            self.assertIn("770 (12/17)", information_text)
            self.assertFalse(list(reader.pages[-1].images))

    def test_unlimited_records_create_numbered_continuation_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = CaseRepository(root / "multi.sqlite3")
            case = repository.create_case("26-EXCHANGE", "Officer Primary")
            case.crash_date = "2026-08-05"
            case.crash_time = "14:35"
            case.assigned_officer_dpsst = "12345"
            case.assignment = "East Precinct"
            repository.save_case(case)
            repository.save_crash_details(CrashDetails(
                case_id=case.id,
                road_name="North Example Street",
                intersection_road="West Sample Avenue",
            ))
            vehicles: list[Vehicle] = []
            for index in range(7):
                driver = repository.save_person(Person(
                    id="",
                    case_id=case.id,
                    first_name=f"Driver{index + 1}",
                    last_name=f"Example{index + 1}",
                    address=f"{100 + index} Driver Street",
                    city="Portland",
                    state="OR",
                    zip_code=f"972{index:02d}",
                    home_phone=f"503-555-10{index:02d}",
                    work_phone=f"503-555-20{index:02d}",
                    cell_phone=f"503-555-30{index:02d}",
                    roles=["Driver"],
                ))
                repository.save_driver_profile(DriverProfile(
                    person_id=driver.id,
                    license_number=f"DL-{index + 1:03d}",
                    license_state="OR",
                ))
                vehicle = repository.save_vehicle(Vehicle(
                    id="",
                    case_id=case.id,
                    vehicle_number=f"V-{index + 1}",
                    year=str(2020 + index),
                    make=f"Make{index + 1}",
                    model=f"Model{index + 1}",
                    body_style="Four-door SUV",
                    color=f"Color{index + 1}",
                    plate=f"PLATE{index + 1}",
                    plate_state="OR",
                    driver_person_id=driver.id,
                    insurance_company=f"Insurance Company {index + 1}",
                    insurance_policy_number=f"POLICY-{index + 1:03d}",
                    property_damage="None" if index % 2 == 0 else "Roadside fence",
                ))
                vehicles.append(vehicle)

            for index in range(9):
                role = "Passenger" if index % 2 == 0 else "Witness"
                person = repository.save_person(Person(
                    id="",
                    case_id=case.id,
                    first_name=f"Person{index + 1}",
                    last_name=f"Exchange{index + 1}",
                    address=f"{200 + index} Person Avenue",
                    city="Portland",
                    state="OR",
                    zip_code=f"971{index:02d}",
                    cell_phone=f"971-555-40{index:02d}",
                    roles=[role],
                ))
                if role == "Passenger":
                    repository.save_participant_details(ParticipantDetails(
                        person_id=person.id,
                        vehicle_id=vehicles[index % len(vehicles)].id,
                    ))
            repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Pat",
                last_name="Pedestrian",
                address="310 Walking Way",
                city="Portland",
                state="OR",
                zip_code="97210",
                cell_phone="971-555-5000",
                roles=["Pedestrian"],
            ))
            repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Blair",
                last_name="Bicyclist",
                address="311 Riding Road",
                city="Portland",
                state="OR",
                zip_code="97211",
                cell_phone="971-555-5001",
                roles=["Bicyclist"],
            ))
            repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Morgan",
                last_name="Motorcyclist",
                address="312 Motorcycle Way",
                city="Portland",
                state="OR",
                zip_code="97212",
                cell_phone="971-555-5002",
                roles=["Motorcyclist"],
            ))

            path = export_exchange_report_pdf(
                repository,
                case.id,
                root / "multi-exchange.pdf",
            )
            reader = PdfReader(path)
            self.assertEqual(len(reader.pages), 4)
            page_texts = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(page_texts)
            self.assertIn("08/05/2026 02:35 PM", text)
            self.assertIn("North Example Street / West Sample Avenue", text)
            self.assertIn("Officer Primary", text)
            self.assertIn("12345", text)
            self.assertIn("East Precinct", text)
            self.assertIn("Example1, Driver1", text)
            self.assertIn("DL-001", text)
            self.assertIn("V-7", text)
            self.assertIn("PLATE7", text)
            self.assertIn("POLICY-007", text)
            self.assertIn("Exchange1, Person1", text)  # Passenger
            self.assertIn("Exchange2, Person2", text)  # Witness
            self.assertIn("Exchange9, Person9", text)
            self.assertIn("Pedestrian, Pat", text)
            self.assertIn("PEDESTRIAN", text)
            self.assertIn("Bicyclist, Blair", text)
            self.assertIn("BICYCLIST", text)
            self.assertIn("Motorcyclist, Morgan", text)
            self.assertIn("MOTORCYCLIST", text)
            self.assertEqual(text.count("PERSON NAME (LAST, FIRST, MI)"), 12)
            self.assertIn("1 / 3", page_texts[0])
            self.assertIn("2 / 3", page_texts[1])
            self.assertIn("3 / 3", page_texts[2])
            self.assertIn(
                "IT IS NOT AN OFFICIAL OREGON POLICE TRAFFIC CRASH REPORT",
                page_texts[-1],
            )
            self.assertFalse(list(reader.pages[-1].images))

    def test_unlinked_driver_and_vehicle_owner_vru_are_both_printed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = CaseRepository(root / "legacy-links.sqlite3")
            case = repository.create_case("26-LEGACY-LINKS", "Officer Link")
            case.assigned_officer_dpsst = "24680"
            case.assignment = "Traffic Investigations"
            repository.save_case(case)

            driver = repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Dana",
                last_name="Driver",
                address="100 Driver Drive",
                city="Portland",
                state="OR",
                zip_code="97201",
                cell_phone="503-555-1000",
                roles=["Driver"],
            ))
            pedestrian_owner = repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Parker",
                last_name="Pedestrian",
                address="200 Walking Way",
                city="Portland",
                state="OR",
                zip_code="97202",
                cell_phone="503-555-2000",
                roles=["Pedestrian", "Vehicle Owner"],
            ))
            bicyclist = repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name="Bailey",
                last_name="Bicyclist",
                address="300 Bicycle Boulevard",
                city="Portland",
                state="OR",
                zip_code="97203",
                cell_phone="503-555-3000",
                roles=["Bicyclist"],
            ))
            repository.save_driver_profile(DriverProfile(
                person_id=driver.id,
                license_number="DL-LEGACY",
                license_state="OR",
            ))
            repository.save_vehicle(Vehicle(
                id="",
                case_id=case.id,
                vehicle_number="V-1",
                year="2024",
                make="Example",
                model="Vehicle",
                plate="LEGACY1",
                plate_state="OR",
                owner_person_id=pedestrian_owner.id,
            ))

            path = export_exchange_report_pdf(
                repository,
                case.id,
                root / "legacy-links-exchange.pdf",
            )
            reader = PdfReader(path)
            front_text = "\n".join(
                page.extract_text() or "" for page in reader.pages[:-1]
            )
            self.assertIn("Driver, Dana", front_text)
            self.assertIn("DL-LEGACY", front_text)
            self.assertIn("Pedestrian, Parker", front_text)
            self.assertIn("PEDESTRIAN", front_text)
            self.assertIn("Bicyclist, Bailey", front_text)
            self.assertIn("BICYCLIST", front_text)
            self.assertIn("24680", front_text)
            self.assertIn("Traffic Investigations", front_text)


if __name__ == "__main__":
    unittest.main()
