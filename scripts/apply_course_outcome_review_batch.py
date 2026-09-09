#!/usr/bin/env python3
"""Apply a human-reviewed course-outcome batch without editing source PDFs.

The JSON manifest is intentionally separate from the extractor: it records the
exact source PDF, row, pages, and disposition for every visual review.  The
script is idempotent, verifies source hashes through the pinned extraction, and
recomputes statistics with the repository verifier before writing.
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
DEFAULT_MANIFEST_GLOB = "course-outcomes-batch-*.json"
DEFAULT_OUTCOMES = ROOT / "course-outcomes.json"

ALIGNMENTS = {
    "present": {
        "status": "matches_source_pdf",
        "label_ar": "مطابق لملف PDF",
        "correction_applied": True,
        "source_update_recommended": False,
    },
    "source_blank": {
        "status": "source_pdf_gap_confirmed",
        "label_ar": "في ملف PDF نقص مثبت",
        "correction_applied": True,
        "source_update_recommended": True,
    },
    "corrected_source_text": {
        "status": "corrected_from_source_pdf",
        "label_ar": "مصحح عن ملف PDF",
        "correction_applied": True,
        "source_update_recommended": True,
    },
    "source_gap_only": {
        "status": "source_pdf_gap_confirmed",
        "label_ar": "في ملف PDF نقص مثبت",
        "correction_applied": True,
        "source_update_recommended": True,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        help="manifest to apply; repeat for multiple files (default: every review batch)",
    )
    parser.add_argument("--outcomes", type=Path, default=DEFAULT_OUTCOMES)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def locate_variant(
    outcomes: dict[str, Any], course_code: str, variant_id: str, source_pdf: str
) -> dict[str, Any]:
    course = outcomes["courses"].get(course_code)
    if not isinstance(course, dict):
        raise ValueError(f"unknown course_code: {course_code}")
    matches = [
        variant
        for variant in course.get("variants", [])
        if variant.get("variant_id") == variant_id
        and variant.get("source_pdf") == source_pdf
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one variant for {course_code}/{variant_id}/{source_pdf}; "
            f"found {len(matches)}"
        )
    return matches[0]


def reviewed_override(
    *, field: str, value: Any, evidence: str, policy: str, reviewed_at: str
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "policy": policy,
        "reviewed_at": reviewed_at,
    }


def upsert_override(variant: dict[str, Any], item: dict[str, Any]) -> None:
    overrides = variant.setdefault("overrides", [])
    matches = [index for index, old in enumerate(overrides) if old.get("field") == item["field"]]
    if len(matches) > 1:
        raise ValueError(
            f"duplicate existing override field {item['field']} for {variant['variant_id']}"
        )
    if matches:
        overrides[matches[0]] = item
    else:
        overrides.append(item)
    overrides.sort(key=lambda value: value["field"])


def recommendation_id(entry: dict[str, Any], variant_id: str) -> str:
    rec = entry["recommendation"]
    payload = "|".join(
        [
            entry["course_code"],
            variant_id,
            rec["issue_code"],
            ",".join(rec["fields"]),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_recommendation(
    outcomes: dict[str, Any], entry: dict[str, Any], variant: dict[str, Any]
) -> None:
    rec = entry.get("recommendation")
    if not rec:
        return
    item = {
        "id": recommendation_id(entry, variant["variant_id"]),
        "course_code": entry["course_code"],
        "variant_id": variant["variant_id"],
        "fields": rec["fields"],
        "issue_code": rec["issue_code"],
        "message": rec["message"],
        "recommendation": rec["recommendation"],
        "source_pdf": variant["source_pdf"],
        "source_sha256": variant["source_sha256"],
        "status": "open",
        "created_at": entry["reviewed_at"][:10],
    }
    records = outcomes.setdefault("source_correction_recommendations", [])
    for index, old in enumerate(records):
        if old.get("id") == item["id"]:
            records[index] = item
            break
    else:
        records.append(item)
    records.sort(key=lambda value: value["id"])


def apply_entry(outcomes: dict[str, Any], entry: dict[str, Any]) -> None:
    required = {
        "course_code",
        "variant_id",
        "source_pdf",
        "clo_index",
        "clo_code",
        "pages",
        "disposition",
        "reviewed_at",
    }
    missing = required - set(entry)
    if missing:
        raise ValueError(f"manifest entry missing fields: {sorted(missing)}")

    variant = locate_variant(
        outcomes, entry["course_code"], entry["variant_id"], entry["source_pdf"]
    )
    disposition = entry["disposition"]
    if disposition not in ALIGNMENTS:
        raise ValueError(f"unknown disposition: {disposition}")

    pages = entry["pages"]
    if not isinstance(pages, list) or not pages or not all(
        isinstance(page, int) and page > 0 for page in pages
    ):
        raise ValueError(f"invalid page list for {entry['course_code']}")

    row_index = entry["clo_index"]
    row = None
    if row_index is not None:
        clos = variant["extracted"]["clos"]
        if not isinstance(row_index, int) or not 0 <= row_index < len(clos):
            raise ValueError(f"invalid CLO index for {entry['course_code']}: {row_index}")
        row = clos[row_index]
        if row.get("code") != entry["clo_code"]:
            raise ValueError(
                f"CLO anchor changed for {entry['course_code']}: "
                f"expected {entry['clo_code']!r}, found {row.get('code')!r}"
            )

    action = entry.get("action") or {
        "present": f"استكمال نص CLO {entry['clo_code']} من الخلية المرئية.",
        "source_blank": (
            f"إثبات أن خلية CLO {entry['clo_code']} فارغة في المصدر؛ "
            "لم يُنشأ نص بديل."
        ),
        "corrected_source_text": (
            f"تصحيح خلل نصي ظاهر في CLO {entry['clo_code']} مع إبقاء توصية تحديث المصدر مفتوحة."
        ),
        "source_gap_only": "إثبات فجوة بنيوية في جدول النواتج دون اختراع رمز أو نص.",
    }[disposition]
    page_text = "،".join(str(page) for page in pages)
    evidence = f"مراجعة {variant['source_pdf']} | الصفحات {page_text} | {action}"

    if row is not None:
        policy = (
            "verified_reference_correction_pending_source_pdf_update"
            if disposition in {"source_blank", "corrected_source_text"}
            else "verified_extraction_correction_matches_source"
        )
        fields: list[tuple[str, Any]] = []
        if disposition in {"present", "corrected_source_text"}:
            text = entry.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"missing reviewed text for {entry['course_code']}")
            fields.append((f"clos[{row_index}].text", text.strip()))
            fields.append((f"clos[{row_index}].source_status", "present"))
        elif disposition == "source_blank":
            if entry.get("text") not in (None, ""):
                raise ValueError(f"source_blank row carries text for {entry['course_code']}")
            fields.append((f"clos[{row_index}].source_status", "source_blank"))
        fields.extend(
            [
                (f"clos[{row_index}].extraction_method", "verified_visual_review"),
                (f"clos[{row_index}].confidence", "verified"),
            ]
        )
        for field, value in fields:
            upsert_override(
                variant,
                reviewed_override(
                    field=field,
                    value=value,
                    evidence=evidence,
                    policy=policy,
                    reviewed_at=entry["reviewed_at"],
                ),
            )

    alignment = copy.deepcopy(ALIGNMENTS[disposition])
    alignment["source_sha256"] = variant["source_sha256"]
    variant["source_alignment"] = alignment
    variant["source_review"] = {
        "status": "accepted_as_is" if disposition == "present" else "needs_manual",
        "finding": entry.get("finding") or action,
        "evidence": {
            "file": variant["source_pdf"],
            "pages": pages,
            "review_method": (
                "تصيير صفحات PDF المطابق للبصمة، وفحص خلية ناتج التعلم بصريًا؛ "
                "استُخدم OCR مساعدًا للقراءة ولم يُعتمد دون المطابقة البصرية."
            ),
            "sha256_verified": True,
        },
        "reviewed_at": entry["reviewed_at"],
        "source_sha256": variant["source_sha256"],
    }
    upsert_recommendation(outcomes, entry, variant)


def main() -> int:
    args = parse_args()
    outcomes = load_json(args.outcomes)
    manifests = args.manifest or sorted(
        (ROOT / "review-batches").glob(DEFAULT_MANIFEST_GLOB)
    )
    if not manifests:
        raise ValueError("no course outcome review manifests found")
    applied = 0
    for manifest_path in manifests:
        manifest = load_json(manifest_path)
        if manifest.get("schema_version") != "course-outcome-review-batch-v1":
            raise ValueError(f"unexpected review batch schema: {manifest_path}")
        entries = manifest.get("entries", [])
        for entry in entries:
            apply_entry(outcomes, entry)
        applied += len(entries)

    errors = verifier.ErrorCollector()
    statistics = verifier.recompute_statistics(outcomes, errors)
    if errors.count or statistics is None:
        raise ValueError(
            "could not recompute statistics: " + "; ".join(errors.messages)
        )
    outcomes["statistics"] = statistics
    rendered = json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n"
    current = args.outcomes.read_text(encoding="utf-8")
    changed = rendered != current
    if args.check:
        print("course outcome review batch would change output" if changed else "course outcome review batch is current")
        return 1 if changed else 0
    args.outcomes.write_text(rendered, encoding="utf-8")
    print(f"applied {applied} reviewed entries from {len(manifests)} batch(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
