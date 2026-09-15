#!/usr/bin/env python3
"""Refresh the specialty-missing inventory after the eight-course completion batch."""

from __future__ import annotations

import json
import re

from update_specialty_missing_markdown import ROOT, ROW_RE, calculate


TARGET = ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md"
COVERAGE_JSON = ROOT / "tmp/eight-course-completion-20260915/specialty-coverage.json"
RECOVERED_CODES = {
    "2001113-2",
    "2001160-2",
    "2001424-2",
    "2003220-2",
    "2004205-2",
    "2004209-2",
    "2004403-2",
}


def main() -> int:
    required, available, missing_identities, programs = calculate()
    missing = required - available
    actual = (required, available, missing, len(missing_identities))
    expected = (756, 653, 103, 89)
    if actual != expected:
        raise ValueError(f"unexpected recalculated specialty coverage: {actual}")

    text = TARGET.read_text(encoding="utf-8")
    text = re.sub(
        r"تاريخ الاستخراج: \d{4}-\d{2}-\d{2}\.",
        "تاريخ الاستخراج: 2026-09-15.",
        text,
    )
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

    program_rows: list[dict] = []
    for (program, degree), stats in programs.items():
        missing_count = stats["required"] - stats["available"]
        replacement = (
            f"| {program} | {degree} | {stats['available']}/{stats['required']} | "
            f"{stats['available'] / stats['required']:.2%} | {missing_count} |"
        )
        pattern = rf"^\| {re.escape(program)} \| {re.escape(degree)} \|.*$"
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"program summary row not found: {(program, degree)}")
        program_rows.append(
            {
                "program": program,
                "degree": degree,
                "required": stats["required"],
                "available": stats["available"],
                "missing": missing_count,
                "missing_identities": len(stats["missing_identities"]),
            }
        )

    lines: list[str] = []
    numbered = 0
    removed: set[str] = set()
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            lines.append(line)
            continue
        code = match.group(2).strip()
        if code in RECOVERED_CODES:
            removed.add(code)
            continue
        numbered += 1
        lines.append(re.sub(r"^\|\s*\d+\s*\|", f"| {numbered} |", line))

    if removed != RECOVERED_CODES:
        raise ValueError(f"recovered rows absent: {sorted(RECOVERED_CODES - removed)}")
    if numbered != len(missing_identities):
        raise ValueError(
            f"Markdown rows {numbered} do not match calculated missing identities "
            f"{len(missing_identities)}"
        )
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")

    COVERAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_JSON.write_text(
        json.dumps(
            {
                "date": "2026-09-15",
                "required": required,
                "available": available,
                "missing": missing,
                "coverage": available / required,
                "missing_identities": len(missing_identities),
                "recovered_codes": sorted(RECOVERED_CODES),
                "programs": program_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"updated {TARGET.name}: {available}/{required}, "
        f"missing appearances={missing}, identities={len(missing_identities)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
