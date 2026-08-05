from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.generate_release_manifests import generate_release_manifests
from scripts.verify_release_assets import verify_release_assets
from traffic_crash_notebook.updates import (
    REQUIRED_PORTABLE_FILES,
    UpdateError,
    download_portable_update,
    fetch_update_manifest,
    is_update_available,
    parse_update_manifest,
    should_check_for_updates,
)


def portable_zip_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in REQUIRED_PORTABLE_FILES:
            archive.writestr(name, f"test content for {name}\n")
    return output.getvalue()


def manifest_payload(package: bytes, version: str = "1.2.3") -> dict:
    tag = f"v{version}"
    filename = f"TrafficCrashNotebook-{version}-Windows-Portable.zip"
    base = (
        "https://github.com/gdowkpc/traffic-crash-notebook/releases/download/"
        f"{tag}"
    )
    return {
        "schema_version": 1,
        "application_id": "traffic-crash-notebook",
        "application_name": "Traffic Crash Notebook",
        "channel": "stable",
        "version": version,
        "release_tag": tag,
        "published_at": "2026-08-05T21:00:00Z",
        "release_page_url": (
            f"https://github.com/gdowkpc/traffic-crash-notebook/releases/tag/{tag}"
        ),
        "release_notes": "Verified portable update.",
        "minimum_supported_version": "0.4.8",
        "windows_portable": {
            "filename": filename,
            "download_url": f"{base}/{filename}",
            "sha256": hashlib.sha256(package).hexdigest(),
            "size_bytes": len(package),
            "build_id": f"{version}-test",
            "architecture": "x86_64",
            "packaging": "portable-zip",
            "requires_admin": False,
            "self_test": "PASS",
        },
        "package_manifest": {
            "filename": f"TrafficCrashNotebook-{version}-Windows-Portable.files.json",
            "download_url": (
                f"{base}/TrafficCrashNotebook-{version}-Windows-Portable.files.json"
            ),
            "sha256": "a" * 64,
        },
        "source": {
            "repository_url": "https://github.com/gdowkpc/traffic-crash-notebook",
            "commit": "f" * 40,
        },
    }


