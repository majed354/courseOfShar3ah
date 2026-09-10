import hashlib
import json
import re
import unicodedata
import unittest
from collections import defaultdict
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets/course-specifications/shared-course-blank-plo-20260905"
MANIFEST_PATH = BUNDLE / "manifest.json"
ARABIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)
PLO_TOKEN_RE = re.compile(r"(?<!\w)[عمقكKSVP]\s*[0-9]{1,2}(?:\.[0-9]+)?(?!\w)")
PROGRAM_LABELS = (
    "القرآن وعلومه",
    "القراءات",
    "الدراسات الإسلامية",
    "الشريعة",
    "الأنظمة",
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value):
    text = unicodedata.normalize("NFKC", str(value or "")).translate(ARABIC_DIGITS)
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def scopes(variant):
    if isinstance(variant.get("scopes"), list):
        return variant["scopes"]
    if isinstance(variant.get("scope"), dict):
        return [variant["scope"]]
    return []


class SharedCoursePloBlankingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.outcomes = json.loads(
            (ROOT / "course-outcomes.json").read_text(encoding="utf-8")
        )

    def test_inventory_uses_program_not_plan_identity(self):
        identities = defaultdict(set)
        plan_counts = defaultdict(int)
        for program in self.data["programs"]:
            program_id = (program["name"], program["degree"])
            for course in program["courses"]:
                key = (course["code"], normalize(course["name"]))
                identities[key].add(program_id)
                plan_counts[key] += 1
        shared = {key for key, programs in identities.items() if len(programs) > 1}
        same_program_multiple_plans = {
            key
            for key, programs in identities.items()
            if len(programs) == 1 and plan_counts[key] > 1
        }
        self.assertEqual(self.manifest["shared_course_count"], len(shared))
        self.assertTrue(same_program_multiple_plans)
        self.assertTrue(shared.isdisjoint(same_program_multiple_plans))

    def test_manifest_hashes_and_redacted_cells(self):
        self.assertEqual(72, self.manifest["output_count"])
        self.assertEqual(516, self.manifest["clo_row_count"])
        for record in self.manifest["records"]:
            source = ROOT / record["source"]
            output = ROOT / record["output"]
            self.assertEqual(record["source_sha256"], sha256(source))
            self.assertEqual(record["output_sha256"], sha256(output))
            self.assertTrue(record["cleared_cells"], record["output"])
            with pymupdf.open(output) as document:
                for cell in record["cleared_cells"]:
                    page = document[cell["page_1_based"] - 1]
                    value = " ".join(
                        page.get_textbox(pymupdf.Rect(cell["mapping_rect"])).split()
                    )
                    self.assertIsNone(
                        PLO_TOKEN_RE.search(value), (record["output"], cell, value)
                    )
                    self.assertFalse(
                        any(label in value for label in PROGRAM_LABELS),
                        (record["output"], cell, value),
                    )

    def test_verified_web_recovery_reduces_missing_shared_specs(self):
        recovered = {
            record["course_key"]
            for record in self.manifest["records"]
            if record.get("recovered_at") == "2026-09-10"
        }
        self.assertEqual(
            {"105115-2", "6602322-2", "990113-2", "990311-2"}, recovered
        )
        self.assertEqual(55, self.manifest["shared_course_with_spec_count"])
        self.assertEqual(54, self.manifest["shared_course_without_spec_count"])
        for record in self.manifest["records"]:
            if record.get("recovered_at") != "2026-09-10":
                continue
            self.assertTrue(record["web_source"]["source_url"].startswith("https://"))
            self.assertIn("tu.edu.sa/", record["web_source"]["source_url"])

    def test_every_shared_spec_variant_is_rerouted(self):
        outputs = {record["output"] for record in self.manifest["records"]}
        linked = {
            variant.get("pdf_url")
            for detail in self.data["course_details"].values()
            for variant in detail.get("variants", [])
        }
        self.assertTrue(outputs.issubset(linked))
        sources = {record["source"] for record in self.manifest["records"]}
        self.assertTrue(sources.isdisjoint(linked))

    def test_all_published_shared_rows_are_explicitly_unmapped(self):
        outputs = {record["output"] for record in self.manifest["records"]}
        rows = []
        for course in self.outcomes["courses"].values():
            for variant in course.get("variants", []):
                if variant["source_pdf"] not in outputs:
                    continue
                rows.extend(variant["extracted"]["clos"])
        self.assertTrue(rows)
        for row in rows:
            for mapping in row["plo_mappings"]:
                self.assertEqual("explicitly_unmapped", mapping["status"])
                self.assertEqual([], mapping["plo_codes"])


if __name__ == "__main__":
    unittest.main()
