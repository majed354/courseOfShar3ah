from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_institutional_recovery_20260911 as builder  # noqa: E402


class InstitutionalRecovery20260911Tests(unittest.TestCase):
    def test_published_bundle_matches_builder_contract(self) -> None:
        bundle = builder.DEFAULT_OUTPUT
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        entries = json.loads((bundle / "data-entries.json").read_text(encoding="utf-8"))
        self.assertEqual(7, manifest["counts"]["imported_course_identities"])
        self.assertEqual(4, manifest["counts"]["identity_completed_sources"])
        self.assertEqual(10, manifest["counts"]["linked_plan_appearances"])
        self.assertEqual({item["code"] for item in builder.COURSES}, set(entries["course_details"]))

        for record in manifest["records"]:
            path = bundle / f"{record['code']}.pdf"
            self.assertTrue(path.is_file())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(record["output_sha256"], digest)
            self.assertEqual(record["page_count"], len(PdfReader(str(path)).pages))
            subprocess.run(["qpdf", "--check", str(path)], check=True, capture_output=True)

    def test_apply_script_accepts_bundle_and_rejects_second_application(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data.json"
            target.write_bytes((ROOT / "data.json").read_bytes())
            original = json.loads(target.read_text(encoding="utf-8"))
            for code in builder.COURSES:
                original["course_details"].pop(code["code"], None)
            target.write_text(
                json.dumps(original, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(ROOT / "scripts" / "apply_institutional_recovery_20260911.py"),
                "--data",
                str(target),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            updated = json.loads(target.read_text(encoding="utf-8"))
            self.assertTrue({item["code"] for item in builder.COURSES} <= set(updated["course_details"]))
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(0, repeated.returncode)
            self.assertIn("Refusing to replace", repeated.stderr)


if __name__ == "__main__":
    unittest.main()
