#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CODEX_ROOT = ROOT.parent
OUTPUTS_ROOT = CODEX_ROOT / "جداول الخطط" / "مخرجات_استخراج_الخطط"
PLANS_CSV = OUTPUTS_ROOT / "الخطط.csv"

PROGRAM_CANONICAL_NAMES = {
    ("البكالوريوس", "القرآن"): "القرآن وعلومه",
    ("البكالوريوس", "الثقافة"): "الدراسات الإسلامية",
}

DEGREE_AR_MAP = {
    "البكالوريوس": "بكالوريوس",
    "الماجستير": "ماجستير",
    "الدكتوراه": "دكتوراه",
}

DEGREE_EN_MAP = {
    "بكالوريوس": "Bachelor",
    "ماجستير": "Master",
    "دكتوراه": "PhD",
}

PLAN_TYPE_MAP = {
    "الملف القديم": "قديمة",
    "الملف الحديث": "جديدة",
    "الدراسات العليا": "جديدة",
}

ORDINAL_LEVELS = {
    "الأول": 1,
    "الثاني": 2,
    "الثالث": 3,
    "الرابع": 4,
    "الخامس": 5,
    "السادس": 6,
    "السابع": 7,
    "الثامن": 8,
    "التاسع": 9,
    "العاشر": 10,
}

COMMON_REQUIREMENT_PREFIXES = (
    "99",
    "999",
    "103",
    "104",
    "105",
    "106",
    "108",
    "201",
    "202",
    "203",
    "206",
    "305",
    "317",
    "319",
    "373",
    "440",
    "501",
    "502",
    "660",
)

