from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPageLayout, QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..models import TowedVehicleSummary
from ..pdf_printing import print_pdf_document, selected_pdf_page_indexes
from ..reports import RIVERGATE_REPORT_TITLE, TOWED_VEHICLE_HEADERS, export_rivergate_report_pdf, towed_vehicle_cells
from ..repository import CaseRepository


class RivergateReportDialog(QDialog):
    def __init__(self, repository: CaseRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.entries: list[TowedVehicleSummary] = []
        self.visible_entries: list[TowedVehicleSummary] = []
        self.selected_vehicle: tuple[str, str] | None = None
        self.load_failed = False
        self.setWindowTitle(RIVERGATE_REPORT_TITLE)
        self.resize(1140, 640)
        layout = QVBoxLayout(self)
        guidance = QLabel(
            "Vehicles marked Towed, with Rivergate in Towed to, and Released unchecked. "
            "Archived cases are included unless you uncheck the option below. "
            "Open a vehicle to review or update its release status."
        )
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(self.summary_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search cases, tow numbers, vehicles, plates, VINs, destinations, or investigators")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        controls = QHBoxLayout()
        self.include_closed = QCheckBox("Include archived cases")
        self.include_closed.setChecked(True)
        controls.addWidget(self.include_closed)
        controls.addStretch()
        self.refresh_button = QPushButton("Refresh")
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)
        self.table = QTableWidget(0, len(TOWED_VEHICLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TOWED_VEHICLE_HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate([140, 120, 200, 110, 165, 220, 130, 170]):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        buttons = QHBoxLayout()
        self.open_vehicle_button = QPushButton("Open Vehicle")
        self.export_button = QPushButton("Save PDF...")
        self.print_button = QPushButton("Print...")
        for button in (self.open_vehicle_button, self.export_button, self.print_button):
            buttons.addWidget(button)
        buttons.addStretch()
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.search.textChanged.connect(self.apply_filters)
        self.include_closed.toggled.connect(self.refresh)
        self.refresh_button.clicked.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(self.open_selected_vehicle)
        self.open_vehicle_button.clicked.connect(self.open_selected_vehicle)
        self.export_button.clicked.connect(self.save_pdf)
        self.print_button.clicked.connect(self.print_report)
        self.refresh()

    def refresh(self, *_args) -> bool:
        try:
            self.entries = self.repository.list_unreleased_towed_vehicles(
                include_closed=self.include_closed.isChecked(),
            )
        except (OSError, sqlite3.Error) as error:
            self.entries = []
            self.load_failed = True
            self.apply_filters()
            QMessageBox.critical(self, "Report could not be loaded", str(error))
            return False
        self.load_failed = False
        self.generated_at = datetime.now().astimezone()
        self.apply_filters()
        return True

    def apply_filters(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        selected = self._selected_identity()
        self.visible_entries = [entry for entry in self.entries
                                if query in " ".join(towed_vehicle_cells(entry)).casefold()]
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.visible_entries))
        for row, entry in enumerate(self.visible_entries):
            identity = (entry.vehicle.case_id, entry.vehicle.id)
            for column, value in enumerate(towed_vehicle_cells(entry)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, identity)
                self.table.setItem(row, column, item)
            if identity == selected:
                self.table.selectRow(row)
        self.table.resizeRowsToContents()
        self.summary_label.setText(f"{len(self.visible_entries)} unreleased vehicle(s)")
        self.result_label.setText(
            f"Showing {len(self.visible_entries)} of {len(self.entries)} vehicles. "
            "PDF and print use the current filters. Loaded "
            f"{self.generated_at.strftime('%m/%d/%Y %I:%M %p')}."
            if not self.load_failed else "Report could not be loaded. Reconnect the data drive and choose Refresh."
        )
        if not self.visible_entries and not self.load_failed:
            self.result_label.setText("No unreleased vehicles match this report. PDF and print use the current filters.")
        if self.load_failed:
            self.summary_label.setText("Report unavailable")
        self._update_buttons()

    def _selected_identity(self) -> tuple[str, str] | None:
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_buttons(self) -> None:
        self.open_vehicle_button.setEnabled(self._selected_identity() is not None and not self.load_failed)
        self.export_button.setEnabled(not self.load_failed)
        self.print_button.setEnabled(not self.load_failed)

    def open_selected_vehicle(self, *_args) -> None:
        identity = self._selected_identity()
        if identity is not None and not self.load_failed:
            self.selected_vehicle = identity
            self.accept()

    def _write_pdf(self, path: Path) -> None:
        export_rivergate_report_pdf(
            self.visible_entries, path, include_closed=self.include_closed.isChecked(),
            search=self.search.text(), generated_at=self.generated_at,
        )

    def save_pdf(self) -> None:
        if not self.refresh():
            return
        reports_directory = self.repository.database_path.parent / "Reports"
        try:
            reports_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, "Report folder unavailable", str(error))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Rivergate Report", str(reports_directory / "Rivergate_Unreleased_Vehicles.pdf"),
            "PDF files (*.pdf)",
        )
        if not path:
            return
        output = Path(path)
        if output.suffix.lower() != ".pdf":
            output = output.with_name(output.name + ".pdf")
        try:
            self._write_pdf(output)
        except Exception as error:
            QMessageBox.critical(self, "Report could not be saved", str(error))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output.resolve())))

    def print_report(self) -> None:
        if not self.refresh():
            return
        document = QPdfDocument(self)
        buffer = QBuffer(document)
        try:
            with tempfile.TemporaryDirectory(prefix="tcn-rivergate-") as directory:
                path = Path(directory) / "rivergate-report.pdf"
                self._write_pdf(path)
                buffer.setData(QByteArray(path.read_bytes()))
                if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                    raise RuntimeError("The report PDF could not be opened in memory.")
                document.load(buffer)
                if document.error() != QPdfDocument.Error.None_ or document.pageCount() < 1:
                    raise RuntimeError("The report PDF could not be opened for printing.")
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setDocName(RIVERGATE_REPORT_TITLE)
                printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
                printer.setPageOrientation(QPageLayout.Orientation.Landscape)
                dialog = QPrintDialog(printer, self)
                dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, True)
                dialog.setMinMax(1, document.pageCount())
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    print_pdf_document(document, printer, selected_pdf_page_indexes(printer, document.pageCount()))
                document.close()
        except Exception as error:
            QMessageBox.critical(self, "Report could not be printed", str(error))
        finally:
            document.close()
            buffer.close()
            document.deleteLater()
