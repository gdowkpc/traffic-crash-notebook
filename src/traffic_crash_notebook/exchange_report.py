from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from . import __version__
from .date_format import format_date_for_display, format_time_for_display
from .models import Person, Vehicle, format_crash_location
from .repository import CaseRepository
from .resources import exchange_report_back_path


VEHICLE_BLOCK_HEIGHT = 1.58 * inch
PERSON_BLOCK_HEIGHT = 0.75 * inch
CONTENT_HEIGHT_PER_PAGE = 8.45 * inch
EXCHANGE_PERSON_ROLES = {
    "Driver",
    "Passenger",
    "Pedestrian",
    "Bicyclist",
    "Witness",
    "Victim",
    "Vehicle Owner",
}

LINE_COLOR = colors.HexColor("#27323A")
LABEL_COLOR = colors.HexColor("#3F4B53")
LIGHT_FILL = colors.HexColor("#F1F3F4")


def person_name_last_first(person: Person | None) -> str:
    if person is None:
        return ""
    given = " ".join(
        value for value in (person.first_name, person.middle_name) if value
    )
    if person.last_name and given:
        return f"{person.last_name}, {given}"
    return person.last_name or given


def person_exchange_address(person: Person | None) -> str:
    if person is None:
        return ""
    state_zip = " ".join(value for value in (person.state, person.zip_code) if value)
    return ", ".join(
        value for value in (person.address, person.city, state_zip) if value
    )


def person_exchange_phone(person: Person | None) -> str:
    if person is None:
        return ""
    return "  ".join(
        value for value in (
            f"HM {person.home_phone}" if person.home_phone else "",
            f"BU {person.work_phone}" if person.work_phone else "",
            f"CL {person.cell_phone}" if person.cell_phone else "",
        ) if value
    )


def vehicle_exchange_party(
    vehicle: Vehicle,
    people: dict[str, Person],
) -> Person | None:
    return people.get(vehicle.driver_person_id) or people.get(vehicle.owner_person_id)


def exchange_report_people(
    people: list[Person],
    vehicles: list[Vehicle],
) -> list[Person]:
    """Return involved people not already printed in a vehicle/driver block."""
    people_by_id = {person.id: person for person in people}
    represented_person_ids = {
        party.id
        for vehicle in vehicles
        if (party := vehicle_exchange_party(vehicle, people_by_id)) is not None
    }
    return [
        person
        for person in people
        if person.id not in represented_person_ids
        and EXCHANGE_PERSON_ROLES.intersection(person.roles)
    ]


def exchange_report_page_plan(
    vehicles: list[Vehicle],
    people: list[Person],
) -> list[tuple[list[Vehicle], list[Person]]]:
    """Pack only existing records onto as few readable front pages as possible."""
    items: list[tuple[str, Vehicle | Person, float]] = [
        ("vehicle", vehicle, VEHICLE_BLOCK_HEIGHT) for vehicle in vehicles
    ]
    items.extend(
        ("person", person, PERSON_BLOCK_HEIGHT) for person in people
    )
    if not items:
        return [([], [])]

    pages: list[tuple[list[Vehicle], list[Person]]] = []
    item_index = 0
    while item_index < len(items):
        page_vehicles: list[Vehicle] = []
        page_people: list[Person] = []
        remaining_height = CONTENT_HEIGHT_PER_PAGE
        while item_index < len(items):
            kind, record, block_height = items[item_index]
            if block_height > remaining_height and (page_vehicles or page_people):
                break
            if kind == "vehicle":
                page_vehicles.append(record)  # type: ignore[arg-type]
            else:
                page_people.append(record)  # type: ignore[arg-type]
            remaining_height -= block_height
            item_index += 1
        pages.append((page_vehicles, page_people))
    return pages


def _fit_text(
    pdf: canvas.Canvas,
    value: str,
    x: float,
    y: float,
    width: float,
    *,
    font_name: str = "Helvetica",
    font_size: float = 8.2,
    minimum_size: float = 5.2,
) -> None:
    text = " ".join(str(value or "").split())
    if not text:
        return
    available = max(1.0, width)
    size = font_size
    while size > minimum_size and stringWidth(text, font_name, size) > available:
        size -= 0.25
    if stringWidth(text, font_name, size) > available:
        suffix = "..."
        while text and stringWidth(text + suffix, font_name, size) > available:
            text = text[:-1]
        text = text.rstrip() + suffix
    pdf.setFont(font_name, size)
    pdf.setFillColor(colors.black)
    pdf.drawString(x, y, text)


