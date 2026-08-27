#!/usr/bin/env python3
"""Validate and merge the raw-recovery course entries into ``data.json``.

The merge is deliberately additive: every proposed course code must be absent
from ``course_details``.  This protects specifications already published on the
site, in keeping with the raw-folder policy of recovering missing courses only.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data.json"
DEFAULT_BUNDLE = ROOT / "assets/course-specifications/raw-recovery-20260827"
DEFAULT_MANIFEST = DEFAULT_BUNDLE / "manifest.json"
DEFAULT_RECORD_COPY = DEFAULT_BUNDLE / "data-entries.json"

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_arabic(value: str) -> str:
    """Return a conservative identity key for comparing Arabic plan titles."""

    value = unicodedata.normalize("NFKD", str(value)).translate(ARABIC_DIGITS)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("ـ", "")
    value = re.sub(r"[إأآٱ]", "ا", value)
    value = value.replace("ى", "ي")
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE).lower()


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def scope_key(scope: dict) -> tuple[str, str, str, str]:
    return (
        str(scope["program"]),
        str(scope["degree"]),
        str(scope["plan_type"]),
        str(scope["version"]),
    )


def expected_scopes(data: dict, code: str, title: str) -> set[tuple[str, str, str, str]]:
    title_key = normalize_arabic(title)
    found: set[tuple[str, str, str, str]] = set()
    for program in data.get("programs", []):
        for course in program.get("courses", []):
            if str(course.get("code")) != code:
                continue
            if normalize_arabic(course.get("name", "")) != title_key:
                continue
            found.add(
                (
                    str(program["name"]),
                    str(program["degree"]),
                    str(program["plan_type"]),
                    str(program["version"]),
                )
            )
    return found


def validate_and_prepare(data: dict, proposal: dict, manifest: dict, bundle: Path) -> dict:
    entries = proposal.get("course_details")
    if set(proposal) != {"course_details"} or not isinstance(entries, dict):
        raise ValueError("Proposal must contain exactly one course_details object")
    if len(entries) != 55:
        raise ValueError(f"Expected 55 recovery entries, found {len(entries)}")

    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != 55:
        raise ValueError("The final PDF manifest must contain 55 records")
    match_types = {str(record["code"]): str(record["match_type"]) for record in records}
    if set(match_types) != set(entries):
        raise ValueError("Proposal codes do not match the final PDF manifest")

    existing = data.get("course_details")
    if not isinstance(existing, dict):
        raise ValueError("data.json has no course_details object")
    collisions = sorted(set(existing).intersection(entries))
    if collisions:
        raise ValueError(
            "Refusing to replace existing site specifications: " + ", ".join(collisions)
        )

    prepared = copy.deepcopy(proposal)
    for code, detail in prepared["course_details"].items():
        variants = detail.get("variants")
        if not isinstance(variants, list) or len(variants) != 1:
            raise ValueError(f"{code}: expected exactly one scoped variant")
        variant = variants[0]
        if str(variant.get("specification_code")) != code:
            raise ValueError(f"{code}: specification_code mismatch")

        expected_url = f"assets/course-specifications/raw-recovery-20260827/{code}.pdf"
        if variant.get("pdf_url") != expected_url:
            raise ValueError(f"{code}: unexpected PDF URL")
        if not (ROOT / expected_url).is_file():
            raise FileNotFoundError(ROOT / expected_url)

        expected_status = (
            "adapted_verified"
            if match_types[code] == "approved_code_change_same_identity"
            else "verified"
        )
        variant["match_status"] = expected_status

        actual_scope_set = {scope_key(scope) for scope in variant.get("scopes", [])}
        plan_scope_set = expected_scopes(data, code, variant.get("title", ""))
        if actual_scope_set != plan_scope_set or not actual_scope_set:
            missing = sorted(plan_scope_set - actual_scope_set)
            extra = sorted(actual_scope_set - plan_scope_set)
            raise ValueError(f"{code}: scope mismatch; missing={missing}, extra={extra}")

        forbidden = set(variant).intersection({"match_note", "verification_note", "internal_note"})
        if forbidden:
            raise ValueError(f"{code}: public data contains internal-note fields: {sorted(forbidden)}")

    return prepared


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--record-copy", type=Path, default=DEFAULT_RECORD_COPY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_json(args.data)
    proposal = load_json(args.proposal)
    manifest = load_json(args.manifest)
    prepared = validate_and_prepare(data, proposal, manifest, args.bundle)

    before = len(data["course_details"])
    data["course_details"].update(prepared["course_details"])
    write_json(args.record_copy, prepared)
    write_json(args.data, data)
    after = len(data["course_details"])
    print(f"Added {after - before} missing specifications; course_details={after}")


if __name__ == "__main__":
    main()
