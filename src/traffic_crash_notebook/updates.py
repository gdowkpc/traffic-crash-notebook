from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


APPLICATION_ID = "traffic-crash-notebook"
APPLICATION_NAME = "Traffic Crash Notebook"
GITHUB_REPOSITORY = "gdowkpc/traffic-crash-notebook"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}"
DEFAULT_UPDATE_MANIFEST_URL = (
    f"{GITHUB_REPOSITORY_URL}/releases/latest/download/update-manifest.json"
)
UPDATE_MANIFEST_SCHEMA_VERSION = 1
MAXIMUM_MANIFEST_BYTES = 512 * 1024
DEFAULT_CHECK_INTERVAL = timedelta(hours=24)
REQUIRED_PORTABLE_FILES = (
    "TrafficCrashNotebook/TrafficCrashNotebook.exe",
    "TrafficCrashNotebook/START_HERE.txt",
    "TrafficCrashNotebook/BUILD_INFO.txt",
    "TrafficCrashNotebook/VERIFY_PORTABLE.bat",
)
_ALLOWED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(RuntimeError):
    pass


class UpdateCancelled(UpdateError):
    pass


@dataclass(frozen=True, slots=True)
class PortableRelease:
    filename: str
    download_url: str
    sha256: str
    size_bytes: int
    build_id: str
    architecture: str = "x86_64"
    packaging: str = "portable-zip"
    requires_admin: bool = False
    self_test: str = "PASS"


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    release_tag: str
    published_at: str
    release_page_url: str
    release_notes: str
    minimum_supported_version: str
    portable: PortableRelease
    package_manifest_url: str = ""
    package_manifest_sha256: str = ""


