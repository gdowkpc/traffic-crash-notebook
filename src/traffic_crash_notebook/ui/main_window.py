from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QDir,
    QIODevice,
    QTemporaryDir,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIntValidator,
    QPageLayout,
    QPageSize,
    QPalette,
    QPixmap,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..build_info import format_about_text, load_build_info
from ..date_format import (
    DISPLAY_DATE_PLACEHOLDER,
    DISPLAY_TIME_PLACEHOLDER,
    format_date_for_display,
    format_time_for_display,
    normalize_date_for_storage,
    normalize_time_for_storage,
)
from ..exchange_report import (
    exchange_report_page_plan,
    exchange_report_people,
    export_exchange_report_pdf,
    person_exchange_address,
    person_exchange_phone,
    resolve_exchange_vehicle_drivers,
)
from ..models import (
    CARDINAL_DIRECTIONS,
    CASE_STATUSES,
    CHECKLIST_DATE_FIELDS,
    HIT_RUN_INVESTIGATION_STATUSES,
    INVESTIGATIVE_CHECKLIST_GROUPS,
    ROAD_AREA_OPTIONS,
    SCENE_EVIDENCE_METHODS,
    SURVEILLANCE_VIDEO_EVIDENCE,
    WEATHER_DISPLAY_UNITS,
    ContactRelationship,
    CrashCase,
    CrashDetails,
    HitRunEvidenceItem,
    HitRunOverview,
    HitRunPersonLead,
    HitRunVehicleLead,
    Person,
    InvestigativeChecklist,
    RoadConditions,
    UserDefaults,
    Vehicle,
    VEHICLE_WORKFLOW_FIELDS,
    format_crash_location,
    normalize_scene_evidence_methods,
)
from ..pdf_export import export_case_compact_pdf, export_case_pdf, export_case_summary_pdf
from ..pdf_printing import print_pdf_document, selected_pdf_page_indexes
from ..repository import SCHEMA_VERSION, CaseRepository
from ..resources import tiu_logo_path
from ..updates import (
    UpdateManifest,
    format_download_size,
    is_update_available,
    should_check_for_updates,
    successful_check_timestamp,
)
from .app_identity import configure_application
from .dialogs import (
    ChronologyDialog,
    ChargeDispositionDialog,
    ContactRelationshipDialog,
    DriverProfileDialog,
    HitRunEvidenceDialog,
    HitRunPersonLeadDialog,
    HitRunVehicleLeadDialog,
    MotorcycleInspectionDialog,
    ParticipantDetailsDialog,
    PersonDialog,
    RoadwayDialog,
    SurfaceObservationDialog,
    TaskDialog,
    VehicleDialog,
    VehicleInspectionDialog,
    VideoSourceDialog,
    VRUAnalysisDialog,
    WitnessDetailsDialog,
)
from .spellcheck_text_edit import SpellCheckedTextEdit
from .storage_setup import run_storage_setup
from .update_support import UpdateCheckThread, UpdateDownloadThread


WEATHER_HISTORY_URL = "https://www.wunderground.com/history"


APP_STYLE = """
QMainWindow, QWidget { background: #f4f6f8; color: #172733; }
QToolBar { background: #18344a; spacing: 6px; border: none; padding: 5px; }
QToolBar QToolButton { color: white; background: transparent; padding: 7px 10px; border-radius: 4px; }
QToolBar QToolButton:hover { background: #2e607e; }
QToolBar QToolButton:checked { background: #2e6f95; }
QTabWidget::pane { background: white; border: 1px solid #d8dfe4; }
QTabBar::tab { background: #e8edf1; padding: 8px 15px; margin-right: 2px; }
QTabBar::tab:selected { background: white; color: #18344a; font-weight: 600; }
QLineEdit, QTextEdit, QComboBox, QTableWidget, QListWidget {
    background: white; border: 1px solid #c9d2d9; border-radius: 3px; padding: 5px;
}
QListWidget::item { color: #172733; padding: 6px 5px; }
QListWidget::item:hover { background: #dcebf4; color: #172733; }
QListWidget::item:selected,
QListWidget::item:selected:active,
QListWidget::item:selected:!active { background: #2e6f95; color: #ffffff; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #2e6f95; }
QPushButton { background: #2e6f95; color: white; border: none; border-radius: 4px; padding: 7px 12px; }
QPushButton:hover { background: #245a79; }
QPushButton[secondary="true"] { background: #e5ebef; color: #263c4b; }
QHeaderView::section { background: #eaf2f7; color: #18344a; padding: 6px; border: none; border-right: 1px solid #d6e0e6; font-weight: 600; }
QLabel#caseTitle { font-size: 21px; font-weight: 700; color: #18344a; }
QLabel#caseSubtitle { color: #5d6870; }
"""


