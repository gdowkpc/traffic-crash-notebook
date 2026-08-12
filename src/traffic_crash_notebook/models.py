from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


VRU_PERSON_ROLES = (
    "Pedestrian",
    "Bicyclist",
    "Motorcyclist",
)


PERSON_ROLES = (
    "Driver",
    "Passenger",
    *VRU_PERSON_ROLES,
    "Witness",
    "Suspect",
    "Victim",
    "Vehicle Owner",
    "Next of Kin",
    "Family / Contact",
    "Other",
)

CASE_STATUSES = (
    "Active",
    "Waiting for Records",
    "Analysis",
    "Review",
    "Inactive",
    "Closed",
)

TASK_STATUSES = ("Open", "Waiting", "Completed", "Not Needed")

PROPERTY_LODGING_TYPES = (
    "Evidence",
    "Found Property",
    "Prison Property",
    "Safe Keeping",
)

HIT_RUN_INVESTIGATION_STATUSES = (
    "Active",
    "Vehicle Lead Developed",
    "Vehicle Identified",
    "Driver Lead Developed",
    "Driver Identified",
    "Inactive",
    "Closed",
)

HIT_RUN_LEAD_STATUSES = (
    "Possible",
    "Investigating",
    "Eliminated",
    "Confirmed",
)

HIT_RUN_CONFIDENCE_LEVELS = ("Unknown", "Low", "Medium", "High")

CHRONOLOGY_CATEGORIES = (
    "General",
    "Interview",
    "Evidence",
    "Medical",
    "Vehicle",
    "Scene",
    "Analysis",
    "Administrative",
)

INVESTIGATIVE_CHECKLIST_GROUPS = (
    ("Evidence Collection", (
        "Participant Interviews",
        "Witness Interviews",
        "Medical Records - Hospital",
        "Medical Records - Medical Examiner",
        "Toxicology",
    )),
    ("Vehicle(s)", (
        "Insurance - Exchange Report",
    )),
    ("Reporting", (
        "Weather Obtained",
        "CAD Printouts - Police",
        "CAD Printouts - EMS",
        "FARO Scan Processing",
        "FARO - Point Cloud Created",
        "Crash Report Completed",
        "Crash Report - Truck/Bus Addendum",
        "Crash Diagram Completed",
        "Axon Shared to DA",
        "Report Peer Reviewed",
        "Report Sgt Reviewed",
        "Submitted to DA",
    )),
)

CHECKLIST_DATE_FIELDS = {
    "Report Peer Reviewed": "peer_review_date",
    "Report Sgt Reviewed": "sergeant_review_date",
    "Submitted to DA": "submitted_to_da_date",
}

ROUTING_STATUS_OPTIONS = ("Not Started", "Pending", "Complete")

CHECKLIST_STATUS_FIELDS = {
    "Report Peer Reviewed": "peer_review_status",
    "Report Sgt Reviewed": "sergeant_review_status",
    "Submitted to DA": "submitted_to_da_status",
}

VEHICLE_WORKFLOW_FIELDS = (
    ("warrant_obtained", "Warrant"),
    ("vehicle_inspection_completed", "Vehicle Inspection"),
    ("nhtsa_recalls_checked", "NHTSA Recalls Checked"),
    ("cdr_equipped", "CDR Equipped"),
    ("cdr_imaged", "CDR Imaged"),
    ("cdr_report_uploaded", "CDR Report Uploaded"),
    ("released", "Released"),
)

SCENE_EVIDENCE_METHODS = (
    "FED Photos",
    "Investigator Photos",
    "Uploaded to Axon",
    "UAS",
    "Axon",
    "FARO",
)

SCENE_EVIDENCE_ALIASES = {
    "DIMS": "Axon",
}

SURVEILLANCE_VIDEO_EVIDENCE = "Surveillance Video"


