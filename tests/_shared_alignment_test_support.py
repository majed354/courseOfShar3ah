"""Test-only access to the immutable pre-specialization audit and its children.

Historical mutating importers must be replayed against their historical snapshot:
they predate program-specific children and can replace the newer override layer.
The current children are checked independently, in full, by the specialization
contract tests. This helper does not change production lookup or replay behavior.
"""

import copy
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261016"
# Second specialization (eleven further shared courses), applied after BUNDLE.
SPLIT_BUNDLE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261028"
# Quran copies repointed from blanked shared PDFs to official specifications (2026-10-28).
QURAN_OFFICIAL_BUNDLE = ROOT / "assets/course-specifications/quran-official-source-20261028"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def previous_context():
    context = load(BUNDLE / "previous-context.json")
    # Missing history is an error, never an excuse to omit historical assertions.
    return context["data"], context["course_outcomes"]


def scope_key(scope):
    return tuple(str(scope.get(key, "")) for key in ("program", "degree", "plan_type", "version"))


def scope_set(scopes):
    return {scope_key(scope) for scope in scopes}


def lineage_records():
    return load(BUNDLE / "variant-lineage.json")["records"]


def split_lineage_records():
    """Lineage of the 2026-10-28 specialization of the remaining shared copies."""
    return load(SPLIT_BUNDLE / "variant-lineage.json")["records"]


def split_snapshot():
    """Frozen parent records of the 2026-10-28 specialization."""
    return load(SPLIT_BUNDLE / "previous-context.json")


def quran_official_lineage():
    """Lineage of the Quran copies repointed to their official specifications."""
    return load(QURAN_OFFICIAL_BUNDLE / "variant-lineage.json")["records"]


def before_quran_official_repointing(data, outcomes):
    """Live records with the repointed courses restored from their frozen snapshot.

    Earlier package contracts govern the state they produced; the repointing is
    checked against this snapshot by its own contract test.
    """
    snapshot = load(QURAN_OFFICIAL_BUNDLE / "previous-context.json")
    data, outcomes = copy.deepcopy(data), copy.deepcopy(outcomes)
    data["course_details"].update(copy.deepcopy(snapshot["data_course_details"]))
    outcomes["courses"].update(copy.deepcopy(snapshot["outcome_courses"]))
    return data, outcomes


def specialized_course_codes():
    """Every course whose live variants were re-created per programme."""
    return {r["course_code"] for r in lineage_records()} | {r["course_code"] for r in split_lineage_records()}


def effective_extraction(variant):
    value = copy.deepcopy(variant["extracted"])
    for override in variant.get("overrides", []):
        tokens = [name or int(index) for name, index in re.findall(r"([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]", override["field"])]
        target = value
        for token in tokens[:-1]:
            target = target[token]
        target[tokens[-1]] = copy.deepcopy(override["value"])
    return value


def trim_variant_to_scopes(variant, scopes):
    """Expected inherited extraction, including all historical override metadata."""
    result = copy.deepcopy(variant)
    result["scopes"] = copy.deepcopy(scopes)

    def trim(mappings):
        return [copy.deepcopy(mapping) for scope in scopes for mapping in mappings if mapping["scope"] == scope]

    for row in result["extracted"]["clos"]:
        row["plo_mappings"] = trim(row["plo_mappings"])
    for override in result.get("overrides", []):
        if override["field"] == "clos":
            for row in override["value"]:
                row["plo_mappings"] = trim(row["plo_mappings"])
        elif re.fullmatch(r"clos\[\d+\]\.plo_mappings", override["field"]):
            override["value"] = trim(override["value"])
    return result
