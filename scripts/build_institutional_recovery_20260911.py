#!/usr/bin/env python3
"""Build the audited 2026-09-11 institutional course-specification bundle.

The seven inputs are synced copies from the university's curated Google Drive
library.  The visible pages are preserved byte-for-byte at the content level;
only PDF metadata, a bookmark, and invisible accessible identity text are added
so the established extractor can read the audited course code and title.
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
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path(
    "/Users/majd/Library/CloudStorage/GoogleDrive-majedaljohanitaif@gmail.com/"
    "ملفاتي/اااالمراجعة الشاملة/توصيف المقررات الشامل/المستويات pdf"
)
DEFAULT_OUTPUT = (
    ROOT / "assets" / "course-specifications" / "institutional-recovery-20260911"
)

QURAN_OLD_39 = {
    "program": "القرآن وعلومه",
    "degree": "بكالوريوس",
    "plan_type": "قديمة",
    "version": "39",
}
QURAN_NEW_47 = {
    "program": "القرآن وعلومه",
    "degree": "بكالوريوس",
    "plan_type": "جديدة",
    "version": "47",
}

COURSES = (
    {
        "code": "2001205-2",
        "title": "الحديث (1)",
        "source": "03) المستوى الثالث/2001205-2 الحديث (1).pdf",
        "source_sha256": "6914827caa4358cecc9cf29d351bd5035e38ffdb859fd5152ac6ed7165b3082a",
        "page_count": 8,
        "printed_identity_status": "administrative_placeholder_in_code_cell",
        "summary": "يتناول أربعين حديثًا من جوامع الكلم النبوي بالحفظ والدراسة التحليلية.",
        "scopes": (QURAN_OLD_39,),
        "identity_evidence": (
            "اسم الملف المؤسسي يحمل الرمز 2001205-2، والغلاف يثبت عنوان الحديث (1) "
            "وبرنامج القرآن وعلومه وساعتين معتمدتين، والخطة 39 تحمل الهوية نفسها. "
            "خانة الرمز في الغلاف تحمل عبارة إدارية عن الاستحداث بدل الرمز."
        ),
    },
    {
        "code": "2001209-2",
        "title": "الحديث (2)",
        "source": "04) المستوى الرابع/2001209-2 الحديث (2).pdf",
        "source_sha256": "94dfb435984c8caf49d8bd9f6ea71dc24032a39206a3b5387023b212ea8eb273",
        "page_count": 8,
        "printed_identity_status": "administrative_placeholder_in_code_cell",
        "summary": "يتناول أحاديث فضائل القرآن والسور وأبواب التفسير بالدراسة التحليلية.",
        "scopes": (QURAN_OLD_39,),
        "identity_evidence": (
            "اسم الملف المؤسسي يحمل الرمز 2001209-2، والغلاف يثبت عنوان الحديث (2) "
            "وبرنامج القرآن وعلومه وساعتين معتمدتين، والخطة 39 تحمل الهوية نفسها. "
            "خانة الرمز في الغلاف تحمل عبارة إدارية عن الاستحداث بدل الرمز."
        ),
    },
    {
        "code": "2001221-2",
        "title": "الفقه (1)",
        "source": "03) المستوى الثالث/2001221-2 الفقه (1).pdf",
        "source_sha256": "0fe9d01a4fe08bd19561d5ab3e231900ba13b8f6976a51722cebbc1d6582a8f2",
        "page_count": 7,
        "printed_identity_status": "exact",
        "summary": "يتناول أحكام العبادات من الطهارة والصلاة والزكاة والصيام والمناسك والجهاد.",
        "scopes": (QURAN_NEW_47,),
        "identity_evidence": (
            "الغلاف يثبت الرمز والعنوان وبرنامج القرآن وعلومه والساعات، وتطابقها خطة 47."
        ),
    },
    {
        "code": "2001320-2",
        "title": "الحديث (3)",
        "source": "05) المستوى الخامس/2001320-2 الحديث (3).pdf",
        "source_sha256": "72241c78b37cdfce57e900d5450d73c8354f1af9b598d5150533c041f6b91862",
        "page_count": 7,
        "printed_identity_status": "administrative_placeholder_in_code_cell",
        "summary": "يتناول اثنين وثلاثين حديثًا من أحاديث العبادات بالدراسة التحليلية.",
        "scopes": (QURAN_OLD_39,),
        "identity_evidence": (
            "اسم الملف المؤسسي يحمل الرمز 2001320-2، والغلاف يثبت عنوان الحديث (3) "
            "وبرنامج القرآن وعلومه وساعتين معتمدتين، والخطة 39 تحمل الهوية نفسها في "
            "المستوى السادس. لم يُستخدم اسم مجلد المستوى لإثبات الهوية."
        ),
    },
    {
        "code": "2001322-2",
        "title": "الفقه (2)",
        "source": "04) المستوى الرابع/2001322-2 الفقه (2).pdf",
        "source_sha256": "1e1ca855446a581c9ea5d29d64c55c1b8e97595fb1a6406ccadde2016ad59f18",
        "page_count": 6,
        "printed_identity_status": "exact",
        "summary": "يتناول الأحكام الفقهية المتعلقة بفقه المعاملات وما يلحق به من أبواب.",
        "scopes": (QURAN_OLD_39, QURAN_NEW_47),
        "identity_evidence": (
            "الغلاف يثبت الرمز والعنوان وبرنامج القرآن وعلومه والساعات، وتطابقها الخطتان 39 و47."
        ),
    },
    {
        "code": "2001317-2",
        "title": "الفقه (3)",
        "source": "05) المستوى الخامس/2001317-2 الفقه (3).pdf",
        "source_sha256": "a2e1ecb86d5461ac4fa9427849d06da8f7dd32e84e8410c803c274e2e0aef2b3",
        "page_count": 6,
        "printed_identity_status": "exact",
        "summary": "يتناول فقه الأسرة والجنايات والدعاوى والبينات.",
        "scopes": (QURAN_OLD_39, QURAN_NEW_47),
        "identity_evidence": (
            "الغلاف يثبت الرمز والعنوان وبرنامج القرآن وعلومه والساعات، وتطابقها الخطتان 39 و47."
        ),
    },
    {
        "code": "2001330-2",
        "title": "أصول الفقه (2)",
        "source": "06) المستوى السادس/2001330-2 أصول الفقه (2).pdf",
        "source_sha256": "00a2897b04a62a7f9b783d356b7858443d9082b9a13cd62fe40e34cf073caa6d",
        "page_count": 7,
        "printed_identity_status": "blank_code_cell",
        "summary": "يتناول المعايير الأساسية لعلم أصول الفقه وتطبيقاتها.",
        "scopes": (QURAN_OLD_39, QURAN_NEW_47),
        "identity_evidence": (
            "اسم الملف المؤسسي يحمل الرمز 2001330-2، والغلاف يثبت عنوان أصول الفقه (2) "
            "وبرنامج القرآن وعلومه وساعتين معتمدتين، والخطتان 39 و47 تحملان الهوية نفسها. "
            "خانة الرمز في الغلاف فارغة."
        ),
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
    """Add a bookmark and invisible Unicode identity without visible alteration."""

    reader = PdfReader(str(path), strict=False)
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata({"/Title": f"{code} {title}"})
    writer.add_outline_item(f"{code} {title}", 0)
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
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.pdf"):
        stale.unlink()

    records: list[dict[str, object]] = []
    course_details: dict[str, object] = {}
    for item in COURSES:
        source = source_root / str(item["source"])
        if not source.is_file():
            raise FileNotFoundError(source)
        source_hash = sha256(source)
        if source_hash != item["source_sha256"]:
            raise ValueError(f"{item['code']}: unexpected source fingerprint {source_hash}")
        source_pages = len(PdfReader(str(source), strict=False).pages)
        if source_pages != item["page_count"]:
            raise ValueError(
                f"{item['code']}: expected {item['page_count']} pages, found {source_pages}"
            )

        target = output / f"{item['code']}.pdf"
        shutil.copy2(source, target)
        add_accessible_identity(target, str(item["title"]), str(item["code"]))
        subprocess.run(["qpdf", "--check", str(target)], check=True, capture_output=True)
        if len(PdfReader(str(target), strict=False).pages) != source_pages:
            raise RuntimeError(f"{item['code']}: page count changed during identity completion")

        scopes = [dict(scope) for scope in item["scopes"]]
        completed = item["printed_identity_status"] != "exact"
        records.append(
            {
                "code": item["code"],
                "title": item["title"],
                "source_library": "Google Drive institutional comprehensive course specifications",
                "source_relative_path": item["source"],
                "source_sha256": source_hash,
                "page_count": source_pages,
                "printed_identity_status": item["printed_identity_status"],
                "identity_completion_applied": completed,
                "identity_evidence": item["identity_evidence"],
                "adaptation": "exact_copy_plus_invisible_accessible_identity",
                "visible_content_changed": False,
                "scopes": scopes,
                "output_sha256": sha256(target),
            }
        )
        course_details[str(item["code"])] = {
            "variants": [
                {
                    "scopes": scopes,
                    "title": item["title"],
                    "summary": item["summary"],
                    "pdf_url": (
                        "assets/course-specifications/institutional-recovery-20260911/"
                        f"{item['code']}.pdf"
                    ),
                    "specification_code": item["code"],
                    "match_status": "verified",
                    "match_note": item["identity_evidence"],
                }
            ]
        }

    manifest = {
        "schema": "institutional-recovery-v1",
        "recovered_at": "2026-09-11",
        "source": {
            "library": "Google Drive institutional comprehensive course specifications",
            "collection": "توصيف المقررات الشامل/المستويات pdf",
        },
        "selection_rule": (
            "الرمز والعنوان والبرنامج والساعات متطابقة، أو كان نقص الرمز محصورًا في "
            "خانة الغلاف وأمكن إكماله من اسم الملف المؤسسي والخطة المطابقة دون تغيير المحتوى المرئي."
        ),
        "scope_rule": (
            "رُبطت نسخ برنامج القرآن وعلومه فقط؛ لم تُنقل إلى القراءات أو الأنظمة "
            "لأن حقل البرنامج داخل الملفات لا يثبت تلك السياقات."
        ),
        "records": records,
        "counts": {
            "imported_course_identities": len(records),
            "identity_completed_sources": sum(
                bool(record["identity_completion_applied"]) for record in records
            ),
            "linked_plan_appearances": sum(len(item["scopes"]) for item in COURSES),
        },
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "data-entries.json", {"course_details": course_details})
    (output / "README.md").write_text(
        "# استرداد مؤسسي لتوصيفات القرآن وعلومه — 2026-09-11\n\n"
        "تضم الحزمة سبعة توصيفات من المكتبة المؤسسية الشاملة. ثلاثة منها تحمل "
        "رمز المقرر مطبوعًا، وأربعة كان نقص الرمز فيها محصورًا في خانة الغلاف "
        "(خانة فارغة أو عبارة إدارية). اكتملت الهوية من اسم الملف المؤسسي والخطة "
        "المطابقة والعنوان والبرنامج والساعات.\n\n"
        "لم يتغير المحتوى المرئي لملفات PDF. أضيفت هوية نصية غير مرئية وبيانات "
        "وصفية لتحسين الاستخراج الآلي. اقتصرت الروابط على برنامج القرآن وعلومه، "
        "وبقيت سياقات القراءات والأنظمة غير مربوطة حتى يظهر دليل خاص بها.\n",
        encoding="utf-8",
    )
    hashed = [
        *sorted(output.glob("*.pdf")),
        output / "manifest.json",
        output / "data-entries.json",
        output / "README.md",
    ]
    (output / "hashes.sha256").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in hashed),
        encoding="utf-8",
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
