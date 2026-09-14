#!/usr/bin/env python3
"""Apply the audited 2026-09-14 cross-program bundle to data.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets" / "course-specifications" / "cross-program-updates-20260914"
EXPECTED_CODES = {
    "20021202-2", "2002220-2", "2002202-2", "2002225-2", "2002226-2",
    "2002228-2", "2002229-2", "2002235-2", "2002236-2", "2002221-2",
    "2002128-1", "2002129-1", "2002211-1", "2002221-1", "2002311-1",
    "2002312-1", "2002411-1", "20022103-2", "20041201-2",
}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).translate(ARABIC_DIGITS)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي").replace("ـ", "")
    return re.sub(r"[^\w]+", "", text).lower()


def scope_key(scope: dict) -> tuple[str, str, str, str]:
    return tuple(str(scope[key]) for key in ("program", "degree", "plan_type", "version"))


def plan_has_identity(data: dict, code: str, title: str, scope: tuple[str, ...]) -> bool:
    return any(
        (program["name"], program["degree"], program["plan_type"], str(program["version"])) == scope
        and any(
            str(course.get("code")) == code
            and normalize(course.get("name")) == normalize(title)
            for course in program.get("courses", [])
        )
        for program in data["programs"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data.json")
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    proposal = json.loads((args.bundle / "data-entries.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    entries = proposal.get("course_details")
    if not isinstance(entries, dict) or set(entries) != EXPECTED_CODES:
        raise ValueError("Unexpected course-code set in data entries")
    if len(manifest.get("records", [])) != 22:
        raise ValueError("Manifest must contain 22 publication records")
    manifest_by_output = {record["output"]: record for record in manifest["records"]}

    for code, detail in entries.items():
        variants = detail.get("variants")
        if not isinstance(variants, list) or not variants:
            raise ValueError(f"{code}: missing variants")
        for variant in variants:
            if variant.get("specification_code") != code:
                raise ValueError(f"{code}: specification_code mismatch")
            url = variant.get("pdf_url")
            if url not in manifest_by_output:
                raise ValueError(f"{code}: URL absent from manifest: {url}")
            target = ROOT / url
            record = manifest_by_output[url]
            if not target.is_file() or sha256(target) != record["output_sha256"]:
                raise ValueError(f"{code}: publication PDF hash mismatch")
            scopes = variant.get("scopes")
            if not isinstance(scopes, list) or not scopes:
                raise ValueError(f"{code}: missing scopes")
            for raw_scope in scopes:
                key = scope_key(raw_scope)
                if not plan_has_identity(data, code, variant.get("title", ""), key):
                    raise ValueError(f"{code}: identity not found in plan scope {key}")

    if args.check:
        print(json.dumps({"codes": len(entries), "variants": sum(len(x["variants"]) for x in entries.values())}))
        return 0

    data["course_details"].update(entries)
    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {len(entries)} course codes; course_details={len(data['course_details'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
