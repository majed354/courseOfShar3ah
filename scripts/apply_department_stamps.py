#!/usr/bin/env python3
"""Apply department stamps to audited course-specification PDFs.

The script never edits source PDFs in place. It writes a parallel output tree,
merges a one-image overlay into the target page, and refuses any
placement that intersects detected page ink within the configured safety
margin. Crowded approval pages receive a separate final stamp page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


STAMP_SIZE_PT = {
    "qiraat": (170.0, 62.4),
    "sharia": (180.0, 77.1),
    "law": (180.0, 77.1),
    "islamic_culture": (180.0, 70.7),
}

SAFETY_MARGIN_PT = 12.0
AFTER_TABLE_GAP_PT = 16.0
RENDER_DPI = 150
MAX_RASTER_STAMP_WIDTH_PX = 900

# These pages were independently reviewed at 300 dpi. A full-size stamp plus
# the 12 pt safety margin does not fit beside/below the approval table.
FORCE_APPEND_PAGE = {
    "islamic-studies-bundle-1444/20011104-2.pdf",
    "islamic-studies-bundle-1444/20013108-2.pdf",
    "islamic-studies-bundle-1444/20014105-2.pdf",
    "islamic-studies-bundle-1444/20014206-2.pdf",
    "islamic-studies-bundle-1444/20021201-2.pdf",
    "islamic-studies-bundle-1444/20022103-2.pdf",
    "islamic-studies-bundle-1444/20022104-2.pdf",
    "islamic-studies-bundle-1444/20022203-2.pdf",
    "islamic-studies-bundle-1444/20023103-2.pdf",
    "islamic-studies-bundle-1444/20024103-2.pdf",
    "islamic-studies-bundle-1444/20043206-2.pdf",
    "islamic-studies-bundle-1444/20044107-2.pdf",
    "sharia-ba-1445/2001127-2.pdf",
    "sharia-ba-1445/2001225-2.pdf",
    "usul-master-1446/2001700-2.pdf",
    "usul-master-1446/2001701-3.pdf",
    "usul-master-1446/2001704-2.pdf",
    "usul-master-1446/2001707-2.pdf",
    "quran-old-v39/2002125-2.pdf",
    "quran-old-v39/2002131-2.pdf",
    "quran-old-v39/2002204-2.pdf",
    "quran-old-v39/2002208-2.pdf",
    "quran-old-v39/2002314-2.pdf",
    "quranic-studies-master-1447/pending-code-tafsir-tahlili-2.pdf",
    "systems-source-2022/2003112-2.pdf",
    "systems-source-2022/20033201-3.pdf",
    "systems-source-2022/2003381-3.pdf",
    "systems-source-2022/20034101-3.pdf",
    "systems-source-2022/20034108-2.pdf",
    "systems-source-2022/2003442-3.pdf",
}


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_geometry(path: Path, page_index: int) -> tuple[float, float, int]:
    reader = PdfReader(str(path), strict=False)
    page = reader.pages[page_index]
    box = page.mediabox
    width = float(box.width)
    height = float(box.height)
    rotation = int(page.get("/Rotate", 0) or 0) % 360
    if rotation != 0:
        raise RuntimeError(f"Unsupported rotated target page ({rotation}): {path}")
    return width, height, len(reader.pages)


def render_page(path: Path, page_number: int, directory: Path) -> Image.Image:
    prefix = directory / "target"
    run(
        [
            "pdftoppm",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            "-r",
            str(RENDER_DPI),
            "-png",
            "-singlefile",
            str(path),
            str(prefix),
        ]
    )
    return Image.open(prefix.with_suffix(".png")).convert("RGB")


def quantized_background(rgb: np.ndarray) -> np.ndarray:
    sample = rgb[::8, ::8].reshape(-1, 3)
    quantized = (sample // 8).astype(np.int16)
    packed = quantized[:, 0] * 1024 + quantized[:, 1] * 32 + quantized[:, 2]
    mode = int(np.bincount(packed).argmax())
    return np.array(
        [((mode // 1024) % 32) * 8 + 4, ((mode // 32) % 32) * 8 + 4, (mode % 32) * 8 + 4],
        dtype=np.float32,
    )


def ink_mask(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image, dtype=np.float32)
    background = quantized_background(rgb)
    distance = np.sqrt(np.square(rgb - background).sum(axis=2))
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    luminance = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    return ((distance > 28.0) | (saturation > 35.0)) & (luminance < 248.0)


def bbox_pixels(
    bbox_top_pt: tuple[float, float, float, float],
    page_width_pt: float,
    page_height_pt: float,
    image: Image.Image,
    margin_pt: float = 0.0,
) -> tuple[int, int, int, int]:
    x, top, width, height = bbox_top_pt
    sx = image.width / page_width_pt
    sy = image.height / page_height_pt
    left = max(0, math.floor((x - margin_pt) * sx))
    upper = max(0, math.floor((top - margin_pt) * sy))
    right = min(image.width, math.ceil((x + width + margin_pt) * sx))
    lower = min(image.height, math.ceil((top + height + margin_pt) * sy))
    return left, upper, right, lower


def collision_stats(
    image: Image.Image,
    bbox_top_pt: tuple[float, float, float, float],
    page_width_pt: float,
    page_height_pt: float,
) -> dict[str, float | int]:
    mask = ink_mask(image)
    left, upper, right, lower = bbox_pixels(
        bbox_top_pt,
        page_width_pt,
        page_height_pt,
        image,
        SAFETY_MARGIN_PT,
    )
    region = mask[upper:lower, left:right]
    pixels = int(region.sum())
    area = int(region.size)
    return {
        "ink_pixels_with_margin": pixels,
        "checked_pixels_with_margin": area,
        "ink_fraction_with_margin": pixels / area if area else 1.0,
    }


def last_table_bottom(path: Path, page_index: int) -> float | None:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        tables = pdf.pages[page_index].find_tables()
        return float(tables[-1].bbox[3]) if tables else None


def create_stamp_page(
    output: Path,
    stamp: Path,
    page_width: float,
    page_height: float,
    bbox_top_pt: tuple[float, float, float, float],
) -> None:
    x, top, width, height = bbox_top_pt
    pdf = canvas.Canvas(str(output), pagesize=(page_width, page_height), pageCompression=1)
    pdf.drawImage(
        str(stamp),
        x,
        page_height - top - height,
        width=width,
        height=height,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )
    pdf.showPage()
    pdf.save()


def publication_stamp(stamp: Path, directory: Path) -> Path:
    """Downsample oversized lossless stamp art to a print-safe 360 dpi copy.

    The 180 pt-wide Law stamp needs only 750 pixels for 300 dpi output. Keeping
    a 900-pixel publication copy preserves extra print headroom while avoiding
    embedding the 1916-pixel source PNG in every PDF. JPEG source stamps are
    already compact and are embedded unchanged.
    """

    if stamp.suffix.lower() != ".png":
        return stamp
    with Image.open(stamp) as source_image:
        if source_image.width <= MAX_RASTER_STAMP_WIDTH_PX:
            return stamp
        ratio = MAX_RASTER_STAMP_WIDTH_PX / source_image.width
        size = (
            MAX_RASTER_STAMP_WIDTH_PX,
            max(1, round(source_image.height * ratio)),
        )
        prepared = directory / "publication-stamp.png"
        source_image.convert("RGB").resize(size, Image.Resampling.LANCZOS).save(
            prepared,
            format="PNG",
            optimize=True,
            compress_level=9,
        )
        return prepared


def overlay_page(source: Path, overlay: Path, target_page: int, output: Path) -> None:
    # qpdf's page-as-Form overlay changes transparency blending in some Word
    # exports. Merging the tiny overlay content directly preserves their page
    # transparency group and therefore gives a pixel-identical render outside
    # the stamp rectangle.
    source_reader = PdfReader(str(source), strict=False)
    overlay_reader = PdfReader(str(overlay), strict=False)
    writer = PdfWriter()
    writer.clone_document_from_reader(source_reader)
    writer.pages[target_page - 1].merge_page(
        overlay_reader.pages[0], over=True, expand=False
    )
    with output.open("wb") as stream:
        writer.write(stream)


def append_page(source: Path, stamp_page: Path, output: Path) -> None:
    # Starting from an empty qpdf and reassembling pages discards document-level
    # structures such as bookmarks/outlines. Clone the complete source document
    # first, then append only the new page so metadata, outlines, destinations,
    # attachments, and the original page objects remain intact.
    source_reader = PdfReader(str(source), strict=False)
    stamp_reader = PdfReader(str(stamp_page), strict=False)
    writer = PdfWriter()
    writer.clone_document_from_reader(source_reader)
    writer.add_page(stamp_reader.pages[0])
    with output.open("wb") as stream:
        writer.write(stream)


def optimize_pdf(source: Path, output: Path) -> None:
    """Generate compressed object streams without changing rendered content."""

    run(
        [
            "qpdf",
            "--object-streams=generate",
            "--stream-data=compress",
            "--compression-level=9",
            str(source),
            str(output),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Optional pristine PDF root; relative paths from the inventory are resolved here",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    args.output_root.mkdir(parents=True, exist_ok=True)
    audit_records: list[dict[str, object]] = []

    for index, record in enumerate(inventory["records"], start=1):
        relative = Path(record["relative_path"])
        source = (
            args.source_root / relative
            if args.source_root is not None
            else Path(record["absolute_path"])
        )
        output = args.output_root / relative
        output.parent.mkdir(parents=True, exist_ok=True)

        if record["stamp_status"] == "already_correct_stamp":
            audit_records.append(
                {
                    "relative_path": relative.as_posix(),
                    "department_key": record["department_key"],
                    "status": "preserved_existing_correct_stamp",
                    "baseline_sha256": record["baseline_sha256"],
                    "output_sha256": record["baseline_sha256"],
                    "page_count_before": record["page_count"],
                    "page_count_after": record["page_count"],
                }
            )
            continue

        department = record["department_key"]
        stamp = Path(record["expected_stamp_asset"])
        stamp_width, stamp_height = STAMP_SIZE_PT[department]
        target_page = int(record["stamp_target_page_1_based"])
        append = relative.as_posix() in FORCE_APPEND_PAGE

        # Five source files have a blank trailing template page. Put the stamp
        # there instead of touching the crowded approval table on the prior page.
        if record["approval_location"] == "penultimate_complete_final_blank":
            target_page = int(record["page_count"])

        page_width, page_height, page_count = page_geometry(source, target_page - 1)
        x = (page_width - stamp_width) / 2.0

        with tempfile.TemporaryDirectory(prefix="department-stamp-") as temporary:
            temp = Path(temporary)
            rendered = render_page(source, target_page, temp)

            if append:
                stamp_top = 96.0
                placement = "appended_final_stamp_page"
                collision = {
                    "ink_pixels_with_margin": 0,
                    "checked_pixels_with_margin": 0,
                    "ink_fraction_with_margin": 0.0,
                }
            elif record["approval_location"] == "penultimate_complete_final_blank":
                stamp_top = 132.0
                placement = "existing_blank_final_page"
                collision = collision_stats(
                    rendered,
                    (x, stamp_top, stamp_width, stamp_height),
                    page_width,
                    page_height,
                )
            else:
                table_bottom = last_table_bottom(source, target_page - 1)
                if table_bottom is None:
                    raise RuntimeError(f"Approval table not detected: {relative}")
                stamp_top = table_bottom + AFTER_TABLE_GAP_PT
                placement = "below_approval_table"
                if stamp_top + stamp_height + SAFETY_MARGIN_PT > page_height:
                    raise RuntimeError(f"Stamp exceeds page boundary: {relative}")
                collision = collision_stats(
                    rendered,
                    (x, stamp_top, stamp_width, stamp_height),
                    page_width,
                    page_height,
                )

            if collision["ink_pixels_with_margin"] != 0:
                raise RuntimeError(
                    f"Ink collision ({collision['ink_pixels_with_margin']} px): {relative}"
                )

            overlay = temp / "stamp.pdf"
            prepared_stamp = publication_stamp(stamp, temp)
            create_stamp_page(
                overlay,
                prepared_stamp,
                page_width,
                page_height,
                (x, stamp_top, stamp_width, stamp_height),
            )
            unoptimized_output = temp / "unoptimized.pdf"
            if append:
                append_page(source, overlay, unoptimized_output)
            else:
                overlay_page(source, overlay, target_page, unoptimized_output)
            temporary_output = temp / "output.pdf"
            optimize_pdf(unoptimized_output, temporary_output)
            run(["qpdf", "--check", str(temporary_output)], capture=True)
            shutil.copy2(temporary_output, output)

        _, _, output_page_count = page_geometry(output, 0)
        audit_records.append(
            {
                "relative_path": relative.as_posix(),
                "department_key": department,
                "stamp_asset": str(stamp),
                "stamp_asset_sha256": sha256(stamp),
                "status": "stamp_added",
                "placement": placement,
                "target_page_1_based": output_page_count if append else target_page,
                "bbox_top_points": [
                    round(x, 3),
                    round(stamp_top, 3),
                    stamp_width,
                    stamp_height,
                ],
                "safety_margin_points": SAFETY_MARGIN_PT,
                **collision,
                "baseline_sha256": record["baseline_sha256"],
                "output_sha256": sha256(output),
                "page_count_before": page_count,
                "page_count_after": output_page_count,
            }
        )
        print(f"[{index:03d}/{len(inventory['records'])}] {relative}")

    result = {
        "schema": "department-stamp-application-audit-v1",
        "source_inventory": str(args.inventory),
        "policy": {
            "qiraat": "Qiraat and Quranic studies at all degrees",
            "sharia": "Sharia, Fiqh, and Usul al-Fiqh",
            "law": "Regulations and Law",
            "islamic_culture": "Islamic Studies and Creed",
        },
        "stamp_size_points": STAMP_SIZE_PT,
        "safety_margin_points": SAFETY_MARGIN_PT,
        "records": audit_records,
        "counts": {
            "total": len(audit_records),
            "preserved_existing": sum(
                item["status"] == "preserved_existing_correct_stamp" for item in audit_records
            ),
            "stamped": sum(item["status"] == "stamp_added" for item in audit_records),
            "appended_pages": sum(
                item.get("placement") == "appended_final_stamp_page" for item in audit_records
            ),
        },
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
