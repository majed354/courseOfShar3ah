#!/usr/bin/env python3
"""Refresh specialty-missing Markdown after the systems-law recovery."""

from __future__ import annotations

import json
import re

from update_specialty_missing_markdown import ROOT, ROW_RE, calculate


TARGET = ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md"
COVERAGE_JSON = (
    ROOT
    / "assets/course-specifications/systems-law-completion-20260915/coverage.json"
)
RECOVERED_CODE = "2003102-3"


def main() -> int:
    required, available, missing_identities, programs = calculate()
    missing = required - available
    actual = (required, available, missing, len(missing_identities))
    expected = (756, 654, 102, 88)
    if actual != expected:
        raise ValueError(f"unexpected recalculated specialty coverage: {actual}")

    text = TARGET.read_text(encoding="utf-8")
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
    removed = False
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            lines.append(line)
            continue
        if match.group(2).strip() == RECOVERED_CODE:
            removed = True
            continue
        numbered += 1
        lines.append(re.sub(r"^\|\s*\d+\s*\|", f"| {numbered} |", line))

    if not removed:
        raise ValueError(f"missing row was not found for {RECOVERED_CODE}")
    if numbered != len(missing_identities):
        raise ValueError(
            f"Markdown rows {numbered} do not match calculated identities "
            f"{len(missing_identities)}"
        )
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    COVERAGE_JSON.write_text(
        json.dumps(
            {
                "date": "2026-09-15",
                "required": required,
                "available": available,
                "missing": missing,
                "coverage": available / required,
                "available_identities": 384,
                "required_identities": 472,
                "missing_identities": len(missing_identities),
                "recovered_codes": [RECOVERED_CODE],
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
