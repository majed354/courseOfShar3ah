#!/usr/bin/env python3
"""Apply a fingerprint-pinned visual recovery of an entire CLO table."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import verify_course_outcomes as verifier


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reviewed_override(field: str, value: Any, evidence: str, reviewed_at: str) -> dict:
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "policy": "verified_extraction_correction_matches_source",
        "reviewed_at": reviewed_at,
    }


def locate_variant(outcomes: dict, record: dict) -> dict:
    matches = [
        variant
        for variant in outcomes["courses"][record["course_code"]]["variants"]
        if variant["variant_id"] == record["variant_id"]
        and variant["source_pdf"] == record["source_pdf"]
    ]
    if len(matches) != 1:
        raise ValueError(f"variant identity mismatch for {record['course_code']}")
    return matches[0]


def reviewed_clos(template: dict, variant: dict, source_pdf: str) -> tuple[list, list]:
    output = []
    warnings = [
        {
            "code": "assessment_plan_missing",
            "message": "no assessment-plan row with both a label and a printed weight was recovered",
        }
    ]
    for index, item in enumerate(template["clos"]):
        assessment = item.get("assessment")
        evidence = (
            f"مراجعة بصرية لجدول النواتج في {source_pdf}، الصفحة 3، "
            f"وجدول التدريس والتقييم في الصفحة 4؛ الصف {item['code']}."
        )
        mappings = [
            {
                "scope": copy.deepcopy(scope),
                "plo_codes": [item["plo_code"]],
                "status": "mapped",
                "confidence": "verified",
                "source_page": 3,
                "evidence": evidence,
            }
            for scope in variant["scopes"]
        ]
        output.append(
            {
                "assessment": assessment,
                "assessment_source_page": 4 if assessment is not None else None,
                "code": item["code"],
                "confidence": "verified",
                "document_plo_codes": [item["plo_code"]],
                "extraction_method": "verified_visual_review",
                "plo_mappings": mappings,
                "source_page": 3,
                "source_status": "present",
                "text": item["text"],
            }
        )
        if assessment is None:
            warnings.append(
                {
                    "clo_code": item["code"],
                    "clo_index": index,
                    "code": "direct_assessment_unresolved",
                    "message": "no unambiguous direct-assessment text was recovered for this CLO",
                    "source_page": 4,
                }
            )
    return output, warnings


def apply_record(outcomes: dict, record: dict, template: dict, reviewed_at: str) -> None:
    variant = locate_variant(outcomes, record)
    source_path = ROOT / record["source_pdf"]
    actual_hash = sha256(source_path)
    if actual_hash != record["source_sha256"] or actual_hash != variant["source_sha256"]:
        raise ValueError(f"source hash mismatch for {record['course_code']}")

    clos, warnings = reviewed_clos(template, variant, record["source_pdf"])
    evidence = (
        f"مراجعة {record['source_pdf']} | الصفحات 1،3،4،6 | "
        "تصيير PDF المطابق للبصمة وفحص الغلاف وجدول النواتج وربطه وجدول الاعتماد بصريًا."
    )
    values = {
        "assessment_plan": [],
        "assessment_plan_complete": False,
        "assessment_plan_total": None,
        "captured_clo_row_count": len(clos),
        "clos": clos,
        "course_name": record["course_name"],
        "course_name_metadata": {
            "confidence": "verified",
            "source_page": 1,
            "extraction_method": "verified_visual_review",
        },
        "extraction_status": "complete",
        "source_clo_row_count": len(clos),
        "source_status": "present",
        "warnings": warnings,
    }
    variant["overrides"] = [
        reviewed_override(field, value, evidence, reviewed_at)
        for field, value in sorted(values.items())
    ]
    variant["source_alignment"] = {
        "status": "matches_source_pdf",
        "label_ar": "مطابق لملف PDF",
        "correction_applied": True,
        "source_update_recommended": bool(
            any(item["code"] == "direct_assessment_unresolved" for item in warnings)
        ),
        "source_sha256": actual_hash,
    }
    variant["source_review"] = {
        "status": "accepted_as_is",
        "finding": "استُعيد جدول CLO كاملًا من المراجعة البصرية للنسخة المصورة.",
        "evidence": {
            "file": record["source_pdf"],
            "pages": [1, 3, 4, 6],
            "review_method": (
                "تصيير صفحات PDF المطابق للبصمة وفحص الغلاف وجدول النواتج "
                "ورموز البرنامج وجدول التدريس والتقييم وصفحة الاعتماد بصريًا."
            ),
            "sha256_verified": True,
        },
        "reviewed_at": reviewed_at,
        "source_sha256": actual_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, default=ROOT / "course-outcomes.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "full-variant-visual-review-v1":
        raise ValueError("unexpected full-variant review schema")
    outcomes = json.loads(args.outcomes.read_text(encoding="utf-8"))
    for record in manifest["records"]:
        apply_record(
            outcomes,
            record,
            manifest["templates"][record["template"]],
            manifest["reviewed_at"],
        )

    errors = verifier.ErrorCollector()
    statistics = verifier.recompute_statistics(outcomes, errors)
    if errors.count or statistics is None:
        raise ValueError("statistics failed: " + "; ".join(errors.messages))
    outcomes["statistics"] = statistics
    rendered = json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n"
    changed = rendered != args.outcomes.read_text(encoding="utf-8")
    if args.check:
        print("full-variant review would change output" if changed else "full-variant review is current")
        return 1 if changed else 0
    args.outcomes.write_text(rendered, encoding="utf-8")
    print(f"applied {len(manifest['records'])} full-variant visual reviews")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
