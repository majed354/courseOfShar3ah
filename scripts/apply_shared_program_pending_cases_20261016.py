"""Apply the authorised decisions on the three pending shared-course cases.

Reads ``pending-cases-decisions.json``. Only the ``modify`` part changes data:
the Systems-38 copy of 2003215-2 gets ``clos[5].code`` = 2.3 (printed as 3.2
inside the skills section; the course's other specification numbers it 2.3).
The decision record and its mapping evidence are refreshed. No row is added,
no PDF or ``extracted`` value changes, and other programmes are untouched.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_course_outcomes as verifier  # noqa: E402
from _shared_alignment_test_support import effective_extraction  # noqa: E402
from apply_shared_program_alignment_followup_20261016 import BUNDLE, POLICY, dump, load, mapped_evidence  # noqa: E402

CODE_POLICY = "verified_reference_correction_pending_source_pdf_update"
RECORD = "assets/course-specifications/shared-program-json-alignment-20261016/pending-cases-decisions.json"
ROUND = "pending-cases-2026-10-16"


def main() -> int:
    outcomes = load(ROOT / "course-outcomes.json")
    decisions = load(BUNDLE / "alignment-decisions.json")
    record = load(BUNDLE / "pending-cases-decisions.json")
    references = {r["id"]: r for r in load(BUNDLE / "program-plo-reference.json")["program_versions"]}
    item = next(d for d in record["decisions"] if d.get("recode"))
    variant = next(v for v in outcomes["courses"]["2003215-2"]["variants"] if v["variant_id"] == item["variant_id"])
    if hashlib.sha256((ROOT / item["witness_pdf"]).read_bytes()).hexdigest() != item["witness_sha256"]:
        raise SystemExit("witness hash mismatch")
    index = item["clo_index"]
    row = effective_extraction(variant)["clos"][index]
    if row["code"] != item["recode"]["from"]:
        raise SystemExit(f"unexpected code {row['code']}")
    field = f"clos[{index}].code"
    if any(o["field"] == field for o in variant["overrides"]):
        raise SystemExit("code override exists")
    variant["overrides"].append({
        "field": field,
        "value": item["recode"]["to"],
        "evidence": (
            f"مراجعة بصرية لملف {variant['source_pdf']} المطابق للبصمة SHA256={variant['source_sha256']} | الصفحات 5,6. "
            f"الصف مطبوع برمز {item['recode']['from']} داخل قسم المهارات، ويرقمه التوصيف الآخر للمقرر نفسه "
            f"{item['witness_pdf']} SHA256={item['witness_sha256']} برمز {item['recode']['to']}. "
            "إعادة ترميز في JSON بقرار اجتهادي مأذون («اجتهد فيها بنفسك إما تقليص المخرجات أو التعديل») مع بقاء PDF كما طُبع. "
            f"السجل: {RECORD}."
        ),
        "policy": CODE_POLICY,
        "reviewed_at": record["reviewed_at"],
    })
    rationale = (
        "صف مهاري طُبع برمز 3.2 داخل قسم المهارات وأعيد ترميزه 2.3 بقرار اجتهادي موافقةً للتوصيف الآخر للمقرر نفسه؛ "
        "مضمونه التفاعل مع التشريعات والاتفاقيات وتفسيرها لاستنباط الأحكام، فيطابق م1 «تفسير النصوص القانونية تفسيراً سليماً»."
    )
    rows = [r for r in decisions["records"] if r["variant_id"] == variant["variant_id"] and r["clo_index"] == index]
    if len(rows) != 1:
        raise SystemExit("expected one decision row")
    decision = rows[0]
    reference = references[decision["program_reference_id"]]
    outcome = next(o for o in reference["outcomes"] if o["code"] == decision["plo_code"])
    decision.update({
        "clo_code": item["recode"]["to"],
        "rationale": rationale,
        "formal_domain_match": decision["plo_code"].startswith("م"),
        "pending_case": {"round": ROUND, "previous_clo_code": item["recode"]["from"], "record": RECORD},
    })
    override = next(o for o in variant["overrides"] if o["field"] == f"clos[{index}].plo_mappings" and o.get("policy") == POLICY)
    for position, mapping in enumerate(override["value"]):
        if mapping["scope"] == decision["scope"]:
            mapping["evidence"] = mapped_evidence(
                variant, mapping["source_page"], reference, outcome, decision["scope"], rationale, decision["alignment_type"]
            ).replace("مراجعة المتابعة: followup-2026-10-16.", f"مراجعة المتابعة: {ROUND}.")
    override["evidence"] = " | ".join(m["evidence"] for m in override["value"])
    override["reviewed_at"] = record["reviewed_at"]
    if re.search(r"SHA256=([a-f0-9]{64})", override["evidence"]).group(1) != variant["source_sha256"]:
        raise SystemExit("evidence order broken")
    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        print("\n".join(errors.messages), file=sys.stderr)
        return 1
    dump(ROOT / "course-outcomes.json", outcomes)
    dump(BUNDLE / "alignment-decisions.json", decisions)
    print("recoded", variant["variant_id"][:8], field, "->", item["recode"]["to"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