class FakeResponse:
    def __init__(self, payload: bytes, final_url: str, content_length: bool = True):
        self.stream = io.BytesIO(payload)
        self.final_url = final_url
        self.headers = {"Content-Length": str(len(payload))} if content_length else {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def geturl(self) -> str:
        return self.final_url

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


class UpdateTest(unittest.TestCase):
    def test_manifest_parses_and_versions_compare(self):
        package = portable_zip_bytes()
        manifest = parse_update_manifest(manifest_payload(package))
        self.assertEqual(manifest.version, "1.2.3")
        self.assertEqual(manifest.portable.size_bytes, len(package))
        self.assertTrue(is_update_available("1.2.2", manifest.version))
        self.assertFalse(is_update_available("1.2.3", manifest.version))
        self.assertFalse(is_update_available("2.0.0", manifest.version))

    def test_manifest_rejects_untrusted_or_unverified_packages(self):
        package = portable_zip_bytes()
        untrusted = manifest_payload(package)
        untrusted["windows_portable"]["download_url"] = "https://example.com/update.zip"
        with self.assertRaises(UpdateError):
            parse_update_manifest(untrusted)

        admin_package = manifest_payload(package)
        admin_package["windows_portable"]["requires_admin"] = True
        with self.assertRaises(UpdateError):
            parse_update_manifest(admin_package)

        bad_hash = manifest_payload(package)
        bad_hash["windows_portable"]["sha256"] = "not-a-hash"
        with self.assertRaises(UpdateError):
            parse_update_manifest(bad_hash)

    def test_automatic_check_interval_is_twenty_four_hours(self):
        now = datetime(2026, 8, 5, 21, 0, tzinfo=timezone.utc)
        self.assertTrue(should_check_for_updates("", now=now))
        self.assertFalse(
            should_check_for_updates(
                (now - timedelta(hours=23)).isoformat(),
                now=now,
            )
        )
        self.assertTrue(
            should_check_for_updates(
                (now - timedelta(hours=24)).isoformat(),
                now=now,
            )
        )
        self.assertTrue(should_check_for_updates("invalid timestamp", now=now))

    def test_manifest_download_is_size_limited_and_parsed(self):
        package = portable_zip_bytes()
        payload = json.dumps(manifest_payload(package)).encode("utf-8")
        response = FakeResponse(
            payload,
            "https://release-assets.githubusercontent.com/update-manifest.json",
            content_length=False,
        )
        with patch("traffic_crash_notebook.updates.urlopen", return_value=response):
            manifest = fetch_update_manifest()
        self.assertEqual(manifest.version, "1.2.3")

    def test_portable_download_verifies_hash_size_and_required_files(self):
        package = portable_zip_bytes()
        manifest = parse_update_manifest(manifest_payload(package))
        response = FakeResponse(
            package,
            "https://release-assets.githubusercontent.com/portable.zip",
        )
        progress: list[tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as directory, patch(
            "traffic_crash_notebook.updates.urlopen",
            return_value=response,
        ):
            result = download_portable_update(
                manifest.portable,
                directory,
                progress=lambda received, total: progress.append((received, total)),
            )
            self.assertEqual(result.read_bytes(), package)
            self.assertEqual(progress[-1], (len(package), len(package)))
            self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_failed_hash_never_replaces_the_final_download(self):
        package = portable_zip_bytes()
        manifest = parse_update_manifest(manifest_payload(package))
        release = replace(manifest.portable, sha256="0" * 64)
        response = FakeResponse(
            package,
            "https://release-assets.githubusercontent.com/portable.zip",
        )
        with tempfile.TemporaryDirectory() as directory, patch(
            "traffic_crash_notebook.updates.urlopen",
            return_value=response,
        ):
            with self.assertRaises(UpdateError):
                download_portable_update(release, directory)
            self.assertFalse((Path(directory) / release.filename).exists())
            self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_release_generator_creates_update_and_full_file_manifests(self):
        package = portable_zip_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "TrafficCrashNotebook-1.2.3-Windows-Portable.zip"
            archive.write_bytes(package)
            build_info = root / "BUILD_INFO.txt"
            build_info.write_text(
                "Traffic Crash Notebook 1.2.3\n"
                "Portable Windows x64 build\n"
                "Build ID: 1.2.3-test-build\n"
                "Built: 08/05/2026 14:30:00 -07:00\n",
                encoding="utf-8",
            )
            release_notes = root / "RELEASE_NOTES.md"
            release_notes.write_text("Verified updater release.", encoding="utf-8")
            output = root / "release"
            with patch.dict(
                "os.environ",
                {"GITHUB_SHA": "f" * 40},
                clear=False,
            ):
                update_path, files_path = generate_release_manifests(
                    project_root=root,
                    version="1.2.3",
                    archive=archive,
                    build_info_path=build_info,
                    release_notes_path=release_notes,
                    output_directory=output,
                )

            parsed = parse_update_manifest(update_path.read_bytes())
            self.assertEqual(parsed.portable.build_id, "1.2.3-test-build")
            self.assertEqual(parsed.portable.sha256, hashlib.sha256(package).hexdigest())
            full_manifest = json.loads(files_path.read_text(encoding="utf-8"))
            self.assertEqual(full_manifest["archive"]["entry_count"], 4)
            self.assertEqual(
                {entry["path"] for entry in full_manifest["files"]},
                set(REQUIRED_PORTABLE_FILES),
            )
            self.assertTrue(all(entry["sha256"] for entry in full_manifest["files"]))
            verify_release_assets(update_path, archive, files_path)


if __name__ == "__main__":
    unittest.main()
