from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

from docx import Document
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_cross_program_updates_20260914 as builder  # noqa: E402
from update_specialty_missing_markdown import calculate  # noqa: E402


RECOVERED_CODES = {"2002228-2", "2002229-2", "2002236-2", "20041201-2"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CrossProgramUpdates20260914Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (builder.OUTPUT / "manifest.json").read_text(encoding="utf-8")
        )
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.outcomes = json.loads(
            (ROOT / "course-outcomes.json").read_text(encoding="utf-8")
        )

    def test_bundle_counts_hashes_and_source_fidelity(self) -> None:
        self.assertEqual(
            {
                "publication_pdfs": 22,
                "replacements": 18,
                "additions": 4,
                "course_codes": 19,
                "program_plan_contexts": 29,
            },
            self.manifest["counts"],
        )
        self.assertEqual(22, len(self.manifest["records"]))
        for record in self.manifest["records"]:
            published = ROOT / record["output"]
            source = ROOT / record["source"]
            self.assertTrue(published.is_file())
            self.assertEqual(record["output_sha256"], sha256(published))
            self.assertEqual(record["page_count"], len(PdfReader(str(published)).pages))
            if source.suffix.lower() == ".pdf":
                self.assertTrue(record["source_byte_identical"])
                self.assertEqual(sha256(source), sha256(published))

    def test_data_and_outcomes_use_all_22_published_variants(self) -> None:
        expected_outputs = {record["output"] for record in self.manifest["records"]}
        data_outputs = {
            variant["pdf_url"]
            for code in {record["code"] for record in self.manifest["records"]}
            for variant in self.data["course_details"][code]["variants"]
        }
        self.assertEqual(expected_outputs, data_outputs)
        outcome_variants = [
            variant
            for code in {record["code"] for record in self.manifest["records"]}
            for variant in self.outcomes["courses"][code]["variants"]
        ]
        self.assertEqual(expected_outputs, {item["source_pdf"] for item in outcome_variants})
        self.assertEqual(22, len(outcome_variants))
        self.assertTrue(
            all(item["extracted"]["extraction_status"] == "complete" for item in outcome_variants)
        )
        self.assertTrue(all(item["overrides"] == [] for item in outcome_variants))

    def test_four_missing_courses_are_now_published(self) -> None:
        manifest_additions = {
            record["code"]
            for record in self.manifest["records"]
            if record["action"] == "add"
        }
        self.assertEqual(RECOVERED_CODES, manifest_additions)
        markdown = (
            ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md"
        ).read_text(encoding="utf-8")
        self.assertTrue(all(code not in markdown for code in RECOVERED_CODES))
        required, available, missing_identities, _ = calculate()
        self.assertEqual((756, 653, 103, 89), (
            required,
            available,
            required - available,
            len(missing_identities),
        ))

    def test_code_mismatch_remains_excluded(self) -> None:
        self.assertEqual(1, len(self.manifest["excluded"]))
        excluded = self.manifest["excluded"][0]
        self.assertEqual("2002412-1", excluded["code_in_source"])
        self.assertEqual("2002421-1", excluded["planned_code"])

    def test_word_inventory_matches_current_coverage(self) -> None:
        path = ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-14.docx"
        document = Document(path)
        self.assertEqual(97, len(document.tables[1].rows))
        codes = {row.cells[1].text.strip() for row in document.tables[1].rows[1:]}
        self.assertTrue(RECOVERED_CODES.isdisjoint(codes))
        body = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("639 موضعًا متاحًا", body)
        self.assertIn("117 موضعًا مفقودًا", body)
        self.assertIn("96 هوية مقرر", body)


if __name__ == "__main__":
    unittest.main()
