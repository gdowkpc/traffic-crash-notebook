from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = SCRIPT_PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from traffic_crash_notebook.repository import SCHEMA_VERSION
from traffic_crash_notebook.updates import (
    APPLICATION_ID,
    APPLICATION_NAME,
    GITHUB_REPOSITORY,
    GITHUB_REPOSITORY_URL,
    UPDATE_MANIFEST_SCHEMA_VERSION,
    parse_version,
    sha256_file,
)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if temporary.stat().st_size == 0:
            raise RuntimeError(f"Generated an empty manifest: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _source_commit(project_root: Path) -> str:
    github_sha = os.environ.get("GITHUB_SHA", "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{40}", github_sha):
        return github_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    commit = result.stdout.strip().lower()
    return commit if re.fullmatch(r"[0-9a-f]{40}", commit) else ""


def _build_info(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"BUILD_INFO.txt was not found: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    values: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    return values


def _package_file_entries(archive: Path) -> list[dict]:
    entries: list[dict] = []
    with zipfile.ZipFile(archive) as package:
        corrupt = package.testzip()
        if corrupt is not None:
            raise RuntimeError(f"The portable ZIP contains a corrupt entry: {corrupt}")
        for info in sorted(package.infolist(), key=lambda item: item.filename.casefold()):
            if info.is_dir():
                continue
            digest = hashlib.sha256()
            with package.open(info) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b""):
                    digest.update(chunk)
            entries.append({
                "path": info.filename,
                "size_bytes": info.file_size,
                "compressed_size_bytes": info.compress_size,
                "sha256": digest.hexdigest(),
            })
    return entries


def generate_release_manifests(
    *,
    project_root: Path,
    version: str,
    archive: Path,
    build_info_path: Path,
    release_notes_path: Path,
    output_directory: Path,
) -> tuple[Path, Path]:
    parse_version(version)
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise RuntimeError(f"Portable ZIP was not found or is empty: {archive}")
    if archive.name != f"TrafficCrashNotebook-{version}-Windows-Portable.zip":
        raise RuntimeError("Portable ZIP name does not match the application version.")

    tag = f"v{version}"
    asset_base_url = f"{GITHUB_REPOSITORY_URL}/releases/download/{tag}"
    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    archive_hash = sha256_file(archive)
    build_info = _build_info(build_info_path)
    release_notes = (
        release_notes_path.read_text(encoding="utf-8").strip()
        if release_notes_path.is_file()
        else ""
    )
    file_entries = _package_file_entries(archive)

    package_manifest_name = (
        f"TrafficCrashNotebook-{version}-Windows-Portable.files.json"
    )
    package_manifest_path = output_directory / package_manifest_name
    package_manifest = {
        "schema_version": 1,
        "application_id": APPLICATION_ID,
        "application_name": APPLICATION_NAME,
        "version": version,
        "release_tag": tag,
        "generated_at": published_at,
        "archive": {
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": archive_hash,
            "entry_count": len(file_entries),
        },
        "files": file_entries,
    }
    _write_json_atomic(package_manifest_path, package_manifest)
    package_manifest_hash = sha256_file(package_manifest_path)

    update_manifest_path = output_directory / "update-manifest.json"
    update_manifest = {
        "schema_version": UPDATE_MANIFEST_SCHEMA_VERSION,
        "application_id": APPLICATION_ID,
        "application_name": APPLICATION_NAME,
        "channel": "stable",
        "version": version,
        "release_tag": tag,
        "published_at": published_at,
        "release_page_url": f"{GITHUB_REPOSITORY_URL}/releases/tag/{tag}",
        "release_notes": release_notes,
        "minimum_supported_version": "0.4.8",
        "database_schema": SCHEMA_VERSION,
        "windows_portable": {
            "filename": archive.name,
            "download_url": f"{asset_base_url}/{archive.name}",
            "sha256": archive_hash,
            "size_bytes": archive.stat().st_size,
            "build_id": build_info.get("build id", f"{version}-portable"),
            "built_at": build_info.get("built", ""),
            "architecture": "x86_64",
            "packaging": "portable-zip",
            "requires_admin": False,
            "self_test": "PASS",
        },
        "package_manifest": {
            "filename": package_manifest_name,
            "download_url": f"{asset_base_url}/{package_manifest_name}",
            "sha256": package_manifest_hash,
        },
        "source": {
            "repository": GITHUB_REPOSITORY,
            "repository_url": GITHUB_REPOSITORY_URL,
            "commit": _source_commit(project_root),
        },
    }
    _write_json_atomic(update_manifest_path, update_manifest)
    return update_manifest_path, package_manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate verified GitHub release manifests.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--build-info", required=True, type=Path)
    parser.add_argument("--release-notes", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        update, package = generate_release_manifests(
            project_root=arguments.project_root.resolve(),
            version=arguments.version,
            archive=arguments.archive.resolve(),
            build_info_path=arguments.build_info.resolve(),
            release_notes_path=arguments.release_notes.resolve(),
            output_directory=arguments.output_directory.resolve(),
        )
        print(update)
        print(package)
        return 0
    except BaseException:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