def normalize_scene_evidence_methods(selected_methods: list[str]) -> list[str]:
    """Translate retired scene-evidence labels while preserving saved choices."""
    return list(dict.fromkeys(
        SCENE_EVIDENCE_ALIASES.get(method, method)
        for method in selected_methods
    ))


def scene_evidence_for_output(
    selected_methods: list[str],
    *,
    has_video_sources: bool,
) -> list[str]:
    """Filter retired choices and append evidence derived from related records."""
    selected = set(normalize_scene_evidence_methods(selected_methods))
    methods = [
        method
        for method in SCENE_EVIDENCE_METHODS
        if method in selected
        and (method != "Uploaded to Axon" or "Investigator Photos" in selected)
    ]
    if has_video_sources:
        methods.append(SURVEILLANCE_VIDEO_EVIDENCE)
    return methods

CARDINAL_DIRECTIONS = ("", "North", "South", "East", "West")

WEATHER_DISPLAY_UNITS = {
    "temperature": "F",
    "dew_point": "F",
    "winds": "mph",
    "humidity": "%",
    "pressure": "inHg",
    "precipitation": "in",
    "visibility": "mi",
}

_WEATHER_UNIT_PATTERNS = {
    "temperature": re.compile(
        r"(?:\d\s*°?\s*[fc]|degrees?\s*[fc]|fahrenheit|celsius)\.?$",
        re.IGNORECASE,
    ),
    "dew_point": re.compile(
        r"(?:\d\s*°?\s*[fc]|degrees?\s*[fc]|fahrenheit|celsius)\.?$",
        re.IGNORECASE,
    ),
    "winds": re.compile(
        r"\b(?:mph|kph|km/h|knots?|kt|m/s)\b",
        re.IGNORECASE,
    ),
    "humidity": re.compile(r"%|\bpercent\b", re.IGNORECASE),
    "pressure": re.compile(
        r"\b(?:in\s*hg|inhg|hpa|mbar|millibars?|mb|kpa|mm\s*hg)\b",
        re.IGNORECASE,
    ),
    "precipitation": re.compile(
        r"\b(?:in(?:ch(?:es)?)?|mm|cm)\b|[\"″]",
        re.IGNORECASE,
    ),
    "visibility": re.compile(
        r"\b(?:mi(?:les)?|km|kilometers?|m)\b",
        re.IGNORECASE,
    ),
}


def format_weather_measurement(field_name: str, value: str | None) -> str:
    """Add the customary display unit once without changing saved source data."""
    text = (value or "").strip()
    unit = WEATHER_DISPLAY_UNITS.get(field_name)
    if not text or not unit or not any(character.isdigit() for character in text):
        return text
    pattern = _WEATHER_UNIT_PATTERNS.get(field_name)
    if pattern and pattern.search(text):
        return text
    separator = "" if unit == "%" else " "
    return f"{text}{separator}{unit}"

ROAD_AREA_OPTIONS = (
    "Residential",
    "Business",
    "Industrial",
    "Rural",
    "Interstate",
    "Other",
)

PHYSICAL_CONDITION_OPTIONS = (
    "None",
    "Heart Condition",
    "Diabetes",
    "Epilepsy",
    "Hearing",
    "Vision",
    "Other",
)

IMPAIRMENT_TESTING_OPTIONS = (
    "BAC - Breath",
    "BAC - Urine",
    "BAC - Blood",
    "Controlled Substance",
    "DRE",
    "SFST",
)

INJURY_CODE_OPTIONS = (
    "1 - Laceration",
    "2 - Abrasion",
    "3 - Contusion",
    "4 - Puncture",
    "5 - Internal Injury",
    "6 - Burn",
    "7 - Simple Fracture",
    "8 - Compound Fracture",
    "9 - Partially Severed",
    "10 - Severed",
    "11 - Complaint of Injury",
    "12 - Other / Specify",
)

PARTICIPANT_EVIDENCE_OPTIONS = ("Hair", "Blood", "DNA", "Clothing", "Skin", "Shoes", "Other")