def _draw_cell(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    value: str = "",
    *,
    fill: colors.Color | None = None,
) -> None:
    if fill is not None:
        pdf.setFillColor(fill)
        pdf.rect(x, y, width, height, stroke=0, fill=1)
    pdf.setStrokeColor(LINE_COLOR)
    pdf.setLineWidth(0.55)
    pdf.rect(x, y, width, height, stroke=1, fill=0)
    pdf.setFillColor(LABEL_COLOR)
    _fit_text(
        pdf,
        label.upper(),
        x + 4,
        y + height - 6.5,
        width - 8,
        font_name="Helvetica-Bold",
        font_size=5.8,
        minimum_size=4.8,
    )
    _fit_text(
        pdf,
        value,
        x + 4,
        y + 3.5,
        width - 8,
        font_size=8.2,
        minimum_size=5.2,
    )


def _draw_checkbox(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    checked: bool,
) -> None:
    size = 7.0
    pdf.setStrokeColor(LINE_COLOR)
    pdf.setLineWidth(0.6)
    pdf.rect(x, y, size, size, stroke=1, fill=0)
    if checked:
        pdf.setLineWidth(1.1)
        pdf.line(x + 1.3, y + 1.3, x + size - 1.3, y + size - 1.3)
        pdf.line(x + 1.3, y + size - 1.3, x + size - 1.3, y + 1.3)


def _draw_header(
    pdf: canvas.Canvas,
    *,
    page_number: int,
    page_count: int,
    case_number: str,
    crash_datetime: str,
    location: str,
    left: float,
    top: float,
    width: float,
) -> float:
    title_height = 0.34 * inch
    page_width = 1.05 * inch
    _draw_cell(
        pdf,
        left,
        top - title_height,
        width - page_width,
        title_height,
        "",
        "",
        fill=LIGHT_FILL,
    )
    _draw_cell(
        pdf,
        left + width - page_width,
        top - title_height,
        page_width,
        title_height,
        "PAGE / OF",
        f"{page_number} / {page_count}",
        fill=LIGHT_FILL,
    )
    pdf.setFillColor(LINE_COLOR)
    pdf.setFont("Helvetica-BoldOblique", 14)
    pdf.drawCentredString(
        left + (width - page_width) / 2,
        top - title_height + 8,
        "TRAFFIC CRASH EXCHANGE REPORT",
    )

    y = top - title_height
    notice_height = 0.28 * inch
    pdf.setFillColor(colors.black)
    pdf.rect(left, y - notice_height, width, notice_height, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 10.2)
    pdf.drawCentredString(
        left + width / 2,
        y - notice_height + 6.1,
        "TRAFFIC CRASH INFORMATION EXCHANGE - RETAIN THIS FORM",
    )

    y -= notice_height
    information_height = 0.27 * inch
    _draw_cell(
        pdf,
        left,
        y - information_height,
        width,
        information_height,
        "",
        "",
        fill=LIGHT_FILL,
    )
    pdf.setFillColor(LABEL_COLOR)
    pdf.setFont("Helvetica", 7.7)
    pdf.drawCentredString(
        left + width / 2,
        y - information_height + 6.0,
        "Please retain for your records and insurance purposes. The Portland Police Bureau will not retain a copy of this form.",
    )

    y -= information_height
    crash_height = 0.43 * inch
    date_width = 2.05 * inch
    _draw_cell(
        pdf,
        left,
        y - crash_height,
        date_width,
        crash_height,
        "CRASH DATE / TIME",
        crash_datetime,
    )
    _draw_cell(
        pdf,
        left + date_width,
        y - crash_height,
        width - date_width,
        crash_height,
        "LOCATION OF CRASH",
        location,
    )
    arrow_x = left + width - 13
    arrow_y = y - crash_height + 11
    pdf.setStrokeColor(LINE_COLOR)
    pdf.setLineWidth(0.6)
    pdf.circle(arrow_x, arrow_y, 6, stroke=1, fill=0)
    pdf.line(arrow_x, arrow_y - 4, arrow_x, arrow_y + 4)
    pdf.line(arrow_x, arrow_y + 4, arrow_x - 2, arrow_y + 1)
    pdf.line(arrow_x, arrow_y + 4, arrow_x + 2, arrow_y + 1)
    pdf.setFont("Helvetica-Bold", 5.5)
    pdf.drawCentredString(arrow_x, arrow_y + 7.5, "N")

    if case_number:
        pdf.setFillColor(LABEL_COLOR)
        pdf.setFont("Helvetica", 5.5)
        pdf.drawRightString(
            left + width - 3,
            top - title_height + 3,
            f"CASE {case_number}",
        )
    return y - crash_height


