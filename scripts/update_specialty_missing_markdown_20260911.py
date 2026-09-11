#!/usr/bin/env python3
"""Update the published specialty-missing Markdown for the institutional batch."""

from __future__ import annotations

import re
from pathlib import Path

from update_specialty_missing_markdown import ROOT, ROW_RE, calculate


TARGET = ROOT / "قائمة_المقررات_التخصصية_المفقودة_2026-09-10.md"
PARTIAL_ROWS = {
    "2001205-2": "| {n} | 2001205-2 | الحديث (1) | القراءات | القراءات: قديمة 38 | 1 | يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط |",
    "2001209-2": "| {n} | 2001209-2 | الحديث (2) | القراءات | القراءات: قديمة 38 | 1 | يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط |",
    "2001221-2": "| {n} | 2001221-2 | الفقه (1) | القراءات | القراءات: جديدة 47؛ القراءات: قديمة 38 | 2 | يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط |",
    "2001320-2": "| {n} | 2001320-2 | الحديث (3) | القراءات | القراءات: قديمة 38 | 1 | يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط |",
    "2001322-2": "| {n} | 2001322-2 | الفقه (2) | القراءات | القراءات: قديمة 38 | 1 | يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط |",
    "2001330-2": "| {n} | 2001330-2 | أصول الفقه (2) | الأنظمة | الأنظمة: قديمة 38 | 1 | يوجد توصيف مؤسسي لبرنامج القرآن وعلومه فقط |",
}


def main() -> int:
    required, available, missing_identities, programs = calculate()
    missing = required - available
    expected = (756, 635, 121, 100)
    if (required, available, missing, len(missing_identities)) != expected:
        raise ValueError(
            "unexpected recalculated specialty coverage: "
            f"{required, available, missing, len(missing_identities)}"
        )

    text = TARGET.read_text(encoding="utf-8")
    text = re.sub(r"تاريخ الاستخراج: \d{4}-\d{2}-\d{2}\.", "تاريخ الاستخراج: 2026-09-11.", text)
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
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            lines.append(line)
            continue
        code = match.group(2).strip()
        if code == "2001317-2":
            continue
        numbered += 1
        if code in PARTIAL_ROWS:
            line = PARTIAL_ROWS[code].format(n=numbered)
        else:
            line = re.sub(r"^\|\s*\d+\s*\|", f"| {numbered} |", line)
        lines.append(line)

    if numbered != 100:
        raise ValueError(f"unexpected remaining Markdown identity rows: {numbered}")
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"updated {TARGET.name}: {available}/{required}, "
        f"missing appearances={missing}, identities={len(missing_identities)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
