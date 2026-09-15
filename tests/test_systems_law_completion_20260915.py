from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets/course-specifications/systems-law-completion-20260915"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SystemsLawCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load(BUNDLE / "manifest.json")
        cls.data = load(ROOT / "data.json")
        cls.outcomes = load(ROOT / "course-outcomes.json")
        cls.record = cls.manifest["selected"][0]

    def test_both_source_bundles_are_pinned_and_fully_inventoried(self) -> None:
        self.assertEqual(330, self.manifest["counts"]["reviewed_pdf_pages"])
        self.assertEqual(41, self.manifest["counts"]["reviewed_course_blocks"])
        self.assertEqual(0, self.manifest["counts"]["exact_missing_code_hits"])
        for source in self.manifest["sources"]:
            path = ROOT / source["file"]
            self.assertEqual(source["sha256"], sha256(path))
            self.assertEqual(source["page_count"], len(PdfReader(str(path)).pages))

    def test_single_selected_adaptation_is_hash_bound_to_eight_pages(self) -> None:
        self.assertEqual("2003102-3", self.record["target_code"])
        self.assertEqual("2003417-3", self.record["source_code"])
        path = ROOT / self.record["output_file"]
        self.assertEqual(self.record["output_sha256"], sha256(path))
        self.assertEqual(8, len(PdfReader(str(path)).pages))

    def test_data_route_is_limited_to_the_new_systems_plan(self) -> None:
        variant = self.data["course_details"]["2003102-3"]["variants"][0]
        self.assertEqual("reviewed_adaptation", variant["match_status"])
        self.assertEqual(self.record["output_file"], variant["pdf_url"])
        self.assertEqual(
            [{"program": "الأنظمة", "degree": "بكالوريوس", "plan_type": "جديدة", "version": "47"}],
            variant["scopes"],
        )

    def test_reviewed_outcomes_preserve_source_evidence_and_pdf_gap(self) -> None:
        variant = self.outcomes["courses"]["2003102-3"]["variants"][0]
        self.assertEqual(self.record["output_sha256"], variant["source_sha256"])
        self.assertEqual("source_pdf_gap_confirmed", variant["source_alignment"]["status"])
        self.assertTrue(variant["source_alignment"]["source_update_recommended"])
        overrides = {item["field"]: item["value"] for item in variant["overrides"]}
        self.assertEqual("قانون العمل والتأمينات الاجتماعية", overrides["course_name"])
        self.assertEqual(9, len(overrides["clos"]))
        self.assertEqual(
            ["ع1", "ع2", "ع3", "م1", "م2", "م3", "ق1", "ق2", "ق1"],
            [row["document_plo_codes"][0] for row in overrides["clos"]],
        )
        self.assertEqual(overrides["clos"][6]["text"], overrides["clos"][8]["text"])
        self.assertEqual(100, sum(item["weight"] for item in overrides["assessment_plan"]))

    def test_coverage_and_rejections_are_published(self) -> None:
        coverage = load(BUNDLE / "coverage.json")
        self.assertEqual((756, 654, 102, 88), (
            coverage["required"], coverage["available"], coverage["missing"], coverage["missing_identities"]
        ))
        self.assertEqual(8, len(self.manifest["rejected_near_matches"]))
        missing_text = (ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md").read_text(encoding="utf-8")
        self.assertNotIn("| 2003102-3 |", missing_text)


if __name__ == "__main__":
    unittest.main()
