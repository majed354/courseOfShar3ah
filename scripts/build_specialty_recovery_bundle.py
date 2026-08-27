#!/usr/bin/env python3
"""Build the seven-course specialty recovery PDF bundle.

The source PDFs remain untouched. Two exact specifications are sliced from the
combined Islamic Studies source and receive the Islamic Culture department
stamp. Five already approved and stamped specifications receive a narrow,
cover-title-only adaptation so their visible titles match the plan catalogue.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import fitz
import arabic_reshaper
from bidi.algorithm import get_display
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


BACKGROUND = (241 / 255, 242 / 255, 241 / 255)
ARIAL = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
SAKKAL_REGULAR = Path(
    "/Users/majd/Library/Group Containers/UBF8T346G9.Office/FontCache/4/"
    "CloudFonts/Sakkal Majalla/33893302280.ttf"
)
SAKKAL_BOLD = Path(
    "/Users/majd/Library/Group Containers/UBF8T346G9.Office/FontCache/4/"
    "CloudFonts/Sakkal Majalla/34866040251.ttf"
)
STAMP = Path("الأختام/photo_1448-03-06 21.11.32.jpeg")


@dataclass(frozen=True)
class CoverEdit:
    code: str
    source: Path
    source_title: str
    target_title: str
    mask: tuple[float, float, float, float]
    text_box: tuple[float, float, float, float]
    font: Path
    font_size: float
    color: str


COVER_EDITS = (
    CoverEdit(
        "20012106-2",
        Path("assets/course-specifications/islamic-studies-bundle-1444/20012106-2.pdf"),
        "أصول الفقه (1)",
        "أصول فقه (1)",
        (360.0, 409.0, 448.7, 430.2),
        (360.0, 407.8, 448.2, 431.0),
        SAKKAL_REGULAR,
        14.0,
        "#5279ba",
    ),
    CoverEdit(
        "20014101-2",
        Path("assets/course-specifications/islamic-studies-bundle-1444/20014101-2.pdf"),
        "أصول الفقه (3)",
        "أصول فقه (3)",
        (360.0, 409.0, 448.7, 430.2),
        (360.0, 407.8, 448.2, 431.0),
        SAKKAL_REGULAR,
        14.0,
        "#5279ba",
    ),
    CoverEdit(
        "20044202-2",
        Path("assets/course-specifications/islamic-studies-bundle-1444/20044202-2.pdf"),
        "بحث تخرج",
        "بحث التخرج",
        (360.0, 409.0, 448.7, 430.2),
        (360.0, 407.8, 448.2, 431.0),
        SAKKAL_REGULAR,
        14.0,
        "#5279ba",
    ),
    CoverEdit(
        "2002313-2",
        Path("assets/course-specifications/quran-old-v39/2002313-2.pdf"),
        "علوم القرآن (5)",
        "علوم قرآن (5)",
        (329.0, 154.0, 435.0, 180.0),
        (329.0, 151.5, 434.0, 181.5),
        SAKKAL_BOLD,
        18.0,
        "#000000",
    ),
    CoverEdit(
        "2003442-3",
        Path("assets/course-specifications/systems-source-2022/2003442-3.pdf"),
        "القانون الدولي الخاص",
        "النظام الدولي الخاص",
        (284.0, 332.5, 408.8, 352.4),
        (284.0, 331.0, 408.0, 353.5),
        ARIAL,
        14.0,
        "#000000",
    ),
)


EXACT_SLICES = (
    {
        "code": "20012102-2",
        "title": "الفقه (2)",
        "pages": "110-119",
        "page_count": 10,
        "approval_page": 10,
    },
    {
        "code": "20023205-2",
        "title": "التفسير التحليلي (3)",
        "pages": "332-338",
        "page_count": 7,
        "approval_page": 7,
    },
)


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def actual_text_hex(text: str) -> str:
    return "FEFF" + text.encode("utf-16-be").hex().upper()


def add_accessible_identity(path: Path, title: str, code: str, working: Path) -> None:
    """Add invisible Unicode /ActualText for reliable title/code extraction."""
    reader = PdfReader(str(path), strict=False)
    writer = PdfWriter(clone_from=reader)
    writer.add_outline_item(title, 0)
    page = writer.pages[0]
    resources = page.get("/Resources") or DictionaryObject()
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    fonts = resources.get("/Font") or DictionaryObject()
    if hasattr(fonts, "get_object"):
        fonts = fonts.get_object()
    fonts[NameObject("/FActual")] = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    stream = DecodedStreamObject()
    stream.set_data(
        (
            f"/Span << /ActualText <{actual_text_hex(title)}> >> BDC\n"
            "BT /FActual 1 Tf 3 Tr 36 20 Td (x) Tj ET\nEMC\n"
            f"/Span << /ActualText <{actual_text_hex(code)}> >> BDC\n"
            "BT /FActual 1 Tf 3 Tr 36 18 Td (x) Tj ET\nEMC\n"
        ).encode("ascii")
    )
    stream_reference = writer._add_object(stream)
    contents = page.get("/Contents")
    resolved_contents = (
        contents.get_object() if hasattr(contents, "get_object") else contents
    )
    if contents is None:
        page[NameObject("/Contents")] = stream_reference
    elif isinstance(resolved_contents, ArrayObject):
        page[NameObject("/Contents")] = ArrayObject(
            [*resolved_contents, stream_reference]
        )
    else:
        page[NameObject("/Contents")] = ArrayObject([contents, stream_reference])

    intermediate = working / f"{code}-accessible.pdf"
    optimized = working / f"{code}-accessible-optimized.pdf"
    writer.write(str(intermediate))
    run(
        [
            "qpdf",
            "--object-streams=generate",
            "--stream-data=compress",
            "--compression-level=9",
            str(intermediate),
            str(optimized),
        ]
    )
    shutil.copy2(optimized, path)


def adapt_legacy_quran_cover(
    edit: CoverEdit, output: Path, working: Path
) -> dict[str, object]:
    """Cover the legacy raster title cell and merge the catalogue title."""
    reader = PdfReader(str(edit.source), strict=False)
    first_page = reader.pages[0]
    page_width = float(first_page.mediabox.width)
    page_height = float(first_page.mediabox.height)
    overlay_path = working / f"{edit.code}-title-overlay.pdf"

    font_name = "SakkalMajallaBoldRecovery"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(edit.font)))
    overlay = canvas.Canvas(
        str(overlay_path), pagesize=(page_width, page_height), pageCompression=1
    )
    x0, top, x1, bottom = edit.mask
    overlay.setFillColorRGB(*BACKGROUND)
    overlay.rect(
        x0,
        page_height - bottom,
        x1 - x0,
        bottom - top,
        stroke=0,
        fill=1,
    )
    overlay.setFillColorRGB(0, 0, 0)
    overlay.setFont(font_name, edit.font_size)
    overlay.drawRightString(
        edit.text_box[2],
        page_height - 174.0,
        get_display(arabic_reshaper.reshape(edit.target_title)),
    )
    overlay.showPage()
    overlay.save()

    overlay_reader = PdfReader(str(overlay_path), strict=False)
    writer = PdfWriter(clone_from=reader)
    writer.pages[0].merge_page(overlay_reader.pages[0], over=True, expand=False)
    intermediate = working / f"{edit.code}-edited.pdf"
    writer.write(str(intermediate))
    run(
        [
            "qpdf",
            "--object-streams=generate",
            "--stream-data=compress",
            "--compression-level=9",
            str(intermediate),
            str(output),
        ]
    )
    add_accessible_identity(output, edit.target_title, edit.code, working)
    run(["qpdf", "--check", str(output)], capture=True)
    return {
        "code": edit.code,
        "title": edit.target_title,
        "source": edit.source.as_posix(),
        "source_sha256": sha256(edit.source),
        "adaptation": "legacy_cover_title_overlay",
        "source_title": edit.source_title,
        "mask_top_points": list(edit.mask),
        "text_box_top_points": list(edit.text_box),
        "font": str(edit.font),
        "font_sha256": sha256(edit.font),
        "outline_titles_updated": 0,
        "accessible_identity_actual_text": True,
        "page_count": len(reader.pages),
        "output_sha256": sha256(output),
        "approval_and_stamp": "preserved from source",
    }


def adapt_cover(edit: CoverEdit, output: Path, working: Path) -> dict[str, object]:
    if edit.code == "2002313-2":
        return adapt_legacy_quran_cover(edit, output, working)

    first_page_source = working / f"{edit.code}-page1-source.pdf"
    run(
        [
            "qpdf",
            "--empty",
            "--pages",
            str(edit.source),
            "1",
            "--",
            str(first_page_source),
        ]
    )
    document = fitz.open(first_page_source)
    page = document[0]
    mask = fitz.Rect(*edit.mask)
    page.add_redact_annot(mask, fill=BACKGROUND, cross_out=False)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )

    css = f"""
        @font-face {{ font-family: SiteArabic; src: url('{edit.font.name}'); }}
        html, body {{ margin: 0; padding: 0; }}
        div {{
            margin: 0; padding: 0;
            font-family: SiteArabic;
            font-size: {edit.font_size}pt;
            color: {edit.color};
            direction: rtl;
            text-align: right;
            line-height: 1.12;
        }}
    """
    archive = fitz.Archive(str(edit.font.parent))
    spare_height, scale = page.insert_htmlbox(
        fitz.Rect(*edit.text_box),
        f'<div dir="rtl">{html.escape(edit.target_title)}</div>',
        css=css,
        archive=archive,
        scale_low=0.85,
        overlay=True,
    )
    if spare_height < 0:
        document.close()
        raise RuntimeError(f"Replacement title did not fit: {edit.code}")

    intermediate = working / f"{edit.code}-edited.pdf"
    document.save(intermediate, garbage=4, deflate=True, clean=True)
    document.close()
    assembled = working / f"{edit.code}-assembled.pdf"
    run(
        [
            "qpdf",
            "--empty",
            "--pages",
            str(intermediate),
            "1",
            str(edit.source),
            "2-z",
            "--",
            str(assembled),
        ]
    )
    run(
        [
            "qpdf",
            "--object-streams=generate",
            "--stream-data=compress",
            "--compression-level=9",
            str(assembled),
            str(output),
        ]
    )
    run(["qpdf", "--check", str(output)], capture=True)
    add_accessible_identity(output, edit.target_title, edit.code, working)
    run(["qpdf", "--check", str(output)], capture=True)
    return {
        "code": edit.code,
        "title": edit.target_title,
        "source": edit.source.as_posix(),
        "source_sha256": sha256(edit.source),
        "adaptation": "cover_title_only",
        "source_title": edit.source_title,
        "mask_top_points": list(edit.mask),
        "text_box_top_points": list(edit.text_box),
        "font": str(edit.font),
        "font_sha256": sha256(edit.font),
        "htmlbox_scale": scale,
        "outline_titles_updated": 1,
        "accessible_identity_actual_text": True,
        "page_count": len(fitz.open(output)),
        "output_sha256": sha256(output),
        "approval_and_stamp": "preserved from source",
    }


def build_exact_slices(root: Path, working: Path) -> tuple[Path, list[dict[str, object]]]:
    source = root / "توصيفات برنامج الدراسات الإسلامية.pdf"
    baseline = working / "exact-baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for item in EXACT_SLICES:
        output = baseline / f"{item['code']}.pdf"
        run(
            [
                "qpdf",
                "--empty",
                "--pages",
                str(source),
                str(item["pages"]),
                "--",
                str(output),
            ]
        )
        run(["qpdf", "--check", str(output)], capture=True)
        add_accessible_identity(output, str(item["title"]), str(item["code"]), working)
        records.append(
            {
                "relative_path": output.name,
                "absolute_path": str(output.resolve()),
                "stamp_status": "missing_stamp",
                "department_key": "islamic_culture",
                "expected_stamp_asset": str((root / STAMP).resolve()),
                "stamp_target_page_1_based": item["approval_page"],
                "approval_location": "final_complete",
                "baseline_sha256": sha256(output),
                "page_count": item["page_count"],
            }
        )
    inventory = working / "exact-stamp-inventory.json"
    inventory.write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return inventory, records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/course-specifications/specialty-recovery-20260826"),
    )
    parser.add_argument("--working", type=Path, default=Path("tmp/pdfs/specialty-recovery"))
    args = parser.parse_args()

    root = args.root.resolve()
    output = (root / args.output).resolve()
    working = (root / args.working).resolve()
    output.mkdir(parents=True, exist_ok=True)
    working.mkdir(parents=True, exist_ok=True)

    inventory, stamp_records = build_exact_slices(root, working)
    stamped = working / "exact-stamped"
    stamp_audit = output / "stamp-audit.json"
    run(
        [
            sys.executable,
            str(root / "scripts/apply_department_stamps.py"),
            "--inventory",
            str(inventory),
            "--source-root",
            str(working / "exact-baseline"),
            "--output-root",
            str(stamped),
            "--audit-output",
            str(stamp_audit),
        ]
    )

    manifest_records: list[dict[str, object]] = []
    source_combined = root / "توصيفات برنامج الدراسات الإسلامية.pdf"
    stamp_audit_data = json.loads(stamp_audit.read_text(encoding="utf-8"))
    stamp_by_code = {
        Path(record["relative_path"]).stem: record
        for record in stamp_audit_data["records"]
    }
    for item, baseline_record in zip(EXACT_SLICES, stamp_records):
        code = str(item["code"])
        source_pdf = stamped / f"{code}.pdf"
        target_pdf = output / f"{code}.pdf"
        shutil.copy2(source_pdf, target_pdf)
        manifest_records.append(
            {
                "code": code,
                "title": item["title"],
                "source": source_combined.name,
                "source_sha256": sha256(source_combined),
                "source_pages_inclusive": item["pages"],
                "adaptation": "exact_slice_plus_department_stamp",
                "baseline_sha256": baseline_record["baseline_sha256"],
                "page_count": item["page_count"],
                "department_stamp": stamp_by_code[code],
                "output_sha256": sha256(target_pdf),
            }
        )

    for edit in COVER_EDITS:
        target_pdf = output / f"{edit.code}.pdf"
        manifest_records.append(adapt_cover(edit, target_pdf, working))

    manifest = {
        "schema": "specialty-recovery-bundle-v1",
        "policy": (
            "Original PDFs are preserved. Exact specifications are sliced from the combined "
            "source and stamped; title adaptations remove only the old cover title and insert "
            "the catalogue title while preserving all other pages, approvals, and stamps."
        ),
        "records": manifest_records,
        "counts": {
            "total": len(manifest_records),
            "exact_slices_stamped": len(EXACT_SLICES),
            "cover_titles_adapted": len(COVER_EDITS),
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    run(
        [
            sys.executable,
            str(root / "scripts/sanitize_audit_paths.py"),
            str(output),
        ]
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
