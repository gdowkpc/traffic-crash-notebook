from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from traffic_crash_notebook.pdf_printing import selected_pdf_page_indexes


class PdfPrintingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_page_range_current_page_and_reverse_order_are_honored(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setFromTo(2, 4)
        self.assertEqual(
            selected_pdf_page_indexes(printer, 5, current_page=0),
            [1, 2, 3],
        )

        printer.setPageOrder(QPrinter.PageOrder.LastPageFirst)
        self.assertEqual(
            selected_pdf_page_indexes(printer, 5, current_page=0),
            [3, 2, 1],
        )

        printer.setPageOrder(QPrinter.PageOrder.FirstPageFirst)
        printer.setPrintRange(QPrinter.PrintRange.CurrentPage)
        self.assertEqual(
            selected_pdf_page_indexes(printer, 5, current_page=3),
            [3],
        )
