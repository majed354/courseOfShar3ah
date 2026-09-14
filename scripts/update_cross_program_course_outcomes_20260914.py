#!/usr/bin/env python3
"""Re-extract only the 2026-09-14 cross-program course variants.

The rest of course-outcomes.json, including reviewed override layers, is preserved
byte-for-byte at the Python object level.  Superseded target variants are replaced
because their source PDFs and stable variant identities intentionally changed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from extract_course_outcomes import (
    _excluded_reason,
    _statistics,
    extract_variant_worker,
    load_auxiliary_sources,
    logical_variants,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
OUTCOMES_PATH = ROOT / "course-outcomes.json"
SPECIFICATIONS = ROOT / "assets/course-specifications"
GENERATED_AT = "2026-09-14T22:30:00+03:00"
TARGET_CODES = {
    "20021202-2",
    "2002128-1",
    "2002129-1",
    "2002202-2",
    "20022103-2",
    "2002211-1",
    "2002220-2",
    "2002221-1",
    "2002221-2",
    "2002225-2",
    "2002226-2",
    "2002228-2",
    "2002229-2",
    "2002235-2",
    "2002236-2",
    "2002311-1",
    "2002312-1",
    "2002411-1",
    "20041201-2",
}


def _add_review_statistics(outcomes: dict[str, object]) -> None:
    alignment_counts: dict[str, int] = {}
    review_counts: dict[str, int] = {}
    courses = outcomes["courses"]
    assert isinstance(courses, dict)
    for course in courses.values():
        for variant in course["variants"]:
            alignment = variant.get("source_alignment")
            if isinstance(alignment, dict) and isinstance(alignment.get("status"), str):
                status = alignment["status"]
                alignment_counts[status] = alignment_counts.get(status, 0) + 1
            review = variant.get("source_review")
            if isinstance(review, dict) and isinstance(review.get("status"), str):
                status = review["status"]
                review_counts[status] = review_counts.get(status, 0) + 1
    statistics = outcomes["statistics"]
    assert isinstance(statistics, dict)
    if alignment_counts:
        statistics["source_alignment_counts"] = dict(sorted(alignment_counts.items()))
    if review_counts:
        statistics["source_review_counts"] = dict(sorted(review_counts.items()))


def _write(outcomes: dict[str, object]) -> None:
    temporary = OUTCOMES_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, OUTCOMES_PATH)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--statistics-only", action="store_true")
    args = parser.parse_args()
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_PATH.read_text(encoding="utf-8"))
    if args.statistics_only:
        _add_review_statistics(outcomes)
        _write(outcomes)
        print(json.dumps(outcomes["statistics"], ensure_ascii=False))
        return
    variants = [
        variant
        for variant in logical_variants(data)
        if variant["course_code"] in TARGET_CODES
    ]
    actual_codes = {variant["course_code"] for variant in variants}
    if actual_codes != TARGET_CODES:
        missing = sorted(TARGET_CODES - actual_codes)
        raise RuntimeError(f"target codes missing from data.json: {missing}")
    if len(variants) != 22:
        raise RuntimeError(f"expected 22 target variants, found {len(variants)}")

    auxiliary_lookup, _ = load_auxiliary_sources(ROOT)
    new_courses: dict[str, dict[str, list[dict[str, object]]]] = {}
    for item in variants:
        source_pdf = item["source_pdf"]
        source_sha256 = sha256_file(ROOT / source_pdf)
        payload = {
            **item,
            "repo_root": str(ROOT),
            "auxiliary": auxiliary_lookup.get(source_pdf),
            "source_sha256": source_sha256,
        }
        variant_id, extracted = extract_variant_worker(payload)
        if variant_id != item["variant_id"]:
            raise RuntimeError(f"variant identity changed while extracting {source_pdf}")
        record = {
            "variant_id": variant_id,
            "scopes": item["scopes"],
            "catalog": item["catalog"],
            "source_pdf": source_pdf,
            "source_sha256": source_sha256,
            "extracted": extracted,
            "overrides": [],
        }
        new_courses.setdefault(item["course_code"], {"variants": []})[
            "variants"
        ].append(record)

    for record in new_courses.values():
        record["variants"].sort(key=lambda variant: str(variant["variant_id"]))
    courses = dict(outcomes["courses"])
    courses.update(new_courses)
    outcomes["courses"] = {code: courses[code] for code in sorted(courses)}

    all_pdfs = {
        path.relative_to(ROOT).as_posix()
        for path in SPECIFICATIONS.rglob("*.pdf")
    }
    active_paths = {
        variant["source_pdf"]
        for course in outcomes["courses"].values()
        for variant in course["variants"]
    }
    unknown_active = sorted(active_paths - all_pdfs)
    if unknown_active:
        raise FileNotFoundError(f"active source PDFs are missing: {unknown_active}")
    outcomes["excluded_sources"] = [
        {
            "source_pdf": path,
            "source_sha256": sha256_file(ROOT / path),
            "reason": _excluded_reason(path),
        }
        for path in sorted(all_pdfs - active_paths)
    ]
    outcomes["source_data"]["sha256"] = sha256_file(DATA_PATH)
    outcomes["generated_at"] = GENERATED_AT
    outcomes["source_correction_recommendations"] = [
        item
        for item in outcomes.get("source_correction_recommendations", [])
        if item.get("course_code") not in TARGET_CODES
    ]
    outcomes["statistics"] = _statistics(
        outcomes["courses"], len(outcomes["excluded_sources"])
    )
    _add_review_statistics(outcomes)
    _write(outcomes)
    print(
        json.dumps(
            {
                "course_codes": outcomes["statistics"]["course_codes"],
                "variants": outcomes["statistics"]["variants"],
                "active_pdf_sources": outcomes["statistics"]["active_pdf_sources"],
                "excluded_pdf_sources": outcomes["statistics"]["excluded_pdf_sources"],
                "target_variants": len(variants),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
