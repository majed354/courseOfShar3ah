import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets" / "course-specifications" / "clo-plo-corrections-20260901"
UNIFIED_MANIFEST = ROOT / "assets" / "course-specifications" / "unified-new-program-mappings-20260901.json"
SAME_IDENTITY_MANIFEST = ROOT / "assets" / "course-specifications" / "same-identity-unification-20260901.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def variant_scopes(variant):
    if isinstance(variant.get("scopes"), list):
        return variant["scopes"]
    if isinstance(variant.get("scope"), dict):
        return [variant["scope"]]
    return []


class NarrowCloPloCorrectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))

    def test_manifest_counts_and_hashes_are_current(self):
        records = self.manifest["records"]
        unified_sources = {
            record["path"]
            for record in json.loads(UNIFIED_MANIFEST.read_text(encoding="utf-8"))["records"]
        }
        self.assertEqual(31, self.manifest["output_count"])
        self.assertEqual(
            {"changed_variants": 31, "split_source_variants": 17},
            self.manifest["data_changes"],
        )
        self.assertEqual(49, sum(len(record["edits"]) for record in records))
        self.assertEqual(
            26,
            sum("text_to" in edit for record in records for edit in record["edits"]),
        )
        self.assertEqual(
            1,
            sum("clo_to" in edit for record in records for edit in record["edits"]),
        )
        for record in records:
            source = ROOT / record["source"]
            output = ROOT / record["output"]
            self.assertTrue(source.is_file(), record["source"])
            self.assertTrue(output.is_file(), record["output"])
            if record["source"] not in unified_sources:
                self.assertEqual(record["source_sha256"], sha256(source))
            self.assertEqual(record["output_sha256"], sha256(output))

    def test_every_corrected_output_has_one_variant_and_expected_scopes(self):
        unified_sources = {
            record["path"]
            for record in json.loads(UNIFIED_MANIFEST.read_text(encoding="utf-8"))["records"]
        }
        same_identity_records = json.loads(
            SAME_IDENTITY_MANIFEST.read_text(encoding="utf-8")
        )["records"]
        selected_same_identity = {
            record["selected_pdf"]: record for record in same_identity_records
        }
        archived_same_identity = {
            record["archived_pdf"] for record in same_identity_records
        }
        variants_by_pdf = {}
        for detail in self.data["course_details"].values():
            for variant in detail.get("variants", []):
                variants_by_pdf.setdefault(variant.get("pdf_url", ""), []).append(variant)

        scope_count = 0
        for record in self.manifest["records"]:
            linked = variants_by_pdf.get(record["output"], [])
            if record["source"] in unified_sources or record["output"] in archived_same_identity:
                self.assertEqual([], linked, record["output"])
                continue
            self.assertEqual(1, len(linked), record["output"])
            scopes = variant_scopes(linked[0])
            self.assertTrue(scopes, record["output"])
            scope_count += len(scopes)
            if record["output"] in selected_same_identity:
                expected = {
                    json.dumps(scope, ensure_ascii=False, sort_keys=True)
                    for scope in selected_same_identity[record["output"]]["published_scopes"]
                }
                actual = {
                    json.dumps(scope, ensure_ascii=False, sort_keys=True)
                    for scope in scopes
                }
                self.assertEqual(expected, actual, record["output"])
                continue
            for scope in scopes:
                self.assertTrue(
                    any(
                        all(str(scope.get(key, "")) == str(value) for key, value in selector.items())
                        for selector in record["selectors"]
                    ),
                    (record["output"], scope),
                )
        self.assertEqual(46, scope_count)

    def test_course_scopes_remain_unique(self):
        for code, detail in self.data["course_details"].items():
            scopes = Counter(
                json.dumps(scope, ensure_ascii=False, sort_keys=True)
                for variant in detail.get("variants", [])
                for scope in variant_scopes(variant)
            )
            duplicates = [scope for scope, count in scopes.items() if count > 1]
            self.assertEqual([], duplicates, code)


if __name__ == "__main__":
    unittest.main()
