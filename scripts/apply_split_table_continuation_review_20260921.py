#!/usr/bin/env python3
"""Re-extract six visually reviewed CLO rows split across adjacent PDF pages."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import extract_course_outcomes as extractor
import verify_course_outcomes as verifier


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "review-batches" / "split-table-continuations-20260921.json"
DEFAULT_OUTCOMES = ROOT / "course-outcomes.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_override(variant: dict[str, Any], item: dict[str, Any]) -> None:
    overrides = variant.setdefault("overrides", [])
    matches = [index for index, old in enumerate(overrides) if old.get("field") == item["field"]]
    if len(matches) > 1:
        raise ValueError(f"duplicate override field {item['field']} for {variant['variant_id']}")
    if matches:
        overrides[matches[0]] = item
    else:
        overrides.append(item)
    overrides.sort(key=lambda value: value["field"])


def reviewed_override(
    field: str,
    value: Any,
    evidence: str,
    reviewed_at: str,
    *,
    pending_source_update: bool = False,
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "policy": (
            "verified_reference_correction_pending_source_pdf_update"
            if pending_source_update
            else "verified_extraction_correction_matches_source"
        ),
        "reviewed_at": reviewed_at,
    }


def upsert_source_recommendation(
    outcomes: dict[str, Any],
    variant: dict[str, Any],
    record: dict[str, Any],
    reviewed_at: str,
) -> None:
    if not record.get("source_update_required"):
        return
    identity = "|".join(
        [
            record["course_code"],
            record["variant_id"],
            f"clos[{record['clo_code']}].plo_mappings",
            "SOURCE_PLO_MAPPING_PENDING_UPDATE",
        ]
    )
    recommendation = {
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "course_code": record["course_code"],
        "variant_id": record["variant_id"],
        "fields": [f"clos[{record['clo_code']}].plo_mappings"],
        "issue_code": "SOURCE_PLO_MAPPING_PENDING_UPDATE",
        "message": record["source_update_reason"],
        "recommendation": (
            "تحديث خلية ربط PLO في صف CLO 3.1 داخل PDF الرسمي لتوافق الربط "
            "المعتمد في JSON، ثم إعادة الاستخراج والتحقق من البصمة."
        ),
        "source_pdf": record["source_pdf"],
        "source_sha256": record["source_sha256"],
        "status": "open",
        "created_at": reviewed_at[:10],
    }
    recommendations = outcomes.setdefault("source_correction_recommendations", [])
    recommendations[:] = [
        item for item in recommendations if item.get("id") != recommendation["id"]
    ]
    recommendations.append(recommendation)
    recommendations.sort(key=lambda item: item["id"])


def locate_variant(outcomes: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    variants = outcomes["courses"][record["course_code"]]["variants"]
    matches = [
        variant
        for variant in variants
        if variant.get("variant_id") == record["variant_id"]
        and variant.get("source_pdf") == record["source_pdf"]
        and variant.get("source_sha256") == record["source_sha256"]
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one pinned variant for {record['course_code']}; found {len(matches)}"
        )
    return matches[0]


def mapping_override(row: dict[str, Any], plo_codes: list[str]) -> list[dict[str, Any]]:
    status = "mapped" if plo_codes else "explicitly_unmapped"
    evidence = (
        "رمز PLO مقروء من الخلية المرئية في صف الاستمرار."
        if plo_codes
        else "خلية PLO فارغة عمدًا في نسخة المقرر المشترك المنقحة."
    )
    return [
        {
            "scope": copy.deepcopy(mapping["scope"]),
            "plo_codes": list(plo_codes),
            "status": status,
            "confidence": "verified",
            "source_page": row["source_page"],
            "evidence": evidence,
        }
        for mapping in row["plo_mappings"]
    ]


def apply_record(
    outcomes: dict[str, Any],
    logical_by_id: dict[str, dict[str, Any]],
    auxiliary: dict[str, Any],
    record: dict[str, Any],
    reviewed_at: str,
) -> None:
    variant = locate_variant(outcomes, record)
    source = ROOT / record["source_pdf"]
    actual_hash = extractor.sha256_file(source)
    if actual_hash != record["source_sha256"]:
        raise ValueError(f"source hash changed for {record['source_pdf']}")
    logical = logical_by_id.get(record["variant_id"])
    if logical is None or logical["source_pdf"] != record["source_pdf"]:
        raise ValueError(f"logical variant anchor changed for {record['course_code']}")
    _, extracted = extractor.extract_variant_worker(
        {
            **logical,
            "repo_root": str(ROOT),
            "auxiliary": auxiliary.get(record["source_pdf"]),
            "source_sha256": actual_hash,
        }
    )
    rows = [row for row in extracted["clos"] if row.get("code") == record["clo_code"]]
    if len(rows) != 1 or rows[0].get("text") != record["clo_text"]:
        raise ValueError(f"reviewed continuation row changed for {record['course_code']}")
    if extracted.get("extraction_status") != "complete":
        raise ValueError(f"continuation extraction remains incomplete for {record['course_code']}")
    variant["extracted"] = extracted

    # A previous local mirror may have appended the missing row manually.  The
    # source-backed row now supersedes that repair and must not appear twice.
    variant["overrides"] = [
        item
        for item in variant.get("overrides", [])
        if not (
            item.get("field") == "clos.append"
            and isinstance(item.get("value"), dict)
            and item["value"].get("code") == record["clo_code"]
        )
    ]
    row_index = extracted["clos"].index(rows[0])
    page_text = "،".join(str(page) for page in record["pages"])
    evidence = (
        f"مراجعة بصرية لملف {record['source_pdf']} المطابق للبصمة {actual_hash} | "
        f"الصفحات {page_text} | صف CLO {record['clo_code']} ممتد بين صفحتين."
    )
    upsert_override(
        variant,
        reviewed_override(
            f"clos[{row_index}].assessment",
            record["direct_assessment"],
            evidence,
            reviewed_at,
        ),
    )
    if "reviewed_plo_codes" in record:
        plo_codes = record["reviewed_plo_codes"]
        pending_source_update = bool(record.get("source_update_required"))
        upsert_override(
            variant,
            reviewed_override(
                f"clos[{row_index}].plo_mappings",
                mapping_override(rows[0], plo_codes),
                evidence,
                reviewed_at,
                pending_source_update=pending_source_update,
            ),
        )
        upsert_override(
            variant,
            reviewed_override(
                f"clos[{row_index}].document_plo_codes",
                list(plo_codes),
                evidence,
                reviewed_at,
                pending_source_update=pending_source_update,
            ),
        )
    source_update_required = bool(record.get("source_update_required"))
    variant["source_alignment"] = {
        "status": (
            "source_pdf_gap_confirmed"
            if source_update_required
            else "matches_source_pdf"
        ),
        "label_ar": (
            "بيانات القاعدة مكتملة؛ PDF بحاجة إلى تعديل"
            if source_update_required
            else "مطابق لملف PDF بعد تصحيح الاستخراج"
        ),
        "correction_applied": True,
        "source_update_recommended": source_update_required,
        "source_sha256": actual_hash,
    }
    variant["source_review"] = {
        "status": "needs_manual" if source_update_required else "accepted_as_is",
        "finding": (
            record["source_update_reason"]
            if source_update_required
            else (
                f"استُعيد صف CLO {record['clo_code']} الذي يبدأ في صفحة ويكتمل جدوله "
                "في الصفحة التالية؛ لا يحتاج PDF إلى تعديل لهذا السبب."
            )
        ),
        "evidence": {
            "file": record["source_pdf"],
            "pages": record["pages"],
            "review_method": (
                "تصيير صفحتي جدول CLO المتجاورتين وفحص الرمز والنص وطريقة "
                "التقييم وخانة PLO بصريًا مع تثبيت بصمة المصدر."
            ),
            "sha256_verified": True,
        },
        "reviewed_at": reviewed_at,
        "source_sha256": actual_hash,
    }
    upsert_source_recommendation(outcomes, variant, record, reviewed_at)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--outcomes", type=Path, default=DEFAULT_OUTCOMES)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = load(args.manifest)
    if manifest.get("schema_version") != "split-table-continuation-review-v1":
        raise ValueError("unexpected split-table review schema")
    outcomes = load(args.outcomes)
    data = load(ROOT / "data.json")
    logical_by_id = {
        variant["variant_id"]: variant for variant in extractor.logical_variants(data)
    }
    auxiliary, _ledger = extractor.load_auxiliary_sources(ROOT)
    for record in manifest["records"]:
        apply_record(outcomes, logical_by_id, auxiliary, record, manifest["reviewed_at"])

    outcomes["extractor"]["script_sha256"] = extractor.sha256_file(
        ROOT / outcomes["extractor"]["script"]
    )
    errors = verifier.ErrorCollector()
    statistics = verifier.recompute_statistics(outcomes, errors)
    if errors.count or statistics is None:
        raise ValueError("statistics failed: " + "; ".join(errors.messages))
    outcomes["statistics"] = statistics
    rendered = json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n"
    changed = rendered != args.outcomes.read_text(encoding="utf-8")
    if args.check:
        print("split-table review would change output" if changed else "split-table review is current")
        return 1 if changed else 0
    args.outcomes.write_text(rendered, encoding="utf-8")
    print(f"applied {len(manifest['records'])} split-table continuation reviews")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
