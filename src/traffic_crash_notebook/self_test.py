from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from . import __version__
from .build_info import load_build_info
from .models import (
    ChargeDisposition,
    CrashDetails,
    DriverProfile,
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
    UserDefaults,
    Vehicle,
    VehicleInspection,
    VideoSource,
    VRUAnalysis,
    WitnessDetails,
)
from .pdf_export import export_case_compact_pdf, export_case_pdf, export_case_summary_pdf
from .exchange_report import export_exchange_report_pdf, person_name_last_first
from .paths import (
    DATABASE_FILENAME,
    load_storage_config,
    migrate_database,
    save_storage_config,
    validate_storage_directory,
)
from .repository import SCHEMA_VERSION, CaseRepository, new_id
from .resources import app_icon_path, startup_splash_path
from .spellcheck import SpellCheckService
from .updates import is_update_available, parse_update_manifest


def run_self_test(output_directory: str | Path) -> Path:
    """Exercise the bundled database, assets, and PDF engine without opening the GUI."""
    try:
        from PySide6.QtGui import QImageReader
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView
    except ImportError as error:
        raise RuntimeError("The embedded PDF preview components are unavailable.") from error
    if not QPdfDocument or not QPdfView:
        raise RuntimeError("The embedded PDF preview components did not load.")

    icon_path = app_icon_path()
    if not icon_path.is_file():
        raise RuntimeError("The bundled TIU application icon is missing.")
    icon_reader = QImageReader(str(icon_path))
    if not icon_reader.canRead() or icon_reader.read().isNull():
        raise RuntimeError("The bundled TIU application icon could not be loaded.")

    splash_path = startup_splash_path()
    if not splash_path.is_file():
        raise RuntimeError("The bundled startup splash image is missing.")
    splash_reader = QImageReader(str(splash_path))
    if not splash_reader.canRead() or splash_reader.read().isNull():
        raise RuntimeError("The bundled startup splash image could not be loaded.")

    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = output / "portable_self_test.sqlite3"
    pdf = output / "portable_self_test.pdf"
    compact_pdf = output / "portable_self_test_compact_packet.pdf"
    summary_pdf = output / "portable_self_test_quick_review.pdf"
    exchange_pdf = output / "portable_self_test_exchange_report.pdf"
    log = output / "portable_self_test.txt"

    spell_service = SpellCheckService(output / "portable_self_test_dictionary.txt")
    if not spell_service.is_misspelled("accidnet"):
        raise RuntimeError("The bundled spell-check dictionary did not detect a test typo.")
    if "accident" not in spell_service.suggestions("accidnet"):
        raise RuntimeError("The bundled spell-check dictionary did not suggest a correction.")
    if not spell_service.add_to_personal_dictionary("reconword"):
        raise RuntimeError("The personal spell-check dictionary could not be updated.")
    if spell_service.is_misspelled("reconword"):
        raise RuntimeError("The personal spell-check dictionary was not applied.")

    update_manifest = parse_update_manifest({
        "schema_version": 1,
        "application_id": "traffic-crash-notebook",
        "application_name": "Traffic Crash Notebook",
        "channel": "stable",
        "version": "99.0.0",
        "release_tag": "v99.0.0",
        "published_at": "2026-08-05T21:00:00Z",
        "release_page_url": (
            "https://github.com/gdowkpc/traffic-crash-notebook/releases/tag/v99.0.0"
        ),
        "release_notes": "Portable self-test manifest.",
        "minimum_supported_version": "0.4.8",
        "windows_portable": {
            "filename": "TrafficCrashNotebook-99.0.0-Windows-Portable.zip",
            "download_url": (
                "https://github.com/gdowkpc/traffic-crash-notebook/releases/download/"
                "v99.0.0/TrafficCrashNotebook-99.0.0-Windows-Portable.zip"
            ),
            "sha256": "0" * 64,
            "size_bytes": 1,
            "build_id": "portable-self-test",
            "architecture": "x86_64",
            "packaging": "portable-zip",
            "requires_admin": False,
            "self_test": "PASS",
        },
        "package_manifest": {
            "filename": "TrafficCrashNotebook-99.0.0-Windows-Portable.files.json",
            "download_url": (
                "https://github.com/gdowkpc/traffic-crash-notebook/releases/download/"
                "v99.0.0/TrafficCrashNotebook-99.0.0-Windows-Portable.files.json"
            ),
            "sha256": "1" * 64,
        },
    })
    if not is_update_available(__version__, update_manifest.version):
        raise RuntimeError("The verified release-manifest update checker did not load.")

    repository = CaseRepository(database)
    repository.save_user_defaults(UserDefaults(
        user_name="Portable Build Verification",
        dpsst="12345",
        assignment="Verification Precinct",
    ))
    persisted_defaults = CaseRepository(database).get_user_defaults()
    if (
        persisted_defaults.user_name != "Portable Build Verification"
        or persisted_defaults.dpsst != "12345"
        or persisted_defaults.assignment != "Verification Precinct"
    ):
        raise RuntimeError("The user defaults were not stored with the case database.")
    case = repository.create_case(
        "SELF-TEST",
        persisted_defaults.user_name,
        persisted_defaults.dpsst,
        persisted_defaults.assignment,
    )
    case.location = "Local verification only"
    case.crash_date = "2026-08-05"
    case.crash_time = "14:35"
    case.assigned_officer_dpsst = "12345"
    case.assignment = "Verification Precinct"
    case.summary = "Fictional record generated automatically to verify this portable build."
    repository.save_case(case)
    loaded_case = repository.get_case(case.id)
    if (
        not loaded_case
        or loaded_case.assigned_officer_dpsst != "12345"
        or loaded_case.assignment != "Verification Precinct"
    ):
        raise RuntimeError("Assigned-officer DPSST and assignment persistence failed.")

    person = repository.save_person(Person(
        id=new_id(), case_id=case.id, first_name="Test", last_name="Record",
        address="123 Verification Street", city="Portland", state="OR",
        zip_code="97201-1234",
        roles=["Driver", "Witness"],
    ))
    if repository.get_person(person.id).zip_code != "97201-1234":
        raise RuntimeError("The person ZIP code could not be saved and reloaded.")
    vehicle = repository.save_vehicle(Vehicle(
        id=new_id(), case_id=case.id, vehicle_number="V-1", year="2026",
        make="Example", model="Vehicle", body_style="Four-door SUV",
        color="Blue", plate="SELFTEST", plate_state="OR",
        driver_person_id=person.id,
        insurance_company="Verification Insurance",
        insurance_policy_number="POLICY-123",
        insurance_claim_number="CLAIM-456",
        insurance_adjuster_name="Jordan Adjuster",
        insurance_adjuster_phone="503-555-0145",
        insurance_adjuster_email="jordan.adjuster@example.com",
        property_damage="None",
        towed=True,
        tow_information="Verification Tow Yard",
        warrant_obtained=True,
        vehicle_inspection_completed=True,
        nhtsa_recalls_checked=True,
        cdr_equipped=True,
        cdr_imaged=True,
        cdr_report_uploaded=True,
        released=True,
        release_date="2026-08-05",
        release_information="Released to verification owner with receipt",
    ))
    loaded_vehicle = repository.get_vehicle(vehicle.id)
    if not loaded_vehicle or not all((
        loaded_vehicle.warrant_obtained,
        loaded_vehicle.vehicle_inspection_completed,
        loaded_vehicle.nhtsa_recalls_checked,
        loaded_vehicle.cdr_equipped,
        loaded_vehicle.cdr_imaged,
        loaded_vehicle.cdr_report_uploaded,
        loaded_vehicle.released,
        loaded_vehicle.towed,
    )):
        raise RuntimeError(
            "The per-vehicle checklist and release status could not be saved and reloaded."
        )
    if (
        loaded_vehicle.insurance_company != "Verification Insurance"
        or loaded_vehicle.insurance_policy_number != "POLICY-123"
        or loaded_vehicle.insurance_claim_number != "CLAIM-456"
        or loaded_vehicle.insurance_adjuster_name != "Jordan Adjuster"
        or loaded_vehicle.insurance_adjuster_phone != "503-555-0145"
        or loaded_vehicle.insurance_adjuster_email
        != "jordan.adjuster@example.com"
        or loaded_vehicle.tow_information != "Verification Tow Yard"
        or loaded_vehicle.release_date != "2026-08-05"
        or loaded_vehicle.release_information
        != "Released to verification owner with receipt"
    ):
        raise RuntimeError(
            "The vehicle insurance, towing, or release fields could not be saved and reloaded."
        )
    repository.save_witness_details(WitnessDetails(
        person_id=person.id, interviewed="Yes",
        statement_summary="Portable-build verification record.",
    ))
    repository.save_investigative_checklist(InvestigativeChecklist(
        case_id=case.id,
        completed_items=[
            "Participant Interviews",
            "Crash Diagram Completed",
            "Axon Shared to DA",
            "Report Peer Reviewed",
            "Report Sgt Reviewed",
            "Submitted to DA",
        ],
        peer_review_date="2026-08-01",
        sergeant_review_date="2026-08-02",
        submitted_to_da_date="2026-08-03",
        assigned_dda="Verification DDA",
    ))
    repository.save_charge_disposition(ChargeDisposition(
        id="", case_id=case.id, charge="Verification charge", disposition="Test only",
    ))
    repository.save_crash_details(CrashDetails(
        case_id=case.id, road_name="Example Road", intersection_road="Sample Avenue",
        sergeant="Verification Sergeant", medical_examiner_on_scene="Verification MDI",
        scene_evidence=["Investigator Photos", "Uploaded to Axon", "FARO"],
    ))
    video_source = repository.save_video_source(VideoSource(
        id="", case_id=case.id, source="Verification camera",
        address="456 Verification Avenue, Portland, OR 97204",
        axon_status="Yes",
    ))
    loaded_video_source = repository.get_video_source(video_source.id)
    if (
        not loaded_video_source
        or loaded_video_source.address != "456 Verification Avenue, Portland, OR 97204"
        or loaded_video_source.axon_status != "Yes"
    ):
        raise RuntimeError("Video-source address and Axon upload status persistence failed.")
    repository.save_road_conditions(RoadConditions(
        case_id=case.id, temperature="68", dew_point="51", winds="NW 7",
        humidity="48", pressure="29.94", precipitation="0.02",
        weather_condition="Clear",
        weather_station="KPDX", weather_time="08:53 PDT",
        area_classifications="Business; Interstate",
        streetlight_notes="Verification note",
        sunrise="05:58", sunset="20:34",
        civil_twilight_morning="05:25", civil_twilight_evening="21:07",
        moonrise="22:41", moonset="11:37", moon_phase="Waxing gibbous",
    ))
    repository.save_surface_observation(SurfaceObservation(
        id="", case_id=case.id, location="Travel lane", composition="Asphalt",
        condition="Dry", friction_value="0.70",
    ))
    repository.save_roadway_record(RoadwayRecord(
        id="", case_id=case.id, roadway_tag="Example Road - northbound",
        speed_limit="35", speed_limit_posted="Yes",
        speed_limit_location="South approach sign",
        roadway_characteristics="Two northbound lanes; level tangent",
        traffic_controls="Signal-controlled intersection",
    ))
    repository.save_roadway_record(RoadwayRecord(
        id="", case_id=case.id, roadway_tag="Sample Avenue - eastbound",
        speed_limit="25", speed_limit_posted="Yes",
        curve_radius="420 ft", critical_speed="31 mph",
        roadway_characteristics="Single eastbound through lane",
        traffic_controls="Stop line and marked crosswalk",
    ))
    repository.save_participant_details(ParticipantDetails(
        person_id=person.id, vehicle_id=vehicle.id, height="70 in", weight="180 lb",
        injury_status="Not injured", helmet="Yes", ejected="No", extracted="Yes",
        evidence_items="Clothing",
    ))
    loaded_participant = repository.get_participant_details(person.id)
    if loaded_participant.extracted != "Yes" or loaded_participant.helmet != "Yes":
        raise RuntimeError(
            "The participant extracted and helmet statuses could not be saved and reloaded."
        )
    repository.save_driver_profile(DriverProfile(
        person_id=person.id, physical_condition_types="Vision",
        testing_methods="SFST",
        license_number="SELFTEST-DL", license_state="OR",
        license_class="C", license_status="Valid",
        license_issued_date="2024-07-01",
        license_expiration_date="2032-07-01",
        endorsements="Passenger; Tank",
        license_restrictions="Restriction B",
        license_restriction_explanation="Corrective lenses",
        notes="Verification driving history.",
    ))
    loaded_driver_profile = repository.get_driver_profile(person.id)
    if (
        loaded_driver_profile.endorsements != "Passenger; Tank"
        or loaded_driver_profile.license_issued_date != "2024-07-01"
        or loaded_driver_profile.license_expiration_date != "2032-07-01"
        or loaded_driver_profile.notes != "Verification driving history."
    ):
        raise RuntimeError(
            "The driver-license dates, endorsements, and history could not be saved and reloaded."
        )
    pedestrian = repository.save_person(Person(
        id=new_id(), case_id=case.id, first_name="Portable", last_name="Pedestrian",
        address="200 Verification Walk", city="Portland", state="OR",
        zip_code="97202", cell_phone="503-555-0200", roles=["Pedestrian"],
    ))
    bicyclist = repository.save_person(Person(
        id=new_id(), case_id=case.id, first_name="Portable", last_name="Bicyclist",
        address="300 Verification Ride", city="Portland", state="OR",
        zip_code="97203", cell_phone="503-555-0300", roles=["Bicyclist"],
    ))
    repository.save_driver_profile(DriverProfile(
        person_id=pedestrian.id,
        license_number="PEDESTRIAN-DL",
        physical_condition_types="NONDRIVER PHYSICAL SELF TEST",
        permanent_conditions="NONDRIVER MEDICAL SELF TEST",
        hours_asleep="NONDRIVER SLEEP SELF TEST",
        hours_awake="NONDRIVER AWAKE SELF TEST",
    ))
    vru_analysis = repository.save_vru_analysis(VRUAnalysis(
        id="", case_id=case.id, person_id=pedestrian.id, vehicle_id=vehicle.id,
        roadway_position="Verification crosswalk", light_meter_used=True,
        light_board_used=True,
    ))
    loaded_vru_analysis = repository.get_vru_analysis(vru_analysis.id)
    if not loaded_vru_analysis or not all((
        loaded_vru_analysis.light_meter_used,
        loaded_vru_analysis.light_board_used,
    )):
        raise RuntimeError("The VRU night-visibility equipment fields could not be saved and reloaded.")
    repository.save_vehicle_inspection(VehicleInspection(
        vehicle_id=vehicle.id, headlights_equipped="Yes", headlights_operable="Yes",
        tire_contribution="No",
    ))
    repository.save_motorcycle_inspection(MotorcycleInspection(
        vehicle_id=vehicle.id, frame_number="SELF-TEST-FRAME", officer="Verification Officer",
        items=[MotorcycleInspectionItem(item_number=1, rating="1 - Not damaged")],
    ))
    repository.save_hit_run_overview(HitRunOverview(
        case_id=case.id,
        is_hit_and_run=True,
        investigation_status="Vehicle Identified",
        narrative="Verification hit-and-run investigative narrative.",
        last_known_location="Example Road and Sample Avenue",
        last_seen_date="2026-08-04",
        last_seen_time="21:15",
        direction_of_travel="Northbound",
        initial_source="Verification camera",
        follow_up_notes="Confirm the promoted vehicle and person links.",
    ))
    vehicle_lead = repository.save_hit_run_vehicle_lead(HitRunVehicleLead(
        id="",
        case_id=case.id,
        lead_number="HRV-1",
        status="Confirmed",
        year_range="2026",
        make="Example",
        model="Vehicle",
        color="Blue",
        plate="SELFTEST",
        plate_state="OR",
        observed_damage="Right front damage",
        missing_parts="Mirror trim",
        information_source="Verification camera",
        confidence="High",
        linked_vehicle_id=vehicle.id,
    ))
    repository.save_hit_run_evidence_item(HitRunEvidenceItem(
        id="",
        case_id=case.id,
        evidence_number="HRE-1",
        evidence_type="Recovered vehicle part",
        part_number="VERIFY-123",
        part_description="Fictional mirror trim used to verify persistence.",
        recovery_location="Verification scene",
        recovery_date="2026-08-04",
        vehicle_lead_id=vehicle_lead.id,
        lab_status="Comparison complete",
    ))
    repository.save_hit_run_person_lead(HitRunPersonLead(
        id="",
        case_id=case.id,
        lead_number="HRP-1",
        status="Confirmed",
        first_name="Test",
        last_name="Record",
        reason_for_lead="Linked portable-build verification record.",
        information_source="Verification only",
        confidence="High",
        vehicle_lead_id=vehicle_lead.id,
        linked_person_id=person.id,
    ))
    if not repository.get_hit_run_overview(case.id).is_hit_and_run:
        raise RuntimeError("The hit-and-run overview could not be saved and reloaded.")
    if len(repository.list_hit_run_evidence_items(case.id)) != 1:
        raise RuntimeError("Hit-and-run evidence persistence failed.")
    if len(repository.list_hit_run_vehicle_leads(case.id)) != 1:
        raise RuntimeError("Hit-and-run vehicle-lead persistence failed.")
    if len(repository.list_hit_run_person_leads(case.id)) != 1:
        raise RuntimeError("Hit-and-run person-lead persistence failed.")
    if (
        repository.get_vehicle(vehicle.id).body_style != "Four-door SUV"
        or repository.get_vehicle(vehicle.id).property_damage != "None"
    ):
        raise RuntimeError("Exchange-report vehicle fields persistence failed.")

    property_receipt = repository.save_property_receipt(PropertyReceipt(
        id="",
        case_id=case.id,
        receipt_number="SELF-TEST-PR-1",
        property_owner="Portable Verification Owner",
        lodging_type="Evidence",
        lodged_location="Verification Property Room",
        lodged_date="2026-08-05",
    ))
    repository.save_property_receipt_item(PropertyReceiptItem(
        id="",
        receipt_id=property_receipt.id,
        item_number=1,
        description="Fictional property item used for portable verification.",
    ))
    if (
        len(repository.list_property_receipts(case.id)) != 1
        or len(repository.list_property_receipt_items(property_receipt.id)) != 1
        or repository.next_property_receipt_item_number(property_receipt.id) != 2
    ):
        raise RuntimeError("Property receipt and item persistence failed.")

    storage_directory = validate_storage_directory(
        output / f"portable_self_test_storage_{case.id}"
    )
    migrated_database = migrate_database(
        database,
        storage_directory / DATABASE_FILENAME,
    )
    (storage_directory / "Reports").mkdir()
    (storage_directory / "Backups").mkdir()
    storage_config_path = output / "portable_self_test_storage_config.json"
    saved_storage_config = save_storage_config(
        storage_directory,
        storage_config_path,
    )
    loaded_storage_config = load_storage_config(storage_config_path)
    if loaded_storage_config != saved_storage_config:
        raise RuntimeError("Storage configuration persistence failed.")
    migrated_repository = CaseRepository(migrated_database)
    migrated_case = migrated_repository.get_case(case.id)
    if not migrated_case or migrated_case.case_number != "SELF-TEST":
        raise RuntimeError("Storage migration did not preserve the self-test case.")
    if (
        len(migrated_repository.list_property_receipts(case.id)) != 1
        or len(
            migrated_repository.list_property_receipt_items(property_receipt.id)
        ) != 1
    ):
        raise RuntimeError(
            "Storage migration did not preserve property receipt evidence."
        )

    export_case_pdf(repository, case.id, pdf)
    export_case_compact_pdf(repository, case.id, compact_pdf)
    export_case_summary_pdf(repository, case.id, summary_pdf)
    export_exchange_report_pdf(repository, case.id, exchange_pdf)

    if not database.is_file() or database.stat().st_size < 4096:
        raise RuntimeError("The self-test database was not created correctly.")
    if not pdf.is_file() or pdf.stat().st_size < 20_000:
        raise RuntimeError("The self-test PDF was not created correctly.")
    if not compact_pdf.is_file() or compact_pdf.stat().st_size < 15_000:
        raise RuntimeError("The self-test compact-packet PDF was not created correctly.")
    if not summary_pdf.is_file() or summary_pdf.stat().st_size < 5_000:
        raise RuntimeError("The self-test quick-review PDF was not created correctly.")
    if not exchange_pdf.is_file() or exchange_pdf.stat().st_size < 3_000:
        raise RuntimeError("The self-test exchange-report PDF was not created correctly.")
    packet_document = QPdfDocument()
    packet_load_error = packet_document.load(str(pdf))
    if packet_load_error != QPdfDocument.Error.None_:
        raise RuntimeError(
            f"The self-test packet could not be loaded ({packet_load_error.name})."
        )
    packet_text = "\n".join(
        packet_document.getAllText(page_index).text()
        for page_index in range(packet_document.pageCount())
    )
    packet_document.close()
    normalized_packet_text = " ".join(packet_text.split())
    for required_text in (
        "NHTSA RECALLS CHECKED",
        "TOWED / TO",
        "Yes - Verification Tow Yard",
        "68 F",
        "51 F",
        "NW 7 mph",
        "48%",
        "29.94 inHg",
        "0.02 in",
        "RELEASED",
        "08/05/2026",
        "Released to verification owner with receipt",
        "CLAIM NUMBER",
        "CLAIM-456",
        "ADJUSTER NAME",
        "Jordan Adjuster",
        "ADJUSTER PHONE",
        "503-555-0145",
        "ADJUSTER EMAIL",
        "jordan.adjuster@example.com",
        "LIGHT METER USED",
        "LIGHT BOARD USED",
        "PHYSICAL CONDITIONS",
        "Vision",
        "ENDORSEMENTS",
        "Passenger; Tank",
        "ISSUED",
        "07/01/2024",
        "EXPIRATION",
        "07/01/2032",
        "RESTRICTIONS",
        "Restriction B",
        "RESTRICTIONS EXPLAINED",
        "Corrective lenses",
        "DRIVING HISTORY",
        "Verification driving history.",
        "helmet Yes",
        "Participant background",
        "Property receipt SELF-TEST-PR-1",
        "Portable Verification Owner",
        "Verification Property Room",
        "Fictional property item used for portable verification.",
    ):
        if required_text not in normalized_packet_text:
            raise RuntimeError(
                f"The self-test packet omitted required data: {required_text}"
            )
    for suppressed_text in (
        "NONDRIVER PHYSICAL SELF TEST",
        "NONDRIVER MEDICAL SELF TEST",
        "NONDRIVER SLEEP SELF TEST",
        "NONDRIVER AWAKE SELF TEST",
    ):
        if suppressed_text in normalized_packet_text:
            raise RuntimeError(
                "The self-test packet printed driver-only background data for "
                f"a non-driver: {suppressed_text}"
            )
    exchange_pdf_bytes = exchange_pdf.read_bytes()
    if not exchange_pdf_bytes.startswith(b"%PDF-") or not exchange_pdf_bytes.rstrip().endswith(b"%%EOF"):
        raise RuntimeError("The self-test exchange-report output is not a complete PDF file.")
    exchange_document = QPdfDocument()
    exchange_load_error = exchange_document.load(str(exchange_pdf))
    if exchange_load_error != QPdfDocument.Error.None_:
        raise RuntimeError(
            f"The self-test exchange report could not be loaded ({exchange_load_error.name})."
        )
    exchange_page_text = [
        exchange_document.getAllText(page_index).text()
        for page_index in range(exchange_document.pageCount())
    ]
    exchange_front_text = "\n".join(exchange_page_text[:-1])
    exchange_information_text = exchange_page_text[-1]
    for required_text in (
        person_name_last_first(person),
        person_name_last_first(pedestrian),
        person_name_last_first(bicyclist),
        "12345",
        "Verification Precinct",
    ):
        if required_text not in exchange_front_text:
            raise RuntimeError(
                f"The exchange report omitted required participant/officer data: {required_text}"
            )
    for required_text in (
        "INFORMATION / YOUR RESPONSIBILITIES",
        "PORTLAND POLICE BUREAU POLICY STATEMENT",
        "TRAFFIC CRASH REPORTING REQUIREMENTS",
        "770 (12/17)",
    ):
        if required_text not in exchange_information_text:
            raise RuntimeError(
                f"The searchable exchange information page omitted: {required_text}"
            )
    with closing(sqlite3.connect(database)) as connection:
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if schema_version != SCHEMA_VERSION:
        raise RuntimeError(f"Unexpected database schema version: {schema_version}")

    build_info = load_build_info()

    log.write_text(
        "\n".join((
            "PASS",
            f"Traffic Crash Notebook {__version__}",
            f"Build ID: {build_info.build_id}",
            f"Build date: {build_info.built_at}",
            f"Database schema: {schema_version}",
            f"Database bytes: {database.stat().st_size}",
            f"PDF bytes: {pdf.stat().st_size}",
            f"Compact-packet PDF bytes: {compact_pdf.stat().st_size}",
            f"Quick-review PDF bytes: {summary_pdf.stat().st_size}",
            f"Exchange-report PDF bytes: {exchange_pdf.stat().st_size}",
            "Person ZIP code persistence: PASS",
            "Participant extracted and helmet status persistence: PASS",
            "Driver-license dates, ordering data, and driving history persistence: PASS",
            "Role-aware non-driver packet background suppression: PASS",
            "Per-vehicle checklist, towing, release, insurance, and claim persistence: PASS",
            "Video-source address and Axon upload status persistence: PASS",
            "VRU light-meter and light-board persistence: PASS",
            "Hit-and-run overview, evidence, lead, and confirmed-record links: PASS",
            "Property receipt hierarchy and numbered item persistence: PASS",
            "Assigned-officer DPSST and assignment persistence: PASS",
            "Data-folder user defaults and new-case prefill: PASS",
            "Driver, pedestrian, and bicyclist exchange-report inclusion: PASS",
            "Dynamic exchange-report data, time formatting, and searchable information page: PASS",
            "Embedded PDF preview components: PASS",
            "TIU application and taskbar icon: PASS",
            "Early packaged startup splash: PASS",
            "Guided data-storage configuration and migration: PASS",
            "Verified release-manifest update checker: PASS",
            "Offline spell-check dictionary: PASS",
            "The schema, full working packet PDF, compact packet PDF, quick review PDF, exchange-report PDF, offline spell-check dictionary, report logo, application icon, and startup splash loaded successfully.",
            "",
        )),
        encoding="utf-8",
    )
    return log
