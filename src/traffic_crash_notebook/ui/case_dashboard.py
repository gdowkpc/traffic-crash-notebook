from __future__ import annotations

import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ..repository import CaseRepository


class CaseDashboardDialog(QDialog):
    def __init__(self, repository: CaseRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.counts: dict[str, int] = {}
        self.setWindowTitle("Case Dashboard")
        self.resize(680, 510)
        layout = QVBoxLayout(self)
        title = QLabel("Cases by status")
        title.setStyleSheet("font-size: 21px; font-weight: 700; color: #18344a;")
        layout.addWidget(title)
        guidance = QLabel(
            "Archived cases are excluded. Counts include all other cases, "
            "regardless of the case-list filter or selected case."
        )
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 30px; font-weight: 700; color: #18344a;")
        layout.addWidget(self.total_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Status", "Cases", "Share of cases"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.refresh()

    def refresh(self) -> None:
        try:
            counts = self.repository.case_status_counts()
        except (OSError, sqlite3.Error) as error:
            self.counts = {}
            self.table.setRowCount(0)
            self.total_label.setText("Cases unavailable")
            self.result_label.setText("Counts could not be loaded. Reconnect the data drive and choose Refresh.")
            QMessageBox.critical(self, "Dashboard could not be loaded", str(error))
            return
        self.counts = counts
        total = sum(counts.values())
        self.total_label.setText(f"{total} case{'s' if total != 1 else ''}")
        self.table.setRowCount(0)
        self.table.setRowCount(len(counts))
        for row, (status, count) in enumerate(counts.items()):
            self.table.setItem(row, 0, QTableWidgetItem(status or "No status entered"))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, count_item)
            share = QProgressBar()
            share.setRange(0, max(1, total))
            share.setValue(count)
            share.setFormat(f"{count / total * 100 if total else 0:.1f}%")
            share.setStyleSheet(
                "QProgressBar { border: 1px solid #c9d2d9; border-radius: 3px; "
                "background: #eaf2f7; text-align: center; color: #172733; margin: 8px; }"
                "QProgressBar::chunk { background: #9ec6df; }"
            )
            self.table.setCellWidget(row, 2, share)
            self.table.setRowHeight(row, 44)
        self.result_label.setText(
            f"Updated {datetime.now().astimezone().strftime('%m/%d/%Y %I:%M %p')}."
            if total else "No cases to show. Archived cases are excluded."
        )
