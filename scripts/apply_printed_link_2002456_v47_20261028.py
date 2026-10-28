"""Let the printed code govern 2002456-2 CLO 2.1 in the Quran v47 copy.

The copy uses the Quran/Qiraat new-plan specification, which prints م3 for CLO
2.1 (PDF page 5); the earlier authorized link said م2. The Quran programme's own
official specification (quran-old-v39/2002456-2.pdf) prints م3 for the same CLO,
and م3 is a Quran v47 outcome, so there is no evidence of a printing error. The
override keeps the authorized policy because the shared file's link column is
recorded as ambiguous for scope; its value now follows the print. No PDF is
written.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_course_outcomes as verifier  # noqa: E402

SPECS = "assets/course-specifications/"
BUNDLE = ROOT / SPECS / "quran-official-source-20261028"
RECORD = BUNDLE / "printed-link-followup.json"
REFERENCE = ROOT / SPECS / "shared-program-json-alignment-20261016/program-plo-reference.json"
CODE, VARIANT, INDEX, CLO, PAGE = "2002456-2", "6b04def5", 3, "2.1", 5
FROM, TO = "م2", "م3"
CORROBORATION = SPECS + "quran-old-v39/2002456-2.pdf"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if RECORD.exists():
        raise SystemExit("This follow-up already exists; review it before replacing anything.")
    outcomes = load(ROOT / "course-outcomes.json")
    variant = next(v for v in outcomes["courses"][CODE]["variants"] if v["variant_id"].startswith(VARIANT))
    scope = variant["scopes"][0]
    if [(s["program"], s["version"]) for s in variant["scopes"]] != [("القرآن وعلومه", "47")]:
        raise SystemExit("unexpected scope")
    if digest(ROOT / variant["source_pdf"]) != variant["source_sha256"]:
        raise SystemExit("course PDF hash mismatch")
    reviewed = next(o for o in variant["overrides"] if o["field"] == "clos")["value"][INDEX]
    if reviewed["code"] != CLO or reviewed["document_plo_codes"] != [TO]:
        raise SystemExit("printed code is not the expected one")
    field = f"clos[{INDEX}].plo_mappings"
    override = next(o for o in variant["overrides"] if o["field"] == field)
    if override["policy"] != "authorized_program_alignment_revision" or override["value"][0]["plo_codes"] != [FROM]:
        raise SystemExit("unexpected authorized link")
    previous = json.loads(json.dumps(override))
    reference = next(r for r in load(REFERENCE)["program_versions"] if scope in r["scopes"])
    outcome = next(o for o in reference["outcomes"] if o["code"] == TO)
    corroboration_sha = digest(ROOT / CORROBORATION)
    evidence = (
        f"الرابط المطبوع يحكم بقرار المستخدم. مصدر CLO والرابط: {variant['source_pdf']} SHA256={variant['source_sha256']} "
        f"ص{PAGE}: يطبع الصف {CLO} الرمز {TO}، والتوصيف متعدد البرامج (القرآن وعلومه – القراءات) فخليته مسجلة غامضة النطاق. "
        f"يعضده توصيف المقرر الرسمي لبرنامج القرآن وعلومه {CORROBORATION} SHA256={corroboration_sha} الذي يطبع {TO} للمخرج نفسه. "
        f"مصدر PLO: {reference['source_pdf']} SHA256={reference['source_sha256']} ص{outcome['source_pages'][0]}. "
        f"الناتج {TO}: {outcome['text']} لا دليل على خطأ طباعي؛ كان الربط المأذون السابق {FROM}. "
        f"سجل القرار: {RECORD.relative_to(ROOT).as_posix()}."
    )
    override["value"] = [{**override["value"][0], "plo_codes": [TO], "status": "mapped", "confidence": "high",
                          "source_page": PAGE, "evidence": evidence}]
    override["evidence"] = evidence
    override["reviewed_at"] = "2026-10-28"
    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        print("\n".join(errors.messages), file=sys.stderr)
        return 1
    dump(ROOT / "course-outcomes.json", outcomes)
    dump(RECORD, {
        "schema_version": "quran-printed-link-followup-v1",
        "reviewed_at": "2026-10-28",
        "authority_ar": "قاعدة المستخدم: يحكم الرابط المطبوع في نسخ القرآن وعلومه ما لم يقم دليل على خطأ طباعي؛ أحالت الجلسة الأم هذا الصف بعد مزامنة الأنبوب.",
        "applied": [{"course_code": CODE, "variant_id": variant["variant_id"], "scope": scope, "clo_index": INDEX, "clo_code": CLO,
                     "source_pdf": variant["source_pdf"], "source_sha256": variant["source_sha256"], "source_page": PAGE,
                     "printed_plo_code": TO, "previous_authorized_plo_code": FROM, "read_by": "visual_review",
                     "corroboration": {"pdf": CORROBORATION, "sha256": corroboration_sha, "printed_plo_code": TO},
                     "previous_override": previous}],
        "not_applied": [
            {"course_code": c, "variant_id": v, "clo_codes": clos, "version": "47", "authorized": a, "printed": p,
             "reason_ar": "التوصيف متطلب كلية متعدد البرامج (خمسة برامج) بخلية رمز واحدة، فالرمز المطبوع لا يخص نواتج القرآن وعلومه؛ يبقى الربط المأذون حتى يتوفر توصيف خاص بالبرنامج أو قرار بشري."}
            for c, v, clos, a, p in [
                ("2002252-2", "67ea9d68", ["2.1", "2.2"], "م2", "م3"),
                ("20031301-2", "f54cd6cb", ["2.1"], "ع3", "م2"),
                ("2003220-2", "a2230a47", ["2.1"], "ع3", "م2"),
            ]
        ],
    })
    print(json.dumps({"course": CODE, "clo": CLO, "from": FROM, "to": TO}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
