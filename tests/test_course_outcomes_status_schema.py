import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_course_outcomes as verifier  # noqa: E402


SCOPE = {
    "program": "القرآن وعلومه",
    "degree": "بكالوريوس",
    "plan_type": "قديمة",
    "version": "39",
}


def outcome_row(*, text="أن يصف الطالب المفهوم وصفا صحيحا", source_status="present"):
    return {
        "code": "1.1",
        "text": text,
        "source_status": source_status,
        "assessment": "الاختبار النهائي",
        "assessment_source_page": 1,
        "plo_mappings": [
            {
                "scope": dict(SCOPE),
                "plo_codes": ["ع1"],
                "status": "mapped",
                "confidence": "high",
                "source_page": 1,
                "evidence": "exact test cell",
            }
        ],
        "document_plo_codes": ["ع1"],
        "confidence": "medium" if text is not None else "low",
        "source_page": 1,
        "extraction_method": "geometric_pdf",
    }


def extracted(
    *,
    row=None,
    source_status="present",
    source_count=1,
    captured_count=1,
    extraction_status="complete",
    warnings=None,
):
    rows = [] if row is False else [row or outcome_row()]
    return {
        "course_name": "مقرر اختباري",
        "course_name_metadata": {
            "confidence": "high",
            "source_page": 1,
            "extraction_method": "geometric_pdf",
        },
        "clos": rows,
        "assessment_plan": [
            {
                "label": "الاختبار النهائي",
                "weight": 100,
                "source_page": 1,
                "confidence": "high",
            }
        ],
        "assessment_plan_total": 100,
        "assessment_plan_complete": True,
        "warnings": list(warnings or []),
        "extraction_status": extraction_status,
        "source_status": source_status,
        "source_clo_row_count": source_count,
        "captured_clo_row_count": captured_count,
        "page_count": 1,
    }


def validation_errors(value, *, source_sha256=None):
    errors = verifier.ErrorCollector()
    verifier.validate_extracted(
        value,
        [SCOPE],
        "variant.extracted",
        errors,
        source_sha256=source_sha256,
    )
    return errors.messages


