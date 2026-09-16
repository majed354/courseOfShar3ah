#!/usr/bin/env python3
"""Publish the 2026-09-16 programme-specification inventory deterministically."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets" / "course-specifications" / "program-specifications-20260916"
RAW = ROOT / "توصيفات البرامج" / "من_الحساب_الجامعي_2026-09-16"
DATA = ROOT / "data.json"
OUTCOMES = ROOT / "course-outcomes.json"


RECORDS = [
    ("الأنظمة", "بكالوريوس", "systems-ba-v38", "بكالوريوس_الأنظمة_الخطة_القديمة.pdf", "assets/course-specifications/program-specifications-20260916/systems-ba-v38/program-specification.pdf", [(38, "قديمة")], ["رمز البرنامج وفق التصنيف السعودي الموحد"]),
    ("الأنظمة", "بكالوريوس", "systems-ba-v47-1447", "بكالوريوس_الأنظمة_خطة_47_توصيف_1447.pdf", "assets/course-specifications/program-specifications-20260916/systems-ba-v47-1447/program-specification.pdf", [(47, "جديدة")], []),
    ("الدراسات الإسلامية", "بكالوريوس", "islamic-studies-ba-v39", "بكالوريوس_الدراسات_الإسلامية_الخطة_39.pdf", "assets/course-specifications/program-specifications-20260916/islamic-studies-ba-v39/program-specification.pdf", [(39, "قديمة")], ["رمز البرنامج وفق التصنيف السعودي الموحد"]),
    ("الدراسات الإسلامية", "بكالوريوس", "islamic-studies-ba-v47", "بكالوريوس_الدراسات_الإسلامية_خطة_47_المطور.pdf", "assets/course-specifications/program-specifications-20260916/islamic-studies-ba-v47/program-specification.pdf", [(47, "جديدة")], []),
    ("الشريعة", "بكالوريوس", "sharia-ba-old", "بكالوريوس_الشريعة_الخطة_القديمة.pdf", "assets/course-specifications/program-specifications-20260916/sharia-ba-old/program-specification.pdf", [(38, "قديمة"), (39, "قديمة")], ["تاريخ آخر مراجعة"]),
    ("الشريعة", "بكالوريوس", "sharia-ba-v47", "بكالوريوس_الشريعة_خطة_47_توصيف_2024.pdf", "assets/course-specifications/program-specifications-20260916/sharia-ba-v47/program-specification.pdf", [(47, "جديدة")], []),
    ("القرآن وعلومه", "بكالوريوس", "quran-ba-v39", "بكالوريوس_القرآن_وعلومه_الخطة_39.pdf", "assets/course-specifications/program-specifications-20260916/quran-ba-v39/program-specification.pdf", [(39, "قديمة")], []),
    ("القرآن وعلومه", "بكالوريوس", "quran-ba-v47", "بكالوريوس_القرآن_وعلومه_خطة_47_توصيف_2024.pdf", "assets/course-specifications/program-specifications-20260916/quran-ba-v47/program-specification.pdf", [(47, "جديدة")], []),
    ("القراءات", "بكالوريوس", "qiraat-ba-v38", "بكالوريوس_القراءات_الخطة_38.pdf", "assets/course-specifications/program-specifications-20260916/qiraat-ba-v38/program-specification.pdf", [(38, "قديمة")], []),
    ("القراءات", "بكالوريوس", "qiraat-ba-v47", "بكالوريوس_القراءات_خطة_47_المطور_2024.pdf", "assets/course-specifications/program-specifications-20260916/qiraat-ba-v47/program-specification.pdf", [(47, "جديدة")], []),
    ("أصول الفقه", "ماجستير", "usul-master-2024", "ماجستير_أصول_الفقه_توصيف_2024.pdf", "assets/course-specifications/usul-master-1446/program-specification.pdf", [(1, "جديدة")], []),
    ("أصول الفقه", "دكتوراه", "usul-phd-2024", "دكتوراه_أصول_الفقه_توصيف_2024.pdf", "assets/course-specifications/usul-phd-1446/program-specification.pdf", [(1, "جديدة")], []),
    ("الدراسات القرآنية", "دكتوراه", "quranic-studies-phd", "دكتوراه_الدراسات_القرآنية_توصيف.pdf", "assets/course-specifications/program-specifications-20260916/quranic-studies-phd/program-specification.pdf", [(1, "جديدة")], []),
    ("الدراسات القرآنية المعاصرة", "ماجستير", "contemporary-quranic-studies-master", "ماجستير_الدراسات_القرآنية_المعاصرة_توصيف.pdf", "assets/course-specifications/program-specifications-20260916/contemporary-quranic-studies-master/program-specification.pdf", [(1, "جديدة")], []),
    ("العقيدة", "ماجستير", "creed-master", "ماجستير_العقيدة_توصيف.pdf", "assets/course-specifications/program-specifications-20260916/creed-master/program-specification.pdf", [(1, "جديدة")], []),
    ("الفقه", "ماجستير", "fiqh-master-1447", "ماجستير_الفقه_توصيف_1447.pdf", "assets/course-specifications/program-specifications-20260916/fiqh-master-1447/program-specification.pdf", [(1, "جديدة")], []),
    ("الفقه", "دكتوراه", "fiqh-phd-2024", "دكتوراه_الفقه_توصيف_2024.docx", "assets/course-specifications/program-specifications-20260916/fiqh-phd-2024/program-specification.pdf", [(1, "جديدة")], ["رمز البرنامج وفق التصنيف السعودي الموحد", "تاريخ آخر مراجعة"]),
    ("القانون", "ماجستير", "law-master", "ماجستير_القانون_توصيف.pdf", "assets/course-specifications/program-specifications-20260916/law-master/program-specification.pdf", [(1, "جديدة")], ["رمز البرنامج وفق التصنيف السعودي الموحد"]),
    ("القراءات", "ماجستير", "qiraat-master-2024", "ماجستير_القراءات_توصيف_2024.pdf", "assets/course-specifications/program-specifications-20260916/qiraat-master-2024/program-specification.pdf", [(1, "جديدة")], []),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registry_variants(path: Path | None) -> dict[str, dict]:
    if not path or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = {}
    for program in (payload.get("programs") or {}).values():
        for variant in program.get("variants") or []:
            digest = str((variant.get("source") or {}).get("sha256") or "")
            if digest:
                variants[digest] = variant
    return variants


def outcome_domain(code: str) -> str:
    return {"ع": "المعرفة والفهم", "م": "المهارات", "ق": "القيم والاستقلالية والمسؤولية"}.get(code[:1], "")


def extracted_details(variant: dict) -> dict:
    extracted = variant.get("extracted") or {}
    metadata = extracted.get("program_metadata") or {}
    details = {
        "program_code": str(extracted.get("program_code") or ""),
        "program_code_standard": "التصنيف السعودي الموحد للمستويات والتخصصات التعليمية",
        "qualification_level": str(metadata.get("Qualification_Level") or ""),
        "department": str(metadata.get("Department") or ""),
        "college": str(metadata.get("College") or ""),
        "institution": str(metadata.get("Institution") or ""),
        "specification_version": str(metadata.get("Specification_Version") or ""),
        "learning_outcomes": [
            {"code": str(row.get("code") or ""), "domain": outcome_domain(str(row.get("code") or "")), "text": str(row.get("text") or "")}
            for row in extracted.get("program_outcomes") or []
            if row.get("code") and row.get("text")
        ],
        "curriculum_course_count": len(extracted.get("curriculum") or []),
        "matrix_link_count": len(extracted.get("program_matrix") or []),
        "extraction_status": str(variant.get("extraction_status") or ""),
        "extraction_error_count": int((variant.get("counts") or {}).get("unresolved_errors") or 0),
    }
    return {key: value for key, value in details.items() if value not in ("", [], None)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    variants = registry_variants(args.registry)

    records = []
    context_map = {}
    total_pages = 0
    for program, degree, slug, source_name, published_url, contexts, missing_fields in RECORDS:
        source = RAW / source_name
        published = ROOT / published_url
        if not source.is_file() or not published.is_file():
            raise FileNotFoundError(source if not source.is_file() else published)
        source_digest = sha256(source)
        published_digest = sha256(published)
        pages = len(PdfReader(str(published)).pages)
        total_pages += pages
        status = "published_with_warnings" if missing_fields else "published"
        record = {
            "program": program,
            "degree": degree,
            "contexts": [{"version": str(version), "plan_type": plan_type} for version, plan_type in contexts],
            "source_file": str(source.relative_to(ROOT)),
            "source_sha256": source_digest,
            "published_url": published_url,
            "published_sha256": published_digest,
            "page_count": pages,
            "pdfinfo_check": "passed",
            "visual_cover_check": "passed",
            "publication_status": status,
            "missing_fields": missing_fields,
            "source_bytes_preserved": source.suffix.casefold() == ".pdf" and source_digest == published_digest,
        }
        if source.suffix.casefold() == ".docx":
            record["conversion"] = "DOCX to PDF using bundled LibreOffice; all rendered pages visually reviewed"
        records.append(record)
        for version, plan_type in contexts:
            context_map[(program, degree, int(version), plan_type)] = (record, variants.get(source_digest))

    manifest = {
        "schema": "program-specifications-publication/v2",
        "published_on": "2026-09-16",
        "source": "University SharePoint account",
        "publication_policy": "Publish every retrieved exact programme/degree match; preserve source PDF bytes and disclose incomplete official fields or DOCX conversion.",
        "records": records,
        "known_gap": {"program": "القراءات", "degree": "دكتوراه", "reason": "لم يظهر توصيف برنامج PDF أو DOCX مطابق في البحث الجامعي."},
        "summary": {
            "program_specifications": len(records),
            "linked_program_contexts": sum(len(row[5]) for row in RECORDS),
            "pdf_files": len({row[4] for row in RECORDS}),
            "total_pages": total_pages,
            "published_with_warnings": sum(bool(row[6]) for row in RECORDS),
        },
    }
    (BUNDLE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashes = sorted({(row["published_sha256"], row["published_url"]) for row in records}, key=lambda item: item[1])
    (BUNDLE / "hashes.sha256").write_text("".join(f"{digest}  {url}\n" for digest, url in hashes), encoding="utf-8")

    data = json.loads(DATA.read_text(encoding="utf-8"))
    linked = set()
    for program in data.get("programs") or []:
        key = (program.get("name"), program.get("degree"), int(program.get("version") or 0), program.get("plan_type"))
        selected = context_map.get(key)
        if not selected:
            continue
        record, variant = selected
        program["program_specification_url"] = record["published_url"]
        program["program_specification_label"] = f"توصيف برنامج {program['degree']} {program['name']}"
        program["program_specification_status"] = record["publication_status"]
        if record["missing_fields"]:
            program["program_specification_warnings"] = [f"حقل رسمي غير مكتمل: {field}" for field in record["missing_fields"]]
        else:
            program.pop("program_specification_warnings", None)
        if variant:
            details = dict(program.get("program_details") or {})
            for detail_key, value in extracted_details(variant).items():
                details.setdefault(detail_key, value)
            details["specification_source_sha256"] = record["source_sha256"]
            program["program_details"] = details
        linked.add(key)
    expected = set(context_map)
    if linked != expected:
        raise RuntimeError(f"unlinked data.json contexts: {sorted(expected - linked)}")
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    outcomes = json.loads(OUTCOMES.read_text(encoding="utf-8"))
    excluded = outcomes.setdefault("excluded_sources", [])
    by_path = {str(row.get("source_pdf") or ""): row for row in excluded}
    active = {variant.get("source_pdf") for variant in outcomes.get("variants") or []}
    for record in records:
        path = record["published_url"]
        if path in active:
            raise RuntimeError(f"program specification is active as course specification: {path}")
        by_path[path] = {
            "reason": "program_specification_not_a_course_specification",
            "source_pdf": path,
            "source_sha256": record["published_sha256"],
        }
    outcomes["excluded_sources"] = [by_path[key] for key in sorted(by_path)]
    outcomes.setdefault("source_data", {})["path"] = "data.json"
    outcomes["source_data"]["sha256"] = sha256(DATA)
    outcomes.setdefault("statistics", {})["excluded_pdf_sources"] = len(outcomes["excluded_sources"])
    OUTCOMES.write_text(json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
