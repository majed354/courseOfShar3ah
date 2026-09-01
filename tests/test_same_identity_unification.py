import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
MANIFEST_PATH = ROOT / "assets/course-specifications/same-identity-unification-20260901.json"
EXPECTED_CODES = {
    "2001115-4",
    "2001116-4",
    "2001215-4",
    "2001216-4",
    "2001311-4",
    "2001321-4",
    "2001411-4",
    "2001346-2",
    "2001465-2",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SameIdentityUnificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_scope_and_counts_are_narrow(self):
        scope = self.manifest["scope"]
        records = self.manifest["records"]
        self.assertEqual(9, scope["course_count"])
        self.assertEqual(407, scope["variant_count_before"])
        self.assertEqual(398, scope["variant_count_after"])
        self.assertEqual(9, scope["removed_public_variant_count"])
        self.assertEqual(0, scope["deleted_pdf_count"])
        self.assertEqual(9, scope["archived_pdf_count"])
        self.assertEqual(0, scope["different_code_course_count"])
        self.assertEqual(EXPECTED_CODES, {record["course_code"] for record in records})

    def test_each_course_has_one_published_variant_with_all_three_scopes(self):
        expected_scopes = {
            ("الشريعة", "بكالوريوس", "قديمة", "38"),
            ("الشريعة", "بكالوريوس", "قديمة", "39"),
            ("الشريعة", "بكالوريوس", "جديدة", "47"),
        }
        records = {record["course_code"]: record for record in self.manifest["records"]}
        for code in EXPECTED_CODES:
            variants = self.data["course_details"][code]["variants"]
            self.assertEqual(1, len(variants), code)
            variant = variants[0]
            record = records[code]
            self.assertEqual(code, variant["specification_code"])
            self.assertEqual(record["title"], variant["title"])
            self.assertEqual(record["selected_pdf"], variant["pdf_url"])
            self.assertIn("ملف موحّد للخطتين القديمة والجديدة", variant["match_note"])
            actual_scopes = {
                (
                    scope.get("program"),
                    scope.get("degree"),
                    scope.get("plan_type"),
                    str(scope.get("version")),
                )
                for scope in variant["scopes"]
            }
            self.assertEqual(expected_scopes, actual_scopes, code)

    def test_selected_hashes_are_current_and_archival_pdfs_remain(self):
        published_urls = {
            variant["pdf_url"]
            for detail in self.data["course_details"].values()
            for variant in detail.get("variants", [])
        }
        for record in self.manifest["records"]:
            selected = ROOT / record["selected_pdf"]
            archived = ROOT / record["archived_pdf"]
            self.assertTrue(selected.is_file(), record["selected_pdf"])
            self.assertTrue(archived.is_file(), record["archived_pdf"])
            self.assertEqual(record["selected_sha256"], sha256(selected))
            self.assertEqual(record["archived_sha256"], sha256(archived))
            self.assertIn(record["selected_pdf"], published_urls)
            self.assertNotIn(record["archived_pdf"], published_urls)

    def test_different_code_candidates_were_not_merged(self):
        for code in (
            "20042102-2",
            "20012102-2",
            "20043205-2",
            "20023205-2",
            "2003442-3",
            "2003105-3",
            "2001824-2",
            "2001881-2",
            "2001833-4",
            "2001713-4",
        ):
            self.assertIn(code, self.data["course_details"])
            variants = self.data["course_details"][code]["variants"]
            self.assertTrue(variants, code)
            self.assertTrue(all(variant["specification_code"] == code for variant in variants), code)


if __name__ == "__main__":
    unittest.main()
