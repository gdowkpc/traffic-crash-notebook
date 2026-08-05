from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication

from traffic_crash_notebook.spellcheck import SpellCheckService
from traffic_crash_notebook.ui.spellcheck_text_edit import (
    SpellCheckedLineEdit,
    SpellCheckedTextEdit,
)


class SpellCheckServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dictionary_path = Path(self.temp.name) / "personal_dictionary.txt"
        self.service = SpellCheckService(self.dictionary_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_detects_typo_and_offers_likely_correction(self):
        self.assertFalse(self.service.is_misspelled("accident"))
        self.assertTrue(self.service.is_misspelled("accidnet"))
        self.assertIn("accident", self.service.suggestions("accidnet"))

    def test_avoids_noise_for_acronyms_codes_and_domain_terms(self):
        self.assertFalse(self.service.is_misspelled("FARO"))
        self.assertFalse(self.service.is_misspelled("V-1"))
        self.assertFalse(self.service.is_misspelled("crashworthiness"))
        self.assertFalse(self.service.is_misspelled("centerline"))
        self.assertFalse(self.service.is_misspelled("yawmark"))

    def test_personal_dictionary_is_saved_and_reloaded(self):
        self.assertTrue(self.service.is_misspelled("reconword"))
        self.assertTrue(self.service.add_to_personal_dictionary("reconword"))
        self.assertFalse(self.service.is_misspelled("reconword"))
        self.assertEqual(self.dictionary_path.read_text(encoding="utf-8"), "reconword\n")

        reloaded = SpellCheckService(self.dictionary_path)
        self.assertFalse(reloaded.is_misspelled("reconword"))

    def test_session_ignore_is_not_written_to_personal_dictionary(self):
        self.assertTrue(self.service.is_misspelled("temporaryword"))
        self.assertTrue(self.service.ignore_word("temporaryword"))
        self.assertFalse(self.service.is_misspelled("temporaryword"))
        self.assertFalse(self.dictionary_path.exists())

class SpellCheckedTextEditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.service = SpellCheckService(Path(self.temp.name) / "personal_dictionary.txt")
        self.editor = SpellCheckedTextEdit(spell_service=self.service)

    def tearDown(self) -> None:
        self.editor.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_misspelled_word_is_underlined_in_real_time(self):
        self.editor.setPlainText("The accidnet was documented.")
        self.app.processEvents()

        formats = self.editor.document().firstBlock().layout().formats()
        self.assertTrue(any(
            item.format.underlineStyle()
            == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
            for item in formats
        ))

    def test_replacement_preserves_the_rest_of_the_text(self):
        self.editor.setPlainText("The accidnet was documented.")
        cursor = self.editor.textCursor()
        cursor.setPosition(6)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        self.editor._replace_word(cursor, "accident")
        self.assertEqual(self.editor.toPlainText(), "The accident was documented.")

    def test_single_line_editor_flattens_line_breaks_and_tabs_change_focus(self):
        editor = SpellCheckedLineEdit(
            "123 Example Street\nApartment 4",
            spell_service=self.service,
        )
        try:
            self.assertEqual(editor.text(), "123 Example Street Apartment 4")
            self.assertTrue(editor.tabChangesFocus())
            self.assertEqual(editor.minimumHeight(), editor.maximumHeight())
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
