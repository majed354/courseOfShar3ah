#!/usr/bin/env python3
"""Validate and add the 2026-09-11 institutional recovery to data.json."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = (
    ROOT / "assets" / "course-specifications" / "institutional-recovery-20260911"
)
EXPECTED_SCOPES = {
    "2001205-2": {("القرآن وعلومه", "بكالوريوس", "قديمة", "39")},
    "2001209-2": {("القرآن وعلومه", "بكالوريوس", "قديمة", "39")},
    "2001221-2": {("القرآن وعلومه", "بكالوريوس", "جديدة", "47")},
    "2001320-2": {("القرآن وعلومه", "بكالوريوس", "قديمة", "39")},
    "2001322-2": {
        ("القرآن وعلومه", "بكالوريوس", "قديمة", "39"),
        ("القرآن وعلومه", "بكالوريوس", "جديدة", "47"),
    },
    "2001317-2": {
        ("القرآن وعلومه", "بكالوريوس", "قديمة", "39"),
        ("القرآن وعلومه", "بكالوريوس", "جديدة", "47"),
    },
    "2001330-2": {
        ("القرآن وعلومه", "بكالوريوس", "قديمة", "39"),
        ("القرآن وعلومه", "بكالوريوس", "جديدة", "47"),
    },
}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_arabic(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).translate(ARABIC_DIGITS)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("ـ", "")
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي")
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE).lower()


def scope_key(scope: dict) -> tuple[str, str, str, str]:
    return tuple(
        str(scope[key]) for key in ("program", "degree", "plan_type", "version")
    )


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def plan_has_identity(data: dict, code: str, title: str, scope: tuple[str, ...]) -> bool:
    title_key = normalize_arabic(title)
    return any(
        (program["name"], program["degree"], program["plan_type"], str(program["version"]))
        == scope
        and any(
            str(course.get("code")) == code
            and normalize_arabic(course.get("name")) == title_key
            for course in program["courses"]
        )
        for program in data["programs"]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data.json")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()

    data = load_json(args.data)
    proposal = load_json(args.bundle / "data-entries.json")
    manifest = load_json(args.bundle / "manifest.json")
    entries = proposal.get("course_details")
    if not isinstance(entries, dict) or set(entries) != set(EXPECTED_SCOPES):
        raise ValueError("Proposal does not contain the expected seven course identities")
    record_codes = {str(record["code"]) for record in manifest.get("records", [])}
    if record_codes != set(EXPECTED_SCOPES):
        raise ValueError("Manifest does not contain the expected seven course identities")
    collisions = sorted(set(EXPECTED_SCOPES).intersection(data["course_details"]))
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
            "assets/course-specifications/institutional-recovery-20260911/"
            f"{code}.pdf"
        )
        if variant.get("pdf_url") != expected_url or not (ROOT / expected_url).is_file():
            raise ValueError(f"{code}: missing or unexpected PDF URL")
        actual = {scope_key(scope) for scope in variant.get("scopes", [])}
        if actual != EXPECTED_SCOPES[code]:
            raise ValueError(f"{code}: unexpected scopes {sorted(actual)}")
        for scope in actual:
            if not plan_has_identity(data, code, str(variant.get("title", "")), scope):
                raise ValueError(f"{code}: identity not found in plan scope {scope}")

    data["course_details"].update(entries)
    args.data.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Added {len(entries)} specifications; course_details={len(data['course_details'])}")


if __name__ == "__main__":
    main()