VRU_PROJECTION_OPTIONS = (
    "High Front",
    "Low Front",
    "Adult",
    "Juvenile",
    "Front Fender Vault",
    "Roof Vault",
    "Drag",
)

MOTORCYCLE_INSPECTION_ITEMS = (
    (1, "Fasteners"),
    (2, "Turn Signals"),
    (3, "Head Lamp / Tail Lamp"),
    (4, "Throttle / Clutch Controls"),
    (5, "Front Brake Controls"),
    (6, "Fork"),
    (7, "Front Fork Oil Leakage"),
    (8, "Front Tire Pressure"),
    (9, "Front Fender and/or Brace"),
    (10, "Front Tire Wear"),
    (11, "Front Wheel, Cast"),
    (12, "Front Wheel, Spokes"),
    (13, "Front Tire Mounting"),
    (14, "Front Tire Type"),
    (15, "Steering Head Bearings"),
    (16, "Mirrors"),
    (17, "Front Brakes"),
    (18, "Handle Bars and Associated Switches"),
    (19, "Speedometer"),
    (20, "Odometer"),
    (21, "Trip Meter"),
    (22, "Rear Tire Wear"),
    (23, "Rear Tire Pressure"),
    (24, "Rear Tire Mounting"),
    (25, "Rear Wheel, Spokes"),
    (26, "Rear Tire Type"),
    (27, "Drive Chain"),
    (28, "Drive Belt"),
    (29, "Swing Arm Pivot"),
    (30, "Rear Fender"),
    (31, "Rear Lights"),
    (32, "Rear Brakes"),
    (33, "Wheel Base"),
    (34, "Gas Tank"),
    (35, "Travel Trunk"),
    (36, "Side / Center Stand"),
    (37, "Cargo Load Distribution"),
    (38, "Accessories"),
    (39, "Fairing / Windshield"),
    (40, "Modification"),
    (41, "Fork Angle"),
    (42, "Shifter"),
    (43, "Steering Head Alignment"),
    (44, "Warning Labels / VIN Locations"),
)


@dataclass(slots=True)
class UserDefaults:
    user_name: str = ""
    dpsst: str = ""
    assignment: str = ""
    auto_check_updates: bool = True
    last_update_check: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class CrashCase:
    id: str
    case_number: str = ""
    crash_date: str = ""
    crash_time: str = ""
    location: str = ""
    investigator: str = ""
    assigned_officer_dpsst: str = ""
    assignment: str = ""
    status: str = "Active"
    first_harmful_event: str = ""
    summary: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class Person:
    id: str
    case_id: str
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    dob: str = ""
    sex: str = ""
    race: str = ""
    phone: str = ""
    cell_phone: str = ""
    home_phone: str = ""
    work_phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    occupation: str = ""
    business_address: str = ""
    notes: str = ""
    roles: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def display_name(self) -> str:
        return " ".join(
            part.strip() for part in (self.first_name, self.middle_name, self.last_name) if part.strip()
        ) or "Unnamed person"


@dataclass(slots=True)
class Vehicle:
    id: str
    case_id: str
    vehicle_number: str = ""
    year: str = ""
    make: str = ""
    model: str = ""
    body_style: str = ""
    color: str = ""
    vin: str = ""
    plate: str = ""
    plate_state: str = ""
    owner_person_id: Optional[str] = None
    driver_person_id: Optional[str] = None
    insurance: str = ""
    insurance_company: str = ""
    insurance_policy_number: str = ""
    insurance_claim_number: str = ""
    insurance_adjuster_name: str = ""
    insurance_adjuster_phone: str = ""
    insurance_adjuster_email: str = ""
    property_damage: str = ""
    towed: bool = False
    tow_information: str = ""
    edr_status: str = ""
    warrant_obtained: bool = False
    vehicle_inspection_completed: bool = False
    nhtsa_recalls_checked: bool = False
    cdr_equipped: bool = False
    cdr_imaged: bool = False
    cdr_report_uploaded: bool = False
    released: bool = False
    release_date: str = ""
    release_information: str = ""
    damage_notes: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def description(self) -> str:
        vehicle = " ".join(part for part in (self.year, self.make, self.model) if part)
        return vehicle or "Unidentified vehicle"


