from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..date_format import (
    DISPLAY_DATE_PLACEHOLDER,
    format_date_for_display,
    normalize_date_for_storage,
)
from ..models import (
    CHRONOLOGY_CATEGORIES,
    HIT_RUN_CONFIDENCE_LEVELS,
    HIT_RUN_LEAD_STATUSES,
    IMPAIRMENT_TESTING_OPTIONS,
    INJURY_CODE_OPTIONS,
    MOTORCYCLE_INSPECTION_ITEMS,
    PARTICIPANT_EVIDENCE_OPTIONS,
    PERSON_ROLES,
    PHYSICAL_CONDITION_OPTIONS,
    TASK_STATUSES,
    VRU_PROJECTION_OPTIONS,
    CaseTask,
    ChargeDisposition,
    ChronologyEntry,
    ContactRelationship,
    DriverProfile,
    HitRunEvidenceItem,
    HitRunPersonLead,
    HitRunVehicleLead,
    MotorcycleInspection,
    MotorcycleInspectionItem,
    ParticipantDetails,
    Person,
    RoadwayRecord,
    SurfaceObservation,
    TireInspection,
    Vehicle,
    VehicleInspection,
    VEHICLE_WORKFLOW_FIELDS,
    VideoSource,
    VRUAnalysis,
    WitnessDetails,
)
from .spellcheck_text_edit import SpellCheckedLineEdit, SpellCheckedTextEdit


YES_NO_UNKNOWN = ("Unknown", "Yes", "No")


def _line(text: str = "", placeholder: str = "") -> QLineEdit:
    widget = QLineEdit(text)
    if placeholder:
        widget.setPlaceholderText(placeholder)
    return widget


def _date_line(text: str = "") -> QLineEdit:
    widget = _line(format_date_for_display(text), DISPLAY_DATE_PLACEHOLDER)
    widget.editingFinished.connect(
        lambda: widget.setText(format_date_for_display(widget.text()))
    )
    return widget


def _combo(values: tuple[str, ...] | list[str], current: str = "", editable: bool = False) -> QComboBox:
    widget = QComboBox()
    widget.setEditable(editable)
    widget.addItems(values)
    if current:
        index = widget.findText(current)
        if index >= 0:
            widget.setCurrentIndex(index)
        elif editable:
            widget.setCurrentText(current)
    return widget


def _stored_selections(value: str) -> set[str]:
    normalized = value.replace("\n", ";")
    return {item.strip() for item in normalized.split(";") if item.strip()}


