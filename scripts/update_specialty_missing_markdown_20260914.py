#!/usr/bin/env python3
"""Update the missing-specialty Markdown after the 2026-09-14 publication."""

from __future__ import annotations

import re

from update_specialty_missing_markdown import ROOT, ROW_RE, calculate


TARGET = ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md"
RECOVERED_CODES = {"2002228-2", "2002229-2", "2002236-2", "20041201-2"}


def main() -> int:
    required, available, missing_identities, programs = calculate()
    missing = required - available
    expected = (756, 639, 117, 96)
    if (required, available, missing, len(missing_identities)) != expected:
        raise ValueError(
            "unexpected recalculated specialty coverage: "
            f"{required, available, missing, len(missing_identities)}"
        )

    text = TARGET.read_text(encoding="utf-8")
    text = re.sub(
        r"تاريخ الاستخراج: \d{4}-\d{2}-\d{2}\.",
        "تاريخ الاستخراج: 2026-09-14.",
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
        raise ValueError(f"not all recovered rows were present: {sorted(RECOVERED_CODES - removed)}")
    if numbered != 96:
        raise ValueError(f"unexpected remaining Markdown identity rows: {numbered}")
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"updated {TARGET.name}: {available}/{required}, "
        f"missing appearances={missing}, identities={len(missing_identities)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
