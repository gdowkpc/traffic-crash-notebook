from __future__ import annotations

from math import ceil

from PySide6.QtCore import QSize
from PySide6.QtGui import QTextDocument, QTextOption
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem


class CaseListDelegate(QStyledItemDelegate):
    """Reserve enough height for wrapped case details in the narrow sidebar."""

    def sizeHint(self, option, index) -> QSize:
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        # Allow for the list frame, item padding, and selection inset. Using the
        # viewport also accounts for the vertical scrollbar when it appears.
        width = max(1, self.parent().viewport().width() - 32)
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(styled_option.font)
        text_option = document.defaultTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(text_option)
        document.setPlainText(styled_option.text)
        document.setTextWidth(width)
        return QSize(0, ceil(document.size().height()) + 24)
