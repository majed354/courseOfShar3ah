#!/usr/bin/env python3
"""Validate and add the reviewed Drive-omnibus specifications to data.json."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    ROOT
    / "assets"
    / "course-specifications"
    / "university-omnibus-recovery-20260910"
)
EXPECTED_CODES = {
    "2002202-2",
    "2002230-2",
    "2002241-2",
    "2002242-2",
    "2002343-2",
}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_arabic(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).translate(ARABIC_DIGITS)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("ـ", "")
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي")
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE).lower()


def scope_key(scope: dict) -> tuple[str, str, str, str]:
    return (
        str(scope["program"]),
        str(scope["degree"]),
        str(scope["plan_type"]),
        str(scope["version"]),
    )


def expected_scopes(data: dict, code: str, title: str) -> set[tuple[str, str, str, str]]:
    title_key = normalize_arabic(title)
    return {
        (
            str(program["name"]),
            str(program["degree"]),
            str(program["plan_type"]),
            str(program["version"]),
        )
        for program in data["programs"]
        for course in program["courses"]
        if str(course.get("code")) == code
        and normalize_arabic(course.get("name")) == title_key
    }


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data.json")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()

    data = load_json(args.data)
    proposal = load_json(args.bundle / "data-entries.json")
    manifest = load_json(args.bundle / "manifest.json")
    entries = proposal.get("course_details")
    if not isinstance(entries, dict) or set(entries) != EXPECTED_CODES:
        raise ValueError("Proposal does not contain the expected five course identities")
    record_codes = {str(record["code"]) for record in manifest.get("records", [])}
    if record_codes != EXPECTED_CODES:
        raise ValueError("Manifest does not contain the expected five course identities")
    collisions = sorted(EXPECTED_CODES.intersection(data["course_details"]))
    if collisions:
        raise ValueError("Refusing to replace existing specifications: " + ", ".join(collisions))

    for code, detail in entries.items():
        variants = detail.get("variants")
        if not isinstance(variants, list) or len(variants) != 1:
            raise ValueError(f"{code}: expected one variant")
        variant = variants[0]
        if variant.get("specification_code") != code:
            raise ValueError(f"{code}: specification_code mismatch")
        expected_url = (
            "assets/course-specifications/university-omnibus-recovery-20260910/"
            f"{code}.pdf"
        )
        if variant.get("pdf_url") != expected_url or not (ROOT / expected_url).is_file():
            raise ValueError(f"{code}: missing or unexpected PDF URL")
        actual = {scope_key(scope) for scope in variant.get("scopes", [])}
        expected = expected_scopes(data, code, str(variant.get("title", "")))
        if not expected or actual != expected:
            raise ValueError(
                f"{code}: scope mismatch; missing={sorted(expected - actual)}, "
                f"extra={sorted(actual - expected)}"
            )

    data["course_details"].update(entries)
    args.data.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Added {len(entries)} specifications; course_details={len(data['course_details'])}")


if __name__ == "__main__":
    main()
