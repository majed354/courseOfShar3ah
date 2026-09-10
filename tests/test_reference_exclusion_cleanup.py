import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets/course-specifications/reference-exclusion-cleanup-20260901"
SHARED_BLANK_MANIFEST = ROOT / "assets/course-specifications/shared-course-blank-plo-20260905/manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReferenceExclusionCleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))

    def test_counts_and_current_hashes(self):
        scope = self.manifest["scope"]
        records = self.manifest["records"]
        self.assertEqual(410, scope["published_pdf_count_scanned"])
        self.assertEqual(7, scope["affected_pdf_count"])
        self.assertEqual(13, scope["removed_reference_entry_count"])
        self.assertEqual(1, scope["heritage_replacement_count"])
        self.assertEqual(9, scope["restored_pdf_count_after_availability_exception_review"])
        self.assertEqual(14, scope["restored_reference_entry_count"])
        self.assertEqual(7, len(records))
        self.assertEqual(13, sum(len(record["removed"]) for record in records))

        for record in records:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(record["output_sha256"], sha256(path), record["path"])
            self.assertNotEqual(record["before_sha256"], record["output_sha256"])

    def test_every_edited_pdf_is_still_published(self):
        published = {
            variant["pdf_url"]
            for detail in self.data["course_details"].values()
            for variant in detail.get("variants", [])
        }
        final_route = {
            record["source"]: record["output"]
            for record in json.loads(
                SHARED_BLANK_MANIFEST.read_text(encoding="utf-8")
            )["records"]
        }
        for record in self.manifest["records"]:
            self.assertIn(
                final_route.get(record["path"], record["path"]),
                published,
                record["path"],
            )

    def test_replacement_policy_was_applied_only_when_needed(self):
        replacements = [record for record in self.manifest["records"] if record["replacement"]]
        self.assertEqual(1, len(replacements))
        self.assertEqual("20043101-2", replacements[0]["course_code"])
        self.assertIn("البقاعي", replacements[0]["replacement"])
        for record in self.manifest["records"]:
            if record["course_code"] != "20043101-2":
                self.assertIsNone(record["replacement"])

    def test_hash_ledger_matches_manifest(self):
        ledger = {}
        for line in (BUNDLE / "hashes.sha256").read_text(encoding="utf-8").splitlines():
            digest, relative_path = line.split(None, 1)
            ledger[(BUNDLE / relative_path.strip()).resolve()] = digest
        self.assertEqual(7, len(ledger))
        for record in self.manifest["records"]:
            path = (ROOT / record["path"]).resolve()
            self.assertEqual(record["output_sha256"], ledger[path])


if __name__ == "__main__":
    unittest.main()
