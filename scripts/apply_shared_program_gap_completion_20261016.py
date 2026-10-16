"""Complete the last shared-program alignment gaps by authorised judgment.

The user asked on 2026-10-16 to complete the remaining gaps by expert judgment
(«أكمل النقص اجتهاديا»). This script reads the sealed record
``gap-completions-by-judgment.json`` and:

* writes the authored CLO texts (and their assessment methods) for source cells
  that are blank in the PDF, under the policy
  ``verified_reference_correction_pending_source_pdf_update`` with evidence that
  states plainly they are not PDF text;
* writes the reviewed programme links for those rows and for the rows that had
  no suitable PLO, under ``authorized_program_alignment_revision``;
* refreshes the package records and the recomputed statistics.

PDFs, ``extracted``, ``document_plo_codes`` and scopes are never touched, and
the script refuses to run when the current state differs from the record.
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
from apply_shared_program_alignment_followup_20261016 import (  # noqa: E402
    BUNDLE, POLICY, dump, end_sentence, load, mapped_evidence, unmapped_evidence,
)

TEXT_POLICY = "verified_reference_correction_pending_source_pdf_update"
RECORD = "assets/course-specifications/shared-program-json-alignment-20261016/gap-completions-by-judgment.json"
ROUND = "gap-completion-2026-10-16"


def main() -> int:
    outcomes_path = ROOT / "course-outcomes.json"
    outcomes = load(outcomes_path)
    decisions_doc = load(BUNDLE / "alignment-decisions.json")
    gaps_doc = load(BUNDLE / "remaining-alignment-gaps.json")
    record = load(BUNDLE / "gap-completions-by-judgment.json")
    references = {r["id"]: r for r in load(BUNDLE / "program-plo-reference.json")["program_versions"]}
    reviewed_at = record["reviewed_at"]

    # 1. Authored texts for blank source cells, on every programme copy of the source.
    texts = {}
    for item in record["texts"]:
        pdf = ROOT / item["source_pdf"]
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if sha != item["source_sha256"]:
            raise SystemExit(f"source hash mismatch {item['source_pdf']}")
        hits = [v for v in outcomes["courses"][item["course_code"]]["variants"] if v["source_pdf"] == item["source_pdf"]]
        if not hits:
            raise SystemExit(f"no variant for {item['course_code']} {item['source_pdf']}")
        evidence = (
            f"مراجعة بصرية لملف {item['source_pdf']} المطابق للبصمة SHA256={sha} | الصفحات {item['source_page']}. "
            "استكمال اجتهادي بتوجيه المستخدم في 2026-10-16 («أكمل النقص اجتهاديا»)، وليس نصًا من PDF؛ "
            f"خلية CLO {item['clo_code']} فارغة في المصدر. الأساس: {item['basis']} "
            f"السجل: {RECORD}."
        )
        for variant in hits:
            index = item["clo_index"]
            row = effective_extraction(variant)["clos"][index]
            if row["code"] != item["clo_code"] or row["text"] is not None:
                raise SystemExit(f"unexpected row {item['course_code']} {index}: {row['code']} {row['text']!r}")
            existing = {o["field"] for o in variant["overrides"]}
            for name, value in (("text", item["text"]), ("assessment", item["assessment"])):
                field = f"clos[{index}].{name}"
                if field in existing:
                    raise SystemExit(f"override path already exists {item['course_code']} {field}")
                variant["overrides"].append({
                    "field": field, "value": value, "evidence": evidence,
                    "policy": TEXT_POLICY, "reviewed_at": reviewed_at,
                })
            texts[(item["course_code"], variant["variant_id"], index)] = item["text"]

    # 2. Programme links.
    variants = {(code, v["variant_id"]): v for code, c in outcomes["courses"].items() for v in c["variants"]}
    changed = 0
    touched = set()
    for link in record["links"]:
        rows = [
            r for r in decisions_doc["records"]
            if r["course_code"] == link["course_code"] and r["clo_code"] == link["clo_code"]
            and r["program_reference_id"] == link["program_reference_id"] and r["plo_code"] is None
        ]
        if len(rows) != link["expected_rows"]:
            raise SystemExit(f"unexpected open rows for {link['course_code']} {link['clo_code']} {link['program_reference_id']}: {len(rows)}")
        reference = references[link["program_reference_id"]]
        outcome = next(o for o in reference["outcomes"] if o["code"] == link["plo_code"])
        rationale = end_sentence(link["rationale_ar"])
        for record_row in rows:
            variant = variants[record_row["course_code"], record_row["variant_id"]]
            index = record_row["clo_index"]
            key = (record_row["course_code"], record_row["variant_id"], index)
            if key in texts:
                record_row["clo_text_in_json"] = texts[key]
            previous = {k: record_row[k] for k in ("plo_code", "alignment_type", "confidence", "rationale")}
            domain = {"1": "ع", "2": "م", "3": "ق"}.get(record_row["clo_code"][:1])
            record_row.update({
                "plo_code": link["plo_code"],
                "alignment_type": link["alignment_type"],
                "confidence": link["confidence"],
                "rationale": rationale,
                "selected_plo_text": outcome["text"],
                "selected_plo_pages": outcome["source_pages"],
                "formal_domain_match": bool(domain) and link["plo_code"].startswith(domain),
                "gap_completion": {"round": ROUND, "previous": previous, "basis": link["basis"],
                                   "independent_verifier": link["independent_verifier"]},
            })
            field = f"clos[{index}].plo_mappings"
            override = next(o for o in variant["overrides"] if o["field"] == field and o.get("policy") == POLICY)
            position = next(i for i, m in enumerate(override["value"]) if m["scope"] == record_row["scope"])
            mapping = override["value"][position]
            if mapping["plo_codes"]:
                raise SystemExit(f"row already mapped {key}")
            override["value"][position] = {
                "scope": mapping["scope"],
                "plo_codes": [link["plo_code"]],
                "status": "mapped",
                "confidence": link["confidence"],
                "source_page": mapping["source_page"],
                "evidence": mapped_evidence(variant, mapping["source_page"], reference, outcome,
                                            record_row["scope"], rationale, link["alignment_type"]).replace(
                    "مراجعة المتابعة: followup-2026-10-16.", f"مراجعة المتابعة: {ROUND}."),
            }
            touched.add((record_row["course_code"], record_row["variant_id"], field))
            changed += 1
    for code, vid, field in touched:
        variant = variants[code, vid]
        override = next(o for o in variant["overrides"] if o["field"] == field and o.get("policy") == POLICY)
        override["evidence"] = " | ".join(m["evidence"] for m in override["value"])
        override["reviewed_at"] = reviewed_at
        if re.search(r"SHA256=([a-f0-9]{64})", override["evidence"]).group(1) != variant["source_sha256"]:
            raise SystemExit(f"evidence order broken {code} {field}")

    # 3. Package summaries.
    records = decisions_doc["records"]
    counts = Counter(r["alignment_type"] for r in records)
    summary = decisions_doc["summary"]
    summary["mapped_clo_scope_rows"] = sum(1 for r in records if r["plo_code"] is not None)
    summary["unresolved_clo_scope_rows"] = sum(1 for r in records if r["plo_code"] is None)
    summary["alignment_type_counts"] = {k: counts.get(k, 0) for k in ("direct", "supporting_transfer", "unresolved", "preserved_existing")}
    open_keys = {(r["course_code"], r["variant_id"], r["clo_index"], scope_key(r["scope"])) for r in records if r["plo_code"] is None}
    gaps_doc["records"] = [g for g in gaps_doc["records"] if (g["course_code"], g["variant_id"], g["clo_index"], scope_key(g["scope"])) in open_keys]
    reasons = Counter(g["reason_code"] for g in gaps_doc["records"])
    gaps_doc["summary"] = {
        "total_unresolved_clo_scope_rows": len(gaps_doc["records"]),
        "blank_source_clo_scope_rows": reasons.get("CLO_SOURCE_BLANK", 0),
        "no_suitable_plo_clo_scope_rows": reasons.get("NO_SEMANTICALLY_SUITABLE_PROGRAM_PLO", 0),
        "by_program": dict(Counter(g["scope"]["program"] for g in gaps_doc["records"]).most_common()),
        "gap_completion_round": ROUND,
    }

    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        for message in errors.messages:
            print("ERROR:", message, file=sys.stderr)
        return 1
    dump(outcomes_path, outcomes)
    dump(BUNDLE / "alignment-decisions.json", decisions_doc)
    dump(BUNDLE / "remaining-alignment-gaps.json", gaps_doc)
    print(json.dumps({"text_rows": len(texts), "linked_rows": changed, "summary": summary["alignment_type_counts"],
                      "gaps": gaps_doc["summary"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
