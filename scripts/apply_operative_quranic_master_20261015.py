#!/usr/bin/env python3
"""Publish the operative 14-course master's specification without rewriting sources."""
import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

from verify_course_outcomes import ErrorCollector, expected_excluded_reason, recompute_statistics

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path('assets/course-specifications/quranic-master-operative-2023')
PROPOSED_SHA = '46db21fdf5e5aee97c46c25641469660c6cd4e6f6b5cb00b7ec45e164e83eff5'
OPERATIVE_SHA = '4d82f5733fbe9264b7a032fa4a87e08a990c618f8e8c43367322381ae87e67a0'
PLAN_SHA = '9ad53d22f91b8e9ad5ed579b607c35e0eb934e60a6dc3aa3b54b2a77ee088788'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, payload, *, sort_keys=False):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--specification', type=Path, required=True)
    parser.add_argument('--curriculum', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    assert digest(args.specification) == OPERATIVE_SHA
    assert digest(args.curriculum) == PLAN_SHA
    reference = json.loads(args.reference.read_text())
    assert reference['program_metadata']['Source_Matrix_Review_SHA256'] == OPERATIVE_SHA
    courses = reference['curriculum']
    assert len(courses) == 14 and sum(r['hours'] for r in courses) == 34
    assert len(reference['program_outcomes']) == 7 and len(reference['program_matrix']) == 40
    target = ROOT / BUNDLE
    target.mkdir(parents=True, exist_ok=True)
    for source, name in [(args.specification, 'program-specification.pdf'), (args.curriculum, 'official-curriculum.pdf')]:
        destination = target / name
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
    write(target / 'program-reference.json', reference)
    data_path = ROOT / 'data.json'
    data = json.loads(data_path.read_text())
    program = next(p for p in data['programs'] if (p['name'], p['degree']) == ('الدراسات القرآنية المعاصرة', 'ماجستير'))
    historical = target / 'proposed-program-history.json'
    if not historical.exists():
        assert program['program_details']['specification_source_sha256'] == PROPOSED_SHA
        write(historical, {'operational_status': 'proposed_not_implemented', 'recorded_on': '2026-10-15', 'program': copy.deepcopy(program)})
    history = json.loads(historical.read_text())
    old_url = history['program']['program_specification_url']
    assert digest(ROOT / old_url) == PROPOSED_SHA
    canonical = {r['code']: r for r in courses}
    assert {c['code'] for c in program['courses']} == set(canonical)
    for course in program['courses']:
        row = canonical[course['code']]
        course['level'] = int(row['level'].split()[-1])
        course['hours'] = int(row['hours'])
    for course in data['courses_catalog']:
        if course['code'] == '2002871-2':
            course['levels_by_program'][program['name']] = 3
    details = program['program_details']
    details.update(
        last_review='8/2023م', curriculum_course_count=14, matrix_link_count=40,
        specification_source_sha256=OPERATIVE_SHA, extraction_status='needs_review', extraction_error_count=0,
        total_credit_hours=34, operative_status='implemented',
        learning_outcomes=[{'code': r['code'], 'domain': {'ع': 'المعرفة والفهم', 'م': 'المهارات', 'ق': 'القيم والاستقلالية والمسؤولية'}[r['code'][0]], 'text': r['text']} for r in reference['program_outcomes']],
        objectives=[
            'إتقان مهارات البحث القرآني المعاصر لإعداد باحثين متميزين.',
            'تعزيز القدرة التحليلية في مجال الدراسات القرآنية لمواجهة التحديات المعاصرة.',
            'تطوير القدرات المهنية للطلاب لإثراء المجال الأكاديمي والمهني بأفكار ودراسات مبتكرة..',
            'بناء شراكات استراتيجية لتوظيف القرآن في حل المشكلات المجتمعية.',
            'صقل المهارات المتخصصة لتلبية متطلبات سوق العمل ومؤسسات التعليم في الدراسات القرآنية.',
            'تطوير مهارات الاتصال لنقل المعرفة وتعزيز الحوار البنّاء.',
            'ترسيخ أخلاقيات البحث والمسؤولية الاجتماعية في العمل الأكاديمي.',
        ],
        matrix_mastery_missing=['ق1'],
    )
    program['program_specification_url'] = (BUNDLE / 'program-specification.pdf').as_posix()
    program['program_specification_label'] = 'توصيف برنامج ماجستير الدراسات القرآنية المعاصرة — المعمول به'
    program['program_reference_url'] = (BUNDLE / 'program-reference.json').as_posix()
    program['official_curriculum_url'] = (BUNDLE / 'official-curriculum.pdf').as_posix()
    write(data_path, data)
    manifest = {
        'schema_version': 1, 'corrected_on': '2026-10-15', 'operational_status': 'implemented',
        'program': program['name'], 'degree': program['degree'], 'source_bytes_preserved': True,
        'program_pdf': {'path': program['program_specification_url'], 'sha256': OPERATIVE_SHA, 'pages': 13},
        'official_curriculum': {'path': program['official_curriculum_url'], 'sha256': PLAN_SHA, 'pages': 1},
        'reference': {'path': program['program_reference_url'], 'sha256': digest(target / 'program-reference.json')},
        'superseded_proposal': {'path': old_url, 'sha256': PROPOSED_SHA, 'operational_status': 'proposed_not_implemented'},
        'counts': {'courses': 14, 'credit_hours': 34, 'program_outcomes': 7, 'matrix_links': 40},
        'course_code_corrections': {'2002851-3': '2002851-4', '2002861-2': '2002861-4', '2002888-2': '2002888-4'},
        'curriculum_level_corrections': {'2002871-2': {'from': 2, 'to': 3}},
        'academic_gaps': [{'code': 'PROGRAM_MASTERY_MISSING', 'plo_code': 'ق1', 'message': 'لا يوجد تصنيف تمكين 3 لهذا الناتج في مصفوفة المصدر؛ لم يُغيّر أي ربط أكاديمي.'}],
        'course_outcomes_policy': 'Preserve existing course PDF bytes, CLO texts, scoped PLO mappings and reviews; this batch corrects program source and curriculum facts only.',
    }
    write(target / 'manifest.json', manifest)
    historical_manifest_path = ROOT / 'assets/course-specifications/program-specifications-20260916/manifest.json'
    historical_manifest = json.loads(historical_manifest_path.read_text())
    for record in historical_manifest['records']:
        if record['published_url'] == old_url:
            record.update(operational_status='proposed_not_implemented', superseded_by=program['program_specification_url'])
    write(historical_manifest_path, historical_manifest)
    outcomes_path = ROOT / 'course-outcomes.json'
    outcomes = json.loads(outcomes_path.read_text())
    before_courses = copy.deepcopy(outcomes['courses'])
    excluded = {r['source_pdf']: r for r in outcomes['excluded_sources']}
    for name in ['program-specification.pdf', 'official-curriculum.pdf']:
        path = (BUNDLE / name).as_posix()
        excluded[path] = {'source_pdf': path, 'source_sha256': digest(ROOT / path), 'reason': expected_excluded_reason(path)}
    outcomes['excluded_sources'] = [excluded[k] for k in sorted(excluded)]
    outcomes['source_data']['sha256'] = digest(data_path)
    errors = ErrorCollector()
    outcomes['statistics'].update(recompute_statistics(outcomes, errors))
    assert outcomes['courses'] == before_courses
    write(outcomes_path, outcomes)
    print(json.dumps(manifest['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
