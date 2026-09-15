#!/usr/bin/env python3
"""Apply the fingerprint- and scope-bound readiness completion batch.

The extractor testimony in ``extracted`` is immutable.  This script adds only
reviewed overrides, records the source-PDF disposition separately, and refuses
to carry any correction across a changed PDF hash or academic scope.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import verify_course_outcomes as verifier


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT
    / "assets"
    / "course-specifications"
    / "targeted-readiness-completion-20260915"
    / "manifest.json"
)
DEFAULT_OUTCOMES = ROOT / "course-outcomes.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reviewed_override(
    field: str,
    value: Any,
    *,
    evidence: str,
    analytical: bool,
    reviewed_at: str,
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "policy": (
            "verified_reference_correction_pending_source_pdf_update"
            if analytical
            else "verified_extraction_correction_matches_source"
        ),
        "reviewed_at": reviewed_at,
    }


def upsert_override(variant: dict[str, Any], item: dict[str, Any]) -> None:
    overrides = variant.setdefault("overrides", [])
    matches = [i for i, old in enumerate(overrides) if old.get("field") == item["field"]]
    if len(matches) > 1:
        raise ValueError(f"duplicate override path {item['field']!r}")
    if matches:
        overrides[matches[0]] = item
    else:
        overrides.append(item)
    overrides.sort(key=lambda value: value["field"])


def locate_variant(outcomes: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    course = outcomes.get("courses", {}).get(record["course_code"])
    if not isinstance(course, dict):
        raise ValueError(f"unknown course {record['course_code']}")
    matches = [
        variant
        for variant in course.get("variants", [])
        if variant.get("variant_id") == record["variant_id"]
        and variant.get("source_pdf") == record["source_pdf"]
        and variant.get("source_sha256") == record["source_sha256"]
    ]
    if len(matches) != 1:
        raise ValueError(f"variant/hash mismatch for {record['course_code']}")
    variant = matches[0]
    source = ROOT / record["source_pdf"]
    if sha256(source) != record["source_sha256"]:
        raise ValueError(f"source file changed for {record['course_code']}")
    if record["scope"] not in variant.get("scopes", []):
        raise ValueError(f"scope mismatch for {record['course_code']}")
    return variant


def mapping_override(
    variant: dict[str, Any], record: dict[str, Any], clo_index: int, plo_codes: list[str]
) -> list[dict[str, Any]]:
    mappings = copy.deepcopy(variant["extracted"]["clos"][clo_index].get("plo_mappings") or [])
    matched = 0
    for mapping in mappings:
        if mapping.get("scope") != record["scope"]:
            continue
        mapping.update(
            {
                "plo_codes": list(plo_codes),
                "status": "mapped" if plo_codes else "explicitly_unmapped",
                "confidence": "verified",
                "source_page": record["program_matrix"]["pages"][0],
                "evidence": record["program_matrix"]["note"],
            }
        )
        matched += 1
    if matched != 1:
        raise ValueError(
            f"expected one scoped PLO row for {record['course_code']} CLO index {clo_index}"
        )
    return mappings


def recommendation_id(record: dict[str, Any]) -> str:
    value = "|".join(
        [
            record["course_code"],
            record["variant_id"],
            record["recommendation"]["issue_code"],
            ",".join(record["recommendation"]["fields"]),
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def upsert_recommendation(
    outcomes: dict[str, Any], record: dict[str, Any], reviewed_at: str
) -> None:
    recommendation = record.get("recommendation")
    if not recommendation:
        return
    item = {
        "id": recommendation_id(record),
        "course_code": record["course_code"],
        "variant_id": record["variant_id"],
        "fields": recommendation["fields"],
        "issue_code": recommendation["issue_code"],
        "message": recommendation["message"],
        "recommendation": recommendation["recommendation"],
        "source_pdf": record["source_pdf"],
        "source_sha256": record["source_sha256"],
        "status": "open",
        "created_at": reviewed_at[:10],
    }
    rows = outcomes.setdefault("source_correction_recommendations", [])
    for index, old in enumerate(rows):
        if old.get("id") == item["id"]:
            rows[index] = item
            break
    else:
        rows.append(item)
    rows.sort(key=lambda value: value["id"])


def apply_record(
    outcomes: dict[str, Any], record: dict[str, Any], reviewed_at: str
) -> None:
    variant = locate_variant(outcomes, record)
    page_text = ",".join(str(page) for page in record["pages"])
    base_evidence = (
        f"مراجعة بصرية لملف {record['source_pdf']} المطابق للبصمة "
        f"{record['source_sha256']} | الصفحات {page_text}."
    )
    for change in record.get("overrides", []):
        evidence = f"{base_evidence} {change['evidence']}"
        upsert_override(
            variant,
            reviewed_override(
                change["field"],
                change["value"],
                evidence=evidence,
                analytical=bool(change.get("analytical")),
                reviewed_at=reviewed_at,
            ),
        )

    for clo_code, plo_codes in (record.get("program_mapping") or {}).items():
        rows = variant["extracted"]["clos"]
        indexes = [index for index, row in enumerate(rows) if row.get("code") == clo_code]
        if len(indexes) != 1:
            raise ValueError(f"CLO anchor mismatch for {record['course_code']} {clo_code}")
        index = indexes[0]
        evidence = (
            f"{base_evidence} استكمال ربط برنامج القرآن وعلومه من مصفوفة البرنامج "
            f"{record['program_matrix']['document']}، الصفحات "
            f"{','.join(str(page) for page in record['program_matrix']['pages'])}، "
            f"البصمة {record['program_matrix']['sha256']}."
        )
        upsert_override(
            variant,
            reviewed_override(
                f"clos[{index}].plo_mappings",
                mapping_override(variant, record, index, plo_codes),
                evidence=evidence,
                analytical=True,
                reviewed_at=reviewed_at,
            ),
        )

    needs_update = bool(record.get("pdf_needs_update"))
    variant["source_alignment"] = {
        "status": "source_pdf_gap_confirmed" if needs_update else "matches_source_pdf",
        "label_ar": (
            "بيانات القاعدة مكتملة؛ PDF بحاجة إلى تعديل"
            if needs_update
            else "مطابق لملف PDF بعد تصحيح الاستخراج"
        ),
        "correction_applied": True,
        "source_update_recommended": needs_update,
        "source_sha256": record["source_sha256"],
    }
    variant["source_review"] = {
        "status": "needs_manual" if needs_update else "accepted_as_is",
        "finding": record["finding"],
        "evidence": {
            "file": record["source_pdf"],
            "pages": record["pages"],
            "review_method": (
                "تصيير صفحات PDF المطابق للبصمة وفحص خلايا CLO وطرق التقويم "
                "وخطة التقويم بصريًا، ثم فصل التصحيح الاستخراجي عن الاستكمال التحليلي."
            ),
            "sha256_verified": True,
        },
        "reviewed_at": reviewed_at,
        "source_sha256": record["source_sha256"],
    }
    upsert_recommendation(outcomes, record, reviewed_at)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--outcomes", type=Path, default=DEFAULT_OUTCOMES)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = load(args.manifest)
    if manifest.get("schema_version") != "targeted-readiness-completion-v1":
        raise ValueError("unexpected manifest schema")
    outcomes = load(args.outcomes)
    for record in manifest["records"]:
        apply_record(outcomes, record, manifest["reviewed_at"])

    errors = verifier.ErrorCollector()
    statistics = verifier.recompute_statistics(outcomes, errors)
    if errors.count or statistics is None:
        raise ValueError("statistics failed: " + "; ".join(errors.messages))
    outcomes["statistics"] = statistics
    rendered = json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n"
    current = args.outcomes.read_text(encoding="utf-8")
    changed = rendered != current
    if args.check:
        print("targeted readiness completion would change output" if changed else "targeted readiness completion is current")
        return 1 if changed else 0
    args.outcomes.write_text(rendered, encoding="utf-8")
    print(f"applied {len(manifest['records'])} targeted readiness records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
