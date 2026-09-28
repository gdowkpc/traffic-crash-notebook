from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from functools import partial
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    CondPageBreak,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import __version__
from .date_format import format_date_for_display, format_time_for_display, weekday_name
from .models import (
    CaseTask,
    CHECKLIST_DATE_FIELDS,
    CHECKLIST_STATUS_FIELDS,
    ChargeDisposition,
    ChronologyEntry,
    ContactRelationship,
    CrashCase,
    CrashDetails,
    DriverProfile,
    HitRunEvidenceItem,
    HitRunOverview,
    HitRunPersonLead,
    HitRunVehicleLead,
    INVESTIGATIVE_CHECKLIST_GROUPS,
    InvestigativeChecklist,
    MOTORCYCLE_INSPECTION_ITEMS,
    MotorcycleInspection,
    ParticipantDetails,
    Person,
    PropertyReceipt,
    PropertyReceiptItem,
    RoadConditions,
    RoadwayRecord,
    ROUTING_STATUS_OPTIONS,
    SurfaceObservation,
    TireInspection,
    Vehicle,
    VehicleInspection,
    VEHICLE_WORKFLOW_FIELDS,
    VideoSource,
    VRUAnalysis,
    WitnessDetails,
    contact_common_fields,
    format_crash_location,
    format_weather_measurement,
    participant_has_injury_or_death,
    participant_is_deceased,
    scene_evidence_for_output,
)
from .repository import CaseRepository
from .resources import tiu_logo_path


NAVY = colors.HexColor("#18344A")
BLUE = colors.HexColor("#2E6F95")
PALE_BLUE = colors.HexColor("#EAF2F7")
GRAY = colors.HexColor("#5D6870")
LIGHT_GRAY = colors.HexColor("#E4E8EB")
WARNING = colors.HexColor("#FFF3CD")
DECEASED_RED = "#B00020"
AGENCY_UNIT_HEADING = "PORTLAND POLICE BUREAU - TRAFFIC INVESTIGATIONS UNIT"


class _PacketCanvas(pdf_canvas.Canvas):
    """Add case identity and final page counts after ReportLab knows the total."""

    def __init__(
        self,
        *args,
        case_label: str,
        investigator: str,
        crash_date: str,
        footer_label: str,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._case_label = case_label
        self._investigator = investigator
        self._crash_date = crash_date
        self._footer_label = footer_label
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:  # noqa: N802 - ReportLab API name
        page_state = dict(self.__dict__)
        page_state.pop("_saved_page_states", None)
        self._saved_page_states.append(page_state)
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        saved_states = self._saved_page_states
        for page_state in saved_states:
            self.__dict__.update(page_state)
            self._draw_running_matter(page_count)
            super().showPage()
        super().save()

    def _draw_running_matter(self, page_count: int) -> None:
        width, height = self._pagesize
        self.saveState()
        self.setStrokeColor(LIGHT_GRAY)
        self.setLineWidth(0.5)
        self.line(0.65 * inch, height - 0.99 * inch, width - 0.65 * inch, height - 0.99 * inch)
        self.line(0.65 * inch, 0.5 * inch, width - 0.65 * inch, 0.5 * inch)

        header_parts = [f"CASE {self._case_label}"]
        if self._crash_date:
            header_parts.append(self._crash_date)
        self.setFillColor(GRAY)
        self.setFont("Helvetica-Bold", 7.5)
        self.drawString(0.65 * inch, height - 0.84 * inch, "  |  ".join(header_parts))
        if self._investigator:
            self.setFont("Helvetica", 7.5)
            self.drawRightString(width - 0.65 * inch, height - 0.84 * inch, self._investigator)

        self.setFont("Helvetica", 7.5)
        self.drawString(0.65 * inch, 0.31 * inch, self._footer_label)
        self.drawRightString(
            width - 0.65 * inch,
            0.31 * inch,
            f"Page {self._pageNumber} of {page_count}",
        )
        self.restoreState()


def _text(value: object) -> str:
    if value is None or value == "":
        return "-"
    return escape(str(value)).replace("\n", "<br/>")


def _field_cell(label: object, value: object, styles) -> list[Paragraph]:
    """Render one field label and its value together in a single table cell."""
    return [
        Paragraph(_text(label), styles["Label"]),
        Paragraph(_text(value), styles["Cell"]),
    ]


def _coordinates_field_cell(details: CrashDetails, styles) -> list[Paragraph]:
    """Render coordinates as a Google Maps link when both values are available."""
    latitude = details.latitude.strip()
    longitude = details.longitude.strip()
    coordinates = ", ".join(value for value in (latitude, longitude) if value)
    value = _text(coordinates)
    if latitude and longitude:
        query = quote(f"{latitude},{longitude}", safe=",.-")
        maps_url = f"https://www.google.com/maps/search/?api=1&query={query}"
        value = (
            f'<link href="{escape(maps_url)}" color="#2E6F95">'
            f"<u>{_text(coordinates)}</u></link>"
        )
    return [
        Paragraph("COORDINATES", styles["Label"]),
        Paragraph(value, styles["Cell"]),
    ]


def _name(person_id: str | None, people: dict[str, Person]) -> str:
    if not person_id:
        return "-"
    person = people.get(person_id)
    return person.display_name if person else "Unknown person"


def _person_address(person: Person) -> str:
    state_and_zip = " ".join(
        value for value in (person.state, person.zip_code) if value
    )
    return ", ".join(
        value for value in (person.address, person.city, state_and_zip) if value
    )


def export_case_pdf(
    repository: CaseRepository,
    case_id: str,
    destination: str | Path,
    *,
    working_copy: bool = True,
) -> Path:
    """Export either the full writable field packet or its compact counterpart."""
    case = repository.get_case(case_id)
    if not case:
        raise ValueError(f"Case not found: {case_id}")

    people_list = repository.list_people(case_id)
    people = {person.id: person for person in people_list}
    vehicles = repository.list_vehicles(case_id)
    chronology = repository.list_chronology(case_id)
    tasks = repository.list_tasks(case_id)
    property_receipts = repository.list_property_receipts(case_id)
    property_receipt_items = {
        receipt.id: repository.list_property_receipt_items(receipt.id)
        for receipt in property_receipts
    }
    conditions = repository.get_road_conditions(case_id)
    surface_observations = repository.list_surface_observations(case_id)
    roadway_records = repository.list_roadway_records(case_id)
    checklist = repository.get_investigative_checklist(case_id)
    charge_dispositions = repository.list_charge_dispositions(case_id)
    crash_details = repository.get_crash_details(case_id)
    video_sources = repository.list_video_sources(case_id)
    hit_run_overview = repository.get_hit_run_overview(case_id)
    hit_run_evidence = repository.list_hit_run_evidence_items(case_id)
    hit_run_vehicle_leads = repository.list_hit_run_vehicle_leads(case_id)
    hit_run_person_leads = repository.list_hit_run_person_leads(case_id)
    participant_details = {person.id: repository.get_participant_details(person.id) for person in people_list}
    driver_profiles = {person.id: repository.get_driver_profile(person.id) for person in people_list}
    witness_details = {person.id: repository.get_witness_details(person.id) for person in people_list}
    inspections = {vehicle.id: repository.get_vehicle_inspection(vehicle.id) for vehicle in vehicles}
    motorcycle_inspections = {
        vehicle.id: repository.get_motorcycle_inspection(vehicle.id) for vehicle in vehicles
    }
    tires = {vehicle.id: repository.list_tires(vehicle.id) for vehicle in vehicles}
    contacts = repository.list_contacts(case_id)
    vru_analyses = repository.list_vru_analyses(case_id)
    counts = repository.case_counts(case_id)

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    styles = _styles()
    packet_name = "Full Working Packet" if working_copy else "Compact Completed-Case Packet"
    cover_print_mode = "" if working_copy else packet_name.upper()
    footer_label = (
        "Not an official report"
        if working_copy
        else "Compact completed-case packet - not an official report"
    )
    document_title = (
        f"Traffic Crash Investigation Packet - {case.case_number or 'Untitled Case'}"
        if working_copy
        else f"Traffic Crash Notebook {packet_name} - {case.case_number or 'Untitled Case'}"
    )
    document = SimpleDocTemplate(
        str(destination),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=1.15 * inch,
        bottomMargin=0.7 * inch,
        title=document_title,
        author=case.investigator or "Traffic Crash Notebook",
        subject="Personal investigative working notes",
    )

    story: list[object] = []
    overview_location = format_crash_location(
        crash_details.road_name,
        crash_details.intersection_road,
    ) or case.location
    story.extend(
        _packet_cover(
            case,
            counts,
            checklist,
            styles,
            cover_print_mode,
            overview_location,
        )
    )
    if working_copy:
        story.extend(_write_in_area("Cover Notes", styles, lines=5))
    story.append(PageBreak())
    story.extend(_packet_case_section(
        case, checklist, charge_dispositions, crash_details, video_sources, counts, styles
    ))
    if working_copy:
        story.extend(_write_in_area("Packet / Crash Information Additions", styles, lines=5))

    has_conditions = (
        _has_detail(conditions, {"case_id", "updated_at"})
        or bool(surface_observations)
        or bool(roadway_records)
    )
    if working_copy or has_conditions:
        story.extend(_conditions_section(
            conditions,
            surface_observations,
            roadway_records,
            styles,
        ))
        if working_copy:
            story.extend(_write_in_area("Road / Weather Follow-Up", styles, lines=4))

    has_hit_run = _has_hit_run_content(
        hit_run_overview,
        hit_run_evidence,
        hit_run_vehicle_leads,
        hit_run_person_leads,
    )
    if has_hit_run:
        story.append(PageBreak() if working_copy else CondPageBreak(3.2 * inch))
        story.extend(_hit_run_section(
            hit_run_overview,
            hit_run_evidence,
            hit_run_vehicle_leads,
            hit_run_person_leads,
            people,
            {vehicle.id: vehicle for vehicle in vehicles},
            styles,
        ))
        if working_copy:
            story.extend(_write_in_area(
                "Hit-and-Run Additions / Lead Development",
                styles,
                lines=12,
            ))

    if working_copy or people_list:
        story.extend(_people_section(people_list, participant_details, styles))
        if working_copy:
            story.extend(_write_in_area("Additional People / Contact Updates", styles, lines=12))

    participant_story = _participant_sections(
        people_list, participant_details, driver_profiles, vehicles, styles
    )
    if participant_story:
        story.append(PageBreak() if working_copy else CondPageBreak(3.2 * inch))
        story.extend(participant_story)
        if working_copy:
            story.extend(_write_in_area("Participant / Driver Follow-Up", styles, lines=10))
    elif working_copy:
        story.append(PageBreak())
        story.extend(_empty_working_section(
            "Participant and Driver Details",
            "Use this area for participant, injury, transport, licensing, or driver-background updates.",
            styles,
            lines=8,
        ))

    if working_copy or vehicles:
        story.extend(_vehicles_section(
            vehicles, people, inspections, tires, motorcycle_inspections, styles
        ))
        if working_copy:
            story.extend(_write_in_area("Vehicle / Inspection Follow-Up", styles, lines=20))

    witness_contact_story = _witness_contact_sections(
        people_list, witness_details, contacts, people, vehicles, styles
    )
    if witness_contact_story:
        story.append(PageBreak() if working_copy else CondPageBreak(2.5 * inch))
        story.extend(witness_contact_story)
    elif working_copy:
        story.append(PageBreak())
        story.extend(_empty_working_section(
            "Witness Interviews and Contacts",
            "Record newly identified witnesses, interview information, and contact information.",
            styles,
            lines=9,
        ))

    vru_story = _vru_section(vru_analyses, people, vehicles, styles)
    if vru_story:
        story.extend(vru_story)
        if working_copy:
            story.extend(_write_in_area("VRU Analysis Follow-Up", styles, lines=8))
    elif working_copy:
        story.extend(_empty_working_section(
            "Vulnerable Road User Analysis",
            "Use when pedestrian, bicyclist, motorcyclist, or other vulnerable-road-user facts are developed.",
            styles,
            lines=5,
        ))

    if working_copy or property_receipts or tasks or chronology or case.notes:
        story.append(PageBreak())
        if working_copy or property_receipts:
            story.extend(_evidence_section(
                property_receipts,
                property_receipt_items,
                styles,
            ))
            if working_copy:
                story.extend(_write_in_area(
                    "Evidence Receipt / Property Item Continuation",
                    styles,
                    lines=6,
                ))
        if working_copy or tasks:
            story.extend(_tasks_section(tasks, styles))
            if working_copy:
                story.extend(_write_in_area("Task Continuation", styles, lines=6))
        if working_copy or chronology:
            story.extend(_chronology_section(chronology, styles))
            if working_copy:
                story.extend(_write_in_area("Journal Continuation", styles, lines=7))
        if working_copy or case.notes:
            story.extend(_notes_section(case, styles))
            if working_copy:
                story.extend(_write_in_area("General Handwritten Continuation", styles, lines=20))

    canvas_factory = partial(
        _PacketCanvas,
        case_label=case.case_number or "Untitled Case",
        investigator=case.investigator,
        crash_date=format_date_for_display(case.crash_date),
        footer_label=footer_label,
    )
    document.build(story, canvasmaker=canvas_factory)
    return destination


def export_case_compact_pdf(
    repository: CaseRepository,
    case_id: str,
    destination: str | Path,
) -> Path:
    """Export the complete entered record without blank handwriting sections."""
    return export_case_pdf(repository, case_id, destination, working_copy=False)


def export_case_summary_pdf(
    repository: CaseRepository,
    case_id: str,
    destination: str | Path,
) -> Path:
    """Export a concise review copy while the primary export remains the full packet."""
    case = repository.get_case(case_id)
    if not case:
        raise ValueError(f"Case not found: {case_id}")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    document = SimpleDocTemplate(
        str(destination),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=1.15 * inch,
        bottomMargin=0.7 * inch,
        title=f"Traffic Crash Notebook Quick Review - {case.case_number or 'Untitled Case'}",
        author=case.investigator or "Traffic Crash Notebook",
        subject="Concise investigative working-notes review",
    )
    crash_details = repository.get_crash_details(case_id)
    overview_location = format_crash_location(
        crash_details.road_name,
        crash_details.intersection_road,
    ) or case.location
    story: list[object] = []
    story.extend(
        _case_overview(
            case,
            repository.case_counts(case_id),
            styles,
            "QUICK REVIEW",
            overview_location,
        )
    )
    hit_run_overview = repository.get_hit_run_overview(case_id)
    hit_run_evidence = repository.list_hit_run_evidence_items(case_id)
    hit_run_vehicle_leads = repository.list_hit_run_vehicle_leads(case_id)
    hit_run_person_leads = repository.list_hit_run_person_leads(case_id)
    if _has_hit_run_content(
        hit_run_overview,
        hit_run_evidence,
        hit_run_vehicle_leads,
        hit_run_person_leads,
    ):
        people = {person.id: person for person in repository.list_people(case_id)}
        vehicles = {
            vehicle.id: vehicle for vehicle in repository.list_vehicles(case_id)
        }
        story.extend(_hit_run_section(
            hit_run_overview,
            hit_run_evidence,
            hit_run_vehicle_leads,
            hit_run_person_leads,
            people,
            vehicles,
            styles,
        ))
    property_receipts = repository.list_property_receipts(case_id)
    story.extend(_evidence_section(
        property_receipts,
        {
            receipt.id: repository.list_property_receipt_items(receipt.id)
            for receipt in property_receipts
        },
        styles,
    ))
    story.extend(_tasks_section(repository.list_tasks(case_id), styles))
    story.extend(_chronology_section(repository.list_chronology(case_id), styles))
    story.extend(_notes_section(case, styles))
    canvas_factory = partial(
        _PacketCanvas,
        case_label=case.case_number or "Untitled Case",
        investigator=case.investigator,
        crash_date=format_date_for_display(case.crash_date),
        footer_label="Quick review - not an official report",
    )
    document.build(story, canvasmaker=canvas_factory)
    return destination


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=15, leading=18, textColor=NAVY, alignment=TA_LEFT, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="CoverCaseNumber", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=23, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="CaseTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=26, textColor=NAVY, alignment=TA_LEFT, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="CaseSubtitle", parent=styles["Normal"], fontSize=10, leading=14,
        textColor=GRAY, spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="PrintMode", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8, leading=10, textColor=BLUE, spaceBefore=1, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="Subsection", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=BLUE, spaceBefore=7, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodySmall", parent=styles["BodyText"], fontSize=8.5, leading=11,
        textColor=colors.black,
    ))
    styles.add(ParagraphStyle(
        name="Label", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.5, leading=9, textColor=GRAY,
    ))
    styles.add(ParagraphStyle(
        name="Cell", parent=styles["Normal"], fontSize=8, leading=10,
    ))
    styles.add(ParagraphStyle(
        name="Empty", parent=styles["BodyText"], fontSize=9, leading=12,
        textColor=GRAY, fontName="Helvetica-Oblique",
    ))
    styles.add(ParagraphStyle(
        name="Metric", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=16, leading=18, textColor=NAVY, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="MetricLabel", parent=styles["Normal"], fontSize=7.5, leading=9,
        textColor=GRAY, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="CoverMetricLabel", parent=styles["Normal"], fontSize=6.4, leading=7.5,
        textColor=GRAY, alignment=TA_CENTER,
    ))
    return styles


