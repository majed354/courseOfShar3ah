import hashlib
import json
import re
import unicodedata
import unittest
from collections import defaultdict
from pathlib import Path

import pymupdf

from _shared_alignment_test_support import BUNDLE as ALIGNMENT_BUNDLE
from _shared_alignment_test_support import QURAN_OFFICIAL_BUNDLE, SPLIT_BUNDLE, effective_extraction, load, previous_context, split_lineage_records


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
        later = json.loads(
            (
                ROOT
                / "assets/course-specifications/cross-program-updates-20260914/manifest.json"
            ).read_text(encoding="utf-8")
        )["records"]
        replaced_by = {
            prior: record["output"]
            for record in later
            for prior in record.get("prior_active_urls", [])
        }
        new_plan = json.loads((ROOT/'assets/course-specifications/new-plan-updates-20261002/manifest.json').read_text())
        replaced_by.update({prior['source_pdf']: record['output'] for record in new_plan['records'] for prior in record['predecessors']})
        # The user authorized pointing Quran-only copies back to the official
        # Quran specification each blank was made from (2026-10-28).
        official = load(QURAN_OFFICIAL_BUNDLE / "variant-lineage.json")["records"]
        replaced_by.update({r["old_source_pdf"]: r["new_source_pdf"] for r in official})
        unresolved = {
            output
            for output in outputs
            if output not in linked and replaced_by.get(output) not in linked
        }
        self.assertEqual(set(), unresolved)
        sources = {record["source"] for record in self.manifest["records"]}
        allowed = {r["new_source_pdf"] for r in official}
        self.assertEqual(14, len(allowed))
        self.assertTrue((sources - allowed).isdisjoint(linked))
        for detail in self.data["course_details"].values():
            for variant in detail.get("variants", []):
                if variant["pdf_url"] in allowed:
                    self.assertEqual({"القرآن وعلومه"}, {s["program"] for s in variant["scopes"]})

    def test_original_shared_blanks_survive_beside_authorized_json_mappings(self):
        outputs = {record["output"] for record in self.manifest["records"]}
        _, previous_outcomes = previous_context()
        historical_rows = {}
        for code, course in previous_outcomes["courses"].items():
            for variant in course.get("variants", []):
                if variant["source_pdf"] in outputs:
                    for index, row in enumerate(effective_extraction(variant)["clos"]):
                        for mapping in row["plo_mappings"]:
                            historical_rows[code, variant["variant_id"], index, json.dumps(mapping["scope"], sort_keys=True)] = mapping
        self.assertTrue(historical_rows)
        self.assertTrue(any(m["status"] == "explicitly_unmapped" for m in historical_rows.values()))

        decisions = json.loads((ALIGNMENT_BUNDLE / "alignment-decisions.json").read_text(encoding="utf-8"))
        chosen = {
            (r["course_code"], r["variant_id"], r["clo_index"], json.dumps(r["scope"], sort_keys=True)): r
            for r in decisions["records"]
        }
        parents = {
            (r["course_code"], r["new_variant_id"]): r["old_variant_id"]
            for r in json.loads((ALIGNMENT_BUNDLE / "variant-lineage.json").read_text(encoding="utf-8"))["records"]
        }
        # The 2026-10-28 package split eleven further shared copies; its
        # decisions and lineage join the earlier ones for the same contract.
        parents.update({(r["course_code"], r["new_variant_id"]): r["old_variant_id"] for r in split_lineage_records()})
        for r in json.loads((SPLIT_BUNDLE / "alignment-decisions.json").read_text(encoding="utf-8"))["records"]:
            chosen[(r["course_code"], r["variant_id"], r["clo_index"], json.dumps(r["scope"], sort_keys=True))] = r
        checked = 0
        for code, course in self.outcomes["courses"].items():
            for variant in course.get("variants", []):
                if variant["source_pdf"] not in outputs:
                    continue
                for index, row in enumerate(effective_extraction(variant)["clos"]):
                    for mapping in row["plo_mappings"]:
                        checked += 1
                        key = code, variant["variant_id"], index, json.dumps(mapping["scope"], sort_keys=True)
                        if key not in chosen:
                            # Earlier whole-CLO reviews can legitimately contain
                            # scoped academic links despite the blank PDF cells.
                            # They remain byte-for-byte equivalent if this batch
                            # did not review the particular row/scope.
                            old_id = parents.get((code, variant["variant_id"]), variant["variant_id"])
                            self.assertEqual(historical_rows[code, old_id, index, key[-1]], mapping)
                            continue
                        decision = chosen[key]
                        expected = [decision["plo_code"]] if decision["plo_code"] is not None else []
                        self.assertEqual(expected, mapping["plo_codes"])
                        self.assertEqual("mapped" if expected else "explicitly_unmapped", mapping["status"])
                        override = next(o for o in variant["overrides"] if o["field"] == f"clos[{index}].plo_mappings")
                        self.assertEqual("authorized_program_alignment_revision", override["policy"])
                        self.assertIn(variant["source_sha256"], mapping["evidence"])
                        self.assertIn(decision["program_source_sha256"], mapping["evidence"])
                        self.assertIn("ليس استخراجًا من خلية PDF" if expected else "إبقاء الربط غير محسوم وعدم تخمين رمز", mapping["evidence"])
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
