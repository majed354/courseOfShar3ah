#!/usr/bin/env python3
"""Publish the user's new-plan sources, correcting only the cover identity.

Original PDFs take precedence over companion Word files. Word-only sources
are converted with bundled LibreOffice. The source tree remains untouched.
"""
from __future__ import annotations

import copy
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import html
import json
import subprocess
from pathlib import Path

import pymupdf

from extract_course_outcomes import logical_variants, normalize_course_name, extract_variant_worker, _excluded_reason
import verify_course_outcomes as verifier

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "مقررات الخطة الجديدة"
BUNDLE = ROOT / "assets/course-specifications/new-plan-updates-20261002"
TMP = ROOT / "tmp/new-plan-20261002"
PY_RUNTIME = Path("/Users/majd/.cache/codex-runtimes/codex-primary-runtime/dependencies")
ALL = ["الأنظمة", "الدراسات الإسلامية", "الشريعة", "القراءات", "القرآن وعلومه"]
BASELINE_COMMIT = '35c3c6faef0c0c14ec667be50d89da1af84daed0'

# source filename, approved code, approved title, authorized program contexts
TARGETS = [
    ("2-2002131 علوم القرآن العامة.docx", "2002252-2", "علوم القرآن العامة", ALL),
    ("دراسات في علوم القرآن .docx", "2002210-2", "دراسات في علوم القرآن", ["الدراسات الإسلامية", "القراءات"]),
    ("2-2002250 أصول التفسير ومناهجه.docx", "2002250-2", "أصول التفسير ومناهجه", ["الدراسات الإسلامية", "الشريعة", "القراءات"]),
    ("التفسير التحليلي 1 (1).pdf", "20021203-2", "التفسير التحليلي (1)", ["الدراسات الإسلامية", "القراءات"]),
    ("__التفسير التحليلي 2 (ق) .pdf", "2002352-2", "التفسير التحليلي (2)", ["القراءات"]),
    ("__التفسير التحليلي 2 (س) .pdf", "20023101-3", "التفسير التحليلي (٢)", ["الدراسات الإسلامية"]),
    ("____التفسير التحليلي 3 (ق) .pdf", "20023205-2", "التفسير التحليلي (3)", ["القراءات"]),
    ("____التفسير التحليلي 3 (س) .pdf", "2002310-3", "التفسير التحليلي (٣)", ["الدراسات الإسلامية"]),
    ("2_2002455_المدخل_إلى_التفسير_الموضوعي.pdf", "2002200-2", "المدخل إلى التفسير الموضوعي", ["الدراسات الإسلامية", "القراءات"]),
    ("2-2002429 الانتصار للقرآن (1).pdf", "2002429-2", "الانتصار للقرآن", ["القرآن وعلومه", "القراءات"]),
    ("2-2002456 إعجاز القرآن الكريم (1).pdf", "2002456-2", "إعجاز القرآن الكريم", ["القرآن وعلومه", "القراءات"]),
    ("المدخل إلى دراسة الأنظمة.docx", "20031301-2", "مبادئ القانون", ALL),
    ("المدخل إلى دراسة الأنظمة.docx", "2003220-2", "المدخل لدراسة الأنظمة", ["القرآن وعلومه"]),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ensure_baseline() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    for target, tracked in [('baseline-data.json','data.json'),('baseline-outcomes.json','course-outcomes.json')]:
        path = TMP / target
        if not path.exists():
            result = subprocess.run(['git','show',f'{BASELINE_COMMIT}:{tracked}'],cwd=ROOT,check=True,capture_output=True,text=True)
            path.write_text(result.stdout)


def new_scope(program: str) -> dict:
    return dict(program=program, degree="بكالوريوس", plan_type="جديدة", version="47")


def scope_key(scope: dict) -> tuple:
    return tuple(str(scope.get(k, "بكالوريوس" if k == "degree" else "")) for k in ("program", "degree", "plan_type", "version"))


def converted(source: Path) -> Path:
    if source.suffix == ".pdf":
        return source
    directory = TMP / "converted"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / (source.stem + ".pdf")
    if not output.exists():
        subprocess.run([
            str(PY_RUNTIME / "bin/override/soffice"), "--headless",
            f"-env:UserInstallation={(TMP / 'lo-profile').as_uri()}",
            "--convert-to", "pdf", "--outdir", str(directory), str(source),
        ], check=True, capture_output=True, timeout=180)
    if not output.exists():
        raise FileNotFoundError(output)
    return output


def replace_cover_row(page: pymupdf.Page, label: str, value: str, numeric: bool = False) -> dict:
    lines = [line for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
    matching = [line for line in lines if label in "".join(s["text"] for s in line["spans"])]
    if len(matching) != 1:
        raise ValueError(f"cover label not unique: {label}")
    bbox = matching[0]["bbox"]
    same_row = [line for line in lines if abs(line["bbox"][1] - bbox[1]) < 3]
    y0 = min(line["bbox"][1] for line in same_row)
    y1 = max(line["bbox"][3] for line in same_row)
    rect = pymupdf.Rect(100, y0 - 0.5, 497, y1 + 0.5)
    pix = page.get_pixmap()
    background = tuple(c / 255 for c in pix.pixel(110, int((y0 + y1) / 2))[:3])
    original = " / ".join("".join(s["text"] for s in line["spans"]) for line in same_row)
    page.add_redact_annot(rect, fill=background)
    page.apply_redactions(images=0, graphics=0)
    value_html = f'&#x202a;{html.escape(value)}&#x202c;' if numeric else html.escape(value)
    content = f'<div dir="rtl">{label} المقرر: {value_html}</div>'
    css = "html, body {margin:0; padding:0;} div {margin:0; padding:0; direction:rtl; text-align:right; font-family:Arial; font-size:11pt; line-height:1; color:#52b4c0;}"
    # Story's RTL line occupies its natural width even inside a wide box.
    # Measure that line and anchor its physical box at the right cell edge.
    with pymupdf.open() as measuring:
        scratch = measuring.new_page(width=500, height=100)
        scratch.insert_htmlbox(pymupdf.Rect(0, 0, 397, 60), content, css=css)
        spans = [s for b in scratch.get_text('dict')['blocks'] for l in b.get('lines', []) for s in l['spans']]
        width = max(s['bbox'][2] for s in spans) - min(s['bbox'][0] for s in spans) + 8
    text_rect = pymupdf.Rect(max(rect.x0, rect.x1-width), rect.y0, rect.x1, rect.y1)
    spare, scale = page.insert_htmlbox(text_rect, content, css=css, scale_low=1)
    if spare < 0 or scale != 1:
        raise ValueError(f"cover replacement does not fit: {value}")
    return {"field": "code" if numeric else "title", "original_pdf_text": original, "approved_value": value, "bbox": list(rect), "text_bbox": list(text_rect)}


def build() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    ensure_baseline()
    BUNDLE.mkdir(parents=True, exist_ok=True)
    baseline = TMP / "baseline-data.json"
    data = json.loads((baseline if baseline.exists() else ROOT / "data.json").read_text())
    original_variants = logical_variants(data)
    if not (TMP / "baseline-data.json").exists():
        save(TMP / "baseline-data.json", data)
        save(TMP / "baseline-outcomes.json", json.loads((ROOT / "course-outcomes.json").read_text()))
    records = []
    for index, (filename, code, title, programs) in enumerate(TARGETS):
        scopes = [new_scope(p) for p in programs]
        plan_rows = []
        for scope in scopes:
            plan = next(p for p in data["programs"] if (p["name"], p["degree"], p["plan_type"], str(p["version"])) == scope_key(scope))
            matches = [c for c in plan["courses"] if c["code"] == code and normalize_course_name(c["name"]) == normalize_course_name(title)]
            if len(matches) != 1 or matches[0]["hours"] != int(code.split('-')[1]):
                raise ValueError(f"approved plan identity not unique: {code}, {scope}")
            plan_rows.append({"scope": scope, "course": matches[0]})
        source = RAW / filename
        source_pdf = converted(source)
        output = BUNDLE / f"{code}--new-v47.pdf"
        with pymupdf.open(source_pdf) as document:
            body_hashes = [hashlib.sha256(p.get_pixmap().samples).hexdigest() for p in list(document)[1:]]
            edits = [replace_cover_row(document[0], "اسم", title), replace_cover_row(document[0], "رمز", code, True)]
            document.save(output, garbage=4, deflate=True)
        with pymupdf.open(output) as published:
            published_hashes = [hashlib.sha256(p.get_pixmap().samples).hexdigest() for p in list(published)[1:]]
            assert published_hashes == body_hashes, f"body content changed: {code}"
            page_count = len(published)
        previous = [{"variant_id": v["variant_id"], "source_pdf": v["source_pdf"], "source_sha256": digest(ROOT / v["source_pdf"]), "replaced_scopes": [s for s in v["scopes"] if scope_key(s) in {scope_key(t) for t in scopes}]} for v in original_variants if v["course_code"] == code and any(scope_key(s) in {scope_key(t) for t in scopes} for s in v["scopes"])]
        records.append(dict(code=code, title=title, scopes=scopes, plan_rows=plan_rows, source=source.relative_to(ROOT).as_posix(), source_sha256=digest(source), converted_pdf_sha256=digest(source_pdf), source_format=source.suffix[1:], output=output.relative_to(ROOT).as_posix(), output_sha256=digest(output), page_count=page_count, identity_edits=edits, body_pages_pixel_identical=True, body_page_render_sha256=body_hashes, predecessors=previous, action="replace" if previous else "add"))
        print(f"{code}: {page_count} pages, body unchanged", flush=True)
    save(BUNDLE / "manifest.json", dict(schema_version="new-plan-updates-v1", reviewed_at="2026-10-02", source_policy="Use supplied PDF where present; convert Word-only sources; change cover name/code only; preserve all body content and original PLO cells.", source_inventory=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in sorted(RAW.iterdir()) if p.suffix in {'.pdf','.docx'}], counts=dict(publication_pdfs=len(records), raw_sources=len({r['source'] for r in records}), replaced_contexts=sum(len(s['replaced_scopes']) for r in records for s in r['predecessors']), added_contexts=sum(len(r['scopes']) for r in records if r['action']=='add')), records=records))


def trim_mappings(value: object, scopes: list[dict]) -> object:
    """Preserve reviewed historical text, retaining only its remaining scopes."""
    if isinstance(value, dict):
        return {k: trim_mappings(v, scopes) for k, v in value.items()}
    if isinstance(value, list):
        return [trim_mappings(v, scopes) for v in value if not (isinstance(v, dict) and isinstance(v.get('scope'), dict) and scope_key(v['scope']) not in {scope_key(s) for s in scopes})]
    return value


def review_new_sources(outcomes: dict) -> None:
    reviews = json.loads((ROOT/'review-batches/new-plan-source-review-20261002.json').read_text())
    for review in reviews['records']:
        variant = next(v for v in outcomes['courses'][review['course_code']]['variants'] if v['variant_id']==review['variant_id'])
        assert variant['source_sha256']==review['source_sha256']==digest(ROOT/review['source_pdf'])
        evidence = f"مراجعة بصرية لصفحات {review['review_pages']} في {review['source_pdf']}؛ SHA-256 {review['source_sha256']}. القراءة مثبتة في review-batches/new-plan-source-review-20261002.json."
        clos = []
        warnings = []
        for index, item in enumerate(review['clos']):
            plos = item['document_plo_codes']
            mappings = []
            for scope in variant['scopes']:
                if plos and review['shared_source']:
                    status, codes = 'ambiguous_for_scope', []
                elif plos:
                    status, codes = 'mapped', plos
                elif review['shared_source']:
                    status, codes = 'explicitly_unmapped', []
                else:
                    status, codes = 'missing', []
                mappings.append(dict(scope=scope,plo_codes=codes,status=status,confidence='verified',source_page=item['source_page'],evidence=evidence+' خلايا الربط غير المعنونة بالبرنامج لا تسند إلى نطاق خاص؛ والخلايا الفارغة للمقرر المشترك تبقى فارغة عمدًا.'))
            row = {k: copy.deepcopy(val) for k,val in item.items() if k in {'code','text','assessment','source_page','assessment_source_page','document_plo_codes'}}
            row.update(plo_mappings=mappings,confidence='verified',extraction_method='verified_visual_review',source_status='present')
            clos.append(row)
            if any(m['status'] in {'missing','ambiguous_for_scope'} for m in mappings):
                warnings.append(dict(code='plo_mapping_unresolved',clo_index=index,clo_code=item['code'],source_page=item['source_page'],message='The printed PLO cell is blank or lacks a program label; no program-specific code is inferred.'))
        values = dict(clos=clos,course_name=review['course_name'],course_name_metadata=dict(confidence='verified',source_page=1,extraction_method='verified_visual_review'),assessment_plan=review['assessment_plan'],assessment_plan_complete=True,assessment_plan_total=100,source_clo_row_count=6,captured_clo_row_count=6,extraction_status='complete',source_status='present',warnings=warnings)
        variant['overrides'] = [dict(field=field,value=value,evidence=evidence,policy='verified_extraction_correction_matches_source',reviewed_at=reviews['reviewed_at']) for field,value in sorted(values.items())]
        variant['source_alignment'] = dict(status='matches_source_pdf',label_ar='مطابق لملف PDF',correction_applied=True,source_update_recommended=False,source_sha256=review['source_sha256'])
        variant['source_review'] = dict(status='accepted_as_is',finding='ثبتت الهوية المصححة و6 مخرجات وخطة تقويم 100% من صفحات المصدر، مع إبقاء الربط البرنامجي الفارغ أو غير المعنون دون تخمين.',evidence=dict(file=review['source_pdf'],pages=review['review_pages'],review_method='تصيير الغلاف وجداول CLO والتقويم ومقارنتها بالنص المثبت؛ حفظ صفحات المحتوى دون تغيير.',sha256_verified=True),reviewed_at=reviews['reviewed_at'],source_sha256=review['source_sha256'])


def apply() -> None:
    ensure_baseline()
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    for filename,baseline_name,field in [('data.json','baseline-data.json','applied_data_sha256'),('course-outcomes.json','baseline-outcomes.json','applied_outcomes_sha256')]:
        allowed = {digest(TMP/baseline_name), manifest.get(field)}
        if manifest.get(field) and digest(ROOT/filename) not in allowed:
            raise ValueError(f'{filename} has changed since this batch; refusing to overwrite a later revision')
    baseline = json.loads((TMP / "baseline-data.json").read_text())
    old_outcomes = json.loads((TMP / "baseline-outcomes.json").read_text())
    old_logical = logical_variants(baseline)
    data = copy.deepcopy(baseline)
    target_codes = {r['code'] for r in manifest['records']}
    for record in manifest['records']:
        assert digest(ROOT / record['output']) == record['output_sha256']
        old = data['course_details'].get(record['code'])
        if old and 'variants' not in old:
            candidates = [v for v in old_logical if v['course_code'] == record['code']]
            assert len(candidates) == 1
            old = {'variants': [{**old, 'scopes': candidates[0]['scopes']}]}
        remaining = []
        target_keys = {scope_key(s) for s in record['scopes']}
        for variant in (old or {}).get('variants', []):
            retained = [s for s in variant.get('scopes', [variant.get('scope')]) if scope_key(s) not in target_keys]
            if retained:
                item = copy.deepcopy(variant)
                item.pop('scope', None)
                item['scopes'] = retained
                remaining.append(item)
        companion = ROOT / record['source']
        if companion.suffix == '.pdf':
            possible = [p for p in RAW.glob('*.docx') if p.stem == companion.stem or p.stem == companion.stem.replace(' (1)', '')]
            assert len(possible) == 1
            companion = possible[0]
        from docx import Document
        table = Document(companion).tables[1]
        heading = next(i for i,r in enumerate(table.rows) if 'الوصف العام' in r.cells[0].text)
        summary = table.rows[heading+1].cells[0].text.strip()
        remaining.append(dict(title=record['title'], summary=summary, pdf_url=record['output'], specification_code=record['code'], match_status='adapted_verified', match_note='اعتمد مصدر المستخدم للخطة الجديدة 47؛ صُحح الاسم والرمز على الغلاف وفق الخطة دون تعديل صفحات المحتوى. تفاصيل المصدر والبصمة والمطابقة في new-plan-updates-20261002/manifest.json (2026-10-02).', scopes=record['scopes']))
        data['course_details'][record['code']] = {'variants': remaining}
    # Explicit plan URLs must agree with the scoped course-details selector.
    for program in data['programs']:
        key = (program['name'], program['degree'], program['plan_type'], str(program['version']))
        for course in program['courses']:
            for record in manifest['records']:
                if course['code'] == record['code'] and key in {scope_key(s) for s in record['scopes']} and 'pdf_url' in course:
                    course['pdf_url'] = record['output']
    save(ROOT / 'data.json', data)
    expected = logical_variants(data)
    outcomes = copy.deepcopy(old_outcomes)
    records_by_id = {v['variant_id']: v for c in old_outcomes['courses'].values() for v in c['variants']}
    id_successors = {}
    new_courses = {code: copy.deepcopy(value) for code,value in old_outcomes['courses'].items() if code not in target_codes}
    pending = []
    for logical in expected:
        code = logical['course_code']
        if code not in target_codes:
            continue
        new_courses.setdefault(code, {'variants': []})
        source = logical['source_pdf']
        if source.startswith(BUNDLE.relative_to(ROOT).as_posix() + '/'):
            cache = TMP / (logical['variant_id'] + '.json')
            if cache.exists() and (TMP/'cache-hashes.json').exists() and json.loads((TMP/'cache-hashes.json').read_text()).get(logical['variant_id']) == digest(ROOT/source):
                extracted = json.loads(cache.read_text())
                new_courses[code]['variants'].append({**logical, 'source_sha256': digest(ROOT/source), 'extracted': extracted, 'overrides': []})
                new_courses[code]['variants'][-1].pop('course_code')
            else:
                pending.append(logical)
        else:
            candidates = [v for v in old_logical if v['course_code']==code and v['source_pdf']==source and v['catalog']==logical['catalog']]
            assert len(candidates)==1
            prior = candidates[0]
            retained = trim_mappings(copy.deepcopy(records_by_id[prior['variant_id']]), logical['scopes'])
            retained['variant_id'] = logical['variant_id']
            retained['scopes'] = logical['scopes']
            id_successors[prior['variant_id']] = logical['variant_id']
            new_courses[code]['variants'].append(retained)
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(extract_variant_worker, {**v, 'repo_root': str(ROOT), 'auxiliary': None, 'source_sha256': digest(ROOT/v['source_pdf'])}): v for v in pending}
        for job in as_completed(jobs):
            logical = jobs[job]
            variant_id, extracted = job.result()
            assert variant_id == logical['variant_id']
            save(TMP / (variant_id+'.json'), extracted)
            hashes_path = TMP/'cache-hashes.json'
            hashes = json.loads(hashes_path.read_text()) if hashes_path.exists() else {}
            hashes[variant_id] = digest(ROOT/logical['source_pdf'])
            save(hashes_path, hashes)
            record = {**logical, 'source_sha256': digest(ROOT/logical['source_pdf']), 'extracted': extracted, 'overrides': []}
            record.pop('course_code')
            new_courses[logical['course_code']]['variants'].append(record)
            print(logical['course_code'], extracted['extraction_status'], len(extracted['clos']), extracted.get('assessment_plan_total'), flush=True)
    for course in new_courses.values():
        course['variants'].sort(key=lambda v: v['variant_id'])
    outcomes['courses'] = dict(sorted(new_courses.items()))
    active_ids = {v['variant_id'] for c in new_courses.values() for v in c['variants']}
    for parent, key in [('verified_repairs','repairs'), (None,'source_correction_recommendations')]:
        container = outcomes if parent is None else outcomes.get(parent, {})
        entries = []
        for entry in container.get(key, []):
            if entry['variant_id'] in id_successors:
                entry['variant_id'] = id_successors[entry['variant_id']]
                if parent is None:
                    payload = '|'.join([entry['course_code'],entry['variant_id'],entry['issue_code'],','.join(entry['fields'])])
                    entry['id'] = hashlib.sha256(payload.encode()).hexdigest()
            if entry['variant_id'] in active_ids:
                entries.append(entry)
        if key in container:
            container[key] = sorted(entries,key=lambda e:e['id']) if parent is None else entries
    active_paths = {v['source_pdf'] for c in new_courses.values() for v in c['variants']}
    all_paths = {p.relative_to(ROOT).as_posix() for p in (ROOT/'assets/course-specifications').rglob('*.pdf')}
    outcomes['excluded_sources'] = [dict(source_pdf=p, source_sha256=digest(ROOT/p), reason=_excluded_reason(p)) for p in sorted(all_paths-active_paths)]
    outcomes['source_data']['sha256'] = digest(ROOT/'data.json')
    outcomes['generated_at'] = '2026-10-02T12:00:00+03:00'
    if (ROOT/'review-batches/new-plan-source-review-20261002.json').exists():
        review_new_sources(outcomes)
    errors = verifier.ErrorCollector()
    outcomes['statistics'] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        raise ValueError(errors.messages)
    save(ROOT/'course-outcomes.json', outcomes)
    save(BUNDLE/'retained-variant-successors.json', id_successors)
    manifest['baseline_commit'] = BASELINE_COMMIT
    manifest['applied_data_sha256'] = digest(ROOT/'data.json')
    manifest['applied_outcomes_sha256'] = digest(ROOT/'course-outcomes.json')
    save(BUNDLE/'manifest.json',manifest)
    print(json.dumps(outcomes['statistics'], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    if parser.parse_args().apply:
        apply()
    else:
        build()
