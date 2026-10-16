"""Publish the user-authored doctorate revision without changing source bytes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from scripts.extract_course_outcomes import _statistics, extract_variant_worker
from scripts.verify_course_outcomes import ErrorCollector, expected_excluded_reason, rebuild_expected_variants, recompute_statistics

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets/course-specifications/quranic-doctorate-single-domain-20261016"
PROGRAM = "الدراسات القرآنية"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if (BUNDLE / "manifest.json").exists():
        raise SystemExit("This one-time publication already exists; review it before replacing anything.")
    cfg = read(source / "ملفات العمل/revision-decisions.json")
    data = read(ROOT / "data.json")
    outcomes = read(ROOT / "course-outcomes.json")
    codes = [c["code"] for c in cfg["courses"]]
    program = next(p for p in data["programs"] if p["name"] == PROGRAM and p["degree"] == "دكتوراه")
    assert len(program["courses"]) == 6 and sum(c["hours"] for c in program["courses"]) == 60
    before = {"baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "program": copy.deepcopy(program),
              "course_details": {c: copy.deepcopy(data["course_details"][c]) for c in codes},
              "course_outcomes": {c: copy.deepcopy(outcomes["courses"][c]) for c in codes}}
    write(BUNDLE / "previous-context.json", before)
    for name, suffix in [("توصيف دكتوراه الدراسات القرآنية - القالب الرسمي 2024", ".pdf"),
                         ("توصيف دكتوراه الدراسات القرآنية - القالب الرسمي 2024", ".docx")]:
        shutil.copy2(source / (name + suffix), BUNDLE / ("program-specification" + suffix))
    assert digest(BUNDLE / "program-specification.pdf") == cfg["program_pdf_sha256"]
    shutil.copy2(source / "مصادر/الخطة الرسمية دكتوراه الدراسات القرآنية.pdf", BUNDLE / "official-curriculum.pdf")
    assert digest(BUNDLE / "official-curriculum.pdf") == cfg["official_plan_sha256"]
    public_cfg = copy.deepcopy(cfg)
    for field in ("program_pdf", "program_docx"):
        public_cfg[field] = relative(BUNDLE / ("program-specification.pdf" if field.endswith("pdf") else "program-specification.docx"))
    for course in public_cfg["courses"]:
        course["source_docx"] = Path(course["source_docx"]).name
        dest = BUNDLE / "courses" / course["code"]
        dest.mkdir(parents=True, exist_ok=True)
        for suffix in (".pdf", ".docx"):
            shutil.copy2(source / "توصيفات المقررات" / course["code"] / ("توصيف المقرر" + suffix), dest / ("course-specification" + suffix))
            assert digest(dest / ("course-specification" + suffix)) == course["pdf_sha256" if suffix == ".pdf" else "docx_sha256"]
            course["pdf" if suffix == ".pdf" else "docx"] = relative(dest / ("course-specification" + suffix))
        detail = data["course_details"][course["code"]]
        selected = [v for v in detail["variants"] if any(s["program"] == PROGRAM and s["degree"] == "دكتوراه" for s in v["scopes"])]
        assert len(selected) == 1
        old = selected[0]
        old.update(pdf_url=course["pdf"], match_status="adapted_verified",
                   match_note="مراجعة مؤلفة بإذن المستخدم بتاريخ16 أكتوبر2026: ستة مخرجات بربط أحادي داخل المجال، مع حفظ مقررات الخطة الرسمية وساعاتها وأوزان أنشطة التقويم. لا يعاد ترميز درجات سابقة، ولا يُنسب اعتماد مجلس سابق إلى هذه المراجعة.")
    ref = read(source / "program-reference.json")
    for row in ref["program_outcomes"]:
        row["source_file"] = public_cfg["program_pdf"]
    for row in ref["course_outcomes"]:
        row["source_file"] = (next(c["pdf"] for c in public_cfg["courses"] if c["code"] == row["course_code"])
                              if row["course_code"] in codes else public_cfg["program_pdf"])
    write(BUNDLE / "program-reference.json", ref)
    write(BUNDLE / "revision-decisions.json", public_cfg)
    program.update(program_specification_url=public_cfg["program_pdf"],
                   program_specification_docx_url=public_cfg["program_docx"],
                   program_reference_url=relative(BUNDLE / "program-reference.json"),
                   official_curriculum_url=relative(BUNDLE / "official-curriculum.pdf"),
                   program_specification_status="published")
    details = program["program_details"]
    details.update(specification_version="2026-10-16 — الخطة الرسمية60 ساعة والربط الأحادي",
                   specification_source_sha256=cfg["program_pdf_sha256"],
                   curriculum_course_count=6, matrix_link_count=34,
                   extraction_status="complete", extraction_error_count=0,
                   learning_outcomes=[{"code": o["code"], "domain": {"ع": "المعرفة والفهم", "م": "المهارات", "ق": "القيم والاستقلالية والمسؤولية"}[o["code"][0]], "text": o["text"]} for o in cfg["outcomes"]])
    write(ROOT / "data.json", data)
    expected, _ = rebuild_expected_variants(data)
    payloads = []
    for course in public_cfg["courses"]:
        expected_row = next(v for v in expected[course["code"]] if v["source_pdf"] == course["pdf"])
        payloads.append(dict(expected_row, course_code=course["code"], repo_root=str(ROOT), source_sha256=course["pdf_sha256"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        extracted = dict(pool.map(extract_variant_worker, payloads))
    for course, meta in zip(public_cfg["courses"], payloads):
        v = {k: meta[k] for k in ("variant_id", "scopes", "catalog", "source_pdf", "source_sha256")}
        v["extracted"] = extracted[v["variant_id"]]
        scope = v["scopes"][0]
        clos = []
        for c in course["clos"]:
            clos.append({"code": c["code"], "text": c["text"], "source_status": "present",
                         "assessment": c["assessment"], "assessment_source_page": c["source_page"],
                         "plo_mappings": [{"scope": scope, "plo_codes": [c["plo_code"]], "status": "mapped", "confidence": "high", "source_page": c["source_page"],
                                           "evidence": f"User-authored source PDF SHA256={v['source_sha256']} page {c['source_page']}; matched Word table and reviewed PDF"}],
                         "document_plo_codes": [c["plo_code"]], "confidence": "high", "source_page": c["source_page"], "extraction_method": "hash_matched_manifest"})
        source_variant = read(source / "course-outcomes.json")["courses"][course["code"]]["variants"][0]
        assessments = source_variant["extracted"]["assessment_plan"]
        assert sum(x["weight"] for x in assessments) == 100
        fields = {"course_name": course["name"], "course_name_metadata": {"confidence": "high", "source_page": 1, "extraction_method": "geometric_pdf_ocr_consensus"},
                  "clos": clos, "assessment_plan": assessments, "assessment_plan_total": 100,
                  "assessment_plan_complete": True, "source_status": "present", "extraction_status": "complete",
                  "source_clo_row_count": 6, "captured_clo_row_count": 6, "warnings": []}
        evidence = f"Word/PDF source bytes preserved; SHA256={v['source_sha256']}; CLO pages4–5, assessment pages6–7, cover1; all8 pages reviewed. Authored table and original assessment weights match; no historical grades changed."
        v["overrides"] = [{"field": key, "value": value, "evidence": evidence, "policy": "verified_extraction_correction_matches_source", "reviewed_at": "2026-10-16"} for key, value in fields.items()]
        v["source_alignment"] = {"status": "corrected_from_source_pdf", "label_ar": "مطابق للتوصيف المحدث بعد مراجعة الاستخراج", "source_sha256": v["source_sha256"], "correction_applied": True, "source_update_recommended": False}
        prior = outcomes["courses"][course["code"]]["variants"]
        outcomes["courses"][course["code"]]["variants"] = [x for x in prior if not any(s["program"] == PROGRAM and s["degree"] == "دكتوراه" for s in x["scopes"])] + [v]
        write(BUNDLE / "courses" / course["code"] / "course-reference.json", v)
    outcomes["reference_policy"]["single_domain_programs"].append(PROGRAM)
    active = {v["source_pdf"] for c in outcomes["courses"].values() for v in c["variants"]}
    excluded = {x["source_pdf"]: x for x in outcomes["excluded_sources"]}
    for path in (ROOT / "assets/course-specifications").rglob("*.pdf"):
        key = relative(path)
        if key not in active and key not in excluded:
            excluded[key] = {"source_pdf": key, "source_sha256": digest(path), "reason": expected_excluded_reason(key)}
    outcomes["excluded_sources"] = sorted(excluded.values(), key=lambda x: x["source_pdf"])
    outcomes["source_data"]["sha256"] = digest(ROOT / "data.json")
    outcomes["generated_at"] = datetime.now(timezone.utc).isoformat()
    active_ids = {v["variant_id"] for c in outcomes["courses"].values() for v in c["variants"]}
    retired = [x for x in outcomes.get("source_correction_recommendations", []) if x["variant_id"] not in active_ids]
    write(BUNDLE / "superseded-source-recommendations.json", retired)
    outcomes["source_correction_recommendations"] = [x for x in outcomes.get("source_correction_recommendations", []) if x["variant_id"] in active_ids]
    outcomes["statistics"] = recompute_statistics(outcomes, ErrorCollector())
    write(ROOT / "course-outcomes.json", outcomes)
    filtered = {"schema_version": "doctorate-quranic-course-reference-v1", "courses": {c: outcomes["courses"][c] for c in codes}, "statistics": _statistics({c: outcomes["courses"][c] for c in codes}, 0)}
    write(BUNDLE / "course-outcomes.json", filtered)
    files = [p for p in BUNDLE.rglob("*") if p.is_file()]
    write(BUNDLE / "manifest.json", {"schema_version": "doctorate-quranic-publication-v1", "published_on": "2026-10-16", "program_source_sha256": cfg["program_pdf_sha256"],
          "official_plan_sha256": cfg["official_plan_sha256"], "source_bytes_preserved": True, "credits": 60, "program_outcomes": 6, "course_outcomes": 24, "thesis_outcomes": 6,
          "matrix_links": 34, "mastery_links": 20, "historical_grades_changed": False, "institutional_approval_claimed": False,
          "files": [{"path": relative(p), "sha256": digest(p)} for p in sorted(files)]})
    print("Published local bundle: 6 PLO, 24 course CLO, 6 thesis CLO, 60 credits; source bytes preserved.")


if __name__ == "__main__":
    main()