def _draw_vehicle_block(
    pdf: canvas.Canvas,
    *,
    vehicle: Vehicle | None,
    people: dict[str, Person],
    profiles: dict[str, object],
    left: float,
    top: float,
    width: float,
    height: float,
) -> float:
    party = vehicle_exchange_party(vehicle, people) if vehicle else None
    profile = profiles.get(party.id) if party else None
    row_height = height / 6.0
    y = top - row_height
    vehicle_tag = f" - {vehicle.vehicle_number}" if vehicle and vehicle.vehicle_number else ""
    _draw_cell(
        pdf,
        left,
        y,
        width,
        row_height,
        f"NAME (LAST, FIRST, MI){vehicle_tag}",
        person_name_last_first(party),
    )

    y -= row_height
    address_width = width - 2.45 * inch
    license_width = 1.65 * inch
    state_width = width - address_width - license_width
    _draw_cell(
        pdf,
        left,
        y,
        address_width,
        row_height,
        "ADDRESS",
        person_exchange_address(party),
    )
    _draw_cell(
        pdf,
        left + address_width,
        y,
        license_width,
        row_height,
        "OPERATOR LICENSE NO.",
        getattr(profile, "license_number", "") if profile else "",
    )
    _draw_cell(
        pdf,
        left + address_width + license_width,
        y,
        state_width,
        row_height,
        "STATE",
        getattr(profile, "license_state", "") if profile else "",
    )

    y -= row_height
    _draw_cell(
        pdf,
        left,
        y,
        width,
        row_height,
        "PHONE: HM  BU  CL",
        person_exchange_phone(party),
    )

    y -= row_height
    insurance_width = 4.15 * inch
    _draw_cell(
        pdf,
        left,
        y,
        insurance_width,
        row_height,
        "INSURANCE COMPANY (NOT AGENT)",
        (vehicle.insurance_company or vehicle.insurance) if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + insurance_width,
        y,
        width - insurance_width,
        row_height,
        "INSURANCE POLICY NUMBER",
        vehicle.insurance_policy_number if vehicle else "",
    )

    y -= row_height
    plate_width = 1.55 * inch
    plate_state_width = 0.80 * inch
    year_width = 1.10 * inch
    _draw_cell(
        pdf,
        left,
        y,
        plate_width,
        row_height,
        "LICENSE NO.",
        vehicle.plate if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + plate_width,
        y,
        plate_state_width,
        row_height,
        "STATE",
        vehicle.plate_state if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + plate_width + plate_state_width,
        y,
        year_width,
        row_height,
        "VEH YR",
        vehicle.year if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + plate_width + plate_state_width + year_width,
        y,
        width - plate_width - plate_state_width - year_width,
        row_height,
        "MAKE",
        vehicle.make if vehicle else "",
    )

    y -= row_height
    model_width = 1.72 * inch
    style_width = 1.10 * inch
    color_width = 1.05 * inch
    _draw_cell(
        pdf,
        left,
        y,
        model_width,
        row_height,
        "MODEL",
        vehicle.model if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + model_width,
        y,
        style_width,
        row_height,
        "STYLE",
        vehicle.body_style if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + model_width + style_width,
        y,
        color_width,
        row_height,
        "COLOR",
        vehicle.color if vehicle else "",
    )
    _draw_cell(
        pdf,
        left + model_width + style_width + color_width,
        y,
        width - model_width - style_width - color_width,
        row_height,
        "PROPERTY DAMAGED (HOUSE, FENCE, SIGN, ETC.)",
        vehicle.property_damage if vehicle else "",
    )
    return top - height


