import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.verify_course_outcomes import ErrorCollector, validate_single_domain_policy
from _shared_alignment_test_support import lineage_records, previous_context, specialized_course_codes

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / 'assets/course-specifications/quranic-doctorate-single-domain-20261016'


def read(p):
    return json.loads(p.read_text())


def effective(v):
    rows = copy.deepcopy(v['extracted']['clos'])
    for override in v['overrides']:
        if override['field'] == 'clos':
            rows = override['value']
    return rows


class DoctoratePublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = read(B/'revision-decisions.json')
        cls.ref = read(B/'program-reference.json')
        cls.before = read(B/'previous-context.json')
        cls.out = read(ROOT/'course-outcomes.json')
        cls.data = read(ROOT/'data.json')

    def test_official_curriculum_and_zero_credit_exam_preserved(self):
        p = next(x for x in self.data['programs'] if x['name'] == 'الدراسات القرآنية' and x['degree'] == 'دكتوراه')
        self.assertEqual(self.before['program']['courses'], p['courses'])
        self.assertEqual((6,60),(len(p['courses']),sum(x['hours'] for x in p['courses'])))
        self.assertEqual(0,next(x['hours'] for x in p['courses'] if x['code']=='20029999-0'))
        self.assertEqual(self.cfg['program_pdf_sha256'],p['program_details']['specification_source_sha256'])
        self.assertEqual([x['text'] for x in self.cfg['outcomes']],[x['text'] for x in p['program_details']['learning_outcomes']])

    def test_source_files_hashes_and_unclaimed_approval(self):
        m=read(B/'manifest.json')
        for f in m['files']:
            self.assertEqual(f['sha256'],hashlib.sha256((ROOT/f['path']).read_bytes()).hexdigest(),f['path'])
        self.assertFalse(m['historical_grades_changed'])
        self.assertFalse(m['institutional_approval_claimed'])
        self.assertEqual('',self.cfg['academic_approval']['session'])
        self.assertEqual('',self.cfg['academic_approval']['date'])

    def test_all_course_links_match_source_and_domain(self):
        e=ErrorCollector();validate_single_domain_policy(self.out,e);self.assertEqual([],e.messages)
        for c in self.cfg['courses']:
            v=next(v for v in self.out['courses'][c['code']]['variants'] if v['source_sha256']==c['pdf_sha256'])
            rows=effective(v);self.assertEqual(6,len(rows))
            for x,y in zip(rows,c['clos']):
                self.assertEqual((y['code'],y['text'],[y['plo_code']]),(x['code'],x['text'],x['document_plo_codes']))
                self.assertEqual([y['plo_code']],x['plo_mappings'][0]['plo_codes'])
                self.assertEqual('1',x['plo_mappings'][0]['scope']['version'])
                self.assertTrue(x['assessment'])

    def test_matrix_has_supported_mastery_and_q2_coverage(self):
        matrix=self.ref['program_matrix'];clo=self.ref['course_outcomes']
        self.assertEqual((34,20,30),(len(matrix),sum(x['classification']==3 for x in matrix),len(clo)))
        pairs={(x['course_code'],x['plo_code']) for x in clo}
        for row in matrix:
            if row['classification']==3:self.assertIn((row['course_code'],row['plo_code']),pairs)
        for o in self.cfg['outcomes']:
            self.assertGreaterEqual(sum(x['plo_code']==o['code'] and x['classification']==3 for x in matrix),2)
        self.assertEqual({'2002706-3','2002708-3','2002709-48'},{x['course_code'] for x in matrix if x['plo_code']=='ق2' and x['classification']==3})

    def test_unrelated_contexts_unchanged_and_predecessors_archived(self):
        import subprocess
        baseline=json.loads(subprocess.check_output(['git','show',self.before['baseline_commit']+':course-outcomes.json'],cwd=ROOT))
        _, before_specialization = previous_context()
        specialized_codes = specialized_course_codes()
        for code,record in baseline['courses'].items():
            if code not in self.before['course_outcomes']:
                # Only the later authorized 54-course specialization is read
                # from its frozen predecessor here. Its live children are
                # checked individually by the specialization contract.
                current = before_specialization['courses'][code] if code in specialized_codes else self.out['courses'][code]
                self.assertEqual(record,current,code)
            else:
                self.assertEqual(record,self.before['course_outcomes'][code])
                for prior in record['variants']:
                    self.assertTrue((ROOT/prior['source_pdf']).is_file())
                    self.assertEqual(prior['source_sha256'],hashlib.sha256((ROOT/prior['source_pdf']).read_bytes()).hexdigest())
                    self.assertIn(prior['source_pdf'],{x['source_pdf'] for x in self.out['excluded_sources']})


if __name__ == '__main__':
    unittest.main()
