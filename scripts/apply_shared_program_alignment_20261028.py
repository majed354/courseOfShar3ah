"""Write the reviewed programme links for the eleven courses split on 2026-10-28.

Reads ``review-decisions.json`` (one sealed decision per CLO × programme
version) from the 2026-10-28 package and writes, for every programme copy and
CLO row, one ``clos[i].plo_mappings`` override with the policy
``authorized_program_alignment_revision``. An inherited override at the same
path is replaced in place, so no path is duplicated and later whole-table
overrides cannot shadow it. Evidence cites the course PDF hash first and the
programme PDF hash second. The package decision records and the recomputed
statistics are written alongside.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_course_outcomes as verifier  # noqa: E402
from _shared_alignment_test_support import effective_extraction, scope_key  # noqa: E402

BUNDLE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261028"
REFERENCE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261016/program-plo-reference.json"
POLICY = "authorized_program_alignment_revision"
DECISIONS_PATH = "assets/course-specifications/shared-program-json-alignment-20261028/alignment-decisions.json"
ROUND = "shared-program-split-2026-10-28"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def label(scope) -> str:
    return f"{scope['program']} / {scope['degree']} / {scope['plan_type']} {scope['version']}"


def sentence(text: str) -> str:
    text = " ".join(text.split())
    return text if text.endswith((".", "؟", "!")) else text + "."


def main() -> int:
    outcomes = load(ROOT / "course-outcomes.json")
    review = load(BUNDLE / "review-decisions.json")
    lineage = load(BUNDLE / "variant-lineage.json")["records"]
    references = load(REFERENCE)["program_versions"]
    parent_of = {(r["course_code"], r["new_variant_id"]): r["old_variant_id"] for r in lineage}
    variants = {(c, v["variant_id"]): v for c, course in outcomes["courses"].items() for v in course["variants"]}

    def reference_for(scope):
        found = [r for r in references if any(scope_key(s) == scope_key(scope) for s in r["scopes"])]
        if len(found) != 1:
            raise SystemExit(f"no unique programme reference for {scope}")
        return found[0]

    by_unit = {u["unit"]: u for u in review["units"]}
    records = []
    entries = {}
    for unit in review["units"]:
        final = unit["final"]
        rationale = sentence(final["rationale_ar"])
        for row in unit["rows"]:
            variant = variants[unit["course_code"], row["variant_id"]]
            reference = reference_for(row["scope"])
            if reference["id"] != unit["program_reference_id"]:
                raise SystemExit(f"reference mismatch {unit['unit']}")
            clo = effective_extraction(variant)["clos"][unit["clo_index"]]
            if clo["code"] != unit["clo_code"]:
                raise SystemExit(f"code mismatch {unit['unit']}")
            original = next((m for m in clo["plo_mappings"] if scope_key(m["scope"]) == scope_key(row["scope"])), None)
            page = (original or {}).get("source_page") or clo.get("source_page")
            head = (
                f"مصدر CLO: {variant['source_pdf']} SHA256={variant['source_sha256']} ص{page}. "
            )
            if final["plo_code"] is None:
                evidence = (
                    "قرار مراجعة JSON مأذون بإبقاء الربط غير محسوم وعدم تخمين رمز. " + head
                    + f"مرجع PLO المفحوص: {reference['source_pdf']} SHA256={reference['source_sha256']}. "
                    f"النطاق: {label(row['scope'])}. السبب: {rationale} مراجعة: {ROUND}. سجل القرار: {DECISIONS_PATH}."
                )
                mapping = {"scope": row["scope"], "plo_codes": [], "status": "explicitly_unmapped",
                           "confidence": "high" if final["confidence"] == "high" else "low",
                           "source_page": page, "evidence": evidence}
                outcome = None
            else:
                outcome = next(o for o in reference["outcomes"] if o["code"] == final["plo_code"])
                evidence = (
                    "تكييف ربط JSON مأذون من المستخدم، وليس استخراجًا من خلية PDF. " + head
                    + f"مصدر PLO: {reference['source_pdf']} SHA256={reference['source_sha256']} ص{outcome['source_pages'][0]}. "
                    f"النطاق: {label(row['scope'])}. الناتج {outcome['code']}: {outcome['text']} "
                    f"التعليل: {rationale} نوع العلاقة: {final['alignment_type']}. مراجعة: {ROUND}. سجل القرار: {DECISIONS_PATH}."
                )
                mapping = {"scope": row["scope"], "plo_codes": [final["plo_code"]], "status": "mapped",
                           "confidence": final["confidence"], "source_page": page, "evidence": evidence}
            entries.setdefault((unit["course_code"], row["variant_id"], unit["clo_index"]), []).append(mapping)
            domain = {"1": "ع", "2": "م", "3": "ق"}.get(unit["clo_code"][:1])
            record = {
                "course_code": unit["course_code"],
                "original_variant_id": parent_of.get((unit["course_code"], row["variant_id"]), row["variant_id"]),
                "variant_id": row["variant_id"],
                "scope": row["scope"],
                "clo_index": unit["clo_index"],
                "clo_code": unit["clo_code"],
                "clo_text_in_json": clo["text"],
                "original_mapping": original,
                "program_reference_id": reference["id"],
                "program_source_pdf": reference["source_pdf"],
                "program_source_sha256": reference["source_sha256"],
                "plo_code": final["plo_code"],
                "alignment_type": final["alignment_type"],
                "confidence": final["confidence"],
                "rationale": rationale,
                "basis": unit["basis"],
            }
            if outcome:
                record.update({"selected_plo_text": outcome["text"], "selected_plo_pages": outcome["source_pages"],
                               "formal_domain_match": bool(domain) and final["plo_code"].startswith(domain)})
            records.append(record)

    for (code, vid, index), mappings in entries.items():
        variant = variants[code, vid]
        order = {scope_key(s): i for i, s in enumerate(variant["scopes"])}
        mappings.sort(key=lambda m: order[scope_key(m["scope"])])
        if {scope_key(m["scope"]) for m in mappings} != set(order):
            raise SystemExit(f"incomplete scopes {code} {vid[:8]} {index}")
        field = f"clos[{index}].plo_mappings"
        override = {"field": field, "value": mappings, "policy": POLICY,
                    "evidence": " | ".join(m["evidence"] for m in mappings), "reviewed_at": review["reviewed_at"]}
        positions = [i for i, o in enumerate(variant["overrides"]) if o["field"] == field]
        if len(positions) > 1:
            raise SystemExit(f"duplicate path {code} {field}")
        if positions:
            later = [o["field"] for o in variant["overrides"][positions[0] + 1:] if o["field"] == "clos"]
            if later:
                raise SystemExit(f"whole-table override would shadow {code} {field}")
            variant["overrides"][positions[0]] = override
        else:
            variant["overrides"].append(override)
        if re.search(r"SHA256=([a-f0-9]{64})", override["evidence"]).group(1) != variant["source_sha256"]:
            raise SystemExit("evidence order broken")

    # Printed-code alignment on an earlier package's row: the official programme
    # PDF prints the code the authored link must follow (no PDF is changed).
    old_bundle = ROOT / "assets/course-specifications/shared-program-json-alignment-20261016"
    old_decisions = load(old_bundle / "alignment-decisions.json")
    for fix in review.get("printed_code_corrections", []):
        if hashlib.sha256((ROOT / fix["official_pdf"]).read_bytes()).hexdigest() != fix["official_sha256"]:
            raise SystemExit("official PDF hash mismatch")
        rows = [r for r in old_decisions["records"] if r["course_code"] == fix["course_code"]
                and r["clo_code"] == fix["clo_code"] and scope_key(r["scope"]) == scope_key(fix["scope"])]
        if len(rows) != 1 or rows[0]["plo_code"] != fix["from"]:
            raise SystemExit(f"unexpected earlier row for {fix}")
        row = rows[0]
        variant = variants[row["course_code"], row["variant_id"]]
        reference = reference_for(row["scope"])
        outcome = next(o for o in reference["outcomes"] if o["code"] == fix["to"])
        rationale = sentence(fix["rationale_ar"])
        row.update({"plo_code": fix["to"], "rationale": rationale, "selected_plo_text": outcome["text"],
                    "selected_plo_pages": outcome["source_pages"], "formal_domain_match": fix["to"].startswith("م"),
                    "printed_code_alignment": {"round": ROUND, "previous_plo_code": fix["from"],
                                               "official_pdf": fix["official_pdf"], "official_sha256": fix["official_sha256"]}})
        field = f"clos[{row['clo_index']}].plo_mappings"
        override = next(o for o in variant["overrides"] if o["field"] == field and o.get("policy") == POLICY)
        for mapping in override["value"]:
            if scope_key(mapping["scope"]) == scope_key(row["scope"]):
                mapping["plo_codes"] = [fix["to"]]
                mapping["evidence"] = (
                    "تكييف ربط JSON مأذون من المستخدم، وليس استخراجًا من خلية PDF. "
                    f"مصدر CLO: {variant['source_pdf']} SHA256={variant['source_sha256']} ص{mapping['source_page']}. "
                    f"مصدر PLO: {reference['source_pdf']} SHA256={reference['source_sha256']} ص{outcome['source_pages'][0]}. "
                    f"النطاق: {label(row['scope'])}. الناتج {outcome['code']}: {outcome['text']} التعليل: {rationale} "
                    f"الرمز المطبوع في توصيف المقرر الرسمي لبرنامج القرآن وعلومه {fix['official_pdf']} SHA256={fix['official_sha256']}. "
                    f"نوع العلاقة: {row['alignment_type']}. مراجعة: {ROUND}. سجل القرار: "
                    "assets/course-specifications/shared-program-json-alignment-20261016/alignment-decisions.json."
                )
        override["evidence"] = " | ".join(m["evidence"] for m in override["value"])
        override["reviewed_at"] = review["reviewed_at"]
    if review.get("printed_code_corrections"):
        dump(old_bundle / "alignment-decisions.json", old_decisions)

    counts = Counter(r["alignment_type"] for r in records)
    decisions = {
        "schema_version": "shared-program-json-alignment-decisions-v1",
        "authored_at": review["reviewed_at"],
        "authorization": review["authority"],
        "records": records,
        "summary": {
            "clo_scope_rows": len(records),
            "mapped_clo_scope_rows": sum(1 for r in records if r["plo_code"]),
            "unresolved_clo_scope_rows": sum(1 for r in records if not r["plo_code"]),
            "alignment_type_counts": {k: counts.get(k, 0) for k in ("direct", "supporting_transfer", "unresolved")},
        },
    }
    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        print("\n".join(errors.messages), file=sys.stderr)
        return 1
    dump(ROOT / "course-outcomes.json", outcomes)
    dump(BUNDLE / "alignment-decisions.json", decisions)
    print(json.dumps(decisions["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
