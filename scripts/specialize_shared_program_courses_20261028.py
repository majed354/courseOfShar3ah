"""Split the remaining multi-programme shared course copies into one copy per programme.

The 2026-10-16 package specialised 54 shared courses. Eleven further course
records still served several programmes from one variant (six legacy direct
records and five multi-scope variants), so one printed or missing CLO→PLO
mapping was read for programmes whose PLO codes mean different things.

This tool performs only the structural step, mirroring the earlier package:

* ``data.json``: each multi-programme variant (or legacy record) becomes one
  variant per (programme, degree), keeping every catalog field and PDF link;
* ``course-outcomes.json``: each child copies its parent's extraction and
  inherited overrides trimmed to its own scopes; ids are recomputed by the
  verifier's identity function; source-correction recommendations follow the
  child whose programme they concern;
* the package records the lineage and a compact snapshot of the parents.

The academic links are applied afterwards by
``apply_shared_program_alignment_20261028.py``. No PDF is touched.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_course_outcomes as verifier  # noqa: E402
from _shared_alignment_test_support import trim_variant_to_scopes  # noqa: E402

BUNDLE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261028"
TARGETS = [
    "2001113-2", "2001114-2", "20021304-2", "2003220-2", "2004112-2", "20041302-2",
    "20041303-2", "2004205-2", "2004209-2", "2004313-2", "2004403-2",
]
SCOPE_KEYS = ("program", "degree", "plan_type", "version")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def raw_scope(scope):
    return {key: scope[key] for key in SCOPE_KEYS}


def group_key(scope):
    return scope["program"], scope["degree"]


def main() -> int:
    data_path, outcomes_path = ROOT / "data.json", ROOT / "course-outcomes.json"
    data, outcomes = load(data_path), load(outcomes_path)
    before_expected, _ = verifier.rebuild_expected_variants(data)
    snapshot = {"data_course_details": {}, "outcome_courses": {}, "recommendations": []}
    lineage = []

    for code in TARGETS:
        detail = data["course_details"][code]
        snapshot["data_course_details"][code] = copy.deepcopy(detail)
        snapshot["outcome_courses"][code] = copy.deepcopy(outcomes["courses"][code])
        legacy = "variants" not in detail
        source_variants = [detail] if legacy else detail["variants"]
        expected = before_expected[code]
        if len(expected) != len(source_variants):
            raise SystemExit(f"{code}: unexpected variant count")
        new_variants = []
        for raw, built in zip(source_variants, expected):
            groups = {}
            for scope in built["scopes"]:
                groups.setdefault(group_key(scope), []).append(scope)
            if len(groups) == 1 and not legacy:
                new_variants.append(raw)
                continue
            for _, scopes in sorted(groups.items(), key=lambda item: verifier.normalized_scope_sort_key(item[1][0])):
                child = {key: copy.deepcopy(value) for key, value in raw.items() if key not in ("scope", "scopes")}
                child = {"scopes": [raw_scope(s) for s in scopes], **child}
                new_variants.append(child)
        data["course_details"][code] = {"variants": new_variants}

    after_expected, after_stats = verifier.rebuild_expected_variants(data)

    for code in TARGETS:
        parents = {v["variant_id"]: v for v in outcomes["courses"][code]["variants"]}
        children = []
        for built in after_expected[code]:
            if built["variant_id"] in parents:
                children.append(parents[built["variant_id"]])
                continue
            scope_keys = {verifier.normalized_scope_sort_key(s) for s in built["scopes"]}
            parent = next(
                v for b in before_expected[code] for v in [parents[b["variant_id"]]]
                if b["source_pdf"] == built["source_pdf"]
                and scope_keys <= {verifier.normalized_scope_sort_key(s) for s in b["scopes"]}
            )
            if parent["catalog"] != built["catalog"]:
                raise SystemExit(f"{code}: catalog changed for {built['source_pdf']}")
            child = trim_variant_to_scopes(parent, built["scopes"])
            child["variant_id"] = built["variant_id"]
            child["scopes"] = built["scopes"]
            children.append(child)
            lineage.append({
                "course_code": code,
                "old_variant_id": parent["variant_id"],
                "new_variant_id": built["variant_id"],
                "source_pdf": parent["source_pdf"],
                "source_sha256": parent["source_sha256"],
                "old_scopes": parent["scopes"],
                "new_scopes": built["scopes"],
                "legacy_direct_record": "variants" not in snapshot["data_course_details"][code],
            })
        outcomes["courses"][code]["variants"] = sorted(children, key=lambda v: v["variant_id"])

    # Recommendations follow the children of their variant; a programme-specific
    # note follows only the child of that programme.
    by_parent = {}
    for record in lineage:
        by_parent.setdefault(record["old_variant_id"], []).append(record)
    new_recommendations = []
    for entry in outcomes["source_correction_recommendations"]:
        records = by_parent.get(entry["variant_id"])
        if not records:
            new_recommendations.append(entry)
            continue
        snapshot["recommendations"].append(copy.deepcopy(entry))
        targets = records
        if entry["issue_code"] == "program_specific_plo_links_absent":
            targets = [r for r in records if any(s["program"] in entry["message"] for s in r["new_scopes"])]
            if len(targets) != 1:
                raise SystemExit(f"cannot place programme-specific recommendation {entry['id']}")
        for record in targets:
            child = dict(entry)
            child["variant_id"] = record["new_variant_id"]
            child["id"] = hashlib.sha256(verifier.canonical_json(
                {"parent_recommendation_id": entry["id"], "variant_id": record["new_variant_id"]}
            ).encode("utf-8")).hexdigest()
            new_recommendations.append(child)
    outcomes["source_correction_recommendations"] = new_recommendations

    errors = verifier.ErrorCollector()
    outcomes["statistics"] = verifier.recompute_statistics(outcomes, errors)
    if errors.count:
        print("\n".join(errors.messages), file=sys.stderr)
        return 1

    BUNDLE.mkdir(parents=True, exist_ok=True)
    dump(data_path, data)
    outcomes["source_data"]["sha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
    dump(outcomes_path, outcomes)
    dump(BUNDLE / "previous-context.json", {
        "schema_version": "shared-program-split-previous-context-v1",
        "note": "لقطة السجلات الأصلية للمقررات الإحدى عشرة قبل التخصيص؛ بقية المستودع لم يتغير.",
        **snapshot,
    })
    dump(BUNDLE / "variant-lineage.json", {
        "schema_version": "shared-program-variant-lineage-v1",
        "summary": {
            "target_courses": len(TARGETS),
            "parents": len({r["old_variant_id"] for r in lineage}),
            "children": len(lineage),
            "variants_after": after_stats["variants"],
            "scopes_after": after_stats["scopes"],
            "legacy_records_after": after_stats["legacy_records"],
        },
        "records": lineage,
    })
    print(json.dumps({"parents": len({r['old_variant_id'] for r in lineage}), "children": len(lineage), **after_stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
