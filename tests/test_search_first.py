import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SearchFirstExperienceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = r"""
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync('index.html', 'utf8');
const inline = html.split('    <script>')[1].split('    </script>')[0].replace('        loadData();', '');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '', textContent: '', hidden: false,
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, querySelectorAll() { return []; }, focus() {} });
  return elements.get(id);
}
const context = { console, clearTimeout, setTimeout,
  document: { getElementById: element, addEventListener() {}, querySelectorAll() { return []; } },
  window: { addEventListener() {} },
  dataset: JSON.parse(fs.readFileSync('data.json', 'utf8')) };
vm.createContext(context);
vm.runInContext(inline, context);
vm.runInContext('programsData = dataset; rebuildCourseIndexes(); performSearch();', context);
const read = code => vm.runInContext(code, context);
const result = { initial: { total: read('lastSearchResults.length'),
  cards: element('resultsContainer').innerHTML.split('class="result-item ').length - 1,
  moreHidden: element('showMoreResults').hidden } };
element('searchInput').value = '2002110-2';
read('performSearch()');
result.exactFirst = read('lastSearchResults[0].code');
element('searchInput').value = '';
element('searchProgramFilter').value = 'القراءات';
element('searchDegreeFilter').value = 'بكالوريوس';
read('performSearch()');
result.scoped = read('lastSearchResults.every(r => !r.catalog_only && r.occurrence_refs.length && r.occurrence_refs.every(o => o.program === "القراءات" && o.degree === "بكالوريوس"))');
result.scopedCount = read('lastSearchResults.length');
element('searchProgramFilter').value = 'برنامج غير موجود';
read('performSearch()');
result.incompatible = read('lastSearchResults.length');
read('clearSearch(); showMoreSearchResults();');
result.afterClear = { program: element('searchProgramFilter').value, degree: element('searchDegreeFilter').value,
  total: read('lastSearchResults.length'), cards: element('resultsContainer').innerHTML.split('class="result-item ').length - 1,
  clearHidden: element('clearSearchButton').hidden,
  identities: read('new Set(lastSearchResults.map(r => getCourseIdentityKey(r.code, r.name))).size') };
process.stdout.write(JSON.stringify(result));
"""
        cls.result = json.loads(subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True))

    def test_first_visit_shows_a_bounded_course_selection(self):
        self.assertGreater(self.result["initial"]["total"], 6)
        self.assertEqual(self.result["initial"]["cards"], 6)
        self.assertFalse(self.result["initial"]["moreHidden"])

    def test_exact_code_precedes_other_matches(self):
        self.assertEqual(self.result["exactFirst"], "2002110-2")

    def test_filters_preserve_program_scope_and_do_not_fall_back_to_catalog(self):
        self.assertTrue(self.result["scoped"])
        self.assertGreater(self.result["scopedCount"], 0)
        self.assertEqual(self.result["incompatible"], 0)

    def test_reset_and_more_restore_discovery_without_duplicate_identities(self):
        after = self.result["afterClear"]
        self.assertEqual((after["program"], after["degree"]), ("", ""))
        self.assertEqual(after["cards"], 12)
        self.assertEqual(after["total"], self.result["initial"]["total"])
        self.assertEqual(after["identities"], after["total"])
        self.assertTrue(after["clearHidden"])
