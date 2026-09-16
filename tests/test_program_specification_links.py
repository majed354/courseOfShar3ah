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
        self.assertEqual(2, len(self.manifest["records"]))
        for record in self.manifest["records"]:
            pdf_path = BUNDLE / record["published_file"]
            self.assertTrue(pdf_path.is_file(), pdf_path)
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            self.assertEqual(record["sha256"], digest)

    def test_programs_link_to_published_files(self):
        expected = {
            ("الدراسات القرآنية المعاصرة", "ماجستير"),
            ("القراءات", "ماجستير"),
        }
        linked = set()
        for program in self.data["programs"]:
            url = program.get("program_specification_url")
            if not url:
                continue
            key = (program["name"], program["degree"])
            linked.add(key)
            self.assertTrue((ROOT / url).is_file(), url)
            self.assertTrue(program.get("program_specification_label"))
        self.assertTrue(expected.issubset(linked))

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


if __name__ == "__main__":
    unittest.main()