def _cover_detail_table(
    labels: tuple[str, ...],
    values: tuple[str, ...],
    col_widths: list[float],
    styles,
) -> Table:
    table = Table(
        [
            [Paragraph(label, styles["Label"]) for label in labels],
            [Paragraph(_text(value), styles["BodySmall"]) for value in values],
        ],
        colWidths=col_widths,
    )
    table.setStyle(_standard_table_style())
    return table


def _cover_milestone(
    checklist: InvestigativeChecklist,
    item: str,
    date_attribute: str,
) -> str:
    completion_date = getattr(checklist, date_attribute)
    status = _checklist_item_status(checklist, item)
    if status == "Complete" and completion_date:
        return f"Complete - {format_date_for_display(completion_date)}"
    return status


def _checklist_item_status(
    checklist: InvestigativeChecklist,
    item: str,
) -> str:
    status_attribute = CHECKLIST_STATUS_FIELDS.get(item)
    if not status_attribute:
        return "Complete" if item in checklist.completed_items else "Open"
    status = getattr(checklist, status_attribute)
    if status not in ROUTING_STATUS_OPTIONS:
        status = "Not Started"
    date_attribute = CHECKLIST_DATE_FIELDS[item]
    if status == "Not Started" and (
        item in checklist.completed_items or getattr(checklist, date_attribute)
    ):
        return "Complete"
    return status


def _packet_cover(
    case: CrashCase,
    counts: dict[str, int],
    checklist: InvestigativeChecklist,
    styles,
    print_mode: str,
    location: str = "",
) -> list[object]:
    generated = datetime.now().astimezone().strftime("%m/%d/%Y at %I:%M %p")
    crash_date_time = " / ".join(value for value in (
        format_date_for_display(case.crash_date),
        format_time_for_display(case.crash_time),
    ) if value)
    title_content = [
        Paragraph(AGENCY_UNIT_HEADING, styles["Label"]),
        Paragraph("TRAFFIC CRASH INVESTIGATION PACKET", styles["CoverTitle"]),
        Paragraph(
            f"CASE {_text(case.case_number or 'Untitled Case')}",
            styles["CoverCaseNumber"],
        ),
    ]
    if print_mode:
        title_content.append(Paragraph(_text(print_mode), styles["PrintMode"]))
    title_content.append(Paragraph(
        f"Traffic Crash Notebook v{__version__} - generated {_text(generated)}",
        styles["CaseSubtitle"],
    ))
    logo_path = tiu_logo_path()
    if logo_path.exists():
        logo = Image(str(logo_path), width=0.9 * inch, height=0.87 * inch)
        title_table = Table(
            [[logo, title_content]],
            colWidths=[1.08 * inch, 5.52 * inch],
        )
        title_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story: list[object] = [title_table]
    else:
        story = title_content

    story.extend([
        _cover_detail_table(
            ("CRASH DATE / TIME", "CASE STATUS"),
            (
                crash_date_time,
                case.status,
            ),
            [3.3 * inch, 3.3 * inch],
            styles,
        ),
        Spacer(1, 0.07 * inch),
        _cover_detail_table(
            ("ASSIGNED INVESTIGATOR", "DPSST", "ASSIGNMENT"),
            (case.investigator, case.assigned_officer_dpsst, case.assignment),
            [2.8 * inch, 1.0 * inch, 2.8 * inch],
            styles,
        ),
        Spacer(1, 0.07 * inch),
        _cover_detail_table(
            ("CRASH LOCATION",),
            (location or case.location,),
            [6.6 * inch],
            styles,
        ),
        Spacer(1, 0.14 * inch),
    ])

    metric_values = (
        counts["people"],
        counts["vehicles"],
        counts["injured"],
        counts["fatal"],
        counts["vru"],
        counts["chronology"],
        counts["open_tasks"],
    )
    metric_labels = (
        "PEOPLE",
        "VEHICLES",
        "INJURED",
        "FATALITIES",
        "VRU",
        "JOURNAL ENTRIES",
        "OPEN TASKS",
    )
    metrics = Table(
        [
            [Paragraph(str(value), styles["Metric"]) for value in metric_values],
            [Paragraph(label, styles["CoverMetricLabel"]) for label in metric_labels],
        ],
        colWidths=[6.6 * inch / len(metric_values)] * len(metric_values),
    )
    metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8FA")),
        ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LIGHT_GRAY),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
    ]))
    story.extend([metrics, Paragraph("Review and DA Routing", styles["Subsection"])])

    routing = _cover_detail_table(
        ("PEER REVIEW", "MCT SERGEANT REVIEW", "SUBMITTED TO DA"),
        (
            _cover_milestone(
                checklist,
                "Report Peer Reviewed",
                "peer_review_date",
            ),
            _cover_milestone(
                checklist,
                "Report Sgt Reviewed",
                "sergeant_review_date",
            ),
            _cover_milestone(
                checklist,
                "Submitted to DA",
                "submitted_to_da_date",
            ),
        ),
        [2.2 * inch, 2.2 * inch, 2.2 * inch],
        styles,
    )
    da_routing = _cover_detail_table(
        ("ASSIGNED DDA", "DA CASE NUMBER", "COURT CASE NUMBER"),
        (
            checklist.assigned_dda,
            checklist.da_case_number,
            checklist.court_case_number,
        ),
        [2.2 * inch, 2.2 * inch, 2.2 * inch],
        styles,
    )
    story.extend([
        routing,
        Spacer(1, 0.07 * inch),
        da_routing,
    ])
    story.extend(_narrative_block("First Harmful Event", case.first_harmful_event, styles))
    story.extend(_narrative_block("Crash Summary", case.summary, styles))
    return story


