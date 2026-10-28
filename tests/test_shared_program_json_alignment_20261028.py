import hashlib
import re
import sys
import unittest
from collections import Counter, defaultdict

from _shared_alignment_test_support import (
    ROOT, SPLIT_BUNDLE, effective_extraction, load, scope_key, scope_set,
    split_lineage_records, split_snapshot, trim_variant_to_scopes,
)

sys.path.insert(0, str(ROOT / "scripts"))
from verify_course_outcomes import rebuild_expected_variants


POLICY = "authorized_program_alignment_revision"
REFERENCE = ROOT / "assets/course-specifications/shared-program-json-alignment-20261016/program-plo-reference.json"


class SharedProgramSplit20261028Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(ROOT / "data.json")
        cls.outcomes = load(ROOT / "course-outcomes.json")
        cls.snapshot = split_snapshot()
        cls.lineage = split_lineage_records()
        cls.decisions = load(SPLIT_BUNDLE / "alignment-decisions.json")
        cls.review = load(SPLIT_BUNDLE / "review-decisions.json")
        cls.references = load(REFERENCE)["program_versions"]
        cls.variants = {
            (code, v["variant_id"]): v
            for code, course in cls.outcomes["courses"].items()
            for v in course["variants"]
        }
        cls.parents = {
            (code, v["variant_id"]): v
            for code, course in cls.snapshot["outcome_courses"].items()
            for v in course["variants"]
        }
        cls.targets = set(cls.snapshot["outcome_courses"])

    def reference_for(self, scope):
        found = [r for r in self.references if any(scope_key(s) == scope_key(scope) for s in r["scopes"])]
        self.assertEqual(1, len(found), scope)
        return found[0]

    def test_eleven_courses_are_split_one_programme_per_copy(self):
        self.assertEqual(11, len(self.targets))
        self.assertEqual(self.targets, {r["course_code"] for r in self.lineage})
        children = Counter((r["course_code"], r["new_variant_id"]) for r in self.lineage)
        self.assertEqual({1}, set(children.values()))
        self.assertEqual(37, len(children))
        by_parent = defaultdict(list)
        for record in self.lineage:
            parent = self.parents[record["course_code"], record["old_variant_id"]]
            child = self.variants[record["course_code"], record["new_variant_id"]]
            self.assertEqual(parent["scopes"], record["old_scopes"])
            self.assertEqual(child["scopes"], record["new_scopes"])
            for side in (parent, child):
                self.assertEqual(record["source_pdf"], side["source_pdf"])
                self.assertEqual(record["source_sha256"], side["source_sha256"])
            self.assertEqual(parent["catalog"], child["catalog"])
            self.assertEqual(1, len({(s["program"], s["degree"]) for s in child["scopes"]}))
            by_parent[record["course_code"], record["old_variant_id"]].append(child)
        self.assertEqual(11, len(by_parent))
        for key, kids in by_parent.items():
            scopes = [scope_key(s) for kid in kids for s in kid["scopes"]]
            self.assertEqual(len(scopes), len(set(scopes)), key)
            self.assertEqual(scope_set(self.parents[key]["scopes"]), set(scopes), key)
        # Every live variant of a target course is a child or an untouched sibling.
        for code in self.targets:
            live = {v["variant_id"] for v in self.outcomes["courses"][code]["variants"]}
            kids = {r["new_variant_id"] for r in self.lineage if r["course_code"] == code}
            untouched = {v["variant_id"] for v in self.snapshot["outcome_courses"][code]["variants"]} - {
                r["old_variant_id"] for r in self.lineage}
            self.assertEqual(kids | untouched, live, code)
        expected, stats = rebuild_expected_variants(self.data)
        for code in self.targets:
            self.assertIn("variants", self.data["course_details"][code])
            self.assertEqual({v["variant_id"] for v in expected[code]},
                             {v["variant_id"] for v in self.outcomes["courses"][code]["variants"]})
        self.assertEqual((574, 737), (stats["variants"], stats["scopes"]))

    def test_source_bytes_extraction_and_effective_content_are_preserved(self):
        for record in self.lineage:
            parent = self.parents[record["course_code"], record["old_variant_id"]]
            child = self.variants[record["course_code"], record["new_variant_id"]]
            inherited = trim_variant_to_scopes(parent, child["scopes"])
            with self.subTest(course=record["course_code"], child=child["variant_id"][:8]):
                self.assertEqual(inherited["extracted"], child["extracted"])
                before, after = effective_extraction(inherited), effective_extraction(child)
                self.assertEqual(len(before["clos"]), len(after["clos"]))
                for old_row, new_row in zip(before["clos"], after["clos"]):
                    self.assertEqual({k: v for k, v in old_row.items() if k != "plo_mappings"},
                                     {k: v for k, v in new_row.items() if k != "plo_mappings"})
                self.assertEqual({k: v for k, v in before.items() if k != "clos"},
                                 {k: v for k, v in after.items() if k != "clos"})
                authorized = {o["field"] for o in child["overrides"] if o.get("policy") == POLICY}
                self.assertTrue(all(re.fullmatch(r"clos\[\d+\]\.plo_mappings", f) for f in authorized))
                self.assertEqual([o for o in inherited["overrides"] if o["field"] not in authorized],
                                 [o for o in child["overrides"] if o["field"] not in authorized])
                fields = [o["field"] for o in child["overrides"]]
                self.assertEqual(len(fields), len(set(fields)))
                self.assertEqual(child["source_sha256"], hashlib.sha256((ROOT / child["source_pdf"]).read_bytes()).hexdigest())

    def test_every_programme_row_has_one_reviewed_scoped_decision(self):
        keys = Counter()
        for decision in self.decisions["records"]:
            code, vid, index = decision["course_code"], decision["variant_id"], decision["clo_index"]
            keys[code, vid, index, scope_key(decision["scope"])] += 1
            variant = self.variants[code, vid]
            row = effective_extraction(variant)["clos"][index]
            self.assertEqual(decision["clo_code"], row["code"])
            self.assertIn(decision["scope"], variant["scopes"])
            reference = self.reference_for(decision["scope"])
            self.assertEqual(reference["id"], decision["program_reference_id"])
            self.assertEqual(reference["source_sha256"], decision["program_source_sha256"])
            mapping = [m for m in row["plo_mappings"] if m["scope"] == decision["scope"]]
            self.assertEqual(1, len(mapping))
            mapping = mapping[0]
            override = next(o for o in variant["overrides"] if o["field"] == f"clos[{index}].plo_mappings")
            self.assertEqual(POLICY, override["policy"])
            for evidence in (override["evidence"], mapping["evidence"]):
                self.assertEqual(variant["source_sha256"], re.search(r"SHA256=([a-f0-9]{64})", evidence).group(1))
                self.assertIn(reference["source_sha256"], evidence)
            self.assertTrue(decision["rationale"].strip())
            self.assertNotRegex(decision["rationale"], r"[A-Za-z]")
            if decision["plo_code"] is None:
                self.assertEqual([], mapping["plo_codes"])
                self.assertEqual("explicitly_unmapped", mapping["status"])
                continue
            official = next(o for o in reference["outcomes"] if o["code"] == decision["plo_code"])
            self.assertEqual(official["text"], decision["selected_plo_text"])
            self.assertEqual([decision["plo_code"]], mapping["plo_codes"])
            self.assertEqual("mapped", mapping["status"])
            self.assertIn(decision["alignment_type"], {"direct", "supporting_transfer"})
            self.assertIn("ليس استخراجًا من خلية PDF", mapping["evidence"])
        self.assertEqual({1}, set(keys.values()))
        included = {(r["course_code"], r["new_variant_id"]) for r in self.lineage}
        included |= {(u["course_code"], row["variant_id"]) for u in self.review["units"] for row in u["rows"]}
        expected = {
            (code, vid, index, scope_key(scope))
            for code, vid in included
            for index in range(len(effective_extraction(self.variants[code, vid])["clos"]))
            for scope in self.variants[code, vid]["scopes"]
        }
        self.assertEqual(expected, set(keys))
        self.assertEqual(310, len(keys))
        summary = self.decisions["summary"]
        self.assertEqual(len(self.decisions["records"]), summary["clo_scope_rows"])
        self.assertEqual(sum(1 for r in self.decisions["records"] if r["plo_code"]), summary["mapped_clo_scope_rows"])

    def test_recommendations_follow_their_programme_copies(self):
        live = self.outcomes["source_correction_recommendations"]
        old_ids = {r["old_variant_id"] for r in self.lineage}
        self.assertFalse(any(r["variant_id"] in old_ids for r in live))
        children = defaultdict(list)
        for record in self.lineage:
            children[record["old_variant_id"]].append(record)
        for parent in self.snapshot["recommendations"]:
            placed = [r for r in live if r["course_code"] == parent["course_code"] and r["issue_code"] == parent["issue_code"]
                      and r["message"] == parent["message"] and r["variant_id"] in {c["new_variant_id"] for c in children[parent["variant_id"]]}]
            if parent["issue_code"] == "program_specific_plo_links_absent":
                self.assertEqual(1, len(placed))
                child = self.variants[parent["course_code"], placed[0]["variant_id"]]
                self.assertTrue(all(s["program"] in parent["message"] for s in child["scopes"]))
            else:
                self.assertEqual(len(children[parent["variant_id"]]), len(placed))

    def test_printed_code_correction_follows_the_official_programme_pdf(self):
        old = load(ROOT / "assets/course-specifications/shared-program-json-alignment-20261016/alignment-decisions.json")
        for fix in self.review["printed_code_corrections"]:
            self.assertEqual(fix["official_sha256"], hashlib.sha256((ROOT / fix["official_pdf"]).read_bytes()).hexdigest())
            rows = [r for r in old["records"] if r["course_code"] == fix["course_code"] and r["clo_code"] == fix["clo_code"]
                    and scope_key(r["scope"]) == scope_key(fix["scope"])]
            self.assertEqual(1, len(rows))
            self.assertEqual(fix["to"], rows[0]["plo_code"])
            self.assertEqual(fix["from"], rows[0]["printed_code_alignment"]["previous_plo_code"])


if __name__ == "__main__":
    unittest.main()
