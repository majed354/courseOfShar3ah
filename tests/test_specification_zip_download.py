"""Check the public archive layout and ZIP compatibility."""

import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SpecificationZipDownloadTests(unittest.TestCase):
    def test_transient_pdf_download_is_retried(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        start = html.index("        async function fetchSpecificationPdf(")
        end = html.index("        async function downloadAllProgramsSeparately(", start)
        node = r"""
const vm = require('vm');
let calls = 0;
const context = {
  AbortController, DOMException, TypeError,
  fetch: async () => {
    calls += 1;
    if (calls === 1) throw new TypeError('connection lost');
    return { ok: true, arrayBuffer: async () => new TextEncoder().encode('%PDF-test').buffer };
  },
  setTimeout: callback => callback(),
  showSpecificationDownloadStatus() {},
};
vm.createContext(context);
vm.runInContext(process.argv[1], context);
(async () => {
  const bytes = await context.fetchSpecificationPdf({ url: 'sample.pdf', path: 'sample.pdf' }, new AbortController().signal);
  process.stdout.write(JSON.stringify({ calls, valid: bytes.length === 9 }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        output = subprocess.check_output(["node", "-e", node, html[start:end]], cwd=ROOT, text=True)
        self.assertEqual(json.loads(output), {"calls": 2, "valid": True})

    def test_batch_resumes_after_a_program_fails(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        script = html.split("    <script>", 1)[1].split("    </script>", 1)[0]
        script = script.replace("        loadData();", "")
        node = r"""
const fs = require('fs');
const vm = require('vm');
const store = new Map();
const noopClassList = { add() {}, remove() {} };
const button = { disabled: false, textContent: '' };
const cancel = { hidden: false };
const status = { classList: noopClassList };
const message = { textContent: '', addEventListener() {} };
const context = {
  console, AbortController,
  setTimeout: () => 1, clearTimeout() {},
  sessionStorage: {
    getItem: key => store.get(key) || null,
    setItem: (key, value) => store.set(key, value),
    removeItem: key => store.delete(key),
  },
  document: {
    getElementById: id => id === 'allSpecificationZipsButton' ? button
      : id === 'specificationDownloadStatus' ? status : message,
    querySelectorAll: () => [button],
    querySelector: () => cancel,
    addEventListener() {},
  },
  window: { addEventListener() {} },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
vm.runInContext('programsData = { programs: [] }', context);
const groups = ['أ', 'ب', 'ج'].map((label, index) => ({
  label,
  programs: [{ id: index, plan_type: 'جديدة', version: '1', courses: [] }],
  archive: { entries: [], unavailable: [] },
}));
context.groupProgramsForSpecificationDownload = () => groups;
const calls = [];
let failOnce = true;
context.downloadSpecificationZip = async (_index, options) => {
  calls.push(options.progressLabel[0]);
  if (options.progressLabel.startsWith('ب') && failOnce) {
    failOnce = false;
    return false;
  }
  return true;
};
(async () => {
  await context.downloadAllProgramsSeparately();
  const afterFailure = { calls: [...calls], button: button.textContent, saved: !!store.size };
  await context.downloadAllProgramsSeparately();
  process.stdout.write(JSON.stringify({ afterFailure, calls, saved: !!store.size }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        with tempfile.TemporaryDirectory() as directory:
            js_path = Path(directory) / "inline.js"
            js_path.write_text(script, encoding="utf-8")
            output = subprocess.check_output(["node", "-e", node, str(js_path)], cwd=ROOT, text=True)
        result = json.loads(output)
        self.assertEqual(result["afterFailure"]["calls"], ["أ", "ب"])
        self.assertTrue(result["afterFailure"]["saved"])
        self.assertIn("(2)", result["afterFailure"]["button"])
        self.assertEqual(result["calls"], ["أ", "ب", "ب", "ج"])
        self.assertFalse(result["saved"])

    def test_archive_uses_plan_scopes_and_level_folders(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        script = html.split("    <script>", 1)[1].split("    </script>", 1)[0]
        script = script.replace("        loadData();", "")
        node = r"""
const fs = require('fs');
const vm = require('vm');
const htmlScript = fs.readFileSync(process.argv[1], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const stub = { addEventListener() {} };
const context = {
  console,
  document: { getElementById: () => stub, addEventListener() {} },
  window: { addEventListener() {} },
};
vm.createContext(context);
vm.runInContext(htmlScript, context);
vm.runInContext('programsData = archiveData', Object.assign(context, { archiveData: data }));
const old = data.programs.find(p => p.name === 'القرآن وعلومه' && p.plan_type === 'قديمة');
const newer = data.programs.find(p => p.name === 'القرآن وعلومه' && p.plan_type === 'جديدة');
const result = {
  old: context.buildSpecificationArchive([old]),
  newer: context.buildSpecificationArchive([newer]),
  all: context.buildSpecificationArchive(data.programs),
  groups: context.groupProgramsForSpecificationDownload(data.programs).map(group => ({
    label: group.label,
    plans: group.programs.map(program => `${program.plan_type}-${program.version}`),
    pdfCount: group.archive.entries.length,
    missingCount: group.archive.unavailable.length,
  })),
};
process.stdout.write(JSON.stringify(result));
"""
        with tempfile.TemporaryDirectory() as directory:
            js_path = Path(directory) / "inline.js"
            js_path.write_text(script, encoding="utf-8")
            output = subprocess.check_output(
                ["node", "-e", node, str(js_path), str(ROOT / "data.json")],
                cwd=ROOT,
                text=True,
            )
        result = json.loads(output)
        old_paths = [entry["path"] for entry in result["old"]["entries"]]
        new_paths = [entry["path"] for entry in result["newer"]["entries"]]
        all_paths = [entry["path"] for entry in result["all"]["entries"]]

        self.assertTrue(any("الخطة قديمة (إصدار 39)/المستوى الأول/" in p for p in old_paths))
        self.assertTrue(any("الخطة جديدة (إصدار 47)/المستوى الأول/" in p for p in new_paths))
        self.assertTrue(any("2002115-2" in p for p in old_paths))
        self.assertFalse(any("2002115-2" in p for p in new_paths))
        self.assertEqual(len(all_paths), len(set(all_paths)))
        self.assertGreater(len(all_paths), len(old_paths) + len(new_paths))
        self.assertEqual(len(result["groups"]), 15)
        self.assertEqual(sum(group["pdfCount"] for group in result["groups"]), len(all_paths))
        quran = next(group for group in result["groups"] if group["label"] == "القرآن وعلومه - بكالوريوس")
        self.assertEqual(set(quran["plans"]), {"قديمة-39", "جديدة-47"})
        self.assertTrue(all((ROOT / entry["url"]).is_file() for entry in result["all"]["entries"]))
        self.assertIn('تنزيل توصيفات كل برنامج على حدة ZIP', html)
        self.assertIn('تنزيل توصيفات مقررات هذه الخطة ZIP', html)

    def test_zip_writer_produces_valid_arabic_zip(self):
        node = r"""
const fs = require('fs');
const { ZipStore } = require(process.argv[1]);
(async () => {
  const chunks = [];
  const zip = new ZipStore({ write: async b => chunks.push(b), close: async () => {} });
  await zip.add('القرآن وعلومه/الخطة قديمة/المستوى الأول/مقرر.pdf', new Uint8Array([37,80,68,70,45,49]));
  await zip.add('اقرأني.txt', 'ملفات التوصيف');
  await zip.close();
  fs.writeFileSync(process.argv[2], Buffer.concat(chunks));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        with tempfile.TemporaryDirectory() as directory:
            zip_path = Path(directory) / "archive.zip"
            subprocess.run(
                ["node", "-e", node, str(ROOT / "assets/js/zip-store.js"), str(zip_path)],
                cwd=ROOT,
                check=True,
            )
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), 2)
                self.assertEqual(archive.read("اقرأني.txt").decode(), "ملفات التوصيف")
                self.assertTrue(any("المستوى الأول" in name for name in archive.namelist()))


if __name__ == "__main__":
    unittest.main()
