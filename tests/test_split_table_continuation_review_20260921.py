import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "review-batches" / "split-table-continuations-20260921.json"


class SplitTableContinuationReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outcomes = json.loads((ROOT / "course-outcomes.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def variant_for(self, record):
        variants = self.outcomes["courses"][record["course_code"]]["variants"]
        return next(variant for variant in variants if variant["variant_id"] == record["variant_id"])

    def test_all_reviewed_continuation_rows_are_source_backed_and_complete(self):
        self.assertEqual(6, len(self.manifest["records"]))
        for record in self.manifest["records"]:
            with self.subTest(course=record["course_code"]):
                variant = self.variant_for(record)
                rows = [row for row in variant["extracted"]["clos"] if row["code"] == "3.1"]
                self.assertEqual(1, len(rows))
                self.assertEqual(record["clo_text"], rows[0]["text"])
                self.assertEqual("complete", variant["extracted"]["extraction_status"])
                self.assertEqual(6, variant["extracted"]["captured_clo_row_count"])
                update_required = bool(record.get("source_update_required"))
                expected_status = (
                    "source_pdf_gap_confirmed" if update_required else "matches_source_pdf"
                )
                self.assertEqual(expected_status, variant["source_alignment"]["status"])
                self.assertEqual(
                    update_required,
                    variant["source_alignment"]["source_update_recommended"],
                )

    def test_reviewed_assessment_and_plo_corrections_are_kept_as_overrides(self):
        for record in self.manifest["records"]:
            variant = self.variant_for(record)
            fields = {item["field"]: item["value"] for item in variant.get("overrides", [])}
            self.assertEqual(record["direct_assessment"], fields["clos[5].assessment"])
            if "reviewed_plo_codes" in record:
                mappings = fields["clos[5].plo_mappings"]
                expected = record["reviewed_plo_codes"]
                self.assertTrue(mappings)
                self.assertTrue(all(mapping["plo_codes"] == expected for mapping in mappings))
                self.assertEqual(expected, fields["clos[5].document_plo_codes"])

    def test_intentional_json_mapping_differences_keep_pdf_update_flags(self):
        recommendations = self.outcomes["source_correction_recommendations"]
        for record in self.manifest["records"]:
            if not record.get("source_update_required"):
                continue
            with self.subTest(course=record["course_code"]):
                variant = self.variant_for(record)
                self.assertEqual("needs_manual", variant["source_review"]["status"])
                self.assertTrue(
                    any(
                        item["variant_id"] == record["variant_id"]
                        and item["issue_code"] == "SOURCE_PLO_MAPPING_PENDING_UPDATE"
                        and item["status"] == "open"
                        for item in recommendations
                    )
                )


if __name__ == "__main__":
    unittest.main()
