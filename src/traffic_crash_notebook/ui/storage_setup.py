from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from ..paths import (
    DATABASE_FILENAME,
    StorageConfig,
    StorageConfigurationError,
    StorageMigrationError,
    StorageValidationError,
    is_network_location,
    legacy_local_data_directory,
    load_storage_config,
    migrate_database,
    recommended_documents_directory,
    recommended_k_drive_directory,
    save_storage_config,
    validate_storage_directory,
)


class StorageSetupWizard(QWizard):
    def __init__(
        self,
        current_directory: str | Path,
        source_database: str | Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traffic Crash Notebook - Data Storage Setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self.resize(720, 540)
        self.selected_config: StorageConfig | None = None
        self.source_database = (
            Path(source_database).expanduser().resolve()
            if source_database is not None
            else None
        )

        welcome = QWizardPage()
        welcome.setTitle("Choose where Traffic Crash Notebook saves your work")
        welcome_layout = QVBoxLayout(welcome)
        introduction = QLabel(
            "Traffic Crash Notebook stores all cases in one database. This setup "
            "will choose its permanent folder and the default folders for reports "
            "and backups.\n\n"
            "If your K: drive is your assigned private network drive, you can select "
            "it on the next page. The application will test the folder before saving "
            "anything and will never silently switch to an empty local database when "
            "the selected drive is unavailable."
        )
        introduction.setWordWrap(True)
        introduction.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        welcome_layout.addWidget(introduction)
        safety = QLabel(
            "Important: use a folder assigned to one investigator. Do not open the "
            "same database from multiple computers at the same time."
        )
        safety.setWordWrap(True)
        safety.setStyleSheet(
            "background: #fff4d6; border: 1px solid #d9b44a; padding: 10px;"
        )
        welcome_layout.addWidget(safety)
        welcome_layout.addStretch(1)
        self.addPage(welcome)

        location = QWizardPage()
        location.setTitle("Select the investigator's storage folder")
        location.setSubTitle(
            "The case database will be stored here. Reports and backups will use "
            "subfolders inside the same location."
        )
        location_layout = QVBoxLayout(location)
        path_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(Path(current_directory).expanduser()))
        self.folder_edit.setPlaceholderText("K:\\Traffic Crash Notebook")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.folder_edit, 1)
        path_row.addWidget(browse)
        location_layout.addLayout(path_row)

        quick_row = QHBoxLayout()
        use_k_drive = QPushButton("Use K: Drive")
        use_k_drive.clicked.connect(
            lambda: self.folder_edit.setText(
                str(recommended_k_drive_directory())
            )
        )
        use_local = QPushButton("Use Documents Folder")
        use_local.clicked.connect(
            lambda: self.folder_edit.setText(
                str(recommended_documents_directory())
            )
        )
        quick_row.addWidget(use_k_drive)
        quick_row.addWidget(use_local)
        quick_row.addStretch(1)
        location_layout.addLayout(quick_row)

        summary_form = QFormLayout()
        self.database_path_label = QLabel()
        self.reports_path_label = QLabel()
        self.backups_path_label = QLabel()
        for widget in (
            self.database_path_label,
            self.reports_path_label,
            self.backups_path_label,
        ):
            widget.setWordWrap(True)
            widget.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
        summary_form.addRow("Case database", self.database_path_label)
        summary_form.addRow("PDF reports", self.reports_path_label)
        summary_form.addRow("Manual backups", self.backups_path_label)
        location_layout.addLayout(summary_form)

        self.copy_existing = QCheckBox(
            "Copy my existing cases into the selected folder"
        )
        self.copy_existing.setChecked(True)
        location_layout.addWidget(self.copy_existing)
        self.existing_status = QLabel()
        self.existing_status.setWordWrap(True)
        location_layout.addWidget(self.existing_status)

        self.network_warning = QLabel()
        self.network_warning.setWordWrap(True)
        self.network_warning.setStyleSheet(
            "background: #fff4d6; border: 1px solid #d9b44a; padding: 10px;"
        )
        location_layout.addWidget(self.network_warning)
        self.network_acknowledgement = QCheckBox(
            "I will use this database from only one computer at a time"
        )
        location_layout.addWidget(self.network_acknowledgement)
        location_layout.addStretch(1)
        self.addPage(location)

        self.folder_edit.textChanged.connect(self._update_summary)
        self._update_summary()

    @property
    def selected_directory(self) -> Path:
        return Path(self.folder_edit.text().strip()).expanduser()

    def _browse(self) -> None:
        current = self.selected_directory
        start = current if current.is_dir() else current.parent
        if not start.is_dir():
            start = recommended_documents_directory().parent
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Traffic Crash Notebook Data Folder",
            str(start),
        )
        if selected:
            self.folder_edit.setText(selected)

    def _update_summary(self, *_args) -> None:
        selected = self.selected_directory
        database_path = selected / DATABASE_FILENAME
        self.database_path_label.setText(str(database_path))
        self.reports_path_label.setText(str(selected / "Reports"))
        self.backups_path_label.setText(str(selected / "Backups"))

        source_exists = bool(
            self.source_database and self.source_database.is_file()
        )
        same_database = bool(
            self.source_database
            and os.path.normcase(str(self.source_database))
            == os.path.normcase(str(database_path.resolve()))
        )
        target_exists = database_path.is_file()
        can_copy = source_exists and not same_database and not target_exists
        self.copy_existing.setEnabled(can_copy)
        if not can_copy:
            self.copy_existing.setChecked(False)
        elif not self.copy_existing.isChecked():
            self.copy_existing.setChecked(True)

        if same_database:
            status = "Your current case database is already in this folder."
        elif target_exists:
            status = (
                "An existing Traffic Crash Notebook database was found here. "
                "It will be opened; no database will be overwritten."
            )
        elif source_exists:
            status = (
                f"Existing cases are available at {self.source_database}. "
                "Leave the copy option selected to preserve them in the new folder. "
                "The original database will remain unchanged as a recovery copy."
            )
        else:
            status = "No existing case database was found. A new one will be created."
        self.existing_status.setText(status)

        network = is_network_location(selected)
        self.network_warning.setVisible(network)
        self.network_acknowledgement.setVisible(network)
        if network:
            self.network_warning.setText(
                "Network folder selected. If the drive disconnects, Traffic Crash "
                "Notebook will stop and show an error instead of switching storage "
                "locations. SQLite databases should not be opened simultaneously "
                "from multiple computers."
            )
        else:
            self.network_warning.clear()
            self.network_acknowledgement.setChecked(False)

    def validateCurrentPage(self) -> bool:
        if self.currentId() == 0:
            return True
        selected = self.selected_directory
        if is_network_location(selected) and not self.network_acknowledgement.isChecked():
            QMessageBox.warning(
                self,
                "Confirm single-computer use",
                "Confirm that this database will be used from only one computer at a time.",
            )
            return False
        try:
            selected = validate_storage_directory(selected)
            target_database = selected / DATABASE_FILENAME
            if self.copy_existing.isChecked() and self.source_database:
                migrate_database(self.source_database, target_database)
            (selected / "Reports").mkdir(parents=True, exist_ok=True)
            (selected / "Backups").mkdir(parents=True, exist_ok=True)
            self.selected_config = save_storage_config(selected)
        except (
            StorageConfigurationError,
            StorageMigrationError,
            StorageValidationError,
            OSError,
        ) as error:
            QMessageBox.critical(
                self,
                "Storage setup could not be completed",
                str(error),
            )
            return False
        return True


