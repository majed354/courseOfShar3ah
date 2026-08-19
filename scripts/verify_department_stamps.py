#!/usr/bin/env python3
"""Verify stamped PDFs against their audited source versions."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader


RENDER_DPI = 96


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_box(page, name: str) -> tuple[float, float, float, float]:
    box = getattr(page, name)
    return tuple(round(float(value), 4) for value in (box.left, box.bottom, box.right, box.top))


def annotations(page) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for reference in page.get("/Annots", []) or []:
        item = reference.get_object()
        action = item.get("/A")
        result.append(
            {
                "subtype": str(item.get("/Subtype")),
                "rect": [round(float(value), 4) for value in item.get("/Rect", [])],
                "uri": str(action.get("/URI")) if action and action.get("/URI") else None,
            }
        )
    return result


def outline_signature(reader: PdfReader) -> list[object]:
    """Return bookmark titles, nesting, and destinations in a stable form."""

    def convert(items) -> list[object]:
        result: list[object] = []
        for item in items:
            if isinstance(item, list):
                result.append(convert(item))
                continue
            try:
                page_number = reader.get_destination_page_number(item)
            except Exception:
                page_number = None
            title = getattr(item, "title", None)
            if title is None and hasattr(item, "get"):
                title = item.get("/Title")
            result.append({"title": str(title), "page": page_number})
        return result

    return convert(reader.outline)


def document_structure(reader: PdfReader) -> dict[str, object]:
    return {
        "metadata": {str(key): str(value) for key, value in (reader.metadata or {}).items()},
        "catalog_keys": sorted(str(key) for key in reader.trailer["/Root"].keys()),
        "outline": outline_signature(reader),
    }


def extracted_text(path: Path, page_count: int, temporary: Path) -> bytes:
    output = temporary / (path.stem + "-text.txt")
    run(
        [
            "pdftotext",
            "-f",
            "1",
            "-l",
            str(page_count),
            "-layout",
            str(path),
            str(output),
        ]
    )
    return output.read_bytes()


def render_pages(path: Path, page_count: int, directory: Path, prefix: str) -> list[Path]:
    base = directory / prefix
    run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            str(page_count),
            "-r",
            str(RENDER_DPI),
            "-png",
            str(path),
            str(base),
        ]
    )
    return sorted(directory.glob(f"{prefix}-*.png"))


def compare_renders(
    source: Path,
    output: Path,
    page_count: int,
    target_page: int | None,
    bbox_top_points: list[float] | None,
    temporary: Path,
) -> dict[str, object]:
    source_pages = render_pages(source, page_count, temporary, "source")
    output_pages = render_pages(output, page_count, temporary, "output")
    if len(source_pages) != page_count or len(output_pages) != page_count:
        raise RuntimeError("Rendered page count mismatch")

    changed_pages: list[int] = []
    changed_outside_bbox = 0
    changed_inside_bbox = 0
    for page_number, (source_png, output_png) in enumerate(
        zip(source_pages, output_pages, strict=True), start=1
    ):
        before = np.asarray(Image.open(source_png).convert("RGB"), dtype=np.int16)
        after = np.asarray(Image.open(output_png).convert("RGB"), dtype=np.int16)
        if before.shape != after.shape:
            raise RuntimeError(f"Raster shape mismatch on page {page_number}")
        different = np.any(np.abs(before - after) > 1, axis=2)
        count = int(different.sum())
        if not count:
            continue
        changed_pages.append(page_number)
        if page_number != target_page or bbox_top_points is None:
            changed_outside_bbox += count
            continue
        x, top, width, height = bbox_top_points
        sx = before.shape[1] / 595.32
        # Derive the page height from the raster aspect ratio to support the
        # small MediaBox variations present in the source PDFs.
        page_height = before.shape[0] / sx
        sy = before.shape[0] / page_height
        margin = 2.0
        left = max(0, int((x - margin) * sx))
        upper = max(0, int((top - margin) * sy))
        right = min(before.shape[1], int(np.ceil((x + width + margin) * sx)))
        lower = min(before.shape[0], int(np.ceil((top + height + margin) * sy)))
        allowed = np.zeros_like(different)
        allowed[upper:lower, left:right] = True
        changed_outside_bbox += int((different & ~allowed).sum())
        changed_inside_bbox += int((different & allowed).sum())

    return {
        "changed_original_pages": changed_pages,
        "changed_pixels_inside_stamp_bbox": changed_inside_bbox,
        "changed_pixels_outside_stamp_bbox": changed_outside_bbox,
    }


def verify_record(
    record: dict[str, object], source_root: Path, output_root: Path
) -> dict[str, object]:
    relative = Path(str(record["relative_path"]))
    source = source_root / relative
    if record["status"] == "preserved_existing_correct_stamp":
        if sha256(source) != record["baseline_sha256"]:
            raise RuntimeError(f"Preserved file changed since inventory: {relative}")
        return {"relative_path": relative.as_posix(), "status": "pass_preserved"}

    output = output_root / relative
    run(["qpdf", "--check", str(output)], capture=True)
    before = PdfReader(str(source), strict=False)
    after = PdfReader(str(output), strict=False)
    page_count_before = len(before.pages)
    page_count_after = len(after.pages)
    expected_after = page_count_before + (
        1 if record["placement"] == "appended_final_stamp_page" else 0
    )
    if page_count_after != expected_after:
        raise RuntimeError(f"Page count mismatch: {relative}")
    if document_structure(before) != document_structure(after):
        raise RuntimeError(f"Document metadata/catalog/bookmarks changed: {relative}")

    for page_index in range(page_count_before):
        source_page = before.pages[page_index]
        output_page = after.pages[page_index]
        if page_box(source_page, "mediabox") != page_box(output_page, "mediabox"):
            raise RuntimeError(f"MediaBox changed: {relative} page {page_index + 1}")
        if page_box(source_page, "cropbox") != page_box(output_page, "cropbox"):
            raise RuntimeError(f"CropBox changed: {relative} page {page_index + 1}")
        if int(source_page.get("/Rotate", 0) or 0) != int(output_page.get("/Rotate", 0) or 0):
            raise RuntimeError(f"Rotation changed: {relative} page {page_index + 1}")
        if annotations(source_page) != annotations(output_page):
            raise RuntimeError(f"Annotations changed: {relative} page {page_index + 1}")

    with tempfile.TemporaryDirectory(prefix="verify-stamp-") as temporary_name:
        temporary = Path(temporary_name)
        if extracted_text(source, page_count_before, temporary) != extracted_text(
            output, page_count_before, temporary
        ):
            raise RuntimeError(f"Extracted text changed: {relative}")
        target_page = (
            None
            if record["placement"] == "appended_final_stamp_page"
            else int(record["target_page_1_based"])
        )
        bbox = None if target_page is None else list(record["bbox_top_points"])
        raster = compare_renders(
            source,
            output,
            page_count_before,
            target_page,
            bbox,
            temporary,
        )
    if raster["changed_pixels_outside_stamp_bbox"] != 0:
        raise RuntimeError(f"Visible change outside stamp bbox: {relative}")
    if record["placement"] != "appended_final_stamp_page" and not raster[
        "changed_pixels_inside_stamp_bbox"
    ]:
        raise RuntimeError(f"Stamp produced no visible change: {relative}")

    return {
        "relative_path": relative.as_posix(),
        "status": "pass_stamped",
        "qpdf": "pass",
        "text": "identical",
        "page_boxes_rotation_annotations": "identical_on_all_original_pages",
        "document_metadata_catalog_bookmarks": "identical",
        **raster,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(verify_record, record, args.source_root, args.output_root): record
            for record in audit["records"]
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            record = futures[future]
            try:
                results.append(future.result())
            except Exception as error:  # fail report retains every path
                errors.append(
                    {"relative_path": str(record["relative_path"]), "error": str(error)}
                )
            if completed % 20 == 0 or completed == len(futures):
                print(f"verified {completed}/{len(futures)}; errors={len(errors)}", flush=True)

    report = {
        "schema": "department-stamp-verification-v1",
        "render_dpi": RENDER_DPI,
        "counts": {
            "total": len(audit["records"]),
            "passed": len(results),
            "failed": len(errors),
        },
        "errors": errors,
        "records": sorted(results, key=lambda item: str(item["relative_path"])),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
