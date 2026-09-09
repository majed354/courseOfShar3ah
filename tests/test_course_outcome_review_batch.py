import copy
import json
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import apply_course_outcome_review_batch as review_batch  # noqa: E402


class CourseOutcomeReviewBatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outcomes = json.loads(
            (ROOT / "course-outcomes.json").read_text(encoding="utf-8")
        )
        cls.manifest = json.loads(
            (
                ROOT
                / "review-batches"
                / "course-outcomes-batch-01.json"
            ).read_text(encoding="utf-8")
        )
        cls.manifests = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(
                (ROOT / "review-batches").glob("course-outcomes-batch-*.json")
            )
        ]

    def test_manifest_has_unique_visually_reviewed_rows(self):
        entries = self.manifest["entries"]
        anchors = [
            (
                entry["course_code"],
                entry["variant_id"],
                entry["clo_index"],
                entry["clo_code"],
            )
            for entry in entries
        ]
        self.assertEqual(76, len(entries))
        self.assertEqual(len(anchors), len(set(anchors)))
        self.assertEqual(
            Counter(
                {
                    "present": 62,
                    "source_blank": 9,
                    "corrected_source_text": 4,
                    "source_gap_only": 1,
                }
            ),
            Counter(entry["disposition"] for entry in entries),
        )

    def test_batch_application_is_idempotent(self):
        outcomes = copy.deepcopy(self.outcomes)
        for entry in self.manifest["entries"]:
            review_batch.apply_entry(outcomes, entry)
        first = copy.deepcopy(outcomes)
        for entry in self.manifest["entries"]:
            review_batch.apply_entry(outcomes, entry)
        self.assertEqual(first, outcomes)

    def test_complete_review_set_is_idempotent_and_closes_extraction_review(self):
        outcomes = copy.deepcopy(self.outcomes)
        for manifest in self.manifests:
            for entry in manifest["entries"]:
                review_batch.apply_entry(outcomes, entry)
        self.assertEqual(self.outcomes, outcomes)
        self.assertNotIn(
            "extraction_requires_review",
            outcomes["statistics"]["source_alignment_counts"],
        )

    def test_every_entry_resolves_to_its_pinned_source(self):
        for entry in self.manifest["entries"]:
            variant = review_batch.locate_variant(
                self.outcomes,
                entry["course_code"],
                entry["variant_id"],
                entry["source_pdf"],
            )
            self.assertEqual(entry["source_pdf"], variant["source_pdf"])
            self.assertEqual(64, len(variant["source_sha256"]))

    def test_shared_course_program_mappings_are_not_changed(self):
        shared = self.outcomes["courses"]["2002252-2"]["variants"]
        before = [
            row["plo_mappings"]
            for variant in shared
            for row in variant["extracted"]["clos"]
        ]
        outcomes = copy.deepcopy(self.outcomes)
        for entry in self.manifest["entries"]:
            review_batch.apply_entry(outcomes, entry)
        after = [
            row["plo_mappings"]
            for variant in outcomes["courses"]["2002252-2"]["variants"]
            for row in variant["extracted"]["clos"]
        ]
        self.assertEqual(before, after)
        self.assertTrue(all(len(mappings) == 5 for mappings in after))
        first_row = {
            mapping["scope"]["program"]: mapping["plo_codes"]
            for mapping in shared[0]["extracted"]["clos"][0]["plo_mappings"]
        }
        self.assertEqual(
            {
                "الأنظمة": ["ع2"],
                "الدراسات الإسلامية": ["ع2"],
                "الشريعة": ["ع1"],
                "القرآن وعلومه": ["ع2"],
                "القراءات": ["ع3"],
            },
            first_row,
        )

    def test_split_rows_and_source_gaps_have_expected_dispositions(self):
        by_course = {
            entry["course_code"]: entry for entry in self.manifest["entries"]
        }
        self.assertEqual([5, 6], by_course["2003433-3"]["pages"])
        self.assertEqual(
            "source_gap_only", by_course["2001707-2"]["disposition"]
        )
        self.assertEqual(
            "source_blank", by_course["2002456-2"]["disposition"]
        )


if __name__ == "__main__":
    unittest.main()
