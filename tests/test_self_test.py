from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from traffic_crash_notebook.repository import SCHEMA_VERSION
from traffic_crash_notebook.self_test import run_self_test


class PortableSelfTestTest(unittest.TestCase):
    def test_self_test_creates_pass_log_database_and_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            log = run_self_test(output)
            self.assertTrue(log.is_file())
            self.assertTrue(log.read_text(encoding="utf-8").startswith("PASS\n"))
            self.assertGreater((output / "portable_self_test.sqlite3").stat().st_size, 4096)
            self.assertGreater((output / "portable_self_test.pdf").stat().st_size, 20_000)
            self.assertGreater(
                (output / "portable_self_test_compact_packet.pdf").stat().st_size,
                15_000,
            )
            exchange_pdf = output / "portable_self_test_exchange_report.pdf"
            self.assertGreater(exchange_pdf.stat().st_size, 3_000)
            exchange_pdf_bytes = exchange_pdf.read_bytes()
            self.assertTrue(exchange_pdf_bytes.startswith(b"%PDF-"))
            self.assertTrue(exchange_pdf_bytes.rstrip().endswith(b"%%EOF"))
            exchange_reader = PdfReader(exchange_pdf)
            self.assertFalse(list(exchange_reader.pages[-1].images))
            information_text = exchange_reader.pages[-1].extract_text() or ""
            self.assertIn("INFORMATION / YOUR RESPONSIBILITIES", information_text)
            log_text = log.read_text(encoding="utf-8")
            self.assertIn(f"Database schema: {SCHEMA_VERSION}", log_text)
            self.assertIn(
                "Hit-and-run overview, evidence, lead, and confirmed-record links: PASS",
                log_text,
            )
            self.assertIn("Person ZIP code persistence: PASS", log_text)
            self.assertIn("Participant extracted status persistence: PASS", log_text)
            self.assertIn(
                "Per-vehicle checklist, towing, release, and insurance persistence: PASS",
                log_text,
            )
            self.assertIn(
                "VRU light-meter and light-board persistence: PASS",
                log_text,
            )
            self.assertIn(
                "Data-folder user defaults and new-case prefill: PASS",
                log_text,
            )
            self.assertIn(
                "Verified release-manifest update checker: PASS",
                log_text,
            )
            self.assertIn("Compact-packet PDF bytes:", log_text)
            self.assertIn("Exchange-report PDF bytes:", log_text)
            self.assertIn(
                "Driver, pedestrian, and bicyclist exchange-report inclusion: PASS",
                log_text,
            )
            self.assertIn(
                "Dynamic exchange-report data, time formatting, and searchable information page: PASS",
                log_text,
            )
            self.assertIn("Embedded PDF preview components: PASS", log_text)
            self.assertIn("TIU application and taskbar icon: PASS", log_text)
            self.assertIn(
                "Guided data-storage configuration and migration: PASS",
                log_text,
            )
            self.assertTrue(
                (output / "portable_self_test_storage_config.json").is_file()
            )
            migrated_databases = list(
                output.glob(
                    "portable_self_test_storage_*/traffic_crash_notebook.sqlite3"
                )
            )
            self.assertEqual(len(migrated_databases), 1)
            self.assertGreater(migrated_databases[0].stat().st_size, 4_096)
            self.assertNotIn("diagram", log_text.lower())


if __name__ == "__main__":
    unittest.main()