def parse_version(version: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(str(version).strip())
    if not match:
        raise UpdateError(f"Unsupported version value: {version!r}")
    return tuple(int(value) for value in match.groups())


def is_update_available(current_version: str, available_version: str) -> bool:
    return parse_version(available_version) > parse_version(current_version)


def should_check_for_updates(
    last_successful_check: str,
    *,
    now: datetime | None = None,
    interval: timedelta = DEFAULT_CHECK_INTERVAL,
) -> bool:
    if not last_successful_check.strip():
        return True
    try:
        checked_at = datetime.fromisoformat(last_successful_check.replace("Z", "+00:00"))
    except ValueError:
        return True
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return reference.astimezone(timezone.utc) - checked_at.astimezone(timezone.utc) >= interval


def successful_check_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_mapping(payload: object, field: str) -> dict:
    if not isinstance(payload, dict):
        raise UpdateError(f"The update manifest field {field!r} is not an object.")
    return payload


def _require_https_url(value: object, field: str, *, release_asset: bool = False) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UpdateError(f"The update manifest field {field!r} is not a secure URL.")
    if parsed.hostname.lower() not in _ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateError(f"The update manifest field {field!r} uses an untrusted host.")
    if release_asset and not url.startswith(
        f"{GITHUB_REPOSITORY_URL}/releases/download/"
    ):
        raise UpdateError(f"The update package is not hosted by the official repository.")
    return url


def _require_sha256(value: object, field: str) -> str:
    digest = str(value or "").strip().lower()
    if not _SHA256_PATTERN.fullmatch(digest):
        raise UpdateError(f"The update manifest field {field!r} is not a SHA-256 hash.")
    return digest


def parse_update_manifest(payload: bytes | str | dict) -> UpdateManifest:
    if isinstance(payload, bytes):
        if len(payload) > MAXIMUM_MANIFEST_BYTES:
            raise UpdateError("The update manifest is unexpectedly large.")
        try:
            decoded: object = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UpdateError("The update manifest is not valid UTF-8 JSON.") from error
    elif isinstance(payload, str):
        if len(payload.encode("utf-8")) > MAXIMUM_MANIFEST_BYTES:
            raise UpdateError("The update manifest is unexpectedly large.")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as error:
            raise UpdateError("The update manifest is not valid JSON.") from error
    else:
        decoded = payload

    manifest = _require_mapping(decoded, "root")
    if manifest.get("schema_version") != UPDATE_MANIFEST_SCHEMA_VERSION:
        raise UpdateError("The update manifest uses an unsupported schema version.")
    if manifest.get("application_id") != APPLICATION_ID:
        raise UpdateError("The update manifest is for a different application.")
    if manifest.get("channel") != "stable":
        raise UpdateError("The update manifest is not for the stable release channel.")

    version = str(manifest.get("version", "")).strip()
    parse_version(version)
    release_tag = str(manifest.get("release_tag", "")).strip()
    if release_tag != f"v{version}":
        raise UpdateError("The update manifest version and release tag do not match.")

    release_page_url = _require_https_url(
        manifest.get("release_page_url"),
        "release_page_url",
    )
    expected_release_page = f"{GITHUB_REPOSITORY_URL}/releases/tag/{release_tag}"
    if release_page_url != expected_release_page:
        raise UpdateError("The release page is not the official version page.")

    portable_payload = _require_mapping(
        manifest.get("windows_portable"),
        "windows_portable",
    )
    expected_filename = f"TrafficCrashNotebook-{version}-Windows-Portable.zip"
    filename = str(portable_payload.get("filename", "")).strip()
    if filename != expected_filename or Path(filename).name != filename:
        raise UpdateError("The portable update filename does not match the version.")
    try:
        size_bytes = int(portable_payload.get("size_bytes", 0))
    except (TypeError, ValueError) as error:
        raise UpdateError("The portable update size is invalid.") from error
    if size_bytes <= 0:
        raise UpdateError("The portable update size is invalid.")
    requires_admin = portable_payload.get("requires_admin")
    if requires_admin is not False:
        raise UpdateError("The update manifest does not identify a non-admin package.")
    architecture = str(portable_payload.get("architecture", "")).strip()
    packaging = str(portable_payload.get("packaging", "")).strip()
    self_test = str(portable_payload.get("self_test", "")).strip()
    if architecture != "x86_64" or packaging != "portable-zip" or self_test != "PASS":
        raise UpdateError("The update package is not a verified Windows portable build.")

    package_manifest_payload = _require_mapping(
        manifest.get("package_manifest"),
        "package_manifest",
    )
    package_manifest_url = _require_https_url(
        package_manifest_payload.get("download_url"),
        "package_manifest.download_url",
        release_asset=True,
    )
    package_manifest_sha256 = _require_sha256(
        package_manifest_payload.get("sha256"),
        "package_manifest.sha256",
    )

    minimum_supported_version = str(
        manifest.get("minimum_supported_version", "")
    ).strip()
    parse_version(minimum_supported_version)

    return UpdateManifest(
        version=version,
        release_tag=release_tag,
        published_at=str(manifest.get("published_at", "")).strip(),
        release_page_url=release_page_url,
        release_notes=str(manifest.get("release_notes", "")).strip()[:8000],
        minimum_supported_version=minimum_supported_version,
        portable=PortableRelease(
            filename=filename,
            download_url=_require_https_url(
                portable_payload.get("download_url"),
                "windows_portable.download_url",
                release_asset=True,
            ),
            sha256=_require_sha256(
                portable_payload.get("sha256"),
                "windows_portable.sha256",
            ),
            size_bytes=size_bytes,
            build_id=str(portable_payload.get("build_id", "")).strip(),
            architecture=architecture,
            packaging=packaging,
            requires_admin=requires_admin,
            self_test=self_test,
        ),
        package_manifest_url=package_manifest_url,
        package_manifest_sha256=package_manifest_sha256,
    )


def _validate_response_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateError("GitHub redirected the update request to an untrusted location.")


def fetch_update_manifest(
    manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL,
    *,
    timeout_seconds: float = 12.0,
) -> UpdateManifest:
    _require_https_url(manifest_url, "manifest_url")
    request = Request(
        manifest_url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"{APPLICATION_ID}-update-checker",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            _validate_response_url(response.geturl())
            payload = response.read(MAXIMUM_MANIFEST_BYTES + 1)
    except UpdateError:
        raise
    except Exception as error:
        raise UpdateError(f"The update manifest could not be downloaded: {error}") from error
    if len(payload) > MAXIMUM_MANIFEST_BYTES:
        raise UpdateError("The update manifest is unexpectedly large.")
    return parse_update_manifest(payload)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_portable_zip(path: str | Path) -> None:
    archive = Path(path)
    try:
        with zipfile.ZipFile(archive) as package:
            names = set(package.namelist())
            missing = [required for required in REQUIRED_PORTABLE_FILES if required not in names]
            if missing:
                raise UpdateError(
                    "The downloaded ZIP is missing required portable files: "
                    + ", ".join(missing)
                )
            if package.testzip() is not None:
                raise UpdateError("The downloaded ZIP failed its integrity check.")
    except zipfile.BadZipFile as error:
        raise UpdateError("The downloaded update is not a valid ZIP file.") from error


def download_portable_update(
    release: PortableRelease,
    destination_directory: str | Path,
    *,
    timeout_seconds: float = 30.0,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    destination = Path(destination_directory)
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise UpdateError(f"The update folder is unavailable: {destination}") from error
    final_path = destination / release.filename
    try:
        if final_path.is_file() and final_path.stat().st_size == release.size_bytes:
            if sha256_file(final_path) == release.sha256:
                verify_portable_zip(final_path)
                return final_path
    except OSError as error:
        raise UpdateError(f"The existing update file could not be checked: {final_path}") from error

    temporary_path = destination / f".{release.filename}.{uuid.uuid4().hex}.part"
    request = Request(
        release.download_url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": f"{APPLICATION_ID}-update-downloader",
        },
    )
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            _validate_response_url(response.geturl())
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) != release.size_bytes:
                raise UpdateError("The update download size does not match the manifest.")
            with temporary_path.open("xb") as handle:
                while True:
                    if cancelled and cancelled():
                        raise UpdateCancelled("The update download was cancelled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > release.size_bytes:
                        raise UpdateError("The update download exceeded the manifest size.")
                    digest.update(chunk)
                    handle.write(chunk)
                    if progress:
                        progress(downloaded, release.size_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        if downloaded != release.size_bytes:
            raise UpdateError("The update download is incomplete.")
        if digest.hexdigest() != release.sha256:
            raise UpdateError("The update download failed SHA-256 verification.")
        verify_portable_zip(temporary_path)
        os.replace(temporary_path, final_path)
        return final_path
    except (UpdateError, UpdateCancelled):
        raise
    except Exception as error:
        raise UpdateError(f"The portable update could not be downloaded: {error}") from error
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def format_download_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} bytes"
