#!/usr/bin/env python3
"""Create a reproducible decision ledger for an external course-PDF review folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path

ARABIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)

IMPORTED = {
    "القرآن الكريم 1.pdf": "2002128-1",
    "القرآن الكريم 2.pdf": "2002129-1",
    "القرآن الكريم 3.pdf": "2002211-1",
    "القرآن الكريم 4.pdf": "2002221-1",
    "القرآن الكريم 5.pdf": "2002311-1",
    "القرآن الكريم 6.pdf": "2002312-1",
    "القرآن الكريم 7.pdf": "2002411-1",
    "القرآن الكريم 8.pdf": "2002421-1",
    "قرآن كريم حفظ وتلاوة 5.pdf": "2002310-2",
    "سفاري (2).pdf": "20041203-2",
}

SCANNED_EXISTING = {
    "قرآن كريم حفظ وتلاوة 1.pdf": "20021105-2",
    "قرآن كريم حفظ وتلاوة 2.pdf": "20021201-2",
    "قرآن كريم حفظ وتلاوة 3.pdf": "20022103-2",
    "قرآن كريم حفظ وتلاوة 4.pdf": "20022203-2",
    "قرآن كريم حفظ وتلاوة 6.pdf": "20023203-2",
    "قرآن كريم حفظ وتلاوة 7.pdf": "20024103-2",
    "قرآن كريم حفظ وتلاوة 8.pdf": "20024203-2",
}

SPECIAL = {
    "2-2002131 علوم القرآن العامة (1).pdf": (
        "not_selected_shared_mapping_ambiguous",
        "توصيف متعدد البرامج يثبت رمز ناتج برنامج واحدًا لكل مخرج، ولا يفصل رموز البرامج؛ أبقيت النسخ النشطة الخاصة بكل برنامج.",
    ),
    "2-2002131 علوم القرآن العامة.pdf": (
        "not_selected_shared_mapping_ambiguous",
        "توصيف متعدد البرامج يثبت رمز ناتج برنامج واحدًا لكل مخرج، ولا يفصل رموز البرامج؛ أبقيت النسخ النشطة الخاصة بكل برنامج.",
    ),
    "2-2002250 أصول التفسير ومناهجه.pdf": (
        "not_selected_shared_mapping_ambiguous",
        "توصيف متعدد البرامج لا يفصل رموز نواتج البرامج في جدول المخرجات؛ أبقيت النسخ النشطة ذات النطاقات البرنامجية المستقلة.",
    ),
    "دراسات في علوم القرآن .pdf": (
        "rejected_identity_conflict",
        "رمز الغلاف 2002235-2 مستخدم في الخطة الحالية لمقرر القرآن الكريم (7)، فلا يجوز ربطه بهذا العنوان.",
    ),
    "دراسات في توجيه القراءات.pdf": (
        "rejected_identity_conflict",
        "اسم الملف لا يطابق اسم المقرر المثبت داخل التوصيف.",
    ),
    "دراسات في طبقات القراء وأسانيدهم.pdf": (
        "rejected_identity_conflict",
        "اسم الملف والساعات لا يطابقان هوية المقرر المثبتة داخل التوصيف أو الخطة.",
    ),
    "دراسات_في_القراءات_الشاذة_وتوجيهها.pdf": (
        "rejected_identity_conflict",
        "الساعات في رمز التوصيف لا تطابق رمز المقرر في الخطة الحالية.",
    ),
    "التجويد 1.pdf": (
        "rejected_identity_conflict",
        "رمز الغلاف 2002102-2 غير موجود في الخطط الحالية، كما أنه يتعارض مع رمز مقرر آخر قريب الاسم.",
    ),
    "ملخص مقررات علوم القرآن.pdf": (
        "rejected_non_specification",
        "الملف ملخص موضوعي وليس توصيف مقرر رسميًا.",
    ),
    "__التفسير التحليلي 2.pdf": (
        "not_linked_code_absent_from_current_plans",
        "يحمل الغلاف رمزًا جديدًا غير موجود في بيانات الخطط الحالية؛ لم يُسقط على رمز الخطة القديمة بالتشابه الاسمي.",
    ),
    "التفسير التحليلي 1.pdf": (
        "not_linked_code_absent_from_current_plans",
        "يحمل الغلاف رمزًا جديدًا غير موجود في بيانات الخطط الحالية؛ لم يُسقط على رمز الخطة القديمة بالتشابه الاسمي.",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=False,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", "ignore")


def page_count(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], check=True, capture_output=True, text=True
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"pdfinfo did not report a page count for {path}")
    return int(match.group(1))


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", "", value)


def extract_code(path: Path, text: str) -> str | None:
    translated = text.translate(ARABIC_DIGITS)
    codes = re.findall(
        r"(?<!\d)(\d{6,9})\s*[-–—ـ]\s*([12348])(?!\d)", translated
    )
    if codes:
        return f"{codes[0][0]}-{codes[0][1]}"
    filename_match = re.match(r"([12348])[-_ ـ](\d{6,9})(?:\D|$)", path.stem)
    if filename_match:
        return f"{filename_match.group(2)}-{filename_match.group(1)}"
    return SCANNED_EXISTING.get(path.name)


def active_source_map(data: dict) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for code, details in data["course_details"].items():
        variants = details.get("variants", [details])
        output[code] = sorted(
            {
                variant["pdf_url"]
                for variant in variants
                if isinstance(variant, dict) and variant.get("pdf_url")
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    data = json.loads((repo_root / "data.json").read_text(encoding="utf-8"))
    active = active_source_map(data)
    plan_codes = {
        course["code"] for program in data["programs"] for course in program["courses"]
    }

    repository_text_hashes: dict[str, list[str]] = {}
    for pdf in sorted((repo_root / "assets/course-specifications").rglob("*.pdf")):
        text = normalized_text(extract_text(pdf))
        if text:
            repository_text_hashes.setdefault(
                hashlib.sha256(text.encode("utf-8")).hexdigest(), []
            ).append(str(pdf.relative_to(repo_root)))

    records = []
    for source in sorted(args.review_dir.glob("*.pdf"), key=lambda item: item.name):
        raw_text = extract_text(source)
        text = normalized_text(raw_text)
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
        code = IMPORTED.get(source.name) or extract_code(source, raw_text)
        record = {
            "source_file": source.name,
            "source_sha256": sha256(source),
            "pages": page_count(source),
            "extracted_code": code,
        }

        if source.name in IMPORTED:
            repository_pdf = (
                repo_root
                / "assets/course-specifications/reviewed-import-20260909"
                / f"{code}.pdf"
            )
            repository_sha256 = sha256(repository_pdf)
            record.update(
                decision="imported_and_linked",
                repository_pdf=str(repository_pdf.relative_to(repo_root)),
                repository_sha256=repository_sha256,
                preparation=(
                    "ocr_text_layer_added_without_visual_content_change"
                    if repository_sha256 != record["source_sha256"]
                    else "copied_without_content_change"
                ),
                reason="توصيف رسمي مطابق لمقرر في الخطة ولا يوجد له توصيف أحدث في قاعدة البيانات.",
            )
        elif source.name in SPECIAL:
            decision, reason = SPECIAL[source.name]
            record.update(decision=decision, reason=reason)
        elif text_hash and repository_text_hashes.get(text_hash):
            record.update(
                decision="already_present_same_normalized_content",
                existing_sources=repository_text_hashes[text_hash],
                reason="المحتوى النصي المطبع مطابق لمصدر محفوظ في المستودع.",
            )
        elif code in active:
            record.update(
                decision="superseded_or_equivalent_active_specification_exists",
                existing_sources=active[code],
                reason="يوجد توصيف نشط موثق للمقرر، وهو أحدث أو مكافئ ومراجع ضمن مسار البرنامج الصحيح.",
            )
        elif code and code not in plan_codes:
            record.update(
                decision="not_linked_code_absent_from_current_plans",
                reason="رمز التوصيف غير موجود في بيانات الخطط الحالية ولم تُجر مطابقة تخمينية بالاسم.",
            )
        else:
            record.update(
                decision="rejected_identity_not_safely_resolved",
                reason="لم تثبت هوية المقرر ورمزه ونطاق برنامجه بما يكفي للربط الآمن.",
            )
        records.append(record)

    counts = Counter(record["decision"] for record in records)
    payload = {
        "schema": "course-specification-review-audit-v1",
        "review_folder": args.review_dir.name,
        "reviewed_at": "2026-09-09",
        "selection_rule": "استيراد التوصيف الرسمي المطابق لخطة حالية فقط عند غياب توصيف أحدث أو مكافئ، ومنع المطابقة الاسمية أو طمس رموز نواتج البرامج المشتركة.",
        "counts": {"reviewed": len(records), **dict(sorted(counts.items()))},
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
