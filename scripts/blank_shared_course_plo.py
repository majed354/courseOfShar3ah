#!/usr/bin/env python3
"""Publish shared-course specifications with an empty program-outcome column.

A course is shared only when its normalized code-and-name identity occurs in at
least two distinct academic programs.  A program identity is ``(name, degree)``;
plan type and version are deliberately excluded so that an old/new plan pair
for one program is not classified as sharing.

Source PDFs are never overwritten.  The script writes hash-bound copies to a
dated bundle, clears only non-empty body cells in the existing PLO column, and
reroutes the corresponding ``data.json`` variants after every PDF validates.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import pymupdf

from apply_narrow_clo_plo_corrections import (
    dominant_background,
    find_clo_cells,
    get_scopes,
)
from apply_unified_new_program_mappings import canonical_clo_token


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
OUTCOMES_PATH = ROOT / "course-outcomes.json"
BUNDLE_RELATIVE = Path(
    "assets/course-specifications/shared-course-blank-plo-20260905"
)
BUNDLE = ROOT / BUNDLE_RELATIVE
MANIFEST_PATH = BUNDLE / "manifest.json"
AUDIT_PATH = ROOT / "SHARED_COURSE_PLO_BLANKING_AUDIT.md"
DATE = "2026-09-05"
POLICY_NOTE = (
    "المقرر مشترك بين برامج مختلفة؛ أُبقيت خلايا رمز ناتج البرنامج فارغة "
    "لتتولى كل جهة برنامجية الربط المناسب (2026-09-05)."
)
ARABIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)
DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670\u0640]")
PLO_TOKEN_RE = re.compile(r"(?<!\w)[عمقكKSVP]\s*[0-9]{1,2}(?:\.[0-9]+)?(?!\w)")
PROGRAM_LABELS = (
    "القرآن وعلومه",
    "القراءات",
    "الدراسات الإسلامية",
    "الشريعة",
    "الأنظمة",
)
LEGACY_MAPPING_VALUE_RE = re.compile(
    r"(?:TUGA\s*[-:]?\s*[0-9]|(?<![0-9])[0-9]\s*(?:[.\-،,]|\s+[،,])\s*[0-9])",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_identity(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(ARABIC_DIGITS)
    text = DIACRITICS_RE.sub("", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def scope_key(scope: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(
        clean_text(scope.get(field))
        for field in ("program", "degree", "plan_type", "version")
    )


def rect_key(rect: pymupdf.Rect) -> tuple[float, float, float, float]:
    return tuple(round(float(value), 2) for value in rect)


def contains_rect(outer: pymupdf.Rect, inner: pymupdf.Rect, tolerance: float = 1.0) -> bool:
    center = (inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2
    return (
        outer.x0 - tolerance <= center[0] <= outer.x1 + tolerance
        and outer.y0 - tolerance <= center[1] <= outer.y1 + tolerance
    )


def build_shared_inventory(data: dict[str, Any]) -> dict[str, Any]:
    identities: dict[tuple[str, str], dict[str, Any]] = {}
    for program in data.get("programs", []):
        program_identity = (
            clean_text(program.get("name")),
            clean_text(program.get("degree")),
        )
        plan = {
            "program": program_identity[0],
            "degree": program_identity[1],
            "plan_type": clean_text(program.get("plan_type")),
            "version": clean_text(program.get("version")),
        }
        for course in program.get("courses", []):
            key = (clean_text(course.get("code")), normalize_identity(course.get("name")))
            item = identities.setdefault(
                key,
                {
                    "course_code": key[0],
                    "normalized_name": key[1],
                    "names": set(),
                    "programs": set(),
                    "plans": [],
                },
            )
            item["names"].add(clean_text(course.get("name")))
            item["programs"].add(program_identity)
            item["plans"].append(plan)

    shared = [item for item in identities.values() if len(item["programs"]) > 1]
    shared.sort(key=lambda item: (item["course_code"], item["normalized_name"]))

    by_pdf: dict[str, dict[str, Any]] = {}
    for item in shared:
        detail = data.get("course_details", {}).get(item["course_code"], {})
        matching = [
            variant
            for variant in detail.get("variants", [])
            if normalize_identity(variant.get("title")) == item["normalized_name"]
            and clean_text(variant.get("pdf_url"))
        ]
        item["variant_count"] = len(matching)
        item["pdfs"] = sorted({variant["pdf_url"] for variant in matching})
        for variant in matching:
            source = clean_text(variant["pdf_url"])
            target = by_pdf.setdefault(
                source,
                {
                    "source": source,
                    "course_keys": set(),
                    "titles": set(),
                    "selectors": {},
                },
            )
            target["course_keys"].add(item["course_code"])
            target["titles"].update(item["names"])
            for scope in get_scopes(variant):
                target["selectors"][scope_key(scope)] = copy.deepcopy(scope)

    return {"shared": shared, "by_pdf": by_pdf}


def outcome_rows_for_pdf(
    outcomes: dict[str, Any], source: str, course_keys: set[str]
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for course_key in sorted(course_keys):
        for variant in outcomes.get("courses", {}).get(course_key, {}).get("variants", []):
            if clean_text(variant.get("source_pdf")) != source:
                continue
            for clo in variant.get("extracted", {}).get("clos", []):
                code = clean_text(clo.get("code"))
                if not code:
                    continue
                item = rows.setdefault(
                    code,
                    {
                        "clo": code,
                        "page_1_based": int(clo["source_page"]),
                        "document_plo_codes": set(),
                        "mapped_status_present": False,
                    },
                )
                if item["page_1_based"] != int(clo["source_page"]):
                    raise RuntimeError(f"Conflicting pages for {source} CLO {code}")
                item["document_plo_codes"].update(clo.get("document_plo_codes") or [])
                item["mapped_status_present"] = item["mapped_status_present"] or any(
                    mapping.get("status") == "mapped"
                    for mapping in clo.get("plo_mappings", [])
                    if isinstance(mapping, dict)
                )
    output = []
    for item in rows.values():
        item["document_plo_codes"] = sorted(item["document_plo_codes"])
        output.append(item)
    output.sort(key=lambda item: (item["page_1_based"], tuple(map(int, item["clo"].split(".")))))
    return output


def page_tables(page: pymupdf.Page) -> list[Any]:
    return list(page.find_tables().tables)


def find_clo_cell_on_page(
    document: pymupdf.Document, page_1_based: int, clo: str
) -> tuple[Any, ...]:
    page = document[page_1_based - 1]
    raw_candidates = []
    for word in page.get_text("words", sort=True):
        raw = str(word[4]).strip()
        if canonical_clo_token(raw) == clo and raw not in raw_candidates:
            raw_candidates.append(raw)
    matches = []
    for raw in raw_candidates:
        try:
            matches.append(find_clo_cells(document, raw, page_1_based))
        except RuntimeError:
            continue
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one table row for normalized CLO {clo}, found {len(matches)}"
        )
    return matches[0]


def cells_containing_text(
    page: pymupdf.Page,
    tables: Iterable[Any],
    token: str,
) -> list[tuple[Any, pymupdf.Rect]]:
    hits = page.search_for(token)
    found: dict[tuple[float, float, float, float], tuple[Any, pymupdf.Rect]] = {}
    for hit in hits:
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    if not cell:
                        continue
                    rect = pymupdf.Rect(cell)
                    if contains_rect(rect, hit):
                        found.setdefault(rect_key(rect), (table, rect))
    return list(found.values())


def infer_column_from_codes(
    page: pymupdf.Page,
    tables: list[Any],
    plo_codes: Iterable[str],
) -> tuple[Any, pymupdf.Rect] | None:
    candidates: dict[tuple[float, float, float, float], tuple[Any, pymupdf.Rect]] = {}
    for code in plo_codes:
        for table, rect in cells_containing_text(page, tables, code):
            if 35 <= rect.width <= 180 and page.rect.width * 0.18 <= rect.x0 <= page.rect.width * 0.72:
                candidates.setdefault(rect_key(rect), (table, rect))
    if not candidates:
        return None
    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -sum(code in clean_text(page.get_textbox(item[1])) for code in plo_codes),
            item[1].width,
            item[1].x0,
        ),
    )
    return ranked[0]


def matching_column_cells(
    page: pymupdf.Page,
    tables: list[Any],
    anchors: list[tuple[Any | None, pymupdf.Rect]],
) -> list[pymupdf.Rect]:
    output: dict[tuple[float, float, float, float], pymupdf.Rect] = {}
    for anchor_table, anchor in anchors:
        candidate_tables = [anchor_table] if anchor_table is not None else tables
        for table in candidate_tables:
            if table is None:
                continue
            for row in table.rows:
                for cell in row.cells:
                    if not cell:
                        continue
                    rect = pymupdf.Rect(cell)
                    if abs(rect.x0 - anchor.x0) > 2.5 or abs(rect.x1 - anchor.x1) > 2.5:
                        continue
                    value = clean_text(page.get_textbox(rect))
                    normalized = normalize_identity(value)
                    if not value:
                        continue
                    if "برنامج" in normalized and ("ناتج" in normalized or "مرتبط" in normalized):
                        continue
                    output.setdefault(rect_key(rect), rect)
    return list(output.values())


def legacy_program_outcome_cells(
    page: pymupdf.Page, tables: list[Any]
) -> list[pymupdf.Rect]:
    """Find populated mapping cells in older TUGA/numeric-only templates.

    Some official Taif University forms label the program-outcome column but
    store values as ``1-3`` or ``TUGA-2-1``.  Those are intentionally outside
    the modern PLO token parser.  This fallback is geometry-bound to a table
    column whose own header identifies it as the graduate-attribute/program-
    outcome column, then accepts only digit-bearing mapping-shaped values.
    """

    output: dict[tuple[float, float, float, float], pymupdf.Rect] = {}
    for table in tables:
        populated: list[tuple[pymupdf.Rect, str, str]] = []
        for row in table.rows:
            for cell in row.cells:
                if not cell:
                    continue
                rect = pymupdf.Rect(cell)
                value = clean_text(page.get_textbox(rect))
                if value:
                    populated.append((rect, value, normalize_identity(value)))

        header_centers = []
        for rect, _value, normalized in populated:
            is_header = (
                "مخرج التعلم المرتبط" in normalized
                or "خصائص الخريجين" in normalized
                or "خصائص خريجي جامعه" in normalized
                or ("الطائف" in normalized and "مرتبطه بناتج" in normalized)
            )
            if is_header:
                header_centers.append((rect.x0 + rect.x1) / 2)
        if not header_centers:
            continue

        for rect, value, normalized in populated:
            center = (rect.x0 + rect.x1) / 2
            if min(abs(center - anchor) for anchor in header_centers) > 12:
                continue
            if "مخرج التعلم المرتبط" in normalized or "خصائص" in normalized:
                continue
            if not LEGACY_MAPPING_VALUE_RE.search(value):
                continue
            output.setdefault(rect_key(rect), rect)
    return list(output.values())


def redact_cell(page: pymupdf.Page, rect: pymupdf.Rect) -> tuple[float, float, float]:
    background = dominant_background(page, rect)
    interior = pymupdf.Rect(
        rect.x0 + 0.35, rect.y0 + 0.35, rect.x1 - 0.35, rect.y1 - 0.35
    )
    page.add_redact_annot(interior, fill=background, cross_out=False)
    return background


def output_relative_for(source: str, course_key: str) -> Path:
    tag = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    return BUNDLE_RELATIVE / f"{course_key}--{tag}.pdf"


def process_pdf(
    source_record: dict[str, Any], outcomes: dict[str, Any]
) -> tuple[dict[str, Any], Path]:
    source_relative = source_record["source"]
    course_keys = set(source_record["course_keys"])
    if len(course_keys) != 1:
        raise RuntimeError(
            f"One PDF resolved to multiple course codes: {source_relative}: {course_keys}"
        )
    course_key = next(iter(course_keys))
    source = ROOT / source_relative
    if not source.is_file():
        raise FileNotFoundError(source_relative)
    rows = outcome_rows_for_pdf(outcomes, source_relative, course_keys)
    if not rows:
        raise RuntimeError(f"No extracted CLO rows for {source_relative}")

    document = pymupdf.open(source)
    tables_by_page: dict[int, list[Any]] = {}
    anchors_by_page: dict[int, list[tuple[Any | None, pymupdf.Rect]]] = defaultdict(list)
    row_edits: list[dict[str, Any]] = []

    for row in rows:
        page = document[row["page_1_based"] - 1]
        tables = tables_by_page.setdefault(page.number, page_tables(page))
        edit: dict[str, Any] = {
            "clo": row["clo"],
            "page_1_based": row["page_1_based"],
            "plo_from": row["document_plo_codes"],
            "plo_to": [],
            "blank_by_policy": True,
        }
        try:
            found_page, _outcome, mapping, _code, _text, old_mapping = (
                find_clo_cell_on_page(document, row["page_1_based"], row["clo"])
            )
            if found_page.number != page.number:
                raise RuntimeError("CLO resolved on an unexpected page")
            matched_table = next(
                (
                    table
                    for table in tables
                    if contains_rect(pymupdf.Rect(table.bbox), mapping)
                ),
                None,
            )
            anchors_by_page[page.number].append((matched_table, mapping))
            edit["mapping_rect"] = list(rect_key(mapping))
            edit["physical_text_from"] = clean_text(old_mapping)
        except RuntimeError as error:
            edit["mapping_rect"] = None
            edit["geometry_note"] = str(error)
        row_edits.append(edit)

    # Pages with no CLO-code anchor (notably one legacy systems form) are
    # anchored by an exact published PLO token and its containing table cell.
    for page_number in sorted({row["page_1_based"] - 1 for row in rows}):
        if anchors_by_page.get(page_number):
            continue
        page = document[page_number]
        plo_codes = sorted(
            {
                code
                for row in rows
                if row["page_1_based"] - 1 == page_number
                for code in row["document_plo_codes"]
            }
        )
        inferred = infer_column_from_codes(
            page, tables_by_page.setdefault(page_number, page_tables(page)), plo_codes
        )
        if inferred:
            anchors_by_page[page_number].append(inferred)

    cleared_cells: list[dict[str, Any]] = []
    for page_number, anchors in sorted(anchors_by_page.items()):
        page = document[page_number]
        tables = tables_by_page[page_number]
        for rect in matching_column_cells(page, tables, anchors):
            value = clean_text(page.get_textbox(rect))
            if not value:
                continue
            cleared_cells.append(
                {
                    "page_1_based": page_number + 1,
                    "mapping_rect": list(rect_key(rect)),
                    "text_from": value,
                }
            )
            background = redact_cell(page, rect)
            cleared_cells[-1]["background"] = [round(value, 6) for value in background]

    if not cleared_cells:
        for page_number in sorted({row["page_1_based"] - 1 for row in rows}):
            page = document[page_number]
            tables = tables_by_page.setdefault(page_number, page_tables(page))
            for rect in legacy_program_outcome_cells(page, tables):
                value = clean_text(page.get_textbox(rect))
                cleared_cells.append(
                    {
                        "page_1_based": page_number + 1,
                        "mapping_rect": list(rect_key(rect)),
                        "text_from": value,
                        "detection": "legacy_program_outcome_column",
                    }
                )
                background = redact_cell(page, rect)
                cleared_cells[-1]["background"] = [
                    round(component, 6) for component in background
                ]
                anchors_by_page.setdefault(page_number, [])

    if not cleared_cells:
        document.close()
        raise RuntimeError(f"No non-empty PLO cells found for shared PDF {source_relative}")

    for page_number in anchors_by_page:
        document[page_number].apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        # Paint the cell interior after redaction.  This removes residual edge
        # fragments from right-aligned Arabic glyphs whose bounding boxes cross
        # the cell boundary, without touching the neighbouring outcome cell.
        page = document[page_number]
        for cell in cleared_cells:
            if cell["page_1_based"] != page_number + 1:
                continue
            rect = pymupdf.Rect(cell["mapping_rect"])
            interior = pymupdf.Rect(
                rect.x0 + 0.45, rect.y0 + 0.45, rect.x1 - 0.45, rect.y1 - 0.45
            )
            page.draw_rect(
                interior,
                color=None,
                fill=tuple(cell["background"]),
                width=0,
                overlay=True,
            )

    output_relative = output_relative_for(source_relative, course_key)
    output = ROOT / output_relative
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.pdf")
    document.set_metadata({**document.metadata, "modDate": "D:20260905000000+03'00'"})
    document.save(temporary, garbage=4, deflate=True, clean=True)
    document.close()
    subprocess.run(
        ["qpdf", "--check", str(temporary)], check=True, capture_output=True, text=True
    )

    with pymupdf.open(temporary) as verified:
        for cell in cleared_cells:
            rect = pymupdf.Rect(cell["mapping_rect"])
            remaining = clean_text(
                verified[cell["page_1_based"] - 1].get_textbox(rect)
            )
            if PLO_TOKEN_RE.search(remaining) or any(
                label in remaining for label in PROGRAM_LABELS
            ):
                raise RuntimeError(
                    f"PLO cell still contains a program mapping in {output_relative}, "
                    f"page {cell['page_1_based']}: {remaining!r}"
                )
        page_count = len(verified)

    record = {
        "course_key": course_key,
        "title": " / ".join(sorted(source_record["titles"])),
        "source": source_relative,
        "source_sha256": sha256(source),
        "output": output_relative.as_posix(),
        "output_sha256": sha256(temporary),
        "page_count": page_count,
        "selectors": [
            source_record["selectors"][key]
            for key in sorted(source_record["selectors"])
        ],
        "program_identities": sorted(
            {
                (clean_text(scope.get("program")), clean_text(scope.get("degree")))
                for scope in source_record["selectors"].values()
            }
        ),
        "edits": row_edits,
        "cleared_cells": cleared_cells,
    }
    return record, temporary


def strip_superseded_note(note: str) -> str:
    text = clean_text(note)
    superseded = (
        r"ملف موحّد؛ يعرض ربط كل برنامج جديد في سطر مستقل وفق مصفوفة نواتجه بتاريخ 2026-09-01\.",
        r"وربطت خلايا نواتج البرنامج بالبرامج الخمسة في حزمة 2026-09-04 المقيّدة بالبصمة\.",
    )
    for pattern in superseded:
        text = re.sub(pattern, "", text)
    return clean_text(text)


def update_data_json(
    data: dict[str, Any], records: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, int]]:
    route = {record["source"]: record["output"] for record in records}
    updated = copy.deepcopy(data)
    changed_variants = 0
    notes_updated = 0
    for detail in updated.get("course_details", {}).values():
        for variant in detail.get("variants", []):
            source = clean_text(variant.get("pdf_url"))
            if source not in route:
                continue
            variant["pdf_url"] = route[source]
            changed_variants += 1
            note = strip_superseded_note(variant.get("match_note", ""))
            if POLICY_NOTE not in note:
                variant["match_note"] = clean_text(f"{note} {POLICY_NOTE}")
                notes_updated += 1
    return updated, {
        "rerouted_variants": changed_variants,
        "updated_notes": notes_updated,
    }


def markdown(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "\\|")


def write_audit(
    inventory: dict[str, Any], manifest: dict[str, Any]
) -> None:
    shared = inventory["shared"]
    records_by_course: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in manifest["records"]:
        records_by_course[record["course_key"]].append(record)
    with_spec = [item for item in shared if item["variant_count"]]
    without_spec = [item for item in shared if not item["variant_count"]]
    lines = [
        "# جرد المقررات المشتركة وتفريغ رمز ناتج البرنامج",
        "",
        f"تاريخ التنفيذ: {manifest.get('latest_recovery_at', DATE)}م.",
        "",
        "## القاعدة",
        "",
        "- هوية المقرر هي الرمز والاسم بعد تطبيع الأرقام والهمزات والتشكيل.",
        "- هوية البرنامج هي اسم البرنامج والدرجة العلمية فقط.",
        "- تكرار المقرر في الخطة القديمة والجديدة للبرنامج نفسه لا يجعله مقررًا مشتركًا.",
        "- يصبح المقرر مشتركًا عند ظهوره في هويتي برنامج مختلفتين على الأقل.",
        "- في التوصيف المنشور للمقرر المشترك تبقى خلايا «رمز ناتج التعلم المرتبط بالبرنامج» فارغة، ويتولى كل برنامج الربط المناسب لاحقًا.",
        "",
        "## الملخص",
        "",
        f"- المقررات المشتركة: **{len(shared)}** هوية.",
        f"- المقررات المشتركة ذات توصيف منشور: **{len(with_spec)}** هوية.",
        f"- المقررات المشتركة بلا توصيف منشور: **{len(without_spec)}** هوية.",
        f"- ملفات PDF المنشورة المعالجة: **{len(manifest['records'])}** ملفًا.",
        f"- صفوف CLO المشمولة بالسياسة: **{manifest['clo_row_count']}** صفًا.",
        f"- خلايا PLO غير الفارغة التي مُسحت فعليًا: **{manifest['cleared_cell_count']}** خلية.",
        f"- روابط المتغيرات التي حُوّلت إلى النسخ المنقحة: **{manifest['data_changes']['rerouted_variants']}** رابطًا.",
        "",
        "## الجرد التفصيلي",
        "",
        "| م | رمز المقرر | اسم المقرر | البرامج المختلفة | ظهورات الخطط | حالة التوصيف | ملفات التوصيف المنقحة | خلايا PLO المفرغة |",
        "|---:|---|---|---|---:|---|---:|---:|",
    ]
    for index, item in enumerate(shared, 1):
        programs = "، ".join(
            f"{name} ({degree})" for name, degree in sorted(item["programs"])
        )
        records = records_by_course.get(item["course_code"], [])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    f"`{markdown(item['course_code'])}`",
                    markdown(" / ".join(sorted(item["names"]))),
                    markdown(programs),
                    str(len(item["plans"])),
                    "منقح" if records else "لا يوجد توصيف منشور",
                    str(len(records)),
                    str(sum(len(record["cleared_cells"]) for record in records)),
                ]
            )
            + " |"
        )
    AUDIT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_PATH.read_text(encoding="utf-8"))
    inventory = build_shared_inventory(data)
    BUNDLE.mkdir(parents=True, exist_ok=True)

    pending: list[tuple[dict[str, Any], Path]] = []
    for source in sorted(inventory["by_pdf"]):
        pending.append(process_pdf(inventory["by_pdf"][source], outcomes))

    records = [record for record, _temporary in pending]
    updated_data, data_changes = update_data_json(data, records)
    manifest = {
        "generated_at": DATE,
        "policy": (
            "رمز ناتج البرنامج فارغ في كل توصيف لمقرر يخدم برنامجين مختلفين "
            "على الأقل؛ لا تُعد الخطط القديمة والجديدة للبرنامج نفسه برامج مختلفة."
        ),
        "program_identity_fields": ["program", "degree"],
        "course_identity_fields": ["course_code", "normalized_course_name"],
        "shared_course_count": len(inventory["shared"]),
        "shared_course_with_spec_count": sum(
            bool(item["variant_count"]) for item in inventory["shared"]
        ),
        "shared_course_without_spec_count": sum(
            not item["variant_count"] for item in inventory["shared"]
        ),
        "output_count": len(records),
        "clo_row_count": sum(len(record["edits"]) for record in records),
        "cleared_cell_count": sum(
            len(record["cleared_cells"]) for record in records
        ),
        "data_changes": data_changes,
        "records": records,
    }

    # Publish only after every staged PDF passed qpdf, hash, and empty-cell checks.
    for record, temporary in pending:
        output = ROOT / record["output"]
        os.replace(temporary, output)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_audit(inventory, manifest)
    data_temp = DATA_PATH.with_suffix(".shared-plo.tmp.json")
    data_temp.write_text(
        json.dumps(updated_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(data_temp, DATA_PATH)

    print(f"Shared course identities: {manifest['shared_course_count']}")
    print(f"Shared identities with specifications: {manifest['shared_course_with_spec_count']}")
    print(f"Output PDFs: {manifest['output_count']}")
    print(f"CLO rows covered: {manifest['clo_row_count']}")
    print(f"Non-empty PLO cells cleared: {manifest['cleared_cell_count']}")
    print(f"Data variants rerouted: {data_changes['rerouted_variants']}")


if __name__ == "__main__":
    main()
