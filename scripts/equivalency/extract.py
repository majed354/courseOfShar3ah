"""Extract topic rows without asking a language model to invent missing text."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path

import pdfplumber

from scripts.extract_course_outcomes import logical_region_text

ROOT = Path(__file__).resolve().parents[2]
PROGRAM = "القرآن وعلومه"
EXTRACTOR_VERSION = "topic-grid-v7"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.sub(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u200e\u200f\u202a-\u202e\u2066-\u2069ـ]", "", value)
    return " ".join(value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).split())


def compact(value):
    return re.sub(r"[\W_]", "", norm(value))


def extract_pdf(path):
    """Read bounded topic cells; keep original rows, locations and excluded rows.

    Merged hour cells define physical rows. This avoids treating wrapped lines
    as different topics and stitches continuation tables on the following page.
    Unreadable or missing tables remain explicit, never model-completed.
    """
    path = Path(path)
    topics, excluded, warnings, sections = [], [], [], []
    active = None
    with pdfplumber.open(path) as document:
        if len(document.pages) > 40:
            raise ValueError("التجربة تقبل توصيف مقرر واحد لا يزيد عن 40 صفحة")
        for page_number, page in enumerate(document.pages, 1):
            tables = sorted(page.find_tables(), key=lambda t: (t.bbox[1], -(t.bbox[2] - t.bbox[0])))
            consumed = []
            for table in tables:
                if table.bbox[2] - table.bbox[0] < page.width * .55:
                    continue
                if any(abs(table.bbox[1] - y) < 2 for y in consumed):
                    continue
                header = None
                for row in table.rows[:3]:
                    for cell in row.cells:
                        if not cell or not page.width * .38 < cell[2] - cell[0] < (table.bbox[2] - table.bbox[0]) * .88:
                            continue
                        header_text = logical_region_text(page, cell)
                        if len(header_text) > 70:
                            continue
                        text = compact(header_text)
                        if any(h in text for h in ("الموضوعات", "موضوعات", "المضات", "الموضات", "الموضوع", "محتوىالمقرر")):
                            header = cell
                            break
                    if header:
                        break
                if header:
                    continuation = False
                    active = {"x0": header[0], "x1": header[2], "table_x0": table.bbox[0], "last_page": page_number}
                    body_top = header[3]
                    sections.append(page_number)
                elif active and page_number == active["last_page"] + 1 and table.bbox[1] < 160 and abs(table.bbox[0] - active["table_x0"]) < 10:
                    continuation = True
                    # Only the first table on the immediate next page can continue.
                    body_top = table.bbox[1]
                    first = compact(logical_region_text(page, (active["x0"], body_top, active["x1"], min(body_top + 25, table.bbox[3]))))
                    if first in ("أنشطةالتقييم", "المراجع", "استراتيجياتالتدريس", "المرافق"):
                        active = None
                        continue
                else:
                    continue
                x0, x1 = active["x0"], active["x1"]
                spans = []
                for row in table.rows:
                    for c in row.cells:
                        if c and c[2] <= x0 + 1 and c[2] - c[0] > page.width * .07 and c[1] >= body_top - 1 and c[3] - c[1] > 7:
                            spans.append(c)
                # Drop nested duplicates produced by borders and merged cells.
                rows = []
                for c in sorted(spans, key=lambda c: (c[1], -(c[3] - c[1]))):
                    if any(c[1] >= r[1] - 1 and c[3] <= r[3] + 1 for r in rows):
                        continue
                    rows.append(c)
                for c in rows:
                    bbox = [round(x0 + .6, 2), round(c[1] + .4, 2), round(x1 - .6, 2), round(c[3] - .4, 2)]
                    text = norm(logical_region_text(page, bbox))
                    hours_raw = norm(logical_region_text(page, c))
                    key = compact(text)
                    if not key:
                        continue
                    if key in ("المجموع", "مجموع", "اع", "وع", "المجمو", "اجمالي", "الإجمالي"):
                        active = None
                        break
                    if any(k in key for k in ("قائمةالم", "قاالم", "قاهم", "التدريسيةالمتوقعة")):
                        continue
                    record = {"text": text, "page": page_number, "bbox": bbox, "hours_raw": hours_raw}
                    if len(text) < 85 and any(k in key for k in ("مراجعة", "راجعة", "اختبارنهائي", "الاختبارالنهائي", "اختبارفصلي", "الاختبارالفصلي", "اختبارنصفي", "الاختبارالنصفي")):
                        excluded.append({**record, "reason": "مراجعة أو اختبار؛ ليس مفردة موضوعية"})
                        continue
                    if not hours_raw and continuation and topics and abs(c[1] - body_top) < 2 and len(key) >= 3:
                        previous = topics[-1]
                        previous.setdefault("fragments", [{"page": previous["page"], "bbox": previous["bbox"]}]).append({"page": page_number, "bbox": bbox})
                        previous["text"] += " " + text
                        previous["end_page"] = page_number
                        continue
                    # A references/equipment table on the next page is not a
                    # topic continuation. Its left cells contain prose, not hours.
                    numeric_hours = bool(re.fullmatch(r"[0-9٠-٩۰-۹]+(?:[.٫][0-9٠-٩۰-۹]+)?", hours_raw))
                    if not hours_raw or not (numeric_hours or "سا" in compact(hours_raw)) or len(hours_raw) > 40:
                        active = None
                        break
                    if len(text) < 85 and any(k in key for k in ("مراجعة", "راجعة", "اختبارنهائي", "الاختبارالنهائي", "اختبارفصلي", "الاختبارالفصلي", "اختبارنصفي", "الاختبارالنصفي")):
                        excluded.append({**record, "reason": "مراجعة أو اختبار؛ ليس مفردة موضوعية"})
                    elif len(key) < 3:
                        warnings.append(f"نص قصير غير محسوم في الصفحة {page_number}: {text}")
                    else:
                        corrected = text
                        if "البيع" in text:
                            corrected = corrected.replace("وشوطه", "وشروطه").replace("والشوط", "والشروط").replace("المرادبه", "المراد به")
                        if "الإجارة" in text and "بالشكة" in text:
                            corrected = corrected.replace("بالشكة", "بالشركة").replace("والمساقة", "والمساقاة")
                        correction = {} if corrected == text else {"corrected_text": corrected,
                            "correction_method": "contextual_inference", "correction_note": "استعادة حروف/مسافات من سياق أبواب فقه المعاملات بتفويض المستخدم؛ يبقى الأصل محفوظًا"}
                        topics.append({"id": f"t{len(topics) + 1}", **record, **correction})
                if active:
                    active["last_page"] = page_number
                consumed.append(table.bbox[1])
            page.close()
    if not topics:
        warnings.append("لم يستخرج جدول موضوعات موثوق؛ يلزم فحص الصفحة أو إدخال المفردات يدويًا")
    # Contextual readings are a separate layer, never a replacement of PDF text.
    for topic in topics:
        text = topic.get("corrected_text", topic["text"])
        corrected = re.sub(r"\(cid:(?:13|127)\)", "", text)
        corrected = corrected.replace("\uf048", "صلى الله عليه وسلم").replace("\uf076", "").replace("\uf0b7", "")
        corrected = corrected.replace("المدلƒس", "المدلس").replace("المر سل الخفي", "المرسل الخفي")
        if len(corrected) > 85:
            corrected = re.sub(r"^\s*الاختبار النصفي\s*", "", corrected)
        if "(cid:" in text or re.search(r"[A-Z]{2,}", text) or any(c in text for c in ("\uf076", "\uf0b7")):
            corrected = re.sub(r"(?<=[\u0621-\u064a])\s*[NBTz]+\s*(?=[\u0621-\u064a])", "", corrected)
            corrected = corrected.replace("أصو هم", "أصولهم").replace("أهل ا السنة", "أهل السنة").replace("عند ا الصوفية", "عند الصوفية")
            corrected = corrected.replace("المع ˆل", "المعلل")
        corrected = " ".join(corrected.split())
        if corrected != topic["text"]:
            topic.update(corrected_text=corrected, correction_method="contextual_inference",
                         correction_note="قراءة مستكملة من سياق الموضوع؛ أزيلت رموز امتداد/تشكيل تالفة وحفظ النص الخام ومواضع صفحاته")
    if any("(cid:" in t.get("corrected_text", t["text"]) or "\ufffd" in t.get("corrected_text", t["text"]) for t in topics):
        warnings.append("يوجد نص غير مقروء في مفردات مستخرجة")
    return {"source_sha256": digest(path), "extractor": EXTRACTOR_VERSION,
            "topics": topics, "excluded_rows": excluded, "warnings": warnings,
            "status": "extracted_needs_review" if topics and not warnings else "needs_review",
            "reviewed": False}


def apply_readings(extracted, root=ROOT):
    path = root / "equivalency-pilot/topic-readings.json"
    if not path.exists():
        return extracted
    readings = json.loads(path.read_text())
    # Both the PDF and the exact raw row must agree before applying a reading.
    for topic in extracted["topics"]:
        raw_hash = hashlib.sha256(topic["text"].encode()).hexdigest()
        for reading in readings.get("readings", []):
            if reading["source_sha256"] == extracted.get("source_sha256") and reading["raw_text_sha256"] == raw_hash:
                topic.update(corrected_text=reading["corrected_text"], correction_method=reading["method"], correction_note=reading["note"])
    return extracted


def effective_data(root=ROOT):
    # Reuse the actual overlay, including identity guards and excluded scopes.
    code = "const fs=require('fs');const path=require('path');const r=process.argv[1];const data=JSON.parse(fs.readFileSync(path.join(r,'data.json')));const edits=JSON.parse(fs.readFileSync(path.join(r,'site-edits.json')));process.stdout.write(JSON.stringify(require(path.join(r,'assets/js/site-edits.js')).apply(data,edits)));"
    return json.loads(subprocess.check_output(["node", "-e", code, str(root)]))


def matches(scope, context):
    return all(not norm(scope.get(k)) or norm(scope[k]) == norm(context.get(k)) for k in ("program", "degree", "plan_type", "version"))


def select_details(data, course, context):
    raw = data.get("course_details", {}).get(course["code"], {})
    variants = raw.get("variants", [raw])
    eligible = [v for v in variants if norm(v.get("title")) == norm(course["name"])
                and not any(matches(s, context) for s in v.get("excluded_scopes", []))]
    scopes = lambda v: v.get("scopes", [v["scope"]] if v.get("scope") else [])
    return next((v for v in eligible if any(matches(s, context) for s in scopes(v))),
                next((v for v in eligible if not scopes(v)), None))


def build_catalog(output, root=ROOT):
    data = effective_data(root)
    cache_dir = root / "runtime/equivalency/extraction"
    cache_dir.mkdir(parents=True, exist_ok=True)
    courses = []
    for p in data["programs"]:
        if p["name"] != PROGRAM or p["degree"] != "بكالوريوس":
            continue
        context = {"program": p["name"], "degree": p["degree"], "plan_type": p["plan_type"], "version": str(p["version"])}
        for course in p["courses"]:
            details = select_details(data, course, context)
            item = {"id": hashlib.sha256(json.dumps([context, course["code"], course["name"]], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20],
                    "code": course["code"], "name": course["name"], "hours": course.get("hours"), "context": context,
                    "topics": [], "status": "missing_pdf", "reviewed": False, "warnings": []}
            if details and details.get("pdf_url"):
                url = details["pdf_url"]
                path = (root / url).resolve()
                if not path.is_relative_to((root / "assets").resolve()) or not path.is_file():
                    item["warnings"].append("المصدر ليس ملفًا محليًا متاحًا؛ لا يُجلب رابط خارجي تلقائيًا")
                else:
                    sha = digest(path)
                    cached = cache_dir / f"{EXTRACTOR_VERSION}-{sha}.json"
                    if cached.exists():
                        extracted = json.loads(cached.read_text())
                    else:
                        try:
                            extracted = extract_pdf(path)
                        except Exception as e:
                            extracted = {"source_sha256": sha, "topics": [], "status": "needs_review", "reviewed": False, "warnings": [str(e)]}
                        cached.write_text(json.dumps(extracted, ensure_ascii=False, indent=2))
                    item.update(apply_readings(json.loads(json.dumps(extracted)), root), source_pdf=url, match_status=details.get("match_status"), source_note=details.get("match_note", ""))
                    unknown = [t["id"] for t in item["topics"] if norm(t.get("corrected_text", t["text"])) in ("أخرى", "اخرى", "غير محدد")]
                    if unknown:
                        item["warnings"].append("مفردة غير محددة في المصدر: " + ", ".join(unknown) + "؛ لا تُستكمل بالتخمين")
                        item["status"] = "needs_review"
            courses.append(item)
            print(f"{context['version']} {item['code']}: {len(item['topics'])} topics; {item['status']}", flush=True)
    source_hashes = {name: digest(root / name) for name in ("data.json", "site-edits.json")}
    if (root / "equivalency-pilot/topic-readings.json").exists():
        source_hashes["equivalency-pilot/topic-readings.json"] = digest(root / "equivalency-pilot/topic-readings.json")
    catalog = {"schema_version": 1, "program": PROGRAM, "extractor": EXTRACTOR_VERSION,
               "source_hashes": source_hashes, "courses": courses,
               "policy": {"coverage_threshold": 80, "strict_topic_threshold": 80, "lenient_topic_threshold": 60, "weighting": "topic_count", "direction": "uploaded_to_target"}}
    catalog["catalog_id"] = hashlib.sha256(json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    return catalog
