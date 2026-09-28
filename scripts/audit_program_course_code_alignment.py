#!/usr/bin/env python3
"""Compare programme curriculum codes with plan-scoped course specifications.

The report proposes candidates only. It never rewrites source PDFs or JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    text = text.translate(str.maketrans("إأآىة", "ااايه"))
    return re.sub(r"[^\w]+", "", text).casefold()


def specification_variants(record: dict) -> list[dict]:
    return record.get("variants") or [record]


def specification_for_plan(data: dict, code: str, plan: dict) -> dict | None:
    record = data["course_details"].get(code)
    if not record:
        return None
    for variant in specification_variants(record):
        if not variant.get("scopes") and variant.get("specification_code") == code:
            if any(
                course["code"] == code
                and normalize_name(course["name"]) == normalize_name(variant.get("title"))
                for course in plan["courses"]
            ):
                return variant
        for scope in variant.get("scopes") or []:
            if (
                normalize_name(scope.get("program")) == normalize_name(plan["name"])
                and (not scope.get("degree") or scope["degree"] == plan["degree"])
                and scope.get("plan_type") == plan["plan_type"]
                and str(scope.get("version")) == str(plan["version"])
            ):
                return variant
    return None


def audit(data: dict, registry: dict) -> dict:
    plans_by_source: dict[str, list[dict]] = defaultdict(list)
    for plan in data["programs"]:
        digest = (plan.get("program_details") or {}).get("specification_source_sha256")
        if digest:
            plans_by_source[str(digest)].append(plan)

    rows = []
    matrix_orphans = []
    for program in registry["programs"].values():
        for variant in program["variants"]:
            digest = variant["source"]["sha256"]
            curriculum = variant["extracted"].get("curriculum") or []
            plans = plans_by_source.get(digest, [])
            plan_rows = [(plan, course) for plan in plans for course in plan["courses"]]
            plan_codes = {course["code"] for _, course in plan_rows}
            curriculum_codes = {course.get("code") for course in curriculum}
            for matrix in variant["extracted"].get("program_matrix") or []:
                code = matrix.get("course_code")
                if code and code not in curriculum_codes:
                    matrix_orphans.append({"source_sha256": digest, "course_code": code})
            for course in curriculum:
                code = str(course.get("code") or "")
                name = str(course.get("name") or "")
                hours = course.get("hours")
                candidates = []
                code_scoped_specs = [
                    specification_for_plan(data, code, plan)
                    for plan in plans if any(item["code"] == code for item in plan["courses"])
                ]
                if code not in plan_codes:
                    for plan, plan_course in plan_rows:
                        if normalize_name(plan_course["name"]) != normalize_name(name):
                            continue
                        if hours is not None and float(hours) != float(plan_course["hours"]):
                            continue
                        specification = specification_for_plan(data, plan_course["code"], plan)
                        if specification is None:
                            continue
                        candidate = {
                            "code": plan_course["code"],
                            "name": plan_course["name"],
                            "hours": plan_course["hours"],
                            "pdf_url": specification.get("pdf_url"),
                            "match_status": specification.get("match_status"),
                            "program": plan["name"],
                            "degree": plan["degree"],
                            "plan_type": plan["plan_type"],
                            "version": plan["version"],
                        }
                        if not any(existing["code"] == candidate["code"] for existing in candidates):
                            candidates.append(candidate)
                rows.append({
                    "program_name": program["program_name"],
                    "source_sha256": digest,
                    "source_page": course.get("source_page"),
                    "course_code": code,
                    "course_name": name,
                    "hours": hours,
                    "plan_linked": bool(plans),
                    "code_in_linked_plan": code in plan_codes,
                    "code_has_published_specification": code in data["course_details"],
                    "code_has_scoped_specification": any(code_scoped_specs),
                    "candidate_specs": candidates,
                    "target_already_in_curriculum": any(
                        candidate["code"] in curriculum_codes for candidate in candidates
                    ),
                })

    statuses = Counter(
        "plan_code_with_specification" if row["code_in_linked_plan"] and row["code_has_scoped_specification"] else
        "plan_code_without_specification" if row["code_in_linked_plan"] else
        "candidate" if len(row["candidate_specs"]) == 1 else
        "ambiguous" if row["candidate_specs"] else
        "unmapped_program_source" if not row["plan_linked"] else
        "no_scoped_specification_match"
        for row in rows
    )
    return {
        "summary": {
            "programs": len(registry["programs"]),
            "variants": sum(len(program["variants"]) for program in registry["programs"].values()),
            "curriculum_rows": len(rows),
            "matrix_orphans": len(matrix_orphans),
            "statuses": dict(sorted(statuses.items())),
        },
        "rows": rows,
        "matrix_orphans": matrix_orphans,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=ROOT / "data.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(
        json.loads(args.data.read_text(encoding="utf-8")),
        json.loads(args.registry.read_text(encoding="utf-8")),
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
