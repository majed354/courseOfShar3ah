from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "assets/course-specifications/targeted-readiness-completion-20260915/manifest.json"
OUTCOMES = ROOT / "course-outcomes.json"
SCRIPT = ROOT / "scripts/apply_targeted_readiness_completion_20260915.py"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TargetedReadinessCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load(MANIFEST)
        cls.outcomes = load(OUTCOMES)
        cls.records = {item["course_code"]: item for item in cls.manifest["records"]}

    def variant(self, course_code: str) -> dict:
        record = self.records[course_code]
        matches = [
            item
            for item in self.outcomes["courses"][course_code]["variants"]
            if item["variant_id"] == record["variant_id"]
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_manifest_is_bound_to_current_pdf_hash_and_exact_scope(self) -> None:
        self.assertEqual(self.manifest["schema_version"], "targeted-readiness-completion-v1")
        self.assertEqual(len(self.records), 10)
        for record in self.records.values():
            variant = self.variant(record["course_code"])
            self.assertEqual(sha256(ROOT / record["source_pdf"]), record["source_sha256"])
            self.assertEqual(variant["source_sha256"], record["source_sha256"])
            self.assertIn(record["scope"], variant["scopes"])
            self.assertEqual(
                variant["source_alignment"]["source_sha256"],
                record["source_sha256"],
            )

    def test_original_extraction_is_preserved_beside_effective_corrections(self) -> None:
        self.assertEqual(
            sum(item["weight"] for item in self.variant("2002103-2")["extracted"]["assessment_plan"]),
            110,
        )
        self.assertEqual(
            sum(item["weight"] for item in self.variant("2002106-2")["extracted"]["assessment_plan"]),
            110,
        )
        self.assertEqual(
            sum(item["weight"] for item in self.variant("2004111-2")["extracted"]["assessment_plan"]),
            95,
        )
        self.assertIsNone(self.variant("2004111-2")["extracted"]["clos"][5]["text"])

        for course_code in self.records:
            variant = self.variant(course_code)
            plan = next(
                (item["value"] for item in variant["overrides"] if item["field"] == "assessment_plan"),
                variant["extracted"]["assessment_plan"],
            )
            self.assertAlmostEqual(sum(float(item["weight"]) for item in plan), 100.0)

    def test_pdf_update_status_is_independent_from_effective_database_readiness(self) -> None:
        expected_gaps = {"2002103-2", "2002106-2", "2004111-2", "2004112-2", "2004414-2"}
        actual_gaps = {
            code for code, record in self.records.items() if record["pdf_needs_update"]
        }
        self.assertEqual(actual_gaps, expected_gaps)
        for course_code in self.records:
            variant = self.variant(course_code)
            alignment = variant["source_alignment"]
            if course_code in expected_gaps:
                self.assertEqual(alignment["status"], "source_pdf_gap_confirmed")
                self.assertEqual(alignment["label_ar"], "بيانات القاعدة مكتملة؛ PDF بحاجة إلى تعديل")
                self.assertTrue(alignment["source_update_recommended"])
            else:
                self.assertEqual(alignment["status"], "matches_source_pdf")
                self.assertFalse(alignment["source_update_recommended"])

    def test_program_mapping_changes_only_the_quran_scope(self) -> None:
        variant = self.variant("2004112-2")
        quran = self.records["2004112-2"]["scope"]
        mapping_overrides = [
            item for item in variant["overrides"] if item["field"].endswith(".plo_mappings")
        ]
        self.assertEqual(len(mapping_overrides), 6)
        for override in mapping_overrides:
            index = int(override["field"].split("[")[1].split("]")[0])
            before = variant["extracted"]["clos"][index]["plo_mappings"]
            after = override["value"]
            self.assertEqual(len(before), len(after))
            for old, new in zip(before, after):
                if old["scope"] == quran:
                    self.assertIn(new["status"], {"mapped", "explicitly_unmapped"})
                else:
                    self.assertEqual(new, old)

    def test_zero_enrollment_rights_course_was_not_reclassified_as_pdf_defect(self) -> None:
        self.assertNotIn("2003215-2", self.records)
        variants = self.outcomes["courses"]["2003215-2"]["variants"]
        quran = next(
            item for item in variants
            if any(scope.get("program") == "القرآن وعلومه" for scope in item.get("scopes", []))
        )
        self.assertEqual(quran["source_alignment"]["status"], "matches_source_pdf")
        self.assertFalse(quran["source_alignment"]["source_update_recommended"])

    def test_batch_is_idempotent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("is current", result.stdout)


if __name__ == "__main__":
    unittest.main()
