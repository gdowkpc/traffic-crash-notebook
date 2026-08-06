from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from traffic_crash_notebook.paths import (
    DATABASE_FILENAME,
    StorageMigrationError,
    StorageValidationError,
    configured_data_directory,
    legacy_local_data_directory,
    load_storage_config,
    migrate_database,
    recommended_documents_directory,
    save_storage_config,
    validate_storage_directory,
)
from traffic_crash_notebook.ui.storage_setup import (
    StorageSetupWizard,
    ensure_startup_storage,
)


class StorageConfigurationTest(unittest.TestCase):
    def test_local_recommendation_uses_documents_instead_of_appdata(self):
        recommended = recommended_documents_directory()
        self.assertEqual(
            recommended.parts[-2:],
            ("Documents", "Traffic Crash Notebook"),
        )
        self.assertNotEqual(recommended, legacy_local_data_directory())

    def test_first_run_without_k_drive_recommends_documents_not_appdata(self):
        with patch(
            "traffic_crash_notebook.ui.storage_setup.load_storage_config",
            return_value=None,
        ), patch(
            "traffic_crash_notebook.ui.storage_setup.Path.is_dir",
            return_value=False,
        ), patch(
            "traffic_crash_notebook.ui.storage_setup.run_storage_setup",
            return_value=None,
        ) as setup:
            self.assertIsNone(ensure_startup_storage())

        self.assertEqual(
            Path(setup.call_args.kwargs["current_directory"]),
            recommended_documents_directory(),
        )
        self.assertNotEqual(
            Path(setup.call_args.kwargs["current_directory"]),
            legacy_local_data_directory(),
        )

    def test_startup_splash_closes_before_first_run_storage_wizard(self):
        before_prompt = Mock()
        with patch(
            "traffic_crash_notebook.ui.storage_setup.load_storage_config",
            return_value=None,
        ), patch(
            "traffic_crash_notebook.ui.storage_setup.Path.is_dir",
            return_value=False,
        ), patch(
            "traffic_crash_notebook.ui.storage_setup.run_storage_setup",
            return_value=None,
        ):
            self.assertIsNone(
                ensure_startup_storage(before_user_prompt=before_prompt)
            )

        before_prompt.assert_called_once_with()

    def test_configuration_round_trip_and_configured_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_directory = root / "local-settings"
            data_directory = root / "investigator-data"
            config_path = config_directory / "storage_config.json"

            saved = save_storage_config(data_directory, config_path)
            loaded = load_storage_config(config_path)

            self.assertEqual(loaded, saved)
            self.assertEqual(loaded.directory, data_directory.resolve())
            self.assertRegex(loaded.configured_at, r"\d{2}/\d{2}/\d{4}")
            with patch.dict(
                os.environ,
                {"TCN_CONFIG_DIR": str(config_directory)},
                clear=False,
            ):
                self.assertEqual(
                    configured_data_directory(),
                    data_directory.resolve(),
                )

    def test_folder_validation_exercises_files_and_sqlite_without_leaving_probes(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "K-drive-simulation"

            validated = validate_storage_directory(selected)

            self.assertEqual(validated, selected.resolve())
            self.assertEqual(list(selected.glob(".tcn-*")), [])

    def test_folder_validation_rejects_a_file_without_falling_back(self):
        with tempfile.TemporaryDirectory() as directory:
            selected_file = Path(directory) / "not-a-folder"
            selected_file.write_text("occupied", encoding="utf-8")

            with self.assertRaises(StorageValidationError):
                validate_storage_directory(selected_file)

    def test_command_line_storage_override_is_prepared_without_a_wizard(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "command-line-data"
            with patch.dict(
                os.environ,
                {"TCN_DATA_DIR": str(selected)},
                clear=False,
            ):
                config = ensure_startup_storage()

            self.assertEqual(config.directory, selected.resolve())
            self.assertTrue((selected / "Reports").is_dir())
            self.assertTrue((selected / "Backups").is_dir())

    def test_database_migration_is_integrity_checked_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            destination = root / "network" / DATABASE_FILENAME
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
                connection.execute(
                    "INSERT INTO records (value) VALUES ('preserved')"
                )
                connection.commit()

            migrated = migrate_database(source, destination)

            self.assertTrue(source.is_file())
            self.assertEqual(migrated, destination.resolve())
            with closing(sqlite3.connect(destination)) as connection:
                self.assertEqual(
                    connection.execute("SELECT value FROM records").fetchone()[0],
                    "preserved",
                )
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )
            with self.assertRaises(StorageMigrationError):
                migrate_database(source, destination)


class StorageSetupWizardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_wizard_tests_target_and_copies_existing_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_directory = root / "settings"
            source = root / "legacy" / DATABASE_FILENAME
            source.parent.mkdir(parents=True)
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE cases (case_number TEXT NOT NULL)")
                connection.execute(
                    "INSERT INTO cases (case_number) VALUES ('26-TEST')"
                )
                connection.commit()
            target = root / "network-drive" / "Traffic Crash Notebook"

            with patch.dict(
                os.environ,
                {"TCN_CONFIG_DIR": str(config_directory)},
                clear=False,
            ):
                wizard = StorageSetupWizard(
                    current_directory=target,
                    source_database=source,
                )
                try:
                    wizard.show()
                    self.app.processEvents()
                    wizard.next()
                    self.app.processEvents()
                    self.assertEqual(wizard.currentId(), 1)
                    self.assertTrue(wizard.copy_existing.isEnabled())
                    self.assertTrue(wizard.copy_existing.isChecked())
                    self.assertIn(
                        str(target / DATABASE_FILENAME),
                        wizard.database_path_label.text(),
                    )

                    self.assertTrue(wizard.validateCurrentPage())

                    migrated = target / DATABASE_FILENAME
                    self.assertTrue(migrated.is_file())
                    self.assertTrue((target / "Reports").is_dir())
                    self.assertTrue((target / "Backups").is_dir())
                    self.assertEqual(
                        load_storage_config().directory,
                        target.resolve(),
                    )
                    with closing(sqlite3.connect(migrated)) as connection:
                        self.assertEqual(
                            connection.execute(
                                "SELECT case_number FROM cases"
                            ).fetchone()[0],
                            "26-TEST",
                        )
                finally:
                    wizard.close()


if __name__ == "__main__":
    unittest.main()