def _draw_person_block(
    pdf: canvas.Canvas,
    *,
    person: Person,
    participant_vehicle: str,
    left: float,
    top: float,
    width: float,
    height: float,
) -> float:
    upper_height = height * 0.52
    lower_height = height - upper_height
    upper_y = top - upper_height
    lower_y = upper_y - lower_height
    pdf.setStrokeColor(LINE_COLOR)
    pdf.setLineWidth(0.55)
    pdf.rect(left, upper_y, width, upper_height, stroke=1, fill=0)
    name = person_name_last_first(person)
    role_line_y = upper_y + upper_height - 9
    name_line_y = upper_y + 4
    pdf.setFillColor(LABEL_COLOR)
    pdf.setFont("Helvetica-Bold", 5.6)
    role_x = left + 4
    listed_roles = (
        ("Passenger", "PASSENGER"),
        ("Witness", "WITNESS"),
        ("Pedestrian", "PEDESTRIAN"),
        ("Bicyclist", "BICYCLIST"),
    )
    for role, label in listed_roles:
        _draw_checkbox(pdf, role_x, role_line_y - 1, role in person.roles)
        pdf.drawString(role_x + 11, role_line_y, label)
        role_x += 17 + stringWidth(label, "Helvetica-Bold", 5.6)
    other_roles = [
        role for role in person.roles if role not in {item[0] for item in listed_roles}
    ]
    if other_roles:
        _fit_text(
            pdf,
            "ROLES: " + ", ".join(other_roles),
            role_x + 3,
            role_line_y,
            left + width - role_x - 7,
            font_size=5.6,
            bold=True,
        )

    pdf.setFillColor(LABEL_COLOR)
    pdf.setFont("Helvetica-Bold", 5.8)
    pdf.drawString(left + 4, name_line_y, "PERSON NAME (LAST, FIRST, MI)")
    display_name = (
        f"{name} ({participant_vehicle})" if participant_vehicle else name
    )
    _fit_text(
        pdf,
        display_name,
        left + 125,
        name_line_y,
        width - 132,
        font_size=8.0,
    )

    address_width = width - 2.15 * inch
    _draw_cell(
        pdf,
        left,
        lower_y,
        address_width,
        lower_height,
        "ADDRESS",
        person_exchange_address(person),
    )
    _draw_cell(
        pdf,
        left + address_width,
        lower_y,
        width - address_width,
        lower_height,
        "PHONE: HM  BU  CL",
        person_exchange_phone(person),
    )
    return top - height


def _draw_footer(
    pdf: canvas.Canvas,
    *,
    details,
    investigator: str,
    dpsst: str,
    assignment: str,
    case_number: str,
    left: float,
    top: float,
    width: float,
) -> None:
    field_height = 0.34 * inch
    dpsst_width = 1.0 * inch
    precinct_width = 1.75 * inch
    officer_width = width - dpsst_width - precinct_width
    _draw_cell(
        pdf,
        left,
        top - field_height,
        officer_width,
        field_height,
        "ASSIGNED OFFICER",
        investigator or details.assisting_officer,
    )
    _draw_cell(
        pdf,
        left + officer_width,
        top - field_height,
        dpsst_width,
        field_height,
        "DPSST",
        dpsst,
    )
    _draw_cell(
        pdf,
        left + officer_width + dpsst_width,
        top - field_height,
        precinct_width,
        field_height,
        "PRECINCT",
        assignment or details.precinct,
    )
    footer_y = top - field_height - 10
    pdf.setFillColor(LABEL_COLOR)
    pdf.setFont("Helvetica", 6.2)
    if case_number:
        pdf.drawString(left, footer_y, f"CASE {case_number}")
    pdf.drawCentredString(left + width / 2, footer_y, "ORIGINAL / INVOLVED PARTIES")
    pdf.drawRightString(
        left + width,
        footer_y,
        f"Traffic Crash Notebook v{__version__}",
    )


