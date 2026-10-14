from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..date_format import format_date_for_display, parse_date
from ..models import CaseTaskSummary
from ..repository import CaseRepository
from .dialogs import TaskDialog


class AllCaseTasksDialog(QDialog):
    task_changed = Signal()

    def __init__(self, repository: CaseRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.entries: list[CaseTaskSummary] = []
        self.visible_entries: list[CaseTaskSummary] = []
        self.load_failed = False
        self.selected_task: tuple[str, str] | None = None
        self.setWindowTitle("All Case Tasks")
        self.resize(1120, 650)
        layout = QVBoxLayout(self)
        guidance = QLabel(
            "Outstanding tasks from your saved cases, ordered by due date. "
            "Double-click a task to open its case, or select Edit Task to update it."
        )
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(self.summary_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search case numbers, locations, tasks, or notes")
        layout.addWidget(self.search)

        filters = QGridLayout()
        self.case_filter = QComboBox()
        self.case_filter.setMinimumContentsLength(18)
        self.case_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.category_filter = QComboBox()
        self.category_filter.setMinimumContentsLength(12)
        self.category_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Open and Waiting", "Open", "Waiting"])
        self.due_filter = QComboBox()
        self.due_filter.addItems(["All due dates", "Overdue", "Due next 7 days", "No date / check date"])
        for column, (label, widget) in enumerate([
            ("Case", self.case_filter), ("Category", self.category_filter),
            ("Status", self.status_filter), ("Due", self.due_filter),
        ]):
            filters.addWidget(QLabel(label), 0, column)
            filters.addWidget(widget, 1, column)
        layout.addLayout(filters)

        controls = QHBoxLayout()
        self.include_closed = QCheckBox("Include closed cases")
        controls.addWidget(self.include_closed)
        controls.addStretch()
        self.refresh_button = QPushButton("Refresh")
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Due status", "Case", "Case status", "Task", "Due", "Status", "Category", "Notes",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate([110, 120, 130, 260, 110, 85, 120]):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        buttons = QHBoxLayout()
        self.open_case_button = QPushButton("Open Case")
        self.edit_task_button = QPushButton("Edit Task")
        buttons.addWidget(self.open_case_button)
        buttons.addWidget(self.edit_task_button)
        buttons.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        # Enter should not accidentally open the highlighted case while filtering.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)

        self.search.textChanged.connect(self.apply_filters)
        for combo in (self.case_filter, self.category_filter, self.status_filter, self.due_filter):
            combo.currentIndexChanged.connect(self.apply_filters)
        self.include_closed.toggled.connect(self.refresh)
        self.refresh_button.clicked.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(self.open_selected_case)
        self.open_case_button.clicked.connect(self.open_selected_case)
        self.edit_task_button.clicked.connect(self.edit_selected_task)
        self.refresh()

    def refresh(self, *_args) -> None:
        try:
            entries = self.repository.list_outstanding_tasks(
                include_closed=self.include_closed.isChecked()
            )
            cases = self.repository.list_cases()
        except (OSError, sqlite3.Error) as error:
            # Do not leave a stale list looking like a current workload summary.
            self.entries = []
            self.load_failed = True
            self.apply_filters()
            QMessageBox.critical(self, "Tasks could not be loaded", str(error))
            return
        self.entries = entries
        self.load_failed = False
        selected_case = self.case_filter.currentData()
        selected_category = self.category_filter.currentData()
        self.case_filter.blockSignals(True)
        self.category_filter.blockSignals(True)
        self.case_filter.clear()
        self.case_filter.addItem("All cases", None)
        for case in sorted(cases, key=lambda c: (c.case_number.casefold(), c.location.casefold(), c.id)):
            if case.status == "Closed" and not self.include_closed.isChecked():
                continue
            label = case.case_number or "Untitled Case"
            if case.location:
                label += f" - {case.location}"
            self.case_filter.addItem(label, case.id)
        self.case_filter.setCurrentIndex(max(0, self.case_filter.findData(selected_case)))
        self.category_filter.clear()
        self.category_filter.addItem("All categories", None)
        for category in sorted({entry.task.category for entry in entries}, key=str.casefold):
            self.category_filter.addItem(category or "Uncategorized", category)
        self.category_filter.setCurrentIndex(max(0, self.category_filter.findData(selected_category)))
        self.case_filter.blockSignals(False)
        self.category_filter.blockSignals(False)
        self.apply_filters()

    def apply_filters(self, *_args) -> None:
        today = date.today()
        query = self.search.text().strip().casefold()
        case_id = self.case_filter.currentData()
        category = self.category_filter.currentData()
        status = self.status_filter.currentText()
        due_filter = self.due_filter.currentText()
        entries = []
        for entry in self.entries:
            task = entry.task
            due = parse_date(task.due_date)
            if case_id is not None and task.case_id != case_id:
                continue
            if category is not None and task.category != category:
                continue
            if status != "Open and Waiting" and task.status != status:
                continue
            if due_filter == "Overdue" and (due is None or due >= today):
                continue
            if due_filter == "Due next 7 days" and (due is None or not today <= due <= today + timedelta(days=7)):
                continue
            if due_filter == "No date / check date" and due is not None:
                continue
            haystack = " ".join([
                entry.case_number, entry.case_location, entry.case_status,
                task.description, task.notes, task.category, task.status,
            ]).casefold()
            if query and query not in haystack:
                continue
            entries.append(entry)

        def sort_key(entry: CaseTaskSummary):
            due = parse_date(entry.task.due_date)
            return (
                due or date.max, due is None, entry.case_number.casefold(),
                entry.task.sort_order, entry.task.created_at, entry.task.id,
            )

        self.visible_entries = sorted(entries, key=sort_key)
        selected = self._selected_entry()
        selected_id = selected.task.id if selected else None
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.visible_entries))
        overdue_count = 0
        waiting_count = 0
        for row, entry in enumerate(self.visible_entries):
            task = entry.task
            due = parse_date(task.due_date)
            overdue = due is not None and due < today
            overdue_count += int(overdue)
            waiting_count += int(task.status == "Waiting")
            due_status = (
                "Overdue" if overdue else "Due today" if due == today else
                "Upcoming" if due else "Check date" if task.due_date.strip() else "No date"
            )
            values = [
                due_status, entry.case_number or "Untitled Case", entry.case_status,
                task.description, format_date_for_display(task.due_date) or "No date",
                task.status, task.category or "Uncategorized", task.notes,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, (task.case_id, task.id))
                    if overdue:
                        item.setForeground(QColor("#a32626"))
                self.table.setItem(row, column, item)
            if task.id == selected_id:
                self.table.selectRow(row)
        self.summary_label.setText(
            f"{len(entries)} outstanding  ·  {overdue_count} overdue  ·  {waiting_count} waiting"
        )
        self.result_label.setText(
            f"Showing {len(entries)} of {len(self.entries)} outstanding tasks. Summary reflects current filters."
            if entries else
            "No outstanding tasks match these filters." if self.entries else
            "No outstanding tasks in the included cases. Add tasks from a case's Tasks tab."
        )
        if self.load_failed:
            self.summary_label.setText("Tasks unavailable")
            self.result_label.setText("Tasks could not be loaded. Reconnect the data drive and choose Refresh.")
        self._update_buttons()

    def _selected_entry(self) -> CaseTaskSummary | None:
        # Resolve by saved IDs rather than display text or a changing filter index.
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        identity = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((entry for entry in self.entries
                     if (entry.task.case_id, entry.task.id) == identity), None)

    def _update_buttons(self) -> None:
        enabled = self._selected_entry() is not None
        self.open_case_button.setEnabled(enabled)
        self.edit_task_button.setEnabled(enabled)

    def open_selected_case(self, *_args) -> None:
        entry = self._selected_entry()
        if entry:
            self.selected_task = (entry.task.case_id, entry.task.id)
            self.accept()

    def edit_selected_task(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        try:
            task = self.repository.get_task(entry.task.id)
            if task is None:
                self.refresh()
                return
            dialog = TaskDialog(task.case_id, task, self)
            dialog.setWindowTitle(f"Edit Task - {entry.case_number or 'Untitled Case'}")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.repository.save_task(dialog.result_record())
        except (OSError, sqlite3.Error) as error:
            QMessageBox.critical(self, "Task could not be saved", str(error))
            return
        self.task_changed.emit()
        self.refresh()
