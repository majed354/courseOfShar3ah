"""User's two-level thresholds, source evidence, and scoped source selection."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.equivalency.engine import calculate, compare, maximum_matching, validate_pairs
from scripts.equivalency.extract import extract_pdf, select_details
from scripts.equivalency.server import clean_topics


def fixture(scores):
    target = [{"id": f"t{i}", "text": f"الموضوع الهدف رقم {i}"} for i in range(len(scores))]
    source = [{"id": f"s{i}", "text": f"الموضوع المصدر رقم {i}"} for i in range(len(scores))]
    pairs = [{"target_id": t["id"], "source_id": s["id"], "score": score, "reason": "اختبار حدود السياسة",
              "target_quote": t["text"], "source_quote": s["text"]} for t, s, score in zip(target, source, scores)]
    return target, source, pairs


class DecisionTests(unittest.TestCase):
    def test_eighty_percent_strict(self):
        r = calculate(*fixture([80] * 8 + [59] * 2))
        self.assertEqual((r["decision"], r["strict_count"]), ("equivalent", 8))

    def test_sixty_is_per_topic_not_course_coverage(self):
        r = calculate(*fixture([80] * 6 + [60] * 2 + [59] * 2))
        self.assertEqual((r["decision"], r["strict_coverage"], r["lenient_coverage"]), ("lenient", 60, 80))

    def test_lenient_still_requires_eighty_course_coverage(self):
        self.assertEqual(calculate(*fixture([79] * 7 + [59] * 3))["decision"], "not_equivalent")

    def test_do_not_round_79_5_up_to_80(self):
        self.assertEqual(calculate(*fixture([100] * 159 + [0] * 41))["decision"], "not_equivalent")

    def test_empty_or_unreviewed_is_not_rejection(self):
        self.assertEqual(calculate([], [], [])["decision"], "insufficient")
        self.assertEqual(calculate(*fixture([100]), reviewed=False)["decision"], "insufficient")

    def test_unspecified_other_topic_never_becomes_rejection_or_acceptance(self):
        t, s, p = fixture([100])
        t[0]["text"] = "أخرى"
        self.assertEqual(calculate(t, s, p)["decision"], "insufficient")
        with patch("scripts.equivalency.engine.local_model", side_effect=AssertionError("no inference for unknown content")):
            self.assertEqual(compare({"topics": t}, {"topics": s})["provider"], "unresolved_source")

    def test_missing_judgment_is_not_zero(self):
        t, s, p = fixture([100, 100])
        with self.assertRaises(ValueError):
            calculate(t, s, p[:1])

    def test_source_topic_cannot_count_twice(self):
        t, s, p = fixture([100, 100])
        p[1].update(source_id=s[0]["id"], source_quote=s[0]["text"])
        r = calculate(t, s, p)
        self.assertEqual((r["strict_count"], r["decision"]), (1, "not_equivalent"))

    def test_augmenting_path_prevents_greedy_loss(self):
        pairs = [{"target_id": "a", "source_id": "1", "score": 100}, {"target_id": "a", "source_id": "2", "score": 80}, {"target_id": "b", "source_id": "1", "score": 90}]
        self.assertEqual(len(maximum_matching(pairs, 80)), 2)

    def test_direction_uses_target_denominator(self):
        t, s, p = fixture([100, 100])
        s.extend([{"id": "extra", "text": "موضوع إضافي في المصدر"}])
        self.assertEqual(calculate(t, s, p)["strict_coverage"], 100)

    def test_fabricated_quote_rejected(self):
        t, s, p = fixture([100])
        p[0]["source_quote"] = "نص غير وارد في المصدر"
        with self.assertRaises(ValueError):
            validate_pairs(p, t, s)

    def test_nan_fractional_and_out_of_range_scores_rejected(self):
        for score in [float("nan"), 79.9, True, -1, 101]:
            with self.subTest(score=score), self.assertRaises(ValueError):
                validate_pairs(fixture([score])[2], *fixture([score])[:2])

    def test_exact_rows_need_no_model(self):
        topics = [{"id": "1", "text": "تعريف علم القراءات ونشأته"}]
        with patch("scripts.equivalency.engine.local_model", side_effect=AssertionError("must not call model")):
            result = compare({"topics": topics}, {"topics": topics})
        self.assertEqual(result["provider"], "exact_text")


class SourceTests(unittest.TestCase):
    def test_corrected_reading_does_not_replace_original(self):
        original = [{"id": "t1", "text": "وشوطه", "page": 5}]
        before = copy.deepcopy(original)
        result = clean_topics([{"id": "t1", "text": "وشروطه"}], original)
        self.assertEqual(original, before)
        self.assertEqual((result[0]["text"], result[0]["corrected_text"]), ("وشوطه", "وشروطه"))

    def test_context_selects_current_pdf_and_respects_exclusion(self):
        context = {"program": "القرآن وعلومه", "degree": "بكالوريوس", "version": "47", "plan_type": "جديدة"}
        old = {"title": "التجويد", "pdf_url": "old.pdf", "scopes": [context], "excluded_scopes": [context]}
        new = {"title": "التجويد", "pdf_url": "uploaded.pdf", "scopes": [context]}
        data = {"course_details": {"1": {"variants": [old, new]}}}
        self.assertEqual(select_details(data, {"code": "1", "name": "التجويد"}, context)["pdf_url"], "uploaded.pdf")
        self.assertIsNone(select_details(data, {"code": "1", "name": "تفسير"}, context))

    def test_multiline_topics_continue_and_review_is_excluded(self):
        root = Path(__file__).resolve().parents[1]
        result = extract_pdf(root / "assets/course-specifications/quran-old-v39/2002110-2.pdf")
        self.assertEqual(len(result["topics"]), 16)
        self.assertIn("الفرش", result["topics"][0]["text"])
        self.assertEqual(result["topics"][-1]["page"], 5)
        self.assertEqual(len(result["excluded_rows"]), 1)
        self.assertFalse(any("المراجع" in t["text"] for t in result["topics"]))

    def test_old_three_column_template_and_continuation(self):
        root = Path(__file__).resolve().parents[1]
        result = extract_pdf(root / "assets/course-specifications/eight-course-completion-20260915/2001113-2.pdf")
        self.assertEqual(len(result["topics"]), 14)
        self.assertIn("المحكوم فيه", result["topics"][-1]["text"])

    def test_topic_fragment_crossing_pages_is_stitched_before_counting(self):
        root = Path(__file__).resolve().parents[1]
        result = extract_pdf(root / "assets/course-specifications/shared-course-blank-plo-20260905/2001340-2--16914d8743.pdf")
        self.assertEqual(len(result["topics"]), 14)
        self.assertIn("تعريف التخريج", result["topics"][0]["text"])
        self.assertEqual(result["topics"][0]["end_page"], 6)
        self.assertEqual(len(result["excluded_rows"]), 2)

    def test_cid_artifacts_recovered_without_discarding_original(self):
        root = Path(__file__).resolve().parents[1]
        result = extract_pdf(root / "assets/course-specifications/shared-course-blank-plo-20260905/2001101-2--6acb2da09b.pdf")
        self.assertEqual(len(result["topics"]), 14)
        repaired = [t for t in result["topics"] if "(cid:" in t["text"]]
        self.assertTrue(repaired)
        self.assertTrue(all("(cid:" not in t["corrected_text"] for t in repaired))


if __name__ == "__main__":
    unittest.main()
