import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets" / "course-specifications" / "program-specifications-20260916"


class ProgramSpecificationLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        cls.index_html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_manifest_files_and_hashes(self):
        self.assertEqual(19, len(self.manifest["records"]))
        self.assertEqual(19, self.manifest["summary"]["program_specifications"])
        self.assertEqual(20, self.manifest["summary"]["linked_program_contexts"])
        self.assertEqual(5, self.manifest["summary"]["published_with_warnings"])
        for record in self.manifest["records"]:
            pdf_path = ROOT / record["published_url"]
            self.assertTrue(pdf_path.is_file(), pdf_path)
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            self.assertEqual(record["published_sha256"], digest)
            self.assertEqual("passed", record["pdfinfo_check"])
            self.assertEqual("passed", record["visual_cover_check"])
            self.assertGreater(record["page_count"], 0)

    def test_programs_link_to_published_files(self):
        expected = {
            (record["program"], record["degree"], int(context["version"]))
            for record in self.manifest["records"]
            for context in record["contexts"]
        }
        linked = set()
        for program in self.data["programs"]:
            url = program.get("program_specification_url")
            if not url:
                continue
            key = (program["name"], program["degree"], int(program["version"]))
            linked.add(key)
            self.assertTrue((ROOT / url).is_file(), url)
            self.assertTrue(program.get("program_specification_label"))
            self.assertIn(program.get("program_specification_status"), {"published", "published_with_warnings"})
        self.assertEqual(expected, linked)
        self.assertEqual(20, len(linked))

    def test_qiraat_doctorate_is_the_only_known_gap(self):
        unlinked = [program for program in self.data["programs"] if not program.get("program_specification_url")]
        self.assertEqual(1, len(unlinked))
        self.assertEqual(("القراءات", "دكتوراه"), (unlinked[0]["name"], unlinked[0]["degree"]))
        self.assertEqual("القراءات", self.manifest["known_gap"]["program"])
        self.assertEqual("دكتوراه", self.manifest["known_gap"]["degree"])

    def test_site_renders_program_specification_action(self):
        self.assertIn("programSpecificationUrl", self.index_html)
        self.assertIn("عرض توصيف البرنامج", self.index_html)
        self.assertIn("officialProgramsById", self.index_html)

    def test_program_codes_and_outcomes_are_preserved(self):
        programs = {
            (program["name"], program["degree"]): program
            for program in self.data["programs"]
        }
        contemporary = programs[("الدراسات القرآنية المعاصرة", "ماجستير")]["program_details"]
        qiraat = programs[("القراءات", "ماجستير")]["program_details"]
        self.assertEqual("022103", contemporary["program_code"])
        self.assertEqual(7, len(contemporary["learning_outcomes"]))
        self.assertEqual("02210305", qiraat["program_code"])
        self.assertEqual(11, len(qiraat["learning_outcomes"]))
        for details in (contemporary, qiraat):
            self.assertTrue(details["mission"])
            self.assertEqual(4, len(details["objectives"]))
            self.assertEqual(
                len(details["learning_outcomes"]),
                len({item["code"] for item in details["learning_outcomes"]}),
            )

        linked_details = [
            program["program_details"]
            for program in self.data["programs"]
            if program.get("program_specification_url") and program.get("program_details")
        ]
        self.assertEqual(20, len(linked_details))
        self.assertEqual(
            193,
            sum(len(details.get("learning_outcomes", [])) for details in linked_details),
        )


if __name__ == "__main__":
    unittest.main()