OPTIONAL_BUNDLE_CODES = {
    "990113-2",
    "990312-2",
    "990411-2",
    "990412-2",
    "990413-2",
    "990415-2",
    "990416-2",
    "990417-2",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def find_latest_matched_courses_csv() -> Path:
    candidates = sorted(
        (
            folder / "المقررات_بعد_مطابقة_JSON.csv"
            for folder in OUTPUTS_ROOT.iterdir()
            if folder.is_dir() and folder.name.startswith("نسخة_مطابقة_JSON_")
        ),
        key=lambda item: item.parent.name,
    )
    for candidate in reversed(candidates):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate المقررات_بعد_مطابقة_JSON.csv")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_digits(text: str) -> str:
    return (text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


def parse_intish(value: str) -> int | None:
    match = re.search(r"\d+", normalize_digits(value))
    return int(match.group()) if match else None


def parse_level(raw_level: str) -> int | None:
    text = normalize_space(raw_level)
    if not text:
        return None

    matches: list[tuple[int, int]] = []
    for label, numeric in ORDINAL_LEVELS.items():
        idx = text.rfind(label)
        if idx != -1:
            matches.append((idx, numeric))

    if matches:
        matches.sort()
        return matches[-1][1]

    return parse_intish(text)


def clean_type(raw_type: str, course_name: str, existing_type: str | None) -> str:
    text = normalize_space(raw_type)
    name = normalize_space(course_name)

    if "الختبار الشامل" in text or ("اختبار" in text and "شامل" in text):
        return "الاختبار الشامل"
    if name == "الرسالة" or "مشروع" in name:
        return "بحث"
    if text in {"نظري", "عملي", "تدريب"}:
        return text
    if existing_type:
        return existing_type
    return "نظري"


def is_optional_course(row: dict[str, str]) -> bool:
    if row.get("رمز_المقرر") in OPTIONAL_BUNDLE_CODES:
        return True

    fields = " ".join(
        normalize_space(row.get(key, ""))
        for key in ("الفئة", "المجموعة", "اسم_المقرر_إنجليزي", "الساعات_س")
    )
    return "اختيار" in fields or "Optional" in fields


def infer_category(
    row: dict[str, str],
    existing_category: str | None,
    optional_pool: bool,
) -> str:
    if optional_pool:
        return "اختيارية القسم"

    raw_category = normalize_space(row.get("الفئة", ""))
    code = normalize_space(row.get("رمز_المقرر", ""))
    name = normalize_space(row.get("اسم_المقرر_عربي", ""))

    if raw_category == "متطلبات الكلية":
        return "متطلبات الكلية"
    if existing_category:
        return existing_category
    if code.startswith(COMMON_REQUIREMENT_PREFIXES):
        return "متطلبات جامعية"
    if any(token in name for token in ("البلاغة", "البالغة", "النحو", "الصرف", "التحرير العربي")):
        return "متطلبات جامعية"
    return "إجبارية القسم"


def canonical_program_name(plan_row: dict[str, str]) -> str:
    degree = normalize_space(plan_row.get("الدرجة", ""))
    name = normalize_space(plan_row.get("اسم_البرنامج", ""))
    return PROGRAM_CANONICAL_NAMES.get((degree, name), name)


def build_program_identity(plan_row: dict[str, str]) -> tuple[str, str, int, str]:
    name = canonical_program_name(plan_row)
    degree = DEGREE_AR_MAP.get(normalize_space(plan_row.get("الدرجة", "")), normalize_space(plan_row.get("الدرجة", "")))
    version = parse_intish(plan_row.get("الإصدار", "")) or 0
    plan_type = PLAN_TYPE_MAP.get(normalize_space(plan_row.get("نوع_الملف", "")), "جديدة")
    return (name, degree, version, plan_type)


def make_default_label(name: str, degree: str, version: int, plan_type: str, duplicate_keys: set[tuple[str, str]]) -> str:
    if (name, degree) in duplicate_keys:
        return f"{name} ({degree} - إصدار {version} - {plan_type})"
    return name


def normalize_name_key(text: str | None) -> str:
    value = normalize_digits(text or "")
    value = normalize_space(value)
    value = value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    value = value.replace("ى", "ي").replace("ة", "ه")
    value = value.replace("(", "").replace(")", "")
    return value


def choose_name_en(existing_meta: dict[str, Any], course_name_ar: str) -> str | None:
    if normalize_name_key(existing_meta.get("name")) == normalize_name_key(course_name_ar):
        return existing_meta.get("name_en")
    return None


def build_current_metadata(current_data: dict[str, Any]) -> tuple[
    dict[tuple[str, str, int, str], dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    programs_by_identity: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    programs_by_name_degree: dict[tuple[str, str], dict[str, Any]] = {}
    course_meta_by_code: dict[str, dict[str, Any]] = {}

    for program in current_data.get("programs", []):
        identity = (
            normalize_space(program.get("name", "")),
            normalize_space(program.get("degree", "")),
            int(program.get("version", 0) or 0),
            normalize_space(program.get("plan_type", "")),
        )
        programs_by_identity[identity] = program
        programs_by_name_degree.setdefault(
            (identity[0], identity[1]),
            program,
        )

        for course in program.get("courses", []):
            code = normalize_space(course.get("code", ""))
            if not code or code in course_meta_by_code:
                continue
            course_meta_by_code[code] = {
                "name": course.get("name"),
                "name_en": course.get("name_en"),
                "type": course.get("type"),
                "category": course.get("category"),
            }

    return programs_by_identity, programs_by_name_degree, course_meta_by_code


def build_program_position_maps(
    current_data: dict[str, Any],
) -> tuple[
    dict[tuple[str, str, int, str], int],
    defaultdict[tuple[str, str, str], list[tuple[int, int]]],
    defaultdict[tuple[str, str], list[int]],
]:
    identity_positions: dict[tuple[str, str, int, str], int] = {}
    group_positions: defaultdict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
    name_degree_positions: defaultdict[tuple[str, str], list[int]] = defaultdict(list)

    for index, program in enumerate(current_data.get("programs", [])):
        identity = (
            normalize_space(program.get("name", "")),
            normalize_space(program.get("degree", "")),
            int(program.get("version", 0) or 0),
            normalize_space(program.get("plan_type", "")),
        )
        identity_positions[identity] = index
        group_positions[(identity[0], identity[1], identity[3])].append((identity[2], index))
        name_degree_positions[(identity[0], identity[1])].append(index)

    return identity_positions, group_positions, name_degree_positions


def program_sort_position(
    program: dict[str, Any],
    identity_positions: dict[tuple[str, str, int, str], int],
    group_positions: defaultdict[tuple[str, str, str], list[tuple[int, int]]],
    name_degree_positions: defaultdict[tuple[str, str], list[int]],
) -> float:
    identity = (
        normalize_space(program.get("name", "")),
        normalize_space(program.get("degree", "")),
        int(program.get("version", 0) or 0),
        normalize_space(program.get("plan_type", "")),
    )
    if identity in identity_positions:
        return float(identity_positions[identity])

    group_key = (identity[0], identity[1], identity[3])
    if group_key in group_positions:
        ordered = sorted(group_positions[group_key], key=lambda item: (item[0], item[1]))
        if identity[2] < ordered[0][0]:
            return ordered[0][1] - 0.1
        for (version_a, index_a), (version_b, index_b) in zip(ordered, ordered[1:]):
            if version_a < identity[2] < version_b:
                return (index_a + index_b) / 2
        return ordered[-1][1] + 0.1

    name_degree_key = (identity[0], identity[1])
    if name_degree_key in name_degree_positions:
        return min(name_degree_positions[name_degree_key]) + 0.5

    return float(len(identity_positions) + 100)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metadata-json",
        type=Path,
        default=ROOT / "data.json",
        help="JSON file to use as the metadata source for English names and existing UI fields.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "data.json",
        help="Target data.json path to overwrite.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    current_data = load_json(args.metadata_json)
    matched_courses_csv = find_latest_matched_courses_csv()
    plans_rows = read_csv(PLANS_CSV)
    course_rows = read_csv(matched_courses_csv)

    current_programs, current_programs_by_name, current_course_meta = build_current_metadata(current_data)
    identity_positions, group_positions, name_degree_positions = build_program_position_maps(current_data)

    real_plans = [
        row
        for row in plans_rows
        if normalize_space(row.get("معرف_الخطة", "")).startswith("PLAN-")
        and normalize_space(row.get("اسم_البرنامج", ""))
    ]
    real_plan_ids = {row["معرف_الخطة"] for row in real_plans}

    name_degree_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for plan in real_plans:
        identity = build_program_identity(plan)
        name_degree_counts[(identity[0], identity[1])] += 1
    duplicate_name_degree_keys = {key for key, count in name_degree_counts.items() if count > 1}

    rows_by_plan: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in course_rows:
        if row.get("معرف_الخطة") in real_plan_ids:
            rows_by_plan[row["معرف_الخطة"]].append(row)

    programs_output: list[dict[str, Any]] = []

    for plan in real_plans:
        identity = build_program_identity(plan)
        current_program = current_programs.get(identity)
        current_program_by_name = current_programs_by_name.get((identity[0], identity[1]))

        name, degree, version, plan_type = identity
        degree_en = DEGREE_EN_MAP.get(degree, "")
        label = (
            current_program.get("label")
            if current_program
            else make_default_label(name, degree, version, plan_type, duplicate_name_degree_keys)
        )
        label_en = current_program.get("label_en") if current_program else None
        name_en = (
            current_program.get("name_en")
            if current_program and current_program.get("name_en") is not None
            else (current_program_by_name.get("name_en") if current_program_by_name else None)
        )
        department = (
            current_program.get("department")
            if current_program and current_program.get("department")
            else f"قسم {normalize_space(plan.get('القسم', ''))}"
        )

        seen_course_keys: set[tuple[str, str]] = set()
        courses_output: list[dict[str, Any]] = []

        for row in rows_by_plan.get(plan["معرف_الخطة"], []):
            code = normalize_space(row.get("رمز_المقرر", ""))
            name_ar = normalize_space(row.get("اسم_المقرر_عربي", ""))
            if not code or not name_ar:
                continue

            course_key = (code, name_ar)
            if course_key in seen_course_keys:
                continue
            seen_course_keys.add(course_key)

            existing_meta = current_course_meta.get(code, {})
            hours = parse_intish(row.get("الساعات_س", "") or row.get("ساعات_المقرر", ""))
            optional_pool = is_optional_course(row)
            level = parse_level(row.get("المستوى", ""))

            course = {
                "code": code,
                "name": name_ar,
                "name_en": choose_name_en(existing_meta, name_ar),
                "hours": hours or 0,
                "level": level or 0,
                "type": clean_type(row.get("نوع_الساعات", ""), name_ar, existing_meta.get("type")),
                "category": infer_category(row, existing_meta.get("category"), optional_pool),
                "belongs_to_programs": [label],
            }
            if optional_pool:
                course["optional_pool"] = True

            courses_output.append(course)

        source_value: Any = {"file": normalize_space(plan.get("المصدر", ""))}
        if current_program and current_program.get("source") is not None:
            source_value = current_program["source"]

        programs_output.append(
            {
                "name": name,
                "name_en": name_en,
                "degree": degree,
                "degree_en": degree_en,
                "version": version,
                "plan_type": plan_type,
                "total_hours": parse_intish(plan.get("ساعات_الخطة", "")) or 0,
                "department": department,
                "courses": courses_output,
                "source": source_value,
                "label": label,
                "label_en": label_en,
            }
        )

    programs_output.sort(
        key=lambda program: (
            program_sort_position(program, identity_positions, group_positions, name_degree_positions),
            normalize_space(program.get("name", "")),
            normalize_space(program.get("degree", "")),
            int(program.get("version", 0) or 0),
        )
    )

    for index, program in enumerate(programs_output, start=1):
        program["id"] = index

    catalog_map: dict[str, dict[str, Any]] = {}
    for program in programs_output:
        program_label = program["label"]
        for course in program["courses"]:
            entry = catalog_map.setdefault(
                course["code"],
                {
                    "code": course["code"],
                    "name": course["name"],
                    "name_en": course.get("name_en"),
                    "hours": course["hours"],
                    "type": course["type"],
                    "programs": [],
                    "levels_by_program": {},
                    "categories_by_program": {},
                },
            )
            if program_label not in entry["programs"]:
                entry["programs"].append(program_label)
            entry["levels_by_program"][program_label] = course["level"]
            entry["categories_by_program"][program_label] = course["category"]

    new_data = {
        "university": current_data.get("university", {}),
        "equivalencies": current_data.get("equivalencies", {}),
        "programs": programs_output,
        "courses_catalog": [catalog_map[key] for key in sorted(catalog_map)],
    }

    args.output_json.write_text(
        json.dumps(new_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Using metadata source: {args.metadata_json}")
    print(f"Using corrected courses file: {matched_courses_csv}")
    print(f"Output written to: {args.output_json}")
    print(f"Programs written: {len(programs_output)}")
    print(f"Catalog entries written: {len(new_data['courses_catalog'])}")


if __name__ == "__main__":
    main()
