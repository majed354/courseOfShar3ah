#!/usr/bin/env python3
"""Route matching old/new course identities to the audited v47 PDF.

This intentionally does not edit, copy, or delete PDFs.  A course is eligible
only when the old and new variants have the same official course code, title,
credit hours (the code suffix), and academic content.  The v47 audited output
becomes the single published PDF while the former PDF remains in the repository
as an unlinked archival source.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
MANIFEST_PATH = ROOT / "assets/course-specifications/same-identity-unification-20260901.json"
AUDIT_PATH = ROOT / "SAME_IDENTITY_UNIFICATION_AUDIT.md"
DATE = "2026-09-01"


COURSES: dict[str, dict[str, str]] = {
    "2001115-4": {
        "title": "الفقه (1)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001115-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001115-4--sharia-new-v47.pdf",
    },
    "2001116-4": {
        "title": "الفقه (2)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001116-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001116-4--sharia-new-v47.pdf",
    },
    "2001215-4": {
        "title": "الفقه (3)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001215-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001215-4--sharia-new-v47.pdf",
    },
    "2001216-4": {
        "title": "الفقه (4)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001216-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001216-4--sharia-new-v47.pdf",
    },
    "2001311-4": {
        "title": "الفقه (5)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001311-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001311-4--sharia-new-v47.pdf",
    },
    "2001321-4": {
        "title": "الفقه (6)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001321-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001321-4--sharia-new-v47.pdf",
    },
    "2001411-4": {
        "title": "الفقه (7)",
        "archived": "assets/course-specifications/sharia-ba-1445/2001411-4.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001411-4--sharia-new-v47.pdf",
    },
    "2001346-2": {
        "title": "مقاصد الشريعة",
        "archived": "assets/course-specifications/clo-plo-corrections-20260901/2001346-2--sharia-old-v38-v39.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001346-2--sharia-new-v47.pdf",
    },
    "2001465-2": {
        "title": "فقه النوازل",
        "archived": "assets/course-specifications/clo-plo-corrections-20260901/2001465-2--sharia-old-v38-v39.pdf",
        "selected": "assets/course-specifications/clo-plo-corrections-20260901/2001465-2--sharia-new-v47.pdf",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scopes_of(variant: dict[str, Any]) -> list[dict[str, Any]]:
    if variant.get("scopes"):
        return copy.deepcopy(variant["scopes"])
    if variant.get("scope"):
        return [copy.deepcopy(variant["scope"])]
    return []


def normalized_scope(scope: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(scope.get(key, "")) for key in ("program", "degree", "plan_type", "version"))


def merged_scopes(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for variant in variants:
        for scope in scopes_of(variant):
            by_identity.setdefault(normalized_scope(scope), scope)
    order = {"قديمة": 0, "جديدة": 1}
    return sorted(
        by_identity.values(),
        key=lambda scope: (
            order.get(str(scope.get("plan_type", "")), 9),
            str(scope.get("version", "")),
            str(scope.get("program", "")),
        ),
    )


def ensure_expected_scopes(course_code: str, scopes: list[dict[str, Any]]) -> None:
    actual = {
        (scope.get("program"), scope.get("degree"), scope.get("plan_type"), str(scope.get("version")))
        for scope in scopes
    }
    expected = {
        ("الشريعة", "بكالوريوس", "قديمة", "38"),
        ("الشريعة", "بكالوريوس", "قديمة", "39"),
        ("الشريعة", "بكالوريوس", "جديدة", "47"),
    }
    if actual != expected:
        raise RuntimeError(f"Unexpected scope set for {course_code}: {sorted(actual)}")


def write_audit(records: list[dict[str, Any]]) -> None:
    lines = [
        "# تقرير توحيد توصيفات الهوية الواحدة بين الخطتين",
        "",
        f"تاريخ التنفيذ: {DATE}.",
        "",
        "ضابط التنفيذ: الاسم والرمز والساعات والمضمون متفقة داخل برنامج الشريعة، وتُعتمد نسخة الخطة 47 المدققة للمسارات القديمة والجديدة. لم يُحذف أي PDF؛ أصبحت النسخة السابقة أرشيفية غير منشورة فقط.",
        "",
        "| م | الرمز | المقرر | القديم | الجديد الموحّد | النطاقات بعد التوحيد | سبب الاختيار |",
        "|---:|---|---|---|---|---|---|",
    ]
    for index, record in enumerate(records, 1):
        scopes = "<br>".join(
            f"{scope['program']} - {scope['plan_type']} {scope['version']}"
            for scope in record["published_scopes"]
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    f"`{record['course_code']}`",
                    record["title"],
                    f"`{record['archived_pdf']}`",
                    f"`{record['selected_pdf']}`",
                    scopes,
                    "نسخة الخطة 47 هي الأحدث وظيفيًا بعد تدقيق المخرجات والربط في 2026-09-01؛ وعند تعادل تاريخ المراجعة الداخلي تُقدَّم الخطة الأحدث.",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## ملاحظات الحفظ",
            "",
            "- الملفات القديمة باقية في المستودع للاسترجاع والتوثيق، لكنها غير مرتبطة ببطاقات الموقع.",
            "- لم تُوحّد مقررات مختلفة الرمز، ولم تُمس المقررات المشتركة بين برامج مختلفة في هذه المرحلة.",
            "- الربط الظاهر داخل PDF هو ربط الخطة الجديدة، وفق قرار اعتماد النسخة الأحدث على الخطتين.",
        ]
    )
    AUDIT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    previous_manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.exists()
        else {}
    )
    previous_records = {
        record["course_code"]: record for record in previous_manifest.get("records", [])
    }
    records: list[dict[str, Any]] = []
    newly_unified = 0
    already_unified = 0
    variant_count_before = sum(len(detail.get("variants", [])) for detail in data["course_details"].values())

    for course_code, rule in COURSES.items():
        detail = data["course_details"].get(course_code)
        if not detail:
            raise RuntimeError(f"Missing course detail: {course_code}")
        variants = detail.get("variants", [])
        candidates = [
            variant
            for variant in variants
            if variant.get("pdf_url") in {rule["archived"], rule["selected"]}
        ]
        if len(candidates) not in {1, 2}:
            raise RuntimeError(f"Expected one or two variants for {course_code}, found {len(candidates)}")
        for variant in candidates:
            if variant.get("title") != rule["title"]:
                raise RuntimeError(f"Title mismatch for {course_code}: {variant.get('title')}")
            if variant.get("specification_code") != course_code:
                raise RuntimeError(f"Specification code mismatch for {course_code}")

        selected = next(
            (variant for variant in candidates if variant["pdf_url"] == rule["selected"]),
            None,
        )
        if selected is None:
            raise RuntimeError(f"Selected v47 variant is missing for {course_code}")
        archived = next(
            (variant for variant in candidates if variant["pdf_url"] == rule["archived"]),
            None,
        )
        if archived is None:
            previous = previous_records.get(course_code)
            if previous is None:
                raise RuntimeError(f"Archival variant is missing without a prior audit for {course_code}")
            already_unified += 1
        else:
            newly_unified += 1
        scopes = merged_scopes(candidates)
        if archived is None:
            scopes = scopes_of(selected)
        ensure_expected_scopes(course_code, scopes)

        retained = copy.deepcopy(selected)
        retained.pop("scope", None)
        retained["scopes"] = scopes
        note = (
            "ملف موحّد للخطتين القديمة والجديدة؛ اعتمدت نسخة الخطة 47 المدققة بتاريخ "
            "2026-09-01، ويظهر داخل التوصيف ربط الخطة الجديدة فقط. النسخة السابقة محفوظة أرشيفيًا."
        )
        current_note = retained.get("match_note", "").strip()
        if note not in current_note:
            retained["match_note"] = (current_note + " " + note).strip()

        remaining = [variant for variant in variants if variant not in candidates]
        detail["variants"] = remaining + [retained]

        selected_path = ROOT / rule["selected"]
        archived_path = ROOT / rule["archived"]
        if not selected_path.is_file() or not archived_path.is_file():
            raise RuntimeError(f"Missing selected or archival PDF for {course_code}")
        records.append(
            {
                "course_code": course_code,
                "title": rule["title"],
                "program": "الشريعة",
                "degree": "بكالوريوس",
                "archived_pdf": rule["archived"],
                "archived_sha256": sha256(archived_path),
                "selected_pdf": rule["selected"],
                "selected_sha256": sha256(selected_path),
                "published_scopes": scopes,
                "removed_public_variant": (
                    {
                        "pdf_url": archived["pdf_url"],
                        "scopes": scopes_of(archived),
                    }
                    if archived is not None
                    else previous_records[course_code]["removed_public_variant"]
                ),
                "selection_basis": {
                    "plan_version": "47",
                    "audit_date": DATE,
                    "internal_review_date_policy": "عند تعادل التاريخ الداخلي تُقدَّم الخطة الأحدث المدققة.",
                },
            }
        )

    variant_count_after = sum(len(detail.get("variants", [])) for detail in data["course_details"].values())
    if variant_count_before - variant_count_after != newly_unified:
        raise RuntimeError(
            f"Unexpected variant reduction: {variant_count_before} -> {variant_count_after}"
        )

    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "generated_at": DATE,
        "policy": "تعميم أحدث نسخة مدققة على الخطتين عند اتفاق البرنامج والاسم والرمز والساعات والمضمون.",
        "scope": {
            "course_count": len(records),
            "variant_count_before": previous_manifest.get("scope", {}).get(
                "variant_count_before", variant_count_before
            ),
            "variant_count_after": variant_count_after,
            "removed_public_variant_count": len(records),
            "deleted_pdf_count": 0,
            "archived_pdf_count": len(records),
            "different_code_course_count": 0,
        },
        "records": records,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_audit(records)
    print(
        json.dumps(
            {
                "courses": len(records),
                "variants_before": variant_count_before,
                "variants_after": variant_count_after,
                "pdfs_created": 0,
                "pdfs_deleted": 0,
                "newly_unified": newly_unified,
                "already_unified": already_unified,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