@dataclass(slots=True)
class HitRunOverview:
    case_id: str
    is_hit_and_run: bool = False
    investigation_status: str = "Active"
    narrative: str = ""
    last_known_location: str = ""
    last_seen_date: str = ""
    last_seen_time: str = ""
    direction_of_travel: str = ""
    initial_source: str = ""
    follow_up_notes: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class HitRunVehicleLead:
    id: str
    case_id: str
    lead_number: str = ""
    status: str = "Possible"
    year_range: str = ""
    make: str = ""
    model: str = ""
    body_style: str = ""
    color: str = ""
    plate: str = ""
    plate_state: str = ""
    vin: str = ""
    distinguishing_features: str = ""
    observed_damage: str = ""
    missing_parts: str = ""
    last_seen_location: str = ""
    last_seen_date: str = ""
    last_seen_time: str = ""
    direction_of_travel: str = ""
    information_source: str = ""
    confidence: str = "Unknown"
    elimination_reason: str = ""
    notes: str = ""
    linked_vehicle_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def description(self) -> str:
        description = " ".join(
            value for value in (
                self.year_range,
                self.make,
                self.model,
                self.body_style,
                self.color,
            ) if value
        )
        return description or "Unidentified vehicle lead"


@dataclass(slots=True)
class HitRunPersonLead:
    id: str
    case_id: str
    lead_number: str = ""
    status: str = "Possible"
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    alias: str = ""
    sex: str = ""
    race: str = ""
    estimated_age: str = ""
    height: str = ""
    weight_build: str = ""
    hair: str = ""
    eyes: str = ""
    facial_hair: str = ""
    clothing: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    cell_phone: str = ""
    home_phone: str = ""
    work_phone: str = ""
    email: str = ""
    driver_license_number: str = ""
    driver_license_state: str = ""
    relationship_to_vehicle: str = ""
    reason_for_lead: str = ""
    information_source: str = ""
    confidence: str = "Unknown"
    vehicle_lead_id: Optional[str] = None
    follow_up: str = ""
    elimination_reason: str = ""
    linked_person_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def display_name(self) -> str:
        name = " ".join(
            value.strip()
            for value in (self.first_name, self.middle_name, self.last_name)
            if value.strip()
        )
        if self.alias:
            return f'{name or "Unnamed person lead"} (aka {self.alias})'
        return name or "Unnamed person lead"


@dataclass(slots=True)
class HitRunEvidenceItem:
    id: str
    case_id: str
    evidence_number: str = ""
    evidence_type: str = ""
    part_number: str = ""
    part_description: str = ""
    manufacturer_markings: str = ""
    color: str = ""
    material: str = ""
    quantity: str = ""
    damage_paint_transfer: str = ""
    recovery_location: str = ""
    recovery_date: str = ""
    recovery_time: str = ""
    recovered_by: str = ""
    vehicle_fitment: str = ""
    lab_status: str = ""
    vehicle_lead_id: Optional[str] = None
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class ChronologyEntry:
    id: str
    case_id: str
    event_date: str = ""
    event_time: str = ""
    category: str = "General"
    summary: str = ""
    details: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class CaseTask:
    id: str
    case_id: str
    category: str = "General"
    description: str = ""
    status: str = "Open"
    due_date: str = ""
    completed_date: str = ""
    notes: str = ""
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class PropertyReceipt:
    id: str
    case_id: str
    receipt_number: str = ""
    property_owner: str = ""
    lodging_type: str = "Evidence"
    lodged_location: str = ""
    lodged_date: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class PropertyReceiptItem:
    id: str
    receipt_id: str
    item_number: int = 1
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class InvestigativeChecklist:
    case_id: str
    completed_items: list[str] = field(default_factory=list)
    peer_review_status: str = "Not Started"
    sergeant_review_status: str = "Not Started"
    submitted_to_da_status: str = "Not Started"
    peer_review_date: str = ""
    sergeant_review_date: str = ""
    submitted_to_da_date: str = ""
    assigned_dda: str = ""
    da_case_number: str = ""
    court_case_number: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class ChargeDisposition:
    id: str
    case_id: str
    charge: str = ""
    disposition: str = ""
    created_at: str = ""
    updated_at: str = ""