def _case_overview(
    case: CrashCase,
    counts: dict[str, int],
    styles,
    print_mode: str,
    location: str = "",
) -> list[object]:
    generated = datetime.now().astimezone().strftime("%m/%d/%Y at %I:%M %p")
    title_content = [
        Paragraph(AGENCY_UNIT_HEADING, styles["Label"]),
        Paragraph(_text(case.case_number or "Untitled Case"), styles["CaseTitle"]),
        Paragraph(_text(print_mode), styles["PrintMode"]),
        Paragraph(f"Traffic Crash Notebook v{__version__} - generated {_text(generated)}", styles["CaseSubtitle"]),
    ]
    logo_path = tiu_logo_path()
    if logo_path.exists():
        logo = Image(str(logo_path), width=0.78 * inch, height=0.75 * inch)
        title_table = Table([[logo, title_content]], colWidths=[0.95 * inch, 5.65 * inch])
        title_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story: list[object] = [title_table]
    else:
        story = title_content
    facts = [
        [Paragraph("CRASH DATE", styles["Label"]), Paragraph("TIME", styles["Label"]),
         Paragraph("STATUS", styles["Label"]), Paragraph("INVESTIGATOR", styles["Label"])],
        [Paragraph(_text(format_date_for_display(case.crash_date)), styles["BodySmall"]), Paragraph(_text(format_time_for_display(case.crash_time)), styles["BodySmall"]),
         Paragraph(_text(case.status), styles["BodySmall"]), Paragraph(_text(case.investigator), styles["BodySmall"])],
        [Paragraph("LOCATION", styles["Label"]), "", "", ""],
        [Paragraph(_text(location or case.location), styles["BodySmall"]), "", "", ""],
    ]
    facts_table = Table(facts, colWidths=[1.55 * inch, 1.2 * inch, 1.55 * inch, 2.25 * inch])
    facts_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("BACKGROUND", (0, 2), (-1, 2), PALE_BLUE),
        ("SPAN", (0, 2), (-1, 2)), ("SPAN", (0, 3), (-1, 3)),
        ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("INNERGRID", (0, 0), (-1, 1), 0.35, LIGHT_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([facts_table, Spacer(1, 0.18 * inch)])

    metric_data = [
        [Paragraph(str(counts["people"]), styles["Metric"]),
         Paragraph(str(counts["vehicles"]), styles["Metric"]),
         Paragraph(str(counts["chronology"]), styles["Metric"]),
         Paragraph(str(counts["open_tasks"]), styles["Metric"])],
        [Paragraph("PEOPLE", styles["MetricLabel"]), Paragraph("VEHICLES", styles["MetricLabel"]),
         Paragraph("JOURNAL ENTRIES", styles["MetricLabel"]), Paragraph("OPEN / WAITING TASKS", styles["MetricLabel"])],
    ]
    metrics = Table(metric_data, colWidths=[1.65 * inch] * 4)
    metrics.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F8FA")),
        ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LIGHT_GRAY),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story.append(metrics)
    story.extend(_narrative_block("First Harmful Event", case.first_harmful_event, styles))
    story.extend(_narrative_block("Crash summary", case.summary, styles))
    return story


def _narrative_block(title: str, text: str, styles) -> list[object]:
    return [
        Paragraph(title, styles["Section"]),
        Paragraph(_text(text) if text else "No information entered.", styles["BodySmall"] if text else styles["Empty"]),
    ]


