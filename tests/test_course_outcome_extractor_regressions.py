import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_course_outcomes as extractor  # noqa: E402


def synthetic_bundle(rows, *, word_baseline=True):
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    provenance = "word_baseline" if word_baseline else "geometric"
    return {
        "rows": padded,
        "boxes": [[None] * width for _ in padded],
        "cell_provenance": [[provenance] * width for _ in padded],
        "geometric": True,
        "word_baseline_fallback": word_baseline,
        "extraction_provenance": provenance,
    }


class CourseOutcomeExtractorRegressionTest(unittest.TestCase):
    @staticmethod
    def _geometry_page(*, edges, words=()):
        class Page:
            def __init__(self):
                self.edges = edges

            @staticmethod
            def extract_words(**_kwargs):
                return list(words)

        return Page()

    def test_fragmented_rows_use_only_wide_physical_boundaries_for_plo(self):
        rows = [
            ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
            ["م1", "أن يعرف الطالب المفهوم الأول", "1.1"],
            ["م2", "أن يطبق الطالب المفهوم الثاني", "1.2"],
        ]
        boxes = [
            [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
            [(20, 30, 40, 42), (40, 20, 80, 60), (80, 35, 100, 45)],
            [(20, 62, 40, 74), (40, 60, 80, 100), (80, 75, 100, 85)],
        ]
        bundle = {
            "rows": rows,
            "boxes": boxes,
            "cell_provenance": [["geometric"] * 3 for _ in rows],
            "geometric": True,
        }
        groups = extractor._table_code_groups(rows, boxes=boxes)
        page = self._geometry_page(
            edges=[
                {"orientation": "h", "top": y, "x0": 20, "x1": 100}
                for y in (0, 20, 60, 100)
            ]
        )

        aligned = extractor._geometric_plo_values_by_group(
            page,
            bundle,
            groups,
            plo_column=0,
            plo_band=(20, 0, 40, 20),
        )

        self.assertEqual([("م1", "geometric_row_alignment")], aligned[0])
        self.assertEqual([("م2", "geometric_row_alignment")], aligned[1])

    def test_single_exact_rowspan_plo_applies_to_each_covered_clo(self):
        rows = [
            ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
            ["ع2", "الناتج الأول", "1.1"],
            ["", "الناتج الثاني", "1.2"],
            ["", "الناتج الثالث", "1.3"],
        ]
        boxes = [
            [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
            [(20, 20, 40, 110), (40, 20, 80, 50), (80, 20, 100, 50)],
            [None, (40, 50, 80, 80), (80, 50, 100, 80)],
            [None, (40, 80, 80, 110), (80, 80, 100, 110)],
        ]
        bundle = {
            "rows": rows,
            "boxes": boxes,
            "cell_provenance": [["geometric"] * 3 for _ in rows],
            "geometric": True,
        }
        groups = extractor._table_code_groups(rows, boxes=boxes)

        aligned = extractor._geometric_plo_values_by_group(
            self._geometry_page(edges=[]),
            bundle,
            groups,
            plo_column=0,
            plo_band=(20, 0, 40, 20),
        )

        self.assertEqual(
            [[("ع2", "geometric_row_alignment")]] * 3,
            [aligned[index] for index in range(3)],
        )

    def test_multi_code_cell_splits_only_by_distinct_positioned_atoms(self):
        rows = [
            ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
            ["ع2 ع1", "الناتج الأول", "1.1"],
            ["", "الناتج الثاني", "1.2"],
        ]
        boxes = [
            [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
            [(20, 20, 40, 80), (40, 20, 80, 50), (80, 20, 100, 50)],
            [None, (40, 50, 80, 80), (80, 50, 100, 80)],
        ]
        bundle = {
            "rows": rows,
            "boxes": boxes,
            "cell_provenance": [["geometric"] * 3 for _ in rows],
            "geometric": True,
        }
        groups = extractor._table_code_groups(rows, boxes=boxes)
        page = self._geometry_page(
            edges=[],
            words=[
                {"text": "2ع", "x0": 25, "x1": 35, "top": 30, "bottom": 40},
                {"text": "1ع", "x0": 25, "x1": 35, "top": 60, "bottom": 70},
            ],
        )

        aligned = extractor._geometric_plo_values_by_group(
            page,
            bundle,
            groups,
            plo_column=0,
            plo_band=(20, 0, 40, 20),
        )

        self.assertEqual([("ع2", "geometric_row_alignment")], aligned[0])
        self.assertEqual([("ع1", "geometric_row_alignment")], aligned[1])

    def test_page_geometry_recovers_clo_occurrence_split_across_bundles(self):
        host = {
            "rows": [
                ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
                ["ع1", "الناتج الأول", ""],
                ["ع2", "الناتج الثاني", "1.2"],
            ],
            "boxes": [
                [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
                [(20, 25, 40, 40), (40, 20, 80, 60), None],
                [(20, 65, 40, 80), (40, 60, 80, 100), (80, 70, 100, 90)],
            ],
            "cell_provenance": [["geometric"] * 3 for _ in range(3)],
            "geometric": True,
        }
        split_codes = {
            "rows": [["1.1"], ["1.2"]],
            "boxes": [[(82, 30, 98, 45)], [(82, 72, 98, 88)]],
            "cell_provenance": [["word_baseline"], ["word_baseline"]],
            "geometric": True,
            "word_baseline_fallback": True,
        }
        page = self._geometry_page(
            edges=[
                {"orientation": "h", "top": y, "x0": 20, "x1": 100}
                for y in (0, 20, 60, 100)
            ]
        )

        recovered = extractor._geometric_page_plo_values_by_occurrence(
            page, [host, split_codes]
        )
        split_groups = extractor._table_code_groups(
            split_codes["rows"], boxes=split_codes["boxes"]
        )
        first, first_top = extractor._page_plo_values_for_group(
            recovered, split_groups[0]
        )
        second, second_top = extractor._page_plo_values_for_group(
            recovered, split_groups[1]
        )

        self.assertEqual([("ع1", "geometric_row_alignment")], first)
        self.assertEqual([("ع2", "geometric_row_alignment")], second)
        self.assertLess(first_top, second_top)

    def test_page_geometry_rejects_disagreeing_host_interpretations(self):
        def host(plo):
            return {
                "rows": [
                    ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
                    [plo, "الناتج الأول", "1.1"],
                ],
                "boxes": [
                    [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
                    [(20, 20, 40, 60), (40, 20, 80, 60), (80, 20, 100, 60)],
                ],
                "cell_provenance": [["geometric"] * 3 for _ in range(2)],
                "geometric": True,
            }

        first = host("ع1")
        second = host("ع2")
        page = self._geometry_page(
            edges=[
                {"orientation": "h", "top": y, "x0": 20, "x1": 100} for y in (0, 20, 60)
            ]
        )

        recovered = extractor._geometric_page_plo_values_by_occurrence(
            page, [first, second]
        )
        group = extractor._table_code_groups(first["rows"], boxes=first["boxes"])[0]

        self.assertEqual(
            ([], None), extractor._page_plo_values_for_group(recovered, group)
        )

    def test_page_geometry_cannot_override_disagreeing_local_geometry(self):
        local = [("ع1", "geometric_row_alignment")]
        page = [("ع2", "geometric_row_alignment")]

        self.assertEqual([], extractor._reconcile_geometric_plo_values(local, page))
        self.assertEqual(local, extractor._reconcile_geometric_plo_values(local, []))
        self.assertEqual(page, extractor._reconcile_geometric_plo_values([], page))

    def test_scalar_cell_cannot_propagate_without_covering_the_rowspan(self):
        rows = [
            ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
            ["ع1", "الناتج الأول", "1.1"],
            ["", "الناتج الثاني", "1.2"],
        ]
        boxes = [
            [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
            [(20, 25, 40, 40), (40, 20, 80, 60), (80, 25, 100, 40)],
            [None, (40, 60, 80, 100), (80, 70, 100, 85)],
        ]
        bundle = {
            "rows": rows,
            "boxes": boxes,
            "cell_provenance": [["geometric"] * 3 for _ in rows],
            "geometric": True,
        }
        groups = extractor._table_code_groups(rows, boxes=boxes)
        page = self._geometry_page(
            edges=[
                {"orientation": "h", "top": y, "x0": 20, "x1": 100}
                for y in (0, 20, 100)
            ]
        )

        aligned = extractor._geometric_plo_values_by_group(
            page,
            bundle,
            groups,
            plo_column=0,
            plo_band=(20, 0, 40, 20),
        )

        self.assertEqual({}, aligned)

    def test_scalar_rowspan_cannot_cross_domain_heading(self):
        rows = [
            ["رمز ناتج التعلم المرتبط بالبرنامج", "نواتج التعلم", "الرمز"],
            ["ع1", "الناتج الأول", "1.1"],
            ["", "المهارات", "2.0"],
            ["", "الناتج الثاني", "2.1"],
        ]
        boxes = [
            [(20, 0, 40, 20), (40, 0, 80, 20), (80, 0, 100, 20)],
            [(20, 20, 40, 110), (40, 20, 80, 50), (80, 25, 100, 40)],
            [None, (40, 50, 80, 70), (80, 50, 100, 70)],
            [None, (40, 70, 80, 110), (80, 80, 100, 95)],
        ]
        bundle = {
            "rows": rows,
            "boxes": boxes,
            "cell_provenance": [["geometric"] * 3 for _ in rows],
            "geometric": True,
        }
        groups = extractor._table_code_groups(rows, boxes=boxes)

        aligned = extractor._geometric_plo_values_by_group(
            self._geometry_page(edges=[]),
            bundle,
            groups,
            plo_column=0,
            plo_band=(20, 0, 40, 20),
        )

        self.assertEqual({}, aligned)

    def test_invalid_tounicode_plo_prefix_uses_isolated_glyph_ocr_consensus(self):
        class Pixmap:
            @staticmethod
            def tobytes(_format):
                return b"png"

        class RenderPage:
            rect = extractor.pymupdf.Rect(0, 0, 600, 800)

            @staticmethod
            def get_pixmap(**_kwargs):
                return Pixmap()

        pdf_page = type(
            "PdfPage",
            (),
            {
                "chars": [
                    {
                        "text": "ه",
                        "x0": 343.25,
                        "top": 634.98,
                        "x1": 348.686,
                        "bottom": 646.98,
                    },
                    {
                        "text": "3",
                        "x0": 337.15,
                        "top": 634.98,
                        "x1": 343.246,
                        "bottom": 646.98,
                    },
                ]
            },
        )()
        document = [RenderPage()]

        with patch.object(extractor, "_run_tesseract", return_value="م") as ocr:
            recovered = extractor._recover_exact_plo_with_ocr_prefix(
                pdf_page,
                document,
                0,
                (249.6, 632.1, 354.6, 680.6),
                "ه3",
            )

        self.assertEqual("م3", recovered)
        self.assertEqual(6, ocr.call_count)

    def test_invalid_tounicode_plo_prefix_rejects_ambiguous_ocr(self):
        class Pixmap:
            @staticmethod
            def tobytes(_format):
                return b"png"

        class RenderPage:
            rect = extractor.pymupdf.Rect(0, 0, 600, 800)

            @staticmethod
            def get_pixmap(**_kwargs):
                return Pixmap()

        pdf_page = type(
            "PdfPage",
            (),
            {
                "chars": [
                    {"text": "ه", "x0": 10, "top": 10, "x1": 16, "bottom": 22},
                    {"text": "1", "x0": 4, "top": 10, "x1": 10, "bottom": 22},
                ]
            },
        )()
        document = [RenderPage()]

        with patch.object(
            extractor,
            "_run_tesseract",
            side_effect=["م", "ع", "م", "ع", "م", "ع"],
        ):
            recovered = extractor._recover_exact_plo_with_ocr_prefix(
                pdf_page, document, 0, (0, 0, 20, 30), "ه1"
            )

        self.assertIsNone(recovered)

    def test_digit_only_plo_recovers_one_adjacent_placeholder_glyph(self):
        class Pixmap:
            @staticmethod
            def tobytes(_format):
                return b"png"

        class RenderPage:
            rect = extractor.pymupdf.Rect(0, 0, 100, 100)

            @staticmethod
            def get_pixmap(**_kwargs):
                return Pixmap()

        pdf_page = type(
            "PdfPage",
            (),
            {
                "chars": [
                    {"text": "2", "x0": 10, "top": 10, "x1": 18, "bottom": 24},
                    {"text": " ", "x0": 17.9, "top": 10, "x1": 23, "bottom": 24},
                    {"text": " ", "x0": 4, "top": 15, "x1": 5, "bottom": 24},
                ]
            },
        )()

        with patch.object(extractor, "_run_tesseract", return_value="مم") as ocr:
            recovered = extractor._recover_exact_plo_with_ocr_prefix(
                pdf_page, [RenderPage()], 0, (0, 0, 40, 40), "2"
            )

        self.assertEqual("م2", recovered)
        self.assertEqual(6, ocr.call_count)

    def test_digit_only_plo_rejects_multiple_placeholder_glyphs(self):
        pdf_page = type(
            "PdfPage",
            (),
            {
                "chars": [
                    {"text": "1", "x0": 10, "top": 10, "x1": 18, "bottom": 24},
                    {"text": " ", "x0": 18, "top": 10, "x1": 23, "bottom": 24},
                    {"text": " ", "x0": 19, "top": 10, "x1": 24, "bottom": 24},
                ]
            },
        )()

        with patch.object(extractor, "_run_tesseract") as ocr:
            recovered = extractor._recover_exact_plo_with_ocr_prefix(
                pdf_page, [], 0, (0, 0, 40, 40), "1"
            )

        self.assertIsNone(recovered)
        ocr.assert_not_called()

    def test_invalid_prefix_accepts_padded_single_glyph_consensus(self):
        class Pixmap:
            @staticmethod
            def tobytes(_format):
                return b"png"

        class RenderPage:
            rect = extractor.pymupdf.Rect(0, 0, 100, 100)

            @staticmethod
            def get_pixmap(**_kwargs):
                return Pixmap()

        pdf_page = type(
            "PdfPage",
            (),
            {
                "chars": [
                    {"text": "ي", "x0": 18, "top": 10, "x1": 26, "bottom": 24},
                    {"text": "1", "x0": 10, "top": 10, "x1": 18, "bottom": 24},
                ]
            },
        )()

        with patch.object(
            extractor,
            "_run_tesseract",
            side_effect=["", "", "", "", "", "", "ق", "ق", "ق", "ق", ""],
        ) as ocr:
            recovered = extractor._recover_exact_plo_with_ocr_prefix(
                pdf_page, [RenderPage()], 0, (0, 0, 40, 40), "ي1"
            )

        self.assertEqual("ق1", recovered)
        self.assertEqual(11, ocr.call_count)

    def test_clipped_course_topics_heading_is_not_a_clo_continuation(self):
        self.assertTrue(extractor._is_course_topics_heading_fragment("وعات المقرر"))
        self.assertTrue(extractor._is_course_topics_heading_fragment("موضوعات المقرر"))
        self.assertFalse(
            extractor._is_course_topics_heading_fragment(
                "يحلل الطالب موضوعات المقرر تحليلًا نقديًا."
            )
        )

    def test_nested_duplicate_bbox_is_the_same_merged_code_cell(self):
        spanning = (505.381544, 227.363390, 537.931102, 301.339709)
        nested = (505.381544, 288.290004, 532.060010, 301.339709)
        rows = [["1.1"], ["1.1"]]
        boxes = [[spanning], [nested]]

        groups = extractor._table_code_groups(rows, boxes=boxes)

        self.assertEqual(1, len(groups))
        self.assertEqual("1.1", groups[0]["code"])
        self.assertEqual([0, 1], groups[0]["rows"])

    def test_disjoint_duplicate_bbox_remains_two_published_rows(self):
        # These are the two genuinely distinct 2.2 cells in 2003822-2.
        first = (485.62, 565.11, 516.70, 582.55)
        second = (485.62, 669.10, 516.70, 686.58)
        rows = [["2.2"], ["2.2"]]
        boxes = [[first], [second]]

        groups = extractor._table_code_groups(rows, boxes=boxes)

        self.assertEqual(2, len(groups))
        self.assertEqual([[0], [1]], [group["rows"] for group in groups])

    def test_summary_establishes_rows_and_direct_table_only_donates_assessment(self):
        header = [
            "طرق التقييم",
            "",
            "",
            "نواتج التعلم",
            "",
            "الرمز",
            "",
            "رمز مخرج التعلم المرتبط بالبرنامج",
        ]
        summary = synthetic_bundle(
            [
                header,
                ["", "", "", "يصف الطالب المفهوم الأول وصفا واضحا", "", "1.1", "", ""],
                [
                    "",
                    "",
                    "",
                    "يطبق الطالب المفهوم الثاني تطبيقا صحيحا",
                    "",
                    "1.2",
                    "",
                    "",
                ],
            ]
        )
        direct = synthetic_bundle(
            [
                header,
                ["", "", "", "المعرفة والفهم", "", "1.0", "", ""],
                [
                    "الاختبار الدوري",
                    "",
                    "",
                    "يصف نصا مكررا في الجدول المباشر",
                    "",
                    "1.1",
                    "",
                    "",
                ],
                [
                    "سجل المتابعة",
                    "",
                    "",
                    "يطبق نصا مكررا في الجدول المباشر",
                    "",
                    "1.2",
                    "",
                    "",
                ],
                [
                    "اختبار زائد",
                    "",
                    "",
                    "يصف صفا لا يوجد في الملخص المنشور",
                    "",
                    "2.1",
                    "",
                    "",
                ],
            ]
        )

        records, _ = extractor.parse_outcome_tables(
            [[summary], [direct]], [], None, object(), [None, None]
        )

        self.assertEqual(["1.1", "1.2"], [record["code"] for record in records])
        self.assertEqual(
            [
                "يصف الطالب المفهوم الأول وصفا واضحا",
                "يطبق الطالب المفهوم الثاني تطبيقا صحيحا",
            ],
            [record["text"] for record in records],
        )
        self.assertEqual(
            ["الاختبار الدوري", "سجل المتابعة"],
            [record["assessment"] for record in records],
        )
        self.assertEqual([1, 1], [record["source_page"] for record in records])
        self.assertEqual(
            [2, 2], [record["assessment_source_page"] for record in records]
        )

    def test_original_geometric_candidate_beats_longer_word_baseline_candidate(self):
        header = ["", "", "", "نواتج التعلم", "", "الرمز"]
        original = synthetic_bundle(
            [
                header,
                ["", "", "", "يصف الطالب النص الأصلي بوضوح", "", "1.1"],
            ],
            word_baseline=False,
        )
        synthetic = synthetic_bundle(
            [
                header,
                [
                    "",
                    "",
                    "",
                    "يصف الطالب نصا اصطناعيا أطول بكثير لكنه لا يسبق الجدول الهندسي الأصلي",
                    "",
                    "1.1",
                ],
            ]
        )

        records, _ = extractor.parse_outcome_tables(
            [[original, synthetic]], [], None, object(), [None]
        )

        self.assertEqual(1, len(records))
        self.assertEqual("يصف الطالب النص الأصلي بوضوح", records[0]["text"])

    def test_same_code_different_text_does_not_donate_assessment(self):
        header = [
            "طرق التقييم",
            "",
            "",
            "نواتج التعلم",
            "",
            "الرمز",
        ]
        summary = synthetic_bundle(
            [
                header,
                [
                    "",
                    "",
                    "",
                    "يوضح الطالب المفهوم الأصلي شرحا مفصلا واضحا مستقلا",
                    "",
                    "1.1",
                ],
            ],
            word_baseline=False,
        )
        unrelated = synthetic_bundle(
            [
                header,
                [
                    "اختبار شفهي",
                    "",
                    "",
                    "يطبق الطالب مهارة أخرى",
                    "",
                    "1.1",
                ],
            ],
            word_baseline=False,
        )

        records, _ = extractor.parse_outcome_tables(
            [[summary], [unrelated]], [], None, object(), [None, None]
        )

        self.assertEqual(1, len(records))
        self.assertEqual(
            "يوضح الطالب المفهوم الأصلي شرحا مفصلا واضحا مستقلا",
            records[0]["text"],
        )
        self.assertIsNone(records[0]["assessment"])
        self.assertIsNone(records[0]["assessment_source_page"])

    def test_adjacent_page_keeps_all_distinct_rows_after_duplicate_code_is_proven(self):
        header = [
            "طرق التقييم",
            "",
            "",
            "نواتج التعلم",
            "",
            "الرمز",
            "",
            "رمز مخرج التعلم المرتبط بالبرنامج",
        ]
        first_page = synthetic_bundle(
            [
                header,
                ["", "", "", "المعرفة والفهم", "", "1.0", "", ""],
                ["", "", "", "أن يعرف الطالب أحداث السيرة النبوية", "", "1.1", "", ""],
                ["", "", "", "أن يعدد الطالب غزوات النبي وأحداثها", "", "1.2", "", ""],
                [
                    "",
                    "",
                    "",
                    "أن يلخص الطالب أهم أحداث السيرة النبوية",
                    "",
                    "1.3",
                    "",
                    "",
                ],
                ["", "", "", "المهارات", "", "2.0", "", ""],
                [
                    "",
                    "",
                    "",
                    "أن يدرك الطالب أهمية دراسة السيرة النبوية",
                    "",
                    "2.1",
                    "",
                    "",
                ],
                ["", "", "", "أن يقارن الطالب بين الغزوات النبوية", "", "2.2", "", ""],
            ],
            word_baseline=False,
        )
        continuation_page = synthetic_bundle(
            [
                header,
                [
                    "",
                    "",
                    "",
                    "أن يربط الطالب بين دروس السيرة وآيات القرآن",
                    "",
                    "1.3",
                    "",
                    "",
                ],
                ["", "", "", "القيم والاستقلالية والمسؤولية", "", "3.0", "", ""],
                [
                    "",
                    "",
                    "",
                    "أن يفتخر الطالب بالسيرة النبوية وأخلاق النبي",
                    "",
                    "3.1",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "أن يبادر الطالب بنشر قيم السيرة النبوية",
                    "",
                    "3.2",
                    "",
                    "",
                ],
                [
                    "",
                    "",
                    "",
                    "أن يتمكن الطالب من الرد على شبهات أعداء الإسلام",
                    "",
                    "1.3",
                    "",
                    "",
                ],
            ],
            word_baseline=False,
        )

        records, warnings = extractor.parse_outcome_tables(
            [[first_page], [continuation_page]],
            [],
            None,
            object(),
            [None, None],
        )

        self.assertEqual(
            ["1.1", "1.2", "1.3", "2.1", "2.2", "1.3", "3.1", "3.2", "1.3"],
            [record["code"] for record in records],
        )
        repeated = [record for record in records if record["code"] == "1.3"]
        self.assertEqual(3, len(repeated))
        self.assertEqual(
            3, len({extractor.normalized(record["text"]) for record in repeated})
        )
        self.assertEqual([1, 2, 2], [record["source_page"] for record in repeated])
        duplicate_warnings = [
            warning
            for warning in warnings
            if warning["code"] == "duplicate_source_clo_code"
        ]
        # The parser de-duplicates identical warnings on the same source page;
        # the final reconciliation later expands them to per-CLO indexes.
        self.assertEqual(
            [1, 2], [warning["source_page"] for warning in duplicate_warnings]
        )


if __name__ == "__main__":
    unittest.main()
