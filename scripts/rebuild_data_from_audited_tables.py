#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from copy import deepcopy
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


def normalize_course_identity_name(text: str | None) -> str:
    """Normalize only non-semantic formatting in a course identity name."""
    value = unicodedata.normalize("NFC", text or "")
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
    return normalize_space(value)


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
    # Existing values include reviewed corrections that must survive rebuilds.
    if existing_category:
        return existing_category
    if optional_pool:
        return "اختيارية القسم"

    raw_category = normalize_space(row.get("الفئة", ""))
    code = normalize_space(row.get("رمز_المقرر", ""))
    name = normalize_space(row.get("اسم_المقرر_عربي", ""))

    if raw_category == "متطلبات الكلية":
        return "متطلبات الكلية"
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


def build_current_metadata(current_data: dict[str, Any]) -> tuple[
    dict[tuple[str, str, int, str], dict[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
    dict[tuple[tuple[str, str, int, str], str], list[dict[str, Any]]],
    dict[tuple[str, str], dict[str, Any]],
]:
    programs_by_identity: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    programs_by_name_degree: dict[tuple[str, str], dict[str, Any]] = {}
    course_meta_by_program_code: defaultdict[
        tuple[tuple[str, str, int, str], str],
        list[dict[str, Any]],
    ] = defaultdict(list)
    shared_meta_by_course_identity: dict[tuple[str, str], dict[str, Any]] = {}

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
            name = normalize_space(course.get("name", ""))
            if not code or not name:
                continue
            metadata = {
                "name": name,
                "name_en": course.get("name_en"),
                "type": course.get("type"),
                "category": course.get("category"),
            }
            course_meta_by_program_code[(identity, code)].append(metadata)
            shared_meta_by_course_identity.setdefault(
                (code, normalize_course_identity_name(name)),
                {
                    "name_en": course.get("name_en"),
                    "type": course.get("type"),
                },
            )

    # Catalog-only courses participate in the compound identity lookup, but
    # never contribute a plan category because they are not assigned to a plan.
    for course in current_data.get("courses_catalog", []):
        if not isinstance(course, dict):
            continue
        code = normalize_space(course.get("code", ""))
        name = normalize_space(course.get("name", ""))
        if not code or not name:
            continue
        shared_meta_by_course_identity.setdefault(
            (code, normalize_course_identity_name(name)),
            {
                "name_en": course.get("name_en"),
                "type": course.get("type"),
            },
        )

    return (
        programs_by_identity,
        programs_by_name_degree,
        dict(course_meta_by_program_code),
        shared_meta_by_course_identity,
    )


def choose_existing_course_metadata(
    program_identity: tuple[str, str, int, str],
    code: str,
    source_name: str,
    source_variant_count: int,
    course_meta_by_program_code: dict[
        tuple[tuple[str, str, int, str], str],
        list[dict[str, Any]],
    ],
    shared_meta_by_course_identity: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Return metadata without conflating two names that share one code.

    An exact compound-identity match always wins. A sole existing course in
    the same program/code slot may supply a manually corrected display name,
    but only when the audited source also contains one name for that code.
    This preserves corrections such as OCR fixes while keeping two genuine
    renamed courses as two records.
    """
    candidates = course_meta_by_program_code.get((program_identity, code), [])
    source_identity_name = normalize_course_identity_name(source_name)
    exact_matches = [
        candidate
        for candidate in candidates
        if normalize_course_identity_name(candidate.get("name")) == source_identity_name
    ]
    if len(exact_matches) == 1:
        return dict(exact_matches[0])

    if source_variant_count == 1 and len(candidates) == 1:
        return dict(candidates[0])

    shared = shared_meta_by_course_identity.get((code, source_identity_name), {})
    return {
        "name_en": shared.get("name_en"),
        "type": shared.get("type"),
    }


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
    parser.add_argument(
        "--plans-csv",
        type=Path,
        default=PLANS_CSV,
        help="Audited plans CSV. The default points to the workspace extraction output.",
    )
    parser.add_argument(
        "--courses-csv",
        type=Path,
        default=None,
        help="Matched courses CSV. When omitted, the latest workspace extraction is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    current_data = load_json(args.metadata_json)
    matched_courses_csv = args.courses_csv or find_latest_matched_courses_csv()
    plans_rows = read_csv(args.plans_csv)
    course_rows = read_csv(matched_courses_csv)

    (
        current_programs,
        current_programs_by_name,
        course_meta_by_program_code,
        shared_meta_by_course_identity,
    ) = build_current_metadata(current_data)
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

        plan_course_rows = rows_by_plan.get(plan["معرف_الخطة"], [])
        source_names_by_code: defaultdict[str, set[str]] = defaultdict(set)
        for row in plan_course_rows:
            code = normalize_space(row.get("رمز_المقرر", ""))
            source_name = normalize_course_identity_name(row.get("اسم_المقرر_عربي", ""))
            if code and source_name:
                source_names_by_code[code].add(source_name)

        seen_source_course_keys: set[tuple[str, str]] = set()
        seen_output_course_keys: set[tuple[str, str]] = set()
        courses_output: list[dict[str, Any]] = []

        for row in plan_course_rows:
            code = normalize_space(row.get("رمز_المقرر", ""))
            source_name_ar = normalize_space(row.get("اسم_المقرر_عربي", ""))
            if not code or not source_name_ar:
                continue

            source_course_key = (code, normalize_course_identity_name(source_name_ar))
            if source_course_key in seen_source_course_keys:
                continue
            seen_source_course_keys.add(source_course_key)

            existing_meta = choose_existing_course_metadata(
                identity,
                code,
                source_name_ar,
                len(source_names_by_code[code]),
                course_meta_by_program_code,
                shared_meta_by_course_identity,
            )
            name_ar = normalize_space(existing_meta.get("name", "")) or source_name_ar
            output_course_key = (code, normalize_course_identity_name(name_ar))
            if output_course_key in seen_output_course_keys:
                continue
            seen_output_course_keys.add(output_course_key)

            hours = parse_intish(row.get("الساعات_س", "") or row.get("ساعات_المقرر", ""))
            optional_pool = is_optional_course(row)
            level = parse_level(row.get("المستوى", ""))

            course = {
                "code": code,
                "name": name_ar,
                "name_en": existing_meta.get("name_en"),
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

    catalog_map: dict[tuple[str, str], dict[str, Any]] = {}
    for program in programs_output:
        program_label = program["label"]
        for course in program["courses"]:
            catalog_key = (
                normalize_space(course["code"]),
                normalize_course_identity_name(course["name"]),
            )
            entry = catalog_map.setdefault(
                catalog_key,
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

    # Keep audited records that are intentionally searchable but are not yet
    # assigned to a specific plan. Their absence from programs[].courses means
    # they never affect plan hours or occurrence counts.
    for course in current_data.get("courses_catalog", []):
        if not isinstance(course, dict) or not course.get("catalog_only"):
            continue
        catalog_key = (
            normalize_space(course.get("code", "")),
            normalize_course_identity_name(course.get("name", "")),
        )
        if not all(catalog_key) or catalog_key in catalog_map:
            continue
        catalog_map[catalog_key] = deepcopy(course)

    new_data = {
        "university": current_data.get("university", {}),
        "equivalencies": current_data.get("equivalencies", {}),
        "course_details": current_data.get("course_details", {}),
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
