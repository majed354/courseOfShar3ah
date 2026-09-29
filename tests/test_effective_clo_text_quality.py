import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_course_outcomes import ErrorCollector, validate_overrides  # noqa: E402


class EffectiveCloTextQualityTest(unittest.TestCase):
    def test_repeated_latin_glyphs_are_rejected_in_effective_text(self):
        extracted = {"clos": [{"code": "1.1", "text": "نص mmmmmmmm مشوّه"}]}
        errors = ErrorCollector()
        validate_overrides([], extracted, "variant.overrides", errors)
        self.assertTrue(any("repeated Latin glyphs" in message for message in errors.messages))

    def test_verified_correction_replaces_corrupt_raw_text(self):
        extracted = {"clos": [{"code": "1.1", "text": "نص mmmmmmmm مشوّه"}]}
        override = {
            "field": "clos[0].text",
            "value": "نص مخرج تعلم صحيح.",
            "evidence": "مطابقة بصرية مع صفحة التوصيف 4.",
            "policy": "verified_extraction_correction_matches_source",
            "reviewed_at": "2026-09-29T14:00:00+03:00",
        }
        errors = ErrorCollector()
        validate_overrides([override], extracted, "variant.overrides", errors)
        self.assertEqual([], errors.messages)


if __name__ == "__main__":
    unittest.main()
