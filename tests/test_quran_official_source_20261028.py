import hashlib
import json
import re
import unittest
from collections import Counter

from _shared_alignment_test_support import (
    QURAN_OFFICIAL_BUNDLE, ROOT, effective_extraction, load, quran_official_lineage, scope_key,
)


EXTRACTION_FIX = "verified_extraction_correction_matches_source"
AUTHORIZED = "authorized_program_alignment_revision"
BLANKS = ROOT / "assets/course-specifications/shared-course-blank-plo-20260905/manifest.json"
NEW_NOTE = ("تشير نسخة القرآن وعلومه إلى توصيف المقرر الرسمي للبرنامج بروابطه المطبوعة، "
            "وهو الأصل الذي أُخذت منه النسخة المشتركة المفرغة (2026-10-28).")
# Printed link differs from the earlier authorized link; the printed one governs.
# (course, CLO, version) -> (authorized, printed)
DISAGREEMENTS = {
    ("2002110-2", "2.1", "39"): ("م3", "م2"), ("2002110-2", "2.1", "47"): ("م3", "م2"),
    ("2002110-2", "2.2", "39"): ("م3", "م2"), ("2002110-2", "2.2", "47"): ("م3", "م2"),
    ("2002232-2", "2.1", "39"): ("م2", "م3"),
    ("2002250-2", "2.2", "39"): ("م3", "م2"),
    ("2002318-2", "2.1", "39"): ("م2", "م3"), ("2002318-2", "2.1", "47"): ("م2", "م3"),
    ("2002412-2", "1.3", "39"): ("ع2", "ع3"),
    ("2002416-2", "1.1", "39"): ("ع2", "ع3"), ("2002416-2", "1.1", "47"): ("ع2", "ع3"),
    ("2002416-2", "1.2", "39"): ("ع2", "ع3"), ("2002416-2", "1.2", "47"): ("ع2", "ع3"),
    ("2002416-2", "1.3", "39"): ("ع2", "ع3"), ("2002416-2", "1.3", "47"): ("ع2", "ع3"),
    ("2002456-2", "2.1", "39"): ("م2", "م3"),
}


def strip_links(value):
    if isinstance(value, dict):
        return {k: strip_links(v) for k, v in value.items()
                if k not in {"plo_mappings", "document_plo_codes", "warnings"}}
    if isinstance(value, list):
        return [strip_links(v) for v in value]
    return value


