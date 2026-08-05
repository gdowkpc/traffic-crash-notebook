from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw
from pypdf import PdfReader


def _pdf_object(value: Any) -> Any:
    if hasattr(value, "get_object"):
        return value.get_object()
    return value


def _pdf_name(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_pdf(path: Path, output_directory: Path) -> dict[str, Any]:
    reader = PdfReader(str(path))
    root = _pdf_object(reader.trailer["/Root"])
    acroform_reference = root.get("/AcroForm")
    acroform = _pdf_object(acroform_reference) if acroform_reference else None
    xfa = _pdf_object(acroform.get("/XFA")) if acroform and acroform.get("/XFA") else None

    xfa_packets: list[str] = []
    if isinstance(xfa, list):
        xfa_packets = [str(xfa[index]) for index in range(0, len(xfa), 2)]
    elif xfa is not None:
        xfa_packets = [type(xfa).__name__]

    field_error = ""
    try:
        fields = reader.get_fields() or {}
    except Exception as exc:
        fields = {}
        field_error = f"{type(exc).__name__}: {exc}"

    field_types: Counter[str] = Counter()
    field_names: list[str] = []
    nonempty_field_values = 0
    for field_name, raw_field in fields.items():
        field = _pdf_object(raw_field)
        field_names.append(str(field_name))
        field_types[_pdf_name(field.get("/FT")) or "unknown"] += 1
        value = field.get("/V")
        if value not in (None, "", "/Off"):
            nonempty_field_values += 1

    annotation_types: Counter[str] = Counter()
    widgets: list[dict[str, Any]] = []
    page_sizes: Counter[str] = Counter()
    rotations: Counter[str] = Counter()
    pypdf_text: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        page_sizes[f"{width:.1f} x {height:.1f}"] += 1
        rotations[str(page.get("/Rotate", 0))] += 1
        pypdf_text.append(page.extract_text() or "")
        for annotation_reference in page.get("/Annots", []):
            annotation = _pdf_object(annotation_reference)
            subtype = _pdf_name(annotation.get("/Subtype")) or "unknown"
            annotation_types[subtype] += 1
            if subtype == "/Widget":
                widgets.append({
                    "page": page_number,
                    "name": _pdf_name(annotation.get("/T")),
                    "field_type": _pdf_name(annotation.get("/FT")),
                    "alternate_name": _pdf_name(annotation.get("/TU")),
                })

    text_path = output_directory / f"{path.stem}-text.txt"
    page_chunks = [
        f"===== PAGE {index} =====\n{text}"
        for index, text in enumerate(pypdf_text, start=1)
    ]
    text_path.write_text("\n\n".join(page_chunks), encoding="utf-8")

    metadata = {
        str(key): str(value)
        for key, value in (reader.metadata or {}).items()
    }
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "pages": len(reader.pages),
        "encrypted": reader.is_encrypted,
        "metadata": metadata,
        "catalog_keys": sorted(str(key) for key in root.keys()),
        "has_acroform": acroform is not None,
        "acroform_keys": sorted(str(key) for key in acroform.keys()) if acroform else [],
        "has_xfa": xfa is not None,
        "xfa_packets": xfa_packets,
        "field_count": len(fields),
        "field_error": field_error,
        "field_types": dict(sorted(field_types.items())),
        "field_names": sorted(field_names),
        "nonempty_field_values": nonempty_field_values,
        "widget_count": len(widgets),
        "widgets": widgets,
        "annotation_types": dict(sorted(annotation_types.items())),
        "page_sizes": dict(sorted(page_sizes.items())),
        "rotations": dict(sorted(rotations.items())),
        "extracted_text_characters": sum(len(text) for text in pypdf_text),
        "text_output": str(text_path),
    }


def render_contact_sheets(path: Path, output_directory: Path) -> list[str]:
    document = fitz.open(path)
    sheet_paths: list[str] = []
    page_images: list[tuple[int, Image.Image]] = []
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(0.72, 0.72), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            page_images.append((page_index + 1, image))

        pages_per_sheet = 6
        columns = 2
        rows = 3
        margin = 18
        label_height = 24
        cell_width = max(image.width for _, image in page_images) + (margin * 2)
        cell_height = max(image.height for _, image in page_images) + label_height + (margin * 2)

        for start in range(0, len(page_images), pages_per_sheet):
            group = page_images[start:start + pages_per_sheet]
            sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
            draw = ImageDraw.Draw(sheet)
            for offset, (page_number, image) in enumerate(group):
                column = offset % columns
                row = offset // columns
                x = (column * cell_width) + margin
                y = (row * cell_height) + margin + label_height
                draw.text((x, (row * cell_height) + margin), f"Page {page_number}", fill="black")
                sheet.paste(image, (x, y))
                draw.rectangle((x - 1, y - 1, x + image.width, y + image.height), outline="#777777")
            sheet_number = (start // pages_per_sheet) + 1
            sheet_path = output_directory / f"{path.stem}-contact-{sheet_number:02d}.png"
            sheet.save(sheet_path, format="PNG", optimize=True)
            sheet_paths.append(str(sheet_path))
    finally:
        document.close()
        for _, image in page_images:
            image.close()
    return sheet_paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("pdfs", nargs="+", type=Path)
    arguments = parser.parse_args()

    output_directory = arguments.output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"Refusing to overwrite analysis output: {output_directory}")
    output_directory.mkdir(parents=True)

    reports: list[dict[str, Any]] = []
    for pdf_path in arguments.pdfs:
        resolved_pdf = pdf_path.resolve()
        if not resolved_pdf.is_file():
            raise FileNotFoundError(resolved_pdf)
        report = inspect_pdf(resolved_pdf, output_directory)
        report["contact_sheets"] = render_contact_sheets(resolved_pdf, output_directory)
        reports.append(report)

    inventory_path = output_directory / "packet-inventory.json"
    inventory_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(inventory_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
