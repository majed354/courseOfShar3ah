"""Point the Quran-programme copies to their official, link-printed specifications.

Fourteen Quran-only copies were published from shared PDFs whose programme-link
column had been blanked on 2026-09-05. Each blanked file was produced from an
official Quran-programme course specification that is still in the repository
(``quran-old-v39`` or, for 2002454-2, its approved identity-resolution copy).
This one-time step points ``data.json`` back to that official file, re-extracts
the copy through ``extract_variant_worker`` (the repository's extraction path),
and compares every printed link with the authorized link saved earlier:

* printed and authorized agree        -> the authorized override is removed;
  the printed (extracted) link governs.
* printed and authorized differ       -> the printed link governs; the
  disagreement is recorded in ``link-comparison.json``.
* the extractor cannot read the cell  -> the code read visually on the hash-bound
  page is written as ``verified_extraction_correction_matches_source``.

Every other reviewed override is carried forward unchanged in value, with its
evidence re-anchored to the official file. No PDF is written.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_course_outcomes as verifier  # noqa: E402
from extract_course_outcomes import (  # noqa: E402
    _excluded_reason, extract_variant_worker, load_auxiliary_sources,
)
from _shared_alignment_test_support import scope_key  # noqa: E402

SPECS = "assets/course-specifications/"
BUNDLE = ROOT / SPECS / "quran-official-source-20261028"
BLANK_MANIFEST = ROOT / SPECS / "shared-course-blank-plo-20260905/manifest.json"
QURAN_MANIFEST = ROOT / SPECS / "quran-old-v39/manifest.json"
IDENTITY_MANIFEST = ROOT / SPECS / "identity-resolutions-20260829/manifest.json"
REFERENCE = ROOT / SPECS / "shared-program-json-alignment-20261016/program-plo-reference.json"
PROGRAM = "القرآن وعلومه"
REVIEWED_AT = "2026-10-28"
AUTHORIZED = "authorized_program_alignment_revision"
EXTRACTION_FIX = "verified_extraction_correction_matches_source"
PENDING = "verified_reference_correction_pending_source_pdf_update"

TARGETS = {
    "2002110-2": "quran-old-v39/2002110-2.pdf",
    "2002131-2": "quran-old-v39/2002131-2.pdf",
    "2002204-2": "quran-old-v39/2002204-2.pdf",
    "2002208-2": "quran-old-v39/2002208-2.pdf",
    "2002232-2": "quran-old-v39/2002232-2.pdf",
    "2002250-2": "quran-old-v39/2002250-2.pdf",
    "2002306-2": "quran-old-v39/2002306-2.pdf",
    "2002318-2": "quran-old-v39/2002318-2.pdf",
    "2002412-2": "quran-old-v39/2002412-2.pdf",
    "2002416-2": "quran-old-v39/2002416-2.pdf",
    "2002419-2": "quran-old-v39/2002419-2.pdf",
    "2002429-2": "quran-old-v39/2002429-2.pdf",
    "2002454-2": "identity-resolutions-20260829/2002454-2--quran.pdf",
    "2002456-2": "quran-old-v39/2002456-2.pdf",
}

# Printed cells the extractor leaves unread; each was rendered from the
# hash-bound official PDF and read on 2026-10-28 (code, PDF page).
VISUAL_READINGS = {
    ("2002232-2", "3.1"): ("ق1", 4),
    ("2002250-2", "3.1"): ("ق1", 4),
    ("2002318-2", "3.1"): ("ق1", 4),
    ("2002456-2", "3.1"): ("ق2", 4),
}

# Copies whose page-4 continuation row 3.1 was reviewed visually on the official file.
CONTINUATION_REVIEWS = {"2002232-2": "ق1", "2002250-2": "ق1", "2002456-2": "ق2"}

# Quran-specific files present in the repository that were deliberately not used.
NOT_SELECTED = [
    {"course_codes": ["103171-2", "103281-2", "103282-2", "103349-2", "103411-2", "2001101-2", "2001403-2"],
     "files": "assets/course-specifications/clo-plo-corrections-20260901/<code>--quran-old-v39.pdf",
     "reason_ar": "نسخ برنامجية عدّلت جولة 2026-09-01 نصوص مخرجاتها وروابطها داخل PDF؛ ليست توصيفًا رسميًّا بروابط مطبوعة أصلية، وأغلبها ليس أصل النسخة المفرغة الحالية."},
    {"course_codes": ["2001106-2", "990413-2"],
     "files": "assets/course-specifications/identity-resolutions-20260829/2001106-2--quran.pdf",
     "reason_ar": "مأخوذ من كتيّب توصيفات برنامج الدراسات الإسلامية، فروابطه المطبوعة ليست لنواتج برنامج القرآن وعلومه."},
    {"course_codes": ["2004111-2"],
     "files": "assets/course-specifications/local-gap-completion-20260822/quran-culture/2004111-2.pdf",
     "reason_ar": "ليس أصل النسخة المفرغة الحالية، ولم يثبت أنه توصيف رسمي خاص بالبرنامج بروابط مطبوعة."},
    {"course_codes": ["2004403-2"],
     "files": "assets/course-specifications/clo-plo-corrections-20260901/2001403-2--quran-old-v39.pdf",
     "reason_ar": "الملف لمقرر برمز آخر (2001403-2) وللإصدار 39 فقط، والنسخة لإصدار 47."},
]

SHARED_NOTE = re.compile(r"\s*المقرر مشترك بين برامج مختلفة؛ أُبقيت خلايا رمز ناتج البرنامج فارغة لتتولى كل جهة برنامجية الربط المناسب \(2026-09-05\)\.")
NEW_NOTE = ("تشير نسخة القرآن وعلومه إلى توصيف المقرر الرسمي للبرنامج بروابطه المطبوعة، "
            "وهو الأصل الذي أُخذت منه النسخة المشتركة المفرغة (2026-10-28).")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_links(value):
    """Extraction content outside the link column, for the equality guard."""
    if isinstance(value, dict):
        return {k: strip_links(v) for k, v in value.items()
                if k not in {"plo_mappings", "document_plo_codes", "warnings"}}
    if isinstance(value, list):
        return [strip_links(v) for v in value]
    return value


def main() -> int:
    if (BUNDLE / "variant-lineage.json").exists():
        raise SystemExit("This one-time repointing already exists; review it before replacing anything.")
    data = load(ROOT / "data.json")
    outcomes = load(ROOT / "course-outcomes.json")
    blanks = {r["output"]: r for r in load(BLANK_MANIFEST)["records"]}
    eligible = {r["code"]: r["eligible_versions"] for r in load(QURAN_MANIFEST)["specifications"]}
    identity = {SPECS + "identity-resolutions-20260829/" + r["filename"]: r for r in load(IDENTITY_MANIFEST)["records"]}
    references = load(REFERENCE)["program_versions"]

    def valid_codes(scope):
        found = [r for r in references if any(scope_key(s) == scope_key(scope) for s in r["scopes"])]
        if len(found) != 1:
            raise SystemExit(f"no unique programme reference for {scope}")
        return {o["code"] for o in found[0]["outcomes"]}

    old_variants, data_records = {}, {}
    for code, official in TARGETS.items():
        official = SPECS + official
        detail = data["course_details"][code]
        hits = [v for v in detail.get("variants", []) if v["scopes"]
                and all(s["program"] == PROGRAM and s["degree"] == "بكالوريوس" for s in v["scopes"])
                and v["pdf_url"].startswith(SPECS + "shared-course-blank-plo-20260905/")]
        if len(hits) != 1:
            raise SystemExit(f"{code}: expected one Quran copy on a blanked PDF")
        record = hits[0]
        blank = blanks[record["pdf_url"]]
        if blank["source"] != official or digest(ROOT / official) != blank["source_sha256"]:
            raise SystemExit(f"{code}: blanked copy is not derived from {official}")
        origin = identity[official]["source_relative_path"] if official in identity else official
        if Path(origin).name != f"{code}.pdf" or "/quran-old-v39/" not in origin:
            raise SystemExit(f"{code}: official file is not from the Quran programme booklet")
        versions = {int(s["version"]) for s in record["scopes"]}
        if not versions <= set(eligible[code]):
            raise SystemExit(f"{code}: versions {versions} not eligible for {official}")
        olds = [v for v in outcomes["courses"][code]["variants"] if v["source_pdf"] == record["pdf_url"]
                and [scope_key(s) for s in v["scopes"]] == [scope_key(s) for s in record["scopes"]]]
        if len(olds) != 1:
            raise SystemExit(f"{code}: live copy not found")
        old_variants[code] = olds[0]
        data_records[code] = record

    BUNDLE.mkdir(parents=True, exist_ok=True)
    old_ids = {v["variant_id"] for v in old_variants.values()}
    dump(BUNDLE / "previous-context.json", {
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "data_course_details": {c: copy.deepcopy(data["course_details"][c]) for c in TARGETS},
        "outcome_courses": {c: copy.deepcopy(outcomes["courses"][c]) for c in TARGETS},
        "recommendations": [r for r in outcomes["source_correction_recommendations"] if r["variant_id"] in old_ids],
    })

    for code, record in data_records.items():
        record["pdf_url"] = SPECS + TARGETS[code]
        note = SHARED_NOTE.sub("", record.get("match_note", "")).strip()
        record["match_note"] = f"{note} {NEW_NOTE}".strip()
    dump(ROOT / "data.json", data)

    expected, _ = verifier.rebuild_expected_variants(data)
    auxiliary, _ = load_auxiliary_sources(ROOT)
    payloads = []
    for code in TARGETS:
        source = SPECS + TARGETS[code]
        row = [v for v in expected[code] if v["source_pdf"] == source]
        if len(row) != 1:
            raise SystemExit(f"{code}: expected one rebuilt copy for {source}")
        payloads.append(dict(row[0], course_code=code, repo_root=str(ROOT),
                             auxiliary=auxiliary.get(source), source_sha256=digest(ROOT / source)))
    with ThreadPoolExecutor(max_workers=6) as pool:
        extracted = dict(pool.map(extract_variant_worker, payloads))

    comparisons, lineage, notes = [], [], []
    for payload in payloads:
        code = payload["course_code"]
        old = old_variants[code]
        new_extracted = extracted[payload["variant_id"]]
        if strip_links(old["extracted"]) != strip_links(new_extracted):
            raise SystemExit(f"{code}: official extraction differs outside the link column")
        official, sha = payload["source_pdf"], payload["source_sha256"]
        anchor = (f"المصدر الحالي: {official} SHA256={sha}؛ أعيد الاستخراج منه فطابق الاستخراج السابق خارج عمود الربط، "
                  f"والنسخة السابقة {old['source_pdf']} SHA256={old['source_sha256']} مأخوذة منه بتفريغ عمود رمز ناتج البرنامج فقط. ")
        overrides = []
        for override in old["overrides"]:
            field = override["field"]
            link = re.fullmatch(r"clos\[(\d+)\]\.plo_mappings", field)
            if link and override["policy"] == AUTHORIZED:
                index = int(link.group(1))
                row = new_extracted["clos"][index]
                value, visual_used = [], False
                for authorized in override["value"]:
                    printed = next(m for m in row["plo_mappings"] if scope_key(m["scope"]) == scope_key(authorized["scope"]))
                    codes = printed["plo_codes"] or []
                    reading = None
                    if printed["status"] != "mapped" or not codes:
                        reading = VISUAL_READINGS[code, row["code"]]
                        codes = [reading[0]]
                        kind = "printed_read_visually_matches" if codes == authorized["plo_codes"] else "printed_read_visually_differs"
                    elif not set(codes) <= valid_codes(authorized["scope"]):
                        raise SystemExit(f"{code} {row['code']}: printed code {codes} is not a programme outcome")
                    else:
                        kind = "printed_matches" if codes == authorized["plo_codes"] else "printed_differs"
                    comparisons.append({
                        "course_code": code, "old_variant_id": old["variant_id"], "new_variant_id": payload["variant_id"],
                        "clo_index": index, "clo_code": row["code"], "clo_text": row["text"], "scope": authorized["scope"],
                        "authorized_plo_codes": authorized["plo_codes"], "printed_plo_codes": codes,
                        "printed_source_page": reading[1] if reading else printed["source_page"],
                        "printed_read_by": "visual_review" if reading else "extractor",
                        "comparison": kind, "governing_plo_codes": codes, "governing_source": "official_printed",
                    })
                    if reading:
                        visual_used = True
                        value.append({**printed, "plo_codes": codes, "status": "mapped", "confidence": "high",
                                      "source_page": reading[1],
                                      "evidence": (f"قراءة بصرية للخلية المطبوعة في توصيف المقرر الرسمي {official} SHA256={sha} "
                                                   f"ص{reading[1]}: الصف {row['code']} ممتد تحت ترويسة مكررة ورمزه المطبوع {reading[0]}.")})
                    else:
                        value.append(printed)
                if visual_used:
                    overrides.append({"field": field, "value": value, "policy": EXTRACTION_FIX,
                                      "evidence": " | ".join(m["evidence"] for m in value), "reviewed_at": REVIEWED_AT})
                continue
            if link:
                raise SystemExit(f"{code}: unexpected link override policy {override['policy']}")
            if override["policy"] == PENDING and field.endswith(".document_plo_codes"):
                notes.append({"course_code": code, "field": field, "action": "dropped",
                              "reason_ar": "صُحّح لأن الصفحة المستكملة في النسخة المفرغة احتفظت برابط مطبوع؛ وفي التوصيف الرسمي هذا الرابط هو المقصود."})
                continue
            overrides.append({**override, "evidence": anchor + "دليل المراجعة الأصلي: " + override["evidence"],
                              "reviewed_at": REVIEWED_AT})
        variant = {"source_pdf": official, "scopes": payload["scopes"], "catalog": payload["catalog"],
                   "variant_id": payload["variant_id"], "source_sha256": sha,
                   "extracted": new_extracted, "overrides": overrides}
        if code in CONTINUATION_REVIEWS:
            corrected = any(o["policy"] == EXTRACTION_FIX for o in overrides)
            variant["source_alignment"] = {"status": "matches_source_pdf", "label_ar": "مطابق لملف PDF بعد تصحيح الاستخراج",
                                           "correction_applied": corrected, "source_update_recommended": False, "source_sha256": sha}
            variant["source_review"] = {
                "status": "accepted_as_is",
                "finding": (f"صف CLO 3.1 ممتد إلى الصفحة 4 تحت ترويسة مكررة، ورمزه المطبوع {CONTINUATION_REVIEWS[code]} "
                            "وطريقة تقويمه في أعلى الصفحة؛ ما لم يلتقطه القارئ صُحّح استخراجيًّا، ولا نقص في PDF الرسمي."),
                "evidence": {"file": official, "pages": [3, 4], "sha256_verified": True,
                             "review_method": "تصيير صفحتي جدول CLO المتجاورتين من الملف المطابق للبصمة وقراءة الرمز والنص والتقويم وخانة PLO بصريًّا."},
                "reviewed_at": "2026-10-28T12:00:00+03:00", "source_sha256": sha,
            }
        variants = outcomes["courses"][code]["variants"]
        variants[:] = sorted([v for v in variants if v is not old] + [variant], key=lambda v: v["variant_id"])
        lineage.append({"course_code": code, "old_variant_id": old["variant_id"], "new_variant_id": payload["variant_id"],
                        "scopes": payload["scopes"], "old_source_pdf": old["source_pdf"], "old_source_sha256": old["source_sha256"],
                        "new_source_pdf": official, "new_source_sha256": sha})

    retired = [r for r in outcomes["source_correction_recommendations"] if r["variant_id"] in old_ids]
    outcomes["source_correction_recommendations"] = [r for r in outcomes["source_correction_recommendations"] if r["variant_id"] not in old_ids]
    active = {v["source_pdf"] for c in outcomes["courses"].values() for v in c["variants"]}
    excluded = {x["source_pdf"]: x for x in outcomes["excluded_sources"] if x["source_pdf"] not in active}
    for path in {r["old_source_pdf"] for r in lineage} - active:
        excluded[path] = {"source_pdf": path, "source_sha256": digest(ROOT / path), "reason": _excluded_reason(path)}
    outcomes["excluded_sources"] = sorted(excluded.values(), key=lambda x: x["source_pdf"])
    outcomes["source_data"]["sha256"] = digest(ROOT / "data.json")
    # The extractor gained the two reviewed continuation hashes for this step.
    outcomes["extractor"]["script_sha256"] = digest(ROOT / outcomes["extractor"]["script"])
    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        print("\n".join(errors.messages), file=sys.stderr)
        return 1
    dump(ROOT / "course-outcomes.json", outcomes)

    counts = Counter(c["comparison"] for c in comparisons)
    dump(BUNDLE / "variant-lineage.json", {"schema_version": "quran-official-source-lineage-v1", "records": lineage})
    dump(BUNDLE / "link-comparison.json", {
        "schema_version": "quran-official-printed-link-comparison-v1",
        "reviewed_at": REVIEWED_AT,
        "rule_ar": "يحكم الرابط المطبوع في التوصيف الرسمي، إلا إن قام دليل على خطأ طباعي؛ ولم يُعثر على رمز مطبوع خارج نواتج البرنامج.",
        "summary": dict(sorted(counts.items())),
        "records": comparisons,
        "dropped_overrides": notes,
    })
    dump(BUNDLE / "superseded-source-recommendations.json", {
        "reason_ar": "توصيات تحديث خلية الربط في النسخة المفرغة؛ النسخة الحالية تشير إلى التوصيف الرسمي الذي يطبع الرابط المقصود.",
        "records": retired,
    })
    dump(BUNDLE / "selection.json", {
        "rule_ar": ("تُنقل نسخة القرآن وعلومه فقط حين تكون نسختها الحالية مفرغة مأخوذة مباشرة من توصيف رسمي لبرنامج القرآن وعلومه "
                    "موجود في المستودع، ويكون الإصدار مؤهلًا في بيان quran-old-v39."),
        "selected": sorted(TARGETS),
        "not_selected": NOT_SELECTED,
    })
    print(json.dumps({"copies": len(lineage), "comparisons": dict(counts), "retired_recommendations": len(retired)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
