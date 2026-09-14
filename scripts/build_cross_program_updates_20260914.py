#!/usr/bin/env python3
"""Build publication-ready PDFs from the audited cross-program 1446 sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "الاستكمال" / "المقررات المقدمة للأقسام الأخرى"
OUTPUT = ROOT / "assets" / "course-specifications" / "cross-program-updates-20260914"
SOFFICE = Path(
    "/Users/majd/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/bin/override/soffice"
)
PDFTOTEXT = Path("/opt/homebrew/bin/pdftotext")
GENERATED_AT = "2026-09-14T22:30:00+03:00"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def scope(program: str, plan_type: str, version: str) -> dict[str, str]:
    return {
        "program": program,
        "degree": "بكالوريوس",
        "plan_type": plan_type,
        "version": version,
    }


IS_NEW = scope("الدراسات الإسلامية", "جديدة", "47")
IS_OLD = scope("الدراسات الإسلامية", "قديمة", "39")
SH_NEW = scope("الشريعة", "جديدة", "47")
SH_OLD_38 = scope("الشريعة", "قديمة", "38")
SH_OLD_39 = scope("الشريعة", "قديمة", "39")


def record(
    code: str,
    output_name: str,
    source: str,
    scopes: list[dict[str, str]],
    title: str,
    summary: str,
    action: str,
    review_date: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "output_name": output_name,
        "source": source,
        "scopes": scopes,
        "title": title,
        "summary": summary,
        "action": action,
        "review_date": review_date,
    }


IS_NEW_DIR = (
    "المقررات المقدمة لبرنامج الدراسات الاسلامية/توصيفات القران والتجويد"
)
IS_OLD_DIR = (
    "المقررات المقدمة لبرنامج الدراسات الاسلامية/"
    "توصيفات القران الكريم خطة قديمة"
)
SH_NEW_DIR = (
    "المقررات المقدمة لبرنامج الشريعة/"
    "توصيف مقررات القران المقدمة لبرنامج الشريعة (خطة جديدة)"
)
SH_OLD_DIR = (
    "المقررات المقدمة لبرنامج الشريعة/"
    "توصيف مقررات القران المقدمة للشريعة- خطة قديمة"
)


RECORDS = [
    record("20021202-2", "20021202-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/التجويد.pdf", [IS_NEW], "التجويد", "يتناول أحكام تجويد القرآن الكريم بالتفصيل.", "replace", "1446/10/10"),
    record("2002220-2", "2002220-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القرآن الكريم (1).pdf", [IS_NEW], "القرآن الكريم (1)", "يدرّب على تصحيح تلاوة سور الجزء الثلاثين وتسميعها، وتلاوة الجزء الأول من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002202-2", "2002202-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القران الكريم (2) .pdf", [IS_NEW], "القرآن الكريم (2)", "يتناول حفظ الجزء التاسع والعشرين من القرآن الكريم وتجويده وتسميعه، وتلاوة الجزء الثاني.", "replace", "1446/10/10"),
    record("2002225-2", "2002225-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القران الكريم (3).pdf", [IS_NEW], "القرآن الكريم (٣)", "يدرّب على تصحيح تلاوة سور الجزء الثامن والعشرين وتسميعها، وتلاوة الجزء الثالث من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002226-2", "2002226-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القرآن الكريم (4).pdf", [IS_NEW], "القرآن الكريم (٤)", "يدرّب على تصحيح تلاوة سور الجزء السابع والعشرين وتسميعها، وتلاوة الجزء الرابع من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002228-2", "2002228-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القرآن الكريم (5).pdf", [IS_NEW], "القرآن الكريم (٥)", "يتناول حفظ الجزء السادس والعشرين وتصحيحه وتسميعه، وتلاوة الجزء الخامس من القرآن الكريم وتجويده.", "add", "1446/9/1"),
    record("2002229-2", "2002229-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القرآن الكريم (6).pdf", [IS_NEW], "القرآن الكريم (٦)", "يتناول حفظ الجزء الخامس والعشرين وتصحيحه وتسميعه، وتلاوة الجزء السادس من القرآن الكريم وتجويده.", "add", "1446/10/10"),
    record("2002235-2", "2002235-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القرآن الكريم (7).pdf", [IS_NEW], "القرآن الكريم (٧)", "يتناول حفظ سور الجزء الرابع والعشرين وتصحيحها وتسميعها، مع تلاوة الجزء السابع وتجويده.", "replace", "1446/10/10"),
    record("2002236-2", "2002236-2--islamic-studies-new-v47.pdf", f"{IS_NEW_DIR}/القران الكريم (8).pdf", [IS_NEW], "القرآن الكريم (٨)", "يتناول حفظ الجزء الثالث والعشرين وتصحيحه وتسميعه، وتلاوة الجزء الثامن من القرآن الكريم وتجويده.", "add", "1446/10/10"),
    record("2002220-2", "2002220-2--sharia-new-v47.pdf", f"{SH_NEW_DIR}/القرآن الكريم - شريعة (1).pdf", [SH_NEW], "القرآن الكريم (1)", "يدرّب على تصحيح تلاوة سور الجزء الثلاثين وتسميعها، وتلاوة الجزء الأول من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002221-2", "2002221-2--sharia-new-v47.pdf", f"{SH_NEW_DIR}/القران الكريم - شريعة (2).pdf", [SH_NEW], "القرآن الكريم (2)", "يدرّب على تصحيح تلاوة سور الجزء التاسع والعشرين وتسميعها، وتلاوة الجزء الثاني من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002225-2", "2002225-2--sharia-new-v47.pdf", f"{SH_NEW_DIR}/القران الكريم - شريعة (3).pdf", [SH_NEW], "القرآن الكريم (٣)", "يدرّب على تصحيح تلاوة سور الجزء الثامن والعشرين وتسميعها، وتلاوة الجزء الثالث من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002226-2", "2002226-2--sharia-new-v47.pdf", f"{SH_NEW_DIR}/القرآن الكريم (4) - شريعة.pdf", [SH_NEW], "القرآن الكريم (٤)", "يدرّب على تصحيح تلاوة سور الجزء السابع والعشرين وتسميعها، وتلاوة الجزء الرابع من القرآن مع تطبيق أحكام التجويد.", "replace", "1446/10/10"),
    record("2002128-1", "2002128-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القرآن الكريم (1) شريعة خطة قديمة.pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (1)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/10/10"),
    record("2002129-1", "2002129-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القران الكريم (2) شريعة خطة قديمة .pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (2)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/10/10"),
    record("2002211-1", "2002211-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القران الكريم (3) شريعة خطة قديمة.pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (3)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/10/10"),
    record("2002221-1", "2002221-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القرآن الكريم (4) شريعة خطة قديمة.pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (4)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/10/10"),
    record("2002311-1", "2002311-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القرآن الكريم (5) شريعة خطة قديمة.pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (5)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/9/1"),
    record("2002312-1", "2002312-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القرآن الكريم (6) شريعة خطة قديمة.pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (6)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/10/10"),
    record("2002411-1", "2002411-1--sharia-old-v38-v39.pdf", f"{SH_OLD_DIR}/القرآن الكريم (7) شريعة خطة قديمة.pdf", [SH_OLD_38, SH_OLD_39], "القرآن الكريم (7)", "يدرّب المقرر على تلاوة القرآن الكريم تلاوة صحيحة، وحفظ الجزء المقرر، وتطبيق أحكام التجويد ومخارج الحروف وصفاتها.", "replace", "1446/10/10"),
    record("20022103-2", "20022103-2--islamic-studies-old-v39.pdf", f"{IS_OLD_DIR}/قالب توصيف مقرر القرآن الكريم (3)في الدراسات الإسلامية.docx", [IS_OLD], "قرآن كريم حفظ وتلاوة (3)", "يتناول حفظ سور الجزء الثامن والعشرين وتصحيحها وتسميعها، مع تلاوة الجزء الثالث من القرآن الكريم وتجويده.", "replace", "1446/9/1"),
    record("20041201-2", "20041201-2--islamic-studies-old-v39.pdf", f"{IS_OLD_DIR}/التجويد.docx", [IS_OLD], "التجويد", "يهدف المقرر إلى دراسة أحكام تجويد القرآن الكريم بالتفصيل مع التطبيق العملي.", "add", "1444/7/18"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).translate(ARABIC_DIGITS)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي").replace("ـ", "")
    return re.sub(r"[^\w]+", "", text).lower()


def convert_docx(source: Path, temporary: Path) -> Path:
    if not SOFFICE.is_file():
        raise FileNotFoundError(f"Bundled LibreOffice not found: {SOFFICE}")
    out_dir = temporary / "converted"
    profile = temporary / "lo-profile"
    out_dir.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(SOFFICE),
            "--headless",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    converted = out_dir / f"{source.stem}.pdf"
    if not converted.is_file():
        candidates = list(out_dir.glob("*.pdf"))
        if len(candidates) != 1:
            raise RuntimeError(f"DOCX conversion did not create one PDF for {source}")
        converted = candidates[0]
    return converted


def publish_pdf(source: Path, output: Path, temporary: Path) -> tuple[int, int]:
    working_source = convert_docx(source, temporary) if source.suffix.lower() == ".docx" else source
    output.parent.mkdir(parents=True, exist_ok=True)
    # Direct PDF sources are deliberately byte-identical to the files supplied
    # by the user. The visible classification belongs to the official source
    # design and is preserved rather than partially erased from page images.
    shutil.copyfile(working_source, output)
    with pymupdf.open(output) as document:
        classification_pages = sum(
            bool(page.search_for("Restricted") or page.search_for("مقيد"))
            for page in document
        )
        return document.page_count, classification_pages


def catalog_entries() -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in RECORDS:
        url = f"assets/course-specifications/{OUTPUT.name}/{item['output_name']}"
        grouped.setdefault(item["code"], []).append(
            {
                "scopes": item["scopes"],
                "title": item["title"],
                "summary": item["summary"],
                "pdf_url": url,
                "specification_code": item["code"],
                "match_status": "verified",
                "match_note": (
                    "اعتمدت النسخة المرسلة حديثًا بعد مطابقة الرمز والاسم والبرنامج "
                    "والخطة والساعات، مع حفظ محتوى المصدر ووسم التصنيف وبصمته "
                    "(2026-09-14)."
                ),
            }
        )
    return {
        "course_details": {
            code: {"variants": variants}
            for code, variants in sorted(grouped.items())
        }
    }


def source_text(path: Path) -> str:
    if not PDFTOTEXT.is_file():
        raise FileNotFoundError(f"pdftotext not found: {PDFTOTEXT}")
    completed = subprocess.run(
        [str(PDFTOTEXT), "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return completed.stdout


def validate_records() -> None:
    if len(RECORDS) != 22:
        raise ValueError(f"Expected 22 publication records, found {len(RECORDS)}")
    outputs = [item["output_name"] for item in RECORDS]
    if len(set(outputs)) != len(outputs):
        raise ValueError("Duplicate publication output name")
    for item in RECORDS:
        source = SOURCE_ROOT / item["source"]
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.suffix.lower() not in {".pdf", ".docx"}:
            raise ValueError(f"Unexpected source type: {source}")


def build() -> None:
    validate_records()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    current_data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    existing_lineage: dict[str, list[str]] = {}
    existing_manifest_path = OUTPUT / "manifest.json"
    if existing_manifest_path.is_file():
        existing_manifest = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        existing_lineage = {
            str(record["output"]): list(record.get("prior_active_urls", []))
            for record in existing_manifest.get("records", [])
        }
    target_urls_by_code: dict[str, set[str]] = {}
    for item in RECORDS:
        target_urls_by_code.setdefault(item["code"], set()).add(
            f"assets/course-specifications/{OUTPUT.name}/{item['output_name']}"
        )
    manifest_records = []
    with tempfile.TemporaryDirectory(prefix="cross-program-updates-") as temp_name:
        temporary_root = Path(temp_name)
        for index, item in enumerate(RECORDS):
            source = SOURCE_ROOT / item["source"]
            target = OUTPUT / item["output_name"]
            temporary = temporary_root / str(index)
            temporary.mkdir(parents=True)
            page_count, classification_pages = publish_pdf(source, target, temporary)
            text = source_text(target)
            # Arabic PDF text layers often emit the credit suffix before the
            # base code because of bidi ordering (for example ``2- 20021202``).
            # The base identifier is the stable, distinctive part here; the
            # full code was already checked visually during source audit.
            code_base = item["code"].rsplit("-", 1)[0]
            if normalize(code_base) not in normalize(text):
                raise ValueError(f"Published PDF does not expose expected code {item['code']}: {target}")
            current_urls = {
                variant.get("pdf_url")
                for variant in current_data.get("course_details", {})
                .get(item["code"], {})
                .get("variants", [])
                if variant.get("pdf_url")
            }
            prior_urls = sorted(
                {
                    url
                    for url in current_urls
                    if url not in target_urls_by_code[item["code"]]
                }
            )
            if not prior_urls and current_urls & target_urls_by_code[item["code"]]:
                prior_urls = sorted(existing_lineage.get(target.relative_to(ROOT).as_posix(), []))
            manifest_records.append(
                {
                    "code": item["code"],
                    "title": item["title"],
                    "action": item["action"],
                    "scopes": item["scopes"],
                    "review_date_hijri": item["review_date"],
                    "source": source.relative_to(ROOT).as_posix(),
                    "source_sha256": sha256(source),
                    "output": target.relative_to(ROOT).as_posix(),
                    "output_sha256": sha256(target),
                    "page_count": page_count,
                    "classification_preserved": source.suffix.lower() == ".pdf",
                    "classification_text_pages": classification_pages,
                    "source_byte_identical": (
                        source.suffix.lower() == ".pdf" and sha256(source) == sha256(target)
                    ),
                    "prior_active_urls": prior_urls,
                }
            )

    manifest = {
        "schema": "cross-program-course-specification-update-v1",
        "generated_at": GENERATED_AT,
        "selection_rule": (
            "latest exact code+title+program+plan sources from the audited cross-program "
            "folder; the sharia-old Quran 8 code mismatch is excluded"
        ),
        "records": manifest_records,
        "counts": {
            "publication_pdfs": len(manifest_records),
            "replacements": sum(item["action"] == "replace" for item in manifest_records),
            "additions": sum(item["action"] == "add" for item in manifest_records),
            "course_codes": len({item["code"] for item in manifest_records}),
            "program_plan_contexts": sum(len(item["scopes"]) for item in manifest_records),
        },
        "excluded": [
            {
                "code_in_source": "2002412-1",
                "planned_code": "2002421-1",
                "title": "القرآن الكريم (8)",
                "reason": "course-code digit transposition; not safe to replace automatically",
            }
        ],
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT / "data-entries.json").write_text(
        json.dumps(catalog_entries(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUTPUT / "README.md").write_text(
        "# تحديث توصيفات المقررات المقدمة للأقسام الأخرى\n\n"
        "تضم الحزمة 22 نسخة نشر: 18 ترقية لسياقات منشورة وأربعة توصيفات "
        "مفقودة. حُفظت ملفات PDF المرسلة كما هي ببصماتها ووسم التصنيف، وحُوّل "
        "مصدرا Word إلى PDF دون تغيير المحتوى. استُبعد قرآن (8) للشريعة القديمة "
        "حتى حسم اختلاف الرمز.\n",
        encoding="utf-8",
    )
    hash_targets = sorted(OUTPUT.glob("*.pdf")) + [
        OUTPUT / "data-entries.json",
        OUTPUT / "manifest.json",
        OUTPUT / "README.md",
    ]
    (OUTPUT / "hashes.sha256").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in hash_targets),
        encoding="utf-8",
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate sources without writing")
    args = parser.parse_args()
    validate_records()
    if args.check:
        print(json.dumps({"records": len(RECORDS), "sources": "ok"}, ensure_ascii=False))
        return 0
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
