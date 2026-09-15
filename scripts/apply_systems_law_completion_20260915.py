#!/usr/bin/env python3
"""Publish the audited systems-law recovery from the two 2026-09-15 bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import verify_course_outcomes as verifier


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data.json"
OUTCOMES = ROOT / "course-outcomes.json"
SOURCE_PDF = (
    "assets/course-specifications/systems-law-completion-20260915/"
    "2003102-3--from-2003417-3.pdf"
)
SOURCE_SHA256 = "3c85b65ab0a9284012a85346ffe65e7c0cbc340a715a07b4bacacb913856b0b2"
REVIEWED_AT = "2026-09-15T14:15:00+03:00"
SCOPE = {
    "program": "الأنظمة",
    "degree": "بكالوريوس",
    "plan_type": "جديدة",
    "version": "47",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reviewed_override(field: str, value: Any, *, pending_pdf_update: bool = False) -> dict:
    return {
        "field": field,
        "value": value,
        "evidence": (
            f"مراجعة بصرية للمصدر {SOURCE_PDF} (SHA-256 {SOURCE_SHA256})، "
            "الصفحات 1 و3–8؛ طوبق الغلاف والساعات والمستوى والبرنامج وجدول CLO "
            "ورموز PLO وخطة التقويم. المصدر المقتطع هو الصفحات 87–94 من الملف الجامع."
        ),
        "policy": (
            "verified_reference_correction_pending_source_pdf_update"
            if pending_pdf_update
            else "verified_extraction_correction_matches_source"
        ),
        "reviewed_at": REVIEWED_AT,
    }


def update_data() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    source_path = ROOT / SOURCE_PDF
    if sha256(source_path) != SOURCE_SHA256:
        raise ValueError("systems-law output PDF hash mismatch")
    entry = {
        "variants": [
            {
                "scopes": [SCOPE],
                "title": "قانون العمل والتأمينات الاجتماعية",
                "summary": (
                    "يعرّف بنظامي العمل والتأمينات الاجتماعية وعقد العمل وأطرافه "
                    "وحقوقهم والتزاماتهم، ويعالج المنازعات العمالية والفئات الخاضعة "
                    "للتأمينات والاستثناءات النظامية."
                ),
                "pdf_url": SOURCE_PDF,
                "specification_code": "2003102-3",
                "match_status": "reviewed_adaptation",
                "match_note": (
                    "إعادة ترميز موثقة داخل خطة الأنظمة المطورة: المصدر يحمل الرمز "
                    "2003417-3 والعنوان «نظام العمل والتأمينات الاجتماعية»، بينما خطة "
                    "الإصدار 47 تحمل 2003102-3 «قانون العمل والتأمينات الاجتماعية». "
                    "البرنامج والمستوى السابع والساعات الثلاثة والمحتوى متطابقة؛ بقيت "
                    "توصية تحديث غلاف PDF بالرمز والعنوان الجديدين مفتوحة."
                ),
            }
        ]
    }
    existing = data["course_details"].get("2003102-3")
    if existing is not None and existing != entry:
        raise ValueError("course_details[2003102-3] already exists with different content")
    data["course_details"]["2003102-3"] = entry
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("published data.json route for 2003102-3")


CLOS = [
    (
        "1.1",
        "أن يفهم الطالب المصطلحات القانونية الواردة في هذا المقرر كعقد العمل، صاحب العمل، العامل، الحدث، العمل المؤقت، العمل العرضي، العمل الموسمي، العمل لبعض الوقت، الأجر الأساسي، الأجر الفعلي، العمولة، البدلات، المنحة أو المكافأة، الميزات العينية.",
        "ع1",
        "الاختبارات النظرية، تقييم الواجبات.",
        4,
    ),
    (
        "1.2",
        "أن يستنبط ويوضح الأحكام القانونية المتعلقة بنظام العمل من حيث بيان مصادره وخصائصه، آثاره، وقف عقد العمل وانقضائه.",
        "ع2",
        "الاختبارات النظرية، تقييم التكليفات.",
        4,
    ),
    (
        "1.3",
        "أن يعرف الطالب أوجه الفرق بين عقود العمل الفردية والجماعية وعقد الشركة والمقاولة والبيع والوكالة.",
        "ع3",
        "الاختبارات النهائية وواجبات منزلية وأبحاث (سواء جماعية أم فردية).",
        4,
    ),
    (
        "2.1",
        "أن يطبق الطالب القواعد القانونية تطبيقاً يتفق وصحيح القانون فيما يتعلق بالمنازعات العمالية.",
        "م1",
        "الاختبار والأعمال الفصلية.",
        4,
    ),
    (
        "2.2",
        "أن يقارن الطالب بين عقد العمل بشرط التجربة وعقد التأهيل والتدريب.",
        "م2",
        "الاختبارات، وطرح القضايا وضرب الأمثلة واختبار قدرة الطالب على الإلمام بمضمونها واقتراح الحلول المناسبة.",
        4,
    ),
    (
        "2.3",
        "أن يفسر النصوص القانونية بنظامي العمل والتأمينات الاجتماعية تفسيراً سليماً لاستنباط الأحكام القانونية منها.",
        "م3",
        "الاختبارات، وطرح القضايا وضرب الأمثلة واختبار قدرة الطالب على الإلمام بمضمونها واقتراح الحلول المناسبة.",
        4,
    ),
    (
        "3.1",
        "أن يتحلى بأخلاقيات المهنة ومراعاة أنظمتها والنزاهة والأخلاق الأكاديمية والالتزام بالسلوك المهني القويم.",
        "ق1",
        "عقد جلسات الحوار والمناقشة للتحقق من مدى استيعاب الطلاب للقيم المستهدفة من المقرر.",
        5,
    ),
    (
        "3.2",
        "التواصل الفعال مع الآخرين في المشاريع والمبادرات المشتركة والعمل بروح الفريق، وتحمل المسؤولية من خلال العمل الجماعي.",
        "ق2",
        "عقد جلسات الحوار والمناقشة للتحقق من مدى استيعاب الطلاب للقيم المستهدفة من المقرر.",
        5,
    ),
    (
        "3.3",
        "أن يتحلى بأخلاقيات المهنة ومراعاة أنظمتها والنزاهة والأخلاق الأكاديمية والالتزام بالسلوك المهني القويم.",
        "ق1",
        "عقد جلسات الحوار والمناقشة للتحقق من مدى استيعاب الطلاب للقيم المستهدفة من المقرر.",
        5,
    ),
]


def reviewed_clos() -> list[dict]:
    output = []
    for code, text, plo, assessment, page in CLOS:
        output.append(
            {
                "assessment": assessment,
                "assessment_source_page": page,
                "code": code,
                "confidence": "verified",
                "document_plo_codes": [plo],
                "extraction_method": "verified_visual_review",
                "plo_mappings": [
                    {
                        "confidence": "verified",
                        "evidence": "رمز PLO مقروء في خلية الصف نفسه في جدول نواتج المقرر.",
                        "plo_codes": [plo],
                        "scope": SCOPE,
                        "source_page": page,
                        "status": "mapped",
                    }
                ],
                "source_page": page,
                "source_status": "present",
                "text": text,
            }
        )
    return output


def apply_reviews() -> None:
    outcomes = json.loads(OUTCOMES.read_text(encoding="utf-8"))
    variants = outcomes["courses"]["2003102-3"]["variants"]
    matches = [item for item in variants if item["source_pdf"] == SOURCE_PDF]
    if len(matches) != 1:
        raise ValueError("could not locate unique 2003102-3 systems-law variant")
    variant = matches[0]
    if variant["source_sha256"] != SOURCE_SHA256 or sha256(ROOT / SOURCE_PDF) != SOURCE_SHA256:
        raise ValueError("source hash changed before review")
    if variant["scopes"] != [SCOPE]:
        raise ValueError("unexpected scope for 2003102-3")

    plan = [
        {"confidence": "verified", "label": "التكليفات والواجبات أثناء الفصل الدراسي", "source_page": 7, "weight": 10},
        {"confidence": "verified", "label": "الاختبار الدوري", "source_page": 7, "weight": 30},
        {"confidence": "verified", "label": "الاختبار النهائي", "source_page": 7, "weight": 60},
    ]
    values = {
        "assessment_plan": plan,
        "assessment_plan_complete": True,
        "assessment_plan_total": 100,
        "captured_clo_row_count": 9,
        "clos": reviewed_clos(),
        "course_name": "قانون العمل والتأمينات الاجتماعية",
        "course_name_metadata": {
            "confidence": "verified",
            "extraction_method": "verified_visual_review",
            "source_page": 1,
        },
        "extraction_status": "complete",
        "source_clo_row_count": 9,
        "source_status": "present",
        "warnings": [],
    }
    variant["overrides"] = [
        reviewed_override(field, value, pending_pdf_update=(field == "course_name"))
        for field, value in sorted(values.items())
    ]
    variant["source_alignment"] = {
        "status": "source_pdf_gap_confirmed",
        "label_ar": "بيانات القاعدة مكتملة؛ PDF بحاجة إلى تحديث الغلاف",
        "correction_applied": True,
        "source_update_recommended": True,
        "source_sha256": SOURCE_SHA256,
    }
    variant["source_review"] = {
        "status": "needs_manual",
        "finding": (
            "المصدر الحديث يثبت المحتوى والساعات والمستوى والبرنامج، لكنه ما زال يحمل "
            "الرمز السابق 2003417-3 والعنوان «نظام العمل والتأمينات الاجتماعية». يلزم "
            "تحديث الغلاف إلى 2003102-3 «قانون العمل والتأمينات الاجتماعية». حُفظ تكرار "
            "نص CLO 3.3 المطابق لـ3.1 كما طُبع دون اختراع تصحيح."
        ),
        "evidence": {
            "file": SOURCE_PDF,
            "pages": [1, 3, 4, 5, 6, 7, 8],
            "review_method": (
                "تصيير الصفحات وفحص الغلاف والساعات والمستوى والوصف وجدول CLO وربط PLO "
                "وطرق التقويم وخطته وصفحة الاعتماد بصريًا."
            ),
            "sha256_verified": True,
        },
        "reviewed_at": REVIEWED_AT,
        "source_sha256": SOURCE_SHA256,
    }
    recommendations = [
        item
        for item in outcomes.get("source_correction_recommendations", [])
        if item.get("course_code") != "2003102-3"
    ]
    recommendation_id = hashlib.sha256(
        (
            "2003102-3|"
            + variant["variant_id"]
            + "|course_name|specification_code|2026-09-15"
        ).encode("utf-8")
    ).hexdigest()
    recommendations.append(
        {
            "id": recommendation_id,
            "course_code": "2003102-3",
            "variant_id": variant["variant_id"],
            "fields": ["course_name", "specification_code"],
            "issue_code": "SOURCE_PDF_IDENTITY_UPDATE_REQUIRED",
            "message": (
                "غلاف المصدر يحمل 2003417-3 «نظام العمل والتأمينات الاجتماعية»، "
                "بينما الهوية المعتمدة في خطة الأنظمة 47 هي 2003102-3 «قانون العمل "
                "والتأمينات الاجتماعية»."
            ),
            "recommendation": (
                "إصدار PDF رسمي جديد يحدّث الرمز والعنوان على الغلاف، مع إبقاء "
                "المحتوى والساعات والمستوى وجدول CLO كما في النسخة المراجعة."
            ),
            "source_pdf": SOURCE_PDF,
            "source_sha256": SOURCE_SHA256,
            "status": "open",
            "created_at": "2026-09-15",
        }
    )
    outcomes["source_correction_recommendations"] = sorted(
        recommendations, key=lambda item: item["id"]
    )

    errors = verifier.ErrorCollector()
    statistics = verifier.recompute_statistics(outcomes, errors)
    if errors.count or statistics is None:
        raise ValueError("statistics failed: " + "; ".join(errors.messages))
    outcomes["statistics"] = statistics
    OUTCOMES.write_text(
        json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("applied fingerprint-pinned visual review for 2003102-3")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("data", "reviews"))
    args = parser.parse_args()
    update_data() if args.stage == "data" else apply_reviews()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
