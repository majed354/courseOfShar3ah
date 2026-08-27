import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apply_raw_recovery_data import expected_scopes, scope_key  # noqa: E402


class RawRecoveryBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = ROOT / "assets/course-specifications/raw-recovery-20260827"
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.entries = json.loads((cls.bundle / "data-entries.json").read_text(encoding="utf-8"))[
            "course_details"
        ]
        cls.manifest = json.loads((cls.bundle / "manifest.json").read_text(encoding="utf-8"))
        cls.source_manifest = json.loads(
            (cls.bundle / "source-manifest.json").read_text(encoding="utf-8")
        )

    def test_bundle_contains_only_the_55_selected_missing_courses(self):
        self.assertEqual(55, len(self.entries))
        self.assertEqual(55, self.manifest["counts"]["total"])
        self.assertEqual(55, len(self.source_manifest["records"]))
        self.assertTrue(
            all(
                not record["target"]["current_course_details_present"]
                for record in self.source_manifest["records"]
            )
        )
        self.assertEqual(set(self.entries), {record["code"] for record in self.manifest["records"]})
        self.assertEqual(
            set(self.entries),
            {record["target"]["code"] for record in self.source_manifest["records"]},
        )

    def test_every_public_entry_and_pdf_is_present(self):
        bundle_pdfs = {path.stem for path in self.bundle.glob("*.pdf")}
        self.assertEqual(set(self.entries), bundle_pdfs)
        for code, detail in self.entries.items():
            self.assertEqual(detail, self.data["course_details"][code])
            variant = detail["variants"][0]
            self.assertEqual(code, variant["specification_code"])
            self.assertTrue((ROOT / variant["pdf_url"]).is_file())
            self.assertFalse(
                {"match_note", "verification_note", "internal_note"}.intersection(variant)
            )

    def test_statuses_and_scopes_match_the_audited_identity_decisions(self):
        match_types = {record["code"]: record["match_type"] for record in self.manifest["records"]}
        adapted = set()
        for code, detail in self.entries.items():
            variant = detail["variants"][0]
            expected_status = (
                "adapted_verified"
                if match_types[code] == "approved_code_change_same_identity"
                else "verified"
            )
            self.assertEqual(expected_status, variant["match_status"])
            if expected_status == "adapted_verified":
                adapted.add(code)

            actual = {scope_key(scope) for scope in variant["scopes"]}
            expected = expected_scopes(self.data, code, variant["title"])
            self.assertEqual(expected, actual, code)

        self.assertEqual({"2002200-2", "20023110-2"}, adapted)

    def test_stamp_qa_is_complete(self):
        report = json.loads((self.bundle / "stamp-qa-report.json").read_text(encoding="utf-8"))
        self.assertEqual({"total": 52, "passed": 52, "failed": 0}, report["counts"])
        self.assertEqual([], report["errors"])

    def test_inherited_blank_and_local_machine_links_were_removed(self):
        removed = [
            edit
            for record in self.manifest["records"]
            for edit in record["edits_applied"]
            if edit["kind"] == "remove_nonpublic_link_annotations"
        ]
        self.assertEqual(13, sum(edit["count"] for edit in removed))
        self.assertEqual({"2001112-2", "2001421-4", "2003230-2"}, {
            record["code"]
            for record in self.manifest["records"]
            if any(
                edit["kind"] == "remove_nonpublic_link_annotations"
                for edit in record["edits_applied"]
            )
        })

    def test_published_audit_json_does_not_expose_local_absolute_paths(self):
        for path in self.bundle.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/majd", text, path.name)
            self.assertNotIn("file:///", text.lower(), path.name)


if __name__ == "__main__":
    unittest.main()
