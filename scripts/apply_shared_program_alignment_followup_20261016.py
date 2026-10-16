"""Apply the reviewed follow-up of the shared-program CLO→PLO specialisation.

The package ``shared-program-json-alignment-20261016`` already holds one
decision per (course, programme child, CLO row, scope). This follow-up reads two
sealed review files from the same package and rewrites only:

* ``clos[i].plo_mappings`` entries whose unit decision changed, under the policy
  ``authorized_program_alignment_revision`` (scoped, one PLO at most);
* verbatim CLO text completions transcribed from the hash-matched source PDF,
  under ``verified_extraction_correction_matches_source``;
* the package records, counts and hashes, and the recomputed statistics.

It never touches PDFs, ``document_plo_codes``, ``extracted`` or another
programme's mapping, and it refuses to run when the current state differs from
what the review files expect.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_course_outcomes as verifier  # noqa: E402
from _shared_alignment_test_support import effective_extraction, scope_key  # noqa: E402

BUNDLE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261016"
DECISIONS_PATH = "assets/course-specifications/shared-program-json-alignment-20261016/alignment-decisions.json"
POLICY = "authorized_program_alignment_revision"
TEXT_POLICY = "verified_extraction_correction_matches_source"
ROUND = "followup-2026-10-16"
TYPE_LABEL = {"direct": "direct", "supporting_transfer": "supporting_transfer"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scope_label(scope) -> str:
    return f"{scope['program']} / {scope['degree']} / {scope['plan_type']} {scope['version']}"


def mapped_evidence(variant, row_page, reference, outcome, scope, rationale, alignment_type) -> str:
    return (
        "تكييف ربط JSON مأذون من المستخدم بتاريخ 2026-10-16، وليس استخراجًا من خلية PDF. "
        f"مصدر CLO: {variant['source_pdf']} SHA256={variant['source_sha256']} ص{row_page}. "
        f"مصدر PLO: {reference['source_pdf']} SHA256={reference['source_sha256']} ص{outcome['source_pages'][0]}. "
        f"النطاق: {scope_label(scope)}. الناتج {outcome['code']}: {outcome['text']} "
        f"التعليل: {rationale} نوع العلاقة: {TYPE_LABEL[alignment_type]}. "
        f"مراجعة المتابعة: {ROUND}. سجل القرار: {DECISIONS_PATH}."
    )


def unmapped_evidence(variant, row_page, reference, scope, rationale) -> str:
    return (
        "قرار مراجعة JSON مأذون بتاريخ 2026-10-16 بإبقاء الربط غير محسوم وعدم تخمين رمز. "
        f"مصدر CLO: {variant['source_pdf']} SHA256={variant['source_sha256']} ص{row_page}. "
        f"مرجع PLO المفحوص: {reference['source_pdf']} SHA256={reference['source_sha256']}. "
        f"النطاق: {scope_label(scope)}. السبب: {rationale} "
        f"مراجعة المتابعة: {ROUND}. سجل القرار: {DECISIONS_PATH}."
    )


def end_sentence(text: str) -> str:
    text = " ".join(text.split())
    return text if text.endswith((".", "؟", "!")) else text + "."


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-at", default="2026-10-16T21:00:00+03:00")
    parser.add_argument("--check", action="store_true", help="validate inputs without writing")
    args = parser.parse_args(argv)

    outcomes_path = ROOT / "course-outcomes.json"
    outcomes = load(outcomes_path)
    decisions_doc = load(BUNDLE / "alignment-decisions.json")
    gaps_doc = load(BUNDLE / "remaining-alignment-gaps.json")
    review = load(BUNDLE / "followup-review-decisions.json")
    completions = load(BUNDLE / "clo-text-completions.json")
    references = {r["id"]: r for r in load(BUNDLE / "program-plo-reference.json")["program_versions"]}
    variants = {(code, v["variant_id"]): v for code, c in outcomes["courses"].items() for v in c["variants"]}
    targets = {r["course_code"] for r in decisions_doc["records"]}

    # 1. Verbatim CLO text completions (all children sharing the source row).
    text_changes = 0
    completed = {}
    for item in completions["records"]:
        if item["decision"] != "complete_verbatim":
            continue
        pdf = ROOT / item["source_pdf"]
        if sha256(pdf) != item["source_sha256"]:
            raise SystemExit(f"source hash mismatch for {item['source_pdf']}")
        hits = [
            (code, v) for (code, _), v in variants.items()
            if code == item["course_code"] and v["source_pdf"] == item["source_pdf"]
        ]
        if not hits:
            raise SystemExit(f"no current variant for {item['course_code']} {item['source_pdf']}")
        index = item["clo_index"]
        evidence = (
            f"مراجعة {item['source_pdf']} SHA256={item['source_sha256']} | الصفحات {item['source_page']} | "
            f"نقل حرفي لنص CLO {item['clo_code']} من خلية المصدر المرئية بعد قراءتين مستقلتين متطابقتين؛ "
            f"لا تأليف ولا تعديل للنص. الحالة السابقة: {item['previous_state']}. "
            f"سجل النقل: assets/course-specifications/shared-program-json-alignment-20261016/clo-text-completions.json."
        )
        for code, variant in hits:
            row = effective_extraction(variant)["clos"][index]
            if row["code"] != item["clo_code"]:
                raise SystemExit(f"row code mismatch {code} {index}")
            if row["text"] != item["text_before"]:
                raise SystemExit(f"unexpected current text {code} {index}: {row['text']!r}")
            fields = {
                f"clos[{index}].text": item["text_verbatim"],
                f"clos[{index}].source_status": "present",
                f"clos[{index}].extraction_method": "verified_visual_review",
                f"clos[{index}].confidence": "verified",
            }
            existing = {o["field"] for o in variant["overrides"]}
            for field, value in fields.items():
                if field in existing:
                    raise SystemExit(f"text override path already exists {code} {field}")
                variant["overrides"].append({
                    "field": field,
                    "value": value,
                    "evidence": evidence,
                    "policy": TEXT_POLICY,
                    "reviewed_at": args.reviewed_at,
                })
            completed[(code, variant["variant_id"], index)] = item["text_verbatim"]
            text_changes += 1

    # 2. Unit decisions.
    by_key = {
        (r["course_code"], r["variant_id"], r["clo_index"], scope_key(r["scope"])): r
        for r in decisions_doc["records"]
    }
    changed_rows = 0
    reviewed_rows = 0
    touched_overrides = set()
    for unit in review["units"]:
        final = unit["final"]
        for row_ref in unit["rows"]:
            key = (unit["course_code"], row_ref["variant_id"], unit["clo_index"], scope_key(row_ref["scope"]))
            record = by_key[key]
            if record["program_reference_id"] != unit["program_reference_id"]:
                raise SystemExit(f"programme reference mismatch {key}")
            previous = {k: record[k] for k in ("plo_code", "alignment_type", "confidence", "rationale")}
            if previous != unit["previous"]:
                raise SystemExit(f"stale review input for {key}: {previous!r}")
            reviewed_rows += 1
            record["followup_review"] = {
                "round": ROUND,
                "verdict": unit["verdict"],
                "category": unit["category"],
                "first_reviewer": unit["first_reviewer"],
                "independent_verifier": unit.get("independent_verifier"),
            }
            if (code_text := completed.get((unit["course_code"], row_ref["variant_id"], unit["clo_index"]))):
                record["clo_text_in_json"] = code_text
            if unit["verdict"] == "keep":
                continue
            changed_rows += 1
            record["followup_review"]["previous"] = previous
            reference = references[record["program_reference_id"]]
            variant = variants[unit["course_code"], row_ref["variant_id"]]
            rationale = end_sentence(final["rationale_ar"])
            record.update({
                "plo_code": final["plo_code"],
                "alignment_type": final["alignment_type"],
                "confidence": final["confidence"],
                "rationale": rationale,
            })
            field = f"clos[{unit['clo_index']}].plo_mappings"
            override = next(o for o in variant["overrides"] if o["field"] == field and o.get("policy") == POLICY)
            position = next(i for i, m in enumerate(override["value"]) if m["scope"] == row_ref["scope"])
            mapping = override["value"][position]
            page = mapping["source_page"]
            if final["plo_code"] is None:
                for name in ("selected_plo_text", "selected_plo_pages", "formal_domain_match"):
                    record.pop(name, None)
                if final["alignment_type"] != "unresolved":
                    raise SystemExit(f"null PLO needs unresolved type {key}")
                new_mapping = {
                    "scope": mapping["scope"],
                    "plo_codes": [],
                    "status": "explicitly_unmapped",
                    "confidence": "high" if final["confidence"] == "high" else "low",
                    "source_page": page,
                    "evidence": unmapped_evidence(variant, page, reference, row_ref["scope"], rationale),
                }
            else:
                outcome = next(o for o in reference["outcomes"] if o["code"] == final["plo_code"])
                if final["alignment_type"] not in TYPE_LABEL or final["confidence"] not in {"high", "medium"}:
                    raise SystemExit(f"invalid mapped type/confidence {key}")
                domain = {"1": "ع", "2": "م", "3": "ق"}.get(record["clo_code"][:1])
                record.update({
                    "selected_plo_text": outcome["text"],
                    "selected_plo_pages": outcome["source_pages"],
                    "formal_domain_match": bool(domain) and final["plo_code"].startswith(domain),
                })
                new_mapping = {
                    "scope": mapping["scope"],
                    "plo_codes": [final["plo_code"]],
                    "status": "mapped",
                    "confidence": final["confidence"],
                    "source_page": page,
                    "evidence": mapped_evidence(variant, page, reference, outcome, row_ref["scope"], rationale, final["alignment_type"]),
                }
            override["value"][position] = new_mapping
            touched_overrides.add((unit["course_code"], row_ref["variant_id"], field))

    for code, vid, field in touched_overrides:
        variant = variants[code, vid]
        override = next(o for o in variant["overrides"] if o["field"] == field and o.get("policy") == POLICY)
        override["evidence"] = " | ".join(m["evidence"] for m in override["value"])
        override["reviewed_at"] = args.reviewed_at
        first = re.search(r"SHA256=([a-f0-9]{64})", override["evidence"]).group(1)
        if first != variant["source_sha256"]:
            raise SystemExit(f"evidence order broken {code} {field}")

    # Records whose text was completed but whose unit had no review entry.
    for (code, vid, index), text in completed.items():
        for record in decisions_doc["records"]:
            if (record["course_code"], record["variant_id"], record["clo_index"]) == (code, vid, index):
                record["clo_text_in_json"] = text

    # 3. Package summaries.
    records = decisions_doc["records"]
    counts = Counter(r["alignment_type"] for r in records)
    mapped = sum(1 for r in records if r["plo_code"] is not None)
    unresolved_records = [r for r in records if r["plo_code"] is None]
    summary = decisions_doc["summary"]
    summary["mapped_clo_scope_rows"] = mapped
    summary["unresolved_clo_scope_rows"] = len(unresolved_records)
    summary["alignment_type_counts"] = {k: counts.get(k, 0) for k in ("direct", "supporting_transfer", "unresolved", "preserved_existing")}

    blank_keys = {
        (g["course_code"], g["variant_id"], g["clo_index"], scope_key(g["scope"]))
        for g in gaps_doc["records"] if g["reason_code"] == "CLO_SOURCE_BLANK"
    }
    gap_records = []
    for r in unresolved_records:
        key = (r["course_code"], r["variant_id"], r["clo_index"], scope_key(r["scope"]))
        gap_records.append({
            "course_code": r["course_code"],
            "variant_id": r["variant_id"],
            "original_variant_id": r["original_variant_id"],
            "scope": r["scope"],
            "clo_code": r["clo_code"],
            "clo_index": r["clo_index"],
            "clo_text_in_json": r["clo_text_in_json"],
            "program_reference_id": r["program_reference_id"],
            "rationale": r["rationale"],
            "reason_code": "CLO_SOURCE_BLANK" if key in blank_keys else "NO_SEMANTICALLY_SUITABLE_PROGRAM_PLO",
            "followup_round": ROUND,
        })
    by_program = Counter(g["scope"]["program"] for g in gap_records)
    reasons = Counter(g["reason_code"] for g in gap_records)
    gaps_doc["records"] = gap_records
    gaps_doc["summary"] = {
        "total_unresolved_clo_scope_rows": len(gap_records),
        "blank_source_clo_scope_rows": reasons.get("CLO_SOURCE_BLANK", 0),
        "no_suitable_plo_clo_scope_rows": reasons.get("NO_SEMANTICALLY_SUITABLE_PROGRAM_PLO", 0),
        "by_program": dict(by_program.most_common()),
    }

    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        for message in errors.messages:
            print("ERROR:", message, file=sys.stderr)
        return 1

    print(json.dumps({
        "text_completion_variant_rows": text_changes,
        "reviewed_rows": reviewed_rows,
        "changed_rows": changed_rows,
        "mapped": mapped,
        "unresolved": len(unresolved_records),
        "alignment_type_counts": summary["alignment_type_counts"],
        "gap_summary": gaps_doc["summary"],
        "targets": len(targets),
    }, ensure_ascii=False, indent=1))
    if args.check:
        return 0

    dump(outcomes_path, outcomes)
    dump(BUNDLE / "alignment-decisions.json", decisions_doc)
    dump(BUNDLE / "remaining-alignment-gaps.json", gaps_doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
