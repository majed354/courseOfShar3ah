#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rebuild_data_from_audited_tables.py"
REPOSITORY_DATA = ROOT / "data.json"
OUTPUTS_ROOT = ROOT.parent / "جداول الخطط" / "مخرجات_استخراج_الخطط"
REPOSITORY_PLANS = OUTPUTS_ROOT / "الخطط.csv"


def latest_repository_courses_csv() -> Path | None:
    if not OUTPUTS_ROOT.exists():
        return None
    candidates = sorted(
        folder / "المقررات_بعد_مطابقة_JSON.csv"
        for folder in OUTPUTS_ROOT.iterdir()
        if folder.is_dir() and folder.name.startswith("نسخة_مطابقة_JSON_")
    )
    return next((candidate for candidate in reversed(candidates) if candidate.exists()), None)


REPOSITORY_COURSES = latest_repository_courses_csv()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_rebuild(metadata: Path, output: Path, plans: Path, courses: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--metadata-json",
            str(metadata),
            "--output-json",
            str(output),
            "--plans-csv",
            str(plans),
            "--courses-csv",
            str(courses),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def program_identity(program: dict[str, Any]) -> tuple[str, str, int, str]:
    return (
        program.get("name", ""),
        program.get("degree", ""),
        int(program.get("version", 0) or 0),
        program.get("plan_type", ""),
    )


def course_name_category_snapshot(
    data: dict[str, Any],
) -> dict[tuple[str, str, int, str], Counter[tuple[str, str, str]]]:
    return {
        program_identity(program): Counter(
            (
                course.get("code", ""),
                course.get("name", ""),
                course.get("category", ""),
            )
            for course in program.get("courses", [])
        )
        for program in data.get("programs", [])
    }


class SyntheticSemanticNoRegressionTest(unittest.TestCase):
    def test_preserves_corrections_and_same_code_different_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rebuild-semantic-test-") as temp_name:
            temp_dir = Path(temp_name)
            metadata = temp_dir / "metadata.json"
            first_output = temp_dir / "first.json"
            second_output = temp_dir / "second.json"
            plans = temp_dir / "plans.csv"
            courses = temp_dir / "courses.csv"

            current_data = {
                "university": {"name": "جامعة اختبار"},
                "equivalencies": {},
                "course_details": {
                    "2002131-2": {
                        "variants": [
                            {"title": "علوم القرآن (1)"},
                            {"title": "علوم القرآن العامة"},
                        ]
                    }
                },
                "programs": [
                    {
                        "id": 1,
                        "name": "القرآن وعلومه",
                        "name_en": "Quran and its Sciences",
                        "degree": "بكالوريوس",
                        "degree_en": "Bachelor",
                        "version": 47,
                        "plan_type": "جديدة",
                        "total_hours": 7,
                        "department": "قسم القراءات",
                        "label": "القرآن وعلومه (47 جديدة)",
                        "label_en": None,
                        "source": {"file": "plan.pdf"},
                        "courses": [
                            {
                                "code": "104999-3",
                                "name": "البلاغة",
                                "name_en": None,
                                "hours": 3,
                                "level": 1,
                                "type": "نظري",
                                "category": "متطلبات جامعية",
                                "belongs_to_programs": ["القرآن وعلومه (47 جديدة)"],
                            },
                            {
                                "code": "2002131-2",
                                "name": "علوم القرآن (1)",
                                "name_en": None,
                                "hours": 2,
                                "level": 2,
                                "type": "نظري",
                                "category": "إجبارية القسم",
                                "belongs_to_programs": ["القرآن وعلومه (47 جديدة)"],
                            },
                            {
                                "code": "2002131-2",
                                "name": "علوم القرآن العامة",
                                "name_en": None,
                                "hours": 2,
                                "level": 3,
                                "type": "نظري",
                                "category": "متطلبات الكلية",
                                "belongs_to_programs": ["القرآن وعلومه (47 جديدة)"],
                            },
                        ],
                    }
                ],
                "courses_catalog": [
                    {
                        "catalog_id": "2002131-2::independent",
                        "catalog_only": True,
                        "code": "2002131-2",
                        "name": "علوم القرآن المتقدمة",
                        "hours": 2,
                        "type": "نظري",
                        "programs": [],
                    }
                ],
            }
            metadata.write_text(
                json.dumps(current_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            write_csv(
                plans,
                [
                    "معرف_الخطة",
                    "اسم_البرنامج",
                    "الدرجة",
                    "الإصدار",
                    "نوع_الملف",
                    "القسم",
                    "ساعات_الخطة",
                    "المصدر",
                ],
                [
                    {
                        "معرف_الخطة": "PLAN-1",
                        "اسم_البرنامج": "القرآن",
                        "الدرجة": "البكالوريوس",
                        "الإصدار": "47",
                        "نوع_الملف": "الملف الحديث",
                        "القسم": "القراءات",
                        "ساعات_الخطة": "7",
                        "المصدر": "plan.pdf",
                    }
                ],
            )
            write_csv(
                courses,
                [
                    "معرف_الخطة",
                    "رمز_المقرر",
                    "اسم_المقرر_عربي",
                    "اسم_المقرر_إنجليزي",
                    "الساعات_س",
                    "ساعات_المقرر",
                    "نوع_الساعات",
                    "الفئة",
                    "المجموعة",
                    "المستوى",
                ],
                [
                    {
                        "معرف_الخطة": "PLAN-1",
                        "رمز_المقرر": "104999-3",
                        "اسم_المقرر_عربي": "البالغة",
                        "اسم_المقرر_إنجليزي": "",
                        "الساعات_س": "3",
                        "ساعات_المقرر": "3",
                        "نوع_الساعات": "نظري",
                        "الفئة": "متطلبات الكلية",
                        "المجموعة": "",
                        "المستوى": "المستوى الأول",
                    },
                    {
                        "معرف_الخطة": "PLAN-1",
                        "رمز_المقرر": "2002131-2",
                        "اسم_المقرر_عربي": "علوم القرآن (1)",
                        "اسم_المقرر_إنجليزي": "",
                        "الساعات_س": "2",
                        "ساعات_المقرر": "2",
                        "نوع_الساعات": "نظري",
                        "الفئة": "إجبارية القسم",
                        "المجموعة": "",
                        "المستوى": "المستوى الثاني",
                    },
                    {
                        "معرف_الخطة": "PLAN-1",
                        "رمز_المقرر": "2002131-2",
                        "اسم_المقرر_عربي": "علوم القرآن العامة",
                        "اسم_المقرر_إنجليزي": "",
                        "الساعات_س": "2",
                        "ساعات_المقرر": "2",
                        "نوع_الساعات": "نظري",
                        "الفئة": "متطلبات الكلية",
                        "المجموعة": "",
                        "المستوى": "المستوى الثالث",
                    },
                ],
            )

            run_rebuild(metadata, first_output, plans, courses)
            first_data = load_json(first_output)

            self.assertEqual(
                course_name_category_snapshot(current_data),
                course_name_category_snapshot(first_data),
            )
            self.assertEqual(
                [
                    (course["code"], course["name"])
                    for course in first_data["programs"][0]["courses"]
                    if course["code"] == "2002131-2"
                ],
                [
                    ("2002131-2", "علوم القرآن (1)"),
                    ("2002131-2", "علوم القرآن العامة"),
                ],
            )
            self.assertTrue(
                any(
                    course.get("catalog_only")
                    and course.get("name") == "علوم القرآن المتقدمة"
                    for course in first_data["courses_catalog"]
                )
            )
            self.assertEqual(current_data["course_details"], first_data["course_details"])

            run_rebuild(first_output, second_output, plans, courses)
            self.assertEqual(first_data, load_json(second_output))


@unittest.skipUnless(
    REPOSITORY_DATA.exists() and REPOSITORY_PLANS.exists() and REPOSITORY_COURSES is not None,
    "Workspace extraction tables are not available.",
)
class RepositorySemanticNoRegressionTest(unittest.TestCase):
    def test_current_names_and_categories_survive_first_rebuild(self) -> None:
        assert REPOSITORY_COURSES is not None
        with tempfile.TemporaryDirectory(prefix="rebuild-repository-test-") as temp_name:
            temp_dir = Path(temp_name)
            first_output = temp_dir / "first.json"
            second_output = temp_dir / "second.json"

            run_rebuild(
                REPOSITORY_DATA,
                first_output,
                REPOSITORY_PLANS,
                REPOSITORY_COURSES,
            )
            before = load_json(REPOSITORY_DATA)
            first = load_json(first_output)
            self.assertEqual(
                course_name_category_snapshot(before),
                course_name_category_snapshot(first),
            )

            run_rebuild(
                first_output,
                second_output,
                REPOSITORY_PLANS,
                REPOSITORY_COURSES,
            )
            self.assertEqual(first, load_json(second_output))


if __name__ == "__main__":
    unittest.main()