def _write_in_area(title: str, styles, *, lines: int = 4) -> list[object]:
    """Create ruled space that remains useful after the packet is printed."""
    rows: list[list[object]] = [[Paragraph(title.upper(), styles["Label"])]]
    rows.extend([[""] for _ in range(lines)])
    row_heights = [0.26 * inch] + [0.31 * inch] * lines
    table = Table(
        rows,
        colWidths=[6.6 * inch],
        rowHeights=row_heights,
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LIGHT_GRAY),
        ("LEFTPADDING", (0, 0), (-1, 0), 6),
        ("RIGHTPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]))
    required_height = (0.43 + 0.31 * lines) * inch
    return [CondPageBreak(required_height), Spacer(1, 0.12 * inch), table]


def _empty_working_section(
    title: str,
    guidance: str,
    styles,
    *,
    lines: int,
) -> list[object]:
    story: list[object] = [
        CondPageBreak((0.95 + 0.31 * lines) * inch),
        Paragraph(title, styles["Section"]),
        Paragraph(guidance, styles["BodySmall"]),
    ]
    story.extend(_write_in_area("Handwritten Additions / Follow-Up", styles, lines=lines))
    return story


def _packet_case_section(
    case: CrashCase,
    checklist: InvestigativeChecklist,
    charges: list[ChargeDisposition],
    details: CrashDetails,
    video_sources: list[VideoSource],
    counts: dict[str, int],
    styles,
) -> list[object]:
    story: list[object] = [Paragraph("Investigative Packet", styles["Section"])]
    day_of_week = weekday_name(case.crash_date)

    checklist_rows: list[list[Paragraph]] = [[
        Paragraph("AREA", styles["Label"]),
        Paragraph("MILESTONE", styles["Label"]),
        Paragraph("STATUS", styles["Label"]),
        Paragraph("DATE", styles["Label"]),
    ]]
    for group, items in INVESTIGATIVE_CHECKLIST_GROUPS:
        for item in items:
            date_attribute = CHECKLIST_DATE_FIELDS.get(item)
            completion_date = (
                getattr(checklist, date_attribute)
                if date_attribute
                else ""
            )
            checklist_rows.append([
                Paragraph(_text(group), styles["Cell"]),
                Paragraph(_text(item), styles["Cell"]),
                Paragraph(
                    _checklist_item_status(checklist, item),
                    styles["Cell"],
                ),
                Paragraph(
                    _text(format_date_for_display(completion_date)),
                    styles["Cell"],
                ),
            ])
    checklist_table = Table(
        checklist_rows,
        colWidths=[1.1 * inch, 3.5 * inch, 0.85 * inch, 1.15 * inch],
        repeatRows=1,
    )
    checklist_table.setStyle(_standard_table_style())
    story.extend([Paragraph("Investigative Checklist", styles["Subsection"]), checklist_table])

    da_rows = [
        [
            Paragraph("ASSIGNED DDA", styles["Label"]),
            Paragraph("DA CASE NUMBER", styles["Label"]),
            Paragraph("COURT CASE NUMBER", styles["Label"]),
        ],
        [
            Paragraph(_text(checklist.assigned_dda), styles["Cell"]),
            Paragraph(_text(checklist.da_case_number), styles["Cell"]),
            Paragraph(_text(checklist.court_case_number), styles["Cell"]),
        ],
    ]
    da_table = Table(da_rows, colWidths=[2.2 * inch, 2.2 * inch, 2.2 * inch])
    da_table.setStyle(_standard_table_style())
    story.extend([Paragraph("District Attorney / Charges", styles["Subsection"]), da_table])
    if charges:
        charge_rows = [[Paragraph("CHARGE", styles["Label"]), Paragraph("DISPOSITION", styles["Label"])]]
        charge_rows.extend([
            [Paragraph(_text(record.charge), styles["Cell"]), Paragraph(_text(record.disposition), styles["Cell"])]
            for record in charges
        ])
        charge_table = Table(charge_rows, colWidths=[3.3 * inch, 3.3 * inch], repeatRows=1)
        charge_table.setStyle(_standard_table_style())
        story.append(charge_table)

    story.append(CondPageBreak(3.6 * inch))
    story.append(Paragraph("Crash Information", styles["Subsection"]))
    location = format_crash_location(details.road_name, details.intersection_road)
    non_intersection_distance = " / ".join(value for value in (
        f"{details.non_intersection_feet} ft" if details.non_intersection_feet else "",
        f"{details.non_intersection_miles} mi" if details.non_intersection_miles else "",
    ) if value)
    non_intersection = " ".join(value for value in (
        non_intersection_distance,
        details.non_intersection_direction,
        (
            "of intersection"
            if details.non_intersection_direction
            else "from intersection"
        ) if non_intersection_distance or details.non_intersection_direction else "",
    ) if value)
    scene_evidence = scene_evidence_for_output(
        details.scene_evidence,
        has_video_sources=bool(video_sources),
    )
    response = [
        [_field_cell("DATE / DAY / TIME", " / ".join(value for value in (
            format_date_for_display(case.crash_date), day_of_week,
            format_time_for_display(case.crash_time),
        ) if value), styles),
         _field_cell("CITY / COUNTY", " / ".join(value for value in (
             details.nearest_city, details.county,
         ) if value), styles)],
        [_field_cell("LOCATION", location or case.location, styles),
         _field_cell("NOT AT INTERSECTION", non_intersection, styles)],
        [_coordinates_field_cell(details, styles),
         _field_cell("JURISDICTION", details.road_jurisdiction, styles)],
        [_field_cell("TEAM NOTIFIED", " ".join(value for value in (
            format_date_for_display(details.team_notified_date),
            details.team_notified_time,
        ) if value), styles),
         _field_cell("EN ROUTE / ARRIVAL", " / ".join(value for value in (
             details.investigator_en_route, details.investigator_arrival,
         ) if value), styles)],
        [_field_cell("SCENE PERSONNEL", "; ".join(value for value in (
            f"MCT Sergeant: {details.sergeant}" if details.sergeant else "",
            f"Prosecutor: {details.prosecutor_on_scene}"
            if details.prosecutor_on_scene else "",
            f"MDI: {details.medical_examiner_on_scene}"
            if details.medical_examiner_on_scene else "",
        ) if value), styles),
         _field_cell("RECORD COUNTS", (
             f"{counts['vehicles']} vehicles; {counts['injured']} injured; "
             f"{counts['fatal']} fatal; {counts['vru']} VRU"
         ), styles)],
        [_field_cell("SCENE EVIDENCE", ", ".join(scene_evidence), styles),
         _field_cell("VIDEO SOURCES", str(len(video_sources)), styles)],
    ]
    response_table = Table(response, colWidths=[3.3 * inch, 3.3 * inch])
    response_table.setStyle(_standard_table_style())
    story.append(response_table)
    if video_sources:
        video_rows = [[
            Paragraph("VIDEO SOURCE", styles["Label"]),
            Paragraph("ADDRESS", styles["Label"]),
            Paragraph("UPLOADED TO AXON", styles["Label"]),
            Paragraph("NOTES", styles["Label"]),
        ]]
        video_rows.extend([
            [Paragraph(_text(record.source), styles["Cell"]),
             Paragraph(_text(record.address), styles["Cell"]),
             Paragraph(_text(record.axon_status), styles["Cell"]),
             Paragraph(_text(record.notes), styles["Cell"])]
            for record in video_sources
        ])
        video_table = Table(
            video_rows,
            colWidths=[1.65 * inch, 2.1 * inch, 1.25 * inch, 1.6 * inch],
            repeatRows=1,
        )
        video_table.setStyle(_standard_table_style())
        story.extend([Paragraph("Video Sources", styles["Subsection"]), video_table])
    return story


def _has_detail(record, ignored: set[str]) -> bool:
    for key, value in asdict(record).items():
        if key in ignored:
            continue
        if value not in (None, "", "Unknown"):
            return True
    return False


def _has_hit_run_content(
    overview: HitRunOverview,
    evidence: list[HitRunEvidenceItem],
    vehicle_leads: list[HitRunVehicleLead],
    person_leads: list[HitRunPersonLead],
) -> bool:
    return bool(
        overview.is_hit_and_run
        or evidence
        or vehicle_leads
        or person_leads
        or _has_detail(
            overview,
            {
                "case_id",
                "is_hit_and_run",
                "investigation_status",
                "updated_at",
            },
        )
    )


def _hit_run_detail_table(rows: list[tuple[str, str, str, str]], styles) -> Table:
    data = [
        [
            _field_cell(left_label, left_value, styles),
            _field_cell(right_label, right_value, styles),
        ]
        for left_label, left_value, right_label, right_value in rows
    ]
    table = Table(data, colWidths=[3.3 * inch, 3.3 * inch])
    table.setStyle(_standard_table_style())
    return table


def _append_hit_run_narratives(
    story: list[object],
    values: tuple[tuple[str, str], ...],
    styles,
) -> None:
    for label, value in values:
        if value:
            story.extend([
                Paragraph(_text(label), styles["Label"]),
                Paragraph(_text(value), styles["BodySmall"]),
            ])


def _hit_run_section(
    overview: HitRunOverview,
    evidence: list[HitRunEvidenceItem],
    vehicle_leads: list[HitRunVehicleLead],
    person_leads: list[HitRunPersonLead],
    people: dict[str, Person],
    vehicles: dict[str, Vehicle],
    styles,
) -> list[object]:
    story: list[object] = [
        Paragraph("Hit &amp; Run Investigation", styles["Section"]),
    ]
    last_seen = " ".join(
        value for value in (
            format_date_for_display(overview.last_seen_date),
            overview.last_seen_time,
        ) if value
    )
    story.append(_hit_run_detail_table([
        (
            "CLASSIFICATION",
            "Hit-and-run investigation" if overview.is_hit_and_run else "Hit-and-run lead data entered",
            "STATUS",
            overview.investigation_status,
        ),
        (
            "LAST KNOWN LOCATION",
            overview.last_known_location,
            "LAST SEEN",
            last_seen,
        ),
        (
            "DIRECTION OF TRAVEL",
            overview.direction_of_travel,
            "INITIAL SOURCE",
            overview.initial_source,
        ),
    ], styles))
    _append_hit_run_narratives(
        story,
        (
            ("Hit-and-Run Narrative", overview.narrative),
            ("Hit-and-Run Follow-Up", overview.follow_up_notes),
        ),
        styles,
    )

    vehicle_lead_labels = {
        lead.id: lead.lead_number or "Unnumbered vehicle lead"
        for lead in vehicle_leads
    }

    story.append(CondPageBreak(2.7 * inch if evidence else 0.8 * inch))
    story.append(Paragraph("Recovered Parts / Evidence", styles["Subsection"]))
    if not evidence:
        story.append(Paragraph("No recovered parts or hit-and-run evidence entered.", styles["Empty"]))
    for index, record in enumerate(evidence):
        if index:
            story.append(CondPageBreak(2.4 * inch))
        heading = " - ".join(
            value for value in (
                record.evidence_number or "Unnumbered evidence",
                record.evidence_type,
            ) if value
        )
        story.append(Paragraph(_text(heading), styles["Subsection"]))
        recovery = " ".join(
            value for value in (
                format_date_for_display(record.recovery_date),
                record.recovery_time,
            ) if value
        )
        story.append(_hit_run_detail_table([
            ("PART NUMBER", record.part_number, "QUANTITY", record.quantity),
            (
                "MARKINGS",
                record.manufacturer_markings,
                "COLOR / MATERIAL",
                " / ".join(value for value in (record.color, record.material) if value),
            ),
            ("RECOVERED", recovery, "RECOVERED BY", record.recovered_by),
            (
                "RECOVERY LOCATION",
                record.recovery_location,
                "VEHICLE LEAD",
                vehicle_lead_labels.get(record.vehicle_lead_id, ""),
            ),
            ("LAB STATUS", record.lab_status, "EVIDENCE TYPE", record.evidence_type),
        ], styles))
        _append_hit_run_narratives(
            story,
            (
                ("Part / Evidence Description", record.part_description),
                ("Damage / Paint Transfer", record.damage_paint_transfer),
                ("Possible Vehicle Fitment", record.vehicle_fitment),
                ("Evidence Notes", record.notes),
            ),
            styles,
        )

    story.append(CondPageBreak(3.0 * inch if vehicle_leads else 0.8 * inch))
    story.append(Paragraph("Possible Vehicle Leads", styles["Subsection"]))
    if not vehicle_leads:
        story.append(Paragraph("No possible vehicle leads entered.", styles["Empty"]))
    for index, lead in enumerate(vehicle_leads):
        if index:
            story.append(CondPageBreak(2.7 * inch))
        heading = f"{lead.lead_number or 'Unnumbered lead'} - {lead.description}"
        linked_vehicle = vehicles.get(lead.linked_vehicle_id)
        linked_vehicle_label = (
            f"{linked_vehicle.vehicle_number} - {linked_vehicle.description}"
            if linked_vehicle else ""
        )
        last_seen = " ".join(
            value for value in (
                format_date_for_display(lead.last_seen_date),
                lead.last_seen_time,
            ) if value
        )
        story.append(Paragraph(_text(heading), styles["Subsection"]))
        story.append(_hit_run_detail_table([
            ("STATUS", lead.status, "CONFIDENCE", lead.confidence),
            (
                "YEAR / MAKE / MODEL",
                " ".join(value for value in (lead.year_range, lead.make, lead.model) if value),
                "BODY STYLE / COLOR",
                " / ".join(value for value in (lead.body_style, lead.color) if value),
            ),
            (
                "PLATE",
                " ".join(value for value in (lead.plate_state, lead.plate) if value),
                "VIN",
                lead.vin,
            ),
            (
                "LAST SEEN",
                last_seen,
                "DIRECTION",
                lead.direction_of_travel,
            ),
            (
                "LAST SEEN LOCATION",
                lead.last_seen_location,
                "LINKED VEHICLE",
                linked_vehicle_label,
            ),
            (
                "INFORMATION SOURCE",
                lead.information_source,
                "LINK STATUS",
                "Confirmed record linked" if linked_vehicle else "Not linked",
            ),
        ], styles))
        _append_hit_run_narratives(
            story,
            (
                ("Distinguishing Features", lead.distinguishing_features),
                ("Observed / Expected Damage", lead.observed_damage),
                ("Missing Parts", lead.missing_parts),
                ("Elimination Reason", lead.elimination_reason),
                ("Vehicle Lead Notes", lead.notes),
            ),
            styles,
        )

    story.append(CondPageBreak(3.3 * inch if person_leads else 0.8 * inch))
    story.append(Paragraph("Person Leads / Possible Suspects", styles["Subsection"]))
    if not person_leads:
        story.append(Paragraph("No person leads or possible suspects entered.", styles["Empty"]))
    for index, lead in enumerate(person_leads):
        if index:
            story.append(CondPageBreak(3.0 * inch))
        heading = f"{lead.lead_number or 'Unnumbered lead'} - {lead.display_name}"
        linked_person = people.get(lead.linked_person_id)
        associated_vehicle = vehicle_lead_labels.get(lead.vehicle_lead_id, "")
        address = ", ".join(
            value for value in (
                lead.address,
                lead.city,
                " ".join(value for value in (lead.state, lead.zip_code) if value),
            ) if value
        )
        phones = "; ".join(
            value for value in (
                f"Cell {lead.cell_phone}" if lead.cell_phone else "",
                f"Home {lead.home_phone}" if lead.home_phone else "",
                f"Work {lead.work_phone}" if lead.work_phone else "",
                lead.email,
            ) if value
        )
        physical = "; ".join(
            value for value in (
                " / ".join(value for value in (lead.sex, lead.race) if value),
                f"Age {lead.estimated_age}" if lead.estimated_age else "",
                " / ".join(value for value in (lead.height, lead.weight_build) if value),
                " / ".join(value for value in (lead.hair, lead.eyes) if value),
                f"Facial hair: {lead.facial_hair}" if lead.facial_hair else "",
            ) if value
        )
        story.append(Paragraph(_text(heading), styles["Subsection"]))
        story.append(_hit_run_detail_table([
            ("STATUS", lead.status, "CONFIDENCE", lead.confidence),
            ("PHYSICAL DESCRIPTION", physical, "CLOTHING", lead.clothing),
            ("ADDRESS", address, "CONTACT", phones),
            (
                "DRIVER LICENSE",
                " ".join(
                    value for value in (
                        lead.driver_license_state,
                        lead.driver_license_number,
                    ) if value
                ),
                "VEHICLE LEAD",
                associated_vehicle,
            ),
            (
                "VEHICLE RELATIONSHIP",
                lead.relationship_to_vehicle,
                "LINKED PERSON",
                linked_person.display_name if linked_person else "",
            ),
        ], styles))
        _append_hit_run_narratives(
            story,
            (
                ("Reason for Lead / Possible Suspect", lead.reason_for_lead),
                ("Information Source", lead.information_source),
                ("Follow-up", lead.follow_up),
                ("Elimination Reason", lead.elimination_reason),
            ),
            styles,
        )
    return story


def _conditions_section(
    conditions: RoadConditions,
    surface_observations: list[SurfaceObservation],
    roadway_records: list[RoadwayRecord],
    styles,
) -> list[object]:
    story: list[object] = [Paragraph("Road and Weather Conditions", styles["Section"])]
    if (
        not _has_detail(conditions, {"case_id", "updated_at"})
        and not surface_observations
        and not roadway_records
    ):
        story.append(Paragraph("No detailed road or weather conditions entered.", styles["Empty"]))
        return story
    temperature = format_weather_measurement("temperature", conditions.temperature)
    dew_point = format_weather_measurement("dew_point", conditions.dew_point)
    winds = format_weather_measurement("winds", conditions.winds)
    humidity = format_weather_measurement("humidity", conditions.humidity)
    pressure = format_weather_measurement("pressure", conditions.pressure)
    precipitation = format_weather_measurement(
        "precipitation",
        conditions.precipitation,
    )
    visibility = format_weather_measurement("visibility", conditions.visibility)
    data = [
        [_field_cell("TEMPERATURE", temperature, styles),
         _field_cell("WEATHER", conditions.weather_condition, styles)],
        [_field_cell("WEATHER STATION", conditions.weather_station, styles),
         _field_cell("TIME OF READING", conditions.weather_time, styles)],
        [_field_cell("VISIBILITY", visibility, styles), ""],
        [_field_cell("WINDS", winds, styles),
         _field_cell("PRECIPITATION", precipitation, styles)],
        [_field_cell("HUMIDITY / DEW POINT", " / ".join(
            x for x in (humidity, dew_point) if x
        ), styles), _field_cell("PRESSURE", pressure, styles)],
        [_field_cell("AREA CLASSIFICATIONS", conditions.area_classifications, styles),
         _field_cell("AREA TYPE", conditions.area_type, styles)],
    ]
    table = Table(data, colWidths=[3.3 * inch, 3.3 * inch])
    table.setStyle(_standard_table_style())
    table.setStyle(TableStyle([("SPAN", (0, 2), (1, 2))]))
    story.append(table)
    if conditions.other_weather:
        story.extend([
            Paragraph("Other Weather Information", styles["Subsection"]),
            Paragraph(_text(conditions.other_weather), styles["BodySmall"]),
        ])
    if roadway_records:
        roadway_rows = [[Paragraph(item, styles["Label"]) for item in (
            "ROADWAY",
            "SPEED",
            "POSTED / LOCATION",
            "CURVE / CRITICAL SPEED",
            "CHARACTERISTICS / CONTROLS",
        )]]
        for roadway in roadway_records:
            speed = f"{roadway.speed_limit} mph" if roadway.speed_limit else ""
            posting = "; ".join(
                value
                for value in (
                    f"Posted: {roadway.speed_limit_posted}"
                    if roadway.speed_limit_posted
                    else "",
                    roadway.speed_limit_location,
                )
                if value
            )
            curve = "; ".join(
                value
                for value in (
                    f"R {roadway.curve_radius}" if roadway.curve_radius else "",
                    f"C {roadway.chord}" if roadway.chord else "",
                    f"MO {roadway.middle_ordinate}"
                    if roadway.middle_ordinate
                    else "",
                    f"Speed {roadway.critical_speed}"
                    if roadway.critical_speed
                    else "",
                )
                if value
            )
            details = "; ".join(
                value
                for value in (
                    f"Characteristics: {roadway.roadway_characteristics}"
                    if roadway.roadway_characteristics
                    else "",
                    f"Controls: {roadway.traffic_controls}"
                    if roadway.traffic_controls
                    else "",
                )
                if value
            )
            roadway_rows.append([
                Paragraph(_text(roadway.roadway_tag), styles["Cell"]),
                Paragraph(_text(speed), styles["Cell"]),
                Paragraph(_text(posting), styles["Cell"]),
                Paragraph(_text(curve), styles["Cell"]),
                Paragraph(_text(details), styles["Cell"]),
            ])
        roadway_table = Table(
            roadway_rows,
            colWidths=[1.15 * inch, 0.65 * inch, 1.15 * inch, 1.45 * inch, 2.2 * inch],
            repeatRows=1,
        )
        roadway_table.setStyle(_standard_table_style())
        story.extend([
            Paragraph("Roadways", styles["Subsection"]),
            roadway_table,
        ])
    lighting_data = [
        [_field_cell("SUNRISE", conditions.sunrise, styles),
         _field_cell("SUNSET", conditions.sunset, styles)],
        [_field_cell("MORNING CIVIL TWILIGHT", conditions.civil_twilight_morning, styles),
         _field_cell("EVENING CIVIL TWILIGHT", conditions.civil_twilight_evening, styles)],
        [_field_cell("MOONRISE", conditions.moonrise, styles),
         _field_cell("MOONSET", conditions.moonset, styles)],
        [_field_cell("MOON PHASE", conditions.moon_phase, styles),
         _field_cell("STREETLIGHTS", conditions.streetlights_working, styles)],
    ]
    lighting_table = Table(
        lighting_data,
        colWidths=[3.3 * inch, 3.3 * inch],
    )
    lighting_table.setStyle(_standard_table_style())
    story.extend([
        Paragraph("Lighting and Visibility", styles["Subsection"]),
        lighting_table,
    ])
    narratives = (
        ("Lighting Conditions", conditions.lighting_conditions),
        ("Streetlight Notes", conditions.streetlight_notes),
        ("Visual Obstructions", conditions.visual_obstructions),
        ("Initial Point of Collision", conditions.initial_point_of_collision),
        ("Skid Test / Drag Sled Notes", conditions.skid_test_notes),
    )
    for title, value in narratives:
        if value:
            story.extend([Paragraph(title, styles["Subsection"]), Paragraph(_text(value), styles["BodySmall"])])
    if surface_observations:
        surface_rows = [[Paragraph(item, styles["Label"]) for item in (
            "LOCATION", "COMPOSITION", "CONDITION", "FRICTION", "NOTES"
        )]]
        for surface in surface_observations:
            surface_rows.append([
                Paragraph(_text(surface.location), styles["Cell"]),
                Paragraph(_text(surface.composition), styles["Cell"]),
                Paragraph(_text(surface.condition), styles["Cell"]),
                Paragraph(_text(surface.friction_value), styles["Cell"]),
                Paragraph(_text(surface.notes), styles["Cell"]),
            ])
        surface_table = Table(
            surface_rows,
            colWidths=[1.25 * inch, 1.3 * inch, 1.1 * inch, 0.8 * inch, 2.15 * inch],
            repeatRows=1,
        )
        surface_table.setStyle(_standard_table_style())
        story.extend([Paragraph("Surface Observations", styles["Subsection"]), surface_table])
    return story


def _people_section(
    people: list[Person],
    participant_details: dict[str, ParticipantDetails],
    styles,
) -> list[object]:
    story: list[object] = [Paragraph("People", styles["Section"])]
    if not people:
        story.append(Paragraph("No people entered.", styles["Empty"]))
        return story
    data = [[Paragraph(item, styles["Label"]) for item in (
        "NAME", "ROLE(S)", "IDENTITY", "ADDRESS", "CONTACT", "OCCUPATION / NOTES"
    )]]
    for person in people:
        role_markup = _text(", ".join(person.roles))
        details = participant_details.get(person.id)
        if details and participant_is_deceased(details):
            role_markup += (
                f'<br/><font color="{DECEASED_RED}"><b>DECEASED</b></font>'
            )
        phones = "; ".join(value for value in (
            f"Cell {person.cell_phone}" if person.cell_phone else "",
            f"Home {person.home_phone}" if person.home_phone else "",
            f"Work {person.work_phone}" if person.work_phone else "",
            person.email,
        ) if value)
        sex_and_race = " / ".join(
            value for value in (person.sex, person.race) if value
        )
        display_dob = format_date_for_display(person.dob)
        identity_lines = [
            _text(value)
            for value in (
                sex_and_race,
                f"DOB: {display_dob}" if display_dob else "",
            )
            if value
        ]
        data.append([
            Paragraph(_text(person.display_name), styles["Cell"]),
            Paragraph(role_markup, styles["Cell"]),
            Paragraph("<br/>".join(identity_lines) or "-", styles["Cell"]),
            Paragraph(_text(_person_address(person)), styles["Cell"]),
            Paragraph(_text(phones), styles["Cell"]),
            Paragraph(_text("; ".join(value for value in (
                person.occupation,
                f"Business: {person.business_address}" if person.business_address else "",
                person.notes,
            ) if value)), styles["Cell"]),
        ])
    table = Table(
        data,
        colWidths=[1.1 * inch, 0.85 * inch, 1.05 * inch, 1.25 * inch, 1.15 * inch, 1.2 * inch],
        repeatRows=1,
    )
    table.setStyle(_standard_table_style())
    story.append(table)
    return story


def _participant_sections(
    people: list[Person],
    participant_details: dict[str, ParticipantDetails],
    driver_profiles: dict[str, DriverProfile],
    vehicles: list[Vehicle],
    styles,
) -> list[object]:
    vehicle_names = {vehicle.id: f"{vehicle.vehicle_number} - {vehicle.description}" for vehicle in vehicles}
    qualifying = [
        person for person in people
        if _has_detail(participant_details[person.id], {"person_id", "updated_at"})
        or _has_detail(driver_profiles[person.id], {"person_id", "updated_at"})
    ]
    if not qualifying:
        return []
    story: list[object] = [Paragraph("Participant and Driver Details", styles["Section"])]
    for person in qualifying:
        details = participant_details[person.id]
        profile = driver_profiles[person.id]
        person_type = "; ".join(
            role.strip() for role in person.roles if role and role.strip()
        ) or "Not specified"
        story.append(CondPageBreak(3.0 * inch))
        story.append(Paragraph(
            f"{_text(person.display_name)} - Person Type: {_text(person_type)}",
            styles["Subsection"],
        ))
        if _has_detail(details, {"person_id", "updated_at"}):
            has_injury_or_death = participant_has_injury_or_death(details)
            participant_data = [
                [_field_cell("GENDER / RACE", " / ".join(
                    value for value in (person.sex, person.race) if value
                ), styles), _field_cell(
                    "DOB", format_date_for_display(person.dob), styles
                )],
            ]
            if has_injury_or_death:
                participant_data.extend([
                    [_field_cell("VEHICLE / POSITION", "; ".join(
                        x for x in (
                            vehicle_names.get(details.vehicle_id, ""),
                            details.occupant_position,
                        ) if x
                    ), styles), _field_cell("INJURY STATUS", details.injury_status, styles)],
                    [_field_cell("HEIGHT / WEIGHT", " / ".join(
                        value for value in (details.height, details.weight) if value
                    ), styles), _field_cell("INJURY CODES", details.injury_codes, styles)],
                ])
            else:
                participant_data.append([
                    _field_cell("VEHICLE / POSITION", "; ".join(
                        x for x in (
                            vehicle_names.get(details.vehicle_id, ""),
                            details.occupant_position,
                        ) if x
                    ), styles),
                    _field_cell("HEIGHT / WEIGHT", " / ".join(
                        value for value in (details.height, details.weight) if value
                    ), styles),
                ])
            participant_data.extend([
                [_field_cell("TRANSPORT", (
                    f"{details.transported} - {details.transported_to}"
                    if details.transported_to else details.transported
                ), styles), _field_cell("HOSPITAL / RECORDS", "; ".join(
                    value for value in (
                        details.hospital, details.medical_records_status,
                    ) if value
                ), styles)],
                [_field_cell("RESTRAINT / AIR BAG", (
                    f"Installed {details.seatbelt_installed}; "
                    f"used {details.seatbelt_used}; "
                    f"air bag {details.airbag_deployed}; helmet {details.helmet}"
                ), styles), _field_cell("EJECTED / EXTRACTED", (
                    f"Ejected {details.ejected}; extracted {details.extracted}"
                ), styles)],
            ])
            if has_injury_or_death:
                participant_data.append([
                    _field_cell("DEATH / AUTOPSY", "; ".join(x for x in (
                        format_date_for_display(details.date_of_death),
                        details.cause_of_death,
                        f"Autopsy: {details.autopsy_performed}"
                        if details.autopsy_performed != "Unknown" else "",
                    ) if x), styles), _field_cell("NEXT OF KIN", (
                        f"{details.next_of_kin_notified}; "
                        f"by {details.next_of_kin_notified_by}"
                        if details.next_of_kin_notified_by
                        else details.next_of_kin_notified
                    ), styles),
                ])
            table = Table(participant_data, colWidths=[3.35 * inch, 3.25 * inch])
            table.setStyle(_standard_table_style())
            story.append(table)
            for title, value in (("Injuries", details.injuries),
                                 ("Structured Evidence", details.evidence_items),
                                 ("Evidence Obtained", details.evidence_obtained),
                                 ("Lab Information", details.lab_information), ("Participant Notes", details.notes)):
                if value:
                    story.extend([Paragraph(title, styles["Label"]), Paragraph(_text(value), styles["BodySmall"])])
        if _has_detail(profile, {"person_id", "updated_at"}):
            is_driver = any(
                role.strip().casefold() == "driver"
                for role in person.roles
            )
            restrictions = profile.license_restrictions
            if (
                not restrictions
                and profile.license_restricted not in ("", "Unknown")
            ):
                restrictions = profile.license_restricted
            driving_history = "; ".join(
                value
                for value in (
                    (
                        f"Years driving: {profile.years_driving}"
                        if profile.years_driving else ""
                    ),
                    (
                        f"Previous collisions: {profile.previous_collisions}"
                        if profile.previous_collisions else ""
                    ),
                    (
                        "Prior traffic homicide convictions: "
                        f"{profile.previous_traffic_homicide}"
                        if profile.previous_traffic_homicide else ""
                    ),
                    profile.notes,
                )
                if value
            )
            driver_data = [
                [_field_cell("LICENSE NUMBER", profile.license_number, styles),
                 _field_cell("LICENSE STATE", profile.license_state, styles)],
                [_field_cell("CLASS", profile.license_class, styles),
                 _field_cell("STATUS", profile.license_status, styles)],
                [_field_cell(
                    "ISSUED", format_date_for_display(profile.license_issued_date), styles
                ), _field_cell(
                    "EXPIRATION", format_date_for_display(profile.license_expiration_date), styles
                )],
                [_field_cell("ENDORSEMENTS", profile.endorsements, styles),
                 _field_cell("RESTRICTIONS", restrictions, styles)],
                [_field_cell(
                    "RESTRICTIONS EXPLAINED",
                    profile.license_restriction_explanation,
                    styles,
                ), ""],
                [_field_cell("TRIP", (
                    f"{profile.trip_from} to {profile.trip_to}; {profile.trip_purpose}"
                ), styles), _field_cell("IMPAIRMENT", "; ".join(
                    x for x in (
                        profile.impairment_status, profile.bac, profile.testing,
                    ) if x
                ), styles)],
            ]
            span_rows = [4]
            work = "; ".join(
                value
                for value in (profile.hours_worked, profile.type_of_work)
                if value
            )
            if is_driver:
                driver_data.insert(6, [
                    _field_cell(
                        "PHYSICAL CONDITIONS", profile.physical_condition_types, styles
                    ),
                    "",
                ])
                span_rows.append(6)
                driver_data.insert(7, [
                    _field_cell("SLEEP / AWAKE", (
                        f"{profile.hours_asleep} asleep; "
                        f"{profile.hours_awake} awake"
                    ), styles),
                    _field_cell("WORK", work, styles),
                ])
            else:
                driver_data.insert(6, [
                    _field_cell("WORK", work, styles),
                    "",
                ])
                span_rows.append(6)
            driver_data.append([
                _field_cell("FAMILIARITY", (
                    f"Road {profile.familiar_with_road}; "
                    f"vehicle {profile.familiar_with_vehicle}"
                ), styles),
                _field_cell("DRIVING HISTORY", driving_history, styles),
            ])
            table = Table(driver_data, colWidths=[3.35 * inch, 3.25 * inch])
            driver_table_style = _standard_table_style()
            for row in span_rows:
                driver_table_style.add("SPAN", (0, row), (1, row))
            table.setStyle(driver_table_style)
            background_title = (
                "Driver Background" if is_driver else "Participant Background"
            )
            story.extend([Paragraph(background_title, styles["Label"]), table])
            additional_driver_details = [
                ("Testing Methods", profile.testing_methods),
                ("Impairment Notes", profile.impairment_notes),
            ]
            if is_driver:
                additional_driver_details.insert(0, (
                    "Medical Conditions",
                    "\n".join(
                        value
                        for value in (
                            profile.permanent_conditions,
                            profile.temporary_conditions,
                        )
                        if value
                    ),
                ))
            for title, value in additional_driver_details:
                if value:
                    story.extend([Paragraph(title, styles["Label"]), Paragraph(_text(value), styles["BodySmall"])])
        story.append(Spacer(1, 0.08 * inch))
    return story


def _vehicles_section(
    vehicles: list[Vehicle],
    people: dict[str, Person],
    inspections: dict[str, VehicleInspection],
    tires: dict[str, list[TireInspection]],
    motorcycle_inspections: dict[str, MotorcycleInspection],
    styles,
) -> list[object]:
    story: list[object] = [CondPageBreak(4.25 * inch), Paragraph("Vehicles", styles["Section"])]
    if not vehicles:
        story.append(Paragraph("No vehicles entered.", styles["Empty"]))
        return story
    for vehicle in vehicles:
        heading = f"{_text(vehicle.vehicle_number or 'Vehicle')} - {_text(vehicle.description)}"
        insurance_company = vehicle.insurance_company or vehicle.insurance
        towing = "No"
        if vehicle.towed:
            towing = " - ".join(value for value in (
                "Yes",
                vehicle.tow_information,
            ) if value)
        details = [
            [_field_cell("COLOR", vehicle.color, styles), _field_cell(
                "PLATE", " ".join(
                    x for x in (vehicle.plate_state, vehicle.plate) if x
                ), styles
            )],
            [_field_cell("TRIM", vehicle.trim, styles),
             _field_cell("ENGINE", vehicle.engine, styles)],
            [_field_cell("VEHICLE WEIGHT", vehicle.vehicle_weight, styles),
             _field_cell("TIRE SIZE", vehicle.tire_size, styles)],
            [_field_cell("VIN", vehicle.vin, styles),
             _field_cell("TOWED / TO", towing, styles)],
            [_field_cell("DRIVER", _name(vehicle.driver_person_id, people), styles),
             _field_cell("OWNER", _name(vehicle.owner_person_id, people), styles)],
            [_field_cell("INSURANCE COMPANY", insurance_company, styles),
             _field_cell("POLICY NUMBER", vehicle.insurance_policy_number, styles)],
        ]
        table = Table(details, colWidths=[3.3 * inch, 3.3 * inch])
        table.setStyle(_standard_table_style())
        claim_table = Table(
            [
                [_field_cell(
                    "CLAIM NUMBER", vehicle.insurance_claim_number, styles
                ), _field_cell(
                    "ADJUSTER NAME", vehicle.insurance_adjuster_name, styles
                )],
                [_field_cell(
                    "ADJUSTER PHONE", vehicle.insurance_adjuster_phone, styles
                ), _field_cell(
                    "ADJUSTER EMAIL", vehicle.insurance_adjuster_email, styles
                )],
            ],
            colWidths=[3.3 * inch, 3.3 * inch],
        )
        claim_table.setStyle(_standard_table_style())
        workflow_data = [
            [Paragraph(label.upper(), styles["Label"])
             for _attribute, label in VEHICLE_WORKFLOW_FIELDS],
            [Paragraph("Yes" if getattr(vehicle, attribute) else "No", styles["Cell"])
             for attribute, _label in VEHICLE_WORKFLOW_FIELDS],
        ]
        workflow_table = Table(
            workflow_data,
            colWidths=[6.6 * inch / len(VEHICLE_WORKFLOW_FIELDS)]
            * len(VEHICLE_WORKFLOW_FIELDS),
        )
        workflow_table.setStyle(_standard_table_style())
        release_table = Table(
            [
                [_field_cell(
                    "RELEASE DATE", format_date_for_display(vehicle.release_date), styles
                ), _field_cell(
                    "RELEASE INFORMATION", vehicle.release_information, styles
                )],
            ],
            colWidths=[1.4 * inch, 5.2 * inch],
        )
        release_table.setStyle(_standard_table_style())
        block: list[object] = [
            Paragraph(heading, styles["Subsection"]),
            table,
            Paragraph("Insurance Claim", styles["Label"]),
            claim_table,
            Paragraph("Vehicle-Specific Checklist", styles["Label"]),
            workflow_table,
            Paragraph("Vehicle Release", styles["Label"]),
            release_table,
        ]
        if vehicle.edr_status:
            block.extend([
                Paragraph("CDR / EDR Notes", styles["Label"]),
                Paragraph(_text(vehicle.edr_status), styles["BodySmall"]),
            ])
        if vehicle.damage_notes:
            block.extend([Paragraph("Damage", styles["Label"]), Paragraph(_text(vehicle.damage_notes), styles["BodySmall"])])
        if vehicle.notes:
            block.extend([Paragraph("Additional Notes", styles["Label"]), Paragraph(_text(vehicle.notes), styles["BodySmall"])])
        inspection = inspections[vehicle.id]
        if _has_detail(inspection, {"vehicle_id", "updated_at"}):
            inspection_data = [
                [_field_cell("MILEAGE", inspection.mileage, styles),
                 _field_cell("TRANSMISSION / GEAR", " / ".join(
                     x for x in (inspection.transmission, inspection.gear) if x
                 ), styles)],
                [_field_cell("WEIGHTS", "; ".join(x for x in (
                    f"Reg {inspection.registered_weight}"
                    if inspection.registered_weight else "",
                    f"Curb {inspection.curb_weight}"
                    if inspection.curb_weight else "",
                    f"Measured {inspection.measured_weight}"
                    if inspection.measured_weight else "",
                ) if x), styles), _field_cell("STEERING", inspection.steering, styles)],
                [_field_cell("BRAKES", "; ".join(
                    x for x in (
                        inspection.front_brakes, inspection.rear_brakes,
                        inspection.brake_system,
                    ) if x
                ), styles), _field_cell(
                    "TIRE CONTRIBUTION", inspection.tire_contribution, styles
                )],
            ]
            inspection_table = Table(inspection_data, colWidths=[3.35 * inch, 3.25 * inch])
            inspection_table.setStyle(_standard_table_style())
            block.extend([Paragraph("Inspection", styles["Label"]), inspection_table])
            for title, value in (
                ("Lighting / Electrical", inspection.lighting_electrical),
                ("Body Equipment", inspection.body_equipment),
                ("Safety Systems", inspection.safety_systems),
                ("Vehicle Identity Checks", "; ".join(value for value in (
                    f"NICB: {inspection.nicb_status}" if inspection.nicb_status else "",
                    f"NHTSA recalls: {inspection.recall_status}" if inspection.recall_status else "",
                    f"VIN decode: {inspection.vin_decode_status}" if inspection.vin_decode_status else "",
                ) if value)),
                ("Switch Positions", "; ".join(value for value in (
                    f"Headlight: {inspection.headlight_switch_position}" if inspection.headlight_switch_position else "",
                    f"Wiper: {inspection.wiper_switch_position}" if inspection.wiper_switch_position else "",
                    f"Ignition: {inspection.ignition_position}" if inspection.ignition_position else "",
                    f"Radio: {inspection.radio_position}" if inspection.radio_position else "",
                    f"Heater: {inspection.heater_position}" if inspection.heater_position else "",
                ) if value)),
                ("Body / Glazing / Devices", "; ".join(value for value in (
                    f"Headlamp lens: {inspection.headlamp_lens_condition}" if inspection.headlamp_lens_condition else "",
                    f"Glass: {inspection.safety_glass_condition}" if inspection.safety_glass_condition else "",
                    f"Inside mirror: {inspection.inside_mirror}" if inspection.inside_mirror else "",
                    f"Outside mirrors: {inspection.outside_mirrors}" if inspection.outside_mirrors else "",
                    f"Windows: {inspection.window_positions}" if inspection.window_positions else "",
                    f"Air bags: {inspection.airbag_status}" if inspection.airbag_status else "",
                    f"Interior: {inspection.body_interior_condition}" if inspection.body_interior_condition else "",
                    f"Exterior: {inspection.body_exterior_condition}" if inspection.body_exterior_condition else "",
                    inspection.device_observations,
                ) if value)),
                ("Tire Contribution Explanation", inspection.tire_contribution_explanation),
                ("Tire Notes", inspection.tire_notes),
                ("Inspection Notes", inspection.inspection_notes),
            ):
                if value:
                    block.extend([Paragraph(title, styles["Label"]), Paragraph(_text(value), styles["BodySmall"])])
            equipment_rows = [[Paragraph(item, styles["Label"]) for item in (
                "SYSTEM", "EQUIPPED", "OPERABLE"
            )]]
            for key, label in (
                ("headlights", "Headlights"), ("taillights", "Taillights"),
                ("tag_lights", "Tag lights"), ("brake_lights", "Brake lights"),
                ("turn_signals", "Turn signals"), ("parking_lamps", "Parking lamps"),
                ("other_lights", "Other lights"), ("front_wipers", "Front wipers"),
                ("rear_wipers", "Rear wipers"), ("horn", "Horn"),
            ):
                equipped = getattr(inspection, f"{key}_equipped")
                operable = getattr(inspection, f"{key}_operable")
                if equipped != "Unknown" or operable != "Unknown":
                    equipment_rows.append([
                        Paragraph(label, styles["Cell"]),
                        Paragraph(_text(equipped), styles["Cell"]),
                        Paragraph(_text(operable), styles["Cell"]),
                    ])
            if len(equipment_rows) > 1:
                equipment_table = Table(
                    equipment_rows, colWidths=[3.4 * inch, 1.6 * inch, 1.6 * inch], repeatRows=1
                )
                equipment_table.setStyle(_standard_table_style())
                block.extend([Paragraph("Equipment Checks", styles["Label"]), equipment_table])
        vehicle_tires = tires[vehicle.id]
        if vehicle_tires:
            tire_data = [[Paragraph(item, styles["Label"]) for item in
                          ("POS", "MAKE / DESIGN", "SIZE", "PRESSURE", "TREAD I / M / O", "CONDITION")]]
            for tire in vehicle_tires:
                tire_data.append([
                    Paragraph(_text(tire.position), styles["Cell"]),
                    Paragraph(_text(" / ".join(x for x in (tire.make, tire.design) if x)), styles["Cell"]),
                    Paragraph(_text(tire.size), styles["Cell"]),
                    Paragraph(_text(tire.pressure), styles["Cell"]),
                    Paragraph(_text(" / ".join(x for x in (tire.tread_inside, tire.tread_middle, tire.tread_outside) if x)), styles["Cell"]),
                    Paragraph(_text(tire.condition), styles["Cell"]),
                ])
            tire_table = Table(tire_data, colWidths=[0.42 * inch, 1.35 * inch, 0.85 * inch, 0.72 * inch, 1.25 * inch, 2.0 * inch], repeatRows=1)
            tire_table.setStyle(_standard_table_style())
            block.extend([Paragraph("Tires", styles["Label"]), tire_table])
        story.extend(block)
        motorcycle = motorcycle_inspections[vehicle.id]
        has_motorcycle = bool(motorcycle.items) or any((
            motorcycle.frame_number,
            motorcycle.engine_number,
            motorcycle.inspection_date,
            motorcycle.inspection_location,
            motorcycle.officer,
            motorcycle.dpsst,
            motorcycle.general_comments,
        ))
        if has_motorcycle:
            story.append(CondPageBreak(4.0 * inch))
            story.append(Paragraph("Motorcycle Information and 44-Item Inspection", styles["Subsection"]))
            motorcycle_details = [
                [_field_cell("FRAME NUMBER", motorcycle.frame_number, styles),
                 _field_cell("ENGINE NUMBER", motorcycle.engine_number, styles)],
                [_field_cell(
                    "INSPECTION DATE",
                    format_date_for_display(motorcycle.inspection_date),
                    styles,
                ), _field_cell("LOCATION", motorcycle.inspection_location, styles)],
                [_field_cell("OFFICER", motorcycle.officer, styles),
                 _field_cell("DPSST", motorcycle.dpsst, styles)],
            ]
            motorcycle_table = Table(
                motorcycle_details, colWidths=[3.3 * inch, 3.3 * inch]
            )
            motorcycle_table.setStyle(_standard_table_style())
            story.append(motorcycle_table)
            saved_items = {item.item_number: item for item in motorcycle.items}
            item_rows = [
                [Paragraph(
                    f"{_text(heading)} - MOTORCYCLE INSPECTION",
                    styles["Label"],
                ), "", "", "", ""],
                [Paragraph(item, styles["Label"]) for item in (
                    "NO.", "ITEM", "RATING", "MEASUREMENT", "COMMENTS"
                )],
            ]
            for number, name in MOTORCYCLE_INSPECTION_ITEMS:
                item = saved_items.get(number)
                item_rows.append([
                    Paragraph(str(number), styles["Cell"]),
                    Paragraph(_text(name), styles["Cell"]),
                    Paragraph(_text(item.rating if item else ""), styles["Cell"]),
                    Paragraph(_text(item.measurement if item else ""), styles["Cell"]),
                    Paragraph(_text(item.comments if item else ""), styles["Cell"]),
                ])
            item_table = Table(
                item_rows,
                colWidths=[0.38 * inch, 1.75 * inch, 1.2 * inch, 1.2 * inch, 2.07 * inch],
                repeatRows=2,
            )
            item_style = _standard_table_style()
            item_style.add("SPAN", (0, 0), (-1, 0))
            item_style.add("BACKGROUND", (0, 1), (-1, 1), PALE_BLUE)
            item_style.add("TEXTCOLOR", (0, 1), (-1, 1), NAVY)
            item_table.setStyle(item_style)
            story.append(item_table)
            if motorcycle.general_comments:
                story.extend([
                    Paragraph("Motorcycle Inspection Comments", styles["Label"]),
                    Paragraph(_text(motorcycle.general_comments), styles["BodySmall"]),
                ])
        story.append(Spacer(1, 0.12 * inch))
    return story


def _witness_contact_sections(
    people_list: list[Person],
    witness_details: dict[str, WitnessDetails],
    contacts: list[ContactRelationship],
    people: dict[str, Person],
    vehicles: list[Vehicle],
    styles,
) -> list[object]:
    witnesses = [
        (person, witness_details[person.id]) for person in people_list
        if _has_detail(witness_details[person.id], {"person_id", "updated_at"})
    ]
    if not witnesses and not contacts:
        return []
    vehicle_names = {vehicle.id: f"{vehicle.vehicle_number} - {vehicle.description}" for vehicle in vehicles}
    story: list[object] = [Paragraph("Witness Interviews and Contacts", styles["Section"])]
    for person, details in witnesses:
        story.append(Paragraph(_text(person.display_name), styles["Subsection"]))
        data = [
            [_field_cell("IDENTITY", " / ".join(value for value in (
                format_date_for_display(person.dob), person.sex, person.race,
            ) if value), styles), _field_cell(
                "ADDRESS", _person_address(person), styles
            )],
            [_field_cell("PHONES", "; ".join(value for value in (
                f"Cell {person.cell_phone}" if person.cell_phone else "",
                f"Home {person.home_phone}" if person.home_phone else "",
                f"Work {person.work_phone}" if person.work_phone else "",
            ) if value), styles), ""],
            [_field_cell("INTERVIEWED", details.interviewed, styles),
             _field_cell("DATE / INTERVIEWER", " / ".join(
                 x for x in (
                     format_date_for_display(details.interview_date),
                     details.interviewer,
                 ) if x
             ), styles)],
            [_field_cell("SIGNIFICANCE", details.significance, styles), ""],
        ]
        statement_row = None
        if details.statement_summary:
            statement_row = len(data)
            data.append([
                _field_cell("STATEMENT SUMMARY", details.statement_summary, styles),
                "",
            ])
        table = Table(data, colWidths=[3.3 * inch, 3.3 * inch])
        witness_style = _standard_table_style()
        witness_style.add("SPAN", (0, 1), (1, 1))
        witness_style.add("SPAN", (0, 3), (1, 3))
        if statement_row is not None:
            witness_style.add("SPAN", (0, statement_row), (1, statement_row))
        table.setStyle(witness_style)
        story.append(table)
        for title, value in (("Credibility / Consistency", details.credibility_notes),):
            if value:
                story.extend([Paragraph(title, styles["Label"]), Paragraph(_text(value), styles["BodySmall"])])
    if contacts:
        story.append(Paragraph("Contact Relationships", styles["Subsection"]))
        data = [[Paragraph(item, styles["Label"]) for item in
                 ("PERSON", "TYPE", "CONTACT", "PHONES / EMAIL", "ADDRESS / NOTES")]]
        for contact in contacts:
            common_fields = contact_common_fields(
                contact,
                people.get(contact.contact_person_id),
            )
            subject = (
                _name(contact.subject_person_id, people)
                if contact.subject_person_id
                else "Needs person assignment"
            )
            if not contact.subject_person_id and contact.vehicle_id in vehicle_names:
                subject += f" (legacy vehicle: {vehicle_names[contact.vehicle_id]})"
            data.append([
                Paragraph(_text(subject), styles["Cell"]),
                Paragraph(_text(contact.contact_type), styles["Cell"]),
                Paragraph(_text(" - ".join(x for x in (
                    common_fields["contact_name"], contact.organization
                ) if x)), styles["Cell"]),
                Paragraph(_text("; ".join(x for x in (
                    f"Cell {common_fields['cell_phone']}" if common_fields["cell_phone"] else "",
                    f"Home {common_fields['home_phone']}" if common_fields["home_phone"] else "",
                    f"Work {common_fields['work_phone']}" if common_fields["work_phone"] else "",
                    common_fields["email"],
                ) if x)), styles["Cell"]),
                Paragraph(_text("; ".join(x for x in (
                    ", ".join(value for value in (
                        common_fields["address"], common_fields["city"], common_fields["state"]
                    ) if value),
                    contact.notes,
                ) if x)), styles["Cell"]),
            ])
        table = Table(
            data,
            colWidths=[1.25 * inch, 0.8 * inch, 1.35 * inch, 1.3 * inch, 1.9 * inch],
            repeatRows=1,
        )
        table.setStyle(_standard_table_style())
        story.append(table)
    return story


def _vru_section(
    analyses: list[VRUAnalysis], people: dict[str, Person], vehicles: list[Vehicle], styles,
) -> list[object]:
    if not analyses:
        return []
    vehicle_names = {vehicle.id: f"{vehicle.vehicle_number} - {vehicle.description}" for vehicle in vehicles}
    story: list[object] = [Paragraph("Vulnerable Road User Analysis", styles["Section"])]
    for analysis in analyses:
        subject = _name(analysis.person_id, people)
        vehicle = vehicle_names.get(analysis.vehicle_id, "-")
        story.append(Paragraph(f"{_text(subject)} / {_text(vehicle)}", styles["Subsection"]))
        data = [
            [_field_cell("CLOTHING", " / ".join(
                x for x in (analysis.upper_clothing, analysis.lower_clothing) if x
            ), styles), _field_cell("POSITION / MOVEMENT", " / ".join(
                x for x in (analysis.roadway_position, analysis.movement_at_impact) if x
            ), styles)],
            [_field_cell("APPROACH", (
                f"Vehicle: {analysis.vehicle_approach_speed} "
                f"{analysis.vehicle_direction}; VRU: "
                f"{analysis.vru_approach_speed} {analysis.vru_direction}"
            ), styles), _field_cell("THROW DISTANCE", " / ".join(
                x for x in (
                    analysis.person_throw_distance, analysis.bicycle_throw_distance,
                ) if x
            ), styles)],
            [_field_cell("IMPAIRMENT", (
                f"Driver: {analysis.driver_impairment}; "
                f"VRU: {analysis.vru_impairment}"
            ), styles), _field_cell("IMPACT / PROJECTION", " / ".join(
                x for x in (
                    analysis.impact_location_on_vehicle,
                    analysis.projection_classifications,
                    analysis.projection_profile,
                ) if x
            ), styles)],
            [_field_cell(
                "LIGHT METER USED", "Yes" if analysis.light_meter_used else "No", styles
            ), _field_cell(
                "LIGHT BOARD USED", "Yes" if analysis.light_board_used else "No", styles
            )],
        ]
        table = Table(data, colWidths=[3.3 * inch, 3.3 * inch])
        table.setStyle(_standard_table_style())
        story.append(table)
        narratives = (
            ("Sightlines", analysis.sightlines),
            ("Driver Thought Process", analysis.driver_thought_process),
            ("Driver Sleep Information", analysis.driver_sleep_information),
            ("VRU Impairment Notes", analysis.vru_impairment_notes),
            ("Analysis Notes", analysis.notes),
        )
        for title, value in narratives:
            if value:
                story.extend([Paragraph(title, styles["Label"]), Paragraph(_text(value), styles["BodySmall"])])
        story.append(Spacer(1, 0.1 * inch))
    return story


def _evidence_section(
    receipts: list[PropertyReceipt],
    items_by_receipt: dict[str, list[PropertyReceiptItem]],
    styles,
) -> list[object]:
    story: list[object] = [Paragraph("Evidence", styles["Section"])]
    if not receipts:
        story.append(Paragraph("No property receipts entered.", styles["Empty"]))
        return story
    for receipt in receipts:
        story.append(CondPageBreak(1.45 * inch))
        story.append(Paragraph(
            f"Property Receipt {_text(receipt.receipt_number)}",
            styles["Subsection"],
        ))
        receipt_table = Table(
            [
                [
                    _field_cell("PROPERTY OWNER", receipt.property_owner, styles),
                    _field_cell("LODGED AS", receipt.lodging_type, styles),
                    _field_cell("LODGED LOCATION", receipt.lodged_location, styles),
                    _field_cell(
                        "DATE LODGED", format_date_for_display(receipt.lodged_date), styles
                    ),
                ],
            ],
            colWidths=[1.6 * inch, 1.25 * inch, 2.65 * inch, 1.1 * inch],
        )
        receipt_table.setStyle(_standard_table_style())
        story.append(receipt_table)
        items = items_by_receipt.get(receipt.id, [])
        if not items:
            story.append(Paragraph(
                "No items entered for this property receipt.",
                styles["Empty"],
            ))
            continue
        item_rows = [[
            Paragraph("ITEM #", styles["Label"]),
            Paragraph("DESCRIPTION", styles["Label"]),
        ]]
        item_rows.extend(
            [
                Paragraph(_text(item.item_number), styles["Cell"]),
                Paragraph(_text(item.description), styles["Cell"]),
            ]
            for item in items
        )
        item_table = Table(
            item_rows,
            colWidths=[0.75 * inch, 5.85 * inch],
            repeatRows=1,
        )
        item_table.setStyle(_standard_table_style())
        story.append(item_table)
    return story


def _chronology_section(entries: list[ChronologyEntry], styles) -> list[object]:
    story: list[object] = [Paragraph("Investigative Journal", styles["Section"])]
    if not entries:
        story.append(Paragraph("No journal entries.", styles["Empty"]))
        return story
    data = [[Paragraph(item, styles["Label"]) for item in ("DATE", "TIME", "CATEGORY", "ENTRY")]]
    for entry in entries:
        event = entry.summary
        if entry.details:
            event = f"<b>{_text(entry.summary)}</b><br/>{_text(entry.details)}" if entry.summary else _text(entry.details)
        else:
            event = _text(event)
        data.append([
            Paragraph(_text(format_date_for_display(entry.event_date)), styles["Cell"]),
            Paragraph(_text(entry.event_time), styles["Cell"]),
            Paragraph(_text(entry.category), styles["Cell"]),
            Paragraph(event, styles["Cell"]),
        ])
    table = Table(data, colWidths=[0.8 * inch, 0.62 * inch, 0.95 * inch, 4.25 * inch], repeatRows=1)
    table.setStyle(_standard_table_style())
    story.append(table)
    return story


def _tasks_section(tasks: list[CaseTask], styles) -> list[object]:
    story: list[object] = [Paragraph("Tasks", styles["Section"])]
    if not tasks:
        story.append(Paragraph("No tasks entered.", styles["Empty"]))
        return story
    data = [[Paragraph(item, styles["Label"]) for item in ("STATUS", "CATEGORY", "DESCRIPTION", "DUE", "NOTES")]]
    for task in tasks:
        data.append([
            Paragraph(_text(task.status), styles["Cell"]), Paragraph(_text(task.category), styles["Cell"]),
            Paragraph(_text(task.description), styles["Cell"]), Paragraph(_text(format_date_for_display(task.due_date)), styles["Cell"]),
            Paragraph(_text(task.notes), styles["Cell"]),
        ])
    table = Table(data, colWidths=[0.8 * inch, 0.9 * inch, 2.35 * inch, 0.72 * inch, 1.85 * inch], repeatRows=1)
    table.setStyle(_standard_table_style())
    story.append(table)
    return story


def _notes_section(case: CrashCase, styles) -> list[object]:
    return _narrative_block("General investigative notes", case.notes, styles)


def _standard_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LIGHT_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBFCFD")]),
    ])
