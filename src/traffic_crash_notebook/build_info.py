from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import __version__


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str
    build_id: str
    built_at: str
    edition: str
    runtime: str
    application_path: Path
    metadata_path: Path | None = None


def application_path() -> Path:
    """Return the launched executable, or run_app.py for a source checkout."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parents[2] / "run_app.py"


def build_info_path() -> Path:
    return application_path().parent / "BUILD_INFO.txt"


def _source_updated_at() -> str:
    package_file = Path(__file__).resolve().parent / "__init__.py"
    modified = datetime.fromtimestamp(package_file.stat().st_mtime).astimezone()
    return modified.strftime("%m/%d/%Y %H:%M:%S %z")


def load_build_info(path: str | Path | None = None) -> BuildInfo:
    metadata_path = Path(path).resolve() if path is not None else build_info_path()
    launched_path = application_path()
    if metadata_path.is_file():
        lines = [
            line.strip()
            for line in metadata_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        values: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                values[key.strip().lower()] = value.strip()
        first_line = lines[0] if lines else ""
        prefix = "Traffic Crash Notebook "
        version = first_line[len(prefix):].strip() if first_line.startswith(prefix) else __version__
        return BuildInfo(
            version=version or __version__,
            build_id=values.get("build id", f"{version or __version__}-portable"),
            built_at=values.get("built", "Unknown"),
            edition=lines[1] if len(lines) > 1 and ":" not in lines[1] else "Portable Windows build",
            runtime=values.get("build runtime", "Unknown"),
            application_path=launched_path,
            metadata_path=metadata_path,
        )
    return BuildInfo(
        version=__version__,
        build_id=f"{__version__}-source",
        built_at=_source_updated_at(),
        edition="Source / development run",
        runtime=f"Python {platform.python_version()}",
        application_path=launched_path,
    )


def format_about_text(info: BuildInfo, schema_version: int) -> str:
    return "\n".join((
        "Traffic Crash Notebook",
        "",
        f"Version: {info.version}",
        f"Build ID: {info.build_id}",
        f"Build date: {info.built_at}",
        f"Edition: {info.edition}",
        f"Build runtime: {info.runtime}",
        f"Database schema: {schema_version}",
        "",
        f"Running from: {info.application_path}",
        "",
        "Local traffic-crash investigative working notes application.",
    ))
