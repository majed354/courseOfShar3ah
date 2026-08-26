import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicCourseCardCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_html = (REPO_ROOT / "index.html").read_text(encoding="utf-8")

    def test_internal_audit_copy_is_not_rendered(self):
        forbidden_phrases = (
            "رمز التوصيف مطابق",
            "توصيف موثق مستقل",
            "توصيف مكيّف ومطابق للخطة",
            "مطابقة اسمية",
            "مطابقة التوصيف تحتاج مراجعة",
            "رمز التوصيف:",
            "حالة الربط بالخطط",
            "انقر لعرض نبذة المقرر",
            "لا توجد معادلة مسجلة",
        )
        for phrase in forbidden_phrases:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.index_html)

        self.assertNotIn("match_note", self.index_html)
        self.assertNotIn("source_context", self.index_html)
        self.assertNotIn("catalog_note", self.index_html)

    def test_only_publicly_useful_notices_remain(self):
        self.assertIn("اختلاف في عدد الساعات بين الخطة والتوصيف", self.index_html)
        self.assertIn("لا يتوفر ملف توصيف لهذا المقرر.", self.index_html)
        self.assertIn("نبذة المقرر", self.index_html)
        self.assertIn("ظهور المقرر في الخطط", self.index_html)

    def test_pdf_files_are_clearly_labeled(self):
        self.assertIn("renderCoursePdfButton(detailContexts[0].details, 'PDF'", self.index_html)
        self.assertIn("ملفات PDF (${detailContexts.length})", self.index_html)
        self.assertIn("renderCoursePdfButton(details, 'تحميل PDF'", self.index_html)
        self.assertIn('aria-label="طباعة الخطة أو حفظها بصيغة PDF"', self.index_html)
        self.assertIn('.course-detail-actions .course-pdf-btn', self.index_html)


if __name__ == "__main__":
    unittest.main()
