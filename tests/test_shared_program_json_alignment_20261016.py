import hashlib
import re
import sys
import unittest
from collections import Counter, defaultdict

from _shared_alignment_test_support import (
    BUNDLE, ROOT, effective_extraction, lineage_records, load,
    previous_context, scope_key, scope_set, trim_variant_to_scopes,
)

sys.path.insert(0, str(ROOT / "scripts"))
from verify_course_outcomes import rebuild_expected_variants


AUTHORIZATION_POLICY = "authorized_program_alignment_revision"
TEXT_POLICY = "verified_extraction_correction_matches_source"
JUDGMENT_POLICY = "verified_reference_correction_pending_source_pdf_update"
COMPLETION_VALUES = {"source_status": "present", "extraction_method": "verified_visual_review", "confidence": "verified"}


class SharedProgramJsonAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(ROOT / "data.json")
        cls.outcomes = load(ROOT / "course-outcomes.json")
        cls.before_data, cls.before_outcomes = previous_context()
        cls.lineage = lineage_records()
        cls.decisions = load(BUNDLE / "alignment-decisions.json")
        cls.references = {
            row["id"]: row
            for row in load(BUNDLE / "program-plo-reference.json")["program_versions"]
        }
        cls.before_variants = {
            (code, variant["variant_id"]): variant
            for code, course in cls.before_outcomes["courses"].items()
            for variant in course["variants"]
        }
        cls.variants = {
            (code, variant["variant_id"]): variant
            for code, course in cls.outcomes["courses"].items()
            for variant in course["variants"]
        }
        cls.completion_doc = load(BUNDLE / "clo-text-completions.json")
        cls.completions = {
            (item["course_code"], item["source_pdf"], item["clo_index"]): item
            for item in cls.completion_doc["records"]
            if item["decision"] == "complete_verbatim"
        }
        cls.applied_completion_rows = 0
        # Authored completions of blank source cells (user: «أكمل النقص اجتهاديا»).
        cls.judgment = {
            (item["course_code"], item["source_pdf"], item["clo_index"]): item
            for item in load(BUNDLE / "gap-completions-by-judgment.json")["texts"]
        }
        cls.applied_judgment_rows = 0
        # Authorised recodes of a printed CLO code («اجتهد فيها بنفسك إما تقليص المخرجات أو التعديل»).
        cls.recodes = {
            (item["variant_id"], item["clo_index"]): item["recode"]
            for item in load(BUNDLE / "pending-cases-decisions.json")["decisions"]
            if item.get("recode")
        }
        cls.applied_recodes = 0

    def test_lineage_is_complete_disjoint_and_has_one_program_per_child(self):
        by_parent = defaultdict(list)
        by_child = Counter()
        for record in self.lineage:
            key = record["course_code"], record["old_variant_id"]
            parent = self.before_variants[key]
            child_key = record["course_code"], record["new_variant_id"]
            child = self.variants[child_key]
            self.assertEqual(parent["scopes"], record["old_scopes"])
            self.assertEqual(child["scopes"], record["new_scopes"])
            self.assertEqual(parent["source_pdf"], record["source_pdf"])
            self.assertEqual(parent["source_sha256"], record["source_sha256"])
            self.assertEqual(child["source_pdf"], record["source_pdf"])
            self.assertEqual(child["source_sha256"], record["source_sha256"])
            self.assertEqual(1, len({(s["program"], s["degree"]) for s in child["scopes"]}))
            by_parent[key].append(child)
            by_child[child_key] += 1
        self.assertEqual({1}, set(by_child.values()))
        self.assertEqual(79, len(by_parent))
        self.assertEqual(172, len(by_child))
        targets = {code for code, _ in by_parent}
        self.assertEqual(54, len(targets))
        self.assertEqual(
            {(code, v["variant_id"]) for code in targets for v in self.before_outcomes["courses"][code]["variants"]},
            set(by_parent),
        )
        self.assertEqual(
            {(code, v["variant_id"]) for code in targets for v in self.outcomes["courses"][code]["variants"]},
            set(by_child),
        )
        for key, children in by_parent.items():
            actual = [scope_key(s) for child in children for s in child["scopes"]]
            self.assertEqual(len(actual), len(set(actual)), key)
            self.assertEqual(scope_set(self.before_variants[key]["scopes"]), set(actual), key)

    def test_source_bytes_raw_extraction_and_all_effective_clo_content_are_preserved(self):
        checked_hashes = set()
        for record in self.lineage:
            key = record["course_code"], record["old_variant_id"]
            parent = self.before_variants[key]
            child = self.variants[record["course_code"], record["new_variant_id"]]
            inherited = trim_variant_to_scopes(parent, child["scopes"])
            with self.subTest(course=key[0], child=child["variant_id"]):
                self.assertEqual(inherited["extracted"], child["extracted"])
                for field in set(parent) - {"variant_id", "scopes", "extracted", "overrides"}:
                    self.assertEqual(parent[field], child[field], field)
                original = effective_extraction(inherited)
                current = effective_extraction(child)
                self.assertEqual(len(original["clos"]), len(current["clos"]))
                completion_fields = set()
                for index, (old_row, new_row) in enumerate(zip(original["clos"], current["clos"])):
                    # Only the verbatim transfers recorded in the follow-up
                    # package may differ from the parent besides the mappings.
                    item = self.completions.get((key[0], child["source_pdf"], index))
                    changed = {"plo_mappings"}
                    recode = self.recodes.get((child["variant_id"], index))
                    if recode:
                        self.applied_recodes += 1
                        self.assertEqual(recode["from"], old_row["code"])
                        self.assertEqual(recode["to"], new_row["code"])
                        changed.add("code")
                        completion_fields.add(f"clos[{index}].code")
                        override = next(o for o in child["overrides"] if o["field"] == f"clos[{index}].code")
                        self.assertEqual(JUDGMENT_POLICY, override["policy"])
                        self.assertTrue(override["evidence"].startswith(f"مراجعة بصرية لملف {child['source_pdf']} المطابق للبصمة SHA256={child['source_sha256']}"))
                    if item:
                        self.applied_completion_rows += 1
                        if recode:
                            self.assertEqual(item["clo_code"], recode["from"])
                        self.assertEqual(recode["to"] if recode else item["clo_code"], new_row["code"])
                        self.assertEqual(item["text_before"], old_row["text"])
                        self.assertEqual(item["text_verbatim"], new_row["text"])
                        for name, value in COMPLETION_VALUES.items():
                            self.assertEqual(value, new_row[name])
                        names = ("text", *COMPLETION_VALUES)
                        changed |= set(names)
                        completion_fields |= {f"clos[{index}].{name}" for name in names}
                        for name in names:
                            override = next(o for o in child["overrides"] if o["field"] == f"clos[{index}].{name}")
                            self.assertEqual(TEXT_POLICY, override["policy"])
                            self.assertIn(f"SHA256={child['source_sha256']}", override["evidence"])
                    authored = self.judgment.get((key[0], child["source_pdf"], index))
                    if authored:
                        # Blank in the PDF and explicitly labelled as not PDF text.
                        self.applied_judgment_rows += 1
                        self.assertIsNone(old_row["text"])
                        self.assertEqual("source_blank", new_row["source_status"])
                        self.assertEqual(authored["clo_code"], new_row["code"])
                        self.assertEqual(authored["text"], new_row["text"])
                        self.assertEqual(authored["assessment"], new_row["assessment"])
                        changed |= {"text", "assessment"}
                        completion_fields |= {f"clos[{index}].text", f"clos[{index}].assessment"}
                        for name in ("text", "assessment"):
                            override = next(o for o in child["overrides"] if o["field"] == f"clos[{index}].{name}")
                            self.assertEqual(JUDGMENT_POLICY, override["policy"])
                            self.assertIn(f"SHA256={child['source_sha256']}", override["evidence"])
                            self.assertIn("وليس نصًا من PDF", override["evidence"])
                    self.assertEqual(
                        {k: v for k, v in old_row.items() if k not in changed},
                        {k: v for k, v in new_row.items() if k not in changed},
                    )
                self.assertEqual(
                    {k: v for k, v in original.items() if k != "clos"},
                    {k: v for k, v in current.items() if k != "clos"},
                )
                new_overrides = [o for o in child["overrides"] if o.get("policy") == AUTHORIZATION_POLICY]
                new_fields = {o["field"] for o in new_overrides}
                self.assertTrue(all(re.fullmatch(r"clos\[\d+\]\.plo_mappings", f) for f in new_fields))
                self.assertTrue(new_fields.isdisjoint(completion_fields))
                skipped = new_fields | completion_fields
                inherited_overrides = [o for o in inherited["overrides"] if o["field"] not in skipped]
                self.assertEqual(inherited_overrides, [o for o in child["overrides"] if o["field"] not in skipped])
            if child["source_pdf"] not in checked_hashes:
                self.assertEqual(child["source_sha256"], hashlib.sha256((ROOT / child["source_pdf"]).read_bytes()).hexdigest())
                checked_hashes.add(child["source_pdf"])
        self.assertTrue(checked_hashes)
        # Every recorded transfer reached each programme child of its source row.
        expected_rows = sum(
            1 for record in self.lineage for item in self.completions.values()
            if item["course_code"] == record["course_code"]
            and self.variants[record["course_code"], record["new_variant_id"]]["source_pdf"] == item["source_pdf"]
        )
        self.assertEqual(expected_rows, self.applied_completion_rows)
        # 19 transfers from the follow-up round (dd616ed) plus 20 from the
        # text-corrections round, which applied the judgment-only readings and
        # the further truncated/merged/garbled rows of the same source tables
        # after two agreeing image readings. Each round is pinned separately so
        # that neither can grow silently.
        rounds = Counter(item.get("round", "followup-2026-10-16") for item in self.completions.values())
        self.assertEqual({"followup-2026-10-16": 19, "text-corrections-2026-10-16": 20}, dict(rounds))
        self.assertEqual(39, len(self.completions))
        # Seven blank source cells completed by authorised judgment, on every child.
        self.assertEqual(7, len(self.judgment))
        # Exactly one authorised recode (2003215-2, Systems plan 38: 3.2 -> 2.3).
        self.assertEqual(1, len(self.recodes))
        self.assertEqual(1, self.applied_recodes)
        self.assertTrue(set(self.judgment).isdisjoint(self.completions))
        self.assertEqual(
            sum(1 for record in self.lineage for item in self.judgment.values()
                if item["course_code"] == record["course_code"]
                and self.variants[record["course_code"], record["new_variant_id"]]["source_pdf"] == item["source_pdf"]),
            self.applied_judgment_rows,
        )
        for item in self.completions.values():
            self.assertEqual(item["source_sha256"], hashlib.sha256((ROOT / item["source_pdf"]).read_bytes()).hexdigest())
            self.assertFalse(re.search(r"[\u0660-\u0669]", item["text_verbatim"]))

    def test_every_effective_mapping_has_exact_scope_and_a_pinned_program_decision(self):
        decision_keys = Counter()
        mapped = unresolved = 0
        checked_program_hashes = set()
        for decision in self.decisions["records"]:
            code, vid, index = decision["course_code"], decision["variant_id"], decision["clo_index"]
            key = code, vid, index, scope_key(decision["scope"])
            decision_keys[key] += 1
            variant = self.variants[code, vid]
            row = effective_extraction(variant)["clos"][index]
            self.assertEqual(decision["clo_code"], row["code"])
            self.assertEqual(decision["clo_text_in_json"], row["text"])
            self.assertIn(decision["scope"], variant["scopes"])
            matches = [m for m in row["plo_mappings"] if m["scope"] == decision["scope"]]
            self.assertEqual(1, len(matches), key)
            mapping = matches[0]
            reference = self.references[decision["program_reference_id"]]
            self.assertIn(decision["scope"], reference["scopes"])
            self.assertEqual(reference["source_pdf"], decision["program_source_pdf"])
            self.assertEqual(reference["source_sha256"], decision["program_source_sha256"])
            if reference["source_pdf"] not in checked_program_hashes:
                self.assertEqual(reference["source_sha256"], hashlib.sha256((ROOT / reference["source_pdf"]).read_bytes()).hexdigest())
                checked_program_hashes.add(reference["source_pdf"])
            self.assertTrue(decision["rationale"].strip())
            override = next(o for o in variant["overrides"] if o["field"] == f"clos[{index}].plo_mappings")
            self.assertEqual(AUTHORIZATION_POLICY, override["policy"])
            for evidence in (override["evidence"], mapping["evidence"]):
                self.assertIn(variant["source_sha256"], evidence)
                self.assertIn(reference["source_sha256"], evidence)
                if decision["plo_code"] is None:
                    self.assertIn("إبقاء الربط غير محسوم وعدم تخمين رمز", evidence)
                else:
                    self.assertIn("ليس استخراجًا من خلية PDF", evidence)
                self.assertIn("alignment-decisions.json", evidence)
            if decision["plo_code"] is None:
                unresolved += 1
                self.assertEqual("unresolved", decision["alignment_type"])
                self.assertEqual([], mapping["plo_codes"])
                # The explicit authorized empty link must win over any older
                # program matrix/repair layer. Raw source mappings remain
                # preserved and independently compared with the parent above.
                self.assertEqual("explicitly_unmapped", mapping["status"])
                continue
            mapped += 1
            official = next(o for o in reference["outcomes"] if o["code"] == decision["plo_code"])
            self.assertEqual(official["text"], decision["selected_plo_text"])
            self.assertEqual(official["source_pages"], decision["selected_plo_pages"])
            self.assertEqual([decision["plo_code"]], mapping["plo_codes"])
            self.assertEqual("mapped", mapping["status"])
            self.assertIn(decision["alignment_type"], {"direct", "supporting_transfer", "preserved_existing"})
            self.assertIn(decision["confidence"], {"high", "medium"})
            self.assertEqual(decision["confidence"], mapping["confidence"])
        self.assertEqual({1}, set(decision_keys.values()))
        expected_keys = {
            (r["course_code"], r["new_variant_id"], i, scope_key(scope))
            for r in self.lineage
            for i in range(len(effective_extraction(self.variants[r["course_code"], r["new_variant_id"]])["clos"]))
            for scope in r["new_scopes"]
        }
        self.assertEqual(expected_keys, set(decision_keys))
        self.assertEqual(self.decisions["summary"]["mapped_clo_scope_rows"], mapped)
        self.assertEqual(self.decisions["summary"]["unresolved_clo_scope_rows"], unresolved)
        self.assertEqual(1590, mapped + unresolved)

    def test_catalogue_and_unrelated_courses_are_unchanged(self):
        targets = {r["course_code"] for r in self.lineage}
        for code, course in self.before_outcomes["courses"].items():
            if code not in targets:
                self.assertEqual(course, self.outcomes["courses"][code], code)
        self.assertEqual(set(self.before_outcomes["courses"]), set(self.outcomes["courses"]))
        for field in set(self.before_data) - {"course_details"}:
            self.assertEqual(self.before_data[field], self.data[field], field)
        self.assertEqual(set(self.before_data["course_details"]), set(self.data["course_details"]))
        before_expected, _ = rebuild_expected_variants(self.before_data)
        after_expected, _ = rebuild_expected_variants(self.data)
        lineage = {(r["course_code"], r["new_variant_id"]): r for r in self.lineage}
        for code, detail in self.before_data["course_details"].items():
            if code not in targets:
                self.assertEqual(detail, self.data["course_details"][code], code)
                continue
            self.assertEqual({k: v for k, v in detail.items() if k != "variants"}, {k: v for k, v in self.data["course_details"][code].items() if k != "variants"})
            before_by_id = {v["variant_id"]: v for v in before_expected[code]}
            for child in after_expected[code]:
                record = lineage[code, child["variant_id"]]
                parent = before_by_id[record["old_variant_id"]]
                self.assertEqual(parent["catalog"], child["catalog"])
                self.assertEqual(parent["source_pdf"], child["source_pdf"])
        self.assertEqual(548, len(self.variants))
        self.assertEqual(737, sum(len(v["scopes"]) for v in self.variants.values()))

    def test_human_rights_has_five_programs_without_cloning_plan_rows_or_pdf(self):
        rights = self.outcomes["courses"]["2003215-2"]["variants"]
        self.assertEqual(5, len(rights))
        self.assertEqual({"الأنظمة", "الدراسات الإسلامية", "الشريعة", "القرآن وعلومه", "القراءات"}, {v["scopes"][0]["program"] for v in rights})
        old_sources = {v["source_pdf"] for v in self.before_outcomes["courses"]["2003215-2"]["variants"]}
        self.assertEqual(old_sources, {v["source_pdf"] for v in rights})
        self.assertEqual(self.before_data["programs"], self.data["programs"])


if __name__ == "__main__":
    unittest.main()
