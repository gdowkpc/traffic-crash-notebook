from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .date_format import format_date_for_display
from .models import TowedVehicleSummary


RIVERGATE_REPORT_TITLE = "Rivergate - Unreleased Vehicles"
TOWED_VEHICLE_HEADERS = ("Case", "Tow number", "Vehicle", "Plate", "VIN", "Towed to", "Case status", "Investigator")


def towed_vehicle_cells(entry: TowedVehicleSummary) -> list[str]:
    vehicle = entry.vehicle
    return [
        "\n".join(filter(None, [entry.case_number or "Untitled Case", format_date_for_display(entry.crash_date)])),
        vehicle.tow_number,
        "\n".join(filter(None, [f"Vehicle {vehicle.vehicle_number}" if vehicle.vehicle_number else "",
                               vehicle.description, vehicle.color])),
        " ".join(filter(None, [vehicle.plate_state, vehicle.plate])),
        vehicle.vin, vehicle.tow_information, entry.case_status, entry.investigator,
    ]


def export_rivergate_report_pdf(
    entries: list[TowedVehicleSummary], output_path: Path, *,
    include_closed: bool = True, search: str = "", generated_at: datetime | None = None,
) -> Path:
    """Write the displayed report atomically, preserving an existing PDF on failure."""
    output_path = Path(output_path)
    generated_at = generated_at or datetime.now().astimezone()
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("ReportCell", fontName="Helvetica", fontSize=8, leading=11, splitLongWords=True)
    header_style = ParagraphStyle("ReportHeader", parent=cell_style, fontName="Helvetica-Bold", textColor=colors.white)

    def paragraph(text: str, style=cell_style):
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    scope = "All cases, including archived cases" if include_closed else "Open cases only; archived cases excluded"
    story = [
        Paragraph(RIVERGATE_REPORT_TITLE, styles["Title"]),
        paragraph(f"Generated: {generated_at.strftime('%m/%d/%Y %I:%M %p %Z')}"),
        paragraph("Criteria: Towed is checked, towing destination contains Rivergate (ignoring case), and Released is unchecked."),
        paragraph(f"Scope: {scope}."),
    ]
    if search.strip():
        story.append(paragraph(f"Search filter: {search.strip()}"))
    story.extend([paragraph(f"{len(entries)} unreleased vehicle(s)"), Spacer(1, 12)])
    if entries:
        rows = [[paragraph(header, header_style) for header in TOWED_VEHICLE_HEADERS]]
        rows.extend([[paragraph(value) for value in towed_vehicle_cells(entry)] for entry in entries])
        table = LongTable(rows, colWidths=[72, 72, 108, 64, 105, 125, 64, 110], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18344a")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f8")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d2d9")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("No unreleased vehicles match this report.", styles["Normal"]))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#526677"))
        canvas.drawString(36, 22, "Traffic Crash Notebook | Rivergate - Unreleased Vehicles")
        canvas.drawRightString(756, 22, f"Page {document.page}")
        canvas.restoreState()

    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        document = SimpleDocTemplate(
            str(temporary), pagesize=landscape(letter), leftMargin=36, rightMargin=36,
            topMargin=30, bottomMargin=38, title=RIVERGATE_REPORT_TITLE,
            author="Traffic Crash Notebook",
        )
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path
