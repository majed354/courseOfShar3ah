#!/usr/bin/env python3
"""Write new-program CLO/PLO mappings into each shared course PDF in place.

The existing NCAAA table is preserved.  Its mapping cell is replaced with one
machine-readable line per new bachelor program.  No program-specific PDF copies
are created.  A dash means that the approved program matrix has no outcome in
the CLO's domain; inventing a cross-domain link is deliberately avoided.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pymupdf

from apply_narrow_clo_plo_corrections import (
    ARIAL,
    dominant_background,
    find_clo_cells,
    get_scopes,
    normalize_text,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
MANIFEST_PATH = ROOT / "assets/course-specifications/unified-new-program-mappings-20260901.json"
AUDIT_PATH = ROOT / "CLO_PLO_NEW_PROGRAM_UNIFIED_AUDIT.md"
PRIOR_MANIFEST = ROOT / "assets/course-specifications/clo-plo-corrections-20260901/manifest.json"
DATE = "2026-09-01"
CURRENT = "$current"
PROGRAM_ORDER = [
    "القرآن وعلومه",
    "القراءات",
    "الدراسات الإسلامية",
    "الشريعة",
    "الأنظمة",
]

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def canonical_clo_token(value: str) -> str | None:
    normalized = str(value).strip().translate(ARABIC_DIGITS)
    match = re.fullmatch(r"([123])[.،,٫](\d+)", normalized)
    return f"{match.group(1)}.{match.group(2)}" if match else None


def find_clo_cells_flexible(document: pymupdf.Document, clo: str):
    raw_candidates = []
    for page in document:
        for word in page.get_text("words", sort=True):
            raw = str(word[4]).strip()
            if canonical_clo_token(raw) == clo and raw not in raw_candidates:
                raw_candidates.append(raw)
    matches = []
    for raw in raw_candidates:
        try:
            matches.append(find_clo_cells(document, raw))
        except RuntimeError:
            continue
    if len(matches) != 1:
        raise RuntimeError(f"Expected one table row for normalized CLO {clo}, found {len(matches)}")
    return matches[0]


def rule(source: str, sha: str, title: str, mappings: dict[str, Any], text_edits: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "input_sha256": sha,
        "title": title,
        "mappings": mappings,
        "text_edits": text_edits or {},
    }


def domains(knowledge: str | None, skill: str | None, value: str | None, *, clo: dict[str, str | None] | None = None) -> dict[str, Any]:
    return {"1": knowledge, "2": skill, "3": value, "clo": clo or {}}


RULES: dict[str, dict[str, Any]] = {
    "2003215-2": rule(
        "assets/course-specifications/2003215-2.pdf",
        "9b2e0abe033321bf98c2346e688acfb820d38e4f988adb301c16302e07c4f0e7",
        "حقوق الإنسان",
        {
            "الدراسات الإسلامية": domains(None, None, None, clo={"3.1": "ق3", "3.2": "ق3", "3.3": "ق2"}),
            "الشريعة": domains("ع1", None, None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", None, clo={"3.1": "ق2", "3.2": "ق2", "3.3": "ق3"}),
        },
    ),
    "2002210-2": rule(
        "assets/course-specifications/local-gap-completion-20260822/quran-culture/2002210-2.pdf",
        "2c3c483937c93e04d28635eb37bb52d9dbce4ac1c82ae509f5013a7e7c5cd2a7",
        "دراسات في علوم القرآن",
        {
            "الدراسات الإسلامية": domains("ع2", None, None),
            "القراءات": domains("ع3", "م2", "ق2"),
        },
    ),
    "2002103-2": rule(
        "assets/course-specifications/qiraat-source-1445/2002103-2.pdf",
        "8354fb861a5d78cf00722e0658bd9364dac5409028dcf338316b9077c37b9251",
        "التجويد (1)",
        {
            "القرآن وعلومه": domains("ع2", "م1", "ق1"),
            "القراءات": domains("ع3", "م2", "ق2"),
        },
    ),
    "2002106-2": rule(
        "assets/course-specifications/qiraat-source-1445/2002106-2.pdf",
        "f7a483a2c8f15ed9498bc64c8bf568ca7910c7027a8ed3762343519f2b4df198",
        "التجويد (2)",
        {
            "القرآن وعلومه": domains("ع2", "م1", "ق1"),
            "القراءات": domains("ع3", "م2", "ق2"),
        },
    ),
    "2002252-2": rule(
        "assets/course-specifications/quranic-course-updates-1446/2002252-2-ulum-alquran-general.pdf",
        "08009f71daffcea8832d51af98d34def7008b2962a0c849bf11119e6e99994c8",
        "علوم القرآن العامة",
        {
            "الأنظمة": domains(CURRENT, CURRENT, CURRENT),
            "الدراسات الإسلامية": domains("ع2", None, None),
            "الشريعة": domains("ع1", None, "ق1"),
            "القرآن وعلومه": domains("ع2", "م3", "ق1"),
            "القراءات": domains("ع3", "م2", "ق2"),
        },
    ),
    "103141-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103141-2.pdf",
        "4e2f115d343d5da0d3a763f9dad7f3fbccb303c6829326c18f31b6ee65671937",
        "البلاغة",
        {
            "الشريعة": domains("ع1", None, None),
            "القراءات": domains("ع2", "م2", "ق1"),
        },
    ),
    "103171-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103171-2.pdf",
        "0659564173c2889c569539f6c1338b97d9d067bf5aafe63071be3f43f78cd53b",
        "التحرير العربي",
        {
            "الدراسات الإسلامية": domains(None, "م3", None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
        {
            "3.1": "أن يتحمل الطالب مسؤولية التحقق من سلامة المعلومات التي يوظفها في التحرير.",
            "3.2": "أن يبادر الطالب إلى تطوير مهاراته في التحرير العربي باستمرار.",
        },
    ),
    "103245-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103245-2.pdf",
        "9ce334f78ecf67d832ff3b3405b35f6a79a92814274c342e5bc61b20e448f206",
        "النحو (3)",
        {
            "الدراسات الإسلامية": domains(None, "م3", None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع2", "م2", "ق1"),
        },
    ),
    "103281-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103281-2.pdf",
        "5754e83ea6d6fd6562c8d4ef1c753371a2369e4a3d4a298183fa84d89aad07dc",
        "النحو (1)",
        {
            "الدراسات الإسلامية": domains(None, "م3", None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع2", "م2", "ق1"),
        },
        {
            "3.1": "أن يتحمل الطالب مسؤولية إنجاز التكليفات النحوية بدقة.",
            "3.2": "أن يبادر الطالب إلى معالجة أخطائه النحوية في التعبير.",
            "3.3": "أن يطور الطالب أداءه في تطبيق القواعد النحوية باستمرار.",
        },
    ),
    "103282-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103282-2.pdf",
        "30805da13e5cbac1443ff5a897e3863a97ff8f8ea08202a5200274ab9d7eb817",
        "النحو (2)",
        {
            "الدراسات الإسلامية": domains(None, "م3", None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع2", "م2", "ق1"),
        },
        {
            "3.1": "أن يتحمل الطالب مسؤولية تطبيق القواعد النحوية في كتاباته.",
            "3.2": "أن يبادر الطالب إلى تصحيح أخطائه النحوية.",
            "3.3": "أن يطور الطالب أداءه في التحليل النحوي باستمرار.",
        },
    ),
    "103349-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103349-2.pdf",
        "b4916b9b316ad84084a7912ff6c4c1eebc7862865ab04a7f882c88a6e4663e4d",
        "النحو (4)",
        {
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع2", "م2", "ق1"),
        },
        {
            "3.1": "أن يتحمل الطالب مسؤولية تطبيق القواعد النحوية المتقدمة بدقة.",
            "3.2": "أن يبادر الطالب إلى تطوير أدائه في التحليل النحوي.",
        },
    ),
    "103411-2": rule(
        "assets/course-specifications/raw-recovery-20260827/103411-2.pdf",
        "3e03f6253863a53e1d25f55053ff1f64e20772732ab609a569b054586d1356f7",
        "الصرف",
        {
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع2", "م2", "ق1"),
        },
        {
            "3.1": "أن يتحمل الطالب مسؤولية ضبط صيغ الكلمات في كتاباته.",
            "3.2": "أن يبادر الطالب إلى تطوير مهاراته الصرفية باستمرار.",
        },
    ),
    "2001112-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2001112-2.pdf",
        "2c61cc5cd856ab38bef825cacbe60cc69b483c0b0766508b0de2dc805834d0a1",
        "المدخل لدراسة الفقه",
        {
            "الأنظمة": domains(CURRENT, CURRENT, CURRENT),
            "الدراسات الإسلامية": domains("ع5", None, None),
            "الشريعة": domains("ع1", None, "ق2"),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
    "2002200-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2002200-2.pdf",
        "47727ddc8313b5ba85b9c85eb25d942e44cdb74f0dac6721e64ce318b8347738",
        "المدخل إلى التفسير الموضوعي",
        {
            "الدراسات الإسلامية": domains("ع2", "م3", None),
            "القراءات": domains("ع2", "م2", "ق2"),
        },
    ),
    "2002220-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2002220-2.pdf",
        "f9ef2786fd27623a5bcbf655ae8762eaf71c7c59df0cf3826e3eda6b13d766af",
        "القرآن الكريم (1)",
        {
            "الدراسات الإسلامية": domains("ع1", "م1", None),
            "الشريعة": domains(None, "م5", None),
        },
    ),
    "2002225-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2002225-2.pdf",
        "fec5aafebaba6ffa9444216f123e224b408d5b78c0242db838dd3e1429891cad",
        "القرآن الكريم (3)",
        {
            "الدراسات الإسلامية": domains("ع1", "م1", None),
            "الشريعة": domains(None, "م5", None),
        },
    ),
    "2002226-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2002226-2.pdf",
        "c2764ca19f5f8165fae31caffd35a8890a8e7f76f0d45d4f418fb8ba61bd44d5",
        "القرآن الكريم (4)",
        {
            "الدراسات الإسلامية": domains("ع1", "م1", None),
            "الشريعة": domains(None, "م5", "ق3"),
        },
    ),
    "2004245-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2004245-2.pdf",
        "e05f75bcc425929761f4e00d06f9dc6a0713c4d601e269ca8fde95cb541b6760",
        "العقيدة (2)",
        {
            "الشريعة": domains(None, None, None, clo={"1.1": "ع3", "1.2": "ع5", "1.3": "ع5"}),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
    "2004258-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2004258-2.pdf",
        "85507cd7c69e94cba9356fef5ed37d904e8eff8053781d255523e426d94b28b0",
        "دراسات في السيرة النبوية",
        {
            "الأنظمة": domains(CURRENT, CURRENT, CURRENT),
            "الدراسات الإسلامية": domains("ع3", None, "ق5"),
            "الشريعة": domains("ع2", None, None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
    "2004273-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2004273-2.pdf",
        "0fea5790322da85c1db2a8cbdd5930ebff9269e1fc933d0d8ddb74d1d2cd7585",
        "العقيدة (1)",
        {
            "الشريعة": domains("ع3", None, None),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
    "2004373-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2004373-2.pdf",
        "8398d8d9b05ecb612faa93c4a3a0b749594801a35880e936be4df8e40370a02c",
        "العقيدة (3)",
        {
            "الشريعة": domains("ع3", None, "ق1"),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
    "2004474-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2004474-2.pdf",
        "1c4ef8d511f7aaea4012229adf1f96ff3f8ed95ef74efdb6fa85467639c64213",
        "العقيدة (4)",
        {
            "الشريعة": domains("ع5", None, "ق2"),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
    "2004493-2": rule(
        "assets/course-specifications/raw-recovery-20260827/2004493-2.pdf",
        "bceaacb6968e38df0a457d29fcf7ffa8be16f69aec2a0210031fa6d3cc9183ef",
        "تخريج ودراسة الأسانيد",
        {
            "الشريعة": domains(None, None, "ق3", clo={"1.1": "ع1", "1.2": "ع3"}),
            "القرآن وعلومه": domains("ع3", None, "ق2"),
            "القراءات": domains("ع3", "م2", "ق1"),
        },
    ),
}


PROGRAM_EVIDENCE = {
    "القرآن وعلومه": {"file": "توصيف القرآن وعلومه.pdf (مصدر مقدم من المستخدم)", "outcomes_pages": [4, 5], "matrix_pages": [10, 11, 12, 13]},
    "الدراسات الإسلامية": {"file": "توصيف الدراسات الإسلامية.pdf (مصدر مقدم من المستخدم)", "outcomes_pages": [4, 5], "matrix_pages": [11, 12, 13, 14]},
    "القراءات": {"file": "ااااالملفات الخام/OneDrive_1447-05-01/توصيف برنامج القراءات المطور معتمد 2024.docx", "outcomes_pages": [8], "matrix_pages": [16, 17]},
    "الشريعة": {"file": "توصيفات البرامج/الشريعة جديد.pdf", "outcomes_pages": [4, 5], "matrix_pages": [8, 9, 10]},
    "الأنظمة": {"file": None, "status": "preserved_from_current_course_specification"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def program_scopes_for_source(data: dict[str, Any], source: str, prior_to_source: dict[str, str]) -> list[str]:
    programs = set()
    for detail in data["course_details"].values():
        for variant in detail.get("variants", []):
            url = variant.get("pdf_url", "")
            canonical = prior_to_source.get(url, url)
            if canonical != source:
                continue
            for scope in get_scopes(variant):
                if scope.get("degree") == "بكالوريوس" and scope.get("plan_type") == "جديدة":
                    programs.add(scope.get("program"))
    return [name for name in PROGRAM_ORDER if name in programs]


def resolve_mapping(mapping: dict[str, Any], clo: str, old_mapping: str) -> str:
    override = mapping.get("clo", {}).get(clo, "__missing__")
    value = mapping.get(clo.split(".", 1)[0]) if override == "__missing__" else override
    if value == CURRENT:
        return old_mapping or "—"
    return value or "—"


def replace_mapping_cell(page: pymupdf.Page, rect: pymupdf.Rect, lines: list[str]) -> float:
    background = dominant_background(page, rect)
    redaction = pymupdf.Rect(rect.x0 + 0.35, rect.y0 + 0.35, rect.x1 - 0.35, rect.y1 - 0.35)
    page.add_redact_annot(redaction, fill=background, cross_out=False)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    font_size = {2: 8.8, 3: 7.2, 4: 6.6, 5: 5.8}.get(len(lines), 8.8)
    insertion = pymupdf.Rect(rect.x0 + 1.2, rect.y0 + 1.0, rect.x1 - 1.2, rect.y1 - 1.0)
    css = f"""
        @font-face {{ font-family: SiteArabic; src: url('{ARIAL.name}'); }}
        html, body {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
        .box {{ box-sizing: border-box; width: 100%; height: 100%; display: flex;
          flex-direction: column; justify-content: center; align-items: stretch;
          padding: 1pt 4pt; direction: rtl; text-align: right;
          font-family: SiteArabic; font-size: {font_size}pt; line-height: 1.02;
          color: #000000; white-space: nowrap; }}
    """
    body = "<br>".join(html.escape(line) for line in lines)
    spare, scale = page.insert_htmlbox(
        insertion,
        f'<div class="box" dir="rtl">{body}</div>',
        css=css,
        archive=pymupdf.Archive(str(ARIAL.parent)),
        scale_low=0.50,
        overlay=True,
    )
    if spare < 0:
        raise RuntimeError(f"Multiline mapping did not fit: {lines}")
    return float(scale)


def replace_outcome_cell(page: pymupdf.Page, rect: pymupdf.Rect, text: str) -> float:
    background = dominant_background(page, rect)
    redaction = pymupdf.Rect(rect.x0 + 0.35, rect.y0 + 0.35, rect.x1 - 0.35, rect.y1 - 0.35)
    page.add_redact_annot(redaction, fill=background, cross_out=False)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    insertion = pymupdf.Rect(rect.x0 + 1.5, rect.y0 + 1.2, rect.x1 - 1.5, rect.y1 - 1.2)
    css = f"""
        @font-face {{ font-family: SiteArabic; src: url('{ARIAL.name}'); }}
        html, body {{ width: 100%; height: 100%; margin: 0; padding: 0; }}
        .box {{ box-sizing: border-box; width: 100%; height: 100%; display: flex;
          align-items: center; justify-content: flex-start; padding: 2pt 4pt;
          direction: rtl; text-align: right; font-family: SiteArabic;
          font-size: 10.7pt; line-height: 1.08; color: #000000; }}
    """
    spare, scale = page.insert_htmlbox(
        insertion,
        f'<div class="box" dir="rtl">{html.escape(text)}</div>',
        css=css,
        archive=pymupdf.Archive(str(ARIAL.parent)),
        scale_low=0.58,
        overlay=True,
    )
    if spare < 0:
        raise RuntimeError(f"Outcome text did not fit: {text}")
    return float(scale)


def discover_clos(document: pymupdf.Document) -> list[str]:
    candidates: list[str] = []
    for page in document:
        for word in page.get_text("words", sort=True):
            value = canonical_clo_token(str(word[4]))
            if value and value not in candidates:
                candidates.append(value)
    found = []
    for clo in candidates:
        try:
            _, _, _, _, old_text, _ = find_clo_cells_flexible(document, clo)
        except RuntimeError:
            continue
        if normalize_text(old_text):
            found.append(clo)
    return found


def stage_one_pdf(course_key: str, item: dict[str, Any], programs: list[str]) -> tuple[dict[str, Any], Path | None]:
    path = ROOT / item["source"]
    before_hash = sha256(path)
    old_record = None
    if MANIFEST_PATH.exists():
        existing_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        old_record = next((r for r in existing_manifest.get("records", []) if r["course_key"] == course_key), None)
    incremental = bool(old_record and before_hash == old_record.get("output_sha256"))
    if not incremental and before_hash != item["input_sha256"]:
        raise RuntimeError(f"Unexpected input hash for {item['source']}: {before_hash}")

    document = pymupdf.open(path)
    clos = discover_clos(document)
    if not clos:
        raise RuntimeError(f"No CLO rows discovered in {item['source']}")
    previous_edits = {edit["clo"]: edit for edit in old_record.get("edits", [])} if incremental else {}
    missing_clos = [clo for clo in clos if clo not in previous_edits]
    if incremental and not missing_clos:
        document.close()
        return old_record, None

    edits = []
    for clo in clos:
        if clo in previous_edits:
            edits.append(previous_edits[clo])
            continue
        page, outcome_cell, mapping_cell, _, old_text, old_mapping = find_clo_cells_flexible(document, clo)
        per_program = {
            program: resolve_mapping(item["mappings"][program], clo, old_mapping)
            for program in programs
        }
        lines = [f"{program}: {per_program[program]}" for program in programs]
        edit_record: dict[str, Any] = {
            "page_1_based": page.number + 1,
            "clo": clo,
            "text_from": old_text,
            "mapping_from": old_mapping,
            "mapping_to": "\n".join(lines),
            "per_program": per_program,
            "mapping_rect": [round(v, 3) for v in mapping_cell],
            "mapping_scale": replace_mapping_cell(page, mapping_cell, lines),
        }
        if clo in item["text_edits"]:
            edit_record["text_to"] = item["text_edits"][clo]
            edit_record["outcome_rect"] = [round(v, 3) for v in outcome_cell]
            edit_record["text_scale"] = replace_outcome_cell(page, outcome_cell, item["text_edits"][clo])
        edits.append(edit_record)

    document.set_metadata({**document.metadata, "modDate": "D:20260901000000+03'00'"})
    temporary = path.with_name(path.stem + ".unified-new-programs.tmp.pdf")
    document.save(temporary, garbage=4, deflate=True, clean=True)
    document.close()
    subprocess.run(["qpdf", "--check", str(temporary)], check=True, capture_output=True, text=True)
    output_hash = sha256(temporary)
    with pymupdf.open(temporary) as verified:
        page_count = len(verified)
    return {
        "course_key": course_key,
        "title": item["title"],
        "path": item["source"],
        "input_sha256": old_record.get("input_sha256", item["input_sha256"]) if incremental else item["input_sha256"],
        "output_sha256": output_hash,
        "programs": programs,
        "page_count": page_count,
        "edits": edits,
    }, temporary


def update_data_json(data: dict[str, Any], prior_to_source: dict[str, str]) -> dict[str, int]:
    rule_sources = {item["source"] for item in RULES.values()}
    changed = 0
    unified_variants = 0
    for detail in data["course_details"].values():
        for variant in detail.get("variants", []):
            url = variant.get("pdf_url", "")
            canonical = prior_to_source.get(url, url)
            if canonical not in rule_sources:
                continue
            if url != canonical:
                variant["pdf_url"] = canonical
                changed += 1
            note = "ملف موحّد؛ يعرض ربط كل برنامج جديد في سطر مستقل وفق مصفوفة نواتجه بتاريخ 2026-09-01."
            current = variant.get("match_note", "").strip()
            if note not in current:
                variant["match_note"] = (current + " " + note).strip()
            unified_variants += 1
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"rerouted_variants": changed, "unified_variants": unified_variants}


def markdown_cell(value: Any) -> str:
    text = str(value if value not in (None, "") else "—")
    return text.replace("|", "\\|").replace("\n", "<br>")


def write_audit(manifest: dict[str, Any]) -> None:
    records = manifest["records"]
    edits = [edit for record in records for edit in record["edits"]]
    rewritten = sum("text_to" in edit for edit in edits)
    blank_links = sum(
        value == "—"
        for edit in edits
        for value in edit["per_program"].values()
    )
    lines = [
        "# الحصر التفصيلي للربط الموحّد بمخرجات البرامج الجديدة",
        "",
        f"تاريخ التنفيذ: {DATE}م.",
        "",
        "## الملخص",
        "",
        f"- عُدّل **{len(records)} ملف مقرر مشترك** في مكانه، من غير إنشاء نسخة مستقلة لكل برنامج.",
        f"- عولجت **{len(edits)} خلية ربط**، وأعيدت صياغة **{rewritten} مخرجات مقررات** كانت مشوشة أو بعيدة عن موضوع المقرر.",
        "- يرد كل برنامج جديد في سطر مستقل داخل خلية الربط الحالية، حتى عند تطابق الرمز بين برنامجين.",
        "- لا ترد الخطط القديمة في خلية الربط. وعلامة «—» تعني أن مصفوفة البرنامج الجديدة لا تخصص ناتجًا في مجال ذلك المخرج.",
        f"- بلغ عدد حالات «—» **{blank_links}**؛ وهي امتناع مقصود عن اختراع ربط بين مجالين مختلفين.",
        "- في برنامج الأنظمة فقط حُفظ الرمز الموجود في توصيف المقرر للصفوف المشتركة؛ لأن توصيف البرنامج الجديد ومصفوفته غير متاحين ضمن المصادر الحالية.",
        "",
        "## جدول التعديلات التفصيلي",
        "",
        "| م | المقرر | الصفحة | رمز مخرج المقرر | النص القديم | النص الجديد | الربط القديم | الربط الجديد (برنامج في كل سطر) | سبب التعديل | شاهد البرنامج |",
        "|---:|---|---:|---|---|---|---|---|---|---|",
    ]
    index = 0
    for record in records:
        evidence_parts = []
        for program in record["programs"]:
            evidence = PROGRAM_EVIDENCE[program]
            if evidence.get("file"):
                pages = evidence.get("matrix_pages", [])
                evidence_parts.append(f"{program}: `{evidence['file']}`، ص " + "، ".join(map(str, pages)))
            else:
                evidence_parts.append(f"{program}: حُفظ الرمز المثبت في ملف المقرر لعدم توافر مصفوفة البرنامج الجديدة")
        evidence_text = "<br>".join(evidence_parts)
        for edit in record["edits"]:
            index += 1
            text_to = edit.get("text_to", "لم يتغير")
            reasons = ["استبدال الرمز المفرد بسطور مستقلة لبرامج الخطة الجديدة وفق مصفوفة كل برنامج."]
            if "—" in edit["per_program"].values():
                reasons.append("لم يوضع ربط في برنامج لا تخصص مصفوفتُه ناتجًا في مجال المخرج.")
            if "text_to" in edit:
                reasons.append("صُححت الصياغة لفساد النص أو بعده عن موضوع المقرر.")
            cells = [
                index,
                f"`{record['course_key']}` — {record['title']}",
                edit["page_1_based"],
                f"`{edit['clo']}`",
                edit["text_from"],
                text_to,
                edit["mapping_from"] or "—",
                edit["mapping_to"],
                " ".join(reasons),
                evidence_text,
            ]
            lines.append("| " + " | ".join(markdown_cell(cell) for cell in cells) + " |")

    lines.extend([
        "",
        "## ضوابط الأتمتة",
        "",
        "- الصيغة الثابتة لكل سطر هي: `اسم البرنامج: رمز الناتج`.",
        "- ترتيب البرامج ثابت: القرآن وعلومه، القراءات، الدراسات الإسلامية، الشريعة، الأنظمة؛ ويظهر من هذا الترتيب ما يرتبط بالمقرر فقط.",
        "- لم يُنشأ جدول جديد، ولم تتغير أعمدة نموذج التوصيف أو بنيته.",
        "- المصدر الآلي الكامل: `assets/course-specifications/unified-new-program-mappings-20260901.json`.",
    ])
    AUDIT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not ARIAL.exists():
        raise RuntimeError(f"Arabic font not found: {ARIAL}")
    previous_run_manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.exists()
        else {}
    )
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    prior_to_source: dict[str, str] = {}
    if PRIOR_MANIFEST.exists():
        prior = json.loads(PRIOR_MANIFEST.read_text(encoding="utf-8"))
        prior_to_source = {record["output"]: record["source"] for record in prior.get("records", [])}

    records = []
    staged: list[tuple[Path, Path]] = []
    try:
        for course_key, item in RULES.items():
            programs = program_scopes_for_source(data, item["source"], prior_to_source)
            expected = [name for name in PROGRAM_ORDER if name in item["mappings"]]
            if programs != expected:
                raise RuntimeError(f"Program scope mismatch for {course_key}: {programs} != {expected}")
            record, temporary = stage_one_pdf(course_key, item, programs)
            records.append(record)
            if temporary is not None:
                staged.append((temporary, ROOT / item["source"]))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    except Exception:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        raise

    data_changes = update_data_json(data, prior_to_source)
    data_changes["rerouted_variants"] = max(
        data_changes["rerouted_variants"],
        previous_run_manifest.get("data_changes", {}).get("rerouted_variants", 0),
    )
    manifest = {
        "generated_at": DATE,
        "policy": "ملف مقرر واحد، وبرنامج جديد واحد في كل سطر داخل خلية الربط الحالية، دون ذكر الخطط القديمة.",
        "file_count": len(records),
        "mapping_cell_count": sum(len(record["edits"]) for record in records),
        "data_changes": data_changes,
        "program_evidence": PROGRAM_EVIDENCE,
        "records": records,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_audit(manifest)
    print(json.dumps({
        "files": len(records),
        "mapping_cells": manifest["mapping_cell_count"],
        **data_changes,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