def _checkbox_group(
    title: str,
    options: tuple[str, ...],
    current: str = "",
    columns: int = 2,
) -> tuple[QGroupBox, dict[str, QCheckBox]]:
    group = QGroupBox(title)
    layout = QGridLayout(group)
    selected = _stored_selections(current)
    boxes: dict[str, QCheckBox] = {}
    for index, option in enumerate(options):
        box = QCheckBox(option)
        box.setChecked(option in selected)
        layout.addWidget(box, index // columns, index % columns)
        boxes[option] = box
    return group, boxes


def _selection_text(boxes: dict[str, QCheckBox]) -> str:
    return "; ".join(option for option, box in boxes.items() if box.isChecked())


class RecordDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(650, 640)
        self.window_layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget()
        self.root = QVBoxLayout(self.content)
        self.scroll_area.setWidget(self.content)
        self.window_layout.addWidget(self.scroll_area, 1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.record_dirty = False
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setDefault(True)

    def finish_layout(self) -> None:
        self.window_layout.addWidget(self.buttons)
        for widget in self.findChildren(QLineEdit):
            widget.textEdited.connect(self._mark_dirty)
        for widget in self.findChildren(QTextEdit):
            widget.textChanged.connect(
                lambda text_widget=widget: self._mark_text_edit_dirty(text_widget)
            )
        for widget in self.findChildren(QComboBox):
            widget.activated.connect(self._mark_dirty)
        for widget in self.findChildren(QCheckBox):
            widget.clicked.connect(self._mark_dirty)
        for widget in self.findChildren(QTableWidget):
            widget.itemChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_args) -> None:
        self.record_dirty = True

    def _mark_text_edit_dirty(self, widget: QTextEdit) -> None:
        if widget.hasFocus() and widget.document().isModified():
            self.record_dirty = True

    def _confirm_discard(self) -> bool:
        if not self.record_dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Discard unsaved record changes?",
            "This record contains changes that have not been saved. Choose No to "
            "return to the record and use Save, or Yes to discard the changes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def reject(self) -> None:
        if self._confirm_discard():
            super().reject()

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    def showEvent(self, event) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            maximum_width = max(420, available.width() - 40)
            maximum_height = max(360, available.height() - 40)
            self.resize(
                min(self.width(), maximum_width),
                min(self.height(), maximum_height),
            )
        super().showEvent(event)

    def _validate_and_accept(self) -> None:
        self.accept()


class PersonDialog(RecordDialog):
    def __init__(self, case_id: str, person: Person | None = None, parent=None):
        super().__init__("Edit Person" if person else "Add Person", parent)
        self.person = person or Person(id="", case_id=case_id)

        form = QFormLayout()
        self.first_name = _line(self.person.first_name)
        self.middle_name = _line(self.person.middle_name)
        self.last_name = _line(self.person.last_name)
        self.dob = _date_line(self.person.dob)
        self.sex = _line(self.person.sex)
        self.race = _line(self.person.race)
        self.cell_phone = _line(self.person.cell_phone)
        self.home_phone = _line(self.person.home_phone)
        self.work_phone = _line(self.person.work_phone)
        self.email = _line(self.person.email)
        self.address = SpellCheckedLineEdit(self.person.address)
        self.city = _line(self.person.city)
        self.state = _line(self.person.state)
        self.zip_code = _line(self.person.zip_code)
        self.occupation = _line(self.person.occupation)
        self.business_address = SpellCheckedTextEdit(self.person.business_address)
        self.business_address.setMaximumHeight(70)
        form.addRow("First name", self.first_name)
        form.addRow("Middle name", self.middle_name)
        form.addRow("Last name", self.last_name)
        form.addRow("Date of birth", self.dob)
        form.addRow("Sex", self.sex)
        form.addRow("Race", self.race)
        form.addRow("Cell phone", self.cell_phone)
        form.addRow("Home phone", self.home_phone)
        form.addRow("Work phone", self.work_phone)
        form.addRow("Email", self.email)
        form.addRow("Street address", self.address)
        form.addRow("City", self.city)
        form.addRow("State", self.state)
        form.addRow("ZIP code", self.zip_code)
        form.addRow("Occupation", self.occupation)
        form.addRow("Business address", self.business_address)
        self.root.addLayout(form)

        group = QGroupBox("Role(s) in this case")
        grid = QGridLayout(group)
        self.role_boxes: dict[str, QCheckBox] = {}
        for index, role in enumerate(PERSON_ROLES):
            box = QCheckBox(role)
            box.setChecked(role in self.person.roles)
            grid.addWidget(box, index // 2, index % 2)
            self.role_boxes[role] = box
        self.root.addWidget(group)

        self.notes = SpellCheckedTextEdit(self.person.notes)
        self.notes.setPlaceholderText("Interview significance, injury information, contact details, or other working notes")
        self.root.addWidget(QLabel("Notes"))
        self.root.addWidget(self.notes, 1)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not (self.first_name.text().strip() or self.last_name.text().strip()):
            QMessageBox.warning(self, "Name required", "Enter at least a first or last name.")
            return
        super()._validate_and_accept()

    def result_record(self) -> Person:
        self.person.first_name = self.first_name.text().strip()
        self.person.middle_name = self.middle_name.text().strip()
        self.person.last_name = self.last_name.text().strip()
        self.person.dob = normalize_date_for_storage(self.dob.text())
        self.person.sex = self.sex.text().strip()
        self.person.race = self.race.text().strip()
        self.person.cell_phone = self.cell_phone.text().strip()
        self.person.home_phone = self.home_phone.text().strip()
        self.person.work_phone = self.work_phone.text().strip()
        self.person.email = self.email.text().strip()
        self.person.address = self.address.text().strip()
        self.person.city = self.city.text().strip()
        self.person.state = self.state.text().strip()
        self.person.zip_code = self.zip_code.text().strip()
        self.person.occupation = self.occupation.text().strip()
        self.person.business_address = self.business_address.toPlainText().strip()
        self.person.notes = self.notes.toPlainText().strip()
        self.person.roles = [role for role, box in self.role_boxes.items() if box.isChecked()]
        return self.person


class VehicleDialog(RecordDialog):
    def __init__(self, case_id: str, people: list[Person], vehicle: Vehicle | None = None, parent=None):
        super().__init__("Edit Vehicle" if vehicle else "Add Vehicle", parent)
        self.vehicle = vehicle or Vehicle(id="", case_id=case_id)
        self.people = people
        form = QFormLayout()
        self.vehicle_number = _line(self.vehicle.vehicle_number, "V-1")
        self.year = _line(self.vehicle.year)
        self.make = _line(self.vehicle.make)
        self.model = _line(self.vehicle.model)
        self.body_style = _line(self.vehicle.body_style, "Sedan, SUV, pickup, motorcycle...")
        self.color = _line(self.vehicle.color)
        self.vin = _line(self.vehicle.vin)
        self.plate = _line(self.vehicle.plate)
        self.plate_state = _line(self.vehicle.plate_state)
        self.driver = self._person_combo(self.vehicle.driver_person_id)
        self.owner = self._person_combo(self.vehicle.owner_person_id)
        self.insurance_company = _line(
            self.vehicle.insurance_company or self.vehicle.insurance
        )
        self.insurance_policy_number = _line(
            self.vehicle.insurance_policy_number
        )
        self.towed = QCheckBox("Yes")
        self.towed.setChecked(
            bool(self.vehicle.towed or self.vehicle.tow_information)
        )
        self.towed_to = _line(
            self.vehicle.tow_information,
            "Tow yard, evidence facility, or other destination",
        )
        self.towed_to.setEnabled(self.towed.isChecked())
        self.towed.toggled.connect(self.towed_to.setEnabled)
        self.edr_status = _line(
            self.vehicle.edr_status,
            "Optional explanatory or legacy CDR / EDR notes",
        )
        self.release_date = _date_line(self.vehicle.release_date)
        self.release_information = SpellCheckedLineEdit(
            self.vehicle.release_information
        )
        self.release_information.setPlaceholderText(
            "Released to, location, authorization, receipt, or other details"
        )
        form.addRow("Vehicle number", self.vehicle_number)
        form.addRow("Year", self.year)
        form.addRow("Make", self.make)
        form.addRow("Model", self.model)
        form.addRow("Body style", self.body_style)
        form.addRow("Color", self.color)
        form.addRow("VIN", self.vin)
        form.addRow("License plate", self.plate)
        form.addRow("Plate state", self.plate_state)
        form.addRow("Driver", self.driver)
        form.addRow("Owner", self.owner)
        form.addRow("Insurance company", self.insurance_company)
        form.addRow("Insurance policy number", self.insurance_policy_number)
        form.addRow("Towed", self.towed)
        form.addRow("Towed to", self.towed_to)
        form.addRow("CDR / EDR notes", self.edr_status)
        form.addRow("Release date", self.release_date)
        form.addRow("Release information", self.release_information)
        self.root.addLayout(form)

        workflow_group = QGroupBox("Vehicle-specific checklist")
        workflow_grid = QGridLayout(workflow_group)
        self.vehicle_workflow_boxes: dict[str, QCheckBox] = {}
        for index, (attribute, label) in enumerate(VEHICLE_WORKFLOW_FIELDS):
            box = QCheckBox(label)
            box.setChecked(bool(getattr(self.vehicle, attribute)))
            workflow_grid.addWidget(box, index // 2, index % 2)
            self.vehicle_workflow_boxes[attribute] = box
        self.root.addWidget(workflow_group)
        self.property_damage = SpellCheckedTextEdit(self.vehicle.property_damage)
        self.property_damage.setPlaceholderText(
            "Non-vehicle property damaged, such as a house, fence, sign, pole, or landscaping; enter None if none"
        )
        self.property_damage.setMaximumHeight(90)
        self.root.addWidget(QLabel("Other property damaged (exchange report)"))
        self.root.addWidget(self.property_damage)
        self.damage_notes = SpellCheckedTextEdit(self.vehicle.damage_notes)
        self.damage_notes.setPlaceholderText("Impact location, damage profile, crush, intrusion, or other observations")
        self.root.addWidget(QLabel("Damage notes"))
        self.root.addWidget(self.damage_notes, 1)
        self.notes = SpellCheckedTextEdit(self.vehicle.notes)
        self.root.addWidget(QLabel("Additional notes"))
        self.root.addWidget(self.notes, 1)
        self.finish_layout()

    def _person_combo(self, selected_id: str | None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Not assigned", None)
        for person in self.people:
            combo.addItem(person.display_name, person.id)
            if person.id == selected_id:
                combo.setCurrentIndex(combo.count() - 1)
        return combo

    def _validate_and_accept(self) -> None:
        if not self.vehicle_number.text().strip():
            QMessageBox.warning(self, "Vehicle number required", "Enter a vehicle number such as V-1.")
            return
        super()._validate_and_accept()

    def result_record(self) -> Vehicle:
        for attribute in ("vehicle_number", "year", "make", "model", "body_style", "color", "vin", "plate",
                          "plate_state", "insurance_company", "insurance_policy_number",
                          "edr_status", "release_information"):
            setattr(self.vehicle, attribute, getattr(self, attribute).text().strip())
        self.vehicle.towed = self.towed.isChecked()
        self.vehicle.tow_information = (
            self.towed_to.text().strip() if self.vehicle.towed else ""
        )
        self.vehicle.release_date = normalize_date_for_storage(
            self.release_date.text()
        )
        self.vehicle.insurance = self.vehicle.insurance_company
        for attribute, _label in VEHICLE_WORKFLOW_FIELDS:
            setattr(
                self.vehicle,
                attribute,
                self.vehicle_workflow_boxes[attribute].isChecked(),
            )
        self.vehicle.driver_person_id = self.driver.currentData()
        self.vehicle.owner_person_id = self.owner.currentData()
        self.vehicle.property_damage = self.property_damage.toPlainText().strip()
        self.vehicle.damage_notes = self.damage_notes.toPlainText().strip()
        self.vehicle.notes = self.notes.toPlainText().strip()
        return self.vehicle


class ChronologyDialog(RecordDialog):
    def __init__(self, case_id: str, entry: ChronologyEntry | None = None, parent=None):
        super().__init__("Edit Journal Entry" if entry else "Add Journal Entry", parent)
        self.entry = entry or ChronologyEntry(id="", case_id=case_id)
        self.resize(620, 420)
        form = QFormLayout()
        self.event_date = _date_line(self.entry.event_date)
        self.event_time = _line(self.entry.event_time, "HH:MM")
        self.category = _combo(CHRONOLOGY_CATEGORIES, self.entry.category, editable=True)
        self.summary = _line(
            self.entry.summary,
            "Brief investigative action, finding, or decision",
        )
        form.addRow("Date", self.event_date)
        form.addRow("Time", self.event_time)
        form.addRow("Category", self.category)
        form.addRow("Summary", self.summary)
        self.root.addLayout(form)
        self.details = SpellCheckedTextEdit(self.entry.details)
        self.details.setPlaceholderText(
            "Full journal details, follow-up, requests, results, or rationale"
        )
        self.root.addWidget(QLabel("Entry details"))
        self.root.addWidget(self.details, 1)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not (self.summary.text().strip() or self.details.toPlainText().strip()):
            QMessageBox.warning(
                self,
                "Journal entry required",
                "Enter a summary or journal details.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> ChronologyEntry:
        self.entry.event_date = normalize_date_for_storage(self.event_date.text())
        self.entry.event_time = self.event_time.text().strip()
        self.entry.category = self.category.currentText().strip()
        self.entry.summary = self.summary.text().strip()
        self.entry.details = self.details.toPlainText().strip()
        return self.entry


class TaskDialog(RecordDialog):
    def __init__(self, case_id: str, task: CaseTask | None = None, parent=None):
        super().__init__("Edit Task" if task else "Add Task", parent)
        self.task = task or CaseTask(id="", case_id=case_id)
        self.resize(620, 420)
        form = QFormLayout()
        self.status = _combo(TASK_STATUSES, self.task.status)
        self.category = _line(self.task.category, "Medical records, Video, Vehicle, Analysis...")
        self.description = _line(self.task.description)
        self.due_date = _date_line(self.task.due_date)
        self.completed_date = _date_line(self.task.completed_date)
        form.addRow("Status", self.status)
        form.addRow("Category", self.category)
        form.addRow("Description", self.description)
        form.addRow("Due date", self.due_date)
        form.addRow("Completed date", self.completed_date)
        self.root.addLayout(form)
        self.notes = SpellCheckedTextEdit(self.task.notes)
        self.root.addWidget(QLabel("Notes"))
        self.root.addWidget(self.notes, 1)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.description.text().strip():
            QMessageBox.warning(self, "Task required", "Enter a task description.")
            return
        super()._validate_and_accept()

    def result_record(self) -> CaseTask:
        self.task.status = self.status.currentText()
        self.task.category = self.category.text().strip()
        self.task.description = self.description.text().strip()
        self.task.due_date = normalize_date_for_storage(self.due_date.text())
        self.task.completed_date = normalize_date_for_storage(self.completed_date.text())
        self.task.notes = self.notes.toPlainText().strip()
        return self.task


class ChargeDispositionDialog(RecordDialog):
    def __init__(
        self,
        case_id: str,
        record: ChargeDisposition | None = None,
        parent=None,
    ):
        super().__init__("Edit Charge / Disposition" if record else "Add Charge / Disposition", parent)
        self.record = record or ChargeDisposition(id="", case_id=case_id)
        self.resize(640, 360)
        form = QFormLayout()
        self.charge = _line(self.record.charge)
        self.disposition = SpellCheckedTextEdit(self.record.disposition)
        self.disposition.setMaximumHeight(150)
        form.addRow("Charge", self.charge)
        form.addRow("Disposition", self.disposition)
        self.root.addLayout(form)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.charge.text().strip():
            QMessageBox.warning(self, "Charge required", "Enter a charge description.")
            return
        super()._validate_and_accept()

    def result_record(self) -> ChargeDisposition:
        self.record.charge = self.charge.text().strip()
        self.record.disposition = self.disposition.toPlainText().strip()
        return self.record


class VideoSourceDialog(RecordDialog):
    def __init__(self, case_id: str, record: VideoSource | None = None, parent=None):
        super().__init__("Edit Video Source" if record else "Add Video Source", parent)
        self.record = record or VideoSource(id="", case_id=case_id)
        self.resize(640, 400)
        form = QFormLayout()
        self.source = _line(self.record.source, "Camera, business, witness, vehicle...")
        self.address = _line(
            self.record.address,
            "Street address for the camera, business, residence, or other source",
        )
        self.axon_status = _combo(YES_NO_UNKNOWN, self.record.axon_status)
        self.notes = SpellCheckedTextEdit(self.record.notes)
        self.notes.setMaximumHeight(170)
        form.addRow("Source", self.source)
        form.addRow("Address", self.address)
        form.addRow("Uploaded to Axon", self.axon_status)
        form.addRow("Notes", self.notes)
        self.root.addLayout(form)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.source.text().strip():
            QMessageBox.warning(self, "Source required", "Describe the video source.")
            return
        if not self.address.text().strip():
            QMessageBox.warning(
                self,
                "Address required",
                "Enter the address where the video source is located.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> VideoSource:
        self.record.source = self.source.text().strip()
        self.record.address = self.address.text().strip()
        self.record.axon_status = self.axon_status.currentText()
        self.record.notes = self.notes.toPlainText().strip()
        return self.record


class SurfaceObservationDialog(RecordDialog):
    def __init__(self, case_id: str, record: SurfaceObservation | None = None, parent=None):
        super().__init__("Edit Surface" if record else "Add Surface", parent)
        self.record = record or SurfaceObservation(id="", case_id=case_id)
        self.resize(640, 450)
        form = QFormLayout()
        self.location = _line(
            self.record.location,
            "Roadway, direction, lane, shoulder, or test location...",
        )
        self.composition = _line(self.record.composition, "Asphalt, concrete, gravel...")
        self.condition = _line(self.record.condition, "Dry, wet, icy...")
        self.friction_value = _line(
            self.record.friction_value,
            "Measured or selected value; include method if helpful",
        )
        form.addRow("Roadway / location", self.location)
        form.addRow("Surface composition", self.composition)
        form.addRow("Surface condition", self.condition)
        form.addRow("Friction / drag factor", self.friction_value)
        self.root.addLayout(form)
        self.notes = SpellCheckedTextEdit(self.record.notes)
        self.notes.setPlaceholderText(
            "Test method, measurement source, lane treatment, contamination, grade, or other details"
        )
        self.root.addWidget(QLabel("Surface notes"))
        self.root.addWidget(self.notes, 1)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.location.text().strip():
            QMessageBox.warning(
                self,
                "Surface location required",
                "Enter the roadway, lane, shoulder, or test location for this surface.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> SurfaceObservation:
        for attribute in ("location", "composition", "condition", "friction_value"):
            setattr(self.record, attribute, getattr(self, attribute).text().strip())
        self.record.notes = self.notes.toPlainText().strip()
        return self.record


class RoadwayDialog(RecordDialog):
    def __init__(self, case_id: str, record: RoadwayRecord | None = None, parent=None):
        super().__init__("Edit Roadway" if record else "Add Roadway", parent)
        self.record = record or RoadwayRecord(id="", case_id=case_id)
        self.resize(720, 700)

        form = QFormLayout()
        self.roadway_tag = _line(
            self.record.roadway_tag,
            "Road name, route, direction, or approach (for example, I-5 NB)",
        )
        self.speed_limit = _line(self.record.speed_limit, "mph")
        self.speed_limit_posted = _combo(
            YES_NO_UNKNOWN,
            self.record.speed_limit_posted,
        )
        self.speed_limit_location = _line(
            self.record.speed_limit_location,
            "Location of sign or source of limit",
        )
        self.curve_radius = _line(self.record.curve_radius, "feet")
        self.chord = _line(self.record.chord, "feet")
        self.middle_ordinate = _line(self.record.middle_ordinate, "feet")
        self.critical_speed = _line(self.record.critical_speed, "mph")
        form.addRow("Roadway", self.roadway_tag)
        form.addRow("Speed limit", self.speed_limit)
        form.addRow("Speed limit posted", self.speed_limit_posted)
        form.addRow("Posting location", self.speed_limit_location)
        form.addRow("Curve radius", self.curve_radius)
        form.addRow("Chord", self.chord)
        form.addRow("Middle ordinate", self.middle_ordinate)
        form.addRow("Critical speed", self.critical_speed)
        self.root.addLayout(form)

        self.roadway_characteristics = SpellCheckedTextEdit(
            self.record.roadway_characteristics
        )
        self.roadway_characteristics.setPlaceholderText(
            "Grade, superelevation, lane geometry, irregularities, sight distance..."
        )
        self.roadway_characteristics.setMaximumHeight(130)
        self.root.addWidget(QLabel("Roadway characteristics"))
        self.root.addWidget(self.roadway_characteristics)

        self.traffic_controls = SpellCheckedTextEdit(self.record.traffic_controls)
        self.traffic_controls.setPlaceholderText(
            "Signals, signs, lane markings, or other controls"
        )
        self.traffic_controls.setMaximumHeight(120)
        self.root.addWidget(QLabel("Traffic controls"))
        self.root.addWidget(self.traffic_controls)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.roadway_tag.text().strip():
            QMessageBox.warning(
                self,
                "Roadway required",
                "Enter a road name, route, direction, or approach.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> RoadwayRecord:
        for attribute in (
            "roadway_tag",
            "speed_limit",
            "speed_limit_location",
            "curve_radius",
            "chord",
            "middle_ordinate",
            "critical_speed",
        ):
            setattr(self.record, attribute, getattr(self, attribute).text().strip())
        self.record.speed_limit_posted = self.speed_limit_posted.currentText()
        self.record.roadway_characteristics = (
            self.roadway_characteristics.toPlainText().strip()
        )
        self.record.traffic_controls = self.traffic_controls.toPlainText().strip()
        return self.record


class MotorcycleInspectionDialog(RecordDialog):
    RATINGS = (
        "",
        "1 - Not damaged",
        "2 - Damaged",
        "3 - Missing",
        "4 - Altered / Added",
    )

    def __init__(
        self,
        vehicle: Vehicle,
        inspection: MotorcycleInspection,
        parent=None,
    ):
        super().__init__(f"Motorcycle Inspection - {vehicle.vehicle_number} {vehicle.description}", parent)
        self.inspection = inspection
        self.resize(1050, 760)
        tabs = QTabWidget()

        details_tab = QWidget()
        details_form = QFormLayout(details_tab)
        for attribute, label in (
            ("frame_number", "Frame number"),
            ("engine_number", "Engine number"),
            ("inspection_date", "Date of inspection"),
            ("inspection_location", "Inspection location"),
            ("officer", "Inspected by / Officer"),
            ("dpsst", "DPSST"),
        ):
            widget = (
                _date_line(getattr(inspection, attribute))
                if attribute == "inspection_date"
                else _line(getattr(inspection, attribute))
            )
            setattr(self, attribute, widget)
            details_form.addRow(label, getattr(self, attribute))
        self.general_comments = SpellCheckedTextEdit(inspection.general_comments)
        details_form.addRow("General comments", self.general_comments)
        tabs.addTab(details_tab, "Inspection details")

        checklist_tab = QWidget()
        checklist_layout = QVBoxLayout(checklist_tab)
        checklist_layout.addWidget(QLabel(
            "Rating: 1 not damaged; 2 damaged; 3 missing; 4 altered or added. "
            "Use measurement and comments for item-specific readings and findings."
        ))
        self.item_table = QTableWidget(0, 5)
        self.item_table.setHorizontalHeaderLabels(
            ["No.", "Inspection item", "Rating", "Measurement / reading", "Comments"]
        )
        self.item_table.verticalHeader().setVisible(False)
        self.item_table.horizontalHeader().setStretchLastSection(True)
        self.item_rating_widgets: dict[int, QComboBox] = {}
        existing = {item.item_number: item for item in inspection.items}
        for number, label in MOTORCYCLE_INSPECTION_ITEMS:
            item = existing.get(number, MotorcycleInspectionItem(item_number=number))
            row = self.item_table.rowCount()
            self.item_table.insertRow(row)
            number_item = QTableWidgetItem(str(number))
            number_item.setFlags(number_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.item_table.setItem(row, 0, number_item)
            self.item_table.setItem(row, 1, label_item)
            rating = _combo(self.RATINGS, item.rating)
            self.item_table.setCellWidget(row, 2, rating)
            self.item_rating_widgets[number] = rating
            self.item_table.setItem(row, 3, QTableWidgetItem(item.measurement))
            self.item_table.setItem(row, 4, QTableWidgetItem(item.comments))
        self.item_table.setColumnWidth(0, 48)
        self.item_table.setColumnWidth(1, 260)
        self.item_table.setColumnWidth(2, 150)
        self.item_table.setColumnWidth(3, 190)
        checklist_layout.addWidget(self.item_table, 1)
        tabs.addTab(checklist_tab, "44-item checklist")

        self.root.addWidget(tabs, 1)
        self.finish_layout()

    def result_record(self) -> MotorcycleInspection:
        for attribute in (
            "frame_number", "engine_number", "inspection_date", "inspection_location",
            "officer", "dpsst",
        ):
            setattr(self.inspection, attribute, getattr(self, attribute).text().strip())
        self.inspection.inspection_date = normalize_date_for_storage(
            self.inspection.inspection_date
        )
        self.inspection.general_comments = self.general_comments.toPlainText().strip()
        items: list[MotorcycleInspectionItem] = []
        for row in range(self.item_table.rowCount()):
            number = int(self.item_table.item(row, 0).text())
            rating = self.item_rating_widgets[number].currentText()
            measurement_item = self.item_table.item(row, 3)
            comments_item = self.item_table.item(row, 4)
            measurement = measurement_item.text().strip() if measurement_item else ""
            comments = comments_item.text().strip() if comments_item else ""
            if rating or measurement or comments:
                items.append(MotorcycleInspectionItem(
                    item_number=number,
                    rating=rating,
                    measurement=measurement,
                    comments=comments,
                ))
        self.inspection.items = items
        return self.inspection


class ParticipantDetailsDialog(RecordDialog):
    def __init__(
        self,
        person: Person,
        vehicles: list[Vehicle],
        details: ParticipantDetails,
        parent=None,
    ):
        super().__init__(f"Participant / Medical - {person.display_name}", parent)
        self.details = details
        self.resize(760, 690)
        tabs = QTabWidget()

        participant_tab = QWidget()
        form = QFormLayout(participant_tab)
        self.vehicle = QComboBox()
        self.vehicle.addItem("Not associated with a vehicle", None)
        for vehicle in vehicles:
            self.vehicle.addItem(f"{vehicle.vehicle_number} - {vehicle.description}", vehicle.id)
            if details.vehicle_id == vehicle.id:
                self.vehicle.setCurrentIndex(self.vehicle.count() - 1)
        self.occupant_position = _line(details.occupant_position, "Driver / Front right / Rear left...")
        self.injury_status = _line(details.injury_status, "Killed / Injured / Not injured")
        self.transported = _combo(YES_NO_UNKNOWN, details.transported)
        self.transported_to = _line(details.transported_to)
        self.hospital = _line(details.hospital)
        self.medical_records_status = _line(details.medical_records_status, "Requested / Obtained / Not requested")
        self.height_value = _line(details.height)
        self.weight_value = _line(details.weight)
        self.seatbelt_installed = _combo(YES_NO_UNKNOWN, details.seatbelt_installed)
        self.seatbelt_used = _combo(YES_NO_UNKNOWN, details.seatbelt_used)
        self.airbag_deployed = _combo(YES_NO_UNKNOWN, details.airbag_deployed)
        self.ejected = _combo(YES_NO_UNKNOWN, details.ejected)
        self.extracted = _combo(YES_NO_UNKNOWN, details.extracted)
        form.addRow("Associated vehicle", self.vehicle)
        form.addRow("Occupant position", self.occupant_position)
        form.addRow("Injury / death status", self.injury_status)
        form.addRow("Transported", self.transported)
        form.addRow("Transported to", self.transported_to)
        form.addRow("Hospital", self.hospital)
        form.addRow("Medical records", self.medical_records_status)
        form.addRow("Height", self.height_value)
        form.addRow("Weight", self.weight_value)
        form.addRow("Seat belt installed", self.seatbelt_installed)
        form.addRow("Seat belt used", self.seatbelt_used)
        form.addRow("Air bag deployed", self.airbag_deployed)
        form.addRow("Ejected", self.ejected)
        form.addRow("Extracted", self.extracted)
        tabs.addTab(participant_tab, "Participant")

        medical_tab = QWidget()
        medical_layout = QFormLayout(medical_tab)
        self.autopsy_performed = _combo(YES_NO_UNKNOWN, details.autopsy_performed)
        self.autopsy_by = _line(details.autopsy_by)
        self.date_of_death = _date_line(details.date_of_death)
        self.cause_of_death = _line(details.cause_of_death)
        self.next_of_kin_notified = _combo(YES_NO_UNKNOWN, details.next_of_kin_notified)
        self.next_of_kin_notified_by = _line(details.next_of_kin_notified_by)
        self.injuries = SpellCheckedTextEdit(details.injuries)
        self.evidence_obtained = SpellCheckedTextEdit(details.evidence_obtained)
        self.lab_information = SpellCheckedTextEdit(details.lab_information)
        for widget in (self.injuries, self.evidence_obtained, self.lab_information):
            widget.setMaximumHeight(95)
        medical_layout.addRow("Autopsy performed", self.autopsy_performed)
        medical_layout.addRow("Autopsy performed by", self.autopsy_by)
        medical_layout.addRow("Date of death", self.date_of_death)
        medical_layout.addRow("Cause of death", self.cause_of_death)
        medical_layout.addRow("Next of kin notified", self.next_of_kin_notified)
        medical_layout.addRow("Notified by", self.next_of_kin_notified_by)
        medical_layout.addRow("Injuries", self.injuries)
        injury_group, self.injury_code_boxes = _checkbox_group(
            "Coded injury types", INJURY_CODE_OPTIONS, details.injury_codes, columns=2
        )
        medical_layout.addRow(injury_group)
        medical_layout.addRow("Evidence obtained", self.evidence_obtained)
        evidence_group, self.evidence_item_boxes = _checkbox_group(
            "Structured evidence collection",
            PARTICIPANT_EVIDENCE_OPTIONS,
            details.evidence_items,
            columns=4,
        )
        medical_layout.addRow(evidence_group)
        medical_layout.addRow("Lab information", self.lab_information)
        tabs.addTab(medical_tab, "Medical / Evidence")

        notes_tab = QWidget()
        notes_layout = QVBoxLayout(notes_tab)
        self.participant_notes = SpellCheckedTextEdit(details.notes)
        self.participant_notes.setPlaceholderText("Additional participant, treatment, or injury notes")
        notes_layout.addWidget(self.participant_notes)
        tabs.addTab(notes_tab, "Notes")
        self.root.addWidget(tabs, 1)
        self.finish_layout()

    def result_record(self) -> ParticipantDetails:
        self.details.vehicle_id = self.vehicle.currentData()
        for attribute in (
            "occupant_position", "injury_status", "transported_to", "medical_records_status",
            "hospital", "autopsy_by", "date_of_death",
            "cause_of_death", "next_of_kin_notified_by",
        ):
            setattr(self.details, attribute, getattr(self, attribute).text().strip())
        self.details.date_of_death = normalize_date_for_storage(
            self.details.date_of_death
        )
        self.details.height = self.height_value.text().strip()
        self.details.weight = self.weight_value.text().strip()
        for attribute in (
            "transported", "seatbelt_installed", "seatbelt_used", "airbag_deployed", "ejected",
            "extracted",
            "autopsy_performed", "next_of_kin_notified",
        ):
            setattr(self.details, attribute, getattr(self, attribute).currentText())
        self.details.injuries = self.injuries.toPlainText().strip()
        self.details.injury_codes = _selection_text(self.injury_code_boxes)
        self.details.evidence_obtained = self.evidence_obtained.toPlainText().strip()
        self.details.evidence_items = _selection_text(self.evidence_item_boxes)
        self.details.lab_information = self.lab_information.toPlainText().strip()
        self.details.notes = self.participant_notes.toPlainText().strip()
        return self.details


class DriverProfileDialog(RecordDialog):
    def __init__(self, person: Person, profile: DriverProfile, parent=None):
        super().__init__(f"Driver Background - {person.display_name}", parent)
        self.profile = profile
        self.resize(780, 710)
        tabs = QTabWidget()

        trip_tab = QWidget()
        trip_form = QFormLayout(trip_tab)
        self.trip_from = _line(profile.trip_from)
        self.trip_to = _line(profile.trip_to)
        self.trip_purpose = _line(profile.trip_purpose)
        self.last_stop_arrival = _line(profile.last_stop_arrival)
        self.last_stop_departed = _line(profile.last_stop_departed)
        trip_form.addRow("Trip from", self.trip_from)
        trip_form.addRow("Trip to", self.trip_to)
        trip_form.addRow("Purpose", self.trip_purpose)
        trip_form.addRow("Last stop arrival", self.last_stop_arrival)
        trip_form.addRow("Last stop departure", self.last_stop_departed)
        tabs.addTab(trip_tab, "Trip")

        condition_tab = QWidget()
        condition_form = QFormLayout(condition_tab)
        self.permanent_conditions = SpellCheckedTextEdit(profile.permanent_conditions)
        self.temporary_conditions = SpellCheckedTextEdit(profile.temporary_conditions)
        physical_group, self.physical_condition_boxes = _checkbox_group(
            "Physical condition selections",
            PHYSICAL_CONDITION_OPTIONS,
            profile.physical_condition_types,
            columns=3,
        )
        self.impairment_status = _combo(YES_NO_UNKNOWN, profile.impairment_status)
        self.bac = _line(profile.bac)
        self.testing = _line(profile.testing, "SFST, breath, urine, blood, DRE...")
        testing_group, self.testing_method_boxes = _checkbox_group(
            "Impairment / testing methods",
            IMPAIRMENT_TESTING_OPTIONS,
            profile.testing_methods,
            columns=3,
        )
        self.controlled_substances = _line(profile.controlled_substances)
        self.impairment_notes = SpellCheckedTextEdit(profile.impairment_notes)
        for widget in (self.permanent_conditions, self.temporary_conditions, self.impairment_notes):
            widget.setMaximumHeight(100)
        condition_form.addRow("Permanent conditions", self.permanent_conditions)
        condition_form.addRow("Temporary conditions", self.temporary_conditions)
        condition_form.addRow(physical_group)
        condition_form.addRow("Impairment indicated", self.impairment_status)
        condition_form.addRow("BAC", self.bac)
        condition_form.addRow("Testing", self.testing)
        condition_form.addRow(testing_group)
        condition_form.addRow("Controlled substances", self.controlled_substances)
        condition_form.addRow("Impairment notes", self.impairment_notes)
        tabs.addTab(condition_tab, "Condition / Impairment")

        history_tab = QWidget()
        history_form = QFormLayout(history_tab)
        for attribute, label in (
            ("sleep_time", "Sleep time"), ("wake_time", "Wake time"),
            ("hours_asleep", "Hours asleep"), ("hours_awake", "Hours awake"),
            ("work_start", "Work start"), ("work_end", "Work end"),
            ("hours_worked", "Hours worked"), ("type_of_work", "Type of work"),
        ):
            setattr(self, attribute, _line(getattr(profile, attribute)))
            history_form.addRow(label, getattr(self, attribute))
        self.familiar_with_road = _combo(YES_NO_UNKNOWN, profile.familiar_with_road)
        self.familiar_with_vehicle = _combo(YES_NO_UNKNOWN, profile.familiar_with_vehicle)
        self.years_driving = _line(profile.years_driving)
        self.previous_collisions = _line(profile.previous_collisions)
        self.previous_traffic_homicide = _line(profile.previous_traffic_homicide)
        history_form.addRow("Familiar with road", self.familiar_with_road)
        history_form.addRow("Familiar with vehicle", self.familiar_with_vehicle)
        history_form.addRow("Years driving", self.years_driving)
        history_form.addRow("Previous collisions", self.previous_collisions)
        history_form.addRow("Prior traffic homicide convictions", self.previous_traffic_homicide)
        tabs.addTab(history_tab, "Sleep / Work / History")

        license_tab = QWidget()
        license_form = QFormLayout(license_tab)
        self.license_restricted = _combo(YES_NO_UNKNOWN, profile.license_restricted)
        self.license_restriction_explanation = _line(profile.license_restriction_explanation)
        license_form.addRow("License restricted", self.license_restricted)
        license_form.addRow("Restriction explanation", self.license_restriction_explanation)
        for attribute, label in (
            ("license_restrictions", "Restrictions"), ("license_number", "License number"),
            ("license_state", "State"), ("license_class", "Class"),
            ("endorsements", "Endorsements"),
            ("license_status", "Status"),
        ):
            setattr(self, attribute, _line(getattr(profile, attribute)))
            license_form.addRow(label, getattr(self, attribute))
        self.driver_notes = SpellCheckedTextEdit(profile.notes)
        license_form.addRow("Additional notes", self.driver_notes)
        tabs.addTab(license_tab, "License / Notes")
        self.root.addWidget(tabs, 1)
        self.finish_layout()

    def result_record(self) -> DriverProfile:
        line_fields = (
            "trip_from", "trip_to", "trip_purpose", "last_stop_arrival", "last_stop_departed",
            "bac", "testing", "controlled_substances", "sleep_time", "wake_time",
            "hours_asleep", "hours_awake", "work_start", "work_end", "hours_worked",
            "type_of_work", "years_driving", "previous_collisions", "previous_traffic_homicide",
            "license_restrictions", "license_number", "license_state", "license_class", "endorsements",
            "license_status",
            "license_restriction_explanation",
        )
        for attribute in line_fields:
            setattr(self.profile, attribute, getattr(self, attribute).text().strip())
        for attribute in (
            "impairment_status", "familiar_with_road", "familiar_with_vehicle", "license_restricted"
        ):
            setattr(self.profile, attribute, getattr(self, attribute).currentText())
        self.profile.permanent_conditions = self.permanent_conditions.toPlainText().strip()
        self.profile.temporary_conditions = self.temporary_conditions.toPlainText().strip()
        self.profile.physical_condition_types = _selection_text(self.physical_condition_boxes)
        self.profile.testing_methods = _selection_text(self.testing_method_boxes)
        self.profile.impairment_notes = self.impairment_notes.toPlainText().strip()
        self.profile.notes = self.driver_notes.toPlainText().strip()
        return self.profile


class VehicleInspectionDialog(RecordDialog):
    DEFAULT_POSITIONS = ("RF", "LF", "LR", "RR", "LR (inner)", "RR (inner)")

    def __init__(
        self,
        vehicle: Vehicle,
        inspection: VehicleInspection,
        tires: list[TireInspection],
        parent=None,
    ):
        super().__init__(f"Vehicle Inspection - {vehicle.vehicle_number} {vehicle.description}", parent)
        self.inspection = inspection
        self.existing_tires = tires
        self.resize(940, 700)
        tabs = QTabWidget()

        general_tab = QWidget()
        form = QFormLayout(general_tab)
        for attribute, label in (
            ("mileage", "Mileage"), ("transmission", "Transmission"), ("gear", "Gear"),
            ("steering", "Steering"), ("registered_weight", "Registered weight"),
            ("curb_weight", "Curb weight"), ("measured_weight", "Measured weight"),
            ("front_brakes", "Front brakes"), ("rear_brakes", "Rear brakes"),
            ("brake_system", "Brake system"),
        ):
            setattr(self, attribute, _line(getattr(inspection, attribute)))
            form.addRow(label, getattr(self, attribute))
        for attribute, label in (
            ("nicb_status", "NICB check"),
            ("recall_status", "NHTSA recalls"),
            ("vin_decode_status", "VIN decode"),
        ):
            setattr(self, attribute, _line(getattr(inspection, attribute)))
            form.addRow(label, getattr(self, attribute))
        self.lighting_electrical = SpellCheckedTextEdit(inspection.lighting_electrical)
        self.body_equipment = SpellCheckedTextEdit(inspection.body_equipment)
        self.safety_systems = SpellCheckedTextEdit(inspection.safety_systems)
        for widget in (self.lighting_electrical, self.body_equipment, self.safety_systems):
            widget.setMaximumHeight(85)
        form.addRow("Lighting / electrical", self.lighting_electrical)
        form.addRow("Body equipment", self.body_equipment)
        form.addRow("Safety systems", self.safety_systems)
        tabs.addTab(general_tab, "General inspection")

        systems_tab = QWidget()
        systems_layout = QVBoxLayout(systems_tab)
        systems_layout.addWidget(QLabel(
            "Record whether each system was equipped and whether it was operable at inspection."
        ))
        self.system_check_widgets: dict[str, tuple[QComboBox, QComboBox]] = {}
        self.systems_table = QTableWidget(0, 3)
        self.systems_table.setHorizontalHeaderLabels(["System", "Equipped", "Operable"])
        self.systems_table.verticalHeader().setVisible(False)
        self.systems_table.horizontalHeader().setStretchLastSection(True)
        for key, label in (
            ("headlights", "Headlights"),
            ("taillights", "Taillights"),
            ("tag_lights", "Tag lights"),
            ("brake_lights", "Brake lights"),
            ("turn_signals", "Turn signals"),
            ("parking_lamps", "Parking lamps"),
            ("other_lights", "Other lights"),
            ("front_wipers", "Front wipers"),
            ("rear_wipers", "Rear wipers"),
            ("horn", "Horn"),
        ):
            row = self.systems_table.rowCount()
            self.systems_table.insertRow(row)
            self.systems_table.setItem(row, 0, QTableWidgetItem(label))
            equipped = _combo(YES_NO_UNKNOWN, getattr(inspection, f"{key}_equipped"))
            operable = _combo(YES_NO_UNKNOWN, getattr(inspection, f"{key}_operable"))
            self.systems_table.setCellWidget(row, 1, equipped)
            self.systems_table.setCellWidget(row, 2, operable)
            self.system_check_widgets[key] = (equipped, operable)
        self.systems_table.setColumnWidth(0, 240)
        systems_layout.addWidget(self.systems_table, 1)
        switches = QFormLayout()
        for attribute, label in (
            ("headlight_switch_position", "Headlight switch position"),
            ("wiper_switch_position", "Wiper switch position"),
            ("ignition_position", "Ignition position"),
            ("radio_position", "Radio position"),
            ("heater_position", "Heater position"),
        ):
            setattr(self, attribute, _line(getattr(inspection, attribute)))
            switches.addRow(label, getattr(self, attribute))
        systems_layout.addLayout(switches)
        tabs.addTab(systems_tab, "Systems")

        body_tab = QWidget()
        body_form = QFormLayout(body_tab)
        for attribute, label in (
            ("headlamp_lens_condition", "Headlamp lens condition"),
            ("safety_glass_condition", "Safety glass condition"),
            ("inside_mirror", "Inside mirror"),
            ("outside_mirrors", "Outside mirrors"),
            ("window_positions", "Window positions"),
            ("airbag_status", "Air bags (equipped / deployed / locations)"),
            ("body_interior_condition", "Interior condition"),
            ("body_exterior_condition", "Exterior condition"),
        ):
            setattr(self, attribute, _line(getattr(inspection, attribute)))
            body_form.addRow(label, getattr(self, attribute))
        for attribute, label in (
            ("seatbelts_equipped", "Seat belts equipped"),
            ("shoulder_harnesses_equipped", "Shoulder harnesses equipped"),
            ("seatbelt_loading", "Seat belt loading"),
            ("steering_wheel_damage", "Steering wheel damage"),
        ):
            setattr(self, attribute, _combo(YES_NO_UNKNOWN, getattr(inspection, attribute)))
            body_form.addRow(label, getattr(self, attribute))
        self.device_observations = SpellCheckedTextEdit(inspection.device_observations)
        self.device_observations.setMaximumHeight(105)
        body_form.addRow("Mounted phone / GPS / backlit device", self.device_observations)
        tabs.addTab(body_tab, "Body / Safety")

        tires_tab = QWidget()
        tires_layout = QVBoxLayout(tires_tab)
        self.tire_contribution = _combo(YES_NO_UNKNOWN, inspection.tire_contribution)
        top = QFormLayout()
        top.addRow("Did tire condition contribute?", self.tire_contribution)
        self.tire_contribution_explanation = SpellCheckedTextEdit(
            inspection.tire_contribution_explanation
        )
        self.tire_contribution_explanation.setMaximumHeight(75)
        top.addRow("Contribution explanation", self.tire_contribution_explanation)
        tires_layout.addLayout(top)
        headers = ["Position", "Make", "Design", "Size", "Pressure", "Tread in", "Tread mid", "Tread out", "Condition"]
        self.tire_table = QTableWidget(0, len(headers))
        self.tire_table.setHorizontalHeaderLabels(headers)
        self.tire_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tire_table.horizontalHeader().setStretchLastSection(True)
        existing = {tire.position: tire for tire in tires}
        positions = list(self.DEFAULT_POSITIONS)
        positions.extend(position for position in existing if position not in positions)
        for position in positions:
            tire = existing.get(position, TireInspection(id="", vehicle_id=vehicle.id, position=position))
            row = self.tire_table.rowCount()
            self.tire_table.insertRow(row)
            values = [
                tire.position, tire.make, tire.design, tire.size, tire.pressure,
                tire.tread_inside, tire.tread_middle, tire.tread_outside, tire.condition,
            ]
            for column, value in enumerate(values):
                self.tire_table.setItem(row, column, QTableWidgetItem(value))
        self.tire_table.setColumnWidth(0, 65)
        self.tire_table.setColumnWidth(1, 110)
        self.tire_table.setColumnWidth(2, 110)
        self.tire_table.setColumnWidth(3, 90)
        tire_buttons = QHBoxLayout()
        add_tire = QPushButton("Add tire position")
        add_tire.clicked.connect(self._add_tire_row)
        remove_tire = QPushButton("Remove selected tire")
        remove_tire.clicked.connect(self._remove_tire_row)
        tire_buttons.addWidget(add_tire)
        tire_buttons.addWidget(remove_tire)
        tire_buttons.addStretch(1)
        tires_layout.addLayout(tire_buttons)
        tires_layout.addWidget(self.tire_table, 1)
        self.tire_notes = SpellCheckedTextEdit(inspection.tire_notes)
        self.tire_notes.setMaximumHeight(100)
        tires_layout.addWidget(QLabel("Tire condition notes"))
        tires_layout.addWidget(self.tire_notes)
        tabs.addTab(tires_tab, "Tires")

        notes_tab = QWidget()
        notes_layout = QVBoxLayout(notes_tab)
        self.inspection_notes = SpellCheckedTextEdit(inspection.inspection_notes)
        self.inspection_notes.setPlaceholderText("Other inspection observations")
        notes_layout.addWidget(self.inspection_notes)
        tabs.addTab(notes_tab, "Notes")
        self.root.addWidget(tabs, 1)
        self.finish_layout()

    def _add_tire_row(self) -> None:
        row = self.tire_table.rowCount()
        self.tire_table.insertRow(row)
        for column in range(self.tire_table.columnCount()):
            self.tire_table.setItem(row, column, QTableWidgetItem(""))
        self.tire_table.setCurrentCell(row, 0)

    def _remove_tire_row(self) -> None:
        row = self.tire_table.currentRow()
        if row >= 0:
            self.tire_table.removeRow(row)

    def result_records(self) -> tuple[VehicleInspection, list[TireInspection]]:
        line_fields = (
            "mileage", "transmission", "gear", "steering", "registered_weight", "curb_weight",
            "measured_weight", "front_brakes", "rear_brakes", "brake_system",
            "nicb_status", "recall_status", "vin_decode_status", "headlight_switch_position",
            "wiper_switch_position", "ignition_position", "radio_position", "heater_position",
            "headlamp_lens_condition", "safety_glass_condition", "inside_mirror",
            "outside_mirrors", "window_positions", "airbag_status", "body_interior_condition",
            "body_exterior_condition",
        )
        for attribute in line_fields:
            setattr(self.inspection, attribute, getattr(self, attribute).text().strip())
        self.inspection.lighting_electrical = self.lighting_electrical.toPlainText().strip()
        self.inspection.body_equipment = self.body_equipment.toPlainText().strip()
        self.inspection.safety_systems = self.safety_systems.toPlainText().strip()
        for key, (equipped, operable) in self.system_check_widgets.items():
            setattr(self.inspection, f"{key}_equipped", equipped.currentText())
            setattr(self.inspection, f"{key}_operable", operable.currentText())
        for attribute in (
            "seatbelts_equipped", "shoulder_harnesses_equipped", "seatbelt_loading",
            "steering_wheel_damage",
        ):
            setattr(self.inspection, attribute, getattr(self, attribute).currentText())
        self.inspection.device_observations = self.device_observations.toPlainText().strip()
        self.inspection.tire_contribution = self.tire_contribution.currentText()
        self.inspection.tire_contribution_explanation = (
            self.tire_contribution_explanation.toPlainText().strip()
        )
        self.inspection.tire_notes = self.tire_notes.toPlainText().strip()
        self.inspection.inspection_notes = self.inspection_notes.toPlainText().strip()
        existing_ids = {t.position: t.id for t in self.existing_tires}
        tires: list[TireInspection] = []
        for row in range(self.tire_table.rowCount()):
            values = [self.tire_table.item(row, column).text().strip() if self.tire_table.item(row, column) else ""
                      for column in range(self.tire_table.columnCount())]
            if not any(values[1:]):
                continue
            tires.append(TireInspection(
                id=existing_ids.get(values[0], ""), vehicle_id=self.inspection.vehicle_id,
                position=values[0], make=values[1], design=values[2], size=values[3],
                pressure=values[4], tread_inside=values[5], tread_middle=values[6],
                tread_outside=values[7], condition=values[8],
            ))
        return self.inspection, tires


class WitnessDetailsDialog(RecordDialog):
    def __init__(self, person: Person, details: WitnessDetails, parent=None):
        super().__init__(f"Witness Interview - {person.display_name}", parent)
        self.details = details
        self.resize(720, 650)
        form = QFormLayout()
        self.interviewed = _combo(YES_NO_UNKNOWN, details.interviewed)
        self.interview_date = _date_line(details.interview_date)
        self.interviewer = _line(details.interviewer)
        self.significance = _line(details.significance, "What this witness may establish")
        form.addRow("Interviewed", self.interviewed)
        form.addRow("Interview date", self.interview_date)
        form.addRow("Interviewer", self.interviewer)
        form.addRow("Significance", self.significance)
        self.root.addLayout(form)
        self.statement_summary = SpellCheckedTextEdit(details.statement_summary)
        self.credibility_notes = SpellCheckedTextEdit(details.credibility_notes)
        self.follow_up = SpellCheckedTextEdit(details.follow_up)
        for label, widget in (
            ("Statement summary", self.statement_summary),
            ("Credibility / consistency notes", self.credibility_notes),
            ("Follow-up", self.follow_up),
        ):
            self.root.addWidget(QLabel(label))
            self.root.addWidget(widget, 1)
        self.finish_layout()

    def result_record(self) -> WitnessDetails:
        self.details.interviewed = self.interviewed.currentText()
        self.details.interview_date = normalize_date_for_storage(
            self.interview_date.text()
        )
        self.details.interviewer = self.interviewer.text().strip()
        self.details.significance = self.significance.text().strip()
        self.details.statement_summary = self.statement_summary.toPlainText().strip()
        self.details.credibility_notes = self.credibility_notes.toPlainText().strip()
        self.details.follow_up = self.follow_up.toPlainText().strip()
        return self.details


def _related_person_combo(people: list[Person], selected_id: str | None, empty_label: str) -> QComboBox:
    combo = QComboBox()
    combo.addItem(empty_label, None)
    for person in people:
        combo.addItem(person.display_name, person.id)
        if person.id == selected_id:
            combo.setCurrentIndex(combo.count() - 1)
    return combo


def _related_vehicle_combo(vehicles: list[Vehicle], selected_id: str | None) -> QComboBox:
    combo = QComboBox()
    combo.addItem("No associated vehicle", None)
    for vehicle in vehicles:
        combo.addItem(f"{vehicle.vehicle_number} - {vehicle.description}", vehicle.id)
        if vehicle.id == selected_id:
            combo.setCurrentIndex(combo.count() - 1)
    return combo


def _related_hit_run_vehicle_lead_combo(
    vehicle_leads: list[HitRunVehicleLead],
    selected_id: str | None,
) -> QComboBox:
    combo = QComboBox()
    combo.addItem("No associated vehicle lead", None)
    for lead in vehicle_leads:
        label = f"{lead.lead_number or 'Unnumbered'} - {lead.description}"
        combo.addItem(label, lead.id)
        if lead.id == selected_id:
            combo.setCurrentIndex(combo.count() - 1)
    return combo


class HitRunEvidenceDialog(RecordDialog):
    def __init__(
        self,
        case_id: str,
        vehicle_leads: list[HitRunVehicleLead],
        record: HitRunEvidenceItem | None = None,
        parent=None,
    ):
        super().__init__(
            "Edit Recovered Part / Evidence" if record else "Add Recovered Part / Evidence",
            parent,
        )
        self.record = record or HitRunEvidenceItem(id="", case_id=case_id)
        self.resize(720, 760)
        form = QFormLayout()
        self.evidence_number = _line(self.record.evidence_number, "Evidence or item number")
        self.evidence_type = _line(
            self.record.evidence_type,
            "Vehicle part, paint transfer, glass, debris...",
        )
        self.part_number = _line(self.record.part_number)
        self.manufacturer_markings = _line(self.record.manufacturer_markings)
        self.color = _line(self.record.color)
        self.material = _line(self.record.material)
        self.quantity = _line(self.record.quantity)
        self.recovery_location = SpellCheckedLineEdit(self.record.recovery_location)
        self.recovery_date = _date_line(self.record.recovery_date)
        self.recovery_time = _line(self.record.recovery_time, "HH:MM")
        self.recovered_by = _line(self.record.recovered_by)
        self.lab_status = _line(
            self.record.lab_status,
            "Not submitted, submitted, results received...",
        )
        self.vehicle_lead = _related_hit_run_vehicle_lead_combo(
            vehicle_leads,
            self.record.vehicle_lead_id,
        )
        for label, widget in (
            ("Evidence / item number", self.evidence_number),
            ("Evidence type", self.evidence_type),
            ("Part number", self.part_number),
            ("Manufacturer markings", self.manufacturer_markings),
            ("Color", self.color),
            ("Material", self.material),
            ("Quantity", self.quantity),
            ("Recovery location", self.recovery_location),
            ("Recovery date", self.recovery_date),
            ("Recovery time", self.recovery_time),
            ("Recovered by", self.recovered_by),
            ("Lab status", self.lab_status),
            ("Associated vehicle lead", self.vehicle_lead),
        ):
            form.addRow(label, widget)
        self.root.addLayout(form)

        self.part_description = SpellCheckedTextEdit(self.record.part_description)
        self.damage_paint_transfer = SpellCheckedTextEdit(
            self.record.damage_paint_transfer
        )
        self.vehicle_fitment = SpellCheckedTextEdit(self.record.vehicle_fitment)
        self.notes = SpellCheckedTextEdit(self.record.notes)
        for label, widget, placeholder in (
            (
                "Part / evidence description",
                self.part_description,
                "Shape, dimensions, condition, identifiers, and notable characteristics",
            ),
            (
                "Damage / paint transfer",
                self.damage_paint_transfer,
                "Fracture surfaces, paint layers, transfer, or collision-related damage",
            ),
            (
                "Possible vehicle fitment",
                self.vehicle_fitment,
                "Known or suspected year, make, model, body style, or fitment range",
            ),
            ("Notes", self.notes, "Chain-of-custody, photographs, comparison, or follow-up"),
        ):
            widget.setPlaceholderText(placeholder)
            widget.setMaximumHeight(105)
            self.root.addWidget(QLabel(label))
            self.root.addWidget(widget)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not any(
            (
                self.evidence_number.text().strip(),
                self.evidence_type.text().strip(),
                self.part_number.text().strip(),
                self.part_description.toPlainText().strip(),
            )
        ):
            QMessageBox.warning(
                self,
                "Evidence description required",
                "Enter an evidence number, type, part number, or description.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> HitRunEvidenceItem:
        for attribute in (
            "evidence_number",
            "evidence_type",
            "part_number",
            "manufacturer_markings",
            "color",
            "material",
            "quantity",
            "recovery_location",
            "recovery_time",
            "recovered_by",
            "lab_status",
        ):
            setattr(self.record, attribute, getattr(self, attribute).text().strip())
        self.record.recovery_date = normalize_date_for_storage(self.recovery_date.text())
        self.record.vehicle_lead_id = self.vehicle_lead.currentData()
        self.record.part_description = self.part_description.toPlainText().strip()
        self.record.damage_paint_transfer = (
            self.damage_paint_transfer.toPlainText().strip()
        )
        self.record.vehicle_fitment = self.vehicle_fitment.toPlainText().strip()
        self.record.notes = self.notes.toPlainText().strip()
        return self.record


class HitRunVehicleLeadDialog(RecordDialog):
    def __init__(
        self,
        case_id: str,
        vehicles: list[Vehicle],
        record: HitRunVehicleLead | None = None,
        parent=None,
    ):
        super().__init__("Edit Possible Vehicle Lead" if record else "Add Possible Vehicle Lead", parent)
        self.record = record or HitRunVehicleLead(id="", case_id=case_id)
        self.resize(760, 800)
        form = QFormLayout()
        self.lead_number = _line(self.record.lead_number, "HRV-1")
        self.status = _combo(HIT_RUN_LEAD_STATUSES, self.record.status)
        self.confidence = _combo(HIT_RUN_CONFIDENCE_LEVELS, self.record.confidence)
        self.year_range = _line(self.record.year_range, "Example: 2018-2022")
        self.make = _line(self.record.make)
        self.model = _line(self.record.model)
        self.body_style = _line(self.record.body_style, "SUV, pickup, sedan...")
        self.color = _line(self.record.color)
        self.plate = _line(self.record.plate)
        self.plate_state = _line(self.record.plate_state)
        self.vin = _line(self.record.vin)
        self.last_seen_location = SpellCheckedLineEdit(self.record.last_seen_location)
        self.last_seen_date = _date_line(self.record.last_seen_date)
        self.last_seen_time = _line(self.record.last_seen_time, "HH:MM")
        self.direction_of_travel = _line(self.record.direction_of_travel)
        self.information_source = _line(
            self.record.information_source,
            "Witness, video, recovered part, database query...",
        )
        self.linked_vehicle = _related_vehicle_combo(
            vehicles,
            self.record.linked_vehicle_id,
        )
        for label, widget in (
            ("Lead number", self.lead_number),
            ("Lead status", self.status),
            ("Confidence", self.confidence),
            ("Year / year range", self.year_range),
            ("Make", self.make),
            ("Model", self.model),
            ("Body style", self.body_style),
            ("Color", self.color),
            ("License plate", self.plate),
            ("Plate state", self.plate_state),
            ("VIN", self.vin),
            ("Last seen location", self.last_seen_location),
            ("Last seen date", self.last_seen_date),
            ("Last seen time", self.last_seen_time),
            ("Direction of travel", self.direction_of_travel),
            ("Information source", self.information_source),
            ("Linked confirmed vehicle", self.linked_vehicle),
        ):
            form.addRow(label, widget)
        self.root.addLayout(form)

        self.distinguishing_features = SpellCheckedTextEdit(
            self.record.distinguishing_features
        )
        self.observed_damage = SpellCheckedTextEdit(self.record.observed_damage)
        self.missing_parts = SpellCheckedTextEdit(self.record.missing_parts)
        self.elimination_reason = SpellCheckedTextEdit(self.record.elimination_reason)
        self.notes = SpellCheckedTextEdit(self.record.notes)
        for label, widget, placeholder in (
            (
                "Distinguishing features",
                self.distinguishing_features,
                "Decals, racks, accessories, modifications, unique marks...",
            ),
            (
                "Observed / expected damage",
                self.observed_damage,
                "Damage location, height, color transfer, or collision signature",
            ),
            (
                "Missing parts",
                self.missing_parts,
                "Lamp, trim, mirror, bumper, wheel cover, glass...",
            ),
            (
                "Elimination reason",
                self.elimination_reason,
                "Why this lead was excluded, if applicable",
            ),
            ("Notes", self.notes, "Checks completed, preservation steps, or follow-up"),
        ):
            widget.setPlaceholderText(placeholder)
            widget.setMaximumHeight(95)
            self.root.addWidget(QLabel(label))
            self.root.addWidget(widget)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.lead_number.text().strip():
            QMessageBox.warning(
                self,
                "Lead number required",
                "Enter a vehicle lead number such as HRV-1.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> HitRunVehicleLead:
        for attribute in (
            "lead_number",
            "year_range",
            "make",
            "model",
            "body_style",
            "color",
            "plate",
            "plate_state",
            "vin",
            "last_seen_location",
            "last_seen_time",
            "direction_of_travel",
            "information_source",
        ):
            setattr(self.record, attribute, getattr(self, attribute).text().strip())
        self.record.status = self.status.currentText()
        self.record.confidence = self.confidence.currentText()
        self.record.last_seen_date = normalize_date_for_storage(self.last_seen_date.text())
        self.record.linked_vehicle_id = self.linked_vehicle.currentData()
        self.record.distinguishing_features = (
            self.distinguishing_features.toPlainText().strip()
        )
        self.record.observed_damage = self.observed_damage.toPlainText().strip()
        self.record.missing_parts = self.missing_parts.toPlainText().strip()
        self.record.elimination_reason = self.elimination_reason.toPlainText().strip()
        self.record.notes = self.notes.toPlainText().strip()
        return self.record


class HitRunPersonLeadDialog(RecordDialog):
    def __init__(
        self,
        case_id: str,
        people: list[Person],
        vehicle_leads: list[HitRunVehicleLead],
        record: HitRunPersonLead | None = None,
        parent=None,
    ):
        super().__init__("Edit Person Lead / Possible Suspect" if record else "Add Person Lead / Possible Suspect", parent)
        self.record = record or HitRunPersonLead(id="", case_id=case_id)
        self.resize(780, 820)

        tabs = QTabWidget()
        identity = QWidget()
        identity_form = QFormLayout(identity)
        self.lead_number = _line(self.record.lead_number, "HRP-1")
        self.status = _combo(HIT_RUN_LEAD_STATUSES, self.record.status)
        self.confidence = _combo(HIT_RUN_CONFIDENCE_LEVELS, self.record.confidence)
        self.first_name = _line(self.record.first_name)
        self.middle_name = _line(self.record.middle_name)
        self.last_name = _line(self.record.last_name)
        self.alias = _line(self.record.alias)
        self.sex = _line(self.record.sex)
        self.race = _line(self.record.race)
        self.estimated_age = _line(self.record.estimated_age)
        self.height_value = _line(self.record.height)
        self.weight_build = _line(self.record.weight_build, "Weight or build")
        self.hair = _line(self.record.hair)
        self.eyes = _line(self.record.eyes)
        self.facial_hair = _line(self.record.facial_hair)
        self.clothing = _line(self.record.clothing)
        for label, widget in (
            ("Lead number", self.lead_number),
            ("Lead status", self.status),
            ("Confidence", self.confidence),
            ("First name", self.first_name),
            ("Middle name", self.middle_name),
            ("Last name", self.last_name),
            ("Alias / nickname", self.alias),
            ("Sex", self.sex),
            ("Race", self.race),
            ("Estimated age", self.estimated_age),
            ("Height", self.height_value),
            ("Weight / build", self.weight_build),
            ("Hair", self.hair),
            ("Eyes", self.eyes),
            ("Facial hair", self.facial_hair),
            ("Clothing", self.clothing),
        ):
            identity_form.addRow(label, widget)
        tabs.addTab(identity, "Identity / Description")

        contact = QWidget()
        contact_form = QFormLayout(contact)
        self.address = SpellCheckedLineEdit(self.record.address)
        self.city = _line(self.record.city)
        self.state = _line(self.record.state)
        self.zip_code = _line(self.record.zip_code)
        self.cell_phone = _line(self.record.cell_phone)
        self.home_phone = _line(self.record.home_phone)
        self.work_phone = _line(self.record.work_phone)
        self.email = _line(self.record.email)
        self.driver_license_number = _line(self.record.driver_license_number)
        self.driver_license_state = _line(self.record.driver_license_state)
        self.relationship_to_vehicle = _line(self.record.relationship_to_vehicle)
        self.vehicle_lead = _related_hit_run_vehicle_lead_combo(
            vehicle_leads,
            self.record.vehicle_lead_id,
        )
        self.linked_person = _related_person_combo(
            people,
            self.record.linked_person_id,
            "No confirmed person linked",
        )
        for label, widget in (
            ("Street address", self.address),
            ("City", self.city),
            ("State", self.state),
            ("ZIP code", self.zip_code),
            ("Cell phone", self.cell_phone),
            ("Home phone", self.home_phone),
            ("Work phone", self.work_phone),
            ("Email", self.email),
            ("Driver license number", self.driver_license_number),
            ("Driver license state", self.driver_license_state),
            ("Relationship to vehicle", self.relationship_to_vehicle),
            ("Associated vehicle lead", self.vehicle_lead),
            ("Linked confirmed person", self.linked_person),
        ):
            contact_form.addRow(label, widget)
        tabs.addTab(contact, "Contact / Associations")
        self.root.addWidget(tabs)

        self.reason_for_lead = SpellCheckedTextEdit(self.record.reason_for_lead)
        self.information_source = SpellCheckedTextEdit(self.record.information_source)
        self.follow_up = SpellCheckedTextEdit(self.record.follow_up)
        self.elimination_reason = SpellCheckedTextEdit(self.record.elimination_reason)
        for label, widget, placeholder in (
            (
                "Reason for lead / possible suspect",
                self.reason_for_lead,
                "Connection to the event, vehicle, location, or evidence",
            ),
            (
                "Information source",
                self.information_source,
                "Witness, video, records, tip, registered owner, other source",
            ),
            ("Follow-up", self.follow_up, "Completed and pending investigative steps"),
            (
                "Elimination reason",
                self.elimination_reason,
                "Why this person was excluded, if applicable",
            ),
        ):
            widget.setPlaceholderText(placeholder)
            widget.setMaximumHeight(100)
            self.root.addWidget(QLabel(label))
            self.root.addWidget(widget)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.lead_number.text().strip():
            QMessageBox.warning(
                self,
                "Lead number required",
                "Enter a person lead number such as HRP-1.",
            )
            return
        if not any(
            (
                self.first_name.text().strip(),
                self.last_name.text().strip(),
                self.alias.text().strip(),
                self.reason_for_lead.toPlainText().strip(),
            )
        ):
            QMessageBox.warning(
                self,
                "Person lead description required",
                "Enter a name, alias, or reason for the lead.",
            )
            return
        super()._validate_and_accept()

    def result_record(self) -> HitRunPersonLead:
        for attribute in (
            "lead_number",
            "first_name",
            "middle_name",
            "last_name",
            "alias",
            "sex",
            "race",
            "estimated_age",
            "weight_build",
            "hair",
            "eyes",
            "facial_hair",
            "clothing",
            "address",
            "city",
            "state",
            "zip_code",
            "cell_phone",
            "home_phone",
            "work_phone",
            "email",
            "driver_license_number",
            "driver_license_state",
            "relationship_to_vehicle",
        ):
            setattr(self.record, attribute, getattr(self, attribute).text().strip())
        self.record.height = self.height_value.text().strip()
        self.record.status = self.status.currentText()
        self.record.confidence = self.confidence.currentText()
        self.record.vehicle_lead_id = self.vehicle_lead.currentData()
        self.record.linked_person_id = self.linked_person.currentData()
        self.record.reason_for_lead = self.reason_for_lead.toPlainText().strip()
        self.record.information_source = self.information_source.toPlainText().strip()
        self.record.follow_up = self.follow_up.toPlainText().strip()
        self.record.elimination_reason = self.elimination_reason.toPlainText().strip()
        return self.record


class ContactRelationshipDialog(RecordDialog):
    CONTACT_TYPES = (
        "Next of Kin", "Family / Contact", "Medical", "Attorney", "Insurance",
        "Employer", "School", "Witness Contact", "Other",
    )

    def __init__(
        self, case_id: str, people: list[Person],
        contact: ContactRelationship | None = None, parent=None,
    ):
        super().__init__("Edit Contact" if contact else "Add Contact", parent)
        self.contact = contact or ContactRelationship(id="", case_id=case_id)
        form = QFormLayout()
        self.contact_type = _combo(self.CONTACT_TYPES, self.contact.contact_type, editable=True)
        self.subject_person = _related_person_combo(
            people,
            self.contact.subject_person_id,
            "Select the person this contact belongs to",
        )
        self.contact_person = _related_person_combo(people, self.contact.contact_person_id, "Not a person already entered")
        self.contact_name = _line(self.contact.contact_name)
        self.organization = _line(self.contact.organization)
        self.cell_phone = _line(self.contact.cell_phone)
        self.home_phone = _line(self.contact.home_phone)
        self.work_phone = _line(self.contact.work_phone)
        self.email = _line(self.contact.email)
        self.address = _line(self.contact.address)
        self.city = _line(self.contact.city)
        self.state = _line(self.contact.state)
        form.addRow("Contact type", self.contact_type)
        form.addRow("Contact for person", self.subject_person)
        form.addRow("Existing person as contact", self.contact_person)
        form.addRow("Contact name", self.contact_name)
        form.addRow("Organization", self.organization)
        form.addRow("Cell phone", self.cell_phone)
        form.addRow("Home phone", self.home_phone)
        form.addRow("Work phone", self.work_phone)
        form.addRow("Email", self.email)
        form.addRow("Address", self.address)
        form.addRow("City", self.city)
        form.addRow("State", self.state)
        self.root.addLayout(form)
        self.notes = SpellCheckedTextEdit(self.contact.notes)
        self.root.addWidget(QLabel("Notes / relationship"))
        self.root.addWidget(self.notes, 1)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.subject_person.currentData():
            QMessageBox.warning(
                self,
                "Person required",
                "Select the person this contact belongs to.",
            )
            return
        if not (self.contact_name.text().strip() or self.contact_person.currentData()):
            QMessageBox.warning(self, "Contact required", "Enter a contact name or select an existing person.")
            return
        super()._validate_and_accept()

    def result_record(self) -> ContactRelationship:
        self.contact.contact_type = self.contact_type.currentText().strip()
        self.contact.subject_person_id = self.subject_person.currentData()
        self.contact.vehicle_id = None
        self.contact.contact_person_id = self.contact_person.currentData()
        for attribute in (
            "contact_name", "organization", "cell_phone", "home_phone",
            "work_phone", "email", "address", "city", "state",
        ):
            setattr(self.contact, attribute, getattr(self, attribute).text().strip())
        self.contact.notes = self.notes.toPlainText().strip()
        return self.contact


class VRUAnalysisDialog(RecordDialog):
    def __init__(
        self, case_id: str, people: list[Person], vehicles: list[Vehicle],
        analysis: VRUAnalysis | None = None, parent=None,
    ):
        super().__init__("Edit VRU Analysis" if analysis else "Add VRU Analysis", parent)
        self.analysis = analysis or VRUAnalysis(id="", case_id=case_id)
        self.resize(820, 720)
        tabs = QTabWidget()

        subject = QWidget()
        form = QFormLayout(subject)
        self.person_id = _related_person_combo(people, self.analysis.person_id, "No VRU selected")
        self.vehicle_id = _related_vehicle_combo(vehicles, self.analysis.vehicle_id)
        form.addRow("Pedestrian / bicyclist", self.person_id)
        form.addRow("Involved vehicle", self.vehicle_id)
        for attribute, label in (
            ("upper_clothing", "Upper clothing"), ("lower_clothing", "Lower clothing"),
            ("roadway_position", "Roadway position"), ("movement_at_impact", "Movement at impact"),
            ("projection_profile", "Projection profile"), ("impact_location_on_vehicle", "Impact location on vehicle"),
        ):
            setattr(self, attribute, _line(getattr(self.analysis, attribute)))
            form.addRow(label, getattr(self, attribute))
        projection_group, self.projection_boxes = _checkbox_group(
            "Projection classifications",
            VRU_PROJECTION_OPTIONS,
            self.analysis.projection_classifications,
            columns=3,
        )
        form.addRow(projection_group)
        self.sightlines = SpellCheckedTextEdit(self.analysis.sightlines)
        self.driver_thought_process = SpellCheckedTextEdit(self.analysis.driver_thought_process)
        self.sightlines.setMaximumHeight(95)
        self.driver_thought_process.setMaximumHeight(95)
        form.addRow("Sightlines", self.sightlines)
        form.addRow("Driver thought process", self.driver_thought_process)
        tabs.addTab(subject, "Subject / Scene")

        motion = QWidget()
        motion_form = QFormLayout(motion)
        for attribute, label in (
            ("vehicle_approach_speed", "Vehicle approach speed"), ("vehicle_direction", "Vehicle direction"),
            ("vru_approach_speed", "VRU approach speed"), ("vru_direction", "VRU direction"),
            ("person_throw_distance", "Person throw distance"), ("bicycle_throw_distance", "Bicycle throw distance"),
        ):
            setattr(self, attribute, _line(getattr(self.analysis, attribute)))
            motion_form.addRow(label, getattr(self, attribute))
        self.driver_impairment = _combo(YES_NO_UNKNOWN, self.analysis.driver_impairment)
        self.vru_impairment = _combo(YES_NO_UNKNOWN, self.analysis.vru_impairment)
        self.driver_sleep_information = SpellCheckedTextEdit(
            self.analysis.driver_sleep_information
        )
        self.vru_impairment_notes = SpellCheckedTextEdit(self.analysis.vru_impairment_notes)
        self.driver_sleep_information.setMaximumHeight(95)
        self.vru_impairment_notes.setMaximumHeight(95)
        motion_form.addRow("Driver impairment", self.driver_impairment)
        motion_form.addRow("Driver sleep information", self.driver_sleep_information)
        motion_form.addRow("VRU impairment", self.vru_impairment)
        motion_form.addRow("VRU impairment notes", self.vru_impairment_notes)
        tabs.addTab(motion, "Motion / Condition")

        night = QWidget()
        night_form = QFormLayout(night)
        self.light_meter_used = QCheckBox("Light meter used")
        self.light_meter_used.setChecked(bool(self.analysis.light_meter_used))
        self.light_board_used = QCheckBox("Light board used")
        self.light_board_used.setChecked(bool(self.analysis.light_board_used))
        night_form.addRow(self.light_meter_used)
        night_form.addRow(self.light_board_used)
        tabs.addTab(night, "Night Visibility")

        notes_tab = QWidget()
        notes_layout = QVBoxLayout(notes_tab)
        self.notes = SpellCheckedTextEdit(self.analysis.notes)
        notes_layout.addWidget(QLabel("Analysis notes"))
        notes_layout.addWidget(self.notes, 1)
        tabs.addTab(notes_tab, "Notes")
        self.root.addWidget(tabs, 1)
        self.finish_layout()

    def _validate_and_accept(self) -> None:
        if not self.person_id.currentData():
            QMessageBox.warning(self, "VRU required", "Select the pedestrian or bicyclist being analyzed.")
            return
        super()._validate_and_accept()

    def result_record(self) -> VRUAnalysis:
        self.analysis.person_id = self.person_id.currentData()
        self.analysis.vehicle_id = self.vehicle_id.currentData()
        combo_fields = ("driver_impairment", "vru_impairment")
        bool_fields = ("light_meter_used", "light_board_used")
        memo_fields = (
            "sightlines", "driver_thought_process", "driver_sleep_information",
            "vru_impairment_notes", "notes",
        )
        retired_fields = {
            "night_test_parameters", "detection_distance", "distance_adjustment",
            "result_67_percent", "result_15_percentile", "prt_base", "prt_expected",
            "prt_sun", "prt_offset", "prt_adjustment", "prt_total",
            "prt_justification", "prt_factors",
        }
        omitted = {
            "id", "case_id", "person_id", "vehicle_id", "created_at", "updated_at",
            "projection_classifications", *combo_fields, *bool_fields, *memo_fields,
            *retired_fields,
        }
        for attribute in self.analysis.__dataclass_fields__:
            if attribute not in omitted:
                setattr(self.analysis, attribute, getattr(self, attribute).text().strip())
        for attribute in combo_fields:
            setattr(self.analysis, attribute, getattr(self, attribute).currentText())
        for attribute in memo_fields:
            setattr(self.analysis, attribute, getattr(self, attribute).toPlainText().strip())
        for attribute in bool_fields:
            setattr(self.analysis, attribute, getattr(self, attribute).isChecked())
        self.analysis.projection_classifications = _selection_text(self.projection_boxes)
        return self.analysis
