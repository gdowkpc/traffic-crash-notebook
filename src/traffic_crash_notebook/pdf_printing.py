from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter


MAX_PRINT_RENDER_DPI = 300
MAX_PRINT_RENDER_PIXELS = 16_000_000


def selected_pdf_page_indexes(
    printer: QPrinter,
    page_count: int,
    *,
    current_page: int = 0,
) -> list[int]:
    """Return zero-based PDF page indexes selected in the print dialog."""
    if page_count < 1:
        return []

    print_range = printer.printRange()
    if print_range in {
        QPrinter.PrintRange.CurrentPage,
        QPrinter.PrintRange.Selection,
    }:
        page_indexes = [max(0, min(current_page, page_count - 1))]
    elif print_range == QPrinter.PrintRange.PageRange:
        first_page = max(1, printer.fromPage() or 1)
        last_page = min(page_count, printer.toPage() or page_count)
        page_indexes = (
            list(range(first_page - 1, last_page))
            if first_page <= last_page
            else []
        )
    else:
        page_indexes = list(range(page_count))

    if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
        page_indexes.reverse()
    return page_indexes


def _render_size(
    document: QPdfDocument,
    page_index: int,
    printer: QPrinter,
) -> QSize:
    page_size = document.pagePointSize(page_index)
    if page_size.width() <= 0 or page_size.height() <= 0:
        raise RuntimeError(f"PDF page {page_index + 1} has an invalid size.")

    printer_resolution = printer.resolution() or MAX_PRINT_RENDER_DPI
    render_dpi = max(72, min(MAX_PRINT_RENDER_DPI, printer_resolution))
    width = max(1, round(page_size.width() * render_dpi / 72))
    height = max(1, round(page_size.height() * render_dpi / 72))
    pixel_count = width * height
    if pixel_count > MAX_PRINT_RENDER_PIXELS:
        reduction = math.sqrt(MAX_PRINT_RENDER_PIXELS / pixel_count)
        width = max(1, round(width * reduction))
        height = max(1, round(height * reduction))
    return QSize(width, height)


def print_pdf_document(
    document: QPdfDocument,
    printer: QPrinter,
    page_indexes: Sequence[int],
) -> int:
    """Render selected PDF pages to a configured Qt printer."""
    pages = list(page_indexes)
    if not pages:
        raise RuntimeError("No PDF pages were selected for printing.")
    if any(page < 0 or page >= document.pageCount() for page in pages):
        raise RuntimeError("The requested print range is outside the PDF.")

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Windows could not start the selected print job.")
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    try:
        for output_index, page_index in enumerate(pages):
            if output_index and not printer.newPage():
                raise RuntimeError("Windows could not start the next printed page.")

            page_size = document.pagePointSize(page_index)
            image = document.render(
                page_index,
                _render_size(document, page_index, printer),
            )
            if image.isNull():
                raise RuntimeError(f"PDF page {page_index + 1} could not be rendered.")

            printable = printer.pageRect(QPrinter.Unit.DevicePixel)
            if printable.width() <= 0 or printable.height() <= 0:
                raise RuntimeError("The selected printer has no printable page area.")
            scale = min(
                printable.width() / page_size.width(),
                printable.height() / page_size.height(),
            )
            target_width = page_size.width() * scale
            target_height = page_size.height() * scale
            target = QRectF(
                printable.x() + (printable.width() - target_width) / 2,
                printable.y() + (printable.height() - target_height) / 2,
                target_width,
                target_height,
            )
            painter.drawImage(target, image)
    finally:
        if painter.isActive():
            painter.end()
    return len(pages)
