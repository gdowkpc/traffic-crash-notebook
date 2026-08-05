from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QStyle, QTextEdit

from ..spellcheck import WORD_PATTERN, SpellCheckService, default_spell_check_service


class SpellCheckHighlighter(QSyntaxHighlighter):
    def __init__(self, document, service: SpellCheckService) -> None:
        super().__init__(document)
        self.service = service
        self.misspelled_format = QTextCharFormat()
        self.misspelled_format.setUnderlineColor(QColor("#c62828"))
        self.misspelled_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline
        )
        self.service.changed.connect(self.rehighlight)

    def highlightBlock(self, text: str) -> None:
        for match in WORD_PATTERN.finditer(text):
            if self.service.is_misspelled(match.group(0)):
                self.setFormat(match.start(), len(match.group(0)), self.misspelled_format)


class SpellCheckedTextEdit(QTextEdit):
    """QTextEdit with live offline spell-check and correction actions."""

    def __init__(
        self,
        text: str = "",
        parent=None,
        *,
        spell_service: SpellCheckService | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.spell_service = spell_service or default_spell_check_service()
        self.spell_highlighter = SpellCheckHighlighter(self.document(), self.spell_service)
        self.setToolTip(
            "Misspelled words are underlined. Right-click an underlined word for corrections."
        )

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.createStandardContextMenu(event.pos())
        cursor = self.cursorForPosition(event.pos())
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText()

        if word and self.spell_service.is_misspelled(word):
            first_action = menu.actions()[0] if menu.actions() else None
            heading = menu.insertAction(first_action, "Spelling suggestions")
            heading.setEnabled(False)
            suggestions = self.spell_service.suggestions(word)
            if suggestions:
                for suggestion in suggestions:
                    action = menu.insertAction(first_action, suggestion)
                    action.triggered.connect(
                        lambda checked=False, replacement=suggestion, selected_cursor=QTextCursor(cursor):
                        self._replace_word(selected_cursor, replacement)
                    )
            else:
                no_suggestions = menu.insertAction(first_action, "No suggestions")
                no_suggestions.setEnabled(False)

            menu.insertSeparator(first_action)
            add_action = menu.insertAction(
                first_action,
                f'Add "{word}" to personal dictionary',
            )
            add_action.triggered.connect(
                lambda checked=False, selected_word=word:
                self.spell_service.add_to_personal_dictionary(selected_word)
            )
            ignore_action = menu.insertAction(
                first_action,
                f'Ignore "{word}" for this session',
            )
            ignore_action.triggered.connect(
                lambda checked=False, selected_word=word:
                self.spell_service.ignore_word(selected_word)
            )
            menu.insertSeparator(first_action)

        menu.exec(event.globalPos())
        menu.deleteLater()

    def _replace_word(self, cursor: QTextCursor, replacement: str) -> None:
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        self.setTextCursor(cursor)


class SpellCheckedLineEdit(SpellCheckedTextEdit):
    """Single-line, tab-navigable text control with live offline spell-check."""

    def __init__(
        self,
        text: str = "",
        parent=None,
        *,
        spell_service: SpellCheckService | None = None,
    ) -> None:
        super().__init__(
            self._single_line(text),
            parent,
            spell_service=spell_service,
        )
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        frame_width = self.style().pixelMetric(
            QStyle.PixelMetric.PM_DefaultFrameWidth,
            None,
            self,
        )
        document_margin = round(self.document().documentMargin())
        self.setFixedHeight(
            self.fontMetrics().height() + (2 * document_margin) + (2 * frame_width)
        )

    @staticmethod
    def _single_line(text: str) -> str:
        return " ".join(
            str(text).replace("\r\n", "\n").replace("\r", "\n").splitlines()
        )

    def text(self) -> str:
        return self.toPlainText()

    def setPlainText(self, text: str) -> None:
        super().setPlainText(self._single_line(text))

    def insertPlainText(self, text: str) -> None:
        super().insertPlainText(self._single_line(text))

    def insertFromMimeData(self, source) -> None:
        cursor = self.textCursor()
        cursor.insertText(self._single_line(source.text()))
        self.setTextCursor(cursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.focusNextChild()
            event.accept()
            return
        super().keyPressEvent(event)
