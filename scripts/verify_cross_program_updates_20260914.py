#!/usr/bin/env python3
"""Verify hashes, source fidelity, and render QA contact sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageDraw

from build_cross_program_updates_20260914 import OUTPUT, RECORDS, ROOT, SOURCE_ROOT, normalize


PDFTOTEXT = Path("/opt/homebrew/bin/pdftotext")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_text(path: Path) -> str:
    return subprocess.run(
        [str(PDFTOTEXT), "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    ).stdout


def page_image(page: pymupdf.Page, zoom: float = 1.25) -> Image.Image:
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def make_contact(path: Path, output: Path) -> None:
    with pymupdf.open(path) as document:
        pages = [page_image(page) for page in document]
    thumb_width = 330
    thumbs = []
    for index, page in enumerate(pages, start=1):
        ratio = thumb_width / page.width
        thumb = page.resize((thumb_width, round(page.height * ratio)), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (thumb_width + 12, thumb.height + 34), "white")
        canvas.paste(thumb, (6, 24))
        ImageDraw.Draw(canvas).text((8, 5), f"Page {index}", fill="black")
        thumbs.append(canvas)
    columns = 3
    rows = (len(thumbs) + columns - 1) // columns
    cell_width = max(image.width for image in thumbs)
    cell_height = max(image.height for image in thumbs)
    contact = Image.new("RGB", (columns * cell_width, rows * cell_height), "#D9D9D9")
    for index, thumb in enumerate(thumbs):
        contact.paste(thumb, ((index % columns) * cell_width, (index // columns) * cell_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    contact.save(output)


def verify_direct_fidelity(source: Path, published: Path) -> None:
    with pymupdf.open(source) as raw, pymupdf.open(published) as final:
        if raw.page_count != final.page_count:
            raise ValueError(f"Page-count mismatch: {source} -> {published}")
        for index in range(raw.page_count):
            raw_image = page_image(raw[index], 1.0)
            final_image = page_image(final[index], 1.0)
            if raw_image.size != final_image.size:
                raise ValueError(f"Page-size mismatch on {published}, page {index + 1}")
            difference = ImageChops.difference(
                raw_image,
                final_image,
            ).convert("L")
            histogram = difference.histogram()
            total_pixels = difference.width * difference.height
            changed_ratio = sum(histogram[1:]) / total_pixels
            normalized_energy = (
                sum(value * count for value, count in enumerate(histogram))
                / (255 * total_pixels)
            )
            if changed_ratio or normalized_energy:
                raise ValueError(f"Unexpected visual difference: {published}, page {index + 1}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contacts", type=Path, default=ROOT / "tmp" / "cross-program-qa")
    args = parser.parse_args()

    manifest = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8"))
    records = {record["output"]: record for record in manifest["records"]}
    if len(records) != 22:
        raise ValueError("Expected 22 manifest records")

    for item in RECORDS:
        published = OUTPUT / item["output_name"]
        relative = published.relative_to(ROOT).as_posix()
        source = SOURCE_ROOT / item["source"]
        record = records[relative]
        if sha256(published) != record["output_sha256"]:
            raise ValueError(f"Hash mismatch: {published}")
        with pymupdf.open(published) as document:
            if document.page_count != record["page_count"]:
                raise ValueError(f"Manifest page-count mismatch: {published}")
        text = extract_text(published)
        if normalize(item["code"].rsplit("-", 1)[0]) not in normalize(text):
            raise ValueError(f"Expected course code absent: {published}")
        if source.suffix.lower() == ".pdf":
            if sha256(source) != sha256(published):
                raise ValueError(f"Direct PDF source is not byte-identical: {published}")
            verify_direct_fidelity(source, published)
        make_contact(published, args.contacts / f"{published.stem}.png")

    print(json.dumps({"verified_pdfs": 22, "contact_sheets": 22, "status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
