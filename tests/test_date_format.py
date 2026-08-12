from __future__ import annotations

import unittest

from traffic_crash_notebook.date_format import (
    add_date_separators,
    add_time_separator,
    format_date_for_display,
    format_time_for_display,
    normalize_date_for_storage,
    normalize_time_for_storage,
    parse_date,
    parse_time,
    weekday_name,
)


class DateFormatTest(unittest.TestCase):
    def test_typed_dates_receive_separators_without_changing_manual_single_digits(self):
        self.assertEqual(add_date_separators("0"), "0")
        self.assertEqual(add_date_separators("08"), "08/")
        self.assertEqual(add_date_separators("0804"), "08/04/")
        self.assertEqual(add_date_separators("08042026"), "08/04/2026")
        self.assertEqual(add_date_separators("8/5/2026"), "8/5/2026")

    def test_typed_times_receive_colons_without_changing_manual_single_digits(self):
        self.assertEqual(add_time_separator("0"), "0")
        self.assertEqual(add_time_separator("14"), "14:")
        self.assertEqual(add_time_separator("1435"), "14:35")
        self.assertEqual(add_time_separator("0235 PM"), "02:35 PM")
        self.assertEqual(add_time_separator("2:35 PM"), "2:35 PM")

    def test_iso_dates_display_as_mm_dd_yyyy(self):
        self.assertEqual(format_date_for_display("2026-08-05"), "08/05/2026")

    def test_us_dates_are_zero_padded_and_stored_as_iso(self):
        self.assertEqual(format_date_for_display("8/5/2026"), "08/05/2026")
        self.assertEqual(normalize_date_for_storage("8/5/2026"), "2026-08-05")
        self.assertEqual(normalize_date_for_storage("2026-08-05"), "2026-08-05")

    def test_blank_and_non_date_text_are_preserved_safely(self):
        self.assertEqual(format_date_for_display(""), "")
        self.assertEqual(normalize_date_for_storage(" Unknown "), "Unknown")
        self.assertIsNone(parse_date("02/30/2026"))
        self.assertEqual(format_date_for_display("02/30/2026"), "02/30/2026")

    def test_weekday_accepts_storage_and_display_formats(self):
        self.assertEqual(weekday_name("2026-08-05"), "Wednesday")
        self.assertEqual(weekday_name("08/05/2026"), "Wednesday")
        self.assertEqual(weekday_name("Unknown"), "")

    def test_crash_times_display_with_am_pm_and_store_in_24_hour_format(self):
        self.assertEqual(format_time_for_display("14:35"), "02:35 PM")
        self.assertEqual(format_time_for_display("2:35 pm"), "02:35 PM")
        self.assertEqual(normalize_time_for_storage("02:35 PM"), "14:35")
        self.assertEqual(normalize_time_for_storage("7:05 am"), "07:05")

    def test_blank_and_non_time_text_are_preserved_safely(self):
        self.assertEqual(format_time_for_display(""), "")
        self.assertEqual(normalize_time_for_storage(" Unknown "), "Unknown")
        self.assertIsNone(parse_time("25:00"))
        self.assertEqual(format_time_for_display("25:00"), "25:00")


if __name__ == "__main__":
    unittest.main()