def format_crash_location(road_name: str, intersection_road: str) -> str:
    """Return the shared Overview/PDF location from the crash-location fields."""
    return " / ".join(
        value.strip()
        for value in (road_name, intersection_road)
        if value and value.strip()
    )


@dataclass(slots=True)
class CrashDetails:
    case_id: str
    nearest_city: str = "Portland"
    county: str = "Multnomah"
    outside_city_feet: str = ""
    outside_city_miles: str = ""
    outside_city_direction: str = ""
    road_name: str = ""
    intersection_road: str = ""
    non_intersection_feet: str = ""
    non_intersection_miles: str = ""
    non_intersection_direction: str = ""
    non_intersection_reference: str = ""
    latitude: str = ""
    longitude: str = ""
    road_jurisdiction: str = ""
    team_notified_date: str = ""
    team_notified_time: str = ""
    investigator_en_route: str = ""
    investigator_arrival: str = ""
    sergeant: str = ""
    prosecutor_on_scene: str = ""
    medical_examiner_on_scene: str = ""
    criminalist_on_scene: str = ""
    scene_evidence: list[str] = field(default_factory=list)
    updated_at: str = ""


@dataclass(slots=True)
class ExchangeReportDetails:
    case_id: str
    assisting_officer: str = ""
    precinct: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class VideoSource:
    id: str
    case_id: str
    source: str = ""
    address: str = ""
    axon_status: str = "Unknown"
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class RoadConditions:
    case_id: str
    temperature: str = ""
    dew_point: str = ""
    winds: str = ""
    humidity: str = ""
    weather_condition: str = ""
    pressure: str = ""
    precipitation: str = ""
    visibility: str = ""
    weather_station: str = ""
    weather_time: str = ""
    other_weather: str = ""
    surface_composition: str = ""
    surface_condition: str = ""
    friction_value: str = ""
    lighting_conditions: str = ""
    sunrise: str = ""
    sunset: str = ""
    civil_twilight_morning: str = ""
    civil_twilight_evening: str = ""
    moonrise: str = ""
    moonset: str = ""
    moon_phase: str = ""
    streetlights_working: str = "Unknown"
    streetlight_notes: str = ""
    visual_obstructions: str = ""
    area_type: str = ""
    area_classifications: str = ""
    speed_limit: str = ""
    speed_limit_posted: str = "Unknown"
    speed_limit_location: str = ""
    curve_radius: str = ""
    chord: str = ""
    middle_ordinate: str = ""
    critical_speed: str = ""
    roadway_characteristics: str = ""
    traffic_controls: str = ""
    initial_point_of_collision: str = ""
    skid_test_notes: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class RoadwayRecord:
    id: str
    case_id: str
    roadway_tag: str = ""
    speed_limit: str = ""
    speed_limit_posted: str = "Unknown"
    speed_limit_location: str = ""
    curve_radius: str = ""
    chord: str = ""
    middle_ordinate: str = ""
    critical_speed: str = ""
    roadway_characteristics: str = ""
    traffic_controls: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class ParticipantDetails:
    person_id: str
    vehicle_id: Optional[str] = None
    occupant_position: str = ""
    injury_status: str = ""
    transported: str = "Unknown"
    transported_to: str = ""
    medical_records_status: str = ""
    hospital: str = ""
    height: str = ""
    weight: str = ""
    seatbelt_installed: str = "Unknown"
    seatbelt_used: str = "Unknown"
    airbag_deployed: str = "Unknown"
    helmet: str = "Not Applicable"
    ejected: str = "Unknown"
    extracted: str = "Unknown"
    autopsy_performed: str = "Unknown"
    autopsy_by: str = ""
    date_of_death: str = ""
    cause_of_death: str = ""
    next_of_kin_notified: str = "Unknown"
    next_of_kin_notified_by: str = ""
    injuries: str = ""
    injury_codes: str = ""
    evidence_obtained: str = ""
    evidence_items: str = ""
    lab_information: str = ""
    notes: str = ""
    updated_at: str = ""


