from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """Resolve an asset in source and bundled PyInstaller builds."""
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / relative_path
    return Path(__file__).resolve().parents[2] / relative_path


def tiu_logo_path() -> Path:
    return resource_path("assets/tiu_logo.jpg")


DIAGRAM_TEMPLATES = {
    "body": "Body - four views",
    "car": "Passenger car - three views",
    "motorcycle": "Motorcycle - two views",
    "pickup": "Pickup - three views",
    "suv": "SUV - three views",
}


def diagram_path(template_name: str) -> Path:
    safe_name = template_name if template_name in DIAGRAM_TEMPLATES else "body"
    return resource_path(f"assets/diagrams/{safe_name}.png")
