"""Apply verbatim CLO text corrections left open by the shared-program follow-up.

Each run applies one named round (``--round``). The first round,
``text-corrections-2026-10-16`` (commit 1fe900d), is the default; later rounds
such as ``machine-extraction-review-2026-10-17`` reuse the same checks.

The follow-up round (commits dd616ed and ad87e4a) transferred 19 CLO texts and
kept further truncated, merged or garbled rows as ``judgment_only_readings``.
This round reads a reviewed input file whose items each carry two independent
image readings of the hash-matched source PDF that agree with the transferred
text, and then:

* appends one record per item to ``clo-text-completions.json`` (decision
  ``complete_verbatim``, under the round given by ``--round``);
* writes ``clos[i].text/source_status/extraction_method/confidence`` under
  ``verified_extraction_correction_matches_source`` to every programme child
  that shares the source row. An existing text override path is replaced in
  place (the verifier rejects duplicate paths); the replaced overrides are kept
  whole in the record as ``superseded_overrides``;
* refreshes ``clo_text_in_json`` in ``alignment-decisions.json`` and
  ``remaining-alignment-gaps.json``, the package hashes and the statistics.

It never touches PDFs, ``extracted``, ``plo_mappings`` or the row count, and
it refuses to run when the current state differs from the input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_course_outcomes as verifier  # noqa: E402
from _shared_alignment_test_support import effective_extraction  # noqa: E402

BUNDLE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261016"
COMPLETIONS_PATH = "assets/course-specifications/shared-program-json-alignment-20261016/clo-text-completions.json"
TEXT_POLICY = "verified_extraction_correction_matches_source"
ROUND = "text-corrections-2026-10-16"
VALUES = {"source_status": "present", "extraction_method": "verified_visual_review", "confidence": "verified"}
READING_KEYS = ("orchestrator_image_reading", "blind_image_reading")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="reviewed correction items (JSON list)")
    parser.add_argument("--reviewed-at", default="2026-10-16T23:00:00+03:00")
    parser.add_argument("--round", default=ROUND, help=f"round label recorded on each item (default {ROUND})")
    parser.add_argument("--check", action="store_true", help="validate inputs without writing")
    args = parser.parse_args(argv)
    round_label = args.round

    outcomes_path = ROOT / "course-outcomes.json"
    outcomes = load(outcomes_path)
    completions = load(BUNDLE / "clo-text-completions.json")
    decisions_doc = load(BUNDLE / "alignment-decisions.json")
    gaps_doc = load(BUNDLE / "remaining-alignment-gaps.json")
    items = load(args.input)
    if any(r.get("round") == round_label for r in completions["records"]):
        raise SystemExit(f"round {round_label} already applied")

    next_id = max(r["id"] for r in completions["records"]) + 1
    seen = set()
    changed = {}
    variant_rows = 0
    for item in items:
        key = item["course_code"], item["source_pdf"], item["clo_index"]
        if key in seen:
            raise SystemExit(f"duplicate item {key}")
        seen.add(key)
        if sha256(ROOT / item["source_pdf"]) != item["source_sha256"]:
            raise SystemExit(f"source hash mismatch for {item['source_pdf']}")
        text = item["text_verbatim"]
        if not text or text != text.strip() or "  " in text:
            raise SystemExit(f"non-normalized text {key}")
        for name in READING_KEYS:
            reading = unicodedata.normalize("NFC", item["readings"][name])
            if reading == unicodedata.normalize("NFC", text):
                continue
            # Only a whitespace difference after a non-joining letter may be
            # settled, and only with a recorded text-layer resolution.
            if "".join(reading.split()) != "".join(unicodedata.normalize("NFC", text).split()):
                raise SystemExit(f"{name} disagrees with transferred text {key}")
            if not item.get("transfer_notes"):
                raise SystemExit(f"{name} whitespace difference without a transfer note {key}")
        hits = [
            v for v in outcomes["courses"][item["course_code"]]["variants"]
            if v["source_pdf"] == item["source_pdf"]
        ]
        if not hits:
            raise SystemExit(f"no current variant for {key}")
        index = item["clo_index"]
        evidence = (
            f"مراجعة {item['source_pdf']} SHA256={item['source_sha256']} | الصفحات {item['source_page']} | "
            f"نقل حرفي لنص CLO {item['clo_code']} من خلية المصدر المرئية بعد قراءتين مستقلتين متطابقتين؛ "
            f"لا تأليف ولا تعديل للنص. الحالة السابقة: {item['previous_state']}. "
            f"سجل النقل: {COMPLETIONS_PATH} (الجولة {round_label})."
        )
        superseded = []
        for variant in hits:
            row = effective_extraction(variant)["clos"][index]
            if row["code"] != item["clo_code"]:
                raise SystemExit(f"row code mismatch {key} {variant['variant_id']}")
            if row["text"] != item["text_before"]:
                raise SystemExit(f"unexpected current text {key}: {row['text']!r}")
            fields = {f"clos[{index}].text": text, **{f"clos[{index}].{k}": v for k, v in VALUES.items()}}
            for field, value in fields.items():
                entry = {
                    "field": field,
                    "value": value,
                    "evidence": evidence,
                    "policy": TEXT_POLICY,
                    "reviewed_at": args.reviewed_at,
                }
                positions = [i for i, o in enumerate(variant["overrides"]) if o["field"] == field]
                if len(positions) > 1:
                    raise SystemExit(f"duplicate override path {key} {field}")
                if positions:
                    previous = variant["overrides"][positions[0]]
                    if previous.get("policy") != TEXT_POLICY:
                        raise SystemExit(f"existing override has another policy {key} {field}")
                    superseded.append({"variant_id": variant["variant_id"], **previous})
                    variant["overrides"][positions[0]] = entry
                else:
                    variant["overrides"].append(entry)
            changed[(item["course_code"], variant["variant_id"], index)] = text
            variant_rows += 1
        completions["records"].append({
            "id": next_id,
            "round": round_label,
            "course_code": item["course_code"],
            "source_pdf": item["source_pdf"],
            "source_sha256": item["source_sha256"],
            "source_page": item["source_page"],
            "clo_code": item["clo_code"],
            "clo_index": index,
            "text_before": item["text_before"],
            "cell_status": "text",
            "decision": "complete_verbatim",
            "text_verbatim": text,
            "previous_state": item["previous_state"],
            "excluded_layout_markers": item.get("excluded_layout_markers", []),
            "readings": item["readings"],
            "note": item["note"],
            "transfer_notes": item.get("transfer_notes", []),
            "programme_rows": len(hits),
            # Earlier verified overrides replaced in place, kept whole so no
            # previous evidence is lost from the audit trail.
            "superseded_overrides": superseded,
        })
        next_id += 1

    decision_rows = 0
    for record in decisions_doc["records"]:
        text = changed.get((record["course_code"], record["variant_id"], record["clo_index"]))
        if text is not None:
            record["clo_text_in_json"] = text
            decision_rows += 1
    gap_rows = 0
    for record in gaps_doc["records"]:
        text = changed.get((record["course_code"], record["variant_id"], record["clo_index"]))
        if text is not None:
            record["clo_text_in_json"] = text
            gap_rows += 1

    applied = [r for r in completions["records"] if r.get("round") == round_label]
    completions["summary"][round_label] = {
        "complete_verbatim": len(applied),
        "programme_rows": variant_rows,
        "judgment_only_readings_applied": sum(
            1 for r in applied if r["readings"].get("prior_judgment_only_reading") is not None
        ),
    }
    completions["summary"]["complete_verbatim_all_rounds"] = sum(
        1 for r in completions["records"] if r["decision"] == "complete_verbatim"
    )

    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        for message in errors.messages:
            print("ERROR:", message, file=sys.stderr)
        return 1

    print(json.dumps({
        "items": len(items),
        "programme_rows": variant_rows,
        "decision_rows": decision_rows,
        "gap_rows": gap_rows,
    }, ensure_ascii=False, indent=1))
    if args.check:
        return 0

    dump(outcomes_path, outcomes)
    dump(BUNDLE / "clo-text-completions.json", completions)
    dump(BUNDLE / "alignment-decisions.json", decisions_doc)
    dump(BUNDLE / "remaining-alignment-gaps.json", gaps_doc)
    manifest_path = BUNDLE / "manifest.json"
    manifest = load(manifest_path)
    for name in ("clo-text-completions.json", "alignment-decisions.json", "remaining-alignment-gaps.json"):
        manifest["reference_files"][name] = sha256(BUNDLE / name)
    dump(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