def participant_is_deceased(details: ParticipantDetails) -> bool:
    status = details.injury_status.strip().casefold()
    return bool(
        details.date_of_death.strip()
        or any(marker in status for marker in ("kill", "fatal", "deceas"))
    )


@dataclass(slots=True)
class DriverProfile:
    person_id: str
    trip_from: str = ""
    trip_to: str = ""
    trip_purpose: str = ""
    last_stop_arrival: str = ""
    last_stop_departed: str = ""
    permanent_conditions: str = ""
    temporary_conditions: str = ""
    physical_condition_types: str = ""
    impairment_status: str = "Unknown"
    bac: str = ""
    testing: str = ""
    testing_methods: str = ""
    controlled_substances: str = ""
    impairment_notes: str = ""
    sleep_time: str = ""
    wake_time: str = ""
    hours_asleep: str = ""
    hours_awake: str = ""
    work_start: str = ""
    work_end: str = ""
    hours_worked: str = ""
    type_of_work: str = ""
    familiar_with_road: str = "Unknown"
    familiar_with_vehicle: str = "Unknown"
    years_driving: str = ""
    previous_collisions: str = ""
    previous_traffic_homicide: str = ""
    license_number: str = ""
    license_state: str = ""
    license_class: str = ""
    license_status: str = ""
    license_issued_date: str = ""
    license_expiration_date: str = ""
    endorsements: str = ""
    license_restrictions: str = ""
    license_restriction_explanation: str = ""
    license_restricted: str = "Unknown"
    notes: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class TireInspection:
    id: str
    vehicle_id: str
    position: str = ""
    make: str = ""
    design: str = ""
    size: str = ""
    pressure: str = ""
    tread_inside: str = ""
    tread_middle: str = ""
    tread_outside: str = ""
    condition: str = ""


