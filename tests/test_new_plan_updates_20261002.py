import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from update_new_plan_specifications_20261002 import trim_mappings, scope_key
from update_specialty_missing_markdown import calculate


def load(path):
    return json.loads(path.read_text())


class NewPlanUpdatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=ROOT/'assets/course-specifications/new-plan-updates-20261002'
        cls.manifest=load(cls.bundle/'manifest.json')
        cls.data=load(ROOT/'data.json')
        cls.outcomes=load(ROOT/'course-outcomes.json')
        cls.successors=load(cls.bundle/'retained-variant-successors.json')
        cls.baseline=json.loads(subprocess.run(['git','show',cls.manifest['baseline_commit']+':course-outcomes.json'],cwd=ROOT,capture_output=True,text=True,check=True).stdout)

    def variant(self,record):
        return next(v for v in self.outcomes['courses'][record['code']]['variants'] if v['source_pdf']==record['output'])

    def test_all_publications_are_hash_pinned_and_body_pages_are_unchanged(self):
        self.assertEqual(13,len(self.manifest['records']))
        self.assertEqual(96,sum(r['page_count'] for r in self.manifest['records']))
        self.assertEqual({'publication_pdfs':13,'raw_sources':12,'replaced_contexts':26,'added_contexts':2},self.manifest['counts'])
        for r in self.manifest['records']:
            path=ROOT/r['output']
            self.assertEqual(r['output_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            with pymupdf.open(path) as document:
                actual=[hashlib.sha256(p.get_pixmap().samples).hexdigest() for p in list(document)[1:]]
                self.assertEqual(r['body_page_render_sha256'],actual)
            self.assertEqual(r['output_sha256'],self.variant(r)['source_sha256'])

    def test_published_names_codes_hours_and_scopes_match_approved_plans(self):
        for r in self.manifest['records']:
            detail=next(v for v in self.data['course_details'][r['code']]['variants'] if v['pdf_url']==r['output'])
            self.assertEqual(r['code'],detail['specification_code'])
            self.assertEqual(r['title'],detail['title'])
            self.assertEqual(r['scopes'],detail['scopes'])
            for row in r['plan_rows']:
                program=next(p for p in self.data['programs'] if (p['name'],p['degree'],p['plan_type'],str(p['version']))==scope_key(row['scope']))
                current=next(c for c in program['courses'] if c['code']==r['code'])
                self.assertEqual({k:v for k,v in row['course'].items() if k!='pdf_url'},{k:v for k,v in current.items() if k!='pdf_url'})
                if 'pdf_url' in current:
                    self.assertEqual(r['output'],current['pdf_url'])
                self.assertEqual(int(r['code'].split('-')[1]),row['course']['hours'])

    def test_effective_rows_and_assessment_are_from_new_hash_pinned_reviews(self):
        for r in self.manifest['records']:
            v=self.variant(r)
            values={o['field']:o['value'] for o in v['overrides']}
            self.assertEqual(6,len(values['clos']))
            self.assertTrue(all(row['text'] and row['assessment'] for row in values['clos']))
            self.assertEqual(100,sum(row['weight'] for row in values['assessment_plan']))
            self.assertEqual('matches_source_pdf',v['source_alignment']['status'])
            self.assertTrue(all(r['output_sha256'] in o['evidence'] for o in v['overrides']))
            for row in values['clos']:
                for mapping in row['plo_mappings']:
                    self.assertIn(mapping['scope'],v['scopes'])
                    # None of these generic source cells labels a program.
                    self.assertFalse(mapping['plo_codes'])
                    self.assertNotEqual('mapped',mapping['status'])
            if r['code'] in {'20021203-2','2002210-2'}:
                self.assertTrue(all(m['status']=='explicitly_unmapped' for row in values['clos'] for m in row['plo_mappings']))

    def test_unchanged_sources_and_historical_review_layers_are_preserved(self):
        target_codes={r['code'] for r in self.manifest['records']}
        for code,course in self.baseline['courses'].items():
            if code not in target_codes:
                self.assertEqual(course,self.outcomes['courses'][code],code)
            for prior in course['variants']:
                if prior['variant_id'] not in self.successors:
                    continue
                current=next(v for v in self.outcomes['courses'][code]['variants'] if v['variant_id']==self.successors[prior['variant_id']])
                expected=trim_mappings(copy.deepcopy(prior),current['scopes'])
                expected['variant_id']=current['variant_id']
                expected['scopes']=current['scopes']
                self.assertEqual(expected,current)
                self.assertTrue(all(s['plan_type']=='قديمة' for s in current['scopes']))

    def test_only_two_missing_contexts_are_added(self):
        required,available,missing,_=calculate()
        self.assertEqual((756,657,99,85),(required,available,required-available,len(missing)))
        self.assertEqual({'2002352-2','2002310-3'},{r['code'] for r in self.manifest['records'] if r['action']=='add'})

    def test_companion_word_does_not_replace_newer_miracle_clo_text(self):
        r=next(r for r in self.manifest['records'] if r['code']=='2002456-2')
        rows=next(o['value'] for o in self.variant(r)['overrides'] if o['field']=='clos')
        self.assertEqual('أن يشرح الطالب مفهوم الإعجاز وأنواعه وعلاقته بمعجزات الأنبياء السابقين.',rows[0]['text'])


if __name__=='__main__':
    unittest.main()
