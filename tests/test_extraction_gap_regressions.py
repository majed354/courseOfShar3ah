import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_course_outcomes as extractor  # noqa: E402


PAGE_BREAK_DROPPED = {
    "2002117-2": "أن يلتزم الطالب بالأمانة العلمية عند نقل المعلومات التاريخية عن المفسرين.",
    "2002215-2": "أن يلتزم الطالب بآداب تلاوة القرآن الكريم أثناء الحفظ والتسميع.",
    "2002222-2": "أن يلتزم الطالب بالموضوعية والأمانة العلمية عند دراسة مناهج المفسرين.",
    "2002313-2": "أن يلتزم الطالب بالدقة اللغوية عند التعامل مع النص القرآني.",
    "2002318-2": "أن يلتزم الطالب بقيم الأمانة العلمية عند دراسة وتحليل توجيهات القراءات المختلفة.",
    "2002333-2": "أن يلتزم الطالب بالدقة العلمية عند التعامل مع الجوانب اللغوية للقرآن.",
    "2002414-2": "أن يلتزم الطالب بآداب تلاوة القرآن الكريم أثناء الحفظ والتسميع بمستوى متقدم.",
}

TOUNICODE_TEXTS = {
    "1.1": "أن يوضح الطالب الأحكام الشرعية التي نصت على أهمية حقوق الإنسان.",
    "2.1": "أن يستنتج الطالب دور الشرعية الإسلامية في بيان حقوق الإنسان.",
    "2.2": "أن يميز الطالب بين حقوق الإنسان في الشريعة الإسلامية وحقوق الإنسان في القانون الوضعي.",
    "3.1": "أن يتعاون الطالب مع زملائه في دراسة حقوق الإنسان وبيان دورها في الأمن الاجتماعي",
    "3.2": "أن يستخدم الطالب ما تعلمه من أحكام فقهية حول حقوق الإنسان لبيان سماحة التشريع الإسلامي.",
}
UNREVIEWED_SPLIT = "2002124-2"


class PublishedGapRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        auxiliary, _ledger = extractor.load_auxiliary_sources(ROOT)
        wanted = set(PAGE_BREAK_DROPPED) | {
            "2004414-2",
            "2004111-2",
            UNREVIEWED_SPLIT,
        }
        cls.extracted = {}
        for variant in extractor.logical_variants(data):
            code = variant["course_code"]
            if code not in wanted:
                continue
            source = ROOT / variant["source_pdf"]
            payload = {
                **variant,
                "repo_root": str(ROOT),
                "auxiliary": auxiliary.get(variant["source_pdf"]),
                "source_sha256": extractor.sha256_file(source),
            }
            _variant_id, extracted = extractor.extract_variant_worker(payload)
            cls.extracted[code] = extracted

    def test_page_break_rows_are_recovered_verbatim(self):
        for code, expected in PAGE_BREAK_DROPPED.items():
            with self.subTest(course=code):
                rows = {row["code"]: row for row in self.extracted[code]["clos"]}
                self.assertEqual(expected, rows["3.1"]["text"])
                self.assertEqual("present", rows["3.1"]["source_status"])

    def test_page_break_capture_is_count_verified(self):
        for code in PAGE_BREAK_DROPPED:
            with self.subTest(course=code):
                extracted = self.extracted[code]
                self.assertEqual("complete", extracted["extraction_status"])
                self.assertEqual(
                    extracted["source_clo_row_count"],
                    extracted["captured_clo_row_count"],
                )
                self.assertEqual(
                    len(extracted["clos"]),
                    extracted["captured_clo_row_count"],
                )

    def test_unreviewed_split_is_counted_but_not_falsely_complete(self):
        extracted = self.extracted[UNREVIEWED_SPLIT]
        self.assertEqual("partial", extracted["extraction_status"])
        self.assertGreater(
            extracted["source_clo_row_count"],
            extracted["captured_clo_row_count"],
        )
        self.assertTrue(
            any(
                warning["code"] == "clo_row_count_mismatch"
                for warning in extracted["warnings"]
            )
        )

    def test_embedded_font_recovers_all_tounicode_texts(self):
        extracted = self.extracted["2004414-2"]
        actual = {row["code"]: row["text"] for row in extracted["clos"]}
        self.assertEqual(TOUNICODE_TEXTS, actual)
        self.assertEqual("complete", extracted["extraction_status"])
        self.assertEqual("present", extracted["source_status"])
        self.assertFalse(
            any(
                warning["code"] == "clo_text_unreadable"
                for warning in extracted["warnings"]
            )
        )

    def test_blank_published_cell_is_kept_and_marked(self):
        extracted = self.extracted["2004111-2"]
        blank_rows = [row for row in extracted["clos"] if row["text"] is None]
        self.assertTrue(blank_rows)
        self.assertTrue(
            all(row["source_status"] == "source_blank" for row in blank_rows)
        )
        self.assertEqual("complete", extracted["extraction_status"])
        self.assertEqual("source_blank", extracted["source_status"])


if __name__ == "__main__":
    unittest.main()