@dataclass(slots=True)
class VehicleInspection:
    vehicle_id: str
    mileage: str = ""
    transmission: str = ""
    gear: str = ""
    steering: str = ""
    registered_weight: str = ""
    curb_weight: str = ""
    measured_weight: str = ""
    front_brakes: str = ""
    rear_brakes: str = ""
    brake_system: str = ""
    lighting_electrical: str = ""
    body_equipment: str = ""
    safety_systems: str = ""
    nicb_status: str = ""
    recall_status: str = ""
    vin_decode_status: str = ""
    headlights_equipped: str = "Unknown"
    headlights_operable: str = "Unknown"
    taillights_equipped: str = "Unknown"
    taillights_operable: str = "Unknown"
    tag_lights_equipped: str = "Unknown"
    tag_lights_operable: str = "Unknown"
    brake_lights_equipped: str = "Unknown"
    brake_lights_operable: str = "Unknown"
    turn_signals_equipped: str = "Unknown"
    turn_signals_operable: str = "Unknown"
    parking_lamps_equipped: str = "Unknown"
    parking_lamps_operable: str = "Unknown"
    other_lights_equipped: str = "Unknown"
    other_lights_operable: str = "Unknown"
    front_wipers_equipped: str = "Unknown"
    front_wipers_operable: str = "Unknown"
    rear_wipers_equipped: str = "Unknown"
    rear_wipers_operable: str = "Unknown"
    horn_equipped: str = "Unknown"
    horn_operable: str = "Unknown"
    headlight_switch_position: str = ""
    wiper_switch_position: str = ""
    ignition_position: str = ""
    radio_position: str = ""
    heater_position: str = ""
    headlamp_lens_condition: str = ""
    safety_glass_condition: str = ""
    inside_mirror: str = ""
    outside_mirrors: str = ""
    window_positions: str = ""
    seatbelts_equipped: str = "Unknown"
    shoulder_harnesses_equipped: str = "Unknown"
    airbag_status: str = ""
    body_interior_condition: str = ""
    body_exterior_condition: str = ""
    seatbelt_loading: str = "Unknown"
    steering_wheel_damage: str = "Unknown"
    device_observations: str = ""
    tire_contribution: str = "Unknown"
    tire_contribution_explanation: str = ""
    tire_notes: str = ""
    inspection_notes: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class WitnessDetails:
    person_id: str
    interviewed: str = "Unknown"
    interview_date: str = ""
    interviewer: str = ""
    significance: str = ""
    statement_summary: str = ""
    credibility_notes: str = ""
    follow_up: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class ContactRelationship:
    id: str
    case_id: str
    contact_type: str = ""
    subject_person_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    contact_person_id: Optional[str] = None
    contact_name: str = ""
    organization: str = ""
    phone: str = ""
    cell_phone: str = ""
    home_phone: str = ""
    work_phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class VRUAnalysis:
    id: str
    case_id: str
    person_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    upper_clothing: str = ""
    lower_clothing: str = ""
    roadway_position: str = ""
    movement_at_impact: str = ""
    projection_profile: str = ""
    projection_classifications: str = ""
    sightlines: str = ""
    driver_thought_process: str = ""
    driver_impairment: str = "Unknown"
    driver_sleep_information: str = ""
    vru_impairment: str = "Unknown"
    vru_impairment_notes: str = ""
    impact_location_on_vehicle: str = ""
    vehicle_approach_speed: str = ""
    vehicle_direction: str = ""
    vru_approach_speed: str = ""
    vru_direction: str = ""
    person_throw_distance: str = ""
    bicycle_throw_distance: str = ""
    light_meter_used: bool = False
    light_board_used: bool = False
    # Retained in storage so legacy case data is not discarded when edited.
    night_test_parameters: str = ""
    detection_distance: str = ""
    distance_adjustment: str = ""
    result_67_percent: str = ""
    result_15_percentile: str = ""
    prt_base: str = "0.50"
    prt_expected: str = ""
    prt_sun: str = ""
    prt_offset: str = ""
    prt_adjustment: str = ""
    prt_total: str = ""
    prt_justification: str = ""
    prt_factors: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class FileReference:
    id: str
    case_id: str
    category: str = ""
    title: str = ""
    file_path: str = ""
    reference_date: str = ""
    status: str = ""
    person_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class DiagramRecord:
    id: str
    case_id: str
    title: str = ""
    diagram_type: str = "Body"
    template_name: str = "body"
    person_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    annotations_json: str = "[]"
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class SurfaceObservation:
    id: str
    case_id: str
    location: str = ""
    composition: str = ""
    condition: str = ""
    friction_value: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class MotorcycleInspectionItem:
    item_number: int
    rating: str = ""
    measurement: str = ""
    comments: str = ""


@dataclass(slots=True)
class MotorcycleInspection:
    vehicle_id: str
    frame_number: str = ""
    engine_number: str = ""
    inspection_date: str = ""
    inspection_location: str = ""
    officer: str = ""
    dpsst: str = ""
    general_comments: str = ""
    items: list[MotorcycleInspectionItem] = field(default_factory=list)
    updated_at: str = ""
