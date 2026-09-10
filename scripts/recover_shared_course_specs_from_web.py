#!/usr/bin/env python3
"""Stage and publish verified Taif University shared-course specifications.

The source PDFs are preserved byte-for-byte in a dated evidence bundle.  The
``stage`` command adds narrowly scoped course-detail entries that point to those
sources so the deterministic outcome extractor can inspect them.  After that
extractor has run, ``publish`` clears the program-outcome column, appends the
hash-bound records to the shared-course manifest, and reroutes the public links.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from blank_shared_course_plo import (
    DATA_PATH,
    MANIFEST_PATH,
    OUTCOMES_PATH,
    ROOT,
    build_shared_inventory,
    clean_text,
    process_pdf,
    sha256,
    update_data_json,
    write_audit,
)


RECOVERY_RELATIVE = Path("assets/course-specifications/web-recovery-20260910")
RECOVERY_DIR = ROOT / RECOVERY_RELATIVE
RECOVERY_MANIFEST = RECOVERY_DIR / "manifest.json"
RECOVERED_AT = "2026-09-10"

RECOVERIES = (
    {
        "code": "105115-2",
        "title": "تاريخ المملكة",
        "document_title": "تاريخ المملكة العربية السعودية",
        "summary": (
            "يتناول نشأة الدولة السعودية ومراحلها، وتوحيد المملكة، ونظام الحكم "
            "والإدارة، وأبرز التحولات السياسية والاجتماعية والاقتصادية والحضارية."
        ),
        "temporary_source": "tmp/pdfs/web-recovery/wayback-matches/3a2ce29704cf5a9c.pdf",
        "source_url": "https://www.tu.edu.sa/Attachments/2b851d3e-0412-441f-90fe-c85eab572026_.pdf",
        "archive_timestamp": "20250702032649",
        "source_sha256": "27f5e817a61789d14969ec4787f1a44a68105353e2b0f3e9b5b6b23f7f611f69",
        "match_note": (
            "توصيف رسمي من جامعة الطائف؛ الرمز مطابق، وعنوان التوصيف الكامل "
            "«تاريخ المملكة العربية السعودية» يطابق الاسم المختصر في الخطة «تاريخ المملكة»."
        ),
    },
    {
        "code": "990113-2",
        "title": "الثقافة الصحية",
        "document_title": "الثقافة الصحية",
        "summary": (
            "يعرض مفاهيم الصحة والمرض والوقاية، والأمراض المعدية والمزمنة، والتغذية، "
            "والإسعافات الأولية، وبناء السلوك الصحي السليم."
        ),
        "temporary_source": "tmp/pdfs/web-recovery/wayback-matches/5e7def57ea8c1def.pdf",
        "source_url": "https://www.tu.edu.sa/Attachments/423d6cf7-9ae1-4b22-a78e-a3c377577fa0_.pdf",
        "archive_timestamp": "20231204033030",
        "source_sha256": "ea55a91f0983b93151312ece9ac82c1ae48fb218f036cd8a2bb3884b765faa7c",
        "match_note": "توصيف رسمي من جامعة الطائف؛ رمز المقرر واسمه مطابقان للخطة.",
    },
    {
        "code": "990311-2",
        "title": "المهارات الجامعية",
        "document_title": "المهارات الجامعية",
        "summary": (
            "ينمي مهارات الدراسة الجامعية والتواصل والعرض والقراءة والكتابة الأكاديمية، "
            "والتفكير الناقد، والعمل الجماعي، والمهارات المهنية والرقمية."
        ),
        "temporary_source": "tmp/pdfs/web-recovery/wayback-matches/14436f09eb0a3eaa.pdf",
        "source_url": "https://www.tu.edu.sa/Attachments/38df2763-0007-42a2-afb7-d8fdc84930e7_.pdf",
        "archive_timestamp": "20231204031839",
        "source_sha256": "27d531fd92c09732e22c7338b282c598008f70729e4b98427945d5ea6b074b9f",
        "match_note": "توصيف رسمي من جامعة الطائف؛ رمز المقرر واسمه مطابقان للخطة.",
    },
    {
        "code": "6602322-2",
        "title": "التجارة الإلكترونية",
        "document_title": "التجارة الإلكترونية",
        "summary": (
            "يعرف بالمفاهيم والأنماط الأساسية للتجارة الإلكترونية، والبنية التحتية، "
            "والحكومة الإلكترونية، والفرص والتحديات، وتطبيقاتها في بيئة الأعمال."
        ),
        "temporary_source": "tmp/pdfs/web-recovery/candidates/ecommerce_optional.pdf",
        "source_url": "https://www.tu.edu.sa/Attachments/9a3ca4c1-cb97-42f8-9d69-ea912397be45_.pdf",
        "source_page_url": "https://www.tu.edu.sa/Ar/كلية-إدارة-الاعمال/98/Pages/20821/قسم-التسويق",
        "source_anchor": "توصيف مقرر التجارة الإلكترونية( متطلب اختياري)",
        "source_sha256": "ce2b8b3ad617ac0289738ee630bdb127767fa345ae3beef006226743a22d2f08",
        "match_note": "توصيف رسمي من جامعة الطائف؛ رمز المقرر واسمه مطابقان للخطة.",
    },
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def source_relative(record: dict[str, str]) -> str:
    return (RECOVERY_RELATIVE / f"{record['code']}.pdf").as_posix()


def recovered_scopes(inventory: dict[str, Any], code: str, title: str) -> list[dict[str, str]]:
    matches = [
        item
        for item in inventory["shared"]
        if item["course_code"] == code and title in item["names"]
    ]
    if len(matches) != 1:
        raise RuntimeError(f"{code}: expected one shared code-title identity, found {len(matches)}")
    scopes = {
        tuple(clean_text(plan[field]) for field in ("program", "degree", "plan_type", "version")): {
            field: clean_text(plan[field])
            for field in ("program", "degree", "plan_type", "version")
        }
        for plan in matches[0]["plans"]
    }
    program_identities = {(scope[0], scope[1]) for scope in scopes}
    if len(program_identities) < 2:
        raise RuntimeError(f"{code}: recovery target is not shared across programs")
    return [scopes[key] for key in sorted(scopes)]


def stage() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    inventory = build_shared_inventory(data)
    collisions = sorted(
        record["code"] for record in RECOVERIES if record["code"] in data["course_details"]
    )
    if collisions:
        raise RuntimeError("Recovery targets already exist in course_details: " + ", ".join(collisions))

    evidence_records = []
    additions: dict[str, Any] = {}
    for record in RECOVERIES:
        source = ROOT / record["temporary_source"]
        if not source.is_file():
            raise FileNotFoundError(source)
        if sha256(source) != record["source_sha256"]:
            raise RuntimeError(f"{record['code']}: downloaded source hash changed")
        subprocess.run(
            ["qpdf", "--check", str(source)], check=True, capture_output=True, text=True
        )
        destination = ROOT / source_relative(record)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha256(destination) != record["source_sha256"]:
            raise RuntimeError(f"{record['code']}: stored source hash mismatch")

        public_note = (
            record["match_note"]
            + " استُعيد التوصيف من الويب وتحقق انتماؤه لجامعة الطائف في 2026-09-10."
        )
        additions[record["code"]] = {
            "variants": [
                {
                    "scopes": recovered_scopes(
                        inventory, record["code"], record["title"]
                    ),
                    "title": record["title"],
                    "summary": record["summary"],
                    "pdf_url": source_relative(record),
                    "specification_code": record["code"],
                    "match_status": "verified",
                    "match_note": public_note,
                }
            ]
        }
        evidence_records.append(
            {
                key: record[key]
                for key in (
                    "code",
                    "title",
                    "document_title",
                    "source_url",
                    "source_page_url",
                    "source_anchor",
                    "archive_timestamp",
                    "source_sha256",
                )
                if key in record
            }
            | {"stored_source": source_relative(record)}
        )

    data["course_details"].update(additions)
    write_json(DATA_PATH, data)
    write_json(
        RECOVERY_MANIFEST,
        {
            "recovered_at": RECOVERED_AT,
            "source_authority": "جامعة الطائف (tu.edu.sa)",
            "acceptance_rule": (
                "ملف PDF لتوصيف مقرر، من نطاق جامعة الطائف، مع تطابق الرمز والاسم "
                "أو تطابق الرمز وتوسع العنوان الرسمي دون تغيير الهوية."
            ),
            "records": evidence_records,
        },
    )
    print(f"Staged {len(additions)} verified web specifications")


def publish() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_PATH.read_text(encoding="utf-8"))
    recovery_manifest = json.loads(RECOVERY_MANIFEST.read_text(encoding="utf-8"))
    evidence_by_source = {
        record["stored_source"]: record for record in recovery_manifest["records"]
    }
    inventory = build_shared_inventory(data)
    sources = {
        source: record
        for source, record in inventory["by_pdf"].items()
        if source in evidence_by_source
    }
    if set(sources) != set(evidence_by_source):
        missing = sorted(set(evidence_by_source) - set(sources))
        raise RuntimeError(f"Recovered shared sources did not resolve in inventory: {missing}")

    existing_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    existing_sources = {record["source"] for record in existing_manifest["records"]}
    overlap = sorted(existing_sources.intersection(sources))
    if overlap:
        raise RuntimeError("Recovered sources already published: " + ", ".join(overlap))

    pending = []
    for source in sorted(sources):
        record, temporary = process_pdf(sources[source], outcomes)
        evidence = evidence_by_source[source]
        record["web_source"] = {
            key: evidence[key]
            for key in (
                "source_url",
                "source_page_url",
                "source_anchor",
                "archive_timestamp",
            )
            if key in evidence
        }
        record["recovered_at"] = RECOVERED_AT
        pending.append((record, temporary))

    new_records = [record for record, _temporary in pending]
    updated_data, changes = update_data_json(data, new_records)
    combined_records = existing_manifest["records"] + new_records
    manifest = copy.deepcopy(existing_manifest)
    manifest["records"] = combined_records
    manifest["shared_course_count"] = len(inventory["shared"])
    manifest["shared_course_with_spec_count"] = sum(
        bool(item["variant_count"]) for item in inventory["shared"]
    )
    manifest["shared_course_without_spec_count"] = sum(
        not item["variant_count"] for item in inventory["shared"]
    )
    manifest["output_count"] = len(combined_records)
    manifest["clo_row_count"] = sum(len(record["edits"]) for record in combined_records)
    manifest["cleared_cell_count"] = sum(
        len(record["cleared_cells"]) for record in combined_records
    )
    manifest["data_changes"] = {
        "rerouted_variants": existing_manifest["data_changes"]["rerouted_variants"]
        + changes["rerouted_variants"],
        "updated_notes": existing_manifest["data_changes"]["updated_notes"]
        + changes["updated_notes"],
    }
    manifest["latest_recovery_at"] = RECOVERED_AT

    for record, temporary in pending:
        os.replace(temporary, ROOT / record["output"])
    write_json(MANIFEST_PATH, manifest)
    write_json(DATA_PATH, updated_data)
    write_audit(inventory, manifest)
    print(f"Published {len(new_records)} recovered shared-course PDFs")
    print(f"Shared identities with specifications: {manifest['shared_course_with_spec_count']}")
    print(f"Output PDFs: {manifest['output_count']}")
    print(f"CLO rows covered: {manifest['clo_row_count']}")
    print(f"Non-empty PLO cells cleared: {manifest['cleared_cell_count']}")


def sync_manifest() -> None:
    """Align recovered manifest selectors with CLO rows in the final PDFs."""

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    outcomes = json.loads(OUTCOMES_PATH.read_text(encoding="utf-8"))
    changed = 0
    for record in manifest["records"]:
        if record.get("recovered_at") != RECOVERED_AT:
            continue
        variants = [
            variant
            for variant in outcomes["courses"][record["course_key"]]["variants"]
            if variant["source_pdf"] == record["output"]
        ]
        if len(variants) != 1:
            raise RuntimeError(
                f"{record['course_key']}: expected one final extracted variant"
            )
        existing = {edit["clo"]: edit for edit in record["edits"]}
        synchronized = []
        for clo in variants[0]["extracted"]["clos"]:
            code = clean_text(clo.get("code"))
            if not code:
                continue
            edit = copy.deepcopy(existing.get(code, {}))
            edit["clo"] = code
            edit["page_1_based"] = int(clo["source_page"])
            edit["plo_from"] = edit.get("plo_from", [])
            edit["plo_to"] = []
            edit["blank_by_policy"] = True
            synchronized.append(edit)
        synchronized.sort(
            key=lambda item: (
                item["page_1_based"],
                tuple(int(part) for part in item["clo"].split(".")),
            )
        )
        if record["edits"] != synchronized:
            record["edits"] = synchronized
            changed += 1
    manifest["clo_row_count"] = sum(
        len(record["edits"]) for record in manifest["records"]
    )
    write_json(MANIFEST_PATH, manifest)
    print(
        f"Synchronized {changed} recovered records; "
        f"CLO rows={manifest['clo_row_count']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("stage", "publish", "sync-manifest"))
    args = parser.parse_args()
    if args.command == "stage":
        stage()
    elif args.command == "publish":
        publish()
    else:
        sync_manifest()


if __name__ == "__main__":
    main()
