#!/usr/bin/env python3
"""Apply the approved Quranic Studies master's corrections reproducibly."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf

from build_raw_recovery_bundle import insert_arabic_html


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_RELATIVE = Path("assets/course-specifications/quranic-studies-master-1447")
USUL_FILENAME = "2002851-4.pdf"
USUL_ORIGINAL_SHA256 = "2c0ee393a9528f29578e8021a856fef6ca28f8aac9bb1bf798174f58e74c58f9"
CORRECTION_DATE = "2026-08-29"
LIGHT_CELL_FILL = (0.9489128, 0.9490349, 0.9488823)
GRAY_CELL_FILL = (0.8509194, 0.8510414, 0.8508888)
PAGE4_TOTAL_FILL = (0.321991, 0.709991, 0.760986)
PAGE5_TOTAL_FILL = (0.294, 0.725, 0.784)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def exact_background(
    page: pymupdf.Page, rect: pymupdf.Rect
) -> tuple[float, float, float]:
    """Return the dominant source RGB without quantizing flat table fills."""
    pixmap = page.get_pixmap(clip=rect, colorspace=pymupdf.csRGB, alpha=False)
    pixels = zip(pixmap.samples[0::3], pixmap.samples[1::3], pixmap.samples[2::3])
    red, green, blue = Counter(pixels).most_common(1)[0][0]
    return (red / 255, green / 255, blue / 255)


def replace_region(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    value: str,
    *,
    font_size: float,
    color: str = "#000000",
    align: str = "center",
    background_rect: pymupdf.Rect | None = None,
    background_color: tuple[float, float, float] | None = None,
    text_rect: pymupdf.Rect | None = None,
    vertical_padding: float = 0.0,
) -> dict[str, Any]:
    background = background_color or exact_background(page, background_rect or rect)
    page.add_redact_annot(rect, fill=background, cross_out=False)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )
    insertion_rect = pymupdf.Rect(text_rect or rect)
    insertion_rect.y0 += vertical_padding
    scale = insert_arabic_html(
        page,
        insertion_rect,
        value,
        align=align,
        font_size=font_size,
        color=color,
    )
    result = {
        "value": value,
        "rect_top_points": [round(number, 3) for number in rect],
        "htmlbox_scale": scale,
    }
    if text_rect is not None or vertical_padding:
        result["text_rect_top_points"] = [
            round(number, 3) for number in insertion_rect
        ]
    return result


def replace_usul_hours(source: Path, output: Path, working: Path) -> list[dict[str, Any]]:
    document = pymupdf.open(source)
    if len(document) != 7:
        raise RuntimeError(f"Unexpected page count for {source}: {len(document)}")

    edits: list[dict[str, Any]] = []
    page3 = document[2]
    page3_edits = [
        (
            "credit_hours",
            "ساعتان في الأسبوع",
            "(أربع ساعات في الأسبوع)",
            pymupdf.Rect(357.0, 159.0, 450.0, 181.5),
            None,
            10.8,
            "#ffffff",
            None,
            (0.298, 0.239, 0.557),
        ),
        (
            "ordinary_instruction_hours",
            "30 ساعة",
            "60 ساعة",
            pymupdf.Rect(236.5, 664.4, 270.9, 682.2),
            pymupdf.Rect(147.2, 660.7, 330.0, 683.4),
            10.2,
            "#000000",
            pymupdf.Rect(154.0, 668.0, 158.0, 672.0),
            LIGHT_CELL_FILL,
        ),
        (
            "ordinary_instruction_percentage",
            "88%",
            "93.75%",
            pymupdf.Rect(111.5, 664.4, 133.9, 682.2),
            pymupdf.Rect(59.3, 660.7, 145.7, 683.4),
            9.7,
            "#000000",
            pymupdf.Rect(66.0, 668.0, 70.0, 672.0),
            LIGHT_CELL_FILL,
        ),
        (
            "electronic_instruction_percentage",
            "12%",
            "6.25%",
            pymupdf.Rect(111.5, 686.7, 133.9, 704.5),
            pymupdf.Rect(59.3, 683.9, 145.7, 706.0),
            9.7,
            "#000000",
            pymupdf.Rect(66.0, 692.0, 70.0, 696.0),
            GRAY_CELL_FILL,
        ),
    ]
    for (
        field,
        old,
        new,
        rect,
        text_rect,
        font_size,
        color,
        background_rect,
        background_color,
    ) in page3_edits:
        edit = replace_region(
            page3,
            rect,
            new,
            font_size=font_size,
            color=color,
            background_rect=background_rect,
            background_color=background_color,
            text_rect=text_rect,
            vertical_padding=2.5 if field == "credit_hours" else 3.0,
        )
        edit.update(
            {
                "kind": "replace_course_hour_value",
                "page_1_based": 3,
                "field": field,
                "from": old,
                "to": new,
            }
        )
        edits.append(edit)

    page4 = document[3]
    page4_edits = [
        (
            "lecture_hours",
            "30 ساعة",
            "60 ساعة",
            pymupdf.Rect(183.8, 226.3, 218.2, 244.1),
            pymupdf.Rect(147.2, 223.8, 260.0, 246.0),
            10.2,
            "#000000",
            pymupdf.Rect(153.0, 233.0, 157.0, 237.0),
            LIGHT_CELL_FILL,
        ),
        (
            "lecture_percentage",
            "88%",
            "93.75%",
            pymupdf.Rect(94.0, 226.3, 116.3, 244.1),
            pymupdf.Rect(59.3, 223.8, 145.7, 246.0),
            9.7,
            "#000000",
            pymupdf.Rect(66.0, 233.0, 70.0, 237.0),
            LIGHT_CELL_FILL,
        ),
        (
            "additional_lesson_percentage",
            "12%",
            "6.25%",
            pymupdf.Rect(94.0, 288.5, 116.3, 306.3),
            pymupdf.Rect(59.3, 286.1, 145.7, 308.2),
            9.7,
            "#000000",
            pymupdf.Rect(66.0, 295.0, 70.0, 299.0),
            GRAY_CELL_FILL,
        ),
        (
            "total_learning_hours",
            "34 ساعة",
            "64 ساعة",
            pymupdf.Rect(184.9, 332.0, 216.8, 348.8),
            pymupdf.Rect(147.2, 329.5, 260.0, 351.5),
            10.2,
            "#ffffff",
            pymupdf.Rect(153.0, 338.0, 157.0, 342.0),
            PAGE4_TOTAL_FILL,
        ),
    ]
    for (
        field,
        old,
        new,
        rect,
        text_rect,
        font_size,
        color,
        background_rect,
        background_color,
    ) in page4_edits:
        edit = replace_region(
            page4,
            rect,
            new,
            font_size=font_size,
            color=color,
            background_rect=background_rect,
            background_color=background_color,
            text_rect=text_rect,
            vertical_padding=3.0,
        )
        edit.update(
            {
                "kind": "replace_course_hour_value",
                "page_1_based": 4,
                "field": field,
                "from": old,
                "to": new,
            }
        )
        edits.append(edit)

    page5 = document[4]
    topic_words = [
        word
        for word in page5.get_text("words", sort=True)
        if str(word[4]) == "ساعتان" and 300.0 < float(word[1]) < 725.0
    ]
    if len(topic_words) != 15:
        raise RuntimeError(f"Expected 15 two-hour topic rows, found {len(topic_words)}")
    topic_cells_by_rect: dict[
        tuple[float, float, float, float],
        tuple[pymupdf.Rect, tuple[float, float, float]],
    ] = {}
    for drawing in page5.get_drawings():
        cell = drawing["rect"]
        fill = drawing.get("fill")
        if (
            fill is not None
            and abs(cell.x0 - 57.624) < 0.1
            and abs(cell.x1 - 146.232) < 0.1
            and 319.0 < cell.y0 < 728.0
            and 25.0 < cell.height < 27.0
        ):
            key = tuple(round(number, 3) for number in cell)
            topic_cells_by_rect[key] = (pymupdf.Rect(cell), tuple(fill))
    topic_cells = [
        topic_cells_by_rect[key]
        for key in sorted(topic_cells_by_rect, key=lambda item: item[1])
    ]
    if len(topic_cells) != 15:
        raise RuntimeError(f"Expected 15 topic-hour cells, found {len(topic_cells)}")
    topic_rects: list[list[float]] = []
    for word, (cell, fill) in zip(topic_words, topic_cells):
        rect = pymupdf.Rect(
            87.4,
            cell.y0 + 0.5,
            117.0,
            cell.y1 - 0.5,
        )
        text_rect = pymupdf.Rect(
            cell.x0 + 1.0,
            cell.y0,
            cell.x1 - 1.0,
            cell.y1,
        )
        topic_edit = replace_region(
            page5,
            rect,
            "أربع ساعات",
            font_size=9.3,
            background_color=fill,
            text_rect=text_rect,
            vertical_padding=8.5,
        )
        topic_rects.append(topic_edit["rect_top_points"])
    edits.append(
        {
            "kind": "replace_topic_hours",
            "page_1_based": 5,
            "rows": list(range(1, 16)),
            "from": "ساعتان",
            "to": "أربع ساعات",
            "rects_top_points": topic_rects,
        }
    )
    total_edit = replace_region(
        page5,
        pymupdf.Rect(79.5, 729.1, 124.5, 760.3),
        "60 ساعة",
        font_size=10.7,
        color="#ffffff",
        background_color=PAGE5_TOTAL_FILL,
        text_rect=pymupdf.Rect(58.6, 728.616, 142.2, 760.776),
        vertical_padding=10.9,
    )
    total_edit.update(
        {
            "kind": "replace_course_hour_value",
            "page_1_based": 5,
            "field": "topic_hours_total",
            "from": 30,
            "to": 60,
        }
    )
    edits.append(total_edit)

    temporary = working / f"{output.stem}-corrected.pdf"
    document.save(
        temporary,
        garbage=4,
        deflate=True,
        clean=True,
        no_new_id=True,
    )
    document.close()
    shutil.copy2(temporary, output)
    run(["qpdf", "--check", str(output)])
    return edits


def update_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_manifest(bundle: Path, new_hash: str, edits: list[dict[str, Any]]) -> None:
    path = bundle / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    record = next(item for item in data["records"] if item["published_file"] == USUL_FILENAME)
    record["credit_hours_in_published_pdf"] = 4
    record["published_sha256"] = new_hash
    record["match_status"] = "verified"
    record["hours_conflict"] = None
    record["approved_corrections"] = {
        "corrected_on": CORRECTION_DATE,
        "basis": "published university plan and approved user decision",
        "source_credit_hours_preserved_in_provenance": record["credit_hours_in_source"],
        "published_credit_hours": 4,
        "teaching_model": {
            "topic_rows": 15,
            "hours_per_topic": 4,
            "lecture_hours": 60,
            "additional_hours": 4,
            "total_learning_hours": 64,
        },
        "edits": edits,
    }
    data["counts"]["published_pages"] = sum(
        int(item["page_count"]) for item in data["records"]
    )
    data["counts"]["hours_warning_records"] = sum(
        item.get("match_status") == "verified_with_hours_warning"
        for item in data["records"]
    )
    update_json(path, data)


def refresh_hashes(bundle: Path) -> None:
    path = bundle / "hashes.sha256"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        _, filename = line.split(maxsplit=1)
        target = bundle / filename
        if not target.is_file():
            raise RuntimeError(f"Missing hashed bundle artifact: {target}")
        lines.append(f"{sha256(target)}  {filename}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_course_detail(container: dict[str, Any]) -> None:
    variant = container["2002851-4"]["variants"][0]
    variant["match_status"] = "verified"
    variant["match_note"] = "4 ساعات معتمدة."


def update_public_data(root: Path) -> None:
    fragment_path = root / BUNDLE_RELATIVE / "course-details.fragment.json"
    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    update_course_detail(fragment)
    update_json(fragment_path, fragment)

    data_path = root / "data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    update_course_detail(data["course_details"])

    program_hits = 0
    for program in data["programs"]:
        if program.get("name") != "الدراسات القرآنية المعاصرة":
            continue
        for course in program.get("courses", []):
            if course.get("code") == "2002871-2":
                course["level"] = 2
                program_hits += 1
    if program_hits != 1:
        raise RuntimeError(f"Expected one program occurrence for 2002871-2, found {program_hits}")

    catalog_hits = 0
    for course in data["courses_catalog"]:
        if course.get("code") == "2002871-2":
            course["levels_by_program"]["الدراسات القرآنية المعاصرة"] = 2
            catalog_hits += 1
    if catalog_hits != 1:
        raise RuntimeError(f"Expected one catalog entry for 2002871-2, found {catalog_hits}")
    update_json(data_path, data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--working",
        type=Path,
        default=Path("tmp/pdfs/approved-quranic-master-corrections"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    bundle = root / BUNDLE_RELATIVE
    working = (root / args.working).resolve()
    working.mkdir(parents=True, exist_ok=True)

    usul = bundle / USUL_FILENAME
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    record = next(
        item for item in manifest["records"]
        if item["published_file"] == USUL_FILENAME
    )
    current_hash = sha256(usul)
    source = working / "2002851-4-baseline.pdf"
    if source.is_file():
        baseline_hash = sha256(source)
        if baseline_hash != USUL_ORIGINAL_SHA256:
            raise RuntimeError(
                f"Unexpected baseline hash for {source}: {baseline_hash}"
            )
        edits = replace_usul_hours(source, usul, working)
    elif current_hash == USUL_ORIGINAL_SHA256:
        shutil.copy2(usul, source)
        edits = replace_usul_hours(source, usul, working)
    elif (
        record.get("published_sha256") == current_hash
        and record.get("credit_hours_in_published_pdf") == 4
        and record.get("approved_corrections")
    ):
        # A clean checkout contains only the corrected publication, not the
        # ignored working baseline. Keep the verified PDF and refresh its
        # metadata, public data, and checksums idempotently.
        edits = record["approved_corrections"]["edits"]
    else:
        raise RuntimeError(f"Unexpected baseline or corrected hash for {usul}: {current_hash}")

    corrected_hash = sha256(usul)
    update_manifest(bundle, corrected_hash, edits)
    update_public_data(root)
    refresh_hashes(bundle)
    print(
        json.dumps(
            {
                "usul_pdf": str(usul.relative_to(root)),
                "sha256": corrected_hash,
                "topic_rows_corrected": 15,
                "topical_tafsir_level": 2,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
