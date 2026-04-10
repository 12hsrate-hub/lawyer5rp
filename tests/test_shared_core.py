from __future__ import annotations

import unittest

from shared.ogp_core import ComplaintInput, build_bbcode, collect_evidence_items, validate_complaint_input
from shared.ogp_models import Representative, Victim


class SharedCoreTests(unittest.TestCase):
    def build_case(self) -> ComplaintInput:
        return ComplaintInput(
            appeal_no="1234",
            org="LSPD",
            subject_names="John Doe",
            situation_description="Описание событий",
            violation_short="Нарушение",
            event_dt="08.04.2026 14:30",
            today_date="08.04.2026",
            representative=Representative(
                name="Rep Name",
                passport="AA123",
                address="Addr",
                phone="1234567",
                discord="rep",
                passport_scan_url="https://example.com/rep",
            ),
            victim=Victim(
                name="Victim Name",
                passport="BB123",
                address="Addr",
                phone="7654321",
                discord="victim",
                passport_scan_url="https://example.com/victim",
            ),
            evidence_items=[("Договор на оказание юридических услуг", "https://example.com/contract")],
        )

    def test_validate_complaint_input_accepts_valid_case(self):
        self.assertEqual(validate_complaint_input(self.build_case()), [])

    def test_build_bbcode_contains_key_fields(self):
        bbcode = build_bbcode(self.build_case())
        self.assertIn("Обращение №1234", bbcode)
        self.assertIn("Victim Name", bbcode)
        self.assertIn("123-45-67", bbcode)
        self.assertIn("765-43-21", bbcode)

    def test_collect_evidence_items_labels_video_parts(self):
        items = collect_evidence_items(
            contract_url="https://example.com/contract",
            video_fix_urls=["https://example.com/fix-1", "https://example.com/fix-2"],
            provided_video_urls=["https://example.com/provided-1", "https://example.com/provided-2"],
        )
        labels = [title for title, _ in items]
        self.assertIn("Видеофиксация процессуальных действий: первая часть записи", labels)
        self.assertIn("Видеофиксация процессуальных действий: вторая часть записи", labels)
        self.assertIn("Предоставленная запись процессуальных действий: первая часть записи", labels)
        self.assertIn("Предоставленная запись процессуальных действий: вторая часть записи", labels)


if __name__ == "__main__":
    unittest.main()
