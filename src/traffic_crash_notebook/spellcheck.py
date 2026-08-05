from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from spellchecker import SpellChecker

from .paths import data_directory


WORD_PATTERN = re.compile(
    r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*(?:-[A-Za-z]+(?:['\u2019][A-Za-z]+)*)*"
)

# Common crash-reconstruction and investigative terms that a general-purpose
# dictionary may not recognize. Acronyms written in all capitals are ignored
# automatically, so they do not need to be duplicated here.
DOMAIN_WORDS = {
    "airbag",
    "airbags",
    "bloodborne",
    "breathalyzer",
    "centerline",
    "crashworthiness",
    "deceleration",
    "drivetrain",
    "evidentiary",
    "gougemark",
    "gougemarks",
    "headlamp",
    "headlamps",
    "kinematics",
    "odometer",
    "photogrammetry",
    "postcrash",
    "postimpact",
    "precrash",
    "preimpact",
    "reconstructionist",
    "roadway",
    "scuffmark",
    "scuffmarks",
    "seatbelt",
    "seatbelts",
    "skidmark",
    "skidmarks",
    "speedometer",
    "tachograph",
    "taillamp",
    "taillamps",
    "toxicology",
    "towaway",
    "undercarriage",
    "underride",
    "understeer",
    "wheelbase",
    "wheelmark",
    "wheelmarks",
    "yawmark",
    "yawmarks",
}


def _match_case(replacement: str, original: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper() and original[1:].islower():
        return replacement.capitalize()
    return replacement


class SpellCheckService(QObject):
    """Shared offline English dictionary and personal-word storage."""

    changed = Signal()

    def __init__(
        self,
        personal_dictionary_path: str | Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.personal_dictionary_path = Path(
            personal_dictionary_path or (data_directory() / "personal_dictionary.txt")
        )
        self._checker = SpellChecker(language="en", distance=1)
        self._checker.word_frequency.load_words(DOMAIN_WORDS)
        self._personal_words: set[str] = set()
        self._ignored_words: set[str] = set()
        self._misspelling_cache: dict[str, bool] = {}
        self._load_personal_dictionary()

    def _load_personal_dictionary(self) -> None:
        if not self.personal_dictionary_path.is_file():
            return
        try:
            words = {
                word
                for line in self.personal_dictionary_path.read_text(encoding="utf-8").splitlines()
                if (word := self._dictionary_word(line))
            }
        except OSError:
            return
        self._personal_words.update(words)
        if words:
            self._checker.word_frequency.load_words(words)

    @staticmethod
    def _dictionary_word(word: str) -> str:
        normalized = word.strip().lower().replace("\u2019", "'")
        if re.fullmatch(r"[a-z]+(?:'[a-z]+)?(?:-[a-z]+(?:'[a-z]+)?)*", normalized):
            return normalized
        return ""

    def _checkable_parts(self, word: str) -> tuple[str, ...]:
        normalized = self._dictionary_word(word)
        if not normalized or len(normalized) < 3 or len(normalized) > 45:
            return ()
        if word.isupper() or any(character.isupper() for character in word[1:]):
            return ()
        if normalized.endswith("'s"):
            normalized = normalized[:-2]
        if "-" in normalized:
            return tuple(part for part in normalized.split("-") if len(part) >= 3)
        return (normalized,)

    def is_misspelled(self, word: str) -> bool:
        parts = self._checkable_parts(word)
        if not parts:
            return False
        cache_key = "\0".join(parts)
        if cache_key not in self._misspelling_cache:
            self._misspelling_cache[cache_key] = any(
                part not in self._ignored_words and bool(self._checker.unknown([part]))
                for part in parts
            )
        return self._misspelling_cache[cache_key]

    def misspelled_words(self, text: str) -> list[str]:
        return [
            match.group(0)
            for match in WORD_PATTERN.finditer(text)
            if self.is_misspelled(match.group(0))
        ]

    def suggestions(self, word: str, limit: int = 6) -> list[str]:
        parts = self._checkable_parts(word)
        if len(parts) != 1:
            return []
        original = parts[0]
        candidates = self._checker.candidates(original) or set()
        ranked = sorted(
            (candidate for candidate in candidates if candidate != original),
            key=lambda candidate: (-self._checker.word_usage_frequency(candidate), candidate),
        )
        return [_match_case(candidate, word) for candidate in ranked[:limit]]

    def ignore_word(self, word: str) -> bool:
        normalized = self._dictionary_word(word)
        if not normalized:
            return False
        self._ignored_words.add(normalized)
        self._misspelling_cache.clear()
        self.changed.emit()
        return True

    def add_to_personal_dictionary(self, word: str) -> bool:
        normalized = self._dictionary_word(word)
        if not normalized:
            return False
        if normalized in self._personal_words:
            return True
        self._personal_words.add(normalized)
        self._checker.word_frequency.load_words([normalized])
        self._write_personal_dictionary()
        self._misspelling_cache.clear()
        self.changed.emit()
        return True

    def _write_personal_dictionary(self) -> None:
        self.personal_dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.personal_dictionary_path.with_suffix(
            self.personal_dictionary_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            "".join(f"{word}\n" for word in sorted(self._personal_words)),
            encoding="utf-8",
        )
        os.replace(temporary_path, self.personal_dictionary_path)


_default_service: SpellCheckService | None = None


def default_spell_check_service() -> SpellCheckService:
    global _default_service
    if _default_service is None:
        _default_service = SpellCheckService()
    return _default_service
