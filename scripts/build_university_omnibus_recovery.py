#!/usr/bin/env python3
"""Build exact course-specification slices from the reviewed Drive omnibus.

The downloaded source stays outside the repository.  This builder accepts the
exact source PDF, verifies its fingerprint and page count, then writes only the
five reviewed course ranges plus reproducible provenance records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "assets"
    / "course-specifications"
    / "university-omnibus-recovery-20260910"
)
EXPECTED_SOURCE_SHA256 = (
    "aa7314c144468998308ff38f57e3efdde9c6ba6b364837b3257bbaec5290a150"
)
SOURCE_PAGE_COUNT = 170
SOURCE_TITLE = "توصيف_المقررات_المقدمة_من_قسم_القراءات_للأقسام_الأخرى.pdf"
SOURCE_DRIVE_ID = "1Iy85KvumwapXlEgpgaBvgTb-pj301xIm"
SOURCE_URL = f"https://drive.google.com/file/d/{SOURCE_DRIVE_ID}/view"

COURSES = (
    {
        "code": "2002202-2",
        "title": "القرآن الكريم (2)",
        "document_title": "القرآن الكريم (2)",
        "pages": (112, 117),
        "approval_page": 6,
        "summary": "يتناول حفظ الجزء التاسع والعشرين من القرآن الكريم وتجويده وتسميعه.",
        "scopes": (
            {
                "program": "الدراسات الإسلامية",
                "degree": "بكالوريوس",
                "plan_type": "جديدة",
                "version": "47",
            },
        ),
        "scope_evidence": (
            "تطابق الرمز والاسم تطابقًا تامًا مع هوية وحيدة في الخطط الحالية، "
            "والملف الجامع مخصص لمقررات قسم القراءات المقدمة للأقسام الأخرى."
        ),
    },
    {
        "code": "2002230-2",
        "title": "علوم قرآن",
        "document_title": "علوم القرآن (شريعة)",
        "pages": (138, 144),
        "approval_page": 7,
        "summary": (
            "يتناول علوم القرآن وقضاياه، ومنها المكي والمدني ونزول القرآن وجمعه "
            "وأسباب النزول."
        ),
        "scopes": (
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "38",
            },
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "39",
            },
        ),
        "scope_evidence": "يحمل غلاف التوصيف وسم (شريعة) مع الرمز نفسه.",
    },
    {
        "code": "2002241-2",
        "title": "تفسير آيات الأحكام (1)",
        "document_title": "تفسير آيات الأحكام (1) (شريعة)",
        "pages": (145, 152),
        "approval_page": 8,
        "summary": (
            "يتناول آيات الأحكام المتعلقة بالطهارة وستر العورة والصلاة في السفر "
            "والحضر وأحكام المساجد."
        ),
        "scopes": (
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "38",
            },
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "39",
            },
        ),
        "scope_evidence": "يحمل غلاف التوصيف وسم (شريعة) مع الرمز نفسه.",
    },
    {
        "code": "2002242-2",
        "title": "تفسير آيات الأحكام (2)",
        "document_title": "تفسير آيات الأحكام (2) (شريعة)",
        "pages": (153, 160),
        "approval_page": 8,
        "summary": (
            "يتناول آيات الأحكام المتعلقة بالزكاة والصيام والحج والبيوع وما يحل "
            "وما يحرم من الأطعمة والأشربة."
        ),
        "scopes": (
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "38",
            },
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "39",
            },
        ),
        "scope_evidence": "يحمل غلاف التوصيف وسم (شريعة) مع الرمز نفسه.",
    },
    {
        "code": "2002343-2",
        "title": "تفسير آيات الأحكام (3)",
        "document_title": "تفسير آيات الأحكام (3) (شريعة)",
        "pages": (161, 170),
        "approval_page": 9,
        "summary": (
            "يتناول آيات الأحكام المتعلقة بالصيد والذبائح والنكاح والأسرة والحدود "
            "والجهاد والتعامل مع أصحاب الديانات الأخرى."
        ),
        "scopes": (
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "38",
            },
            {
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "plan_type": "قديمة",
                "version": "39",
            },
        ),
        "scope_evidence": "يحمل غلاف التوصيف وسم (شريعة) مع الرمز نفسه.",
    },
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def actual_text_hex(text: str) -> str:
    return "FEFF" + text.encode("utf-16-be").hex().upper()


def add_accessible_identity(path: Path, title: str, code: str) -> None:
    """Append invisible Unicode identity text without changing visible pages."""

    reader = PdfReader(str(path), strict=False)
    writer = PdfWriter(clone_from=reader)
    writer.add_outline_item(title, 0)
    page = writer.pages[0]
    resources = page.get("/Resources") or DictionaryObject()
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    fonts = resources.get("/Font") or DictionaryObject()
    if hasattr(fonts, "get_object"):
        fonts = fonts.get_object()
    fonts[NameObject("/FActual")] = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    stream = DecodedStreamObject()
    stream.set_data(
        (
            f"/Span << /ActualText <{actual_text_hex(title)}> >> BDC\n"
            "BT /FActual 1 Tf 3 Tr 36 20 Td (x) Tj ET\nEMC\n"
            f"/Span << /ActualText <{actual_text_hex(code)}> >> BDC\n"
            "BT /FActual 1 Tf 3 Tr 36 18 Td (x) Tj ET\nEMC\n"
        ).encode("ascii")
    )
    stream_reference = writer._add_object(stream)
    contents = page.get("/Contents")
    resolved = contents.get_object() if hasattr(contents, "get_object") else contents
    if contents is None:
        page[NameObject("/Contents")] = stream_reference
    elif isinstance(resolved, ArrayObject):
        page[NameObject("/Contents")] = ArrayObject([*resolved, stream_reference])
    else:
        page[NameObject("/Contents")] = ArrayObject([contents, stream_reference])

    with tempfile.NamedTemporaryFile(
        prefix=f".{path.stem}-", suffix=".pdf", dir=path.parent, delete=False
    ) as stream_out:
        temporary = Path(stream_out.name)
    try:
        writer.write(str(temporary))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    source_hash = sha256(source)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            f"Unexpected source fingerprint: {source_hash}; expected {EXPECTED_SOURCE_SHA256}"
        )
    reader = PdfReader(str(source), strict=False)
    if len(reader.pages) != SOURCE_PAGE_COUNT:
        raise ValueError(f"Expected {SOURCE_PAGE_COUNT} source pages, found {len(reader.pages)}")

    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.pdf"):
        stale.unlink()

    records: list[dict[str, object]] = []
    course_details: dict[str, object] = {}
    for item in COURSES:
        first, last = item["pages"]
        writer = PdfWriter()
        for page_index in range(first - 1, last):
            writer.add_page(reader.pages[page_index])
        target = output / f"{item['code']}.pdf"
        writer.write(str(target))
        add_accessible_identity(target, str(item["title"]), str(item["code"]))
        subprocess.run(["qpdf", "--check", str(target)], check=True, capture_output=True)
        page_count = last - first + 1
        if len(PdfReader(str(target), strict=False).pages) != page_count:
            raise RuntimeError(f"Page-count mismatch after writing {target.name}")

        records.append(
            {
                "code": item["code"],
                "title": item["title"],
                "document_title": item["document_title"],
                "source_drive_id": SOURCE_DRIVE_ID,
                "source_url": SOURCE_URL,
                "source_title": SOURCE_TITLE,
                "source_sha256": source_hash,
                "source_pages_inclusive": f"{first}-{last}",
                "page_count": page_count,
                "approval_page_1_based": item["approval_page"],
                "adaptation": "exact_slice_plus_invisible_accessible_identity",
                "visible_content_changed": False,
                "scope_evidence": item["scope_evidence"],
                "scopes": list(item["scopes"]),
                "output_sha256": sha256(target),
            }
        )
        course_details[str(item["code"])] = {
            "variants": [
                {
                    "scopes": list(item["scopes"]),
                    "title": item["title"],
                    "summary": item["summary"],
                    "pdf_url": (
                        "assets/course-specifications/"
                        "university-omnibus-recovery-20260910/"
                        f"{item['code']}.pdf"
                    ),
                    "specification_code": item["code"],
                    "match_status": "verified",
                }
            ]
        }

    manifest = {
        "schema": "university-omnibus-recovery-v1",
        "recovered_at": "2026-09-10",
        "source": {
            "title": SOURCE_TITLE,
            "drive_id": SOURCE_DRIVE_ID,
            "url": SOURCE_URL,
            "sha256": source_hash,
            "page_count": SOURCE_PAGE_COUNT,
        },
        "selection_rule": (
            "Exact course-code and course-title identity in current plans; receiving "
            "program is explicit on the cover or uniquely established by the current plan."
        ),
        "records": records,
        "counts": {
            "reviewed_source_pages": SOURCE_PAGE_COUNT,
            "imported_course_identities": len(records),
            "linked_plan_appearances": sum(len(item["scopes"]) for item in COURSES),
        },
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "data-entries.json", {"course_details": course_details})
    (output / "README.md").write_text(
        "# استرداد توصيفات الملف الجامع في Google Drive\n\n"
        "حزمة من خمسة توصيفات مقتطعة بحدود صفحاتها الأصلية من ملف جامعة "
        "الطائف الجامع لمقررات قسم القراءات المقدمة للأقسام الأخرى. لم يتغير "
        "المحتوى المرئي؛ أضيف فقط نص هوية غير مرئي لتحسين الاستخراج الآلي.\n\n"
        "- المصدر الخارجي وبصمته ونطاق كل مقرر موثقة في `manifest.json`.\n"
        "- بقي ملف المصدر الجامع خارج المستودع ولم يُعدّل.\n"
        "- رُبطت تسعة مواضع في الخطط بخمس هويات مقررات.\n",
        encoding="utf-8",
    )

    hashed = [*sorted(output.glob("*.pdf")), output / "manifest.json", output / "data-entries.json", output / "README.md"]
    (output / "hashes.sha256").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in hashed),
        encoding="utf-8",
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
