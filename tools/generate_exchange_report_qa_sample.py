from __future__ import annotations

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from traffic_crash_notebook.exchange_report import export_exchange_report_pdf
from traffic_crash_notebook.models import (
    CrashDetails,
    DriverProfile,
    ParticipantDetails,
    Person,
    Vehicle,
)
from traffic_crash_notebook.repository import CaseRepository


def main() -> Path:
    destination = ROOT / "output" / "pdf" / "TrafficCrashExchangeReport-Sample.pdf"
    temporary_parent = ROOT / "tmp" / "pdfs"
    temporary_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="exchange-report-qa-", dir=temporary_parent) as directory:
        repository = CaseRepository(Path(directory) / "sample.sqlite3")
        case = repository.create_case("26-123456", "Officer Primary")
        case.crash_date = "2026-08-05"
        case.crash_time = "14:35"
        case.assigned_officer_dpsst = "12345"
        case.assignment = "Traffic Division"
        repository.save_case(case)
        repository.save_crash_details(CrashDetails(
            case_id=case.id,
            road_name="North Example Street",
            intersection_road="West Sample Avenue",
        ))
        vehicles: list[Vehicle] = []
        for index in range(7):
            number = index + 1
            driver = repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name=f"Driver{number}",
                middle_name="Q",
                last_name=f"Example{number}",
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
                license_number=f"DL-{number:03d}",
                license_state="OR",
            ))
            vehicle = repository.save_vehicle(Vehicle(
                id="",
                case_id=case.id,
                vehicle_number=f"V-{number}",
                year=str(2019 + number),
                make=f"Make{number}",
                model=f"Model{number}",
                body_style="Four-door SUV",
                color=f"Color{number}",
                plate=f"PLATE{number}",
                plate_state="OR",
                driver_person_id=driver.id,
                insurance_company=f"Insurance Company {number}",
                insurance_policy_number=f"POLICY-{number:03d}",
                property_damage="None" if index % 2 == 0 else "Roadside fence",
            ))
            vehicles.append(vehicle)

        for index in range(9):
            number = index + 1
            role = "Passenger" if index % 2 == 0 else "Witness"
            person = repository.save_person(Person(
                id="",
                case_id=case.id,
                first_name=f"Person{number}",
                last_name=f"Exchange{number}",
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

        return export_exchange_report_pdf(repository, case.id, destination)


if __name__ == "__main__":
    try:
        result = main()
        print(result)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    raise SystemExit(0)
