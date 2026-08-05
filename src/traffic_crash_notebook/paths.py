from __future__ import annotations

import ctypes
import json
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


APP_FOLDER_NAME = "TrafficCrashNotebook"
DATABASE_FILENAME = "traffic_crash_notebook.sqlite3"
STORAGE_CONFIG_FILENAME = "storage_config.json"
STORAGE_CONFIG_VERSION = 1


class StorageConfigurationError(RuntimeError):
    pass


class StorageValidationError(RuntimeError):
    pass


class StorageMigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_directory: str
    configured_at: str = ""
    config_version: int = STORAGE_CONFIG_VERSION

    @property
    def directory(self) -> Path:
        return Path(self.data_directory).expanduser()

    @property
    def database_path(self) -> Path:
        return self.directory / DATABASE_FILENAME

    @property
    def reports_directory(self) -> Path:
        return self.directory / "Reports"

    @property
    def backups_directory(self) -> Path:
        return self.directory / "Backups"


def local_settings_directory() -> Path:
    override = os.environ.get("TCN_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / APP_FOLDER_NAME
    return Path.home() / ".local" / "share" / APP_FOLDER_NAME


def legacy_local_data_directory() -> Path:
    return local_settings_directory()


def storage_config_path() -> Path:
    return local_settings_directory() / STORAGE_CONFIG_FILENAME


def load_storage_config(path: str | Path | None = None) -> StorageConfig | None:
    config_path = Path(path) if path is not None else storage_config_path()
    if not config_path.is_file():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        config = StorageConfig(
            data_directory=str(payload["data_directory"]).strip(),
            configured_at=str(payload.get("configured_at", "")),
            config_version=int(payload.get("config_version", 0)),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as error:
        raise StorageConfigurationError(
            f"The storage configuration could not be read: {config_path}"
        ) from error
    if config.config_version != STORAGE_CONFIG_VERSION:
        raise StorageConfigurationError(
            f"Unsupported storage configuration version {config.config_version}."
        )
    if not config.data_directory:
        raise StorageConfigurationError("The configured data folder is blank.")
    return config


def save_storage_config(
    directory: str | Path,
    path: str | Path | None = None,
) -> StorageConfig:
    selected = Path(directory).expanduser().resolve()
    config = StorageConfig(
        data_directory=str(selected),
        configured_at=datetime.now().astimezone().strftime(
            "%m/%d/%Y %H:%M:%S %z"
        ),
    )
    config_path = Path(path) if path is not None else storage_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_name(
        f".{config_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(asdict(config), indent=2) + "\n",
            encoding="utf-8",
        )
        if temporary_path.stat().st_size == 0:
            raise StorageConfigurationError(
                "The new storage configuration file is empty."
            )
        os.replace(temporary_path, config_path)
    except OSError as error:
        raise StorageConfigurationError(
            f"The storage configuration could not be saved: {config_path}"
        ) from error
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass
    return config


def configured_data_directory() -> Path:
    override = os.environ.get("TCN_DATA_DIR")
    if override:
        return Path(override).expanduser()
    config = load_storage_config()
    if config is not None:
        return config.directory
    return legacy_local_data_directory()


def data_directory() -> Path:
    path = configured_data_directory()
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_database_path() -> Path:
    return data_directory() / DATABASE_FILENAME


def reports_directory() -> Path:
    path = data_directory() / "Reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backups_directory() -> Path:
    path = data_directory() / "Backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def recommended_k_drive_directory() -> Path:
    return Path("K:/Traffic Crash Notebook")


def recommended_documents_directory() -> Path:
    return Path.home() / "Documents" / "Traffic Crash Notebook"


def is_network_location(path: str | Path) -> bool:
    selected = Path(path).expanduser()
    if str(selected).startswith(("\\\\", "//")):
        return True
    if os.name != "nt" or not selected.drive:
        return False
    root = f"{selected.drive}\\"
    drive_remote = 4
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(root) == drive_remote
    except (AttributeError, OSError):
        return False


def validate_storage_directory(directory: str | Path) -> Path:
    selected = Path(directory).expanduser()
    if not str(selected).strip():
        raise StorageValidationError("Select a data storage folder.")
    try:
        selected.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StorageValidationError(
            f"The selected folder is not available: {selected}\n\n{error}"
        ) from error
    if not selected.is_dir():
        raise StorageValidationError(
            f"The selected storage location is not a folder: {selected}"
        )

    token = uuid.uuid4().hex
    probe_path = selected / f".tcn-write-test-{token}.tmp"
    renamed_probe_path = selected / f".tcn-write-test-{token}.renamed"
    database_probe_path = selected / f".tcn-database-test-{token}.sqlite3"
    try:
        payload = b"Traffic Crash Notebook storage test\n"
        with probe_path.open("xb") as probe:
            probe.write(payload)
            probe.flush()
            os.fsync(probe.fileno())
        if probe_path.read_bytes() != payload:
            raise StorageValidationError(
                "The selected folder did not return the storage test data correctly."
            )
        probe_path.replace(renamed_probe_path)
        renamed_probe_path.unlink()

        with closing(sqlite3.connect(database_probe_path, timeout=5)) as connection:
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("CREATE TABLE storage_test (value TEXT NOT NULL)")
            connection.execute(
                "INSERT INTO storage_test (value) VALUES (?)",
                ("PASS",),
            )
            connection.commit()
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise StorageValidationError(
                    f"The selected folder failed the database integrity test: {result}"
                )
    except StorageValidationError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise StorageValidationError(
            f"The selected folder failed its write/database test: {selected}\n\n{error}"
        ) from error
    finally:
        for temporary_path in (
            probe_path,
            renamed_probe_path,
            database_probe_path,
            database_probe_path.with_name(database_probe_path.name + "-journal"),
        ):
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except OSError:
                pass
    return selected.resolve()


def migrate_database(source: str | Path, destination: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.is_file():
        raise StorageMigrationError(
            f"The existing case database was not found: {source_path}"
        )
    if os.path.normcase(str(source_path)) == os.path.normcase(str(destination_path)):
        return destination_path
    if destination_path.exists():
        raise StorageMigrationError(
            "A database already exists in the selected folder. Nothing was overwritten."
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(
        f".{destination_path.name}.{uuid.uuid4().hex}.migrating"
    )
    try:
        with closing(sqlite3.connect(source_path, timeout=10)) as source_connection:
            with closing(sqlite3.connect(temporary_path, timeout=10)) as destination_connection:
                source_connection.backup(destination_connection)
                destination_connection.commit()
                result = destination_connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                if result != "ok":
                    raise StorageMigrationError(
                        f"The copied database failed its integrity check: {result}"
                    )
        os.replace(temporary_path, destination_path)
    except StorageMigrationError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise StorageMigrationError(
            f"The existing database could not be copied to {destination_path}."
        ) from error
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass
    return destination_path