def _draw_back_page(pdf: canvas.Canvas, image_path: Path) -> None:
    if not image_path.is_file():
        raise FileNotFoundError(
            f"The exchange-report back-page image is missing: {image_path}"
        )

    page_width, page_height = letter
    image = ImageReader(str(image_path))
    image_width, image_height = image.getSize()

    # Frame the photographed sheet while clipping away the surrounding desk.
    crop_left = image_width * 0.022
    crop_top = image_height * 0.014
    crop_right = image_width * 0.977
    crop_bottom = image_height * 0.941
    crop_width = crop_right - crop_left
    crop_height = crop_bottom - crop_top
    margin = 6.0
    available_width = page_width - 2 * margin
    available_height = page_height - 2 * margin
    scale = min(available_width / crop_width, available_height / crop_height)
    framed_width = crop_width * scale
    framed_height = crop_height * scale
    frame_x = margin + (available_width - framed_width) / 2
    frame_y = margin + (available_height - framed_height) / 2
    image_x = frame_x - crop_left * scale
    image_y = frame_y - (image_height - crop_bottom) * scale

    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    pdf.saveState()
    clip = pdf.beginPath()
    clip.rect(margin, margin, available_width, available_height)
    pdf.clipPath(clip, stroke=0, fill=0)
    pdf.drawImage(
        image,
        image_x,
        image_y,
        width=image_width * scale,
        height=image_height * scale,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.restoreState()
    pdf.showPage()


def export_exchange_report_pdf(
    repository: CaseRepository,
    case_id: str,
    destination: str | Path,
) -> Path:
    case = repository.get_case(case_id)
    if case is None:
        raise ValueError(f"Case not found: {case_id}")

    crash_details = repository.get_crash_details(case_id)
    exchange_details = repository.get_exchange_report_details(case_id)
    people_list = repository.list_people(case_id)
    people = {person.id: person for person in people_list}
    vehicles = repository.list_vehicles(case_id)
    profiles = {
        person.id: repository.get_driver_profile(person.id)
        for person in people_list
    }
    participants = {
        person.id: repository.get_participant_details(person.id)
        for person in people_list
    }
    exchange_people = exchange_report_people(people_list, vehicles)
    vehicle_labels = {
        vehicle.id: vehicle.vehicle_number or vehicle.description
        for vehicle in vehicles
    }
    page_plan = exchange_report_page_plan(vehicles, exchange_people)
    page_count = len(page_plan)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(destination_path), pagesize=letter, pageCompression=1)
    pdf.setTitle(
        f"Traffic Crash Exchange Report - {case.case_number or 'Untitled Case'}"
    )
    pdf.setAuthor(case.investigator or "Traffic Crash Notebook")
    pdf.setSubject("Traffic crash information exchange report")

    page_width, page_height = letter
    left = 0.38 * inch
    top = page_height - 0.38 * inch
    content_width = page_width - (2 * left)
    crash_datetime = " ".join(
        value for value in (
            format_date_for_display(case.crash_date),
            format_time_for_display(case.crash_time),
        ) if value
    )
    location = format_crash_location(
        crash_details.road_name,
        crash_details.intersection_road,
    ) or case.location

    for page_index, (page_vehicles, page_people) in enumerate(page_plan):
        current_top = _draw_header(
            pdf,
            page_number=page_index + 1,
            page_count=page_count,
            case_number=case.case_number,
            crash_datetime=crash_datetime,
            location=location,
            left=left,
            top=top,
            width=content_width,
        )

        for vehicle in page_vehicles:
            current_top = _draw_vehicle_block(
                pdf,
                vehicle=vehicle,
                people=people,
                profiles=profiles,
                left=left,
                top=current_top,
                width=content_width,
                height=VEHICLE_BLOCK_HEIGHT,
            )

        for person in page_people:
            participant_vehicle = vehicle_labels.get(
                participants[person.id].vehicle_id,
                "",
            )
            current_top = _draw_person_block(
                pdf,
                person=person,
                participant_vehicle=participant_vehicle,
                left=left,
                top=current_top,
                width=content_width,
                height=PERSON_BLOCK_HEIGHT,
            )

        _draw_footer(
            pdf,
            details=exchange_details,
            investigator=case.investigator,
            dpsst=case.assigned_officer_dpsst,
            assignment=case.assignment,
            case_number=case.case_number,
            left=left,
            top=0.85 * inch,
            width=content_width,
        )
        pdf.showPage()

    _draw_back_page(pdf, exchange_report_back_path())
    pdf.save()
    return destination_path