def _button(text: str, callback, secondary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("secondary", secondary)
    button.clicked.connect(callback)
    return button


def _date_line(text: str = "") -> QLineEdit:
    widget = QLineEdit(format_date_for_display(text))
    widget.setPlaceholderText(DISPLAY_DATE_PLACEHOLDER)
    widget.editingFinished.connect(
        lambda: widget.setText(format_date_for_display(widget.text()))
    )
    return widget


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setWidget(widget)
    return area


class ApplicationSettingsDialog(QDialog):
    def __init__(
        self,
        data_directory: Path,
        defaults: UserDefaults,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.change_storage_requested = False
        self.last_update_check = defaults.last_update_check
        self.setWindowTitle("Traffic Crash Notebook Settings")
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)

        title = QLabel("Application settings")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #18344a;")
        layout.addWidget(title)

        storage_group = QGroupBox("Case data location")
        storage_layout = QVBoxLayout(storage_group)
        storage_text = QLabel(
            "All cases, reports, backups, the personal spell-check dictionary, and "
            "the user defaults below are kept at this selected location. AppData "
            "contains only a small replaceable pointer to this folder; it does not "
            "contain case records."
        )
        storage_text.setWordWrap(True)
        storage_layout.addWidget(storage_text)
        self.data_directory_label = QLabel(str(data_directory))
        self.data_directory_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.data_directory_label.setWordWrap(True)
        self.data_directory_label.setStyleSheet(
            "background: white; border: 1px solid #c9d2d9; padding: 8px;"
        )
        storage_layout.addWidget(self.data_directory_label)
        self.change_storage_button = QPushButton("Change data location...")
        self.change_storage_button.setProperty("secondary", True)
        self.change_storage_button.clicked.connect(self._request_storage_change)
        storage_layout.addWidget(
            self.change_storage_button,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        layout.addWidget(storage_group)

        defaults_group = QGroupBox("Defaults for new cases")
        defaults_layout = QFormLayout(defaults_group)
        self.user_name_edit = QLineEdit(defaults.user_name)
        self.user_name_edit.setPlaceholderText("Assigned officer name")
        self.dpsst_edit = QLineEdit(defaults.dpsst)
        self.dpsst_edit.setValidator(QIntValidator(0, 999999999, self.dpsst_edit))
        self.dpsst_edit.setMaxLength(9)
        self.dpsst_edit.setPlaceholderText("Numbers only")
        self.assignment_edit = QLineEdit(defaults.assignment)
        self.assignment_edit.setPlaceholderText("Unit, division, or precinct")
        defaults_layout.addRow("User name", self.user_name_edit)
        defaults_layout.addRow("DPSST", self.dpsst_edit)
        defaults_layout.addRow("Assignment", self.assignment_edit)
        defaults_note = QLabel(
            "These values populate the assigned-officer fields when a new case is "
            "created. Existing cases are never overwritten."
        )
        defaults_note.setWordWrap(True)
        defaults_layout.addRow(defaults_note)
        self.auto_check_updates_checkbox = QCheckBox(
            "Automatically check GitHub for verified portable updates"
        )
        self.auto_check_updates_checkbox.setChecked(defaults.auto_check_updates)
        self.auto_check_updates_checkbox.setToolTip(
            "Checks at most once every 24 hours. Updates are never installed automatically."
        )
        defaults_layout.addRow(self.auto_check_updates_checkbox)
        layout.addWidget(defaults_group)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(lambda: self._finish(False))
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _finish(self, change_storage: bool) -> None:
        dpsst = self.dpsst_edit.text().strip()
        if dpsst and not dpsst.isdecimal():
            QMessageBox.warning(
                self,
                "DPSST must be numeric",
                "Enter only numbers in the DPSST field.",
            )
            return
        self.change_storage_requested = change_storage
        self.accept()

    def _request_storage_change(self) -> None:
        self._finish(True)

    def user_defaults(self) -> UserDefaults:
        return UserDefaults(
            user_name=self.user_name_edit.text().strip(),
            dpsst=self.dpsst_edit.text().strip(),
            assignment=self.assignment_edit.text().strip(),
            auto_check_updates=self.auto_check_updates_checkbox.isChecked(),
            last_update_check=self.last_update_check,
        )


class MainWindow(QMainWindow):
    def __init__(self, repository: CaseRepository):
        super().__init__()
        self.repository = repository
        self.build_info = load_build_info()
        self.current_case: CrashCase | None = None
        self.conditions: RoadConditions | None = None
        self.checklist: InvestigativeChecklist | None = None
        self.crash_details: CrashDetails | None = None
        self.hit_run_overview: HitRunOverview | None = None
        self.packet_preview_directory = QTemporaryDir(
            str(
                Path(QDir.tempPath())
                / "TrafficCrashNotebook-packet-preview-XXXXXX"
            )
        )
        if not self.packet_preview_directory.isValid():
            raise RuntimeError("Unable to create the case-packet preview folder.")
        self.packet_preview_generation = 0
        self.packet_stale_preview_paths: set[Path] = set()
        self.packet_preview_path = Path(
            self.packet_preview_directory.path()
        ) / "Traffic_Crash_Case_Packet_Preview_000000.pdf"
        self.exchange_preview_directory = QTemporaryDir(
            str(
                Path(QDir.tempPath())
                / "TrafficCrashNotebook-exchange-preview-XXXXXX"
            )
        )
        if not self.exchange_preview_directory.isValid():
            raise RuntimeError("Unable to create the exchange-report preview folder.")
        self.exchange_preview_generation = 0
        self.exchange_stale_preview_paths: set[Path] = set()
        self.exchange_preview_case_id: str | None = None
        self.exchange_preview_path = Path(
            self.exchange_preview_directory.path()
        ) / "Traffic_Crash_Exchange_Report_Preview_000000.pdf"
        self.loading = False
        self.overview_dirty = False
        self.storage_error_active = False
        self.update_check_thread: UpdateCheckThread | None = None
        self.update_download_thread: UpdateDownloadThread | None = None
        self.update_progress_dialog: QProgressDialog | None = None
        self.update_check_was_manual = False
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(700)
        self.autosave_timer.timeout.connect(self.save_overview)
        self.periodic_autosave_timer = QTimer(self)
        self.periodic_autosave_timer.setInterval(30_000)
        self.periodic_autosave_timer.timeout.connect(self._autosave_if_dirty)
        self.periodic_autosave_timer.start()

        self.setWindowTitle(f"Traffic Crash Notebook {__version__}")
        self.resize(1320, 820)
        self.setMinimumSize(900, 560)
        self._build_menu_bar()
        self._build_toolbar()
        self._build_content()
        self._connect_case_subtab_autosave()
        self.setStatusBar(QStatusBar())
        self.setStyleSheet(APP_STYLE)
        self.refresh_cases(select_first=True)
        if not os.environ.get("TCN_DISABLE_UPDATE_CHECK"):
            QTimer.singleShot(2500, self._check_updates_if_due)

    def _build_menu_bar(self) -> None:
        settings_menu = self.menuBar().addMenu("&Settings")
        self.application_settings_action = QAction("Application Settings...", self)
        self.application_settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(self.application_settings_action)
        settings_menu.addSeparator()
        self.storage_location_action = QAction("Data Storage Location...", self)
        self.storage_location_action.triggered.connect(
            self.change_storage_location
        )
        settings_menu.addAction(self.storage_location_action)

        help_menu = self.menuBar().addMenu("&Help")
        self.check_updates_action = QAction("Check for Updates...", self)
        self.check_updates_action.triggered.connect(
            lambda: self.check_for_updates(manual=True)
        )
        help_menu.addAction(self.check_updates_action)
        help_menu.addSeparator()
        self.about_action = QAction("About Traffic Crash Notebook", self)
        self.about_action.triggered.connect(self.show_about)
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        actions = (
            ("New Case", self.new_case),
            ("Save", self.save_overview),
            ("Export Full Working Packet", self.export_pdf),
            ("Export Compact Packet", self.export_compact_pdf),
            ("Export Exchange Report", self.export_exchange_report),
            ("Export Quick Review", self.export_summary_pdf),
            ("Back Up", self.backup_database),
            ("Data Folder", self.open_data_folder),
        )
        for label, callback in actions:
            action = QAction(label, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)

    def _build_content(self) -> None:
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_case_sidebar())
        splitter.addWidget(self._build_case_workspace())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 1040])
        self.setCentralWidget(splitter)

    def _build_case_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setMinimumWidth(225)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        heading = QLabel("CASES")
        heading.setStyleSheet("font-weight: 700; color: #5d6870; letter-spacing: 1px;")
        layout.addWidget(heading)
        self.case_search = QLineEdit()
        self.case_search.setPlaceholderText("Filter cases")
        self.case_search.textChanged.connect(self.refresh_cases)
        layout.addWidget(self.case_search)
        self.case_list = QListWidget()
        self.case_list.setAlternatingRowColors(True)
        case_list_palette = self.case_list.palette()
        case_list_palette.setColor(QPalette.ColorRole.Highlight, QColor("#2e6f95"))
        case_list_palette.setColor(
            QPalette.ColorRole.HighlightedText,
            QColor("#ffffff"),
        )
        self.case_list.setPalette(case_list_palette)
        self.case_list.currentItemChanged.connect(self._case_selection_changed)
        layout.addWidget(self.case_list, 1)
        layout.addWidget(_button("New Case", self.new_case))
        return panel

    def _build_case_workspace(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        header = QHBoxLayout()
        logo = QLabel()
        logo_path = tiu_logo_path()
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            logo.setPixmap(pixmap.scaled(
                70, 70, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        logo.setFixedSize(76, 76)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background: #000; border-radius: 5px;")
        header.addWidget(logo)
        header_text = QVBoxLayout()
        self.case_title = QLabel("No case selected")
        self.case_title.setObjectName("caseTitle")
        self.case_subtitle = QLabel("Create a case to begin")
        self.case_subtitle.setObjectName("caseSubtitle")
        header_text.addWidget(self.case_title)
        header_text.addWidget(self.case_subtitle)
        header.addLayout(header_text, 1)
        self.counts_label = QLabel()
        self.counts_label.setStyleSheet("color: #5d6870; font-weight: 600;")
        header.addWidget(self.counts_label)
        self.packet_preview_button = _button(
            "Packet Preview",
            self.show_packet_preview,
        )
        self.packet_preview_button.setToolTip(
            "Open the full or compact case-packet preview, printing, and PDF export workspace"
        )
        header.addWidget(self.packet_preview_button)
        self.settings_button = _button(
            "Settings",
            self.show_settings,
            secondary=True,
        )
        self.settings_button.setToolTip(
            "Set the case data location and defaults for new cases"
        )
        header.addWidget(self.settings_button)
        self.about_button = _button(
            f"About v{self.build_info.version}",
            self.show_about,
            secondary=True,
        )
        self.about_button.setToolTip("Show the exact version, build date, and executable location")
        header.addWidget(self.about_button)
        layout.addLayout(header)
        self.packet_preview_dialog = self._build_packet_preview_dialog()
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Overview")
        self.tabs.addTab(self._build_packet_tab(), "Packet")
        self.tabs.addTab(self._build_conditions_tab(), "Road / Weather")
        self.tabs.addTab(self._build_people_tab(), "People")
        self.tabs.addTab(self._build_vehicles_tab(), "Vehicles")
        self.tabs.addTab(self._build_hit_run_tab(), "Hit & Run")
        self.tabs.addTab(self._build_vru_tab(), "VRU Analysis")
        self.tabs.addTab(self._build_chronology_tab(), "Journal")
        self.tabs.addTab(self._build_tasks_tab(), "Tasks / Evidence")
        self.exchange_report_tab_index = self.tabs.addTab(
            self._build_exchange_report_tab(),
            "Exchange Report",
        )
        self.tabs.currentChanged.connect(self._case_tab_changed)
        layout.addWidget(self.tabs, 1)
        return container

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.case_number = QLineEdit()
        self.crash_date = _date_line()
        self.crash_time = QLineEdit()
        self.crash_time.setPlaceholderText(DISPLAY_TIME_PLACEHOLDER)
        self.location = QLineEdit()
        self.location.setReadOnly(True)
        self.location.setPlaceholderText("Entered under Packet > Crash Location")
        self.location.setToolTip(
            "Automatically generated from Road where collision occurred and Intersection with."
        )
        self.investigator = QLineEdit()
        self.assigned_officer_dpsst = QLineEdit()
        self.assigned_officer_dpsst.setValidator(
            QIntValidator(0, 999999999, self.assigned_officer_dpsst)
        )
        self.assigned_officer_dpsst.setPlaceholderText("Numbers only")
        self.assignment = QLineEdit()
        self.assignment.setPlaceholderText("Traffic, East Precinct, Central Precinct...")
        self.status = QComboBox()
        self.status.addItems(CASE_STATUSES)
        form.addRow("Case number", self.case_number)
        form.addRow("Crash date", self.crash_date)
        form.addRow("Crash time", self.crash_time)
        form.addRow("Location", self.location)
        form.addRow("Assigned officer", self.investigator)
        form.addRow("DPSST", self.assigned_officer_dpsst)
        form.addRow("Assignment", self.assignment)
        form.addRow("Status", self.status)
        layout.addLayout(form)
        self.summary = SpellCheckedTextEdit()
        self.summary.setPlaceholderText("Brief description of the crash and the present investigative picture")
        self.general_notes = SpellCheckedTextEdit()
        self.general_notes.setPlaceholderText("General working notes")
        for label, widget in (
            ("Crash summary", self.summary),
            ("General investigative notes", self.general_notes),
        ):
            layout.addWidget(QLabel(label))
            layout.addWidget(widget, 1)
        for widget in (
            self.case_number,
            self.crash_date,
            self.crash_time,
            self.investigator,
            self.assigned_officer_dpsst,
            self.assignment,
        ):
            widget.textChanged.connect(self.schedule_autosave)
        self.status.currentTextChanged.connect(self.schedule_autosave)
        self.summary.textChanged.connect(self.schedule_autosave)
        self.general_notes.textChanged.connect(self.schedule_autosave)
        return tab

    def _build_packet_tab(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        tabs = QTabWidget()
        self.packet_widgets: dict[str, QWidget] = {}
        self.checklist_widgets: dict[str, QLineEdit] = {}
        self.checklist_boxes: dict[str, QCheckBox] = {}
        self.checklist_date_widgets: dict[str, QLineEdit] = {}
        self.scene_evidence_boxes: dict[str, QCheckBox] = {}

        def packet_line(name: str, placeholder: str = "") -> QLineEdit:
            widget = _date_line() if name == "team_notified_date" else QLineEdit()
            widget.setPlaceholderText(placeholder)
            widget.textChanged.connect(self.schedule_autosave)
            self.packet_widgets[name] = widget
            return widget

        def packet_choice(name: str, values: tuple[str, ...]) -> QComboBox:
            widget = QComboBox()
            widget.addItems(values)
            widget.currentTextChanged.connect(self.schedule_autosave)
            self.packet_widgets[name] = widget
            return widget

        milestones = QWidget()
        milestones_layout = QHBoxLayout(milestones)
        for group_name, items in INVESTIGATIVE_CHECKLIST_GROUPS:
            group = QGroupBox(group_name)
            group_layout = QVBoxLayout(group)
            for item in items:
                box = QCheckBox(item)
                box.toggled.connect(self.schedule_autosave)
                self.checklist_boxes[item] = box
                if item in CHECKLIST_DATE_FIELDS:
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.addWidget(box, 1)
                    date_widget = _date_line()
                    date_widget.setToolTip(f"Completion date for {item}")
                    date_widget.setMaximumWidth(110)
                    date_widget.setEnabled(False)
                    date_widget.textChanged.connect(self.schedule_autosave)
                    self.checklist_date_widgets[item] = date_widget
                    box.toggled.connect(
                        lambda checked, checklist_item=item:
                        self._sync_checklist_date_availability(checklist_item, checked)
                    )
                    row_layout.addWidget(date_widget)
                    group_layout.addWidget(row)
                else:
                    group_layout.addWidget(box)
            group_layout.addStretch(1)
            milestones_layout.addWidget(group, 1)
        tabs.addTab(_scrollable(milestones), "Checklist")

        da_tab = QWidget()
        da_layout = QVBoxLayout(da_tab)
        da_form = QFormLayout()
        for name, label, placeholder in (
            ("assigned_dda", "Assigned DDA", ""),
            ("da_case_number", "DA case number", ""),
            ("court_case_number", "Court case number", ""),
        ):
            widget = QLineEdit()
            widget.setPlaceholderText(placeholder)
            widget.textChanged.connect(self.schedule_autosave)
            self.checklist_widgets[name] = widget
            da_form.addRow(label, widget)
        da_layout.addLayout(da_form)
        charges_tab, self.charges_table = self._table_tab(
            ["Charge", "Disposition"],
            self.add_charge_disposition,
            self.edit_charge_disposition,
            self.delete_charge_disposition,
        )
        da_layout.addWidget(charges_tab, 1)
        tabs.addTab(da_tab, "DA / Charges")

        location_tab = QWidget()
        location_form = QFormLayout(location_tab)
        location_form.addRow("City", packet_line("nearest_city"))
        location_form.addRow("County", packet_line("county"))
        road_name = packet_line("road_name")
        intersection_road = packet_line("intersection_road")
        road_name.textChanged.connect(self._sync_location_preview)
        intersection_road.textChanged.connect(self._sync_location_preview)
        location_form.addRow("Road where collision occurred", road_name)
        location_form.addRow("Intersection with", intersection_road)
        location_form.addRow("Not at intersection - feet", packet_line("non_intersection_feet"))
        location_form.addRow("Not at intersection - miles", packet_line("non_intersection_miles"))
        location_form.addRow(
            "Not at intersection - direction",
            packet_choice("non_intersection_direction", CARDINAL_DIRECTIONS),
        )
        location_form.addRow("Latitude", packet_line("latitude"))
        location_form.addRow("Longitude", packet_line("longitude"))
        location_form.addRow("Road jurisdiction", packet_line("road_jurisdiction"))
        tabs.addTab(_scrollable(location_tab), "Crash Location")

        response_tab = QWidget()
        response_layout = QVBoxLayout(response_tab)
        response_form = QFormLayout()
        for name, label, placeholder in (
            (
                "team_notified_date",
                "Crash team notified date",
                DISPLAY_DATE_PLACEHOLDER,
            ),
            ("team_notified_time", "Crash team notified time", "HH:MM"),
            ("investigator_en_route", "Investigator en route", "HH:MM"),
            ("investigator_arrival", "Investigator arrival", "HH:MM"),
            ("sergeant", "MCT Sergeant", ""),
            ("prosecutor_on_scene", "Prosecutor on scene", ""),
            ("medical_examiner_on_scene", "MDI", ""),
        ):
            response_form.addRow(label, packet_line(name, placeholder))
        response_layout.addLayout(response_form)
        evidence_group = QGroupBox("Scene documentation and evidence methods")
        evidence_grid = QGridLayout(evidence_group)
        for index, method in enumerate(SCENE_EVIDENCE_METHODS):
            box = QCheckBox(method)
            box.toggled.connect(self.schedule_autosave)
            self.scene_evidence_boxes[method] = box
            evidence_grid.addWidget(box, index // 3, index % 3)
        self.investigator_photos_checkbox = self.scene_evidence_boxes[
            "Investigator Photos"
        ]
        self.axon_upload_checkbox = self.scene_evidence_boxes["Uploaded to Axon"]
        self.axon_upload_checkbox.setToolTip(
            "Available after Investigator Photos is selected."
        )
        self.investigator_photos_checkbox.toggled.connect(
            self._sync_axon_upload_availability
        )
        self._sync_axon_upload_availability(
            self.investigator_photos_checkbox.isChecked()
        )
        self.surveillance_video_indicator = QCheckBox(
            f"{SURVEILLANCE_VIDEO_EVIDENCE} (automatic from Video Sources)"
        )
        self.surveillance_video_indicator.setEnabled(False)
        self.surveillance_video_indicator.setToolTip(
            "Selected automatically whenever at least one Video Source exists."
        )
        automatic_index = len(SCENE_EVIDENCE_METHODS)
        evidence_grid.addWidget(
            self.surveillance_video_indicator,
            automatic_index // 3,
            automatic_index % 3,
        )
        response_layout.addWidget(evidence_group)
        response_layout.addStretch(1)
        tabs.addTab(_scrollable(response_tab), "Response / Evidence")

        video_tab, self.video_sources_table = self._table_tab(
            ["Video source", "Address", "Uploaded to Axon", "Notes"],
            self.add_video_source,
            self.edit_video_source,
            self.delete_video_source,
        )
        self.video_sources_table.setColumnWidth(0, 220)
        self.video_sources_table.setColumnWidth(1, 240)
        self.video_sources_table.setColumnWidth(2, 130)
        tabs.addTab(video_tab, "Video Sources")

        outer.addWidget(tabs, 1)
        return container

    def _build_conditions_tab(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        self.conditions_tabs = QTabWidget()
        self.conditions_tabs.setObjectName("road_weather_subtabs")
        tabs = self.conditions_tabs
        self.condition_widgets: dict[str, QWidget] = {}
        self.area_type_boxes: dict[str, QCheckBox] = {}

        def line(name: str, placeholder: str = "") -> QLineEdit:
            widget = QLineEdit()
            widget.setPlaceholderText(placeholder)
            widget.textChanged.connect(self.schedule_autosave)
            self.condition_widgets[name] = widget
            return widget

        def memo(name: str, placeholder: str = "") -> QTextEdit:
            widget = SpellCheckedTextEdit()
            widget.setPlaceholderText(placeholder)
            widget.textChanged.connect(self.schedule_autosave)
            self.condition_widgets[name] = widget
            return widget

        def choice(name: str, values: tuple[str, ...]) -> QComboBox:
            widget = QComboBox()
            widget.addItems(values)
            widget.currentTextChanged.connect(self.schedule_autosave)
            self.condition_widgets[name] = widget
            return widget

        weather = QWidget()
        weather.setObjectName("weather_form")
        weather_layout = QVBoxLayout(weather)
        weather_layout.setContentsMargins(10, 10, 10, 10)
        weather_layout.setSpacing(6)
        weather_source_row = QHBoxLayout()
        weather_source_row.addWidget(QLabel("Historical weather source:"))
        self.weather_history_link = QLabel(
            f'<a href="{WEATHER_HISTORY_URL}">'
            "Open Weather Underground History</a>"
        )
        self.weather_history_link.setObjectName("weather_history_link")
        self.weather_history_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.weather_history_link.setOpenExternalLinks(False)
        self.weather_history_link.setToolTip(
            "Opens the fixed Weather Underground history page in the default browser; "
            "no case information is included in the link."
        )
        self.weather_history_link.linkActivated.connect(
            self.open_weather_history
        )
        weather_source_row.addWidget(self.weather_history_link)
        weather_source_row.addStretch(1)
        weather_layout.addLayout(weather_source_row)
        self.weather_fields_grid = QGridLayout()
        self.weather_fields_grid.setObjectName("weather_fields_grid")
        self.weather_fields_grid.setHorizontalSpacing(10)
        self.weather_fields_grid.setVerticalSpacing(5)

        weather_pairs = (
            (
                ("temperature", "Temperature", "Numeric observation"),
                ("dew_point", "Dew point", "Numeric observation"),
            ),
            (
                ("winds", "Winds", "Direction and speed"),
                ("humidity", "Humidity", "Numeric observation"),
            ),
            (
                ("pressure", "Pressure", "Numeric observation"),
                ("precipitation", "Precipitation", "Numeric total or None"),
            ),
            (
                ("weather_station", "Weather station", "Station name or identifier"),
                ("weather_time", "Time of reading", "HH:MM; include time zone if known"),
            ),
        )
        for row, pair in enumerate(weather_pairs):
            for column_group, (name, label, placeholder) in enumerate(pair):
                unit = WEATHER_DISPLAY_UNITS.get(name)
                display_label = f"{label} ({unit})" if unit else label
                label_widget = QLabel(display_label)
                label_widget.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                field_column = column_group * 2
                self.weather_fields_grid.addWidget(label_widget, row, field_column)
                self.weather_fields_grid.addWidget(
                    line(name, placeholder),
                    row,
                    field_column + 1,
                )

        condition_label = QLabel("Condition")
        condition_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.weather_fields_grid.addWidget(condition_label, 4, 0)
        self.weather_fields_grid.addWidget(
            line("weather_condition", "Clear, rain, fog..."),
            4,
            1,
            1,
            3,
        )
        self.weather_fields_grid.setColumnStretch(1, 1)
        self.weather_fields_grid.setColumnStretch(3, 1)
        weather_layout.addLayout(self.weather_fields_grid)
        other_weather = memo("other_weather", "Weather source and other relevant observations")
        other_weather.setMaximumHeight(90)
        weather_layout.addWidget(QLabel("Other weather information"))
        weather_layout.addWidget(other_weather)
        weather_layout.addStretch(1)
        tabs.addTab(_scrollable(weather), "Weather")

        surfaces_tab, self.surface_observations_table = self._table_tab(
            ["Roadway / Location", "Composition", "Condition", "Friction / Drag Factor", "Notes"],
            self.add_surface_observation,
            self.edit_surface_observation,
            self.delete_surface_observation,
            item_name="Surface",
        )
        surfaces_tab.setObjectName("surface_observations_tab")
        self.surface_observations_table.setObjectName("surface_observations_table")
        surface_guidance = QLabel(
            "Add a separate surface record for each roadway, lane, shoulder, or test location. "
            "Double-click a row to edit it."
        )
        surface_guidance.setWordWrap(True)
        surface_guidance.setStyleSheet("color: #5d6870;")
        surfaces_tab.layout().insertWidget(0, surface_guidance)
        self.surface_observations_table.setColumnWidth(0, 190)
        self.surface_observations_table.setColumnWidth(1, 150)
        self.surface_observations_table.setColumnWidth(2, 130)
        self.surface_observations_table.setColumnWidth(3, 145)
        tabs.addTab(surfaces_tab, "Surface")

        lighting = QWidget()
        lighting_form = QFormLayout(lighting)
        lighting_conditions = memo("lighting_conditions", "Ambient light, sun location, artificial lighting, and contrast")
        lighting_conditions.setMaximumHeight(130)
        lighting_form.addRow("Lighting conditions", lighting_conditions)
        lighting_form.addRow("Sunrise", line("sunrise", "HH:MM"))
        lighting_form.addRow("Sunset", line("sunset", "HH:MM"))
        lighting_form.addRow(
            "Civil twilight - morning",
            line("civil_twilight_morning", "HH:MM"),
        )
        lighting_form.addRow(
            "Civil twilight - evening",
            line("civil_twilight_evening", "HH:MM"),
        )
        lighting_form.addRow("Moonrise", line("moonrise", "HH:MM"))
        lighting_form.addRow("Moonset", line("moonset", "HH:MM"))
        lighting_form.addRow(
            "Moon phase",
            line("moon_phase", "New, crescent, quarter, gibbous, or full"),
        )
        lighting_form.addRow("Streetlights working", choice("streetlights_working", ("Unknown", "Yes", "No", "Not applicable")))
        streetlight_notes = memo("streetlight_notes", "Streetlight type, location, condition, or test notes")
        streetlight_notes.setMaximumHeight(90)
        lighting_form.addRow("Streetlight notes", streetlight_notes)
        visual = memo("visual_obstructions", "Vegetation, signs, parked vehicles, glare, roadway geometry...")
        visual.setMaximumHeight(150)
        lighting_form.addRow("Visual obstructions", visual)
        lighting_form.addRow("Area type", line("area_type", "Residential, business, industrial, rural..."))
        area_group = QGroupBox("Area classifications")
        area_layout = QHBoxLayout(area_group)
        for option in ROAD_AREA_OPTIONS:
            box = QCheckBox(option)
            box.toggled.connect(self.schedule_autosave)
            area_layout.addWidget(box)
            self.area_type_boxes[option] = box
        area_layout.addStretch(1)
        lighting_form.addRow(area_group)
        tabs.addTab(_scrollable(lighting), "Lighting / Visibility")

        roadways_tab, self.roadways_table = self._table_tab(
            [
                "Roadway",
                "Speed Limit",
                "Posted",
                "Posting Location",
                "Curve / Critical Speed",
                "Characteristics / Controls",
            ],
            self.add_roadway,
            self.edit_roadway,
            self.delete_roadway,
        )
        self.roadways_table.setColumnWidth(0, 190)
        self.roadways_table.setColumnWidth(1, 90)
        self.roadways_table.setColumnWidth(2, 75)
        self.roadways_table.setColumnWidth(3, 180)
        self.roadways_table.setColumnWidth(4, 190)
        tabs.addTab(roadways_tab, "Roadways")

        analysis = QWidget()
        analysis_layout = QFormLayout(analysis)
        impact = memo("initial_point_of_collision", "Evidence supporting the initial point or area of collision")
        impact.setMaximumHeight(210)
        skid = memo("skid_test_notes", "Drag sled, test skid, surface comparison, and related notes")
        skid.setMaximumHeight(210)
        analysis_layout.addRow("Initial point of collision", impact)
        analysis_layout.addRow("Skid test / drag sled notes", skid)
        tabs.addTab(_scrollable(analysis), "Scene Analysis")
        outer.addWidget(tabs, 1)
        return container

    def _table_tab(
        self,
        columns: list[str],
        add_callback,
        edit_callback,
        delete_callback,
        *,
        item_name: str = "",
    ):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        button_row = QHBoxLayout()
        label_suffix = f" {item_name}" if item_name else ""
        button_row.addWidget(_button(f"Add{label_suffix}", add_callback))
        button_row.addWidget(_button(f"Edit{label_suffix}", edit_callback, secondary=True))
        button_row.addWidget(_button(f"Remove{label_suffix}", delete_callback, secondary=True))
        button_row.addStretch(1)
        layout.addLayout(button_row)
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.doubleClicked.connect(edit_callback)
        layout.addWidget(table, 1)
        return tab, table

    def _build_people_tab(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        self.people_tabs = QTabWidget()

        people_tab, self.people_table = self._table_tab(
            ["Name", "Role(s)", "DOB", "Cell", "Notes"],
            self.add_person, self.edit_person, self.delete_person,
        )
        detail_row = QHBoxLayout()
        detail_row.addWidget(_button("Participant / Medical", self.edit_participant_details, secondary=True))
        detail_row.addWidget(_button("Driver Background", self.edit_driver_profile, secondary=True))
        detail_row.addWidget(_button("Witness Interview", self.edit_witness_details, secondary=True))
        detail_row.addStretch(1)
        people_tab.layout().insertLayout(1, detail_row)
        self.people_table.setColumnWidth(0, 190)
        self.people_table.setColumnWidth(1, 200)
        self.people_tabs.addTab(people_tab, "People")
        self.people_tabs.addTab(self._build_contacts_tab(), "Contacts")
        layout.addWidget(self.people_tabs)
        return container

    def _build_contacts_tab(self):
        tab, self.contacts_table = self._table_tab(
            ["Person", "Type", "Contact", "Cell", "Home", "Work", "Organization", "Notes"],
            self.add_contact, self.edit_contact, self.delete_contact,
        )
        guidance = QLabel(
            "Each contact belongs to one person. Select a person on the People subtab "
            "before adding a contact to prefill that association."
        )
        guidance.setWordWrap(True)
        guidance.setStyleSheet("color: #5d6870;")
        tab.layout().insertWidget(0, guidance)
        self.contacts_table.setColumnWidth(0, 190)
        self.contacts_table.setColumnWidth(1, 125)
        self.contacts_table.setColumnWidth(2, 180)
        return tab

    def _build_vru_tab(self):
        tab, self.vru_table = self._table_tab(
            ["Pedestrian / Bicyclist", "Vehicle", "Position / Movement", "Night Visibility Equipment", "Notes"],
            self.add_vru_analysis, self.edit_vru_analysis, self.delete_vru_analysis,
        )
        self.vru_table.setColumnWidth(0, 190)
        self.vru_table.setColumnWidth(1, 180)
        self.vru_table.setColumnWidth(2, 240)
        return tab

    def _build_vehicles_tab(self):
        tab, self.vehicles_table = self._table_tab(
            [
                "Number",
                "Vehicle",
                "Driver",
                "Plate",
                "Vehicle Workflow",
                "Towing",
                "Release",
                "Insurance / Claim",
                "Damage / Notes",
            ],
            self.add_vehicle, self.edit_vehicle, self.delete_vehicle,
        )
        inspection_row = QHBoxLayout()
        inspection_row.addWidget(_button("Inspection / Tires", self.edit_vehicle_inspection, secondary=True))
        inspection_row.addWidget(_button("Motorcycle Inspection", self.edit_motorcycle_inspection, secondary=True))
        inspection_row.addStretch(1)
        tab.layout().insertLayout(1, inspection_row)
        self.vehicles_table.setColumnWidth(0, 80)
        self.vehicles_table.setColumnWidth(1, 220)
        self.vehicles_table.setColumnWidth(2, 180)
        self.vehicles_table.setColumnWidth(4, 230)
        self.vehicles_table.setColumnWidth(5, 220)
        self.vehicles_table.setColumnWidth(6, 250)
        self.vehicles_table.setColumnWidth(7, 280)
        return tab

    def _build_packet_preview_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("packetPreviewDialog")
        dialog.setWindowTitle("Case Packet Preview")
        dialog.setModal(False)
        dialog.setMinimumSize(760, 540)
        dialog.resize(1100, 800)
        dialog.setSizeGripEnabled(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_packet_preview_panel())
        return dialog

    def _build_packet_preview_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        title = QLabel("Case Packet Preview")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #18344a;")
        layout.addWidget(title)
        guidance = QLabel(
            "This is a read-only preview generated from the current case. Choose the "
            "Full Working Packet for the attorney folder and handwritten continuation "
            "space, or the Compact Packet for a shorter completed-case packet. Make "
            "changes in the case tabs, then refresh this preview."
        )
        guidance.setWordWrap(True)
        guidance.setStyleSheet("color: #5d6870;")
        layout.addWidget(guidance)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Packet type"))
        self.packet_preview_mode = QComboBox()
        self.packet_preview_mode.addItem("Full Working Packet", "full")
        self.packet_preview_mode.addItem("Compact Packet", "compact")
        self.packet_preview_mode.setToolTip(
            "Full includes writable continuation areas; Compact omits unused sections."
        )
        self.packet_preview_mode.currentIndexChanged.connect(self.preview_case_packet)
        actions.addWidget(self.packet_preview_mode)
        actions.addWidget(_button("Refresh Preview", self.preview_case_packet))
        print_button = _button(
            "Print Packet...",
            self.print_case_packet,
            secondary=True,
        )
        print_button.setToolTip(
            "Print the current packet preview using the standard Windows printer dialog"
        )
        actions.addWidget(print_button)
        actions.addWidget(
            _button(
                "Export Preview to PDF",
                self.export_case_packet_preview,
                secondary=True,
            )
        )
        actions.addStretch(1)
        layout.addLayout(actions)

        self.packet_preview_status = QLabel(
            "Open Packet Preview from the case header or choose Refresh Preview."
        )
        self.packet_preview_status.setStyleSheet("color: #5d6870;")
        layout.addWidget(self.packet_preview_status)

        self.packet_pdf_document = QPdfDocument(self)
        self.packet_pdf_buffer: QBuffer | None = None
        self.packet_pdf_view = QPdfView(container)
        self.packet_pdf_view.setDocument(self.packet_pdf_document)
        self.packet_pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.packet_pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(self.packet_pdf_view, 1)
        return container

    def _build_exchange_report_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        title = QLabel("Traffic Crash Exchange Report")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #18344a;")
        layout.addWidget(title)
        guidance = QLabel(
            "This is a read-only preview generated from the existing Overview, People, "
            "Driver Background, Participant / Medical, and Vehicle records. Make changes "
            "in those case areas, then refresh this preview. Every saved Passenger and "
            "Witness is included as an involved-person block, with additional pages added "
            "as needed. The PDF prints only records that exist and always places the "
            "information / responsibilities page last."
        )
        guidance.setWordWrap(True)
        guidance.setStyleSheet("color: #5d6870;")
        layout.addWidget(guidance)

        actions = QHBoxLayout()
        actions.addWidget(_button("Refresh Preview", self.preview_exchange_report))
        print_button = _button(
            "Print Exchange Report...",
            self.print_exchange_report,
            secondary=True,
        )
        print_button.setToolTip(
            "Print the current exchange report using the standard Windows printer dialog"
        )
        actions.addWidget(print_button)
        actions.addWidget(
            _button(
                "Export Preview to PDF",
                self.export_exchange_report,
                secondary=True,
            )
        )
        actions.addStretch(1)
        layout.addLayout(actions)

        self.exchange_readiness_label = QLabel()
        self.exchange_readiness_label.setWordWrap(True)
        self.exchange_readiness_label.setStyleSheet(
            "background: #eaf2f7; color: #18344a; padding: 7px; border-radius: 4px;"
        )
        layout.addWidget(self.exchange_readiness_label)

        self.exchange_preview_status = QLabel("Open this tab or choose Refresh Preview.")
        self.exchange_preview_status.setStyleSheet("color: #5d6870;")
        layout.addWidget(self.exchange_preview_status)

        self.exchange_pdf_document = QPdfDocument(self)
        self.exchange_pdf_buffer: QBuffer | None = None
        self.exchange_pdf_view = QPdfView(container)
        self.exchange_pdf_view.setDocument(self.exchange_pdf_document)
        self.exchange_pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.exchange_pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(self.exchange_pdf_view, 1)
        return container

    def _build_hit_run_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        tabs = QTabWidget()

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        self.hit_run_enabled = QCheckBox("This is a hit-and-run investigation")
        self.hit_run_enabled.setToolTip(
            "Keeps tentative hit-and-run evidence and leads separate from confirmed people and vehicles."
        )
        self.hit_run_enabled.toggled.connect(self.schedule_autosave)
        overview_layout.addWidget(self.hit_run_enabled)
        form = QFormLayout()
        self.hit_run_status = QComboBox()
        self.hit_run_status.addItems(HIT_RUN_INVESTIGATION_STATUSES)
        self.hit_run_last_known_location = QLineEdit()
        self.hit_run_last_seen_date = _date_line()
        self.hit_run_last_seen_time = QLineEdit()
        self.hit_run_last_seen_time.setPlaceholderText("HH:MM")
        self.hit_run_direction = QLineEdit()
        self.hit_run_initial_source = QLineEdit()
        for label, widget in (
            ("Investigation status", self.hit_run_status),
            ("Last known location", self.hit_run_last_known_location),
            ("Last seen date", self.hit_run_last_seen_date),
            ("Last seen time", self.hit_run_last_seen_time),
            ("Direction of travel", self.hit_run_direction),
            ("Initial information source", self.hit_run_initial_source),
        ):
            form.addRow(label, widget)
        overview_layout.addLayout(form)
        self.hit_run_narrative = SpellCheckedTextEdit()
        self.hit_run_narrative.setPlaceholderText(
            "Initial report, sequence, separation from the scene, and current investigative picture"
        )
        self.hit_run_follow_up = SpellCheckedTextEdit()
        self.hit_run_follow_up.setPlaceholderText(
            "Outstanding canvass, records, comparison, identification, and notification steps"
        )
        overview_layout.addWidget(QLabel("Hit-and-run narrative"))
        overview_layout.addWidget(self.hit_run_narrative, 1)
        overview_layout.addWidget(QLabel("Follow-up notes"))
        overview_layout.addWidget(self.hit_run_follow_up, 1)
        overview_layout.addStretch(1)
        for widget in (
            self.hit_run_last_known_location,
            self.hit_run_last_seen_date,
            self.hit_run_last_seen_time,
            self.hit_run_direction,
            self.hit_run_initial_source,
        ):
            widget.textChanged.connect(self.schedule_autosave)
        self.hit_run_status.currentTextChanged.connect(self.schedule_autosave)
        self.hit_run_narrative.textChanged.connect(self.schedule_autosave)
        self.hit_run_follow_up.textChanged.connect(self.schedule_autosave)
        tabs.addTab(_scrollable(overview), "Overview")

        evidence_tab, self.hit_run_evidence_table = self._table_tab(
            [
                "Evidence #",
                "Type",
                "Part #",
                "Description",
                "Recovered",
                "Vehicle Lead",
                "Lab Status",
                "Notes",
            ],
            self.add_hit_run_evidence,
            self.edit_hit_run_evidence,
            self.delete_hit_run_evidence,
        )
        self.hit_run_evidence_table.setColumnWidth(0, 95)
        self.hit_run_evidence_table.setColumnWidth(3, 240)
        self.hit_run_evidence_table.setColumnWidth(4, 180)
        tabs.addTab(evidence_tab, "Recovered Parts / Evidence")

        vehicle_tab, self.hit_run_vehicle_leads_table = self._table_tab(
            [
                "Lead",
                "Status",
                "Possible Vehicle",
                "Plate",
                "Damage / Missing Parts",
                "Last Seen",
                "Source / Confidence",
                "Linked Vehicle",
            ],
            self.add_hit_run_vehicle_lead,
            self.edit_hit_run_vehicle_lead,
            self.delete_hit_run_vehicle_lead,
        )
        promote_vehicle_row = QHBoxLayout()
        promote_vehicle_row.addWidget(
            _button(
                "Promote / Edit Linked Vehicle",
                self.promote_hit_run_vehicle_lead,
                secondary=True,
            )
        )
        promote_vehicle_row.addStretch(1)
        vehicle_tab.layout().insertLayout(1, promote_vehicle_row)
        self.hit_run_vehicle_leads_table.setColumnWidth(0, 80)
        self.hit_run_vehicle_leads_table.setColumnWidth(2, 230)
        self.hit_run_vehicle_leads_table.setColumnWidth(4, 250)
        self.hit_run_vehicle_leads_table.setColumnWidth(5, 190)
        tabs.addTab(vehicle_tab, "Possible Vehicle Leads")

        person_tab, self.hit_run_person_leads_table = self._table_tab(
            [
                "Lead",
                "Status",
                "Name / Alias",
                "Description",
                "Vehicle Lead",
                "Reason / Source",
                "Linked Person",
                "Follow-up",
            ],
            self.add_hit_run_person_lead,
            self.edit_hit_run_person_lead,
            self.delete_hit_run_person_lead,
        )
        promote_person_row = QHBoxLayout()
        promote_person_row.addWidget(
            _button(
                "Promote / Edit Linked Person",
                self.promote_hit_run_person_lead,
                secondary=True,
            )
        )
        promote_person_row.addStretch(1)
        person_tab.layout().insertLayout(1, promote_person_row)
        self.hit_run_person_leads_table.setColumnWidth(0, 80)
        self.hit_run_person_leads_table.setColumnWidth(2, 190)
        self.hit_run_person_leads_table.setColumnWidth(3, 210)
        self.hit_run_person_leads_table.setColumnWidth(5, 240)
        tabs.addTab(person_tab, "Person Leads / Possible Suspects")

        layout.addWidget(tabs, 1)
        return container

    def _build_chronology_tab(self):
        tab, self.chronology_table = self._table_tab(
            ["Date", "Time", "Category", "Summary", "Details"],
            self.add_chronology, self.edit_chronology, self.delete_chronology,
            item_name="Journal Entry",
        )
        tab.setObjectName("journal_tab")
        guidance = QLabel(
            "Use the Journal to document dated investigative actions, decisions, "
            "requests, findings, and follow-up. Double-click an entry to edit it."
        )
        guidance.setObjectName("journal_guidance")
        guidance.setWordWrap(True)
        tab.layout().insertWidget(0, guidance)
        self.chronology_table.setObjectName("journal_table")
        self.chronology_table.setColumnWidth(0, 100)
        self.chronology_table.setColumnWidth(1, 70)
        self.chronology_table.setColumnWidth(2, 120)
        self.chronology_table.setColumnWidth(3, 260)
        return tab

    def _build_tasks_tab(self):
        tab, self.tasks_table = self._table_tab(
            ["Status", "Category", "Task / Evidence", "Due", "Notes"],
            self.add_task, self.edit_task, self.delete_task,
        )
        self.tasks_table.setColumnWidth(0, 100)
        self.tasks_table.setColumnWidth(1, 140)
        self.tasks_table.setColumnWidth(2, 300)
        return tab

    def schedule_autosave(self, *_args) -> None:
        if not self.loading and self.current_case:
            self.overview_dirty = True
            self.autosave_timer.start()

    def _autosave_if_dirty(self) -> None:
        if self.overview_dirty and not self.loading and self.current_case:
            self.save_overview()

    def _connect_case_subtab_autosave(self) -> None:
        for tab_widget in self.findChildren(QTabWidget):
            if tab_widget is not self.tabs:
                tab_widget.currentChanged.connect(self._case_subtab_changed)

    def _case_subtab_changed(self, _index: int) -> None:
        if not self.loading and self.current_case:
            self.save_overview()

    def _packet_location_text(self) -> str:
        road_widget = self.packet_widgets.get("road_name")
        intersection_widget = self.packet_widgets.get("intersection_road")
        road_name = road_widget.text() if isinstance(road_widget, QLineEdit) else ""
        intersection_road = (
            intersection_widget.text() if isinstance(intersection_widget, QLineEdit) else ""
        )
        return format_crash_location(road_name, intersection_road)

    def _sync_location_preview(self, *_args) -> None:
        self.location.setText(self._packet_location_text())

    def _sync_axon_upload_availability(self, investigator_photos_checked: bool) -> None:
        self.axon_upload_checkbox.setEnabled(investigator_photos_checked)
        if not investigator_photos_checked:
            self.axon_upload_checkbox.setChecked(False)

    def _sync_checklist_date_availability(self, item: str, checked: bool) -> None:
        date_widget = self.checklist_date_widgets.get(item)
        if not date_widget:
            return
        date_widget.setEnabled(checked)
        if not checked and not self.loading:
            date_widget.clear()

    def save_overview(self) -> bool:
        if self.loading or not self.current_case:
            return True
        try:
            self._save_overview_records()
        except (OSError, sqlite3.Error) as error:
            self.autosave_timer.stop()
            self.overview_dirty = True
            if not self.storage_error_active:
                QMessageBox.critical(
                    self,
                    "Case data could not be saved",
                    "Traffic Crash Notebook cannot reach or write to its configured "
                    "case database. Reconnect the selected drive, then choose Save "
                    "again. The application did not switch to another database.\n\n"
                    f"{self.repository.database_path}\n\n{error}",
                )
            self.storage_error_active = True
            return False
        self.storage_error_active = False
        self.overview_dirty = False
        self.autosave_timer.stop()
        return True

    def _save_overview_records(self) -> None:
        if self.loading or not self.current_case:
            return
        case = self.current_case
        case.case_number = self.case_number.text().strip()
        case.crash_date = normalize_date_for_storage(self.crash_date.text())
        case.crash_time = normalize_time_for_storage(self.crash_time.text())
        case.investigator = self.investigator.text().strip()
        case.assigned_officer_dpsst = self.assigned_officer_dpsst.text().strip()
        case.assignment = self.assignment.text().strip()
        case.status = self.status.currentText()
        case.summary = self.summary.toPlainText().strip()
        case.notes = self.general_notes.toPlainText().strip()
        self.save_conditions()
        self.save_packet_case_data()
        self.save_hit_run_overview()
        case.location = self._packet_location_text()
        self.location.setText(case.location)
        self.repository.save_case(case)
        self._update_header()
        self._update_case_item(case)
        self.statusBar().showMessage("Saved", 1800)

    def save_hit_run_overview(self) -> None:
        if self.loading or not self.current_case or not self.hit_run_overview:
            return
        overview = self.hit_run_overview
        overview.is_hit_and_run = self.hit_run_enabled.isChecked()
        overview.investigation_status = self.hit_run_status.currentText()
        overview.last_known_location = self.hit_run_last_known_location.text().strip()
        overview.last_seen_date = normalize_date_for_storage(
            self.hit_run_last_seen_date.text()
        )
        overview.last_seen_time = self.hit_run_last_seen_time.text().strip()
        overview.direction_of_travel = self.hit_run_direction.text().strip()
        overview.initial_source = self.hit_run_initial_source.text().strip()
        overview.narrative = self.hit_run_narrative.toPlainText().strip()
        overview.follow_up_notes = self.hit_run_follow_up.toPlainText().strip()
        self.repository.save_hit_run_overview(overview)

    def save_conditions(self) -> None:
        if self.loading or not self.current_case or not self.conditions:
            return
        for name, widget in self.condition_widgets.items():
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, QTextEdit):
                value = widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            else:
                continue
            setattr(self.conditions, name, value)
        self.conditions.area_classifications = "; ".join(
            option for option, checkbox in self.area_type_boxes.items() if checkbox.isChecked()
        )
        self.repository.save_road_conditions(self.conditions)

    def save_packet_case_data(self) -> None:
        if (
            self.loading
            or not self.current_case
            or not self.checklist
            or not self.crash_details
        ):
            return
        self.checklist.completed_items = [
            item for item, checkbox in self.checklist_boxes.items() if checkbox.isChecked()
        ]
        for name, widget in self.checklist_widgets.items():
            setattr(self.checklist, name, widget.text().strip())
        for item, widget in self.checklist_date_widgets.items():
            setattr(
                self.checklist,
                CHECKLIST_DATE_FIELDS[item],
                normalize_date_for_storage(widget.text()),
            )
        self.repository.save_investigative_checklist(self.checklist)

        for name, widget in self.packet_widgets.items():
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            else:
                continue
            if name == "team_notified_date":
                value = normalize_date_for_storage(value)
            setattr(self.crash_details, name, value)
        self.crash_details.scene_evidence = [
            method for method, checkbox in self.scene_evidence_boxes.items() if checkbox.isChecked()
        ]
        self.repository.save_crash_details(self.crash_details)

    def refresh_cases(self, *_args, select_first: bool = False) -> None:
        selected_id = self.current_case.id if self.current_case else None
        query = self.case_search.text().strip().lower() if hasattr(self, "case_search") else ""
        self.case_list.blockSignals(True)
        self.case_list.clear()
        selected_item = None
        for case in self.repository.list_cases():
            display_date = format_date_for_display(case.crash_date)
            haystack = (
                f"{case.case_number} {case.location} {case.crash_date} {display_date}"
            ).lower()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(self._case_item_text(case))
            item.setData(Qt.ItemDataRole.UserRole, case.id)
            self.case_list.addItem(item)
            if case.id == selected_id:
                selected_item = item
        self.case_list.blockSignals(False)
        if selected_item:
            self.case_list.setCurrentItem(selected_item)
        elif select_first and self.case_list.count():
            self.case_list.setCurrentRow(0)

    def _case_item_text(self, case: CrashCase) -> str:
        title = case.case_number or "Untitled Case"
        detail = format_date_for_display(case.crash_date) or case.location or "No crash date"
        return f"{title}\n{detail}  -  {case.status}"

    def _update_case_item(self, case: CrashCase) -> None:
        for index in range(self.case_list.count()):
            item = self.case_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == case.id:
                item.setText(self._case_item_text(case))
                break

    def _case_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if not current:
            return
        if self.current_case:
            self.save_overview()
        case = self.repository.get_case(current.data(Qt.ItemDataRole.UserRole))
        if case:
            self.load_case(case)

    def load_case(self, case: CrashCase) -> None:
        self.autosave_timer.stop()
        self.overview_dirty = False
        if not self.current_case or self.current_case.id != case.id:
            self._invalidate_exchange_preview(
                f"Exchange preview not yet generated for "
                f"{case.case_number or 'this case'}."
            )
        self.loading = True
        self.current_case = case
        self.case_number.setText(case.case_number)
        self.crash_date.setText(format_date_for_display(case.crash_date))
        self.crash_time.setText(format_time_for_display(case.crash_time))
        self.investigator.setText(case.investigator)
        self.assigned_officer_dpsst.setText(case.assigned_officer_dpsst)
        self.assignment.setText(case.assignment)
        index = self.status.findText(case.status)
        self.status.setCurrentIndex(max(0, index))
        self.summary.setPlainText(case.summary)
        self.general_notes.setPlainText(case.notes)
        self.checklist = self.repository.get_investigative_checklist(case.id)
        for name, widget in self.checklist_widgets.items():
            widget.setText(getattr(self.checklist, name))
        for item, widget in self.checklist_date_widgets.items():
            widget.setText(format_date_for_display(
                getattr(self.checklist, CHECKLIST_DATE_FIELDS[item])
            ))
        completed_items = set(self.checklist.completed_items)
        for item, checkbox in self.checklist_boxes.items():
            date_attribute = CHECKLIST_DATE_FIELDS.get(item)
            has_date = bool(
                date_attribute and getattr(self.checklist, date_attribute)
            )
            checkbox.setChecked(item in completed_items or has_date)
            if date_attribute:
                self._sync_checklist_date_availability(
                    item,
                    checkbox.isChecked(),
                )

        self.crash_details = self.repository.get_crash_details(case.id)
        if not format_crash_location(
            self.crash_details.road_name,
            self.crash_details.intersection_road,
        ) and case.location.strip():
            road_name, separator, intersection_road = case.location.partition(" / ")
            self.crash_details.road_name = road_name.strip()
            if separator:
                self.crash_details.intersection_road = intersection_road.strip()
        for name, widget in self.packet_widgets.items():
            value = getattr(self.crash_details, name)
            if isinstance(widget, QLineEdit):
                widget.setText(
                    format_date_for_display(value)
                    if name == "team_notified_date"
                    else value
                )
            elif isinstance(widget, QComboBox):
                index = widget.findText(value)
                widget.setCurrentIndex(max(0, index))
        self._sync_location_preview()
        scene_evidence = set(normalize_scene_evidence_methods(
            self.crash_details.scene_evidence
        ))
        for method, checkbox in self.scene_evidence_boxes.items():
            checkbox.setChecked(method in scene_evidence)
        self._sync_axon_upload_availability(
            self.investigator_photos_checkbox.isChecked()
        )
        self.conditions = self.repository.get_road_conditions(case.id)
        for name, widget in self.condition_widgets.items():
            value = getattr(self.conditions, name)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            elif isinstance(widget, QComboBox):
                index = widget.findText(value)
                widget.setCurrentIndex(max(0, index))
        area_classifications = {
            value.strip()
            for value in self.conditions.area_classifications.replace("\n", ";").split(";")
            if value.strip()
        }
        for option, checkbox in self.area_type_boxes.items():
            checkbox.setChecked(option in area_classifications)
        self.hit_run_overview = self.repository.get_hit_run_overview(case.id)
        self.hit_run_enabled.setChecked(self.hit_run_overview.is_hit_and_run)
        hit_run_status_index = self.hit_run_status.findText(
            self.hit_run_overview.investigation_status
        )
        self.hit_run_status.setCurrentIndex(max(0, hit_run_status_index))
        self.hit_run_last_known_location.setText(
            self.hit_run_overview.last_known_location
        )
        self.hit_run_last_seen_date.setText(
            format_date_for_display(self.hit_run_overview.last_seen_date)
        )
        self.hit_run_last_seen_time.setText(self.hit_run_overview.last_seen_time)
        self.hit_run_direction.setText(self.hit_run_overview.direction_of_travel)
        self.hit_run_initial_source.setText(self.hit_run_overview.initial_source)
        self.hit_run_narrative.setPlainText(self.hit_run_overview.narrative)
        self.hit_run_follow_up.setPlainText(self.hit_run_overview.follow_up_notes)
        self.loading = False
        self.overview_dirty = False
        self.refresh_case_tables()
        self._update_header()

    def _update_header(self) -> None:
        if not self.current_case:
            return
        case = self.current_case
        self.case_title.setText(case.case_number or "Untitled Case")
        details = "  |  ".join(value for value in (
            format_date_for_display(case.crash_date),
            case.location,
            case.status,
        ) if value)
        self.case_subtitle.setText(details or "Personal investigative working notes")
        counts = self.repository.case_counts(case.id)
        journal_count_label = (
            "journal entry" if counts["chronology"] == 1 else "journal entries"
        )
        self.counts_label.setText(
            f"{counts['people']} people   {counts['vehicles']} vehicles   "
            f"{counts['chronology']} {journal_count_label}   "
            f"{counts['open_tasks']} open tasks"
        )

    def refresh_case_tables(self) -> None:
        self.refresh_charge_dispositions()
        self.refresh_video_sources()
        self.refresh_surface_observations()
        self.refresh_roadways()
        self.refresh_people()
        self.refresh_vehicles()
        self.refresh_case_packet_preview()
        self.refresh_exchange_report()
        self.refresh_hit_run_evidence()
        self.refresh_hit_run_vehicle_leads()
        self.refresh_hit_run_person_leads()
        self.refresh_contacts()
        self.refresh_vru_analyses()
        self.refresh_chronology()
        self.refresh_tasks()
        self._update_header()

    def new_case(self) -> None:
        case_number, accepted = QInputDialog.getText(self, "New Case", "Case number (may be left blank)")
        if not accepted:
            return
        self.save_overview()
        defaults = self.repository.get_user_defaults()
        case = self.repository.create_case(
            case_number.strip(),
            defaults.user_name,
            defaults.dpsst,
            defaults.assignment,
        )
        self.refresh_cases()
        for index in range(self.case_list.count()):
            item = self.case_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == case.id:
                self.case_list.setCurrentItem(item)
                break

    def _selected_id(self, table: QTableWidget) -> str | None:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _populate_table(self, table: QTableWidget, rows: list[tuple[str, list[str]]]) -> None:
        table.setRowCount(0)
        for record_id, values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value or "")
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record_id)
                item.setToolTip(value or "")
                table.setItem(row, column, item)
        table.resizeRowsToContents()

    def refresh_charge_dispositions(self) -> None:
        if not self.current_case:
            return
        self._populate_table(
            self.charges_table,
            [
                (record.id, [record.charge, record.disposition])
                for record in self.repository.list_charge_dispositions(self.current_case.id)
            ],
        )

    def add_charge_disposition(self) -> None:
        if not self.current_case:
            return
        dialog = ChargeDispositionDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_charge_disposition(dialog.result_record())
            self.refresh_charge_dispositions()

    def edit_charge_disposition(self, *_args) -> None:
        record_id = self._selected_id(self.charges_table)
        if not record_id:
            return
        record = self.repository.get_charge_disposition(record_id)
        if not record:
            return
        dialog = ChargeDispositionDialog(record.case_id, record, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_charge_disposition(dialog.result_record())
            self.refresh_charge_dispositions()

    def delete_charge_disposition(self) -> None:
        record_id = self._selected_id(self.charges_table)
        if record_id and self._confirm_remove("Remove this charge and disposition?"):
            self.repository.delete_charge_disposition(record_id)
            self.refresh_charge_dispositions()

    def refresh_video_sources(self) -> None:
        if not self.current_case:
            self.surveillance_video_indicator.setChecked(False)
            return
        records = self.repository.list_video_sources(self.current_case.id)
        self._populate_table(
            self.video_sources_table,
            [
                (
                    record.id,
                    [record.source, record.address, record.axon_status, record.notes],
                )
                for record in records
            ],
        )
        self.surveillance_video_indicator.setChecked(bool(records))

    def add_video_source(self) -> None:
        if not self.current_case:
            return
        dialog = VideoSourceDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_video_source(dialog.result_record())
            self.refresh_video_sources()

    def edit_video_source(self, *_args) -> None:
        record_id = self._selected_id(self.video_sources_table)
        if not record_id:
            return
        record = self.repository.get_video_source(record_id)
        if not record:
            return
        dialog = VideoSourceDialog(record.case_id, record, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_video_source(dialog.result_record())
            self.refresh_video_sources()

    def delete_video_source(self) -> None:
        record_id = self._selected_id(self.video_sources_table)
        if record_id and self._confirm_remove("Remove this video source?"):
            self.repository.delete_video_source(record_id)
            self.refresh_video_sources()

    def refresh_surface_observations(self) -> None:
        if not self.current_case:
            return
        self._populate_table(
            self.surface_observations_table,
            [
                (
                    record.id,
                    [
                        record.location,
                        record.composition,
                        record.condition,
                        record.friction_value,
                        record.notes,
                    ],
                )
                for record in self.repository.list_surface_observations(self.current_case.id)
            ],
        )

    def add_surface_observation(self) -> None:
        if not self.current_case:
            return
        dialog = SurfaceObservationDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_surface_observation(dialog.result_record())
            self.refresh_surface_observations()

    def edit_surface_observation(self, *_args) -> None:
        record_id = self._selected_id(self.surface_observations_table)
        if not record_id:
            return
        record = self.repository.get_surface_observation(record_id)
        if not record:
            return
        dialog = SurfaceObservationDialog(record.case_id, record, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_surface_observation(dialog.result_record())
            self.refresh_surface_observations()

    def delete_surface_observation(self) -> None:
        record_id = self._selected_id(self.surface_observations_table)
        if record_id and self._confirm_remove("Remove this surface observation?"):
            self.repository.delete_surface_observation(record_id)
            self.refresh_surface_observations()

    def refresh_roadways(self) -> None:
        if not self.current_case:
            return
        rows: list[tuple[str, list[str]]] = []
        for record in self.repository.list_roadway_records(self.current_case.id):
            curve_details = "; ".join(
                value
                for value in (
                    f"R {record.curve_radius}" if record.curve_radius else "",
                    f"C {record.chord}" if record.chord else "",
                    f"MO {record.middle_ordinate}" if record.middle_ordinate else "",
                    f"Speed {record.critical_speed}"
                    if record.critical_speed
                    else "",
                )
                if value
            )
            narrative = " | ".join(
                value
                for value in (
                    f"Characteristics: {record.roadway_characteristics}"
                    if record.roadway_characteristics
                    else "",
                    f"Controls: {record.traffic_controls}"
                    if record.traffic_controls
                    else "",
                )
                if value
            )
            rows.append((
                record.id,
                [
                    record.roadway_tag,
                    f"{record.speed_limit} mph" if record.speed_limit else "",
                    record.speed_limit_posted,
                    record.speed_limit_location,
                    curve_details,
                    narrative,
                ],
            ))
        self._populate_table(self.roadways_table, rows)

    def add_roadway(self) -> None:
        if not self.current_case:
            return
        dialog = RoadwayDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_roadway_record(dialog.result_record())
            self.refresh_roadways()

    def edit_roadway(self, *_args) -> None:
        record_id = self._selected_id(self.roadways_table)
        if not record_id:
            return
        record = self.repository.get_roadway_record(record_id)
        if not record:
            return
        dialog = RoadwayDialog(record.case_id, record, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_roadway_record(dialog.result_record())
            self.refresh_roadways()

    def delete_roadway(self) -> None:
        record_id = self._selected_id(self.roadways_table)
        if record_id and self._confirm_remove("Remove this roadway record?"):
            self.repository.delete_roadway_record(record_id)
            self.refresh_roadways()

    def refresh_people(self) -> None:
        if not self.current_case:
            return
        people = self.repository.list_people(self.current_case.id)
        self._populate_table(self.people_table, [
            (p.id, [
                p.display_name,
                ", ".join(p.roles),
                format_date_for_display(p.dob),
                p.cell_phone,
                p.notes,
            ])
            for p in people
        ])

    def add_person(self) -> None:
        if not self.current_case:
            return
        dialog = PersonDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_person(dialog.result_record())
            self.refresh_case_tables()

    def edit_person(self, *_args) -> None:
        person_id = self._selected_id(self.people_table)
        if not person_id:
            return
        person = self.repository.get_person(person_id)
        if not person:
            return
        dialog = PersonDialog(person.case_id, person, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_person(dialog.result_record())
            self.refresh_case_tables()

    def delete_person(self) -> None:
        person_id = self._selected_id(self.people_table)
        if person_id and self._confirm_remove("Remove this person from the case?"):
            self.repository.delete_person(person_id)
            self.refresh_case_tables()

    def edit_participant_details(self) -> None:
        person_id = self._selected_id(self.people_table)
        if not person_id or not self.current_case:
            return
        person = self.repository.get_person(person_id)
        if not person:
            return
        details = self.repository.get_participant_details(person_id)
        vehicles = self.repository.list_vehicles(self.current_case.id)
        dialog = ParticipantDetailsDialog(person, vehicles, details, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_participant_details(dialog.result_record())
            self.statusBar().showMessage("Participant details saved", 2200)

    def edit_driver_profile(self) -> None:
        person_id = self._selected_id(self.people_table)
        if not person_id:
            return
        person = self.repository.get_person(person_id)
        if not person:
            return
        profile = self.repository.get_driver_profile(person_id)
        dialog = DriverProfileDialog(person, profile, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_driver_profile(dialog.result_record())
            self.statusBar().showMessage("Driver background saved", 2200)

    def edit_witness_details(self) -> None:
        person_id = self._selected_id(self.people_table)
        if not person_id:
            return
        person = self.repository.get_person(person_id)
        if not person:
            return
        details = self.repository.get_witness_details(person_id)
        dialog = WitnessDetailsDialog(person, details, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_witness_details(dialog.result_record())
            if "Witness" not in person.roles:
                person.roles.append("Witness")
                self.repository.save_person(person)
            self.refresh_people()
            self.statusBar().showMessage("Witness interview saved", 2200)

    def refresh_vehicles(self) -> None:
        if not self.current_case:
            return
        people = {p.id: p for p in self.repository.list_people(self.current_case.id)}
        rows = []
        for v in self.repository.list_vehicles(self.current_case.id):
            driver = people[v.driver_person_id].display_name if v.driver_person_id in people else ""
            plate = " ".join(part for part in (v.plate_state, v.plate) if part)
            notes = " - ".join(part for part in (
                (
                    f"Other property: {v.property_damage}"
                    if v.property_damage else ""
                ),
                v.damage_notes,
                v.notes,
            ) if part)
            workflow = ", ".join(
                label
                for attribute, label in VEHICLE_WORKFLOW_FIELDS
                if getattr(v, attribute)
            )
            insurance = "\n".join(value for value in (
                " / ".join(value for value in (
                    v.insurance_company or v.insurance,
                    v.insurance_policy_number,
                ) if value),
                (
                    f"Claim: {v.insurance_claim_number}"
                    if v.insurance_claim_number else ""
                ),
                (
                    f"Adjuster: {v.insurance_adjuster_name}"
                    if v.insurance_adjuster_name else ""
                ),
                (
                    f"Adjuster phone: {v.insurance_adjuster_phone}"
                    if v.insurance_adjuster_phone else ""
                ),
                (
                    f"Adjuster email: {v.insurance_adjuster_email}"
                    if v.insurance_adjuster_email else ""
                ),
            ) if value)
            release = " - ".join(value for value in (
                "Released" if v.released else "",
                format_date_for_display(v.release_date),
                v.release_information,
            ) if value)
            towing = "No"
            if v.towed:
                towing = " - ".join(value for value in (
                    "Yes",
                    v.tow_information,
                ) if value)
            if v.edr_status:
                notes = " - ".join(value for value in (
                    notes,
                    f"CDR / EDR: {v.edr_status}",
                ) if value)
            rows.append((v.id, [
                v.vehicle_number,
                v.description,
                driver,
                plate,
                workflow,
                towing,
                release,
                insurance,
                notes,
            ]))
        self._populate_table(self.vehicles_table, rows)

    def add_vehicle(self) -> None:
        if not self.current_case:
            return
        people = self.repository.list_people(self.current_case.id)
        vehicle: Vehicle | None = None
        while True:
            dialog = VehicleDialog(
                self.current_case.id,
                people,
                vehicle,
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            vehicle = dialog.result_record()
            if self._save_vehicle_record(vehicle):
                return

    def edit_vehicle(self, *_args) -> None:
        vehicle_id = self._selected_id(self.vehicles_table)
        if not vehicle_id or not self.current_case:
            return
        vehicle = self.repository.get_vehicle(vehicle_id)
        if not vehicle:
            return
        people = self.repository.list_people(vehicle.case_id)
        while True:
            dialog = VehicleDialog(vehicle.case_id, people, vehicle, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            vehicle = dialog.result_record()
            if self._save_vehicle_record(vehicle):
                return

    def _save_vehicle_record(self, vehicle: Vehicle) -> bool:
        try:
            saved = self.repository.save_vehicle(vehicle)
            persisted = self.repository.get_vehicle(saved.id)
            if persisted is None:
                raise RuntimeError(
                    "The database did not return the vehicle after saving it."
                )
        except (OSError, sqlite3.Error, RuntimeError) as error:
            QMessageBox.critical(
                self,
                "Vehicle could not be saved",
                "The vehicle was not confirmed in the case database. Your entries "
                "will remain in the vehicle window so you can reconnect the data "
                "drive and choose Save again.\n\n"
                f"Database: {self.repository.database_path}\n\n{error}",
            )
            return False
        self.refresh_case_tables()
        self.statusBar().showMessage(
            f"Vehicle {persisted.vehicle_number or persisted.description} saved and verified.",
            5000,
        )
        return True

    def delete_vehicle(self) -> None:
        vehicle_id = self._selected_id(self.vehicles_table)
        if vehicle_id and self._confirm_remove("Remove this vehicle from the case?"):
            self.repository.delete_vehicle(vehicle_id)
            self.refresh_case_tables()

    def _case_tab_changed(self, index: int) -> None:
        if self.loading:
            return
        if self.current_case and not self.save_overview():
            return
        if index == self.exchange_report_tab_index:
            self.refresh_exchange_report(force_preview=True)

    def _packet_preview_details(self):
        if self.packet_preview_mode.currentData() == "compact":
            return (
                "Compact Packet",
                "Compact_Packet",
                export_case_compact_pdf,
            )
        return (
            "Full Working Packet",
            "Full_Working_Packet",
            export_case_pdf,
        )

    def show_packet_preview(self) -> None:
        if not self.current_case:
            QMessageBox.information(
                self,
                "Case Packet Preview",
                "Select or create a case before opening the packet preview.",
            )
            return
        if not self.save_overview():
            return
        self.packet_preview_dialog.show()
        self.packet_preview_dialog.raise_()
        self.packet_preview_dialog.activateWindow()
        self.refresh_case_packet_preview(force_preview=True)

    def preview_case_packet(self, *_args) -> None:
        if not self.current_case or not self.save_overview():
            return
        self.refresh_case_packet_preview(force_preview=True)

    def refresh_case_packet_preview(
        self,
        *_args,
        force_preview: bool = False,
    ) -> None:
        if not self.current_case:
            return
        preview_is_visible = (
            hasattr(self, "packet_preview_dialog")
            and self.packet_preview_dialog.isVisible()
        )
        if not force_preview and not preview_is_visible:
            return
        self._generate_case_packet_preview()

    def _generate_case_packet_preview(self) -> None:
        if not self.current_case:
            return
        packet_label, packet_suffix, exporter = self._packet_preview_details()
        self.packet_preview_generation += 1
        next_preview_path = Path(
            self.packet_preview_directory.path()
        ) / (
            f"Traffic_Crash_{packet_suffix}_Preview_"
            f"{self.packet_preview_generation:06d}.pdf"
        )
        next_document = QPdfDocument(self)
        next_buffer = QBuffer(next_document)
        try:
            exporter(
                self.repository,
                self.current_case.id,
                next_preview_path,
            )
            next_buffer.setData(QByteArray(next_preview_path.read_bytes()))
            if not next_buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                raise RuntimeError("The preview PDF could not be opened in memory.")
            next_document.load(next_buffer)
            load_error = next_document.error()
            if load_error != QPdfDocument.Error.None_:
                raise RuntimeError(
                    f"The preview PDF could not be loaded ({load_error.name})."
                )
            if next_document.pageCount() < 1:
                raise RuntimeError("The preview PDF did not contain any pages.")
        except Exception as error:
            next_buffer.close()
            next_document.close()
            next_document.deleteLater()
            self.packet_stale_preview_paths.add(next_preview_path)
            QTimer.singleShot(250, self._cleanup_stale_packet_previews)
            self.packet_preview_status.setText(f"Preview failed: {error}")
            self.packet_preview_status.setStyleSheet("color: #a32a2a;")
            return

        previous_document = self.packet_pdf_document
        previous_preview_path = self.packet_preview_path
        self.packet_pdf_view.setDocument(next_document)
        self.packet_pdf_document = next_document
        self.packet_pdf_buffer = next_buffer
        self.packet_preview_path = next_preview_path
        previous_document.close()
        previous_document.deleteLater()
        if previous_preview_path.is_file():
            self.packet_stale_preview_paths.add(previous_preview_path)
            QTimer.singleShot(250, self._cleanup_stale_packet_previews)
        self.packet_preview_status.setText(
            f"Preview ready - {packet_label}, "
            f"{self.packet_pdf_document.pageCount()} page(s)."
        )
        self.packet_preview_status.setStyleSheet("color: #2f6f3e;")

    def _cleanup_stale_packet_previews(self) -> None:
        for preview_path in tuple(self.packet_stale_preview_paths):
            if preview_path == self.packet_preview_path:
                continue
            try:
                preview_path.unlink(missing_ok=True)
            except OSError:
                # Windows may keep a page-render handle alive briefly after the
                # viewer switches documents. A later refresh or timer will retry.
                continue
            self.packet_stale_preview_paths.discard(preview_path)

    def preview_exchange_report(self, *_args) -> None:
        if not self.current_case or not self.save_overview():
            return
        self.refresh_exchange_report(force_preview=True)

    def refresh_exchange_report(
        self,
        *_args,
        force_preview: bool = False,
    ) -> None:
        if not self.current_case:
            return
        case_id = self.current_case.id
        people_list = self.repository.list_people(case_id)
        vehicles = self.repository.list_vehicles(case_id)
        participants = {
            person.id: self.repository.get_participant_details(person.id)
            for person in people_list
        }
        vehicle_drivers = resolve_exchange_vehicle_drivers(
            vehicles,
            people_list,
            participants,
        )
        exchange_people = exchange_report_people(
            people_list,
            vehicles,
            participants,
        )
        complete_vehicles = 0
        for vehicle in vehicles:
            party = vehicle_drivers.get(vehicle.id)
            profile = self.repository.get_driver_profile(party.id) if party else None
            required_values = (
                party,
                person_exchange_address(party),
                person_exchange_phone(party),
                profile.license_number if profile else "",
                profile.license_state if profile else "",
                vehicle.insurance_company or vehicle.insurance,
                vehicle.insurance_policy_number,
                vehicle.plate,
                vehicle.plate_state,
                vehicle.year,
                vehicle.make,
                vehicle.model,
                vehicle.body_style,
                vehicle.color,
                vehicle.property_damage,
            )
            if all(required_values):
                complete_vehicles += 1

        complete_people = 0
        for person in exchange_people:
            participant = participants[person.id]
            has_required_data = bool(
                person_exchange_address(person) and person_exchange_phone(person)
            )
            if "Passenger" in person.roles and not participant.vehicle_id:
                has_required_data = False
            if has_required_data:
                complete_people += 1

        page_plan = exchange_report_page_plan(vehicles, exchange_people)
        passenger_count = sum("Passenger" in person.roles for person in exchange_people)
        witness_count = sum("Witness" in person.roles for person in exchange_people)
        pedestrian_count = sum("Pedestrian" in person.roles for person in exchange_people)
        bicyclist_count = sum("Bicyclist" in person.roles for person in exchange_people)
        officer_missing = []
        if not self.current_case.investigator:
            officer_missing.append("assigned officer")
        if not self.current_case.assigned_officer_dpsst:
            officer_missing.append("DPSST")
        if not self.current_case.assignment:
            officer_missing.append("assignment / precinct")
        missing_message = (
            f" Missing officer fields: {', '.join(officer_missing)}."
            if officer_missing else ""
        )
        self.exchange_readiness_label.setText(
            f"Preview content: {len(vehicles)} vehicle(s), {len(exchange_people)} additional "
            f"person(s) ({passenger_count} passenger, {witness_count} witness, "
            f"{pedestrian_count} pedestrian, {bicyclist_count} bicyclist). "
            f"Complete records: {complete_vehicles} vehicle block(s) and "
            f"{complete_people} person block(s). The PDF has {len(page_plan)} dynamic "
            f"front page(s) plus the required information page; unused record blocks "
            f"are not printed.{missing_message}"
        )

        preview_is_visible = (
            hasattr(self, "tabs")
            and self.tabs.currentIndex() == self.exchange_report_tab_index
        )
        if not force_preview and not preview_is_visible:
            return
        self._generate_exchange_preview()

    def _invalidate_exchange_preview(self, message: str) -> None:
        self.exchange_preview_case_id = None
        if hasattr(self, "exchange_pdf_view"):
            self.exchange_pdf_view.hide()
        if hasattr(self, "exchange_preview_status"):
            self.exchange_preview_status.setText(message)
            self.exchange_preview_status.setStyleSheet("color: #5d6870;")

    def _exchange_preview_is_current(self) -> bool:
        return bool(
            self.current_case
            and self.exchange_preview_case_id == self.current_case.id
            and self.exchange_preview_path.is_file()
            and self.exchange_pdf_document.pageCount() > 0
            and not self.exchange_preview_status.text().startswith("Preview failed")
        )

    def _generate_exchange_preview(self) -> None:
        if not self.current_case:
            return
        case_id = self.current_case.id
        case_label = self.current_case.case_number or "Untitled Case"
        self._invalidate_exchange_preview(
            f"Generating exchange preview for {case_label}..."
        )
        self.exchange_preview_generation += 1
        next_preview_path = Path(
            self.exchange_preview_directory.path()
        ) / (
            "Traffic_Crash_Exchange_Report_Preview_"
            f"{self.exchange_preview_generation:06d}.pdf"
        )
        next_document = QPdfDocument(self)
        next_buffer = QBuffer(next_document)
        try:
            export_exchange_report_pdf(
                self.repository,
                case_id,
                next_preview_path,
            )
            next_buffer.setData(QByteArray(next_preview_path.read_bytes()))
            if not next_buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                raise RuntimeError("The preview PDF could not be opened in memory.")
            next_document.load(next_buffer)
            load_error = next_document.error()
            if load_error != QPdfDocument.Error.None_:
                raise RuntimeError(
                    f"The preview PDF could not be loaded ({load_error.name})."
                )
            if next_document.pageCount() < 1:
                raise RuntimeError("The preview PDF did not contain any pages.")
            if not self.current_case or self.current_case.id != case_id:
                raise RuntimeError(
                    "The selected case changed while the preview was being generated."
                )
        except Exception as error:
            next_buffer.close()
            next_document.close()
            next_document.deleteLater()
            self.exchange_stale_preview_paths.add(next_preview_path)
            QTimer.singleShot(250, self._cleanup_stale_exchange_previews)
            self.exchange_preview_status.setText(
                f"Preview failed for {case_label}: {error}"
            )
            self.exchange_preview_status.setStyleSheet("color: #a32a2a;")
            return

        previous_document = self.exchange_pdf_document
        previous_preview_path = self.exchange_preview_path
        self.exchange_pdf_view.setDocument(next_document)
        self.exchange_pdf_document = next_document
        self.exchange_pdf_buffer = next_buffer
        self.exchange_preview_path = next_preview_path
        self.exchange_preview_case_id = case_id
        self.exchange_pdf_view.show()
        previous_document.close()
        previous_document.deleteLater()
        if previous_preview_path.is_file():
            self.exchange_stale_preview_paths.add(previous_preview_path)
            QTimer.singleShot(250, self._cleanup_stale_exchange_previews)
        self.exchange_preview_status.setText(
            f"Preview ready - {self.exchange_pdf_document.pageCount()} page(s), "
            "including the information / responsibilities page. "
            f"Case: {case_label}."
        )
        self.exchange_preview_status.setStyleSheet("color: #2f6f3e;")

    def _cleanup_stale_exchange_previews(self) -> None:
        for preview_path in tuple(self.exchange_stale_preview_paths):
            if preview_path == self.exchange_preview_path:
                continue
            try:
                preview_path.unlink(missing_ok=True)
            except OSError:
                # Windows may keep a page-render handle alive briefly after the
                # viewer switches documents. A later refresh or timer will retry.
                continue
            self.exchange_stale_preview_paths.discard(preview_path)

    @staticmethod
    def _next_number(prefix: str, existing_values: list[str]) -> str:
        highest = 0
        normalized_prefix = f"{prefix.upper()}-"
        for value in existing_values:
            normalized = value.strip().upper()
            if not normalized.startswith(normalized_prefix):
                continue
            try:
                highest = max(highest, int(normalized[len(normalized_prefix):]))
            except ValueError:
                continue
        return f"{prefix}-{highest + 1}"

    def _mark_hit_run_active(self) -> None:
        if not self.current_case:
            return
        if self.hit_run_overview is None:
            self.hit_run_overview = HitRunOverview(case_id=self.current_case.id)
        self.hit_run_enabled.setChecked(True)
        self.save_hit_run_overview()

    def refresh_hit_run_evidence(self) -> None:
        if not self.current_case:
            return
        vehicle_leads = {
            lead.id: lead
            for lead in self.repository.list_hit_run_vehicle_leads(self.current_case.id)
        }
        rows = []
        for record in self.repository.list_hit_run_evidence_items(self.current_case.id):
            recovered = " | ".join(
                value for value in (
                    format_date_for_display(record.recovery_date),
                    record.recovery_time,
                    record.recovery_location,
                ) if value
            )
            lead = vehicle_leads.get(record.vehicle_lead_id)
            lead_label = lead.lead_number if lead else ""
            rows.append((record.id, [
                record.evidence_number,
                record.evidence_type,
                record.part_number,
                record.part_description,
                recovered,
                lead_label,
                record.lab_status,
                record.notes,
            ]))
        self._populate_table(self.hit_run_evidence_table, rows)

    def add_hit_run_evidence(self) -> None:
        if not self.current_case:
            return
        records = self.repository.list_hit_run_evidence_items(self.current_case.id)
        record = HitRunEvidenceItem(
            id="",
            case_id=self.current_case.id,
            evidence_number=self._next_number(
                "HRE",
                [item.evidence_number for item in records],
            ),
        )
        dialog = HitRunEvidenceDialog(
            self.current_case.id,
            self.repository.list_hit_run_vehicle_leads(self.current_case.id),
            record,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_hit_run_evidence_item(dialog.result_record())
            self._mark_hit_run_active()
            self.refresh_hit_run_evidence()

    def edit_hit_run_evidence(self, *_args) -> None:
        record_id = self._selected_id(self.hit_run_evidence_table)
        if not record_id or not self.current_case:
            return
        record = self.repository.get_hit_run_evidence_item(record_id)
        if not record:
            return
        dialog = HitRunEvidenceDialog(
            record.case_id,
            self.repository.list_hit_run_vehicle_leads(record.case_id),
            record,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_hit_run_evidence_item(dialog.result_record())
            self._mark_hit_run_active()
            self.refresh_hit_run_evidence()

    def delete_hit_run_evidence(self) -> None:
        record_id = self._selected_id(self.hit_run_evidence_table)
        if record_id and self._confirm_remove("Remove this recovered part / evidence item?"):
            self.repository.delete_hit_run_evidence_item(record_id)
            self.refresh_hit_run_evidence()

    def refresh_hit_run_vehicle_leads(self) -> None:
        if not self.current_case:
            return
        vehicles = {
            vehicle.id: vehicle
            for vehicle in self.repository.list_vehicles(self.current_case.id)
        }
        rows = []
        for lead in self.repository.list_hit_run_vehicle_leads(self.current_case.id):
            plate = " ".join(value for value in (lead.plate_state, lead.plate) if value)
            damage = " | ".join(
                value for value in (lead.observed_damage, lead.missing_parts) if value
            )
            last_seen = " | ".join(
                value for value in (
                    format_date_for_display(lead.last_seen_date),
                    lead.last_seen_time,
                    lead.last_seen_location,
                    lead.direction_of_travel,
                ) if value
            )
            source = " | ".join(
                value for value in (lead.information_source, lead.confidence) if value
            )
            linked = vehicles.get(lead.linked_vehicle_id)
            linked_label = (
                f"{linked.vehicle_number} - {linked.description}" if linked else ""
            )
            rows.append((lead.id, [
                lead.lead_number,
                lead.status,
                lead.description,
                plate,
                damage,
                last_seen,
                source,
                linked_label,
            ]))
        self._populate_table(self.hit_run_vehicle_leads_table, rows)

    def add_hit_run_vehicle_lead(self) -> None:
        if not self.current_case:
            return
        records = self.repository.list_hit_run_vehicle_leads(self.current_case.id)
        record = HitRunVehicleLead(
            id="",
            case_id=self.current_case.id,
            lead_number=self._next_number(
                "HRV",
                [lead.lead_number for lead in records],
            ),
        )
        dialog = HitRunVehicleLeadDialog(
            self.current_case.id,
            self.repository.list_vehicles(self.current_case.id),
            record,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_hit_run_vehicle_lead(dialog.result_record())
            self._mark_hit_run_active()
            self.refresh_case_tables()

    def edit_hit_run_vehicle_lead(self, *_args) -> None:
        record_id = self._selected_id(self.hit_run_vehicle_leads_table)
        if not record_id or not self.current_case:
            return
        record = self.repository.get_hit_run_vehicle_lead(record_id)
        if not record:
            return
        dialog = HitRunVehicleLeadDialog(
            record.case_id,
            self.repository.list_vehicles(record.case_id),
            record,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_hit_run_vehicle_lead(dialog.result_record())
            self._mark_hit_run_active()
            self.refresh_case_tables()

    def delete_hit_run_vehicle_lead(self) -> None:
        record_id = self._selected_id(self.hit_run_vehicle_leads_table)
        if record_id and self._confirm_remove(
            "Remove this possible vehicle lead? Associated evidence and person leads will remain but become unlinked."
        ):
            self.repository.delete_hit_run_vehicle_lead(record_id)
            self.refresh_case_tables()

    def promote_hit_run_vehicle_lead(self) -> None:
        record_id = self._selected_id(self.hit_run_vehicle_leads_table)
        if not record_id or not self.current_case:
            return
        lead = self.repository.get_hit_run_vehicle_lead(record_id)
        if not lead:
            return
        vehicles = self.repository.list_vehicles(self.current_case.id)
        vehicle = (
            self.repository.get_vehicle(lead.linked_vehicle_id)
            if lead.linked_vehicle_id
            else None
        )
        if vehicle is None:
            notes = "\n".join(
                value for value in (
                    f"Body style: {lead.body_style}" if lead.body_style else "",
                    (
                        f"Distinguishing features: {lead.distinguishing_features}"
                        if lead.distinguishing_features else ""
                    ),
                    f"Hit-and-run lead: {lead.lead_number}",
                    lead.notes,
                ) if value
            )
            damage_notes = "\n".join(
                value for value in (
                    lead.observed_damage,
                    f"Missing parts: {lead.missing_parts}" if lead.missing_parts else "",
                ) if value
            )
            vehicle = Vehicle(
                id="",
                case_id=self.current_case.id,
                vehicle_number=self._next_number(
                    "V",
                    [item.vehicle_number for item in vehicles],
                ),
                year=lead.year_range,
                make=lead.make,
                model=lead.model,
                color=lead.color,
                vin=lead.vin,
                plate=lead.plate,
                plate_state=lead.plate_state,
                damage_notes=damage_notes,
                notes=notes,
            )
        dialog = VehicleDialog(
            self.current_case.id,
            self.repository.list_people(self.current_case.id),
            vehicle,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved = self.repository.save_vehicle(dialog.result_record())
            lead.linked_vehicle_id = saved.id
            lead.status = "Confirmed"
            self.repository.save_hit_run_vehicle_lead(lead)
            self.refresh_case_tables()
            self.statusBar().showMessage(
                f"{lead.lead_number} linked to {saved.vehicle_number}",
                2600,
            )

    def refresh_hit_run_person_leads(self) -> None:
        if not self.current_case:
            return
        vehicle_leads = {
            lead.id: lead
            for lead in self.repository.list_hit_run_vehicle_leads(self.current_case.id)
        }
        people = {
            person.id: person
            for person in self.repository.list_people(self.current_case.id)
        }
        rows = []
        for lead in self.repository.list_hit_run_person_leads(self.current_case.id):
            description = " | ".join(
                value for value in (
                    lead.sex,
                    lead.race,
                    f"Age {lead.estimated_age}" if lead.estimated_age else "",
                    lead.height,
                    lead.weight_build,
                    lead.clothing,
                ) if value
            )
            associated_vehicle = vehicle_leads.get(lead.vehicle_lead_id)
            reason = " | ".join(
                value for value in (lead.reason_for_lead, lead.information_source) if value
            )
            linked = people.get(lead.linked_person_id)
            rows.append((lead.id, [
                lead.lead_number,
                lead.status,
                lead.display_name,
                description,
                associated_vehicle.lead_number if associated_vehicle else "",
                reason,
                linked.display_name if linked else "",
                lead.follow_up,
            ]))
        self._populate_table(self.hit_run_person_leads_table, rows)

    def add_hit_run_person_lead(self) -> None:
        if not self.current_case:
            return
        records = self.repository.list_hit_run_person_leads(self.current_case.id)
        record = HitRunPersonLead(
            id="",
            case_id=self.current_case.id,
            lead_number=self._next_number(
                "HRP",
                [lead.lead_number for lead in records],
            ),
        )
        dialog = HitRunPersonLeadDialog(
            self.current_case.id,
            self.repository.list_people(self.current_case.id),
            self.repository.list_hit_run_vehicle_leads(self.current_case.id),
            record,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_hit_run_person_lead(dialog.result_record())
            self._mark_hit_run_active()
            self.refresh_hit_run_person_leads()

    def edit_hit_run_person_lead(self, *_args) -> None:
        record_id = self._selected_id(self.hit_run_person_leads_table)
        if not record_id or not self.current_case:
            return
        record = self.repository.get_hit_run_person_lead(record_id)
        if not record:
            return
        dialog = HitRunPersonLeadDialog(
            record.case_id,
            self.repository.list_people(record.case_id),
            self.repository.list_hit_run_vehicle_leads(record.case_id),
            record,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_hit_run_person_lead(dialog.result_record())
            self._mark_hit_run_active()
            self.refresh_hit_run_person_leads()

    def delete_hit_run_person_lead(self) -> None:
        record_id = self._selected_id(self.hit_run_person_leads_table)
        if record_id and self._confirm_remove("Remove this person lead / possible suspect?"):
            self.repository.delete_hit_run_person_lead(record_id)
            self.refresh_hit_run_person_leads()

    def promote_hit_run_person_lead(self) -> None:
        record_id = self._selected_id(self.hit_run_person_leads_table)
        if not record_id or not self.current_case:
            return
        lead = self.repository.get_hit_run_person_lead(record_id)
        if not lead:
            return
        person = (
            self.repository.get_person(lead.linked_person_id)
            if lead.linked_person_id
            else None
        )
        if person is None:
            notes = "\n".join(
                value for value in (
                    f"Hit-and-run person lead: {lead.lead_number}",
                    f"Alias: {lead.alias}" if lead.alias else "",
                    f"Estimated age: {lead.estimated_age}" if lead.estimated_age else "",
                    f"Height / build: {' / '.join(value for value in (lead.height, lead.weight_build) if value)}"
                    if lead.height or lead.weight_build else "",
                    f"Hair / eyes: {' / '.join(value for value in (lead.hair, lead.eyes) if value)}"
                    if lead.hair or lead.eyes else "",
                    f"Facial hair: {lead.facial_hair}" if lead.facial_hair else "",
                    f"Clothing: {lead.clothing}" if lead.clothing else "",
                    (
                        f"Driver license: {lead.driver_license_state} {lead.driver_license_number}".strip()
                        if lead.driver_license_number or lead.driver_license_state else ""
                    ),
                    (
                        f"Vehicle relationship: {lead.relationship_to_vehicle}"
                        if lead.relationship_to_vehicle else ""
                    ),
                    f"Reason for lead: {lead.reason_for_lead}" if lead.reason_for_lead else "",
                    f"Information source: {lead.information_source}" if lead.information_source else "",
                    f"Follow-up: {lead.follow_up}" if lead.follow_up else "",
                ) if value
            )
            person = Person(
                id="",
                case_id=self.current_case.id,
                first_name=lead.first_name,
                middle_name=lead.middle_name,
                last_name=lead.last_name,
                sex=lead.sex,
                race=lead.race,
                cell_phone=lead.cell_phone,
                home_phone=lead.home_phone,
                work_phone=lead.work_phone,
                email=lead.email,
                address=lead.address,
                city=lead.city,
                state=lead.state,
                zip_code=lead.zip_code,
                notes=notes,
                roles=["Suspect"],
            )
        dialog = PersonDialog(self.current_case.id, person, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved = self.repository.save_person(dialog.result_record())
            lead.linked_person_id = saved.id
            lead.status = "Confirmed"
            self.repository.save_hit_run_person_lead(lead)
            self.refresh_case_tables()
            self.statusBar().showMessage(
                f"{lead.lead_number} linked to {saved.display_name}",
                2600,
            )

    def edit_vehicle_inspection(self) -> None:
        vehicle_id = self._selected_id(self.vehicles_table)
        if not vehicle_id:
            return
        vehicle = self.repository.get_vehicle(vehicle_id)
        if not vehicle:
            return
        inspection = self.repository.get_vehicle_inspection(vehicle_id)
        tires = self.repository.list_tires(vehicle_id)
        dialog = VehicleInspectionDialog(vehicle, inspection, tires, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            inspection, tires = dialog.result_records()
            self.repository.save_vehicle_inspection(inspection)
            self.repository.replace_tires(vehicle_id, tires)
            self.statusBar().showMessage("Vehicle inspection saved", 2200)

    def edit_motorcycle_inspection(self) -> None:
        vehicle_id = self._selected_id(self.vehicles_table)
        if not vehicle_id:
            return
        vehicle = self.repository.get_vehicle(vehicle_id)
        if not vehicle:
            return
        inspection = self.repository.get_motorcycle_inspection(vehicle_id)
        dialog = MotorcycleInspectionDialog(vehicle, inspection, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_motorcycle_inspection(dialog.result_record())
            self.statusBar().showMessage("Motorcycle inspection saved", 2200)

    def _case_relationship_maps(self):
        if not self.current_case:
            return {}, {}
        people = {p.id: p for p in self.repository.list_people(self.current_case.id)}
        vehicles = {v.id: v for v in self.repository.list_vehicles(self.current_case.id)}
        return people, vehicles

    def refresh_contacts(self) -> None:
        if not self.current_case:
            return
        people, vehicles = self._case_relationship_maps()
        rows = []
        for contact in self.repository.list_contacts(self.current_case.id):
            contact_name = people[contact.contact_person_id].display_name if contact.contact_person_id in people else contact.contact_name
            subject = "Needs person assignment"
            if contact.subject_person_id in people:
                subject = people[contact.subject_person_id].display_name
            elif contact.vehicle_id in vehicles:
                vehicle = vehicles[contact.vehicle_id]
                subject += f" (legacy vehicle: {vehicle.vehicle_number} {vehicle.description})"
            rows.append((contact.id, [
                subject, contact.contact_type, contact_name,
                contact.cell_phone, contact.home_phone, contact.work_phone,
                contact.organization, contact.notes,
            ]))
        self._populate_table(self.contacts_table, rows)

    def add_contact(self) -> None:
        if not self.current_case:
            return
        people = self.repository.list_people(self.current_case.id)
        if not people:
            QMessageBox.warning(
                self,
                "Person required",
                "Add the person before adding a related contact.",
            )
            return
        selected_person_id = self._selected_id(self.people_table)
        contact = ContactRelationship(
            id="",
            case_id=self.current_case.id,
            subject_person_id=selected_person_id,
        )
        dialog = ContactRelationshipDialog(
            self.current_case.id,
            people,
            contact,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_contact(dialog.result_record())
            self.refresh_contacts()

    def edit_contact(self, *_args) -> None:
        contact_id = self._selected_id(self.contacts_table)
        if not contact_id or not self.current_case:
            return
        contact = self.repository.get_contact(contact_id)
        if not contact:
            return
        dialog = ContactRelationshipDialog(
            self.current_case.id,
            self.repository.list_people(self.current_case.id),
            contact,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_contact(dialog.result_record())
            self.refresh_contacts()

    def delete_contact(self) -> None:
        contact_id = self._selected_id(self.contacts_table)
        if contact_id and self._confirm_remove("Remove this contact relationship?"):
            self.repository.delete_contact(contact_id)
            self.refresh_contacts()

    def refresh_vru_analyses(self) -> None:
        if not self.current_case:
            return
        people, vehicles = self._case_relationship_maps()
        rows = []
        for analysis in self.repository.list_vru_analyses(self.current_case.id):
            person = people[analysis.person_id].display_name if analysis.person_id in people else ""
            vehicle = vehicles[analysis.vehicle_id] if analysis.vehicle_id in vehicles else None
            vehicle_name = f"{vehicle.vehicle_number} {vehicle.description}" if vehicle else ""
            motion = " / ".join(value for value in (analysis.roadway_position, analysis.movement_at_impact) if value)
            visibility_equipment = ", ".join(
                label
                for used, label in (
                    (analysis.light_meter_used, "Light meter"),
                    (analysis.light_board_used, "Light board"),
                )
                if used
            )
            rows.append((analysis.id, [person, vehicle_name, motion, visibility_equipment, analysis.notes]))
        self._populate_table(self.vru_table, rows)

    def add_vru_analysis(self) -> None:
        if not self.current_case:
            return
        dialog = VRUAnalysisDialog(
            self.current_case.id, self.repository.list_people(self.current_case.id),
            self.repository.list_vehicles(self.current_case.id), parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_vru_analysis(dialog.result_record())
            self.refresh_vru_analyses()

    def edit_vru_analysis(self, *_args) -> None:
        analysis_id = self._selected_id(self.vru_table)
        if not analysis_id or not self.current_case:
            return
        analysis = self.repository.get_vru_analysis(analysis_id)
        if not analysis:
            return
        dialog = VRUAnalysisDialog(
            self.current_case.id, self.repository.list_people(self.current_case.id),
            self.repository.list_vehicles(self.current_case.id), analysis, self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_vru_analysis(dialog.result_record())
            self.refresh_vru_analyses()

    def delete_vru_analysis(self) -> None:
        analysis_id = self._selected_id(self.vru_table)
        if analysis_id and self._confirm_remove("Remove this VRU analysis?"):
            self.repository.delete_vru_analysis(analysis_id)
            self.refresh_vru_analyses()

    def refresh_chronology(self) -> None:
        if not self.current_case:
            return
        self._populate_table(self.chronology_table, [
            (e.id, [
                format_date_for_display(e.event_date),
                e.event_time,
                e.category,
                e.summary,
                e.details,
            ])
            for e in self.repository.list_chronology(self.current_case.id)
        ])

    def add_chronology(self) -> None:
        if not self.current_case:
            return
        dialog = ChronologyDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_chronology(dialog.result_record())
            self.refresh_case_tables()

    def edit_chronology(self, *_args) -> None:
        entry_id = self._selected_id(self.chronology_table)
        if not entry_id or not self.current_case:
            return
        entry = next((e for e in self.repository.list_chronology(self.current_case.id) if e.id == entry_id), None)
        if entry:
            dialog = ChronologyDialog(entry.case_id, entry, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.repository.save_chronology(dialog.result_record())
                self.refresh_case_tables()

    def delete_chronology(self) -> None:
        entry_id = self._selected_id(self.chronology_table)
        if entry_id and self._confirm_remove("Remove this journal entry?"):
            self.repository.delete_chronology(entry_id)
            self.refresh_case_tables()

    def refresh_tasks(self) -> None:
        if not self.current_case:
            return
        self._populate_table(self.tasks_table, [
            (t.id, [
                t.status,
                t.category,
                t.description,
                format_date_for_display(t.due_date),
                t.notes,
            ])
            for t in self.repository.list_tasks(self.current_case.id)
        ])

    def add_task(self) -> None:
        if not self.current_case:
            return
        dialog = TaskDialog(self.current_case.id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.repository.save_task(dialog.result_record())
            self.refresh_case_tables()

    def edit_task(self, *_args) -> None:
        task_id = self._selected_id(self.tasks_table)
        if not task_id or not self.current_case:
            return
        task = next((t for t in self.repository.list_tasks(self.current_case.id) if t.id == task_id), None)
        if task:
            dialog = TaskDialog(task.case_id, task, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.repository.save_task(dialog.result_record())
                self.refresh_case_tables()

    def delete_task(self) -> None:
        task_id = self._selected_id(self.tasks_table)
        if task_id and self._confirm_remove("Remove this task?"):
            self.repository.delete_task(task_id)
            self.refresh_case_tables()

    def _confirm_remove(self, message: str) -> bool:
        answer = QMessageBox.question(
            self, "Confirm removal", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def export_case_packet_preview(self) -> None:
        if not self.current_case or not self.save_overview():
            return
        self.refresh_case_packet_preview(force_preview=True)
        if (
            not self.packet_preview_path.is_file()
            or self.packet_preview_status.text().startswith("Preview failed")
        ):
            QMessageBox.critical(
                self,
                "Case packet export failed",
                "The packet preview could not be generated. Review the preview "
                "message and try again.",
            )
            return
        reports_directory = self._reports_directory()
        if reports_directory is None:
            return
        packet_label, packet_suffix, _exporter = self._packet_preview_details()
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in (self.current_case.case_number or "CrashCase")
        )
        default = str(reports_directory / f"{safe_name}_{packet_suffix}.pdf")
        destination, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {packet_label} PDF",
            default,
            "PDF files (*.pdf)",
        )
        if not destination:
            return
        try:
            shutil.copy2(self.packet_preview_path, destination)
        except Exception as error:
            QMessageBox.critical(self, "Case packet export failed", str(error))
            return
        self.statusBar().showMessage(
            f"{packet_label} exported to {destination}",
            5000,
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(destination))

    def _create_packet_printer(self) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        case_number = self.current_case.case_number if self.current_case else ""
        _packet_label, packet_suffix, _exporter = self._packet_preview_details()
        printer.setDocName(
            f"{case_number or 'Traffic_Crash'}_{packet_suffix}"
        )
        printer.setCreator(f"Traffic Crash Notebook {__version__}")
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        return printer

    def print_case_packet(self) -> None:
        if not self.current_case or not self.save_overview():
            return
        self.refresh_case_packet_preview(force_preview=True)
        page_count = self.packet_pdf_document.pageCount()
        if (
            page_count < 1
            or not self.packet_preview_path.is_file()
            or self.packet_preview_status.text().startswith("Preview failed")
        ):
            QMessageBox.critical(
                self,
                "Case packet print failed",
                "The current packet preview could not be generated. Review the "
                "preview message and try again.",
            )
            return

        packet_label, _packet_suffix, _exporter = self._packet_preview_details()
        printer = self._create_packet_printer()
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(f"Print {packet_label}")
        dialog.setMinMax(1, page_count)
        dialog.setFromTo(1, page_count)
        for option in (
            QAbstractPrintDialog.PrintDialogOption.PrintPageRange,
            QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage,
            QAbstractPrintDialog.PrintDialogOption.PrintShowPageSize,
        ):
            dialog.setOption(option, True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not printer.isValid():
            QMessageBox.warning(
                self,
                "No printer available",
                "Windows did not report an available printer. Add or reconnect a "
                "printer, then try again.",
            )
            return

        current_page = self.packet_pdf_view.pageNavigator().currentPage()
        page_indexes = selected_pdf_page_indexes(
            printer,
            page_count,
            current_page=current_page,
        )
        try:
            printed_pages = print_pdf_document(
                self.packet_pdf_document,
                printer,
                page_indexes,
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Case packet print failed",
                f"The case packet could not be printed.\n\n{error}",
            )
            return
        destination = (
            printer.outputFileName()
            or printer.printerName()
            or "the selected printer"
        )
        self.statusBar().showMessage(
            f"Sent {printed_pages} {packet_label.lower()} page(s) to {destination}.",
            5000,
        )

    def export_pdf(self) -> None:
        if not self.current_case:
            return
        if not self.save_overview():
            return
        reports_directory = self._reports_directory()
        if reports_directory is None:
            return
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (self.current_case.case_number or "CrashCase"))
        default = str(reports_directory / f"{safe_name}_Full_Working_Packet.pdf")
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Full Working Crash Packet PDF",
            default,
            "PDF files (*.pdf)",
        )
        if not destination:
            return
        try:
            export_case_pdf(self.repository, self.current_case.id, destination)
        except Exception as exc:
            QMessageBox.critical(self, "PDF export failed", str(exc))
            return
        self.statusBar().showMessage(f"Full working packet exported to {destination}", 5000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(destination))

    def export_compact_pdf(self) -> None:
        if not self.current_case:
            return
        if not self.save_overview():
            return
        reports_directory = self._reports_directory()
        if reports_directory is None:
            return
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in (self.current_case.case_number or "CrashCase")
        )
        default = str(reports_directory / f"{safe_name}_Compact_Packet.pdf")
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Compact Completed-Case Packet PDF",
            default,
            "PDF files (*.pdf)",
        )
        if not destination:
            return
        try:
            export_case_compact_pdf(self.repository, self.current_case.id, destination)
        except Exception as exc:
            QMessageBox.critical(self, "PDF export failed", str(exc))
            return
        self.statusBar().showMessage(f"Compact packet exported to {destination}", 5000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(destination))

    def export_exchange_report(self) -> None:
        if not self.current_case:
            return
        if not self.save_overview():
            return
        self.refresh_exchange_report(force_preview=True)
        reports_directory = self._reports_directory()
        if reports_directory is None:
            return
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in (self.current_case.case_number or "CrashCase")
        )
        default = str(
            reports_directory / f"{safe_name}_Exchange_Report.pdf"
        )
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Traffic Crash Exchange Report PDF",
            default,
            "PDF files (*.pdf)",
        )
        if not destination:
            return
        destination_path = Path(destination)
        temporary_path = destination_path.with_name(
            f".{destination_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            export_exchange_report_pdf(
                self.repository,
                self.current_case.id,
                temporary_path,
            )
            pdf_bytes = temporary_path.read_bytes()
            if (
                len(pdf_bytes) < 1000
                or not pdf_bytes.startswith(b"%PDF-")
                or b"%%EOF" not in pdf_bytes[-1024:]
            ):
                raise RuntimeError(
                    "The newly generated exchange report did not pass its PDF integrity check."
                )
            os.replace(temporary_path, destination_path)
        except Exception as exc:
            QMessageBox.critical(self, "Exchange report export failed", str(exc))
            return
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        self.statusBar().showMessage(
            f"Exchange report exported to {destination}",
            5000,
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(destination))

    def _create_exchange_printer(self) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        case_number = self.current_case.case_number if self.current_case else ""
        printer.setDocName(
            f"{case_number or 'Traffic_Crash'}_Exchange_Report"
        )
        printer.setCreator(f"Traffic Crash Notebook {__version__}")
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        return printer

    def print_exchange_report(self) -> None:
        if not self.current_case or not self.save_overview():
            return
        self.refresh_exchange_report(force_preview=True)
        page_count = self.exchange_pdf_document.pageCount()
        if not self._exchange_preview_is_current():
            QMessageBox.critical(
                self,
                "Exchange report print failed",
                "A verified preview for the selected case could not be generated. "
                "Nothing was sent to the printer. Review the preview message and "
                "try again.",
            )
            return

        printer = self._create_exchange_printer()
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Print Traffic Crash Exchange Report")
        dialog.setMinMax(1, page_count)
        dialog.setFromTo(1, page_count)
        for option in (
            QAbstractPrintDialog.PrintDialogOption.PrintPageRange,
            QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage,
            QAbstractPrintDialog.PrintDialogOption.PrintShowPageSize,
        ):
            dialog.setOption(option, True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not printer.isValid():
            QMessageBox.warning(
                self,
                "No printer available",
                "Windows did not report an available printer. Add or reconnect a "
                "printer, then try again.",
            )
            return

        current_page = self.exchange_pdf_view.pageNavigator().currentPage()
        page_indexes = selected_pdf_page_indexes(
            printer,
            page_count,
            current_page=current_page,
        )
        try:
            printed_pages = print_pdf_document(
                self.exchange_pdf_document,
                printer,
                page_indexes,
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Exchange report print failed",
                f"The exchange report could not be printed.\n\n{error}",
            )
            return
        destination = (
            printer.outputFileName()
            or printer.printerName()
            or "the selected printer"
        )
        self.statusBar().showMessage(
            f"Sent {printed_pages} exchange-report page(s) to {destination}.",
            5000,
        )

    def export_summary_pdf(self) -> None:
        if not self.current_case:
            return
        if not self.save_overview():
            return
        reports_directory = self._reports_directory()
        if reports_directory is None:
            return
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in (self.current_case.case_number or "CrashCase")
        )
        default = str(reports_directory / f"{safe_name}_Quick_Review.pdf")
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export Quick Review PDF",
            default,
            "PDF files (*.pdf)",
        )
        if not destination:
            return
        try:
            export_case_summary_pdf(self.repository, self.current_case.id, destination)
        except Exception as exc:
            QMessageBox.critical(self, "PDF export failed", str(exc))
            return
        self.statusBar().showMessage(f"Quick review PDF exported to {destination}", 5000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(destination))

    def backup_database(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backups_directory = self._backups_directory()
        if backups_directory is None:
            return
        default = str(backups_directory / f"TrafficCrashNotebook-backup-{timestamp}.sqlite3")
        destination, _ = QFileDialog.getSaveFileName(self, "Back Up Case Database", default, "SQLite database (*.sqlite3)")
        if destination:
            self.repository.backup_to(destination)
            QMessageBox.information(self, "Backup complete", f"Database backed up to:\n{destination}")

    def open_data_folder(self) -> None:
        if not self.repository.database_path.parent.is_dir():
            QMessageBox.critical(
                self,
                "Data folder unavailable",
                "The configured data folder is not currently available:\n\n"
                f"{self.repository.database_path.parent}",
            )
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.repository.database_path.parent))
        )

    def open_weather_history(self, *_args) -> None:
        if QDesktopServices.openUrl(QUrl(WEATHER_HISTORY_URL)):
            return
        QMessageBox.warning(
            self,
            "Unable to open weather history",
            "Traffic Crash Notebook could not open the default browser. "
            f"Open this address manually:\n\n{WEATHER_HISTORY_URL}",
        )

    def _storage_subdirectory(self, name: str) -> Path | None:
        path = self.repository.database_path.parent / name
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(
                self,
                "Data folder unavailable",
                "Traffic Crash Notebook cannot reach the configured storage folder. "
                "Reconnect the drive and try again. No alternate database or report "
                "folder was used.\n\n"
                f"{path}\n\n{error}",
            )
            return None
        return path

    def _reports_directory(self) -> Path | None:
        return self._storage_subdirectory("Reports")

    def _backups_directory(self) -> Path | None:
        return self._storage_subdirectory("Backups")

    def show_settings(self) -> None:
        dialog = ApplicationSettingsDialog(
            self.repository.database_path.parent,
            self.repository.get_user_defaults(),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.repository.save_user_defaults(dialog.user_defaults())
        except (OSError, sqlite3.Error) as error:
            QMessageBox.critical(
                self,
                "Settings could not be saved",
                "Traffic Crash Notebook could not save the user defaults in the "
                "selected case-data location. Reconnect the drive and try again.\n\n"
                f"{self.repository.database_path}\n\n{error}",
            )
            return
        if dialog.change_storage_requested:
            self.change_storage_location()
            return
        self.statusBar().showMessage(
            "Settings saved; defaults will be used for new cases.",
            3500,
        )

    def _check_updates_if_due(self) -> None:
        try:
            defaults = self.repository.get_user_defaults()
        except (OSError, sqlite3.Error):
            return
        if defaults.auto_check_updates and should_check_for_updates(
            defaults.last_update_check
        ):
            self.check_for_updates(manual=False)

    def check_for_updates(self, *, manual: bool = True) -> None:
        if self.update_check_thread and self.update_check_thread.isRunning():
            if manual:
                self.statusBar().showMessage("An update check is already running.", 3000)
            return
        self.update_check_was_manual = manual
        self.check_updates_action.setEnabled(False)
        if manual:
            self.statusBar().showMessage("Checking GitHub for updates...")
        thread = UpdateCheckThread(self)
        self.update_check_thread = thread
        thread.manifest_ready.connect(self._update_manifest_received)
        thread.check_failed.connect(self._update_check_failed)
        thread.finished.connect(self._update_check_finished)
        thread.start()

    def _update_check_finished(self) -> None:
        thread = self.update_check_thread
        self.update_check_thread = None
        self.check_updates_action.setEnabled(True)
        if thread:
            thread.deleteLater()

    def _record_successful_update_check(self) -> None:
        try:
            defaults = self.repository.get_user_defaults()
            defaults.last_update_check = successful_check_timestamp()
            self.repository.save_user_defaults(defaults)
        except (OSError, sqlite3.Error):
            pass

    def _update_manifest_received(self, manifest: UpdateManifest) -> None:
        self._record_successful_update_check()
        if not is_update_available(__version__, manifest.version):
            if self.update_check_was_manual:
                QMessageBox.information(
                    self,
                    "No update available",
                    f"Traffic Crash Notebook {__version__} is current.\n\n"
                    "The verified stable-release manifest was checked on GitHub.",
                )
            else:
                self.statusBar().showMessage("Traffic Crash Notebook is up to date.", 2500)
            return
        self._show_update_available(manifest)

    def _update_check_failed(self, message: str) -> None:
        if self.update_check_was_manual:
            QMessageBox.warning(
                self,
                "Update check unavailable",
                "Traffic Crash Notebook could not check the official GitHub release "
                f"manifest. No application files were changed.\n\n{message}",
            )
        else:
            self.statusBar().showMessage("Automatic update check unavailable.", 3500)

    def _show_update_available(self, manifest: UpdateManifest) -> None:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("Traffic Crash Notebook update available")
        message.setText(
            f"Version {manifest.version} is available. You are running {__version__}."
        )
        notes = manifest.release_notes or "See the GitHub release page for details."
        message.setInformativeText(
            f"{notes}\n\n"
            f"Portable ZIP size: {format_download_size(manifest.portable.size_bytes)}\n"
            "The ZIP will be SHA-256 verified after download. It will not be "
            "installed or extracted automatically."
        )
        message.setDetailedText(
            f"Build ID: {manifest.portable.build_id}\n"
            f"SHA-256: {manifest.portable.sha256}\n"
            f"Release: {manifest.release_page_url}"
        )
        download_button = message.addButton(
            "Download Verified ZIP",
            QMessageBox.ButtonRole.AcceptRole,
        )
        release_button = message.addButton(
            "Open Release Page",
            QMessageBox.ButtonRole.ActionRole,
        )
        message.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if clicked is download_button:
            self._start_update_download(manifest)
        elif clicked is release_button:
            QDesktopServices.openUrl(QUrl(manifest.release_page_url))

    def _start_update_download(self, manifest: UpdateManifest) -> None:
        if self.update_download_thread and self.update_download_thread.isRunning():
            self.statusBar().showMessage("An update download is already running.", 3000)
            return
        destination = self.repository.database_path.parent / "Updates"
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(
                self,
                "Update folder unavailable",
                f"The update ZIP could not be saved in:\n{destination}\n\n{error}",
            )
            return

        progress = QProgressDialog(
            f"Downloading Traffic Crash Notebook {manifest.version}...",
            "Cancel",
            0,
            1000,
            self,
        )
        progress.setWindowTitle("Downloading verified portable update")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        self.update_progress_dialog = progress

        thread = UpdateDownloadThread(manifest.portable, destination, self)
        self.update_download_thread = thread
        thread.download_progress.connect(self._update_download_progress)
        thread.download_ready.connect(self._update_download_ready)
        thread.download_failed.connect(self._update_download_failed)
        thread.download_cancelled.connect(self._update_download_cancelled)
        thread.finished.connect(self._update_download_finished)
        progress.canceled.connect(thread.requestInterruption)
        thread.start()

    def _update_download_progress(self, downloaded: int, total: int) -> None:
        if not self.update_progress_dialog or total <= 0:
            return
        self.update_progress_dialog.setValue(min(1000, int(downloaded * 1000 / total)))
        self.update_progress_dialog.setLabelText(
            "Downloading and verifying portable update...\n"
            f"{format_download_size(downloaded)} of {format_download_size(total)}"
        )

    def _update_download_ready(self, downloaded_path: str) -> None:
        path = Path(downloaded_path)
        if self.update_progress_dialog:
            self.update_progress_dialog.setValue(1000)
            self.update_progress_dialog.close()
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("Verified update downloaded")
        message.setText("The portable update ZIP was downloaded and verified.")
        message.setInformativeText(
            f"{path}\n\n"
            "Close Traffic Crash Notebook before updating. Extract the complete new "
            "TrafficCrashNotebook folder to a writable location, then run the new "
            "executable. No installer or administrator rights are required. Your "
            "case database remains in the separately selected data folder."
        )
        open_button = message.addButton(
            "Open Download Folder",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _update_download_failed(self, message: str) -> None:
        if self.update_progress_dialog:
            self.update_progress_dialog.close()
        QMessageBox.critical(
            self,
            "Update download failed",
            "The portable update was not saved because it could not be completely "
            f"downloaded and verified. No application files were changed.\n\n{message}",
        )

    def _update_download_cancelled(self) -> None:
        if self.update_progress_dialog:
            self.update_progress_dialog.close()
        self.statusBar().showMessage("Update download cancelled.", 3000)

    def _update_download_finished(self) -> None:
        thread = self.update_download_thread
        self.update_download_thread = None
        self.update_progress_dialog = None
        if thread:
            thread.deleteLater()

    def change_storage_location(self) -> None:
        if not self.save_overview():
            return
        current_directory = self.repository.database_path.parent
        config = run_storage_setup(
            current_directory=current_directory,
            source_database=self.repository.database_path,
            parent=self,
        )
        if config is None:
            return
        current_path = os.path.normcase(str(self.repository.database_path.resolve()))
        selected_path = os.path.normcase(str(config.database_path.resolve()))
        if current_path == selected_path:
            QMessageBox.information(
                self,
                "Data storage confirmed",
                f"Traffic Crash Notebook will continue using:\n{config.directory}",
            )
            return
        QMessageBox.information(
            self,
            "Restart required",
            "The new storage folder is ready and any selected existing cases were "
            "copied safely. Traffic Crash Notebook will close now. Reopen it to use:\n\n"
            f"{config.directory}",
        )
        self.close()

    def about_text(self) -> str:
        return "\n".join((
            format_about_text(self.build_info, SCHEMA_VERSION),
            f"Case data folder: {self.repository.database_path.parent}",
        ))

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Traffic Crash Notebook",
            self.about_text(),
        )

    def closeEvent(self, event) -> None:
        if self.update_download_thread and self.update_download_thread.isRunning():
            self.update_download_thread.requestInterruption()
            QMessageBox.information(
                self,
                "Cancelling update download",
                "Traffic Crash Notebook is safely cancelling the update download. "
                "Close the application again after the download window disappears.",
            )
            event.ignore()
            return
        if self.update_check_thread and self.update_check_thread.isRunning():
            QMessageBox.information(
                self,
                "Update check in progress",
                "The update check will finish in a few seconds. Close the application "
                "again after it finishes.",
            )
            event.ignore()
            return
        if not self.save_overview():
            answer = QMessageBox.question(
                self,
                "Unsaved case changes",
                "The configured data folder is unavailable, so recent changes could "
                "not be saved. Exit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.autosave_timer.stop()
        self.periodic_autosave_timer.stop()
        event.accept()


def run(
    repository: CaseRepository,
    on_ready: Callable[[], object] | None = None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    configure_application(app)
    window = MainWindow(repository)
    window.show()
    app.processEvents()
    if on_ready is not None:
        on_ready()
    return app.exec()
