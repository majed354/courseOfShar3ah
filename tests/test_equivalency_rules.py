#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data.json'
VALIDATION = ROOT / 'assets' / 'course-equivalencies' / 'validation.json'


def norm(value: object) -> str:
    return ' '.join(str(value if value is not None else '').split())


class EquivalencyRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(DATA.read_text(encoding='utf-8'))
        cls.rules = cls.data.get('equivalencies', {})

    def test_expected_counts_and_forbidden_pairs(self) -> None:
        self.assertEqual(22, len(self.rules))
        self.assertEqual(32, sum(len(items) for items in self.rules.values()))
        for forbidden in ('2004313-2', '2007314-2', '2002333-2'):
            self.assertNotIn(forbidden, self.rules)

    def test_every_scope_resolves_and_every_pair_is_bidirectional(self) -> None:
        directed = set()
        for source_code, items in self.rules.items():
            for rule in items:
                source_name = norm(rule.get('source_name'))
                self.assertTrue(source_name)
                self.assertEqual('بكالوريوس', norm(rule.get('degree')))
                self.assertEqual(1, len(rule.get('options', [])))
                option = rule['options'][0]
                target_code = norm(option.get('code'))
                target_name = norm(option.get('name'))
                self.assertTrue(target_code and target_name)

                resolved = False
                for program in self.data.get('programs', []):
                    context = {
                        'program': program.get('name'),
                        'degree': program.get('degree'),
                        'plan_type': program.get('plan_type'),
                        'version': program.get('version'),
                    }
                    if any(
                        norm(rule.get(field)) and norm(rule.get(field)) != norm(context.get(field))
                        for field in ('program', 'degree', 'plan_type', 'version')
                    ):
                        continue
                    if any(
                        norm(course.get('code')) == norm(source_code)
                        and norm(course.get('name')) == source_name
                        for course in program.get('courses', [])
                    ):
                        resolved = True
                        break
                self.assertTrue(resolved, f'unresolved scope: {source_code} / {rule}')
                directed.add((norm(source_code), source_name, target_code, target_name))

        for source_code, source_name, target_code, target_name in directed:
            self.assertIn((target_code, target_name, source_code, source_name), directed)
        undirected = {
            tuple(sorted(((source_code, source_name), (target_code, target_name))))
            for source_code, source_name, target_code, target_name in directed
        }
        self.assertEqual(22, len(directed))
        self.assertEqual(11, len(undirected))

    def test_validation_manifest(self) -> None:
        validation = json.loads(VALIDATION.read_text(encoding='utf-8'))
        self.assertEqual('PASS', validation['validation_status'])
        self.assertEqual(11, validation['undirected_pairs'])
        self.assertTrue(validation['all_rules_explicit_degree'])
        self.assertFalse(validation['removed_2007314_2002333_pair_present_in_patch'])


if __name__ == '__main__':
    unittest.main()
