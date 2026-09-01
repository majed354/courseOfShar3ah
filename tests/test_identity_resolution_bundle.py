import hashlib
import json
import re
import subprocess
import unicodedata
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def normalized_pdf_text(value: str) -> str:
    """Normalize Arabic presentation forms emitted by Poppler."""
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
    return re.sub(r"\s+", "", value)


def scopes(detail: dict) -> set[tuple[str, str, str, str]]:
    result = set()
    for variant in detail["variants"]:
        for scope in variant.get("scopes", [variant.get("scope", {})]):
            result.add(
                (
                    scope.get("program", ""),
                    scope.get("degree", "بكالوريوس"),
                    scope.get("plan_type", ""),
                    str(scope.get("version", "")),
                )
            )
    return result


class IdentityResolutionBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = ROOT / "assets/course-specifications/identity-resolutions-20260829"
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((cls.bundle / "manifest.json").read_text(encoding="utf-8"))

    def test_bundle_has_eight_distinct_outputs(self):
        expected = {
            "2001106-2--quran.pdf",
            "2001106-2--qiraat.pdf",
            "2002235-2.pdf",
            "20024102-2.pdf",
            "2002454-2--quran.pdf",
            "2002454-2--qiraat.pdf",
            "2002703-2.pdf",
            "2003347-2.pdf",
        }
        self.assertEqual(8, self.manifest["counts"]["outputs"])
        self.assertEqual(expected, {path.name for path in self.bundle.glob("*.pdf")})
        self.assertEqual(expected, {record["filename"] for record in self.manifest["records"]})

    def test_outputs_exist_and_match_manifest_hashes(self):
        for record in self.manifest["records"]:
            path = self.bundle / record["filename"]
            self.assertTrue(path.is_file(), record["filename"])
            self.assertEqual(record["output_sha256"], digest(path), record["filename"])

    def test_visual_qa_corrections_are_reproducible(self):
        records = {record["filename"]: record for record in self.manifest["records"]}
        for filename in ("2001106-2--quran.pdf", "2001106-2--qiraat.pdf"):
            self.assertIn(
                "complete_total_learning_hours",
                {edit["kind"] for edit in records[filename]["edits"]},
            )
        for filename in ("2002454-2--quran.pdf", "2002454-2--qiraat.pdf"):
            self.assertIn(
                "complete_topic_hours",
                {edit["kind"] for edit in records[filename]["edits"]},
            )
        self.assertIn(
            "complete_total_learning_hours",
            {edit["kind"] for edit in records["2002235-2.pdf"]["edits"]},
        )
        self.assertIn(
            "restore_cover_row_separator",
            {edit["kind"] for edit in records["20024102-2.pdf"]["edits"]},
        )
        self.assertIn(
            "restore_cover_column_separator",
            {edit["kind"] for edit in records["2003347-2.pdf"]["edits"]},
        )
        self.assertIn(
            "repair_digit_text_extraction",
            {edit["kind"] for edit in records["2002454-2--quran.pdf"]["edits"]},
        )
        self.assertIn(
            "replace_broken_outline",
            {edit["kind"] for edit in records["2002235-2.pdf"]["edits"]},
        )
        for record in records.values():
            self.assertIn(
                "set_pdf_title_metadata",
                {edit["kind"] for edit in record["edits"]},
            )
        doctorate_edits = records["2002703-2.pdf"]["edits"]
        removed = next(
            edit for edit in doctorate_edits
            if edit["kind"] == "remove_empty_learning_outcome_template_rows"
        )
        self.assertEqual({"3.3", "2.4"}, set(removed["labels"]))
        self.assertIn(
            "prevent_topic_number_wrapping",
            {edit["kind"] for edit in doctorate_edits},
        )

    def test_corrected_values_are_text_extractable(self):
        quran_tafsir = subprocess.run(
            [
                "pdftotext", "-f", "2", "-l", "2", "-layout",
                str(self.bundle / "2002454-2--quran.pdf"), "-",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("2(", quran_tafsir.replace(" ", ""))

        quran_seven = subprocess.run(
            [
                "pdftotext", "-f", "4", "-l", "4", "-layout",
                str(self.bundle / "2002235-2.pdf"), "-",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertGreaterEqual(len(re.findall(r"\b30\b", quran_seven)), 2)

    def test_pdf_metadata_titles_are_course_specific(self):
        for record in self.manifest["records"]:
            result = subprocess.run(
                ["pdfinfo", str(self.bundle / record["filename"])],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            title_line = next(
                line for line in result.splitlines() if line.startswith("Title:")
            )
            subject_line = next(
                line for line in result.splitlines() if line.startswith("Subject:")
            )
            self.assertEqual(record["title"], title_line.split(":", 1)[1].strip())
            self.assertEqual(
                f"توصيف مقرر {record['title']}",
                subject_line.split(":", 1)[1].strip(),
            )

    def test_quran_seven_is_not_mixed_with_sharia(self):
        detail = self.data["course_details"]["2002235-2"]
        self.assertEqual(
            {(
                "الدراسات الإسلامية",
                "بكالوريوس",
                "جديدة",
                "47",
            )},
            scopes(detail),
        )
        self.assertNotEqual("2002235-2", "2002411-1")
        self.assertNotIn("2002411-1", self.data["course_details"])

    def test_program_specific_tafsir_variants_remain_separate(self):
        bachelor = self.data["course_details"]["2002454-2"]
        self.assertEqual(
            {
                ("القرآن وعلومه", "بكالوريوس", "قديمة", "39"),
                ("القرآن وعلومه", "بكالوريوس", "جديدة", "47"),
                ("القراءات", "بكالوريوس", "قديمة", "38"),
            },
            scopes(bachelor),
        )
        self.assertTrue(
            all(
                scope.get("degree") == "بكالوريوس"
                for variant in bachelor["variants"]
                for scope in variant["scopes"]
            )
        )
        self.assertTrue(
            all(variant["match_status"] == "verified" for variant in bachelor["variants"])
        )
        master = self.data["course_details"]["2002871-2"]["variants"][0]
        self.assertEqual("2002871-2", master["specification_code"])
        self.assertNotIn("identity-resolutions-20260829", master["pdf_url"])

    def test_tafsir_juz_amma_has_no_stale_tafsir_eight_identity(self):
        path = self.bundle / "20024102-2.pdf"
        cover = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "1", "-raw", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        description = subprocess.run(
            ["pdftotext", "-f", "2", "-l", "2", "-raw", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertNotRegex(cover, r"(?<!\d)8(?!\d)")
        self.assertNotRegex(cover, r"-\s+00\s+4\s+7")
        self.assertNotRegex(description, r"(?<!\d)8(?!\d)")
        # Poppler applies RTL display order to /ActualText in raw mode.
        self.assertIn("مع ءزج ريسفت", description)

    def test_bachelor_and_master_usul_al_tafsir_are_separate(self):
        bachelor = self.data["course_details"]["20022250-2"]["variants"][0]
        master = self.data["course_details"]["2002851-4"]["variants"][0]
        self.assertEqual("20022250-2", bachelor["specification_code"])
        self.assertEqual("2002851-4", master["specification_code"])
        self.assertEqual("verified", bachelor["match_status"])
        self.assertEqual("verified", master["match_status"])

    def test_master_usul_hours_are_internally_consistent(self):
        path = (
            ROOT / "assets/course-specifications/quranic-studies-master-1447/2002851-4.pdf"
        )
        pages = {}
        for page_number in (3, 4, 5):
            pages[page_number] = subprocess.run(
                [
                    "pdftotext", "-f", str(page_number), "-l", str(page_number),
                    "-layout", str(path), "-",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        page3 = normalized_pdf_text(pages[3])
        page4 = normalized_pdf_text(pages[4])
        page5 = normalized_pdf_text(pages[5])
        self.assertIn("أربعساعاتفيالأسبوع", page3)
        self.assertIn("60ساعة", page3)
        self.assertIn("93.75%", page3)
        self.assertIn("6.25%", page3)
        self.assertIn("60ساعة", page4)
        self.assertIn("64ساعة", page4)
        self.assertIn("93.75%", page4)
        self.assertIn("6.25%", page4)
        self.assertEqual(15, page5.count("أربعساعات"))
        self.assertIn("60ساعة", page5)

    def test_quranic_master_manifest_counts_and_hashes_are_current(self):
        bundle = ROOT / "assets/course-specifications/quranic-studies-master-1447"
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sum(int(item["page_count"]) for item in manifest["records"]),
            manifest["counts"]["published_pages"],
        )
        self.assertEqual(
            sum(
                item.get("match_status") == "verified_with_hours_warning"
                for item in manifest["records"]
            ),
            manifest["counts"]["hours_warning_records"],
        )
        for line in (bundle / "hashes.sha256").read_text(encoding="utf-8").splitlines():
            expected, filename = line.split(maxsplit=1)
            self.assertEqual(expected, digest(bundle / filename), filename)

    def test_master_topical_level_uses_the_updated_program_description(self):
        program = next(
            item
            for item in self.data["programs"]
            if item["name"] == "الدراسات القرآنية المعاصرة"
        )
        course = next(item for item in program["courses"] if item["code"] == "2002871-2")
        self.assertEqual(2, course["level"])
        catalog = next(
            item for item in self.data["courses_catalog"] if item["code"] == "2002871-2"
        )
        self.assertEqual(2, catalog["levels_by_program"]["الدراسات القرآنية المعاصرة"])

    def test_qiraat_topical_assessment_and_references_are_current(self):
        path = self.bundle / "2002454-2--qiraat.pdf"
        text = subprocess.run(
            ["pdftotext", "-f", "6", "-l", "6", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(1, text.count("التقويم األسبوعي"))
        percentages = []
        for left, right in re.findall(r"%\s*(\d+)|(\d+)\s*%", text):
            percentages.append(int(left or right))
        self.assertEqual([10, 10, 20, 60], percentages)
        self.assertEqual(100, sum(percentages))
        normalized = normalized_pdf_text(text)
        self.assertIn("عبداللهسالمبافرج", normalized)
        self.assertNotIn("أحمدسيدالكومي", normalized)
        self.assertIn("املكتبةالشاملة", normalized)
        record = next(
            item
            for item in self.manifest["records"]
            if item["filename"] == "2002454-2--qiraat.pdf"
        )
        edit_kinds = {edit["kind"] for edit in record["edits"]}
        self.assertIn("remove_duplicate_assessment_row", edit_kinds)
        self.assertIn("complete_course_references", edit_kinds)
        assessment_edit = next(
            edit
            for edit in record["edits"]
            if edit["kind"] == "remove_duplicate_assessment_row"
        )
        self.assertEqual([242, 242, 242], assessment_edit["fill_rgb_255"])
        self.assertEqual(
            [57.27, 458.47, 537.94, 494.2],
            assessment_edit["cleanup_rect_top_points"],
        )
        reference_edit = next(
            edit
            for edit in record["edits"]
            if edit["kind"] == "complete_course_references"
        )
        self.assertTrue(all(row["font_size"] == 8.5 for row in reference_edit["rows"]))

        bbox = subprocess.run(
            ["pdftotext", "-f", "6", "-l", "6", "-bbox", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        tree = ET.fromstring(bbox)
        words = [element for element in tree.iter() if element.tag.endswith("word")]
        value_words = [
            element
            for element in words
            if 556.7 <= float(element.attrib["yMin"]) < 604.1
            and float(element.attrib["xMax"]) < 396.4
        ]
        self.assertTrue(value_words)
        self.assertGreaterEqual(
            min(float(element.attrib["xMin"]) for element in value_words),
            63.0,
        )

    def test_approved_exact_equivalencies_are_bidirectional(self):
        pairs = {
            "2002427-2": "20024102-2",
            "20024102-2": "2002427-2",
            "20024103-2": "2002235-2",
            "2002235-2": "20024103-2",
            "20044207-2": "2001106-2",
        }
        for source, target in pairs.items():
            options = {
                option["code"]
                for rule in self.data["equivalencies"][source]
                for option in rule["options"]
            }
            self.assertIn(target, options, source)
        self.assertTrue(
            all(
                option["code"] == "20044207-2"
                for rule in self.data["equivalencies"]["2001106-2"]
                for option in rule["options"]
            )
        )

    def test_published_audit_json_has_no_local_paths(self):
        for path in self.bundle.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/majd", text, path.name)
            self.assertNotIn("file:///", text.lower(), path.name)


if __name__ == "__main__":
    unittest.main()