class SourceStatusSchemaTest(unittest.TestCase):
    def test_present_source_and_complete_row_capture_are_valid(self):
        self.assertEqual([], validation_errors(extracted()))

    def test_source_blank_is_complete_extraction_not_partial_extraction(self):
        warning = {
            "code": "clo_text_blank_in_source",
            "message": "the published CLO text cell is blank",
            "source_page": 1,
            "clo_code": "1.1",
            "clo_index": 0,
        }
        value = extracted(
            row=outcome_row(text=None, source_status="source_blank"),
            source_status="source_blank",
            warnings=[warning],
        )

        self.assertEqual([], validation_errors(value))

    def test_unreadable_source_is_complete_when_every_row_was_retained(self):
        warning = {
            "code": "clo_text_unreadable",
            "message": "the rendered source text could not be read reliably",
            "source_page": 1,
            "clo_code": "1.1",
            "clo_index": 0,
        }
        value = extracted(
            row=outcome_row(text=None, source_status="unreadable"),
            source_status="unreadable",
            warnings=[warning],
        )

        self.assertEqual([], validation_errors(value))

    def test_row_count_mismatch_requires_partial_and_an_explicit_warning(self):
        value = extracted(
            source_count=2,
            captured_count=1,
            extraction_status="partial",
            warnings=[
                {
                    "code": "clo_row_count_mismatch",
                    "message": "source rows=2; captured rows=1",
                }
            ],
        )

        self.assertEqual([], validation_errors(value))

    def test_unverified_source_count_cannot_be_labelled_complete(self):
        value = extracted(
            source_count=None,
            extraction_status="partial",
            warnings=[
                {
                    "code": "clo_row_count_unverified",
                    "message": "the physical source row count could not be verified",
                }
            ],
        )

        self.assertEqual([], validation_errors(value))

    def test_captured_count_must_equal_the_serialized_clo_rows(self):
        value = extracted(
            source_count=2,
            captured_count=2,
            extraction_status="complete",
        )

        errors = validation_errors(value)
        self.assertTrue(
            any("expected 1 from clos, found 2" in message for message in errors)
        )

    def test_false_complete_is_rejected_when_a_source_row_is_missing(self):
        value = extracted(
            source_count=2,
            captured_count=1,
            extraction_status="complete",
            warnings=[
                {
                    "code": "clo_row_count_mismatch",
                    "message": "source rows=2; captured rows=1",
                }
            ],
        )

        errors = validation_errors(value)
        self.assertTrue(any("expected 'partial'" in message for message in errors))
        self.assertTrue(
            any("complete extraction cannot carry" in message for message in errors)
        )

    def test_blank_and_unreadable_warnings_cannot_be_interchanged(self):
        value = extracted(
            row=outcome_row(text=None, source_status="source_blank"),
            source_status="source_blank",
            warnings=[
                {
                    "code": "clo_text_unreadable",
                    "message": "wrong warning for a proven blank source cell",
                    "source_page": 1,
                    "clo_code": "1.1",
                    "clo_index": 0,
                }
            ],
        )

        errors = validation_errors(value)
        self.assertTrue(
            any("requires clo_text_blank_in_source" in message for message in errors)
        )
        self.assertTrue(
            any("contradicts the indexed CLO" in message for message in errors)
        )

    def test_variant_status_is_the_worst_status_of_its_rows(self):
        value = extracted()
        value["clos"] = [
            outcome_row(),
            {**outcome_row(text=None, source_status="source_blank"), "code": "1.2"},
        ]
        value["source_clo_row_count"] = 2
        value["captured_clo_row_count"] = 2
        value["source_status"] = "present"
        value["warnings"] = [
            {
                "code": "clo_text_blank_in_source",
                "message": "the published CLO text cell is blank",
                "source_page": 1,
                "clo_code": "1.2",
                "clo_index": 1,
            }
        ]

        errors = validation_errors(value)
        self.assertTrue(any("expected 'source_blank'" in message for message in errors))

    def test_statistics_count_row_and_variant_source_statuses(self):
        present = extracted()
        blank = extracted(
            row=outcome_row(text=None, source_status="source_blank"),
            source_status="source_blank",
            warnings=[
                {
                    "code": "clo_text_blank_in_source",
                    "message": "the published CLO text cell is blank",
                    "source_page": 1,
                    "clo_code": "1.1",
                    "clo_index": 0,
                }
            ],
        )
        outcomes = {
            "courses": {
                "1001-2": {
                    "variants": [
                        {"source_pdf": "assets/a.pdf", "extracted": present},
                        {"source_pdf": "assets/b.pdf", "extracted": blank},
                    ]
                }
            },
            "excluded_sources": [],
        }
        errors = verifier.ErrorCollector()

        statistics = verifier.recompute_statistics(copy.deepcopy(outcomes), errors)

        self.assertEqual([], errors.messages)
        self.assertEqual(
            {"present": 1, "source_blank": 1, "unreadable": 0},
            statistics["variant_source_status_counts"],
        )
        self.assertEqual(
            {"present": 1, "source_blank": 1, "unreadable": 0},
            statistics["clo_source_status_counts"],
        )

    def test_embedded_font_cmap_is_rejected_for_an_unreviewed_source(self):
        row = outcome_row()
        row["extraction_method"] = "embedded_font_cmap"
        row["confidence"] = "high"

        errors = validation_errors(extracted(row=row), source_sha256="0" * 64)

        self.assertTrue(
            any(
                "embedded_font_cmap" in message
                and "permitted only for the reviewed embedded-font source_sha256"
                in message
                for message in errors
            )
        )

    def test_embedded_font_continuation_is_rejected_for_an_unreviewed_source(self):
        row = outcome_row()
        row["extraction_method"] = "embedded_font_cmap_with_geometric_continuation"

        errors = validation_errors(extracted(row=row), source_sha256="f" * 64)

        self.assertTrue(
            any(
                "embedded_font_cmap_with_geometric_continuation" in message
                and "permitted only for the reviewed embedded-font source_sha256"
                in message
                for message in errors
            )
        )

    def test_embedded_font_methods_accept_the_reviewed_source(self):
        for method, confidence in (
            ("embedded_font_cmap", "high"),
            ("embedded_font_cmap_with_geometric_continuation", "medium"),
        ):
            with self.subTest(method=method):
                row = outcome_row()
                row["extraction_method"] = method
                row["confidence"] = confidence

                self.assertEqual(
                    [],
                    validation_errors(
                        extracted(row=row),
                        source_sha256=verifier.EMBEDDED_FONT_CMAP_SOURCE_SHA256,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
