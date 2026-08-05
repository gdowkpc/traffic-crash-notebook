from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def _object(value: Any) -> Any:
    if hasattr(value, "get_object"):
        return value.get_object()
    return value


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return cleaned or "packet"


def _caption(field: ET.Element) -> str:
    caption = next((node for node in field if _local_name(node.tag) == "caption"), None)
    if caption is None:
        return ""
    pieces = [piece.strip() for piece in caption.itertext() if piece.strip()]
    return " ".join(pieces)


def _ui_type(field: ET.Element) -> str:
    ui = next((node for node in field if _local_name(node.tag) == "ui"), None)
    if ui is None:
        return ""
    for child in ui:
        name = _local_name(child.tag)
        if name != "extras":
            return name
    return ""


def summarize_template(template_bytes: bytes) -> dict[str, Any]:
    root = ET.fromstring(template_bytes)
    tag_counts = Counter(_local_name(node.tag) for node in root.iter())
    parent_map = {child: parent for parent in root.iter() for child in parent}

    fields: list[dict[str, str]] = []
    for field in (node for node in root.iter() if _local_name(node.tag) == "field"):
        path_parts: list[str] = []
        current: ET.Element | None = field
        while current is not None:
            if _local_name(current.tag) in {"subform", "field", "exclGroup"}:
                name = current.attrib.get("name", "")
                if name:
                    path_parts.append(name)
            current = parent_map.get(current)
        bind = next((node for node in field if _local_name(node.tag) == "bind"), None)
        fields.append({
            "path": ".".join(reversed(path_parts)),
            "name": field.attrib.get("name", ""),
            "caption": _caption(field),
            "ui_type": _ui_type(field),
            "presence": field.attrib.get("presence", "visible"),
            "access": field.attrib.get("access", "open"),
            "bind_ref": bind.attrib.get("ref", "") if bind is not None else "",
        })

    repeatable_subforms: list[dict[str, str]] = []
    for subform in (node for node in root.iter() if _local_name(node.tag) == "subform"):
        occur = next((node for node in subform if _local_name(node.tag) == "occur"), None)
        if occur is None:
            continue
        maximum = occur.attrib.get("max", "1")
        if maximum not in {"0", "1"}:
            repeatable_subforms.append({
                "name": subform.attrib.get("name", ""),
                "minimum": occur.attrib.get("min", "1"),
                "initial": occur.attrib.get("initial", "1"),
                "maximum": maximum,
            })

    scripts: list[dict[str, Any]] = []
    for script in (node for node in root.iter() if _local_name(node.tag) == "script"):
        source = "".join(script.itertext()).strip()
        parent = parent_map.get(script)
        scripts.append({
            "content_type": script.attrib.get("contentType", ""),
            "run_at": script.attrib.get("runAt", ""),
            "parent_type": _local_name(parent.tag) if parent is not None else "",
            "characters": len(source),
        })

    return {
        "tag_counts": dict(sorted(tag_counts.items())),
        "field_count": len(fields),
        "field_ui_types": dict(sorted(Counter(field["ui_type"] or "unknown" for field in fields).items())),
        "fields": fields,
        "repeatable_subforms": repeatable_subforms,
        "script_count": len(scripts),
        "script_languages": dict(sorted(Counter(script["content_type"] or "unknown" for script in scripts).items())),
        "scripts": scripts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()

    pdf_path = arguments.pdf.resolve()
    output_directory = arguments.output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"Refusing to overwrite XFA output: {output_directory}")
    output_directory.mkdir(parents=True)

    reader = PdfReader(str(pdf_path))
    root = _object(reader.trailer["/Root"])
    acroform = _object(root.get("/AcroForm"))
    if not acroform or not acroform.get("/XFA"):
        raise ValueError("The PDF does not contain an XFA form.")
    xfa = _object(acroform["/XFA"])
    if not isinstance(xfa, list):
        raise TypeError("Expected the XFA entry to be a packet array.")

    packet_summary: list[dict[str, Any]] = []
    template_summary: dict[str, Any] | None = None
    for index in range(0, len(xfa), 2):
        packet_name = str(xfa[index])
        packet_object = _object(xfa[index + 1])
        packet_bytes = packet_object.get_data()
        packet_path = output_directory / f"{index // 2:02d}-{_safe_name(packet_name)}.xml"
        packet_path.write_bytes(packet_bytes)
        packet_summary.append({
            "name": packet_name,
            "bytes": len(packet_bytes),
            "path": str(packet_path),
        })
        if packet_name == "template":
            template_summary = summarize_template(packet_bytes)

    summary = {
        "pdf": str(pdf_path),
        "packets": packet_summary,
        "template": template_summary,
    }
    summary_path = output_directory / "xfa-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(summary_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
