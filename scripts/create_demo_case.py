from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from traffic_crash_notebook.models import (
    CaseTask,
    ChronologyEntry,
    ContactRelationship,
    DriverProfile,
    FileReference,
    ParticipantDetails,
    Person,
    RoadConditions,
    SurfaceObservation,
    TireInspection,
    Vehicle,
    VehicleInspection,
    VRUAnalysis,
    WitnessDetails,
)
from traffic_crash_notebook.pdf_export import export_case_pdf
from traffic_crash_notebook.repository import CaseRepository, new_id


def main() -> None:
    output_dir = PROJECT_ROOT / "output" / "pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "demo.sqlite3"
    if database.exists():
        database.unlink()
    repository = CaseRepository(database)
    case = repository.create_case("DEMO-0001", "Example Investigator")
    case.crash_date = "2026-08-04"
    case.crash_time = "14:35"
    case.location = "Example Avenue at Sample Street, Portland, Oregon"
    case.status = "Analysis"
    case.summary = (
        "Vehicle-pedestrian intersection crash used solely to demonstrate the working-notes application. "
        "The fictional investigation is focused on documenting the vehicle and pedestrian paths, interviewing a "
        "witness, and comparing the physical evidence with the available video."
    )
    case.notes = "This demonstration contains fictionalized working-note content for layout verification."
    repository.save_case(case)

    driver = Person(
        id=new_id(), case_id=case.id, first_name="Jordan", last_name="Rivera",
        dob="1998-04-12", phone="503-555-0142", roles=["Driver", "Victim"],
        notes="Hospital interview pending medical clearance.",
    )
    witness = Person(
        id=new_id(), case_id=case.id, first_name="Taylor", last_name="Morgan",
        phone="503-555-0181", roles=["Witness"],
        notes="Reported seeing one vehicle enter the intersection after the signal changed.",
    )
    pedestrian = Person(
        id=new_id(), case_id=case.id, first_name="Avery", last_name="Chen",
        dob="1987-09-23", roles=["Pedestrian", "Victim"],
        notes="Fictional pedestrian used to demonstrate medical and visibility records.",
    )
    repository.save_person(driver)
    repository.save_person(witness)
    repository.save_person(pedestrian)
    vehicle = Vehicle(
        id=new_id(), case_id=case.id, vehicle_number="V-1", year="2022", make="Toyota",
        model="Camry", color="Blue", plate="123ABC", plate_state="OR",
        driver_person_id=driver.id, edr_status="Download scheduled",
        towed=True,
        tow_information="Example Towing - Hold for inspection",
        nhtsa_recalls_checked=True,
        damage_notes="Fictional frontal damage concentrated at the bumper, grille, and leading edge of the hood.",
    )
    repository.save_vehicle(vehicle)
    repository.save_road_conditions(RoadConditions(
        case_id=case.id, temperature="74", dew_point="54", winds="NW 6",
        humidity="43", weather_condition="Clear", precipitation="None",
        weather_time="14:45", lighting_conditions="Daylight; sun southwest of the intersection",
        streetlights_working="Not applicable", area_type="Business",
        speed_limit="35", speed_limit_posted="Yes", speed_limit_location="Both approaches",
        roadway_characteristics="Level four-leg intersection with two through lanes in each direction.",
        traffic_controls="Traffic signals and marked crosswalks on all approaches.",
        initial_point_of_collision="Fictional debris and tire evidence placed the initial contact near the center of the intersection.",
    ))
    repository.save_surface_observation(SurfaceObservation(
        id="", case_id=case.id, location="Example Avenue eastbound lanes",
        composition="Asphalt", condition="Dry", friction_value="0.78",
        notes="Fictional drag-factor entry for the primary travel surface.",
    ))
    repository.save_surface_observation(SurfaceObservation(
        id="", case_id=case.id, location="South crosswalk marking",
        composition="Thermoplastic marking over asphalt", condition="Dry",
        notes="Separate surface record demonstrating multiple locations.",
    ))
    repository.save_participant_details(ParticipantDetails(
        person_id=driver.id, vehicle_id=vehicle.id, occupant_position="Driver",
        injury_status="Injured", transported="Yes", transported_to="Example Medical Center",
        medical_records_status="Requested", seatbelt_installed="Yes", seatbelt_used="Yes",
        airbag_deployed="Yes", ejected="No", injuries="Complaint of chest and left shoulder pain.",
        evidence_obtained="Hospital blood draw documented in the fictional scenario.",
    ))
    repository.save_participant_details(ParticipantDetails(
        person_id=pedestrian.id, injury_status="Injured", transported="Yes",
        transported_to="Example Medical Center", medical_records_status="Obtained",
        injuries="Fictional abrasions and lower-leg injury documented for layout testing.",
        evidence_obtained="Clothing photographed and retained in the fictional scenario.",
    ))
    repository.save_driver_profile(DriverProfile(
        person_id=driver.id, trip_from="Residence", trip_to="Work",
        trip_purpose="Commute", impairment_status="No", testing="No impairment indicators observed",
        sleep_time="23:00", wake_time="06:30", hours_asleep="7.5 hours",
        hours_awake="8 hours", familiar_with_road="Yes", familiar_with_vehicle="Yes",
        years_driving="10 years", license_state="OR", license_class="C", license_status="Valid",
    ))
    repository.save_vehicle_inspection(VehicleInspection(
        vehicle_id=vehicle.id, mileage="28,412", transmission="Automatic", gear="Drive",
        steering="No pre-crash defect identified", front_brakes="Serviceable",
        rear_brakes="Serviceable", brake_system="Four-wheel ABS",
        lighting_electrical="Headlamps and signal lamps inspected; no relevant pre-crash defect identified.",
        safety_systems="Driver frontal air bag deployed; seat belt webbing showed loading.",
        tire_contribution="No", tire_notes="All four tires had serviceable tread in the fictional inspection.",
    ))
    repository.replace_tires(vehicle.id, [
        TireInspection(id=new_id(), vehicle_id=vehicle.id, position=position, make="Example Tire",
                       design="Touring", size="235/45R18", pressure=pressure,
                       tread_inside="7/32", tread_middle="7/32", tread_outside="6/32",
                       condition="Serviceable")
        for position, pressure in (("RF", "34 psi"), ("LF", "34 psi"), ("LR", "33 psi"), ("RR", "33 psi"))
    ])
    repository.save_witness_details(WitnessDetails(
        person_id=witness.id, interviewed="Yes", interview_date="2026-08-04",
        interviewer="Example Investigator", significance="Independent view of signal phase and pedestrian movement",
        statement_summary=(
            "Taylor reported seeing the pedestrian enter the marked crosswalk before the vehicle reached "
            "the stop line. This statement is fictional and included only to demonstrate the interview screen."
        ),
        credibility_notes="View was partially interrupted by a street tree; account should be compared with video.",
        follow_up="Conduct a recorded follow-up after completing the video timing comparison.",
    ))
    repository.save_contact(ContactRelationship(
        id="", case_id=case.id, contact_type="Family / Contact", subject_person_id=pedestrian.id,
        contact_name="Riley Chen", phone="503-555-0126", email="riley.chen@example.invalid",
        notes="Fictional emergency contact for demonstration only.",
    ))
    repository.save_vru_analysis(VRUAnalysis(
        id="", case_id=case.id, person_id=pedestrian.id, vehicle_id=vehicle.id,
        upper_clothing="Dark blue jacket with reflective zipper pull", lower_clothing="Light gray pants",
        roadway_position="East leg marked crosswalk", movement_at_impact="Walking south",
        projection_profile="Forward projection with clockwise rotation", sightlines="Driver view opened beyond the northwest corner landscaping.",
        driver_thought_process="Compare stated signal attention with the available approach video.",
        driver_impairment="No", driver_sleep_information="Reported 7.5 hours of sleep and 8 hours awake.",
        vru_impairment="Unknown", impact_location_on_vehicle="Right-front bumper and hood edge",
        vehicle_approach_speed="Approximately 28 mph", vehicle_direction="Eastbound",
        vru_approach_speed="Walking pace", vru_direction="Southbound", person_throw_distance="34 feet",
        light_meter_used=True, light_board_used=True,
        notes="No reconstruction conclusion is implied by this demonstration.",
    ))
    repository.save_file_reference(FileReference(
        id="", case_id=case.id, category="Video", title="Intersection surveillance export",
        file_path=r"C:\ExampleCase\Video\intersection_camera.mp4", reference_date="2026-08-04",
        status="Reviewed", notes="Fictional path; the application stores a reference and does not copy the file.",
    ))
    repository.save_file_reference(FileReference(
        id="", case_id=case.id, category="Medical", title="Pedestrian treatment records",
        file_path=r"C:\ExampleCase\Medical\Avery_Chen_records.pdf", reference_date="2026-08-06",
        status="Received", person_id=pedestrian.id,
    ))
    repository.save_chronology(ChronologyEntry(
        id=new_id(), case_id=case.id, event_date="2026-08-04", event_time="14:42",
        category="Scene", summary="Major Crash Team notified",
        details="Patrol requested a crash-team response after confirming serious injury in the fictional scenario.",
    ))
    repository.save_chronology(ChronologyEntry(
        id=new_id(), case_id=case.id, event_date="2026-08-04", event_time="16:10",
        category="Evidence", summary="Surveillance video obtained",
        details="Original video file was collected and retained in the approved evidence system.",
    ))
    repository.save_chronology(ChronologyEntry(
        id=new_id(), case_id=case.id, event_date="2026-08-05", event_time="09:15",
        category="Analysis", summary="Vehicle paths reviewed",
        details="Scene measurements were used to document the fictional vehicle paths and approximate impact location.",
    ))
    repository.save_task(CaseTask(
        id=new_id(), case_id=case.id, category="Medical records",
        description="Obtain final hospital records", status="Waiting", due_date="2026-08-14",
        notes="Request submitted; authorization confirmed.",
    ))
    repository.save_task(CaseTask(
        id=new_id(), case_id=case.id, category="Analysis",
        description="Complete video timing comparison", status="Open",
        notes="Verify camera frame rate before relying on the speed estimate.",
    ))
    destination = export_case_pdf(repository, case.id, output_dir / "TrafficCrashNotebook_Demo.pdf")
    print(destination)


if __name__ == "__main__":
    main()
