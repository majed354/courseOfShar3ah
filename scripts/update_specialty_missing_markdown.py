#!/usr/bin/env python3
"""Update the published missing-specialty Markdown after an audited recovery.

Coverage is recalculated from ``data.json``.  The existing human-curated row
order and explanatory text are preserved; only recovered identities are
removed and the affected totals are rewritten.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import extract_course_outcomes as extractor


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md"
RECOVERED_CODES = {
    "2002202-2",
    "2002230-2",
    "2002241-2",
    "2002242-2",
    "2002343-2",
}
ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|")


def scope_matches(left: dict, right: dict) -> bool:
    return all(
        extractor.clean_text(left.get(key)) == extractor.clean_text(right.get(key))
        for key in ("program", "degree", "plan_type", "version")
    )


def is_specialty(course: dict) -> bool:
    code = extractor.clean_text(course.get("code"))
    name = extractor.clean_text(course.get("name"))
    return (
        (code.startswith("200") or code == "101221-2")
        and "الرسالة" not in name
        and "الاختبار الشامل" not in name
    )


def calculate() -> tuple[int, int, set[tuple[str, str]], dict[tuple[str, str], dict]]:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    by_code: dict[str, list[dict]] = defaultdict(list)
    for variant in extractor.logical_variants(data):
        by_code[variant["course_code"]].append(variant)

    required = 0
    available = 0
    missing_identities: set[tuple[str, str]] = set()
    programs: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"required": 0, "available": 0, "missing_identities": set()}
    )
    for program in data["programs"]:
        program_key = (program["name"], program["degree"])
        scope = {
            "program": program["name"],
            "degree": program["degree"],
            "plan_type": program["plan_type"],
            "version": program["version"],
        }
        for course in program["courses"]:
            if not is_specialty(course):
                continue
            required += 1
            programs[program_key]["required"] += 1
            identity = (
                extractor.clean_text(course["code"]),
                extractor.normalize_course_name(course["name"]),
            )
            matched = any(
                extractor.normalize_course_name(course["name"])
                == extractor.normalize_course_name(variant["catalog"].get("title"))
                and any(scope_matches(scope, item) for item in variant["scopes"])
                for variant in by_code[identity[0]]
            )
            if matched:
                available += 1
                programs[program_key]["available"] += 1
            else:
                missing_identities.add(identity)
                programs[program_key]["missing_identities"].add(identity)
    return required, available, missing_identities, programs


def main() -> int:
    required, available, missing_identities, programs = calculate()
    missing = required - available
    if (required, available, missing, len(missing_identities)) != (756, 625, 131, 101):
        raise ValueError("unexpected recalculated specialty coverage")

    text = TARGET.read_text(encoding="utf-8")
    lines = []
    numbered_rows = 0
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if match:
            code = match.group(2).strip()
            if code in RECOVERED_CODES:
                continue
            numbered_rows += 1
            line = re.sub(r"^\|\s*\d+\s*\|", f"| {numbered_rows} |", line)
        lines.append(line)
    if numbered_rows != 101:
        raise ValueError(f"unexpected remaining Markdown identity rows: {numbered_rows}")
    text = "\n".join(lines) + "\n"

    text = re.sub(r"- المتاح: \d+\.", f"- المتاح: {available}.", text)
    text = re.sub(
        r"- المفقود: \d+ موضعًا، تمثل \d+ هوية مقرر فريدة\.",
        f"- المفقود: {missing} موضعًا، تمثل {len(missing_identities)} هوية مقرر فريدة.",
        text,
    )
    text = re.sub(
        r"- نسبة التغطية: \d+\.\d+%\.",
        f"- نسبة التغطية: {available / required:.2%}.",
        text,
    )

    for key in (("الشريعة", "بكالوريوس"), ("الدراسات الإسلامية", "بكالوريوس")):
        stats = programs[key]
        program_missing = stats["required"] - stats["available"]
        replacement = (
            f"| {key[0]} | {key[1]} | {stats['available']}/{stats['required']} | "
            f"{stats['available'] / stats['required']:.2%} | {program_missing} |"
        )
        text, count = re.subn(
            rf"^\| {re.escape(key[0])} \| {re.escape(key[1])} \|.*$",
            replacement,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError(f"program summary row not found: {key}")

    TARGET.write_text(text, encoding="utf-8")
    print(
        f"updated {TARGET.name}: {available}/{required}, "
        f"missing appearances={missing}, identities={len(missing_identities)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
