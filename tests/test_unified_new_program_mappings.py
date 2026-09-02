import hashlib
import json
import sys
import unittest
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "assets" / "course-specifications" / "unified-new-program-mappings-20260901.json"
sys.path.insert(0, str(ROOT / "scripts"))
from apply_unified_new_program_mappings import discover_clos


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def variant_scopes(variant):
    if isinstance(variant.get("scopes"), list):
        return variant["scopes"]
    if isinstance(variant.get("scope"), dict):
        return [variant["scope"]]
    return []


class UnifiedNewProgramMappingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))

    def test_manifest_counts_and_current_hashes(self):
        self.assertEqual(23, self.manifest["file_count"])
        self.assertEqual(182, self.manifest["mapping_cell_count"])
        self.assertEqual(5, self.manifest["data_changes"]["rerouted_variants"])
        self.assertEqual(28, self.manifest["data_changes"]["unified_variants"])
        self.assertEqual(182, sum(len(record["edits"]) for record in self.manifest["records"]))
        for record in self.manifest["records"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(record["output_sha256"], sha256(path), record["path"])

    def test_every_mapping_has_one_line_per_new_program(self):
        for record in self.manifest["records"]:
            programs = record["programs"]
            self.assertGreaterEqual(len(programs), 2)
            self.assertEqual(len(programs), len(set(programs)))
            for edit in record["edits"]:
                lines = edit["mapping_to"].splitlines()
                self.assertEqual(len(programs), len(lines), (record["course_key"], edit["clo"]))
                self.assertEqual(programs, list(edit["per_program"]), (record["course_key"], edit["clo"]))
                self.assertEqual(
                    [f"{program}: {edit['per_program'][program]}" for program in programs],
                    lines,
                )
                self.assertNotIn("قديمة", edit["mapping_to"])
                self.assertNotIn("القديمة", edit["mapping_to"])

    def test_program_mapping_font_is_legible_and_audited(self):
        for record in self.manifest["records"]:
            self.assertEqual(
                "2026-09-02-legible-10.7pt",
                record.get("mapping_style_version"),
                record["course_key"],
            )
            for edit in record["edits"]:
                self.assertEqual(10.7, edit.get("mapping_font_size_pt"))
                self.assertGreater(edit.get("mapping_effective_font_size_pt", 0), 0)

        pictured = next(
            record for record in self.manifest["records"]
            if record["course_key"] == "2002252-2"
        )
        self.assertTrue(pictured["edits"])
        for edit in pictured["edits"]:
            self.assertEqual(1.0, edit["mapping_scale"], edit["clo"])
            self.assertEqual(10.7, edit["mapping_effective_font_size_pt"], edit["clo"])

    def test_every_discoverable_clo_row_was_rewritten(self):
        for record in self.manifest["records"]:
            with pymupdf.open(ROOT / record["path"]) as document:
                discovered = discover_clos(document)
            self.assertEqual(discovered, [edit["clo"] for edit in record["edits"]], record["course_key"])

    def test_shared_new_scopes_point_to_the_single_modified_file(self):
        variants_by_pdf = {}
        for detail in self.data["course_details"].values():
            for variant in detail.get("variants", []):
                variants_by_pdf.setdefault(variant.get("pdf_url", ""), []).append(variant)

        for record in self.manifest["records"]:
            new_programs = set()
            for variant in variants_by_pdf.get(record["path"], []):
                for scope in variant_scopes(variant):
                    if scope.get("degree") == "بكالوريوس" and scope.get("plan_type") == "جديدة":
                        new_programs.add(scope.get("program"))
            self.assertEqual(set(record["programs"]), new_programs, record["course_key"])

    def test_no_program_specific_copy_is_linked_for_unified_sources(self):
        prior_manifest = json.loads(
            (ROOT / "assets/course-specifications/clo-plo-corrections-20260901/manifest.json").read_text(encoding="utf-8")
        )
        unified_sources = {record["path"] for record in self.manifest["records"]}
        superseded_outputs = {
            record["output"]
            for record in prior_manifest["records"]
            if record["source"] in unified_sources
        }
        linked = {
            variant.get("pdf_url")
            for detail in self.data["course_details"].values()
            for variant in detail.get("variants", [])
        }
        self.assertTrue(superseded_outputs)
        self.assertTrue(superseded_outputs.isdisjoint(linked))


if __name__ == "__main__":
    unittest.main()
