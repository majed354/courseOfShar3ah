import hashlib
import json
import sys
import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import apply_full_variant_review_batch as full_review  # noqa: E402


EXPECTED_CODES = {
    "2002202-2",
    "2002230-2",
    "2002241-2",
    "2002242-2",
    "2002343-2",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class UniversityOmnibusRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = (
            ROOT
            / "assets"
            / "course-specifications"
            / "university-omnibus-recovery-20260910"
        )
        cls.manifest = json.loads(
            (cls.bundle / "manifest.json").read_text(encoding="utf-8")
        )
        cls.entries = json.loads(
            (cls.bundle / "data-entries.json").read_text(encoding="utf-8")
        )["course_details"]
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.outcomes = json.loads(
            (ROOT / "course-outcomes.json").read_text(encoding="utf-8")
        )
        cls.review = json.loads(
            (
                ROOT
                / "review-batches"
                / "course-outcomes-full-variant-02.json"
            ).read_text(encoding="utf-8")
        )

    def test_deep_scan_records_exactly_five_recoveries_and_nine_appearances(self):
        self.assertEqual(170, self.manifest["source"]["page_count"])
        self.assertEqual(
            "aa7314c144468998308ff38f57e3efdde9c6ba6b364837b3257bbaec5290a150",
            self.manifest["source"]["sha256"],
        )
        self.assertEqual(EXPECTED_CODES, {row["code"] for row in self.manifest["records"]})
        self.assertEqual(5, self.manifest["counts"]["imported_course_identities"])
        self.assertEqual(9, self.manifest["counts"]["linked_plan_appearances"])

    def test_every_slice_matches_its_manifest_hash_and_page_range(self):
        for record in self.manifest["records"]:
            path = self.bundle / f"{record['code']}.pdf"
            self.assertTrue(path.is_file(), record["code"])
            self.assertEqual(record["output_sha256"], sha256(path))
            self.assertEqual(record["page_count"], len(PdfReader(str(path)).pages))
            self.assertFalse(record["visible_content_changed"])

    def test_data_entries_are_published_with_exact_scopes(self):
        self.assertEqual(EXPECTED_CODES, set(self.entries))
        for code, detail in self.entries.items():
            self.assertEqual(detail, self.data["course_details"][code])
            variant = detail["variants"][0]
            self.assertEqual(code, variant["specification_code"])
            self.assertEqual("verified", variant["match_status"])
            self.assertEqual(
                f"assets/course-specifications/university-omnibus-recovery-20260910/{code}.pdf",
                variant["pdf_url"],
            )

    def test_visual_review_overrides_are_current_and_complete(self):
        records = {row["course_code"]: row for row in self.review["records"]}
        self.assertEqual(EXPECTED_CODES, set(records))
        for code, record in records.items():
            variant = full_review.locate_variant(self.outcomes, record)
            overrides = {item["field"]: item["value"] for item in variant["overrides"]}
            template = self.review["templates"][record["template"]]
            self.assertEqual("complete", overrides["extraction_status"])
            self.assertEqual([], overrides["warnings"])
            self.assertEqual(100.0, overrides["assessment_plan_total"])
            self.assertEqual(
                [(row["code"], row["plo_code"]) for row in template["clos"]],
                [
                    (row["code"], row["document_plo_codes"][0])
                    for row in overrides["clos"]
                ],
            )


if __name__ == "__main__":
    unittest.main()
