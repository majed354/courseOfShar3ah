import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "index.html"


class FlexibleArabicSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = INDEX_HTML.read_text(encoding="utf-8")
        start = cls.index_html.index("        function normalizeText(s) {")
        end = cls.index_html.index("        function normalizePasswordInput(value) {", start)
        cls.search_helpers = cls.index_html[start:end]

    def run_search_helpers(self, expression):
        script = f"""
{self.search_helpers}
const result = ({expression});
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_course_title_matches_requested_arabic_variants(self):
        queries = [
            "اصول فقه ١",
            "اصول الفقه (١)",
            "أصول الفقة ١",
            "أُصُولُ الْفِقْهِ [1]",
            "فقه 1 اصول",
        ]
        results = self.run_search_helpers(
            f"{json.dumps(queries, ensure_ascii=False)}.map(query => "
            "matchesFlexibleSearch(query, ['أصول الفقه (1)']))"
        )
        self.assertEqual([True] * len(queries), results)

    def test_hamza_ta_marbuta_and_tatweel_are_flexible(self):
        cases = [
            ["السيره النبويه", ["السيرة النبوية"]],
            ["مسووليه مجتمعيه", ["المسؤولية المجتمعية"]],
            ["اجــــراءات التنفيذ القضائي", ["إجراءات التنفيذ القضائي"]],
        ]
        results = self.run_search_helpers(
            f"{json.dumps(cases, ensure_ascii=False)}.map(([query, values]) => "
            "matchesFlexibleSearch(query, values))"
        )
        self.assertEqual([True, True, True], results)

    def test_article_omission_does_not_damage_words_beginning_with_alif_lam(self):
        cases = [
            ["دلالات ألفاظ ١", ["دلالات الألفاظ (1)"]],
            ["الفاظ 1 دلالات", ["دلالات الألفاظ (١)"]],
            ["ألفاظ", ["الألفاظ"]],
        ]
        results = self.run_search_helpers(
            f"{json.dumps(cases, ensure_ascii=False)}.map(([query, values]) => "
            "matchesFlexibleSearch(query, values))"
        )
        self.assertEqual([True, True, True], results)

    def test_hamza_seat_variants_are_flexible(self):
        queries = [
            "المسئولية المدنية",
            "المسؤوليه المدنيه",
            "المسوولية المدنية",
        ]
        results = self.run_search_helpers(
            f"{json.dumps(queries, ensure_ascii=False)}.map(query => "
            "matchesFlexibleSearch(query, ['المسؤولية المدنية']))"
        )
        self.assertEqual([True] * len(queries), results)

    def test_quran_alef_hamza_madda_unicode_variants_are_flexible(self):
        queries = [
            "القرآن",
            "القرأن",
            "القران",
            "قران",
            "قرإن",
            "القرءان",
            "القرؤان",
            "القرئان",
            "ٱلْقُرْآن",
            "القرا\u0653ن",
            "ﺍﻟﻘﺮﺁﻥ",
            "القرٲن",
            "القرٳن",
            "القرٵن",
            "والقرآن",
            "للقرآن",
        ]
        results = self.run_search_helpers(
            f"{json.dumps(queries, ensure_ascii=False)}.map(query => "
            "matchesFlexibleSearch(query, ['القرآن الكريم']))"
        )
        self.assertEqual([True] * len(queries), results)

    def test_hamza_flexibility_does_not_merge_distinct_words(self):
        cases = [
            ["القرين الكريم", ["القرآن الكريم"]],
            ["قرون الكريم", ["القرآن الكريم"]],
        ]
        results = self.run_search_helpers(
            f"{json.dumps(cases, ensure_ascii=False)}.map(([query, values]) => "
            "matchesFlexibleSearch(query, values))"
        )
        self.assertEqual([False, False], results)

    def test_arabic_and_eastern_arabic_digits_match_course_code(self):
        queries = ["٢٠٠١٢١٠٢-٢", "۲۰۰۱۲۱۰۲-۲", "20012102 2"]
        results = self.run_search_helpers(
            f"{json.dumps(queries, ensure_ascii=False)}.map(query => "
            "matchesFlexibleSearch(query, ['20012102-2']))"
        )
        self.assertEqual([True, True, True], results)

    def test_english_and_aliases_remain_searchable(self):
        cases = [
            ["PUBLIC INTERNATIONAL LAW", ["القانون الدولي العام", "Public International Law"]],
            ["course alias", ["اسم المقرر", "Course Alias"]],
        ]
        results = self.run_search_helpers(
            f"{json.dumps(cases, ensure_ascii=False)}.map(([query, values]) => "
            "matchesFlexibleSearch(query, values))"
        )
        self.assertEqual([True, True], results)

    def test_empty_or_wrong_queries_do_not_match(self):
        cases = [
            ["ال", ["أصول الفقه (1)"]],
            ["ــ", ["أصول الفقه (1)"]],
            ["أصول الفقه ٢", ["أصول الفقه (1)"]],
            ["أصول الفقه ١", ["أصول الفقه (10)"]],
            ["قانون الطيران المدني", ["أصول الفقه (1)"]],
        ]
        results = self.run_search_helpers(
            f"{json.dumps(cases, ensure_ascii=False)}.map(([query, values]) => "
            "matchesFlexibleSearch(query, values))"
        )
        self.assertEqual([False, False, False, False, False], results)

    def test_flexible_normalization_is_limited_to_search_paths(self):
        self.assertIn("const query = normalizeSearchText(state.search);", self.index_html)
        self.assertIn("const query = normalizeSearchText(queryRaw);", self.index_html)
        self.assertIn("matchesFlexibleSearch(state.search,", self.index_html)
        self.assertGreaterEqual(self.index_html.count("matchesFlexibleSearch(queryRaw,"), 2)

        identity_start = self.index_html.index("function normalizeCourseIdentityName")
        identity_end = self.index_html.index("function getCourseIdentityKey", identity_start)
        self.assertNotIn("normalizeSearchText", self.index_html[identity_start:identity_end])


if __name__ == "__main__":
    unittest.main()
