from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, TypeVar

from .models import (
    CaseTask,
    ChargeDisposition,
    ChronologyEntry,
    ContactRelationship,
    CrashCase,
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
    ParticipantDetails,
    Person,
    PropertyReceipt,
    PropertyReceiptItem,
    RoadConditions,
    RoadwayRecord,
    MotorcycleInspection,
    MotorcycleInspectionItem,
    SurfaceObservation,
    TireInspection,
    UserDefaults,
    VRUAnalysis,
    Vehicle,
    VehicleInspection,
    VEHICLE_WORKFLOW_FIELDS,
    VideoSource,
    WitnessDetails,
    normalize_scene_evidence_methods,
)


T = TypeVar("T")


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA_VERSION = 33


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user_defaults (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_name TEXT NOT NULL DEFAULT '',
    dpsst TEXT NOT NULL DEFAULT '',
    assignment TEXT NOT NULL DEFAULT '',
    auto_check_updates INTEGER NOT NULL DEFAULT 1,
    last_update_check TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    case_number TEXT NOT NULL DEFAULT '',
    crash_date TEXT NOT NULL DEFAULT '',
    crash_time TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    investigator TEXT NOT NULL DEFAULT '',
    assigned_officer_dpsst TEXT NOT NULL DEFAULT '',
    assignment TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Active',
    first_harmful_event TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL DEFAULT '',
    middle_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    dob TEXT NOT NULL DEFAULT '',
    sex TEXT NOT NULL DEFAULT '',
    race TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    cell_phone TEXT NOT NULL DEFAULT '', home_phone TEXT NOT NULL DEFAULT '',
    work_phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
    zip_code TEXT NOT NULL DEFAULT '',
    occupation TEXT NOT NULL DEFAULT '', business_address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_roles (
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (person_id, role)
);

CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    vehicle_number TEXT NOT NULL DEFAULT '',
    year TEXT NOT NULL DEFAULT '',
    make TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    trim TEXT NOT NULL DEFAULT '',
    body_style TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    vehicle_weight TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT '',
    tire_size TEXT NOT NULL DEFAULT '',
    vin TEXT NOT NULL DEFAULT '',
    plate TEXT NOT NULL DEFAULT '',
    plate_state TEXT NOT NULL DEFAULT '',
    owner_person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    driver_person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    insurance TEXT NOT NULL DEFAULT '',
    insurance_company TEXT NOT NULL DEFAULT '',
    insurance_policy_number TEXT NOT NULL DEFAULT '',
    insurance_claim_number TEXT NOT NULL DEFAULT '',
    insurance_adjuster_name TEXT NOT NULL DEFAULT '',
    insurance_adjuster_phone TEXT NOT NULL DEFAULT '',
    insurance_adjuster_email TEXT NOT NULL DEFAULT '',
    property_damage TEXT NOT NULL DEFAULT '',
    towed INTEGER NOT NULL DEFAULT 0,
    tow_information TEXT NOT NULL DEFAULT '',
    edr_status TEXT NOT NULL DEFAULT '',
    warrant_obtained INTEGER NOT NULL DEFAULT 0,
    vehicle_inspection_completed INTEGER NOT NULL DEFAULT 0,
    nhtsa_recalls_checked INTEGER NOT NULL DEFAULT 0,
    cdr_equipped INTEGER NOT NULL DEFAULT 0,
    cdr_imaged INTEGER NOT NULL DEFAULT 0,
    cdr_report_uploaded INTEGER NOT NULL DEFAULT 0,
    released INTEGER NOT NULL DEFAULT 0,
    release_date TEXT NOT NULL DEFAULT '',
    release_information TEXT NOT NULL DEFAULT '',
    damage_notes TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hit_run_overviews (
    case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    is_hit_and_run INTEGER NOT NULL DEFAULT 0,
    investigation_status TEXT NOT NULL DEFAULT 'Active',
    narrative TEXT NOT NULL DEFAULT '',
    last_known_location TEXT NOT NULL DEFAULT '',
    last_seen_date TEXT NOT NULL DEFAULT '',
    last_seen_time TEXT NOT NULL DEFAULT '',
    direction_of_travel TEXT NOT NULL DEFAULT '',
    initial_source TEXT NOT NULL DEFAULT '',
    follow_up_notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hit_run_vehicle_leads (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lead_number TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Possible',
    year_range TEXT NOT NULL DEFAULT '',
    make TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    body_style TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    plate TEXT NOT NULL DEFAULT '',
    plate_state TEXT NOT NULL DEFAULT '',
    vin TEXT NOT NULL DEFAULT '',
    distinguishing_features TEXT NOT NULL DEFAULT '',
    observed_damage TEXT NOT NULL DEFAULT '',
    missing_parts TEXT NOT NULL DEFAULT '',
    last_seen_location TEXT NOT NULL DEFAULT '',
    last_seen_date TEXT NOT NULL DEFAULT '',
    last_seen_time TEXT NOT NULL DEFAULT '',
    direction_of_travel TEXT NOT NULL DEFAULT '',
    information_source TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'Unknown',
    elimination_reason TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    linked_vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hit_run_evidence_items (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_number TEXT NOT NULL DEFAULT '',
    evidence_type TEXT NOT NULL DEFAULT '',
    part_number TEXT NOT NULL DEFAULT '',
    part_description TEXT NOT NULL DEFAULT '',
    manufacturer_markings TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    material TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL DEFAULT '',
    damage_paint_transfer TEXT NOT NULL DEFAULT '',
    recovery_location TEXT NOT NULL DEFAULT '',
    recovery_date TEXT NOT NULL DEFAULT '',
    recovery_time TEXT NOT NULL DEFAULT '',
    recovered_by TEXT NOT NULL DEFAULT '',
    vehicle_fitment TEXT NOT NULL DEFAULT '',
    lab_status TEXT NOT NULL DEFAULT '',
    vehicle_lead_id TEXT REFERENCES hit_run_vehicle_leads(id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hit_run_person_leads (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lead_number TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Possible',
    first_name TEXT NOT NULL DEFAULT '',
    middle_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    alias TEXT NOT NULL DEFAULT '',
    sex TEXT NOT NULL DEFAULT '',
    race TEXT NOT NULL DEFAULT '',
    estimated_age TEXT NOT NULL DEFAULT '',
    height TEXT NOT NULL DEFAULT '',
    weight_build TEXT NOT NULL DEFAULT '',
    hair TEXT NOT NULL DEFAULT '',
    eyes TEXT NOT NULL DEFAULT '',
    facial_hair TEXT NOT NULL DEFAULT '',
    clothing TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    zip_code TEXT NOT NULL DEFAULT '',
    cell_phone TEXT NOT NULL DEFAULT '',
    home_phone TEXT NOT NULL DEFAULT '',
    work_phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    driver_license_number TEXT NOT NULL DEFAULT '',
    driver_license_state TEXT NOT NULL DEFAULT '',
    relationship_to_vehicle TEXT NOT NULL DEFAULT '',
    reason_for_lead TEXT NOT NULL DEFAULT '',
    information_source TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'Unknown',
    vehicle_lead_id TEXT REFERENCES hit_run_vehicle_leads(id) ON DELETE SET NULL,
    follow_up TEXT NOT NULL DEFAULT '',
    elimination_reason TEXT NOT NULL DEFAULT '',
    linked_person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chronology (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    event_date TEXT NOT NULL DEFAULT '',
    event_time TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'General',
    summary TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'General',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Open',
    due_date TEXT NOT NULL DEFAULT '',
    completed_date TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS road_conditions (
    case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    temperature TEXT NOT NULL DEFAULT '', dew_point TEXT NOT NULL DEFAULT '',
    winds TEXT NOT NULL DEFAULT '', humidity TEXT NOT NULL DEFAULT '',
    weather_condition TEXT NOT NULL DEFAULT '', pressure TEXT NOT NULL DEFAULT '',
    precipitation TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL DEFAULT '',
    weather_station TEXT NOT NULL DEFAULT '',
    weather_time TEXT NOT NULL DEFAULT '',
    other_weather TEXT NOT NULL DEFAULT '', surface_composition TEXT NOT NULL DEFAULT '',
    surface_condition TEXT NOT NULL DEFAULT '', friction_value TEXT NOT NULL DEFAULT '',
    lighting_conditions TEXT NOT NULL DEFAULT '', sunrise TEXT NOT NULL DEFAULT '',
    sunset TEXT NOT NULL DEFAULT '', civil_twilight_morning TEXT NOT NULL DEFAULT '',
    civil_twilight_evening TEXT NOT NULL DEFAULT '', moonrise TEXT NOT NULL DEFAULT '',
    moonset TEXT NOT NULL DEFAULT '', moon_phase TEXT NOT NULL DEFAULT '',
    streetlights_working TEXT NOT NULL DEFAULT 'Unknown',
    streetlight_notes TEXT NOT NULL DEFAULT '',
    visual_obstructions TEXT NOT NULL DEFAULT '', area_type TEXT NOT NULL DEFAULT '',
    area_classifications TEXT NOT NULL DEFAULT '',
    speed_limit TEXT NOT NULL DEFAULT '', speed_limit_posted TEXT NOT NULL DEFAULT 'Unknown',
    speed_limit_location TEXT NOT NULL DEFAULT '', curve_radius TEXT NOT NULL DEFAULT '',
    chord TEXT NOT NULL DEFAULT '', middle_ordinate TEXT NOT NULL DEFAULT '',
    critical_speed TEXT NOT NULL DEFAULT '', roadway_characteristics TEXT NOT NULL DEFAULT '',
    traffic_controls TEXT NOT NULL DEFAULT '', initial_point_of_collision TEXT NOT NULL DEFAULT '',
    skid_test_notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participant_details (
    person_id TEXT PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    occupant_position TEXT NOT NULL DEFAULT '', injury_status TEXT NOT NULL DEFAULT '',
    transported TEXT NOT NULL DEFAULT 'Unknown', transported_to TEXT NOT NULL DEFAULT '',
    medical_records_status TEXT NOT NULL DEFAULT '', hospital TEXT NOT NULL DEFAULT '',
    height TEXT NOT NULL DEFAULT '', weight TEXT NOT NULL DEFAULT '',
    seatbelt_installed TEXT NOT NULL DEFAULT 'Unknown',
    seatbelt_used TEXT NOT NULL DEFAULT 'Unknown', airbag_deployed TEXT NOT NULL DEFAULT 'Unknown',
    helmet TEXT NOT NULL DEFAULT 'Not Applicable',
    ejected TEXT NOT NULL DEFAULT 'Unknown', extracted TEXT NOT NULL DEFAULT 'Unknown',
    autopsy_performed TEXT NOT NULL DEFAULT 'Unknown',
    autopsy_by TEXT NOT NULL DEFAULT '', date_of_death TEXT NOT NULL DEFAULT '',
    cause_of_death TEXT NOT NULL DEFAULT '', next_of_kin_notified TEXT NOT NULL DEFAULT 'Unknown',
    next_of_kin_notified_by TEXT NOT NULL DEFAULT '', injuries TEXT NOT NULL DEFAULT '',
    injury_codes TEXT NOT NULL DEFAULT '', evidence_obtained TEXT NOT NULL DEFAULT '',
    evidence_items TEXT NOT NULL DEFAULT '', lab_information TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_profiles (
    person_id TEXT PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    trip_from TEXT NOT NULL DEFAULT '', trip_to TEXT NOT NULL DEFAULT '',
    trip_purpose TEXT NOT NULL DEFAULT '', last_stop_arrival TEXT NOT NULL DEFAULT '',
    last_stop_departed TEXT NOT NULL DEFAULT '', permanent_conditions TEXT NOT NULL DEFAULT '',
    temporary_conditions TEXT NOT NULL DEFAULT '', physical_condition_types TEXT NOT NULL DEFAULT '',
    impairment_status TEXT NOT NULL DEFAULT 'Unknown',
    bac TEXT NOT NULL DEFAULT '', testing TEXT NOT NULL DEFAULT '',
    testing_methods TEXT NOT NULL DEFAULT '',
    controlled_substances TEXT NOT NULL DEFAULT '', impairment_notes TEXT NOT NULL DEFAULT '',
    sleep_time TEXT NOT NULL DEFAULT '', wake_time TEXT NOT NULL DEFAULT '',
    hours_asleep TEXT NOT NULL DEFAULT '', hours_awake TEXT NOT NULL DEFAULT '',
    work_start TEXT NOT NULL DEFAULT '', work_end TEXT NOT NULL DEFAULT '',
    hours_worked TEXT NOT NULL DEFAULT '', type_of_work TEXT NOT NULL DEFAULT '',
    familiar_with_road TEXT NOT NULL DEFAULT 'Unknown',
    familiar_with_vehicle TEXT NOT NULL DEFAULT 'Unknown',
    years_driving TEXT NOT NULL DEFAULT '', previous_collisions TEXT NOT NULL DEFAULT '',
    previous_traffic_homicide TEXT NOT NULL DEFAULT '', license_restrictions TEXT NOT NULL DEFAULT '',
    license_restricted TEXT NOT NULL DEFAULT 'Unknown',
    license_restriction_explanation TEXT NOT NULL DEFAULT '',
    license_number TEXT NOT NULL DEFAULT '', license_state TEXT NOT NULL DEFAULT '',
    license_class TEXT NOT NULL DEFAULT '', license_status TEXT NOT NULL DEFAULT '',
    license_issued_date TEXT NOT NULL DEFAULT '',
    license_expiration_date TEXT NOT NULL DEFAULT '', endorsements TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicle_inspections (
    vehicle_id TEXT PRIMARY KEY REFERENCES vehicles(id) ON DELETE CASCADE,
    mileage TEXT NOT NULL DEFAULT '', transmission TEXT NOT NULL DEFAULT '',
    gear TEXT NOT NULL DEFAULT '', steering TEXT NOT NULL DEFAULT '',
    registered_weight TEXT NOT NULL DEFAULT '', curb_weight TEXT NOT NULL DEFAULT '',
    measured_weight TEXT NOT NULL DEFAULT '', front_brakes TEXT NOT NULL DEFAULT '',
    rear_brakes TEXT NOT NULL DEFAULT '', brake_system TEXT NOT NULL DEFAULT '',
    lighting_electrical TEXT NOT NULL DEFAULT '', body_equipment TEXT NOT NULL DEFAULT '',
    safety_systems TEXT NOT NULL DEFAULT '', nicb_status TEXT NOT NULL DEFAULT '',
    recall_status TEXT NOT NULL DEFAULT '', vin_decode_status TEXT NOT NULL DEFAULT '',
    headlights_equipped TEXT NOT NULL DEFAULT 'Unknown', headlights_operable TEXT NOT NULL DEFAULT 'Unknown',
    taillights_equipped TEXT NOT NULL DEFAULT 'Unknown', taillights_operable TEXT NOT NULL DEFAULT 'Unknown',
    tag_lights_equipped TEXT NOT NULL DEFAULT 'Unknown', tag_lights_operable TEXT NOT NULL DEFAULT 'Unknown',
    brake_lights_equipped TEXT NOT NULL DEFAULT 'Unknown', brake_lights_operable TEXT NOT NULL DEFAULT 'Unknown',
    turn_signals_equipped TEXT NOT NULL DEFAULT 'Unknown', turn_signals_operable TEXT NOT NULL DEFAULT 'Unknown',
    parking_lamps_equipped TEXT NOT NULL DEFAULT 'Unknown', parking_lamps_operable TEXT NOT NULL DEFAULT 'Unknown',
    other_lights_equipped TEXT NOT NULL DEFAULT 'Unknown', other_lights_operable TEXT NOT NULL DEFAULT 'Unknown',
    front_wipers_equipped TEXT NOT NULL DEFAULT 'Unknown', front_wipers_operable TEXT NOT NULL DEFAULT 'Unknown',
    rear_wipers_equipped TEXT NOT NULL DEFAULT 'Unknown', rear_wipers_operable TEXT NOT NULL DEFAULT 'Unknown',
    horn_equipped TEXT NOT NULL DEFAULT 'Unknown', horn_operable TEXT NOT NULL DEFAULT 'Unknown',
    headlight_switch_position TEXT NOT NULL DEFAULT '', wiper_switch_position TEXT NOT NULL DEFAULT '',
    ignition_position TEXT NOT NULL DEFAULT '', radio_position TEXT NOT NULL DEFAULT '',
    heater_position TEXT NOT NULL DEFAULT '', headlamp_lens_condition TEXT NOT NULL DEFAULT '',
    safety_glass_condition TEXT NOT NULL DEFAULT '', inside_mirror TEXT NOT NULL DEFAULT '',
    outside_mirrors TEXT NOT NULL DEFAULT '', window_positions TEXT NOT NULL DEFAULT '',
    seatbelts_equipped TEXT NOT NULL DEFAULT 'Unknown',
    shoulder_harnesses_equipped TEXT NOT NULL DEFAULT 'Unknown', airbag_status TEXT NOT NULL DEFAULT '',
    body_interior_condition TEXT NOT NULL DEFAULT '', body_exterior_condition TEXT NOT NULL DEFAULT '',
    seatbelt_loading TEXT NOT NULL DEFAULT 'Unknown', steering_wheel_damage TEXT NOT NULL DEFAULT 'Unknown',
    device_observations TEXT NOT NULL DEFAULT '', tire_contribution TEXT NOT NULL DEFAULT 'Unknown',
    tire_contribution_explanation TEXT NOT NULL DEFAULT '',
    tire_notes TEXT NOT NULL DEFAULT '', inspection_notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tire_inspections (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    position TEXT NOT NULL DEFAULT '', make TEXT NOT NULL DEFAULT '',
    design TEXT NOT NULL DEFAULT '', size TEXT NOT NULL DEFAULT '',
    pressure TEXT NOT NULL DEFAULT '', tread_inside TEXT NOT NULL DEFAULT '',
    tread_middle TEXT NOT NULL DEFAULT '', tread_outside TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS witness_details (
    person_id TEXT PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    interviewed TEXT NOT NULL DEFAULT 'Unknown', interview_date TEXT NOT NULL DEFAULT '',
    interviewer TEXT NOT NULL DEFAULT '', significance TEXT NOT NULL DEFAULT '',
    statement_summary TEXT NOT NULL DEFAULT '', credibility_notes TEXT NOT NULL DEFAULT '',
    follow_up TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_relationships (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL DEFAULT '',
    subject_person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    contact_person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    contact_name TEXT NOT NULL DEFAULT '', organization TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', cell_phone TEXT NOT NULL DEFAULT '',
    home_phone TEXT NOT NULL DEFAULT '', work_phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vru_analyses (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    upper_clothing TEXT NOT NULL DEFAULT '', lower_clothing TEXT NOT NULL DEFAULT '',
    roadway_position TEXT NOT NULL DEFAULT '', movement_at_impact TEXT NOT NULL DEFAULT '',
    projection_profile TEXT NOT NULL DEFAULT '', projection_classifications TEXT NOT NULL DEFAULT '',
    sightlines TEXT NOT NULL DEFAULT '',
    driver_thought_process TEXT NOT NULL DEFAULT '', driver_impairment TEXT NOT NULL DEFAULT 'Unknown',
    driver_sleep_information TEXT NOT NULL DEFAULT '', vru_impairment TEXT NOT NULL DEFAULT 'Unknown',
    vru_impairment_notes TEXT NOT NULL DEFAULT '', impact_location_on_vehicle TEXT NOT NULL DEFAULT '',
    vehicle_approach_speed TEXT NOT NULL DEFAULT '', vehicle_direction TEXT NOT NULL DEFAULT '',
    vru_approach_speed TEXT NOT NULL DEFAULT '', vru_direction TEXT NOT NULL DEFAULT '',
    person_throw_distance TEXT NOT NULL DEFAULT '', bicycle_throw_distance TEXT NOT NULL DEFAULT '',
    light_meter_used INTEGER NOT NULL DEFAULT 0, light_board_used INTEGER NOT NULL DEFAULT 0,
    night_test_parameters TEXT NOT NULL DEFAULT '', detection_distance TEXT NOT NULL DEFAULT '',
    distance_adjustment TEXT NOT NULL DEFAULT '', result_67_percent TEXT NOT NULL DEFAULT '',
    result_15_percentile TEXT NOT NULL DEFAULT '', prt_base TEXT NOT NULL DEFAULT '0.50',
    prt_expected TEXT NOT NULL DEFAULT '', prt_sun TEXT NOT NULL DEFAULT '',
    prt_offset TEXT NOT NULL DEFAULT '', prt_adjustment TEXT NOT NULL DEFAULT '',
    prt_total TEXT NOT NULL DEFAULT '', prt_justification TEXT NOT NULL DEFAULT '',
    prt_factors TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_references (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '', reference_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '', person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS diagram_records (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '', diagram_type TEXT NOT NULL DEFAULT 'Body',
    template_name TEXT NOT NULL DEFAULT 'body',
    person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
    vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    annotations_json TEXT NOT NULL DEFAULT '[]', notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigative_checklists (
    case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    completed_items_json TEXT NOT NULL DEFAULT '[]',
    peer_review_status TEXT NOT NULL DEFAULT 'Not Started',
    sergeant_review_status TEXT NOT NULL DEFAULT 'Not Started',
    submitted_to_da_status TEXT NOT NULL DEFAULT 'Not Started',
    peer_review_date TEXT NOT NULL DEFAULT '',
    sergeant_review_date TEXT NOT NULL DEFAULT '',
    submitted_to_da_date TEXT NOT NULL DEFAULT '',
    assigned_dda TEXT NOT NULL DEFAULT '',
    da_case_number TEXT NOT NULL DEFAULT '',
    court_case_number TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS property_receipts (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    receipt_number TEXT NOT NULL DEFAULT '',
    property_owner TEXT NOT NULL DEFAULT '',
    lodging_type TEXT NOT NULL DEFAULT 'Evidence',
    lodged_location TEXT NOT NULL DEFAULT '',
    lodged_date TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS property_receipt_items (
    id TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL REFERENCES property_receipts(id) ON DELETE CASCADE,
    item_number INTEGER NOT NULL DEFAULT 1 CHECK (item_number > 0),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (receipt_id, item_number)
);

CREATE TABLE IF NOT EXISTS charge_dispositions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    charge TEXT NOT NULL DEFAULT '', disposition TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crash_details (
    case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    nearest_city TEXT NOT NULL DEFAULT 'Portland', county TEXT NOT NULL DEFAULT 'Multnomah',
    outside_city_feet TEXT NOT NULL DEFAULT '', outside_city_miles TEXT NOT NULL DEFAULT '',
    outside_city_direction TEXT NOT NULL DEFAULT '', road_name TEXT NOT NULL DEFAULT '',
    intersection_road TEXT NOT NULL DEFAULT '', non_intersection_feet TEXT NOT NULL DEFAULT '',
    non_intersection_miles TEXT NOT NULL DEFAULT '', non_intersection_direction TEXT NOT NULL DEFAULT '',
    non_intersection_reference TEXT NOT NULL DEFAULT '', latitude TEXT NOT NULL DEFAULT '',
    longitude TEXT NOT NULL DEFAULT '', road_jurisdiction TEXT NOT NULL DEFAULT '',
    team_notified_date TEXT NOT NULL DEFAULT '', team_notified_time TEXT NOT NULL DEFAULT '',
    investigator_en_route TEXT NOT NULL DEFAULT '', investigator_arrival TEXT NOT NULL DEFAULT '',
    sergeant TEXT NOT NULL DEFAULT '', prosecutor_on_scene TEXT NOT NULL DEFAULT '',
    medical_examiner_on_scene TEXT NOT NULL DEFAULT '', criminalist_on_scene TEXT NOT NULL DEFAULT '',
    scene_evidence_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_report_details (
    case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    assisting_officer TEXT NOT NULL DEFAULT '',
    precinct TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_sources (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
    axon_status TEXT NOT NULL DEFAULT 'Unknown',
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS surface_observations (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    location TEXT NOT NULL DEFAULT '', composition TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT '', friction_value TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roadway_records (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    roadway_tag TEXT NOT NULL DEFAULT '', speed_limit TEXT NOT NULL DEFAULT '',
    speed_limit_posted TEXT NOT NULL DEFAULT 'Unknown',
    speed_limit_location TEXT NOT NULL DEFAULT '', curve_radius TEXT NOT NULL DEFAULT '',
    chord TEXT NOT NULL DEFAULT '', middle_ordinate TEXT NOT NULL DEFAULT '',
    critical_speed TEXT NOT NULL DEFAULT '', roadway_characteristics TEXT NOT NULL DEFAULT '',
    traffic_controls TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS motorcycle_inspections (
    vehicle_id TEXT PRIMARY KEY REFERENCES vehicles(id) ON DELETE CASCADE,
    frame_number TEXT NOT NULL DEFAULT '', engine_number TEXT NOT NULL DEFAULT '',
    inspection_date TEXT NOT NULL DEFAULT '', inspection_location TEXT NOT NULL DEFAULT '',
    officer TEXT NOT NULL DEFAULT '', dpsst TEXT NOT NULL DEFAULT '',
    general_comments TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS motorcycle_inspection_items (
    vehicle_id TEXT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    item_number INTEGER NOT NULL,
    rating TEXT NOT NULL DEFAULT '', measurement TEXT NOT NULL DEFAULT '',
    comments TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (vehicle_id, item_number)
);

CREATE INDEX IF NOT EXISTS idx_people_case ON people(case_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_case ON vehicles(case_id);
CREATE INDEX IF NOT EXISTS idx_chronology_case ON chronology(case_id, event_date, event_time);
CREATE INDEX IF NOT EXISTS idx_tasks_case ON tasks(case_id, status, sort_order);
CREATE INDEX IF NOT EXISTS idx_property_receipts_case
    ON property_receipts(case_id, receipt_number, created_at);
CREATE INDEX IF NOT EXISTS idx_property_receipt_items_receipt
    ON property_receipt_items(receipt_id, item_number, created_at);
CREATE INDEX IF NOT EXISTS idx_tires_vehicle ON tire_inspections(vehicle_id, position);
CREATE INDEX IF NOT EXISTS idx_contacts_case ON contact_relationships(case_id, contact_type);
CREATE INDEX IF NOT EXISTS idx_vru_case ON vru_analyses(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_files_case ON file_references(case_id, category);
CREATE INDEX IF NOT EXISTS idx_diagrams_case ON diagram_records(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_charges_case ON charge_dispositions(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_video_sources_case ON video_sources(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_surfaces_case ON surface_observations(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_roadways_case ON roadway_records(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_hit_run_vehicle_leads_case
    ON hit_run_vehicle_leads(case_id, lead_number, created_at);
CREATE INDEX IF NOT EXISTS idx_hit_run_evidence_case
    ON hit_run_evidence_items(case_id, evidence_number, created_at);
CREATE INDEX IF NOT EXISTS idx_hit_run_person_leads_case
    ON hit_run_person_leads(case_id, lead_number, created_at);
PRAGMA user_version = 33;
"""


class CaseRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            previous_version = connection.execute("PRAGMA user_version").fetchone()[0]
            connection.executescript(SCHEMA)
            self._migrate_schema_33(connection, previous_version)

    @staticmethod
    def _migrate_schema_33(
        connection: sqlite3.Connection,
        previous_version: int,
    ) -> None:
        additions = {
            "user_defaults": {
                "auto_check_updates": "INTEGER NOT NULL DEFAULT 1",
                "last_update_check": "TEXT NOT NULL DEFAULT ''",
            },
            "cases": {
                "assigned_officer_dpsst": "TEXT NOT NULL DEFAULT ''",
                "assignment": "TEXT NOT NULL DEFAULT ''",
                "first_harmful_event": "TEXT NOT NULL DEFAULT ''",
            },
            "vehicles": {
                "insurance_company": "TEXT NOT NULL DEFAULT ''",
                "insurance_policy_number": "TEXT NOT NULL DEFAULT ''",
                "insurance_claim_number": "TEXT NOT NULL DEFAULT ''",
                "insurance_adjuster_name": "TEXT NOT NULL DEFAULT ''",
                "insurance_adjuster_phone": "TEXT NOT NULL DEFAULT ''",
                "insurance_adjuster_email": "TEXT NOT NULL DEFAULT ''",
                "body_style": "TEXT NOT NULL DEFAULT ''",
                "trim": "TEXT NOT NULL DEFAULT ''",
                "vehicle_weight": "TEXT NOT NULL DEFAULT ''",
                "engine": "TEXT NOT NULL DEFAULT ''",
                "tire_size": "TEXT NOT NULL DEFAULT ''",
                "property_damage": "TEXT NOT NULL DEFAULT ''",
                "towed": "INTEGER NOT NULL DEFAULT 0",
                "warrant_obtained": "INTEGER NOT NULL DEFAULT 0",
                "vehicle_inspection_completed": "INTEGER NOT NULL DEFAULT 0",
                "nhtsa_recalls_checked": "INTEGER NOT NULL DEFAULT 0",
                "cdr_equipped": "INTEGER NOT NULL DEFAULT 0",
                "cdr_imaged": "INTEGER NOT NULL DEFAULT 0",
                "cdr_report_uploaded": "INTEGER NOT NULL DEFAULT 0",
                "released": "INTEGER NOT NULL DEFAULT 0",
                "release_date": "TEXT NOT NULL DEFAULT ''",
                "release_information": "TEXT NOT NULL DEFAULT ''",
            },
            "people": {
                "cell_phone": "TEXT NOT NULL DEFAULT ''",
                "home_phone": "TEXT NOT NULL DEFAULT ''",
                "work_phone": "TEXT NOT NULL DEFAULT ''",
                "city": "TEXT NOT NULL DEFAULT ''",
                "state": "TEXT NOT NULL DEFAULT ''",
                "zip_code": "TEXT NOT NULL DEFAULT ''",
                "occupation": "TEXT NOT NULL DEFAULT ''",
                "business_address": "TEXT NOT NULL DEFAULT ''",
            },
            "road_conditions": {
                "streetlight_notes": "TEXT NOT NULL DEFAULT ''",
                "area_classifications": "TEXT NOT NULL DEFAULT ''",
                "weather_station": "TEXT NOT NULL DEFAULT ''",
                "visibility": "TEXT NOT NULL DEFAULT ''",
                "civil_twilight_morning": "TEXT NOT NULL DEFAULT ''",
                "civil_twilight_evening": "TEXT NOT NULL DEFAULT ''",
                "moonrise": "TEXT NOT NULL DEFAULT ''",
                "moonset": "TEXT NOT NULL DEFAULT ''",
                "moon_phase": "TEXT NOT NULL DEFAULT ''",
            },
            "participant_details": {
                "hospital": "TEXT NOT NULL DEFAULT ''",
                "height": "TEXT NOT NULL DEFAULT ''",
                "weight": "TEXT NOT NULL DEFAULT ''",
                "injury_codes": "TEXT NOT NULL DEFAULT ''",
                "evidence_items": "TEXT NOT NULL DEFAULT ''",
                "extracted": "TEXT NOT NULL DEFAULT 'Unknown'",
                "helmet": "TEXT NOT NULL DEFAULT 'Not Applicable'",
            },
            "driver_profiles": {
                "physical_condition_types": "TEXT NOT NULL DEFAULT ''",
                "testing_methods": "TEXT NOT NULL DEFAULT ''",
                "license_restricted": "TEXT NOT NULL DEFAULT 'Unknown'",
                "license_restriction_explanation": "TEXT NOT NULL DEFAULT ''",
                "endorsements": "TEXT NOT NULL DEFAULT ''",
                "license_issued_date": "TEXT NOT NULL DEFAULT ''",
                "license_expiration_date": "TEXT NOT NULL DEFAULT ''",
            },
            "contact_relationships": {
                "cell_phone": "TEXT NOT NULL DEFAULT ''",
                "home_phone": "TEXT NOT NULL DEFAULT ''",
                "work_phone": "TEXT NOT NULL DEFAULT ''",
                "address": "TEXT NOT NULL DEFAULT ''",
                "city": "TEXT NOT NULL DEFAULT ''",
                "state": "TEXT NOT NULL DEFAULT ''",
            },
            "vru_analyses": {
                "projection_classifications": "TEXT NOT NULL DEFAULT ''",
                "prt_factors": "TEXT NOT NULL DEFAULT ''",
                "light_meter_used": "INTEGER NOT NULL DEFAULT 0",
                "light_board_used": "INTEGER NOT NULL DEFAULT 0",
            },
            "investigative_checklists": {
                "peer_review_status": "TEXT NOT NULL DEFAULT 'Not Started'",
                "sergeant_review_status": "TEXT NOT NULL DEFAULT 'Not Started'",
                "submitted_to_da_status": "TEXT NOT NULL DEFAULT 'Not Started'",
                "peer_review_date": "TEXT NOT NULL DEFAULT ''",
                "sergeant_review_date": "TEXT NOT NULL DEFAULT ''",
                "court_case_number": "TEXT NOT NULL DEFAULT ''",
            },
            "vehicle_inspections": {
                "nicb_status": "TEXT NOT NULL DEFAULT ''",
                "recall_status": "TEXT NOT NULL DEFAULT ''",
                "vin_decode_status": "TEXT NOT NULL DEFAULT ''",
                "headlights_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "headlights_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "taillights_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "taillights_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "tag_lights_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "tag_lights_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "brake_lights_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "brake_lights_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "turn_signals_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "turn_signals_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "parking_lamps_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "parking_lamps_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "other_lights_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "other_lights_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "front_wipers_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "front_wipers_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "rear_wipers_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "rear_wipers_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "horn_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "horn_operable": "TEXT NOT NULL DEFAULT 'Unknown'",
                "headlight_switch_position": "TEXT NOT NULL DEFAULT ''",
                "wiper_switch_position": "TEXT NOT NULL DEFAULT ''",
                "ignition_position": "TEXT NOT NULL DEFAULT ''",
                "radio_position": "TEXT NOT NULL DEFAULT ''",
                "heater_position": "TEXT NOT NULL DEFAULT ''",
                "headlamp_lens_condition": "TEXT NOT NULL DEFAULT ''",
                "safety_glass_condition": "TEXT NOT NULL DEFAULT ''",
                "inside_mirror": "TEXT NOT NULL DEFAULT ''",
                "outside_mirrors": "TEXT NOT NULL DEFAULT ''",
                "window_positions": "TEXT NOT NULL DEFAULT ''",
                "seatbelts_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "shoulder_harnesses_equipped": "TEXT NOT NULL DEFAULT 'Unknown'",
                "airbag_status": "TEXT NOT NULL DEFAULT ''",
                "body_interior_condition": "TEXT NOT NULL DEFAULT ''",
                "body_exterior_condition": "TEXT NOT NULL DEFAULT ''",
                "seatbelt_loading": "TEXT NOT NULL DEFAULT 'Unknown'",
                "steering_wheel_damage": "TEXT NOT NULL DEFAULT 'Unknown'",
                "device_observations": "TEXT NOT NULL DEFAULT ''",
                "tire_contribution_explanation": "TEXT NOT NULL DEFAULT ''",
            },
        }
        for table, columns in additions.items():
            existing = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, declaration in columns.items():
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        if previous_version < 30:
            for status_column, date_column, item in (
                ("peer_review_status", "peer_review_date", "Report Peer Reviewed"),
                ("sergeant_review_status", "sergeant_review_date", "Report Sgt Reviewed"),
                ("submitted_to_da_status", "submitted_to_da_date", "Submitted to DA"),
            ):
                connection.execute(
                    f"""
                    UPDATE investigative_checklists
                    SET {status_column} = 'Complete'
                    WHERE TRIM({date_column}) <> ''
                       OR INSTR(completed_items_json, ?) > 0
                    """,
                    (f'"{item}"',),
                )
        if previous_version < 24:
            connection.execute(
                """
                UPDATE vehicles
                SET towed = 1
                WHERE TRIM(tow_information) <> ''
                """
            )
        case_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cases)").fetchall()
        }
        if "key_questions" in case_columns:
            connection.execute("ALTER TABLE cases DROP COLUMN key_questions")
        video_source_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(video_sources)").fetchall()
        }
        if "axon_status" not in video_source_columns:
            if "dims_status" in video_source_columns:
                connection.execute(
                    "ALTER TABLE video_sources RENAME COLUMN dims_status TO axon_status"
                )
            else:
                connection.execute(
                    "ALTER TABLE video_sources "
                    "ADD COLUMN axon_status TEXT NOT NULL DEFAULT 'Unknown'"
                )
        if "address" not in video_source_columns:
            connection.execute(
                "ALTER TABLE video_sources ADD COLUMN address TEXT NOT NULL DEFAULT ''"
            )
        if previous_version < 8:
            legacy_roadways = connection.execute(
                """
                SELECT
                    rc.case_id,
                    COALESCE(
                        NULLIF(TRIM(cd.road_name), ''),
                        NULLIF(TRIM(c.location), ''),
                        'Primary roadway'
                    ) AS roadway_tag,
                    rc.speed_limit,
                    rc.speed_limit_posted,
                    rc.speed_limit_location,
                    rc.curve_radius,
                    rc.chord,
                    rc.middle_ordinate,
                    rc.critical_speed,
                    rc.roadway_characteristics,
                    rc.traffic_controls
                FROM road_conditions rc
                JOIN cases c ON c.id = rc.case_id
                LEFT JOIN crash_details cd ON cd.case_id = rc.case_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM roadway_records rr WHERE rr.case_id = rc.case_id
                )
                  AND (
                    TRIM(rc.speed_limit) <> ''
                    OR rc.speed_limit_posted NOT IN ('', 'Unknown')
                    OR TRIM(rc.speed_limit_location) <> ''
                    OR TRIM(rc.curve_radius) <> ''
                    OR TRIM(rc.chord) <> ''
                    OR TRIM(rc.middle_ordinate) <> ''
                    OR TRIM(rc.critical_speed) <> ''
                    OR TRIM(rc.roadway_characteristics) <> ''
                    OR TRIM(rc.traffic_controls) <> ''
                  )
                ORDER BY rc.case_id
                """
            ).fetchall()
            migrated_at = utc_now()
            for legacy in legacy_roadways:
                values = dict(legacy)
                values.update(
                    id=new_id(),
                    created_at=migrated_at,
                    updated_at=migrated_at,
                )
                connection.execute(
                    """
                    INSERT INTO roadway_records (
                        id, case_id, roadway_tag, speed_limit, speed_limit_posted,
                        speed_limit_location, curve_radius, chord, middle_ordinate,
                        critical_speed, roadway_characteristics, traffic_controls,
                        created_at, updated_at
                    ) VALUES (
                        :id, :case_id, :roadway_tag, :speed_limit, :speed_limit_posted,
                        :speed_limit_location, :curve_radius, :chord, :middle_ordinate,
                        :critical_speed, :roadway_characteristics, :traffic_controls,
                        :created_at, :updated_at
                    )
                    """,
                    values,
                )
        if previous_version < 19:
            legacy_surfaces = connection.execute(
                """
                SELECT
                    rc.case_id,
                    COALESCE(
                        NULLIF(TRIM(cd.road_name), ''),
                        NULLIF(TRIM(c.location), ''),
                        'Primary roadway surface'
                    ) AS location,
                    rc.surface_composition AS composition,
                    rc.surface_condition AS condition,
                    rc.friction_value
                FROM road_conditions rc
                JOIN cases c ON c.id = rc.case_id
                LEFT JOIN crash_details cd ON cd.case_id = rc.case_id
                WHERE (
                    TRIM(rc.surface_composition) <> ''
                    OR TRIM(rc.surface_condition) <> ''
                    OR TRIM(rc.friction_value) <> ''
                )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM surface_observations surface
                    WHERE surface.case_id = rc.case_id
                      AND TRIM(surface.composition) = TRIM(rc.surface_composition)
                      AND TRIM(surface.condition) = TRIM(rc.surface_condition)
                      AND TRIM(surface.friction_value) = TRIM(rc.friction_value)
                )
                ORDER BY rc.case_id
                """
            ).fetchall()
            migrated_at = utc_now()
            for legacy in legacy_surfaces:
                values = dict(legacy)
                values.update(
                    id=new_id(),
                    notes="",
                    created_at=migrated_at,
                    updated_at=migrated_at,
                )
                connection.execute(
                    """
                    INSERT INTO surface_observations (
                        id, case_id, location, composition, condition,
                        friction_value, notes, created_at, updated_at
                    ) VALUES (
                        :id, :case_id, :location, :composition, :condition,
                        :friction_value, :notes, :created_at, :updated_at
                    )
                    """,
                    values,
                )
            connection.execute(
                """
                UPDATE road_conditions
                SET surface_composition = '', surface_condition = '', friction_value = ''
                WHERE TRIM(surface_composition) <> ''
                   OR TRIM(surface_condition) <> ''
                   OR TRIM(friction_value) <> ''
                """
            )
        if previous_version < 11:
            connection.execute(
                """
                UPDATE vehicles
                SET insurance_company = insurance
                WHERE TRIM(insurance_company) = '' AND TRIM(insurance) <> ''
                """
            )
        if previous_version < 14:
            connection.execute(
                """
                UPDATE cases
                SET investigator = COALESCE(
                    NULLIF(TRIM(investigator), ''),
                    (
                        SELECT NULLIF(TRIM(details.assisting_officer), '')
                        FROM exchange_report_details details
                        WHERE details.case_id = cases.id
                    ),
                    ''
                ),
                assignment = COALESCE(
                    NULLIF(TRIM(assignment), ''),
                    (
                        SELECT NULLIF(TRIM(details.precinct), '')
                        FROM exchange_report_details details
                        WHERE details.case_id = cases.id
                    ),
                    ''
                )
                """
            )
        connection.execute("PRAGMA user_version = 33")

    def get_user_defaults(self) -> UserDefaults:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_name, dpsst, assignment, auto_check_updates, "
                "last_update_check, updated_at "
                "FROM user_defaults WHERE id=1"
            ).fetchone()
        if not row:
            return UserDefaults()
        values = dict(row)
        values["auto_check_updates"] = bool(values["auto_check_updates"])
        return UserDefaults(**values)

    def save_user_defaults(self, defaults: UserDefaults) -> UserDefaults:
        defaults.updated_at = utc_now()
        values = asdict(defaults)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO user_defaults
                (id, user_name, dpsst, assignment, auto_check_updates,
                 last_update_check, updated_at)
                VALUES (1, :user_name, :dpsst, :assignment, :auto_check_updates,
                        :last_update_check, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                  user_name=excluded.user_name,
                  dpsst=excluded.dpsst,
                  assignment=excluded.assignment,
                  auto_check_updates=excluded.auto_check_updates,
                  last_update_check=excluded.last_update_check,
                  updated_at=excluded.updated_at""",
                values,
            )
        return defaults

    def create_case(
        self,
        case_number: str = "",
        investigator: str = "",
        assigned_officer_dpsst: str = "",
        assignment: str = "",
    ) -> CrashCase:
        now = utc_now()
        case = CrashCase(
            id=new_id(),
            case_number=case_number,
            investigator=investigator,
            assigned_officer_dpsst=assigned_officer_dpsst,
            assignment=assignment,
            created_at=now,
            updated_at=now,
        )
        self.save_case(case)
        return case

    def save_case(self, case: CrashCase) -> CrashCase:
        if not case.created_at:
            case.created_at = utc_now()
        case.updated_at = utc_now()
        values = asdict(case)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO cases
                (id, case_number, crash_date, crash_time, location, investigator,
                 assigned_officer_dpsst, assignment, status, first_harmful_event, summary, notes,
                 created_at, updated_at)
                VALUES (:id, :case_number, :crash_date, :crash_time, :location, :investigator,
                        :assigned_officer_dpsst, :assignment, :status, :first_harmful_event, :summary, :notes,
                        :created_at, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                  case_number=excluded.case_number, crash_date=excluded.crash_date,
                  crash_time=excluded.crash_time, location=excluded.location,
                  investigator=excluded.investigator,
                  assigned_officer_dpsst=excluded.assigned_officer_dpsst,
                  assignment=excluded.assignment, status=excluded.status,
                  first_harmful_event=excluded.first_harmful_event,
                  summary=excluded.summary, notes=excluded.notes,
                  updated_at=excluded.updated_at""",
                values,
            )
        return case

    def list_cases(self) -> list[CrashCase]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM cases ORDER BY CASE WHEN crash_date='' THEN 1 ELSE 0 END, crash_date DESC, updated_at DESC"
            ).fetchall()
        return [CrashCase(**dict(row)) for row in rows]

    def get_case(self, case_id: str) -> Optional[CrashCase]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return CrashCase(**dict(row)) if row else None

    def delete_case(self, case_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM cases WHERE id=?", (case_id,))

    def save_person(self, person: Person) -> Person:
        if not person.id:
            person.id = new_id()
        if not person.created_at:
            person.created_at = utc_now()
        person.updated_at = utc_now()
        values = asdict(person)
        roles = values.pop("roles")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO people
                (id, case_id, first_name, middle_name, last_name, dob, sex, race, phone,
                 cell_phone, home_phone, work_phone, email, address, city, state, zip_code,
                 occupation, business_address, notes, created_at, updated_at)
                VALUES (:id, :case_id, :first_name, :middle_name, :last_name, :dob, :sex,
                        :race, :phone, :cell_phone, :home_phone, :work_phone, :email,
                        :address, :city, :state, :zip_code, :occupation, :business_address, :notes,
                        :created_at, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                  first_name=excluded.first_name, middle_name=excluded.middle_name,
                  last_name=excluded.last_name, dob=excluded.dob, sex=excluded.sex,
                  race=excluded.race, phone=excluded.phone, cell_phone=excluded.cell_phone,
                  home_phone=excluded.home_phone, work_phone=excluded.work_phone,
                  email=excluded.email, address=excluded.address, city=excluded.city,
                  state=excluded.state, zip_code=excluded.zip_code,
                  occupation=excluded.occupation,
                  business_address=excluded.business_address, notes=excluded.notes,
                  updated_at=excluded.updated_at""",
                values,
            )
            connection.execute("DELETE FROM person_roles WHERE person_id=?", (person.id,))
            connection.executemany(
                "INSERT INTO person_roles(person_id, role) VALUES (?, ?)",
                [(person.id, role) for role in dict.fromkeys(roles) if role],
            )
        return person

    def list_people(self, case_id: str) -> list[Person]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM people WHERE case_id=? ORDER BY last_name, first_name", (case_id,)
            ).fetchall()
            role_rows = connection.execute(
                """SELECT pr.person_id, pr.role FROM person_roles pr
                   JOIN people p ON p.id=pr.person_id WHERE p.case_id=? ORDER BY pr.role""",
                (case_id,),
            ).fetchall()
        roles: dict[str, list[str]] = {}
        for row in role_rows:
            roles.setdefault(row["person_id"], []).append(row["role"])
        return [Person(**dict(row), roles=roles.get(row["id"], [])) for row in rows]

    def get_person(self, person_id: str) -> Optional[Person]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
            role_rows = connection.execute(
                "SELECT role FROM person_roles WHERE person_id=? ORDER BY role", (person_id,)
            ).fetchall()
        return Person(**dict(row), roles=[item["role"] for item in role_rows]) if row else None

    def delete_person(self, person_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM people WHERE id=?", (person_id,))

    @staticmethod
    def _vehicle_from_row(row: sqlite3.Row) -> Vehicle:
        values = dict(row)
        values["towed"] = bool(values["towed"])
        for attribute, _label in VEHICLE_WORKFLOW_FIELDS:
            values[attribute] = bool(values[attribute])
        return Vehicle(**values)

    def save_vehicle(self, vehicle: Vehicle) -> Vehicle:
        if not vehicle.id:
            vehicle.id = new_id()
        if vehicle.insurance_company:
            vehicle.insurance = vehicle.insurance_company
        elif vehicle.insurance:
            vehicle.insurance_company = vehicle.insurance
        if not vehicle.created_at:
            vehicle.created_at = utc_now()
        vehicle.updated_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO vehicles
                (id, case_id, vehicle_number, year, make, model, trim, body_style, color,
                 vehicle_weight, engine, tire_size, vin, plate, plate_state,
                 owner_person_id, driver_person_id, insurance, insurance_company,
                 insurance_policy_number, insurance_claim_number,
                 insurance_adjuster_name, insurance_adjuster_phone,
                 insurance_adjuster_email, property_damage, towed,
                 tow_information, edr_status,
                 warrant_obtained,
                 vehicle_inspection_completed, nhtsa_recalls_checked, cdr_equipped, cdr_imaged,
                 cdr_report_uploaded,
                 released, release_date, release_information, damage_notes, notes, created_at, updated_at)
                VALUES (:id, :case_id, :vehicle_number, :year, :make, :model, :trim, :body_style,
                        :color, :vehicle_weight, :engine, :tire_size, :vin, :plate, :plate_state,
                        :owner_person_id, :driver_person_id, :insurance,
                        :insurance_company, :insurance_policy_number,
                        :insurance_claim_number, :insurance_adjuster_name,
                        :insurance_adjuster_phone, :insurance_adjuster_email,
                        :property_damage, :towed, :tow_information, :edr_status,
                        :warrant_obtained,
                        :vehicle_inspection_completed,
                        :nhtsa_recalls_checked, :cdr_equipped, :cdr_imaged, :cdr_report_uploaded,
                        :released, :release_date,
                        :release_information, :damage_notes, :notes, :created_at, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                  vehicle_number=excluded.vehicle_number, year=excluded.year, make=excluded.make,
                  model=excluded.model, trim=excluded.trim, body_style=excluded.body_style,
                  color=excluded.color, vehicle_weight=excluded.vehicle_weight,
                  engine=excluded.engine, tire_size=excluded.tire_size, vin=excluded.vin,
                  plate=excluded.plate, plate_state=excluded.plate_state,
                  owner_person_id=excluded.owner_person_id, driver_person_id=excluded.driver_person_id,
                  insurance=excluded.insurance, insurance_company=excluded.insurance_company,
                  insurance_policy_number=excluded.insurance_policy_number,
                  insurance_claim_number=excluded.insurance_claim_number,
                  insurance_adjuster_name=excluded.insurance_adjuster_name,
                  insurance_adjuster_phone=excluded.insurance_adjuster_phone,
                  insurance_adjuster_email=excluded.insurance_adjuster_email,
                  property_damage=excluded.property_damage,
                  towed=excluded.towed, tow_information=excluded.tow_information,
                  edr_status=excluded.edr_status,
                  warrant_obtained=excluded.warrant_obtained,
                  vehicle_inspection_completed=excluded.vehicle_inspection_completed,
                  nhtsa_recalls_checked=excluded.nhtsa_recalls_checked,
                  cdr_equipped=excluded.cdr_equipped, cdr_imaged=excluded.cdr_imaged,
                  cdr_report_uploaded=excluded.cdr_report_uploaded,
                  released=excluded.released, release_date=excluded.release_date,
                  release_information=excluded.release_information,
                  damage_notes=excluded.damage_notes,
                  notes=excluded.notes, updated_at=excluded.updated_at""",
                asdict(vehicle),
            )
            if vehicle.driver_person_id:
                connection.execute(
                    "INSERT OR IGNORE INTO person_roles(person_id, role) VALUES (?, 'Driver')",
                    (vehicle.driver_person_id,),
                )
            if vehicle.owner_person_id:
                connection.execute(
                    "INSERT OR IGNORE INTO person_roles(person_id, role) VALUES (?, 'Vehicle Owner')",
                    (vehicle.owner_person_id,),
                )
        return vehicle

    def list_vehicles(self, case_id: str) -> list[Vehicle]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM vehicles WHERE case_id=? ORDER BY vehicle_number, created_at", (case_id,)
            ).fetchall()
        return [self._vehicle_from_row(row) for row in rows]

    def get_vehicle(self, vehicle_id: str) -> Optional[Vehicle]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
        return self._vehicle_from_row(row) if row else None

    def delete_vehicle(self, vehicle_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))

    def get_hit_run_overview(self, case_id: str) -> HitRunOverview:
        record = self._get_one_to_one(
            "hit_run_overviews", HitRunOverview, "case_id", case_id
        )
        if record is None:
            return HitRunOverview(case_id=case_id)
        record.is_hit_and_run = bool(record.is_hit_and_run)
        return record

    def save_hit_run_overview(self, record: HitRunOverview) -> HitRunOverview:
        return self._save_one_to_one("hit_run_overviews", record, "case_id")

    def save_hit_run_vehicle_lead(
        self, record: HitRunVehicleLead
    ) -> HitRunVehicleLead:
        return self._save_simple("hit_run_vehicle_leads", record)

    def list_hit_run_vehicle_leads(self, case_id: str) -> list[HitRunVehicleLead]:
        return self._list_simple(
            "hit_run_vehicle_leads",
            HitRunVehicleLead,
            case_id,
            "lead_number, created_at",
        )

    def get_hit_run_vehicle_lead(
        self, record_id: str
    ) -> Optional[HitRunVehicleLead]:
        return self._get_simple(
            "hit_run_vehicle_leads", HitRunVehicleLead, record_id
        )

    def delete_hit_run_vehicle_lead(self, record_id: str) -> None:
        self._delete_simple("hit_run_vehicle_leads", record_id)

    def save_hit_run_person_lead(
        self, record: HitRunPersonLead
    ) -> HitRunPersonLead:
        return self._save_simple("hit_run_person_leads", record)

    def list_hit_run_person_leads(self, case_id: str) -> list[HitRunPersonLead]:
        return self._list_simple(
            "hit_run_person_leads",
            HitRunPersonLead,
            case_id,
            "lead_number, created_at",
        )

    def get_hit_run_person_lead(
        self, record_id: str
    ) -> Optional[HitRunPersonLead]:
        return self._get_simple("hit_run_person_leads", HitRunPersonLead, record_id)

    def delete_hit_run_person_lead(self, record_id: str) -> None:
        self._delete_simple("hit_run_person_leads", record_id)

    def save_hit_run_evidence_item(
        self, record: HitRunEvidenceItem
    ) -> HitRunEvidenceItem:
        return self._save_simple("hit_run_evidence_items", record)

    def list_hit_run_evidence_items(self, case_id: str) -> list[HitRunEvidenceItem]:
        return self._list_simple(
            "hit_run_evidence_items",
            HitRunEvidenceItem,
            case_id,
            "evidence_number, created_at",
        )

    def get_hit_run_evidence_item(
        self, record_id: str
    ) -> Optional[HitRunEvidenceItem]:
        return self._get_simple(
            "hit_run_evidence_items", HitRunEvidenceItem, record_id
        )

    def delete_hit_run_evidence_item(self, record_id: str) -> None:
        self._delete_simple("hit_run_evidence_items", record_id)

    def save_chronology(self, entry: ChronologyEntry) -> ChronologyEntry:
        return self._save_simple("chronology", entry)

    def list_chronology(self, case_id: str) -> list[ChronologyEntry]:
        return self._list_simple(
            "chronology", ChronologyEntry, case_id,
            "CASE WHEN event_date='' THEN 1 ELSE 0 END, event_date, event_time, created_at",
        )

    def delete_chronology(self, entry_id: str) -> None:
        self._delete_simple("chronology", entry_id)

    def save_task(self, task: CaseTask) -> CaseTask:
        return self._save_simple("tasks", task)

    def list_tasks(self, case_id: str) -> list[CaseTask]:
        return self._list_simple(
            "tasks", CaseTask, case_id,
            "CASE status WHEN 'Open' THEN 0 WHEN 'Waiting' THEN 1 WHEN 'Completed' THEN 2 ELSE 3 END, sort_order, created_at",
        )

    def delete_task(self, task_id: str) -> None:
        self._delete_simple("tasks", task_id)

    def save_property_receipt(self, receipt: PropertyReceipt) -> PropertyReceipt:
        return self._save_simple("property_receipts", receipt)

    def list_property_receipts(self, case_id: str) -> list[PropertyReceipt]:
        return self._list_simple(
            "property_receipts",
            PropertyReceipt,
            case_id,
            "receipt_number, created_at",
        )

    def get_property_receipt(self, receipt_id: str) -> Optional[PropertyReceipt]:
        return self._get_simple("property_receipts", PropertyReceipt, receipt_id)

    def delete_property_receipt(self, receipt_id: str) -> None:
        self._delete_simple("property_receipts", receipt_id)

    def next_property_receipt_item_number(self, receipt_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(item_number), 0) + 1 "
                "FROM property_receipt_items WHERE receipt_id=?",
                (receipt_id,),
            ).fetchone()
        return int(row[0])

    def save_property_receipt_item(
        self,
        item: PropertyReceiptItem,
    ) -> PropertyReceiptItem:
        if item.item_number < 1:
            raise ValueError("Property receipt item numbers must be positive.")
        if not item.id:
            item.id = new_id()
        if not item.created_at:
            item.created_at = utc_now()
        item.updated_at = utc_now()
        values = asdict(item)
        with self._connect() as connection:
            duplicate = connection.execute(
                "SELECT id FROM property_receipt_items "
                "WHERE receipt_id=? AND item_number=? AND id<>?",
                (item.receipt_id, item.item_number, item.id),
            ).fetchone()
            if duplicate:
                raise ValueError(
                    f"Item {item.item_number} already exists on this property receipt."
                )
            connection.execute(
                """INSERT INTO property_receipt_items
                (id, receipt_id, item_number, description, created_at, updated_at)
                VALUES (:id, :receipt_id, :item_number, :description, :created_at, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                  receipt_id=excluded.receipt_id,
                  item_number=excluded.item_number,
                  description=excluded.description,
                  updated_at=excluded.updated_at""",
                values,
            )
        return item

    def list_property_receipt_items(
        self,
        receipt_id: str,
    ) -> list[PropertyReceiptItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM property_receipt_items "
                "WHERE receipt_id=? ORDER BY item_number, created_at",
                (receipt_id,),
            ).fetchall()
        return [PropertyReceiptItem(**dict(row)) for row in rows]

    def get_property_receipt_item(
        self,
        item_id: str,
    ) -> Optional[PropertyReceiptItem]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM property_receipt_items WHERE id=?",
                (item_id,),
            ).fetchone()
        return PropertyReceiptItem(**dict(row)) if row else None

    def delete_property_receipt_item(self, item_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM property_receipt_items WHERE id=?",
                (item_id,),
            )

    def get_investigative_checklist(self, case_id: str) -> InvestigativeChecklist:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM investigative_checklists WHERE case_id=?", (case_id,)
            ).fetchone()
        if not row:
            return InvestigativeChecklist(case_id=case_id)
        values = dict(row)
        completed_items = self._json_list(values.pop("completed_items_json"))
        return InvestigativeChecklist(**values, completed_items=completed_items)

    def save_investigative_checklist(
        self, record: InvestigativeChecklist
    ) -> InvestigativeChecklist:
        record.updated_at = utc_now()
        values = asdict(record)
        values["completed_items_json"] = json.dumps(
            list(dict.fromkeys(record.completed_items)), ensure_ascii=True
        )
        values.pop("completed_items")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO investigative_checklists
                (case_id, completed_items_json, peer_review_status,
                 sergeant_review_status, submitted_to_da_status, peer_review_date,
                 sergeant_review_date, submitted_to_da_date, assigned_dda,
                 da_case_number, court_case_number, updated_at)
                VALUES (:case_id, :completed_items_json, :peer_review_status,
                        :sergeant_review_status, :submitted_to_da_status,
                        :peer_review_date, :sergeant_review_date,
                        :submitted_to_da_date, :assigned_dda, :da_case_number,
                        :court_case_number, :updated_at)
                ON CONFLICT(case_id) DO UPDATE SET
                  completed_items_json=excluded.completed_items_json,
                  peer_review_status=excluded.peer_review_status,
                  sergeant_review_status=excluded.sergeant_review_status,
                  submitted_to_da_status=excluded.submitted_to_da_status,
                  peer_review_date=excluded.peer_review_date,
                  sergeant_review_date=excluded.sergeant_review_date,
                  submitted_to_da_date=excluded.submitted_to_da_date,
                  assigned_dda=excluded.assigned_dda,
                  da_case_number=excluded.da_case_number,
                  court_case_number=excluded.court_case_number,
                  updated_at=excluded.updated_at""",
                values,
            )
        return record

    def save_charge_disposition(self, record: ChargeDisposition) -> ChargeDisposition:
        return self._save_simple("charge_dispositions", record)

    def list_charge_dispositions(self, case_id: str) -> list[ChargeDisposition]:
        return self._list_simple(
            "charge_dispositions", ChargeDisposition, case_id, "created_at, charge"
        )

    def get_charge_disposition(self, record_id: str) -> Optional[ChargeDisposition]:
        return self._get_simple("charge_dispositions", ChargeDisposition, record_id)

    def delete_charge_disposition(self, record_id: str) -> None:
        self._delete_simple("charge_dispositions", record_id)

    def get_crash_details(self, case_id: str) -> CrashDetails:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crash_details WHERE case_id=?", (case_id,)
            ).fetchone()
        if not row:
            return CrashDetails(case_id=case_id)
        values = dict(row)
        scene_evidence = normalize_scene_evidence_methods(
            self._json_list(values.pop("scene_evidence_json"))
        )
        return CrashDetails(**values, scene_evidence=scene_evidence)

    def save_crash_details(self, record: CrashDetails) -> CrashDetails:
        record.updated_at = utc_now()
        record.scene_evidence = normalize_scene_evidence_methods(
            record.scene_evidence
        )
        values = asdict(record)
        values["scene_evidence_json"] = json.dumps(
            list(dict.fromkeys(record.scene_evidence)), ensure_ascii=True
        )
        values.pop("scene_evidence")
        columns = list(values)
        updates = [column for column in columns if column != "case_id"]
        sql = (
            f"INSERT INTO crash_details ({', '.join(columns)}) "
            f"VALUES ({', '.join(':'+column for column in columns)}) "
            f"ON CONFLICT(case_id) DO UPDATE SET "
            f"{', '.join(column+'=excluded.'+column for column in updates)}"
        )
        with self._connect() as connection:
            connection.execute(sql, values)
        return record

    def get_exchange_report_details(self, case_id: str) -> ExchangeReportDetails:
        record = self._get_one_to_one(
            "exchange_report_details",
            ExchangeReportDetails,
            "case_id",
            case_id,
        )
        return record or ExchangeReportDetails(case_id=case_id)

    def save_exchange_report_details(
        self,
        record: ExchangeReportDetails,
    ) -> ExchangeReportDetails:
        return self._save_one_to_one(
            "exchange_report_details",
            record,
            "case_id",
        )

    def save_video_source(self, record: VideoSource) -> VideoSource:
        return self._save_simple("video_sources", record)

    def list_video_sources(self, case_id: str) -> list[VideoSource]:
        return self._list_simple("video_sources", VideoSource, case_id, "created_at, source")

    def get_video_source(self, record_id: str) -> Optional[VideoSource]:
        return self._get_simple("video_sources", VideoSource, record_id)

    def delete_video_source(self, record_id: str) -> None:
        self._delete_simple("video_sources", record_id)

    def save_surface_observation(self, record: SurfaceObservation) -> SurfaceObservation:
        return self._save_simple("surface_observations", record)

    def list_surface_observations(self, case_id: str) -> list[SurfaceObservation]:
        return self._list_simple(
            "surface_observations", SurfaceObservation, case_id, "created_at, location"
        )

    def get_surface_observation(self, record_id: str) -> Optional[SurfaceObservation]:
        return self._get_simple("surface_observations", SurfaceObservation, record_id)

    def delete_surface_observation(self, record_id: str) -> None:
        self._delete_simple("surface_observations", record_id)

    def save_roadway_record(self, record: RoadwayRecord) -> RoadwayRecord:
        return self._save_simple("roadway_records", record)

    def list_roadway_records(self, case_id: str) -> list[RoadwayRecord]:
        return self._list_simple(
            "roadway_records", RoadwayRecord, case_id, "created_at, roadway_tag"
        )

    def get_roadway_record(self, record_id: str) -> Optional[RoadwayRecord]:
        return self._get_simple("roadway_records", RoadwayRecord, record_id)

    def delete_roadway_record(self, record_id: str) -> None:
        self._delete_simple("roadway_records", record_id)

    def get_motorcycle_inspection(self, vehicle_id: str) -> MotorcycleInspection:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM motorcycle_inspections WHERE vehicle_id=?", (vehicle_id,)
            ).fetchone()
            item_rows = connection.execute(
                """SELECT item_number, rating, measurement, comments
                   FROM motorcycle_inspection_items WHERE vehicle_id=? ORDER BY item_number""",
                (vehicle_id,),
            ).fetchall()
        values = dict(row) if row else {"vehicle_id": vehicle_id}
        values["items"] = [MotorcycleInspectionItem(**dict(item)) for item in item_rows]
        return MotorcycleInspection(**values)

    def save_motorcycle_inspection(
        self, record: MotorcycleInspection
    ) -> MotorcycleInspection:
        record.updated_at = utc_now()
        values = asdict(record)
        items = values.pop("items")
        columns = list(values)
        updates = [column for column in columns if column != "vehicle_id"]
        sql = (
            f"INSERT INTO motorcycle_inspections ({', '.join(columns)}) "
            f"VALUES ({', '.join(':'+column for column in columns)}) "
            f"ON CONFLICT(vehicle_id) DO UPDATE SET "
            f"{', '.join(column+'=excluded.'+column for column in updates)}"
        )
        with self._connect() as connection:
            connection.execute(sql, values)
            connection.execute(
                "DELETE FROM motorcycle_inspection_items WHERE vehicle_id=?", (record.vehicle_id,)
            )
            connection.executemany(
                """INSERT INTO motorcycle_inspection_items
                   (vehicle_id, item_number, rating, measurement, comments)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        record.vehicle_id,
                        int(item["item_number"]),
                        item["rating"],
                        item["measurement"],
                        item["comments"],
                    )
                    for item in items
                    if item.get("rating") or item.get("measurement") or item.get("comments")
                ],
            )
        return record

    def get_road_conditions(self, case_id: str) -> RoadConditions:
        record = self._get_one_to_one("road_conditions", RoadConditions, "case_id", case_id)
        return record or RoadConditions(case_id=case_id)

    def save_road_conditions(self, record: RoadConditions) -> RoadConditions:
        return self._save_one_to_one("road_conditions", record, "case_id")

    def get_participant_details(self, person_id: str) -> ParticipantDetails:
        record = self._get_one_to_one("participant_details", ParticipantDetails, "person_id", person_id)
        return record or ParticipantDetails(person_id=person_id)

    def save_participant_details(self, record: ParticipantDetails) -> ParticipantDetails:
        return self._save_one_to_one("participant_details", record, "person_id")

    def get_driver_profile(self, person_id: str) -> DriverProfile:
        record = self._get_one_to_one("driver_profiles", DriverProfile, "person_id", person_id)
        return record or DriverProfile(person_id=person_id)

    def save_driver_profile(self, record: DriverProfile) -> DriverProfile:
        return self._save_one_to_one("driver_profiles", record, "person_id")

    def get_vehicle_inspection(self, vehicle_id: str) -> VehicleInspection:
        record = self._get_one_to_one("vehicle_inspections", VehicleInspection, "vehicle_id", vehicle_id)
        return record or VehicleInspection(vehicle_id=vehicle_id)

    def save_vehicle_inspection(self, record: VehicleInspection) -> VehicleInspection:
        return self._save_one_to_one("vehicle_inspections", record, "vehicle_id")

    def get_witness_details(self, person_id: str) -> WitnessDetails:
        record = self._get_one_to_one("witness_details", WitnessDetails, "person_id", person_id)
        return record or WitnessDetails(person_id=person_id)

    def save_witness_details(self, record: WitnessDetails) -> WitnessDetails:
        return self._save_one_to_one("witness_details", record, "person_id")

    def save_contact(self, record: ContactRelationship) -> ContactRelationship:
        if not record.subject_person_id:
            raise ValueError("Each contact must be assigned to a person.")
        with self._connect() as connection:
            person = connection.execute(
                "SELECT case_id FROM people WHERE id=?",
                (record.subject_person_id,),
            ).fetchone()
        if not person or person["case_id"] != record.case_id:
            raise ValueError("The contact person association must belong to this case.")
        record.vehicle_id = None
        return self._save_simple("contact_relationships", record)

    def list_contacts(self, case_id: str) -> list[ContactRelationship]:
        return self._list_simple("contact_relationships", ContactRelationship, case_id, "contact_type, created_at")

    def get_contact(self, record_id: str) -> Optional[ContactRelationship]:
        return self._get_simple("contact_relationships", ContactRelationship, record_id)

    def delete_contact(self, record_id: str) -> None:
        self._delete_simple("contact_relationships", record_id)

    def save_vru_analysis(self, record: VRUAnalysis) -> VRUAnalysis:
        return self._save_simple("vru_analyses", record)

    def list_vru_analyses(self, case_id: str) -> list[VRUAnalysis]:
        records = self._list_simple("vru_analyses", VRUAnalysis, case_id, "created_at")
        for record in records:
            record.light_meter_used = bool(record.light_meter_used)
            record.light_board_used = bool(record.light_board_used)
        return records

    def get_vru_analysis(self, record_id: str) -> Optional[VRUAnalysis]:
        record = self._get_simple("vru_analyses", VRUAnalysis, record_id)
        if record:
            record.light_meter_used = bool(record.light_meter_used)
            record.light_board_used = bool(record.light_board_used)
        return record

    def delete_vru_analysis(self, record_id: str) -> None:
        self._delete_simple("vru_analyses", record_id)

    def save_file_reference(self, record: FileReference) -> FileReference:
        return self._save_simple("file_references", record)

    def list_file_references(self, case_id: str) -> list[FileReference]:
        return self._list_simple("file_references", FileReference, case_id, "category, title, created_at")

    def get_file_reference(self, record_id: str) -> Optional[FileReference]:
        return self._get_simple("file_references", FileReference, record_id)

    def delete_file_reference(self, record_id: str) -> None:
        self._delete_simple("file_references", record_id)

    def save_diagram(self, record: DiagramRecord) -> DiagramRecord:
        return self._save_simple("diagram_records", record)

    def list_diagrams(self, case_id: str) -> list[DiagramRecord]:
        return self._list_simple("diagram_records", DiagramRecord, case_id, "created_at")

    def get_diagram(self, record_id: str) -> Optional[DiagramRecord]:
        return self._get_simple("diagram_records", DiagramRecord, record_id)

    def delete_diagram(self, record_id: str) -> None:
        self._delete_simple("diagram_records", record_id)

    def list_tires(self, vehicle_id: str) -> list[TireInspection]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tire_inspections WHERE vehicle_id=? ORDER BY position, id", (vehicle_id,)
            ).fetchall()
        return [TireInspection(**dict(row)) for row in rows]

    def replace_tires(self, vehicle_id: str, tires: list[TireInspection]) -> list[TireInspection]:
        with self._connect() as connection:
            connection.execute("DELETE FROM tire_inspections WHERE vehicle_id=?", (vehicle_id,))
            for tire in tires:
                tire.vehicle_id = vehicle_id
                if not tire.id:
                    tire.id = new_id()
                connection.execute(
                    """INSERT INTO tire_inspections
                    (id, vehicle_id, position, make, design, size, pressure,
                     tread_inside, tread_middle, tread_outside, condition)
                    VALUES (:id, :vehicle_id, :position, :make, :design, :size, :pressure,
                            :tread_inside, :tread_middle, :tread_outside, :condition)""",
                    asdict(tire),
                )
        return tires

    def _save_one_to_one(self, table: str, record: T, key: str) -> T:
        allowed = {
            "road_conditions": "case_id",
            "hit_run_overviews": "case_id",
            "exchange_report_details": "case_id",
            "participant_details": "person_id",
            "driver_profiles": "person_id",
            "vehicle_inspections": "vehicle_id",
            "witness_details": "person_id",
        }
        if allowed.get(table) != key:
            raise ValueError("Unsupported table or key")
        setattr(record, "updated_at", utc_now())
        values = asdict(record)
        columns = list(values)
        updates = [column for column in columns if column != key]
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(':'+c for c in columns)}) "
            f"ON CONFLICT({key}) DO UPDATE SET {', '.join(c+'=excluded.'+c for c in updates)}"
        )
        with self._connect() as connection:
            connection.execute(sql, values)
        return record

    def _get_one_to_one(self, table: str, cls: type[T], key: str, value: str) -> Optional[T]:
        allowed = {
            "road_conditions": "case_id",
            "hit_run_overviews": "case_id",
            "exchange_report_details": "case_id",
            "participant_details": "person_id",
            "driver_profiles": "person_id",
            "vehicle_inspections": "vehicle_id",
            "witness_details": "person_id",
        }
        if allowed.get(table) != key:
            raise ValueError("Unsupported table or key")
        with self._connect() as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        return cls(**dict(row)) if row else None

    def _save_simple(self, table: str, record: T) -> T:
        if table not in {"chronology", "tasks", "property_receipts", "contact_relationships", "vru_analyses",
                         "file_references", "diagram_records", "charge_dispositions",
                         "video_sources", "surface_observations", "roadway_records",
                         "hit_run_vehicle_leads", "hit_run_person_leads",
                         "hit_run_evidence_items"}:
            raise ValueError("Unsupported table")
        if not getattr(record, "id"):
            setattr(record, "id", new_id())
        if not getattr(record, "created_at"):
            setattr(record, "created_at", utc_now())
        setattr(record, "updated_at", utc_now())
        values = asdict(record)
        columns = list(values)
        updates = [column for column in columns if column not in {"id", "case_id", "created_at"}]
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(':'+c for c in columns)}) "
            f"ON CONFLICT(id) DO UPDATE SET {', '.join(c+'=excluded.'+c for c in updates)}"
        )
        with self._connect() as connection:
            connection.execute(sql, values)
        return record

    def _list_simple(self, table: str, cls: type[T], case_id: str, order_by: str) -> list[T]:
        if table not in {"chronology", "tasks", "property_receipts", "contact_relationships", "vru_analyses",
                         "file_references", "diagram_records", "charge_dispositions",
                         "video_sources", "surface_observations", "roadway_records",
                         "hit_run_vehicle_leads", "hit_run_person_leads",
                         "hit_run_evidence_items"}:
            raise ValueError("Unsupported table")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE case_id=? ORDER BY {order_by}", (case_id,)
            ).fetchall()
        return [cls(**dict(row)) for row in rows]

    def _get_simple(self, table: str, cls: type[T], record_id: str) -> Optional[T]:
        if table not in {"chronology", "tasks", "property_receipts", "contact_relationships", "vru_analyses",
                         "file_references", "diagram_records", "charge_dispositions",
                         "video_sources", "surface_observations", "roadway_records",
                         "hit_run_vehicle_leads", "hit_run_person_leads",
                         "hit_run_evidence_items"}:
            raise ValueError("Unsupported table")
        with self._connect() as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
        return cls(**dict(row)) if row else None

    def _delete_simple(self, table: str, record_id: str) -> None:
        if table not in {"chronology", "tasks", "property_receipts", "contact_relationships", "vru_analyses",
                         "file_references", "diagram_records", "charge_dispositions",
                         "video_sources", "surface_observations", "roadway_records",
                         "hit_run_vehicle_leads", "hit_run_person_leads",
                         "hit_run_evidence_items"}:
            raise ValueError("Unsupported table")
        with self._connect() as connection:
            connection.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))

    @staticmethod
    def _json_list(value: str) -> list[str]:
        try:
            decoded = json.loads(value or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(decoded, list):
            return []
        return [str(item) for item in decoded if str(item)]

    def case_counts(self, case_id: str) -> dict[str, int]:
        with self._connect() as connection:
            result = {
                "people": connection.execute("SELECT COUNT(*) FROM people WHERE case_id=?", (case_id,)).fetchone()[0],
                "vehicles": connection.execute("SELECT COUNT(*) FROM vehicles WHERE case_id=?", (case_id,)).fetchone()[0],
                "chronology": connection.execute("SELECT COUNT(*) FROM chronology WHERE case_id=?", (case_id,)).fetchone()[0],
                "open_tasks": connection.execute(
                    "SELECT COUNT(*) FROM tasks WHERE case_id=? AND status IN ('Open','Waiting')", (case_id,)
                ).fetchone()[0],
                "injured": connection.execute(
                    """SELECT COUNT(*) FROM participant_details pd
                       JOIN people p ON p.id=pd.person_id
                       WHERE p.case_id=?
                         AND lower(trim(pd.injury_status)) NOT IN (
                           '', 'unknown', 'not injured', 'uninjured', 'none'
                         )
                         AND lower(pd.injury_status) NOT LIKE '%kill%'
                         AND lower(pd.injury_status) NOT LIKE '%fatal%'
                         AND lower(pd.injury_status) NOT LIKE '%deceas%'""",
                    (case_id,),
                ).fetchone()[0],
                "fatal": connection.execute(
                    """SELECT COUNT(*) FROM participant_details pd
                       JOIN people p ON p.id=pd.person_id
                       WHERE p.case_id=? AND (
                         lower(pd.injury_status) LIKE '%kill%'
                         OR lower(pd.injury_status) LIKE '%fatal%'
                         OR lower(pd.injury_status) LIKE '%deceas%'
                         OR trim(pd.date_of_death) <> ''
                       )""",
                    (case_id,),
                ).fetchone()[0],
                "vru": connection.execute(
                    """SELECT COUNT(DISTINCT p.id) FROM people p
                       JOIN person_roles pr ON pr.person_id=p.id
                       WHERE p.case_id=?
                         AND pr.role IN ('Pedestrian', 'Bicyclist', 'Motorcyclist')""",
                    (case_id,),
                ).fetchone()[0],
            }
        return result

    def backup_to(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source_connection:
            backup_connection = sqlite3.connect(destination)
            try:
                source_connection.backup(backup_connection)
            finally:
                backup_connection.close()
        return destination