def run_storage_setup(
    current_directory: str | Path,
    source_database: str | Path | None = None,
    parent=None,
) -> StorageConfig | None:
    wizard = StorageSetupWizard(
        current_directory=current_directory,
        source_database=source_database,
        parent=parent,
    )
    if wizard.exec() != QWizard.DialogCode.Accepted:
        return None
    return wizard.selected_config


def ensure_startup_storage(parent=None) -> StorageConfig | None:
    override = os.environ.get("TCN_DATA_DIR")
    if override:
        selected = validate_storage_directory(override)
        (selected / "Reports").mkdir(parents=True, exist_ok=True)
        (selected / "Backups").mkdir(parents=True, exist_ok=True)
        return StorageConfig(data_directory=str(selected))

    try:
        config = load_storage_config()
    except StorageConfigurationError as error:
        QMessageBox.warning(
            parent,
            "Storage configuration needs attention",
            f"{error}\n\nChoose the storage folder again to repair it.",
        )
        config = None

    legacy_directory = legacy_local_data_directory()
    legacy_database = legacy_directory / DATABASE_FILENAME
    if config is None:
        recommended = (
            recommended_k_drive_directory()
            if Path("K:/").is_dir()
            else recommended_documents_directory()
        )
        return run_storage_setup(
            current_directory=recommended,
            source_database=legacy_database if legacy_database.is_file() else None,
            parent=parent,
        )

    while True:
        try:
            selected = validate_storage_directory(config.directory)
            (selected / "Reports").mkdir(parents=True, exist_ok=True)
            (selected / "Backups").mkdir(parents=True, exist_ok=True)
            return config
        except (StorageValidationError, OSError) as error:
            message = QMessageBox(parent)
            message.setIcon(QMessageBox.Icon.Critical)
            message.setWindowTitle("Configured data folder is unavailable")
            message.setText(
                "Traffic Crash Notebook cannot reach its configured data folder."
            )
            message.setInformativeText(
                f"{config.directory}\n\n{error}\n\n"
                "The application will not open an empty replacement database. "
                "Reconnect the drive and retry, choose a different location, or exit."
            )
            retry = message.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
            change = message.addButton(
                "Choose Different Location",
                QMessageBox.ButtonRole.ActionRole,
            )
            exit_button = message.addButton(
                "Exit",
                QMessageBox.ButtonRole.RejectRole,
            )
            message.setDefaultButton(retry)
            message.exec()
            clicked = message.clickedButton()
            if clicked is retry:
                continue
            if clicked is change:
                source_database = config.database_path
                new_config = run_storage_setup(
                    current_directory=config.directory,
                    source_database=(
                        source_database if source_database.is_file() else None
                    ),
                    parent=parent,
                )
                if new_config is not None:
                    config = new_config
                continue
            if clicked is exit_button:
                return None
            return None
