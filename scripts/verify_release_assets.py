from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
import zipfile
from pathlib import Path

SCRIPT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = SCRIPT_PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from traffic_crash_notebook.updates import (
    UpdateError,
    parse_update_manifest,
    sha256_file,
    verify_portable_zip,
)


def verify_release_assets(
    update_manifest_path: Path,
    archive_path: Path,
    files_manifest_path: Path,
) -> None:
    manifest = parse_update_manifest(update_manifest_path.read_bytes())
    if archive_path.name != manifest.portable.filename:
        raise UpdateError("The archive filename does not match the update manifest.")
    if archive_path.stat().st_size != manifest.portable.size_bytes:
        raise UpdateError("The archive size does not match the update manifest.")
    if sha256_file(archive_path) != manifest.portable.sha256:
        raise UpdateError("The archive hash does not match the update manifest.")
    verify_portable_zip(archive_path)

    if sha256_file(files_manifest_path) != manifest.package_manifest_sha256:
        raise UpdateError("The complete file-manifest hash does not match the update manifest.")
    files_manifest = json.loads(files_manifest_path.read_text(encoding="utf-8"))
    if files_manifest.get("version") != manifest.version:
        raise UpdateError("The complete file manifest version does not match.")
    archive_metadata = files_manifest.get("archive", {})
    if (
        archive_metadata.get("filename") != archive_path.name
        or archive_metadata.get("size_bytes") != archive_path.stat().st_size
        or archive_metadata.get("sha256") != manifest.portable.sha256
    ):
        raise UpdateError("The complete file manifest archive metadata does not match.")

    declared = files_manifest.get("files")
    if not isinstance(declared, list) or not declared:
        raise UpdateError("The complete file manifest has no file entries.")
    declared_by_path = {entry.get("path"): entry for entry in declared}
    if len(declared_by_path) != len(declared) or None in declared_by_path:
        raise UpdateError("The complete file manifest contains duplicate or invalid paths.")

    with zipfile.ZipFile(archive_path) as package:
        actual_names = {info.filename for info in package.infolist() if not info.is_dir()}
        if actual_names != set(declared_by_path):
            raise UpdateError("The complete file manifest does not list the exact ZIP contents.")
        for info in package.infolist():
            if info.is_dir():
                continue
            entry = declared_by_path[info.filename]
            if (
                entry.get("size_bytes") != info.file_size
                or entry.get("compressed_size_bytes") != info.compress_size
            ):
                raise UpdateError(f"File size metadata does not match: {info.filename}")
            digest = hashlib.sha256()
            with package.open(info) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != entry.get("sha256"):
                raise UpdateError(f"File hash does not match: {info.filename}")

    if archive_metadata.get("entry_count") != len(actual_names):
        raise UpdateError("The complete file-manifest entry count does not match the ZIP.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify all portable release assets.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--files", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        verify_release_assets(
            arguments.manifest.resolve(),
            arguments.archive.resolve(),
            arguments.files.resolve(),
        )
        print("Release ZIP and complete manifests: PASS")
        return 0
    except BaseException:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
