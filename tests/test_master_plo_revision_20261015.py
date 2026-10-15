import copy
import hashlib
import json
from pathlib import Path
import unittest
from zipfile import ZipFile
from lxml import etree
from scripts.verify_course_outcomes import ErrorCollector, validate_overrides

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets/course-specifications/quranic-master-plo-update-20261015"
def read(path): return json.loads(path.read_text(encoding="utf-8"))

class MasterPLORevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = read(BUNDLE / 'alignment-decisions.json')
        cls.ref = read(BUNDLE / 'program-reference.json')
        cls.before = read(BUNDLE / 'previous-context.json')
        cls.data = read(ROOT / 'data.json')
        # Verify the preserved edition's source records after the later CLO revision.
        cls.outcomes = {'courses': read(ROOT / 'assets/course-specifications/quranic-master-single-domain-20261015/previous-context.json')['course_outcomes']}

    def test_exact_proposed_outcomes_with_operative_curriculum(self):
        proposal = read(ROOT / 'assets/course-specifications/quranic-master-operative-2023/proposed-program-history.json')
        self.assertEqual(proposal['program']['program_details']['learning_outcomes'], self.cfg['outcomes'])
        current = next(p for p in self.data['programs'] if p['name'] == self.cfg['program'])
        self.assertEqual(self.before['program']['courses'], current['courses'])
        self.assertEqual((14, 34), (len(current['courses']), sum(c['hours'] for c in current['courses'])))
        self.assertEqual(self.cfg['outcomes'], current['program_details']['learning_outcomes'])

    def test_every_matrix_link_has_a_specific_course_outcome_and_mastery(self):
        courses = {c['code']: c for c in self.cfg['courses']}
        self.assertEqual(45, len(self.ref['program_matrix']))
        for row in self.ref['program_matrix']:
            self.assertTrue(any(clo['text'] and row['plo_code'] in clo['new_plo_codes'] for clo in courses[row['course_code']]['clos']))
        for plo in self.cfg['outcomes']:
            mastered = {r['course_code'] for r in self.ref['program_matrix'] if r['plo_code'] == plo['code'] and r['classification'] == 3}
            self.assertEqual(set(self.cfg['mastery'][plo['code']]), mastered)
            self.assertIn(len(mastered), (2, 3))

    def test_course_source_and_other_scopes_preserved(self):
        for old in self.before['course_variants']:
            variant = next(v for v in self.outcomes['courses'][old['course_code']]['variants'] if v['variant_id'] == old['variant']['variant_id'])
            self.assertEqual(old['variant']['extracted'], variant['extracted'])
            self.assertEqual(old['variant']['source_sha256'], variant['source_sha256'])
            self.assertEqual(old['variant']['source_sha256'], hashlib.sha256((ROOT / variant['source_pdf']).read_bytes()).hexdigest())
            for override in variant['overrides']:
                if override.get('policy') != 'authorized_program_alignment_revision': continue
                index = int(override['field'].split('[')[1].split(']')[0])
                old_mappings = old['variant']['extracted']['clos'][index]['plo_mappings']
                for original, new in zip(old_mappings, override['value']):
                    if original['scope']['program'] != self.cfg['program']:
                        self.assertEqual(original, new)

    def test_file_hashes_pdf_sources_and_approval(self):
        manifest = read(BUNDLE / 'manifest.json')
        for row in manifest['files']:
            self.assertEqual(row['sha256'], hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest())
        self.assertFalse(manifest['institutional_approval_claimed'])
        from docx import Document
        doc = Document(BUNDLE / 'program-specification.docx')
        self.assertEqual('', doc.tables[27].rows[1].cells[1].text)
        self.assertEqual('', doc.tables[27].rows[2].cells[1].text)
        self.assertEqual(self.cfg['measurement_policy']['direct_target'], .8)
        self.assertEqual(self.cfg['measurement_policy']['indirect_target'], 4)

    def test_authorized_policy_is_scoped_not_a_generic_source_repair(self):
        old = self.before['course_variants'][0]
        v = next(v for v in self.outcomes['courses'][old['course_code']]['variants'] if v['variant_id'] == old['variant']['variant_id'])
        override = next(o for o in v['overrides'] if o.get('policy') == 'authorized_program_alignment_revision')
        e = ErrorCollector(); validate_overrides([override], v['extracted'], 'review', e)
        self.assertEqual(0, e.count, e.messages)
        bad = copy.deepcopy(override); bad['field'] = 'clos[0].text'; bad['value'] = 'invented'
        e = ErrorCollector(); validate_overrides([bad], v['extracted'], 'review', e)
        self.assertGreater(e.count, 0)
        bad = copy.deepcopy(override); bad['evidence'] = 'unbound'
        e = ErrorCollector(); validate_overrides([bad], v['extracted'], 'review', e)
        self.assertGreater(e.count, 0)
