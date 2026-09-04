import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_font_recovery as recovery  # noqa: E402


class _FakeFont:
    def __init__(self, codepoint_to_gid):
        self._mapping = codepoint_to_gid

    def has_glyph(self, codepoint, **_kwargs):
        return self._mapping.get(codepoint, 0)


class _FakePage:
    def __init__(self, chars):
        self._chars = chars

    @staticmethod
    def get_fonts(*, full):
        assert full
        return [(7, "ttf", "Type0", "ABCDEF+TestArabic", "F1", "Identity-H", 0)]

    def get_texttrace(self):
        return [
            {
                "font": "TestArabic",
                "type": 0,
                "opacity": 1,
                "dir": (1, 0),
                "chars": self._chars,
            }
        ]


class _FakeDocument:
    def __init__(self, page):
        self._page = page

    def __getitem__(self, index):
        if index != 0:
            raise IndexError(index)
        return self._page

    @staticmethod
    def extract_font(xref):
        assert xref == 7
        return ("ABCDEF+TestArabic", "ttf", "Type0", b"font")


def _char(unicode_value, gid, x0, x1):
    return (unicode_value, gid, (x0, 20), (x0, 10, x1, 24))


class EmbeddedFontRecoveryUnitTests(unittest.TestCase):
    def test_recovers_rtl_text_from_glyph_ids_not_tounicode_values(self):
        # Physical order is left-to-right: baa is left, alef is right.  Both
        # bogus ToUnicode values deliberately say SPACE.
        page = _FakePage([_char(32, 2, 10, 18), _char(32, 1, 20, 28)])
        document = _FakeDocument(page)
        font = _FakeFont({ord("ا"): 1, ord("ب"): 2})

        with patch.object(recovery.pymupdf, "Font", return_value=font):
            value = recovery.recover_embedded_font_text(document, 0, (0, 0, 40, 40))

        self.assertEqual("اب", value)

    def test_rejects_a_missing_used_gid(self):
        page = _FakePage([_char(32, 99, 10, 18)])
        document = _FakeDocument(page)
        font = _FakeFont({ord("ا"): 1})

        with patch.object(recovery.pymupdf, "Font", return_value=font):
            value = recovery.recover_embedded_font_text(document, 0, (0, 0, 40, 40))

        self.assertIsNone(value)

    def test_ignores_only_a_zero_width_non_rendering_placeholder(self):
        page = _FakePage(
            [
                _char(ord("ا"), -1, 18, 18),
                _char(32, 2, 10, 18),
                _char(32, 1, 20, 28),
            ]
        )
        document = _FakeDocument(page)
        font = _FakeFont({ord("ا"): 1, ord("ب"): 2})

        with patch.object(recovery.pymupdf, "Font", return_value=font):
            value = recovery.recover_embedded_font_text(document, 0, (0, 0, 40, 40))

        self.assertEqual("اب", value)

    def test_rejects_a_negative_gid_when_it_has_drawn_width(self):
        page = _FakePage([_char(ord("ا"), -1, 10, 18)])
        document = _FakeDocument(page)
        font = _FakeFont({ord("ا"): 1})

        with patch.object(recovery.pymupdf, "Font", return_value=font):
            value = recovery.recover_embedded_font_text(document, 0, (0, 0, 40, 40))

        self.assertIsNone(value)

    def test_rejects_an_ambiguous_used_gid(self):
        page = _FakePage([_char(32, 1, 10, 18)])
        document = _FakeDocument(page)
        font = _FakeFont({ord("ا"): 1, ord("ب"): 1})

        with patch.object(recovery.pymupdf, "Font", return_value=font):
            value = recovery.recover_embedded_font_text(document, 0, (0, 0, 40, 40))

        self.assertIsNone(value)

    def test_rejects_non_identity_or_non_type0_fonts(self):
        page = _FakePage([_char(32, 1, 10, 18)])
        page.get_fonts = lambda **_kwargs: [
            (7, "ttf", "TrueType", "ABCDEF+TestArabic", "F1", "WinAnsiEncoding", 0)
        ]
        document = _FakeDocument(page)

        with patch.object(
            recovery.pymupdf, "Font", return_value=_FakeFont({ord("ا"): 1})
        ):
            value = recovery.recover_embedded_font_text(document, 0, (0, 0, 40, 40))

        self.assertIsNone(value)


class PublishedPdfRecoveryTests(unittest.TestCase):
    PDF = (
        ROOT
        / "assets"
        / "course-specifications"
        / "raw-recovery-20260827"
        / "2004414-2.pdf"
    )

    def test_recovers_all_five_published_clos_exactly(self):
        document = recovery.pymupdf.open(self.PDF)
        try:
            regions = {
                "1.1": (
                    317.0021925547541,
                    498.3545676082857,
                    505.2383261777678,
                    545.839005995,
                ),
                "2.1": (
                    317.0021925547541,
                    568.1045725097143,
                    505.2383261777678,
                    615.6133355444445,
                ),
                "2.2": (
                    317.0021925547541,
                    615.6133355444445,
                    505.2383261777678,
                    661.9399962339394,
                ),
                "3.1": (
                    317.0021925547541,
                    684.4214653005263,
                    505.2383261777678,
                    731.803906027317,
                ),
                "3.2": (
                    317.0021925547541,
                    731.803906027317,
                    505.2383261777678,
                    779.1300036599999,
                ),
            }
            expected = {
                "1.1": "أن يوضح الطالب الأحكام الشرعية التي نصت على أهمية حقوق الإنسان.",
                "2.1": "أن يستنتج الطالب دور الشرعية الإسلامية في بيان حقوق الإنسان.",
                "2.2": "أن يميز الطالب بين حقوق الإنسان في الشريعة الإسلامية وحقوق الإنسان في القانون الوضعي.",
                "3.1": "أن يتعاون الطالب مع زملائه في دراسة حقوق الإنسان وبيان دورها في الأمن الاجتماعي",
                "3.2": "أن يستخدم الطالب ما تعلمه من أحكام فقهية حول حقوق الإنسان لبيان سماحة التشريع",
            }
            actual = {
                code: recovery.recover_embedded_font_text(document, 3, region)
                for code, region in regions.items()
            }
        finally:
            document.close()

        self.assertEqual(expected, actual)

    def test_recovers_the_cross_page_terminal_fragment(self):
        document = recovery.pymupdf.open(self.PDF)
        try:
            continuation = recovery.recover_embedded_font_text(
                document,
                4,
                (
                    315.23066124666667,
                    199.64000875999992,
                    508.721638162,
                    223.79000365999994,
                ),
            )
        finally:
            document.close()

        self.assertEqual("الإسلامي.", continuation)


if __name__ == "__main__":
    unittest.main()