class QuranOfficialSource20261028Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(ROOT / "data.json")
        cls.outcomes = load(ROOT / "course-outcomes.json")
        cls.snapshot = load(QURAN_OFFICIAL_BUNDLE / "previous-context.json")
        cls.lineage = quran_official_lineage()
        cls.comparison = load(QURAN_OFFICIAL_BUNDLE / "link-comparison.json")
        cls.live = {(c, v["variant_id"]): v for c, course in cls.outcomes["courses"].items() for v in course["variants"]}
        cls.old = {(c, v["variant_id"]): v for c, course in cls.snapshot["outcome_courses"].items() for v in course["variants"]}

    def test_fourteen_quran_copies_point_to_their_official_source(self):
        blanks = {r["output"]: r for r in load(BLANKS)["records"]}
        self.assertEqual(14, len(self.lineage))
        self.assertEqual(set(self.snapshot["outcome_courses"]), {r["course_code"] for r in self.lineage})
        for record in self.lineage:
            code = record["course_code"]
            old = self.old[code, record["old_variant_id"]]
            new = self.live[code, record["new_variant_id"]]
            with self.subTest(course=code):
                self.assertNotIn((code, record["old_variant_id"]), self.live)
                self.assertEqual(old["scopes"], new["scopes"])
                self.assertEqual({"القرآن وعلومه"}, {s["program"] for s in new["scopes"]})
                self.assertEqual(blanks[old["source_pdf"]]["source"], new["source_pdf"])
                self.assertEqual(blanks[old["source_pdf"]]["source_sha256"], new["source_sha256"])
                self.assertEqual(new["source_sha256"], hashlib.sha256((ROOT / new["source_pdf"]).read_bytes()).hexdigest())
                self.assertEqual(strip_links(old["extracted"]), strip_links(new["extracted"]))
                # Untouched sibling copies of the course stay exactly as they were,
                # apart from the one printed-link follow-up checked below.
                followup = {a["variant_id"]: a for a in load(QURAN_OFFICIAL_BUNDLE / "printed-link-followup.json")["applied"]}
                siblings_before = [v for v in self.snapshot["outcome_courses"][code]["variants"] if v["variant_id"] != old["variant_id"]]
                siblings_after = [v for v in self.outcomes["courses"][code]["variants"] if v["variant_id"] != new["variant_id"]]
                self.assertEqual([v["variant_id"] for v in siblings_before], [v["variant_id"] for v in siblings_after])
                for before, after in zip(siblings_before, siblings_after):
                    if after["variant_id"] in followup:
                        field = f"clos[{followup[after['variant_id']]['clo_index']}].plo_mappings"
                        before = {**before, "overrides": [o for o in before["overrides"] if o["field"] != field]}
                        after = {**after, "overrides": [o for o in after["overrides"] if o["field"] != field]}
                    self.assertEqual(before, after)
                before = self.snapshot["data_course_details"][code]["variants"]
                after = self.data["course_details"][code]["variants"]
                self.assertEqual(len(before), len(after))
                changed = [(b, a) for b, a in zip(before, after) if b != a]
                self.assertEqual(1, len(changed))
                b, a = changed[0]
                self.assertEqual({"pdf_url", "match_note"}, {k for k in a if a[k] != b.get(k)})
                self.assertEqual(new["source_pdf"], a["pdf_url"])
                self.assertTrue(a["match_note"].endswith(NEW_NOTE))
                self.assertNotIn("أُبقيت خلايا رمز ناتج البرنامج فارغة", a["match_note"])
        # Every other course is untouched by this step.
        self.assertEqual(set(self.snapshot["data_course_details"]), set(self.snapshot["outcome_courses"]))

    def test_printed_link_governs_every_row_and_disagreements_are_explicit(self):
        records = self.comparison["records"]
        self.assertEqual(132, len(records))
        self.assertEqual({"printed_matches": 111, "printed_differs": 16, "printed_read_visually_matches": 5},
                         self.comparison["summary"])
        self.assertEqual(Counter(r["comparison"] for r in records), Counter(self.comparison["summary"]))
        found = {}
        keys = Counter()
        for record in records:
            code = record["course_code"]
            new = self.live[code, record["new_variant_id"]]
            old = self.old[code, record["old_variant_id"]]
            keys[code, record["clo_index"], scope_key(record["scope"])] += 1
            authorized = [m for m in effective_extraction(old)["clos"][record["clo_index"]]["plo_mappings"]
                          if m["scope"] == record["scope"]]
            self.assertEqual([record["authorized_plo_codes"]], [m["plo_codes"] for m in authorized])
            row = effective_extraction(new)["clos"][record["clo_index"]]
            self.assertEqual(record["clo_code"], row["code"])
            effective = [m for m in row["plo_mappings"] if m["scope"] == record["scope"]]
            self.assertEqual(1, len(effective))
            self.assertEqual(record["governing_plo_codes"], effective[0]["plo_codes"])
            self.assertEqual(record["printed_plo_codes"], record["governing_plo_codes"])
            self.assertEqual("mapped", effective[0]["status"])
            raw = [m for m in new["extracted"]["clos"][record["clo_index"]]["plo_mappings"] if m["scope"] == record["scope"]][0]
            field = f"clos[{record['clo_index']}].plo_mappings"
            override = [o for o in new["overrides"] if o["field"] == field]
            if record["printed_read_by"] == "extractor":
                self.assertEqual(raw, effective[0])
                self.assertEqual(record["printed_plo_codes"], raw["plo_codes"])
            else:
                self.assertFalse(raw["plo_codes"])
                self.assertNotEqual("mapped", raw["status"])
                self.assertEqual(EXTRACTION_FIX, override[0]["policy"])
                self.assertIn(f"{new['source_pdf']} SHA256={new['source_sha256']}", effective[0]["evidence"])
                self.assertEqual(new["source_sha256"], re.search(r"SHA256=([a-f0-9]{64})", override[0]["evidence"]).group(1))
            if record["comparison"].endswith("differs"):
                found[code, record["clo_code"], record["scope"]["version"]] = (
                    record["authorized_plo_codes"][0], record["printed_plo_codes"][0])
            else:
                self.assertEqual(record["authorized_plo_codes"], record["printed_plo_codes"])
        self.assertEqual(DISAGREEMENTS, found)
        self.assertEqual({1}, set(keys.values()))
        # Every row × scope of every repointed copy is accounted for.
        expected = {(r["course_code"], i, scope_key(s))
                    for r in self.lineage
                    for i in range(len(self.live[r["course_code"], r["new_variant_id"]]["extracted"]["clos"]))
                    for s in self.live[r["course_code"], r["new_variant_id"]]["scopes"]}
        self.assertEqual(expected, set(keys))

    def test_reviewed_overrides_are_carried_and_no_authored_link_remains(self):
        dropped = {(n["course_code"], n["field"]) for n in self.comparison["dropped_overrides"]}
        self.assertEqual({("2002232-2", "clos[5].document_plo_codes"), ("2002456-2", "clos[5].document_plo_codes")}, dropped)
        for record in quran_official_lineage():
            code = record["course_code"]
            old = self.old[code, record["old_variant_id"]]
            new = self.live[code, record["new_variant_id"]]
            with self.subTest(course=code):
                self.assertFalse(any(o["policy"] == AUTHORIZED for o in new["overrides"]))
                self.assertFalse(any(o["field"].endswith("document_plo_codes") for o in new["overrides"]))
                carried = [o for o in old["overrides"] if not o["field"].endswith("plo_mappings")
                           and (code, o["field"]) not in dropped]
                kept = [o for o in new["overrides"] if not o["field"].endswith("plo_mappings")]
                self.assertEqual([(o["field"], o["value"], o["policy"]) for o in carried],
                                 [(o["field"], o["value"], o["policy"]) for o in kept])
                for override in kept:
                    self.assertTrue(override["evidence"].startswith(
                        f"المصدر الحالي: {new['source_pdf']} SHA256={new['source_sha256']}"))
                    self.assertIn(old["source_sha256"], override["evidence"])
                self.assertEqual(effective_extraction(old)["clos"].__len__(), effective_extraction(new)["clos"].__len__())
                for before, after in zip(effective_extraction(old)["clos"], effective_extraction(new)["clos"]):
                    self.assertEqual({k: v for k, v in before.items() if k not in {"plo_mappings", "document_plo_codes"}},
                                     {k: v for k, v in after.items() if k not in {"plo_mappings", "document_plo_codes"}})
                if "source_review" in new:
                    self.assertEqual(new["source_sha256"], new["source_review"]["source_sha256"])
                    self.assertEqual(new["source_pdf"], new["source_review"]["evidence"]["file"])
                    self.assertEqual(new["source_sha256"], new["source_alignment"]["source_sha256"])
                    self.assertFalse(new["source_alignment"]["source_update_recommended"])

    def test_printed_link_followup_on_the_shared_quran_qiraat_v47_copy(self):
        record = load(QURAN_OFFICIAL_BUNDLE / "printed-link-followup.json")
        self.assertEqual(1, len(record["applied"]))
        item = record["applied"][0]
        variant = self.live[item["course_code"], item["variant_id"]]
        self.assertEqual(item["source_sha256"], hashlib.sha256((ROOT / variant["source_pdf"]).read_bytes()).hexdigest())
        self.assertEqual(item["corroboration"]["sha256"],
                         hashlib.sha256((ROOT / item["corroboration"]["pdf"]).read_bytes()).hexdigest())
        reviewed = next(o for o in variant["overrides"] if o["field"] == "clos")["value"][item["clo_index"]]
        self.assertEqual([item["printed_plo_code"]], reviewed["document_plo_codes"])
        row = effective_extraction(variant)["clos"][item["clo_index"]]
        self.assertEqual(item["clo_code"], row["code"])
        self.assertEqual([[item["printed_plo_code"]]], [m["plo_codes"] for m in row["plo_mappings"]])
        override = next(o for o in variant["overrides"] if o["field"] == f"clos[{item['clo_index']}].plo_mappings")
        self.assertEqual(AUTHORIZED, override["policy"])
        self.assertEqual(variant["source_sha256"], re.search(r"SHA256=([a-f0-9]{64})", override["evidence"]).group(1))
        self.assertEqual([item["previous_authorized_plo_code"]], item["previous_override"]["value"][0]["plo_codes"])
        # The previous authorized link is the one frozen before this step.
        old = next(v for v in self.snapshot["outcome_courses"][item["course_code"]]["variants"] if v["variant_id"] == item["variant_id"])
        self.assertIn(item["previous_override"], old["overrides"])
        # Rows left alone: printed code of a five-programme college requirement.
        for left in record["not_applied"]:
            variant = next(v for (c, vid), v in self.live.items() if c == left["course_code"] and vid.startswith(left["variant_id"]))
            for clo in left["clo_codes"]:
                row = next(r for r in effective_extraction(variant)["clos"] if r["code"] == clo)
                self.assertEqual([left["printed"]], row["document_plo_codes"])
                self.assertEqual([[left["authorized"]]], [m["plo_codes"] for m in row["plo_mappings"]])

    def test_recommendations_and_source_ledger_follow_the_repointing(self):
        retired = load(QURAN_OFFICIAL_BUNDLE / "superseded-source-recommendations.json")["records"]
        self.assertEqual(self.snapshot["recommendations"], retired)
        self.assertEqual({"2002232-2", "2002456-2"}, {r["course_code"] for r in retired})
        live_ids = {r["id"] for r in self.outcomes["source_correction_recommendations"]}
        self.assertTrue(live_ids.isdisjoint({r["id"] for r in retired}))
        active = {v["source_pdf"] for v in self.live.values()}
        excluded = {x["source_pdf"]: x for x in self.outcomes["excluded_sources"]}
        for record in self.lineage:
            self.assertIn(record["new_source_pdf"], active)
            self.assertNotIn(record["new_source_pdf"], excluded)
            self.assertTrue(record["old_source_pdf"] in active or record["old_source_pdf"] in excluded)
        selection = load(QURAN_OFFICIAL_BUNDLE / "selection.json")
        self.assertEqual(sorted(r["course_code"] for r in self.lineage), selection["selected"])


if __name__ == "__main__":
    unittest.main()
