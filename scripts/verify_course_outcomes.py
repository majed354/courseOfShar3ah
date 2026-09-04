#!/usr/bin/env python3
"""Verify the pinned course-outcomes extraction without parsing any PDFs.

The verifier deliberately rebuilds the expected variant identities from
``data.json``.  It then checks the pinned extraction, every referenced file
hash, and the complete PDF inventory.  It uses only the Python standard
library so it can run unchanged in GitHub Actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "course-outcomes-v1"
EXTRACTOR_NAME = "course-outcomes-extractor"
EXTRACTOR_VERSION = "1.1.0"
ROOT_FIELDS = {
    "schema_version",
    "generated_at",
    "extractor",
    "source_data",
    "auxiliary_sources",
    "courses",
    "excluded_sources",
    "statistics",
}
EXTRACTOR_FIELDS = {
    "name",
    "version",
    "script",
    "script_sha256",
    "font_recovery_script",
    "font_recovery_script_sha256",
    "pdfplumber",
    "pymupdf",
    "tesseract",
}
SOURCE_DATA_FIELDS = {"path", "sha256"}
AUXILIARY_SOURCE_FIELDS = {"path", "sha256", "purpose"}
AUXILIARY_SOURCES = {
    "assets/course-specifications/unified-new-program-mappings-20260901.json": "published multi-program PLO mapping cells",
    "assets/course-specifications/clo-plo-corrections-20260901/manifest.json": "published CLO/PLO correction cells",
    "assets/course-specifications/shared-course-completions-20260904/manifest.json": "published shared-course CLO completions and scoped PLO mappings",
}
COURSE_FIELDS = {"variants"}
EXCLUDED_SOURCE_FIELDS = {"source_pdf", "source_sha256", "reason"}
CATALOG_FIELDS = (
    "title",
    "summary",
    "specification_code",
    "match_status",
    "match_note",
    "catalog_id",
)
SCOPE_FIELDS = ("program", "degree", "plan_type", "version")
VARIANT_FIELDS = {
    "variant_id",
    "scopes",
    "catalog",
    "source_pdf",
    "source_sha256",
    "extracted",
    "overrides",
}
OVERRIDE_FIELDS = {"field", "value", "reason", "author", "date"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FIELD_PATH_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*)*"
)
FIELD_TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")
CID_RE = re.compile(r"\(\s*cid\s*:\s*\d+\s*\)", flags=re.IGNORECASE)
ARABIC_DIGIT_RE = re.compile(r"[٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹]")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
CONFIDENCE_VALUES = {"high", "medium", "low"}
EXTRACTION_STATUSES = {"complete", "partial", "failed"}
SOURCE_STATUSES = {"present", "source_blank", "unreadable"}
MAPPING_STATUSES = {
    "mapped",
    "explicitly_unmapped",
    "not_present_for_scope",
    "missing",
    "conflict",
    "ambiguous_for_scope",
}
UNRESOLVED_MAPPING_STATUSES = {"missing", "conflict", "ambiguous_for_scope"}
TITLE_METHODS = {
    "geometric_pdf",
    "page_ocr",
    "geometric_pdf_ocr_consensus",
    "unresolved",
}
CLO_METHODS = {
    "geometric_pdf",
    "geometric_pdf_ocr_consensus",
    "embedded_font_cmap",
    "embedded_font_cmap_with_geometric_continuation",
    "plain_table",
    "plain_cell_fallback",
    "targeted_ocr",
    "hash_matched_manifest",
}
EMBEDDED_FONT_CMAP_METHODS = {
    "embedded_font_cmap",
    "embedded_font_cmap_with_geometric_continuation",
}
EMBEDDED_FONT_CMAP_SOURCE_SHA256 = (
    "51269b1a7e2246e118111a2411852e99ade9030349aa8e4ec5dbfdcc1d8270a0"
)
CLO_CODE_RE = re.compile(r"^(?:[123]\.[1-9][0-9]?|[عمقك][1-9][0-9]?)$")
SOURCE_CLO_MARKER_RE = re.compile(r"^(?:[123])?\.{3}$")
PLO_CODE_RE = re.compile(r"^(?:[عمقك]|[KSVP])[0-9]{1,2}(?:\.[0-9]+)?$")
WARNING_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
EXTRACTED_FIELDS = {
    "course_name",
    "course_name_metadata",
    "clos",
    "assessment_plan",
    "assessment_plan_total",
    "assessment_plan_complete",
    "warnings",
    "extraction_status",
    "source_status",
    "source_clo_row_count",
    "captured_clo_row_count",
    "page_count",
}
COURSE_NAME_METADATA_FIELDS = {"confidence", "source_page", "extraction_method"}
CLO_FIELDS = {
    "code",
    "text",
    "source_status",
    "assessment",
    "assessment_source_page",
    "plo_mappings",
    "document_plo_codes",
    "confidence",
    "source_page",
    "extraction_method",
}
PLO_MAPPING_FIELDS = {
    "scope",
    "plo_codes",
    "status",
    "confidence",
    "source_page",
    "evidence",
}
ASSESSMENT_FIELDS = {"label", "weight", "source_page", "confidence"}
WARNING_REQUIRED_FIELDS = {"code", "message"}
WARNING_OPTIONAL_FIELDS = {"source_page", "clo_code", "clo_index"}
MAX_PRINTED_ERRORS = 200


class VerificationInputError(RuntimeError):
    """Raised when a source-of-truth file cannot be interpreted safely."""


class ErrorCollector:
    def __init__(self) -> None:
        self.count = 0
        self.messages: List[str] = []

    def add(self, message: str) -> None:
        self.count += 1
        if len(self.messages) < MAX_PRINTED_ERRORS:
            self.messages.append(message)


def _reject_duplicate_keys(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VerificationInputError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationInputError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationInputError(f"expected a JSON object in {path}")
    return value


def sha256_file(path: Path, cache: Dict[Path, str]) -> str:
    resolved = path.resolve()
    cached = cache.get(resolved)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise VerificationInputError(f"cannot hash {path}: {exc}") from exc
    result = digest.hexdigest()
    cache[resolved] = result
    return result


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def variant_identity(
    course_code: str,
    source_pdf: str,
    scopes: List[Dict[str, str]],
    catalog: Dict[str, Any],
) -> str:
    identity = {
        "course_code": course_code,
        "source_pdf": source_pdf,
        "scopes": scopes,
        "catalog": catalog,
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def normalize_arabic_identity(value: Any) -> str:
    """Match the repository's conservative code-and-title join semantics."""

    text = unicodedata.normalize("NFKD", str(value)).translate(ARABIC_DIGITS)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("ـ", "")
    text = re.sub(r"[إأآٱ]", "ا", text).replace("ى", "ي")
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE).lower()


def normalized_scope_sort_key(scope: Dict[str, str]) -> Tuple[str, str, str, str]:
    return tuple(scope[field] for field in SCOPE_FIELDS)  # type: ignore[return-value]


def course_matches(program: Dict[str, Any], code: str, title: Any) -> bool:
    title_key = normalize_arabic_identity(title)
    courses = program.get("courses")
    if not isinstance(courses, list):
        return False
    return any(
        isinstance(course, dict)
        and str(course.get("code", "")) == code
        and normalize_arabic_identity(course.get("name", "")) == title_key
        for course in courses
    )


def program_scope(program: Dict[str, Any]) -> Dict[str, str]:
    try:
        return {
            "program": str(program["name"]),
            "degree": str(program["degree"]),
            "plan_type": str(program["plan_type"]),
            "version": str(program["version"]),
        }
    except KeyError as exc:
        raise VerificationInputError(
            f"program record is missing required field {exc.args[0]!r}"
        ) from exc


def normalize_scope(
    raw_scope: Any,
    *,
    code: str,
    title: Any,
    programs: List[Dict[str, Any]],
) -> Dict[str, str]:
    if not isinstance(raw_scope, dict):
        raise VerificationInputError(f"{code}: scope must be an object")
    for field in ("program", "plan_type", "version"):
        if field not in raw_scope or raw_scope[field] in (None, ""):
            raise VerificationInputError(f"{code}: scope is missing {field!r}")

    result = {
        "program": str(raw_scope["program"]),
        "degree": (
            ""
            if raw_scope.get("degree") in (None, "")
            else str(raw_scope.get("degree"))
        ),
        "plan_type": str(raw_scope["plan_type"]),
        "version": str(raw_scope["version"]),
    }
    candidates = [
        program
        for program in programs
        if str(program.get("name", "")) == result["program"]
        and str(program.get("plan_type", "")) == result["plan_type"]
        and str(program.get("version", "")) == result["version"]
    ]
    candidate_degrees = {str(program.get("degree", "")) for program in candidates}
    candidate_degrees.discard("")

    if not result["degree"]:
        if len(candidate_degrees) != 1:
            raise VerificationInputError(
                f"{code}: cannot derive one degree for scope "
                f"({result['program']}, {result['plan_type']}, {result['version']}); "
                f"candidates={sorted(candidate_degrees)!r}"
            )
        result["degree"] = next(iter(candidate_degrees))
    elif result["degree"] not in candidate_degrees:
        raise VerificationInputError(
            f"{code}: scope degree {result['degree']!r} is not present in programs; "
            f"candidates={sorted(candidate_degrees)!r}"
        )

    exact_programs = [
        program
        for program in candidates
        if str(program.get("degree", "")) == result["degree"]
    ]
    if len(exact_programs) != 1:
        raise VerificationInputError(
            f"{code}: normalized scope does not resolve to exactly one program: {result!r}"
        )
    if not course_matches(exact_programs[0], code, title):
        raise VerificationInputError(
            f"{code}: scope {result!r} has no exact code + normalized-title match in programs"
        )
    return result


def scopes_for_variant(
    *,
    code: str,
    variant: Dict[str, Any],
    is_legacy_direct: bool,
    programs: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    has_scope = "scope" in variant
    has_scopes = "scopes" in variant
    if has_scope and has_scopes:
        raise VerificationInputError(f"{code}: variant has both scope and scopes")

    if has_scopes:
        raw_scopes = variant["scopes"]
        if not isinstance(raw_scopes, list):
            raise VerificationInputError(f"{code}: scopes must be a list")
    elif has_scope:
        if not isinstance(variant["scope"], dict):
            raise VerificationInputError(f"{code}: scope must be an object")
        raw_scopes = [variant["scope"]]
    elif "catalog_id" in variant:
        raw_scopes = []
    elif is_legacy_direct:
        inferred = {
            normalized_scope_sort_key(program_scope(program)): program_scope(program)
            for program in programs
            if course_matches(program, code, variant.get("title", ""))
        }
        if not inferred:
            raise VerificationInputError(
                f"{code}: legacy direct record has no exact code + normalized-title program match"
            )
        return [inferred[key] for key in sorted(inferred)]
    else:
        raise VerificationInputError(
            f"{code}: non-catalog variant has neither scope nor scopes"
        )

    if not raw_scopes and "catalog_id" not in variant:
        raise VerificationInputError(
            f"{code}: only catalog_id variants may have an empty scopes list"
        )

    normalized = [
        normalize_scope(
            scope,
            code=code,
            title=variant.get("title", ""),
            programs=programs,
        )
        for scope in raw_scopes
    ]
    by_key: Dict[Tuple[str, str, str, str], Dict[str, str]] = {}
    for scope in normalized:
        key = normalized_scope_sort_key(scope)
        if key in by_key:
            raise VerificationInputError(f"{code}: duplicate scope {scope!r}")
        by_key[key] = scope
    return [by_key[key] for key in sorted(by_key)]


def rebuild_expected_variants(
    data: Dict[str, Any],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
    course_details = data.get("course_details")
    programs = data.get("programs")
    if not isinstance(course_details, dict):
        raise VerificationInputError("data.json course_details must be an object")
    if not isinstance(programs, list) or not all(
        isinstance(item, dict) for item in programs
    ):
        raise VerificationInputError("data.json programs must be a list of objects")

    expected: Dict[str, List[Dict[str, Any]]] = {}
    legacy_records = 0
    legacy_scopes = 0
    total_scopes = 0
    for raw_code, detail in course_details.items():
        code = str(raw_code)
        if not isinstance(detail, dict):
            raise VerificationInputError(
                f"{code}: course_details entry must be an object"
            )
        is_legacy_direct = "variants" not in detail
        if is_legacy_direct:
            legacy_records += 1
            variants = [detail]
        else:
            variants = detail.get("variants")
            if not isinstance(variants, list) or not variants:
                raise VerificationInputError(
                    f"{code}: variants must be a non-empty list"
                )

        built: List[Dict[str, Any]] = []
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                raise VerificationInputError(
                    f"{code}: variant {index} must be an object"
                )
            source_pdf = variant.get("pdf_url")
            if not isinstance(source_pdf, str) or not source_pdf:
                raise VerificationInputError(f"{code}: variant {index} has no pdf_url")
            catalog = {
                field: variant[field] for field in CATALOG_FIELDS if field in variant
            }
            scopes = scopes_for_variant(
                code=code,
                variant=variant,
                is_legacy_direct=is_legacy_direct,
                programs=programs,
            )
            if is_legacy_direct:
                legacy_scopes += len(scopes)
            total_scopes += len(scopes)
            built.append(
                {
                    "variant_id": variant_identity(code, source_pdf, scopes, catalog),
                    "scopes": scopes,
                    "catalog": catalog,
                    "source_pdf": source_pdf,
                }
            )
        expected[code] = built

    expected_ids = [
        variant["variant_id"] for variants in expected.values() for variant in variants
    ]
    if len(expected_ids) != len(set(expected_ids)):
        raise VerificationInputError(
            "normalized data.json produces duplicate logical variant IDs"
        )

    stats = {
        "courses": len(expected),
        "variants": sum(len(items) for items in expected.values()),
        "scopes": total_scopes,
        "legacy_records": legacy_records,
        "legacy_scopes": legacy_scopes,
    }
    return expected, stats


def safe_repository_path(
    root: Path,
    raw_path: Any,
    label: str,
    errors: ErrorCollector,
) -> Optional[Path]:
    if not isinstance(raw_path, str) or not raw_path:
        errors.add(f"{label}: path must be a non-empty string")
        return None
    if "\\" in raw_path:
        errors.add(f"{label}: path must use POSIX separators: {raw_path!r}")
        return None
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        errors.add(f"{label}: unsafe repository-relative path: {raw_path!r}")
        return None
    if pure.as_posix() != raw_path:
        errors.add(f"{label}: path is not canonical: {raw_path!r}")
        return None
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        errors.add(f"{label}: path escapes the repository: {raw_path!r}")
        return None
    return candidate


def validate_sha256(value: Any, label: str, errors: ErrorCollector) -> bool:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        errors.add(f"{label}: sha256 must be 64 lowercase hexadecimal characters")
        return False
    return True


def validate_file_record(
    record: Any,
    *,
    root: Path,
    label: str,
    hash_cache: Dict[Path, str],
    errors: ErrorCollector,
    expected_path: Optional[str] = None,
) -> Optional[str]:
    if not isinstance(record, dict):
        errors.add(f"{label}: expected an object with path and sha256")
        return None
    raw_path = record.get("path")
    if expected_path is not None and raw_path != expected_path:
        errors.add(f"{label}.path: expected {expected_path!r}, found {raw_path!r}")
    path = safe_repository_path(root, raw_path, f"{label}.path", errors)
    digest_value = record.get("sha256")
    digest_valid = validate_sha256(digest_value, f"{label}.sha256", errors)
    if path is None:
        return raw_path if isinstance(raw_path, str) else None
    if not path.is_file():
        errors.add(f"{label}: referenced file does not exist: {raw_path!r}")
        return raw_path if isinstance(raw_path, str) else None
    try:
        actual_digest = sha256_file(path, hash_cache)
    except VerificationInputError as exc:
        errors.add(str(exc))
        return raw_path if isinstance(raw_path, str) else None
    if digest_valid and digest_value != actual_digest:
        errors.add(
            f"{label}: sha256 mismatch for {raw_path!r}; "
            f"recorded={digest_value}, actual={actual_digest}"
        )
    return raw_path if isinstance(raw_path, str) else None


def validate_generated_metadata(
    outcomes: Dict[str, Any],
    root: Path,
    hash_cache: Dict[Path, str],
    errors: ErrorCollector,
) -> None:
    validate_exact_fields(outcomes, ROOT_FIELDS, "root", errors)
    if outcomes.get("schema_version") != SCHEMA_VERSION:
        errors.add(
            f"schema_version: expected {SCHEMA_VERSION!r}, "
            f"found {outcomes.get('schema_version')!r}"
        )

    generated_at = outcomes.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        errors.add("generated_at: expected a non-empty ISO-8601 string")
    else:
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                errors.add("generated_at: ISO-8601 timestamp must include a timezone")
        except ValueError:
            errors.add(f"generated_at: invalid ISO-8601 timestamp {generated_at!r}")

    extractor = outcomes.get("extractor")
    if not isinstance(extractor, dict):
        errors.add("extractor: expected an object")
        return
    validate_exact_fields(extractor, EXTRACTOR_FIELDS, "extractor", errors)
    for field in ("name", "version", "pdfplumber", "pymupdf"):
        value = extractor.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.add(f"extractor.{field}: expected a non-empty string")
    tesseract = extractor.get("tesseract")
    if tesseract is not None and (
        not isinstance(tesseract, str) or not tesseract.strip()
    ):
        errors.add("extractor.tesseract: expected a non-empty string or null")
    if extractor.get("name") != EXTRACTOR_NAME:
        errors.add(
            f"extractor.name: expected {EXTRACTOR_NAME!r}, found "
            f"{extractor.get('name')!r}"
        )
    if extractor.get("version") != EXTRACTOR_VERSION:
        errors.add(
            f"extractor.version: expected {EXTRACTOR_VERSION!r}, found "
            f"{extractor.get('version')!r}"
        )
    script = extractor.get("script")
    if script != "scripts/extract_course_outcomes.py":
        errors.add("extractor.script: expected 'scripts/extract_course_outcomes.py'")
    script_path = safe_repository_path(root, script, "extractor.script", errors)
    digest = extractor.get("script_sha256")
    digest_valid = validate_sha256(digest, "extractor.script_sha256", errors)
    if script_path is not None:
        if not script_path.is_file():
            errors.add("extractor.script: recorded extractor script does not exist")
        else:
            try:
                actual = sha256_file(script_path, hash_cache)
                if digest_valid and digest != actual:
                    errors.add(
                        "extractor.script_sha256: mismatch with the current extractor script"
                    )
            except VerificationInputError as exc:
                errors.add(str(exc))

    font_recovery_script = extractor.get("font_recovery_script")
    if font_recovery_script != "scripts/pdf_font_recovery.py":
        errors.add(
            "extractor.font_recovery_script: expected 'scripts/pdf_font_recovery.py'"
        )
    font_recovery_path = safe_repository_path(
        root,
        font_recovery_script,
        "extractor.font_recovery_script",
        errors,
    )
    font_recovery_digest = extractor.get("font_recovery_script_sha256")
    font_recovery_digest_valid = validate_sha256(
        font_recovery_digest,
        "extractor.font_recovery_script_sha256",
        errors,
    )
    if font_recovery_path is not None:
        if not font_recovery_path.is_file():
            errors.add(
                "extractor.font_recovery_script: recorded helper script does not exist"
            )
        else:
            try:
                actual = sha256_file(font_recovery_path, hash_cache)
                if font_recovery_digest_valid and font_recovery_digest != actual:
                    errors.add(
                        "extractor.font_recovery_script_sha256: mismatch with the "
                        "current helper script"
                    )
            except VerificationInputError as exc:
                errors.add(str(exc))


def validate_page_number(
    value: Any,
    label: str,
    errors: ErrorCollector,
    page_count: Optional[int],
) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        errors.add(f"{label}: source_page must be a positive integer")
        return False
    if page_count is not None and value > page_count:
        errors.add(f"{label}: source_page {value} exceeds page_count {page_count}")
        return False
    return True


def is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def validate_exact_fields(
    value: Dict[str, Any],
    expected: Set[str],
    label: str,
    errors: ErrorCollector,
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        errors.add(f"{label}: missing fields {sorted(missing)!r}")
    if extra:
        errors.add(f"{label}: unexpected fields {sorted(extra)!r}")


def validate_nonempty_nullable_string(
    value: Any,
    label: str,
    errors: ErrorCollector,
) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not value.strip():
        errors.add(f"{label}: expected a non-empty string or null")
        return False
    return True


def validate_normalized_extracted_strings(
    value: Any, label: str, errors: ErrorCollector
) -> None:
    if isinstance(value, str):
        if "\u00a0" in value:
            errors.add(
                f"{label}: extracted text contains U+00A0 instead of a normal space"
            )
        if CID_RE.search(value):
            errors.add(f"{label}: extracted value still contains a (cid:N) placeholder")
        if ARABIC_DIGIT_RE.search(value):
            errors.add(
                f"{label}: extracted value contains an unnormalized Arabic digit"
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "warnings":
                continue
            validate_normalized_extracted_strings(item, f"{label}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_normalized_extracted_strings(item, f"{label}[{index}]", errors)


def validate_extracted(
    value: Any,
    scopes: Any,
    label: str,
    errors: ErrorCollector,
    *,
    source_sha256: Any = None,
) -> None:
    if not isinstance(value, dict):
        errors.add(f"{label}: extracted must be an object")
        return
    validate_exact_fields(value, EXTRACTED_FIELDS, label, errors)

    page_count_value = value.get("page_count")
    if page_count_value is None:
        page_count: Optional[int] = None
    elif (
        isinstance(page_count_value, bool)
        or not isinstance(page_count_value, int)
        or page_count_value < 1
    ):
        errors.add(f"{label}.page_count: expected a positive integer or null")
        page_count = None
    else:
        page_count = page_count_value

    source_row_count_value = value.get("source_clo_row_count")
    if source_row_count_value is None:
        source_row_count: Optional[int] = None
    elif (
        isinstance(source_row_count_value, bool)
        or not isinstance(source_row_count_value, int)
        or source_row_count_value < 0
    ):
        errors.add(
            f"{label}.source_clo_row_count: expected a non-negative integer or null"
        )
        source_row_count = None
    else:
        source_row_count = source_row_count_value

    captured_row_count_value = value.get("captured_clo_row_count")
    if (
        isinstance(captured_row_count_value, bool)
        or not isinstance(captured_row_count_value, int)
        or captured_row_count_value < 0
    ):
        errors.add(f"{label}.captured_clo_row_count: expected a non-negative integer")
        captured_row_count: Optional[int] = None
    else:
        captured_row_count = captured_row_count_value

    course_name = value.get("course_name")
    validate_nonempty_nullable_string(course_name, f"{label}.course_name", errors)

    name_metadata = value.get("course_name_metadata")
    if not isinstance(name_metadata, dict):
        errors.add(f"{label}.course_name_metadata: expected an object")
    else:
        metadata_label = f"{label}.course_name_metadata"
        validate_exact_fields(
            name_metadata, COURSE_NAME_METADATA_FIELDS, metadata_label, errors
        )
        title_confidence = name_metadata.get("confidence")
        title_method = name_metadata.get("extraction_method")
        if title_confidence not in CONFIDENCE_VALUES:
            errors.add(
                f"{metadata_label}.confidence: expected one of "
                f"{sorted(CONFIDENCE_VALUES)!r}"
            )
        if title_method not in TITLE_METHODS:
            errors.add(
                f"{metadata_label}.extraction_method: expected one of "
                f"{sorted(TITLE_METHODS)!r}"
            )
        if "source_page" in name_metadata:
            validate_page_number(
                name_metadata["source_page"], metadata_label, errors, page_count
            )
            if name_metadata["source_page"] != 1:
                errors.add(
                    f"{metadata_label}.source_page: course name must come from page 1"
                )
        if course_name is None:
            if title_confidence != "low" or title_method != "unresolved":
                errors.add(
                    f"{metadata_label}: a null course_name requires low/unresolved metadata"
                )
        elif title_confidence != {
            "geometric_pdf": "high",
            "page_ocr": "medium",
            "geometric_pdf_ocr_consensus": "medium",
        }.get(title_method):
            errors.add(
                f"{metadata_label}: confidence does not match the course-name "
                "extraction method"
            )

    clos = value.get("clos")
    valid_clos: List[Dict[str, Any]] = []
    clo_codes: List[str] = []
    if not isinstance(clos, list):
        errors.add(f"{label}.clos: expected a list")
    else:
        for index, clo in enumerate(clos):
            clo_label = f"{label}.clos[{index}]"
            if not isinstance(clo, dict):
                errors.add(f"{clo_label}: expected an object")
                continue
            valid_clos.append(clo)
            missing_clo_fields = CLO_FIELDS - set(clo)
            extra_clo_fields = set(clo) - (CLO_FIELDS | {"source_code"})
            if missing_clo_fields:
                errors.add(
                    f"{clo_label}: missing fields {sorted(missing_clo_fields)!r}"
                )
            if extra_clo_fields:
                errors.add(
                    f"{clo_label}: unexpected fields {sorted(extra_clo_fields)!r}"
                )

            code = clo.get("code")
            if code is None:
                source_code = clo.get("source_code")
                if source_code is not None and (
                    not isinstance(source_code, str)
                    or not SOURCE_CLO_MARKER_RE.fullmatch(source_code)
                ):
                    errors.add(
                        f"{clo_label}.source_code: expected null/absent for an "
                        "unreadable source cell, or a literal marker such as "
                        "'...' or '3...'"
                    )
            elif not isinstance(code, str) or not CLO_CODE_RE.fullmatch(code):
                errors.add(
                    f"{clo_label}.code: expected a published non-placeholder CLO "
                    "code such as '1.1' or 'ع1', or null for a source ellipsis"
                )
            else:
                clo_codes.append(code)
                if "source_code" in clo:
                    errors.add(
                        f"{clo_label}.source_code: allowed only when code is null"
                    )

            text = clo.get("text")
            validate_nonempty_nullable_string(text, f"{clo_label}.text", errors)
            clo_source_status = clo.get("source_status")
            if clo_source_status not in SOURCE_STATUSES:
                errors.add(
                    f"{clo_label}.source_status: expected one of "
                    f"{sorted(SOURCE_STATUSES)!r}"
                )
            elif text is not None and clo_source_status != "present":
                errors.add(
                    f"{clo_label}.source_status: a non-null CLO text requires 'present'"
                )
            elif text is None and clo_source_status == "present":
                errors.add(
                    f"{clo_label}.source_status: a null CLO text requires "
                    "'source_blank' or 'unreadable'"
                )
            assessment = clo.get("assessment")
            validate_nonempty_nullable_string(
                assessment, f"{clo_label}.assessment", errors
            )
            assessment_source_page = clo.get("assessment_source_page")
            if assessment is None:
                if assessment_source_page is not None:
                    errors.add(
                        f"{clo_label}.assessment_source_page: must be null when "
                        "assessment is null"
                    )
            elif assessment_source_page is None:
                errors.add(
                    f"{clo_label}.assessment_source_page: a non-null assessment "
                    "requires its source page"
                )
            else:
                validate_page_number(
                    assessment_source_page,
                    f"{clo_label}.assessment_source_page",
                    errors,
                    page_count,
                )

            confidence = clo.get("confidence")
            if confidence not in CONFIDENCE_VALUES:
                errors.add(
                    f"{clo_label}.confidence: expected one of "
                    f"{sorted(CONFIDENCE_VALUES)!r}"
                )
            if "source_page" not in clo:
                errors.add(f"{clo_label}: missing source_page")
                clo_page: Optional[int] = None
            else:
                clo_page = (
                    clo["source_page"]
                    if validate_page_number(
                        clo["source_page"], clo_label, errors, page_count
                    )
                    else None
                )
            method = clo.get("extraction_method")
            if method not in CLO_METHODS:
                errors.add(
                    f"{clo_label}.extraction_method: expected one of "
                    f"{sorted(CLO_METHODS)!r}"
                )
            elif (
                method in EMBEDDED_FONT_CMAP_METHODS
                and source_sha256 != EMBEDDED_FONT_CMAP_SOURCE_SHA256
            ):
                errors.add(
                    f"{clo_label}.extraction_method: {method!r} is permitted only "
                    "for the reviewed embedded-font source_sha256 "
                    f"{EMBEDDED_FONT_CMAP_SOURCE_SHA256!r}, found "
                    f"{source_sha256!r}"
                )
            expected_clo_confidence = {
                "geometric_pdf": "medium",
                "geometric_pdf_ocr_consensus": "medium",
                "embedded_font_cmap": "high",
                "embedded_font_cmap_with_geometric_continuation": "medium",
                "plain_table": "low",
                "plain_cell_fallback": "low",
                "targeted_ocr": "medium",
                "hash_matched_manifest": "high",
            }.get(method)
            if text is None and confidence != "low":
                errors.add(
                    f"{clo_label}.confidence: a null CLO text requires low confidence"
                )
            elif (
                text is not None
                and expected_clo_confidence is not None
                and confidence != expected_clo_confidence
            ):
                errors.add(
                    f"{clo_label}.confidence: {method} text requires "
                    f"{expected_clo_confidence} confidence"
                )

            mappings = clo.get("plo_mappings")
            expected_scopes = scopes if isinstance(scopes, list) else []
            if not isinstance(mappings, list):
                errors.add(f"{clo_label}.plo_mappings: expected a list")
            else:
                if len(mappings) != len(expected_scopes):
                    errors.add(
                        f"{clo_label}.plo_mappings: expected exactly one mapping for "
                        f"each of {len(expected_scopes)} scopes, found {len(mappings)}"
                    )
                for mapping_index, mapping in enumerate(mappings):
                    mapping_label = f"{clo_label}.plo_mappings[{mapping_index}]"
                    if not isinstance(mapping, dict):
                        errors.add(f"{mapping_label}: expected an object")
                        continue
                    validate_exact_fields(
                        mapping, PLO_MAPPING_FIELDS, mapping_label, errors
                    )
                    scope = mapping.get("scope")
                    if not isinstance(scope, dict):
                        errors.add(f"{mapping_label}.scope: expected an object")
                    else:
                        validate_exact_fields(
                            scope, set(SCOPE_FIELDS), f"{mapping_label}.scope", errors
                        )
                        if mapping_index >= len(expected_scopes):
                            errors.add(
                                f"{mapping_label}.scope: no corresponding variant scope"
                            )
                        elif scope != expected_scopes[mapping_index]:
                            errors.add(
                                f"{mapping_label}.scope: expected scope "
                                f"{expected_scopes[mapping_index]!r}, found {scope!r}"
                            )
                    plo_codes = mapping.get("plo_codes")
                    valid_plo_codes = True
                    if plo_codes is not None and not isinstance(plo_codes, list):
                        errors.add(
                            f"{mapping_label}.plo_codes: expected an array or null"
                        )
                        valid_plo_codes = False
                    elif isinstance(plo_codes, list):
                        seen_plo_codes: Set[str] = set()
                        for plo_index, plo_code in enumerate(plo_codes):
                            if not isinstance(
                                plo_code, str
                            ) or not PLO_CODE_RE.fullmatch(plo_code):
                                errors.add(
                                    f"{mapping_label}.plo_codes[{plo_index}]: expected "
                                    "a normalized PLO code"
                                )
                                valid_plo_codes = False
                            elif plo_code in seen_plo_codes:
                                errors.add(
                                    f"{mapping_label}.plo_codes[{plo_index}]: duplicate "
                                    f"{plo_code!r}"
                                )
                                valid_plo_codes = False
                            else:
                                seen_plo_codes.add(plo_code)
                    status = mapping.get("status")
                    if status not in MAPPING_STATUSES:
                        errors.add(
                            f"{mapping_label}.status: expected one of "
                            f"{sorted(MAPPING_STATUSES)!r}"
                        )
                    elif valid_plo_codes:
                        if status == "mapped" and not (
                            isinstance(plo_codes, list) and plo_codes
                        ):
                            errors.add(
                                f"{mapping_label}: status 'mapped' requires a non-empty "
                                "plo_codes array"
                            )
                        elif status == "explicitly_unmapped" and plo_codes != []:
                            errors.add(
                                f"{mapping_label}: status 'explicitly_unmapped' requires "
                                "an empty plo_codes array"
                            )
                        elif status not in {"mapped", "explicitly_unmapped"} and (
                            plo_codes is not None
                        ):
                            errors.add(
                                f"{mapping_label}: unresolved or non-applicable status "
                                "requires null plo_codes"
                            )
                    mapping_confidence = mapping.get("confidence")
                    if mapping_confidence not in CONFIDENCE_VALUES:
                        errors.add(
                            f"{mapping_label}.confidence: expected one of "
                            f"{sorted(CONFIDENCE_VALUES)!r}"
                        )
                    elif (
                        status in UNRESOLVED_MAPPING_STATUSES
                        and mapping_confidence != "low"
                    ):
                        errors.add(
                            f"{mapping_label}.confidence: unresolved mappings require low confidence"
                        )
                    elif (
                        status == "not_present_for_scope"
                        and mapping_confidence != "medium"
                    ):
                        errors.add(
                            f"{mapping_label}.confidence: not_present_for_scope requires medium confidence"
                        )
                    elif (
                        status in {"mapped", "explicitly_unmapped"}
                        and mapping_confidence == "low"
                    ):
                        errors.add(
                            f"{mapping_label}.confidence: resolved mappings cannot have low confidence"
                        )
                    if "source_page" in mapping:
                        validate_page_number(
                            mapping["source_page"], mapping_label, errors, page_count
                        )
                        if clo_page is not None and mapping["source_page"] != clo_page:
                            errors.add(
                                f"{mapping_label}.source_page: must equal its CLO page {clo_page}"
                            )
                    evidence = mapping.get("evidence")
                    if not isinstance(evidence, str) or not evidence.strip():
                        errors.add(
                            f"{mapping_label}.evidence: expected a non-empty string"
                        )

            document_plos = clo.get("document_plo_codes")
            if not isinstance(document_plos, list):
                errors.add(f"{clo_label}.document_plo_codes: expected a list")
            else:
                seen_document_plos: Set[str] = set()
                for plo_index, plo in enumerate(document_plos):
                    if not isinstance(plo, str) or not PLO_CODE_RE.fullmatch(plo):
                        errors.add(
                            f"{clo_label}.document_plo_codes[{plo_index}]: "
                            "expected a normalized PLO code"
                        )
                    elif plo in seen_document_plos:
                        errors.add(
                            f"{clo_label}.document_plo_codes[{plo_index}]: duplicate {plo!r}"
                        )
                    else:
                        seen_document_plos.add(plo)

        clo_pages = [
            clo.get("source_page")
            for clo in valid_clos
            if isinstance(clo.get("source_page"), int)
            and not isinstance(clo.get("source_page"), bool)
        ]
        if len(clo_pages) == len(clos) and clo_pages != sorted(clo_pages):
            errors.add(f"{label}.clos: records must be in source-page order")

        if (
            captured_row_count is not None
            and len(valid_clos) == len(clos)
            and captured_row_count != len(clos)
        ):
            errors.add(
                f"{label}.captured_clo_row_count: expected {len(clos)} from clos, "
                f"found {captured_row_count}"
            )
        if (
            source_row_count is not None
            and captured_row_count is not None
            and captured_row_count > source_row_count
        ):
            errors.add(
                f"{label}.source_clo_row_count: cannot be smaller than "
                f"captured_clo_row_count ({source_row_count} < {captured_row_count})"
            )

    source_status = value.get("source_status")
    if source_status not in SOURCE_STATUSES:
        errors.add(
            f"{label}.source_status: expected one of {sorted(SOURCE_STATUSES)!r}"
        )
    elif isinstance(clos, list) and len(valid_clos) == len(clos):
        row_source_statuses = {
            clo.get("source_status")
            for clo in valid_clos
            if clo.get("source_status") in SOURCE_STATUSES
        }
        if "unreadable" in row_source_statuses or not valid_clos:
            expected_source_status = "unreadable"
        elif "source_blank" in row_source_statuses:
            expected_source_status = "source_blank"
        else:
            expected_source_status = "present"
        if source_status != expected_source_status:
            errors.add(
                f"{label}.source_status: expected {expected_source_status!r} from "
                f"the CLO rows, found {source_status!r}"
            )

    assessment_plan = value.get("assessment_plan")
    valid_assessments: List[Dict[str, Any]] = []
    if not isinstance(assessment_plan, list):
        errors.add(f"{label}.assessment_plan: expected a list")
    else:
        for index, assessment in enumerate(assessment_plan):
            assessment_label = f"{label}.assessment_plan[{index}]"
            if not isinstance(assessment, dict):
                errors.add(f"{assessment_label}: expected an object")
                continue
            valid_assessments.append(assessment)
            validate_exact_fields(
                assessment, ASSESSMENT_FIELDS, assessment_label, errors
            )
            item_label = assessment.get("label")
            validate_nonempty_nullable_string(
                item_label, f"{assessment_label}.label", errors
            )
            weight = assessment.get("weight")
            if weight is not None and not is_finite_number(weight):
                errors.add(
                    f"{assessment_label}.weight: expected a finite number or null"
                )
            elif weight is not None and not 0 < weight <= 100:
                errors.add(
                    f"{assessment_label}.weight: expected a value greater than 0 and at most 100"
                )
            assessment_confidence = assessment.get("confidence")
            if assessment_confidence not in CONFIDENCE_VALUES:
                errors.add(
                    f"{assessment_label}.confidence: expected one of "
                    f"{sorted(CONFIDENCE_VALUES)!r}"
                )
            if (
                item_label is None or weight is None
            ) and assessment_confidence != "low":
                errors.add(
                    f"{assessment_label}.confidence: a null label or weight requires low confidence"
                )
            elif (
                item_label is not None
                and weight is not None
                and assessment_confidence == "low"
            ):
                errors.add(
                    f"{assessment_label}.confidence: a complete assessment row cannot have low confidence"
                )
            if "source_page" not in assessment:
                errors.add(f"{assessment_label}: missing source_page")
            else:
                validate_page_number(
                    assessment["source_page"], assessment_label, errors, page_count
                )

        assessment_pages = [
            item.get("source_page")
            for item in valid_assessments
            if isinstance(item.get("source_page"), int)
            and not isinstance(item.get("source_page"), bool)
        ]
        if len(assessment_pages) == len(assessment_plan) and assessment_pages != sorted(
            assessment_pages
        ):
            errors.add(f"{label}.assessment_plan: records must be in source-page order")

    all_plan_weights_valid = bool(valid_assessments) and all(
        is_finite_number(item.get("weight")) for item in valid_assessments
    )
    calculated_total: Optional[float] = (
        sum(float(item["weight"]) for item in valid_assessments)
        if all_plan_weights_valid
        else None
    )
    recorded_total = value.get("assessment_plan_total")
    if recorded_total is not None and not is_finite_number(recorded_total):
        errors.add(f"{label}.assessment_plan_total: expected a finite number or null")
    elif calculated_total is None:
        if recorded_total is not None:
            errors.add(
                f"{label}.assessment_plan_total: must be null when the plan is empty "
                "or has a null/invalid weight"
            )
    elif recorded_total is None or float(recorded_total) != calculated_total:
        errors.add(
            f"{label}.assessment_plan_total: expected recomputed total "
            f"{calculated_total:g}, found {recorded_total!r}"
        )

    plan_complete = value.get("assessment_plan_complete")
    if not isinstance(plan_complete, bool):
        errors.add(f"{label}.assessment_plan_complete: expected a boolean")
    expected_plan_complete = (
        bool(valid_assessments)
        and all(item.get("label") is not None for item in valid_assessments)
        and calculated_total is not None
        and abs(calculated_total - 100.0) <= 0.01
    )
    if isinstance(plan_complete, bool) and plan_complete != expected_plan_complete:
        errors.add(
            f"{label}.assessment_plan_complete: expected {expected_plan_complete} "
            "from the recorded assessment rows"
        )

    warnings = value.get("warnings")
    valid_warnings: List[Dict[str, Any]] = []
    if not isinstance(warnings, list):
        errors.add(f"{label}.warnings: expected a list")
    else:
        for index, warning in enumerate(warnings):
            warning_label = f"{label}.warnings[{index}]"
            if not isinstance(warning, dict):
                errors.add(f"{warning_label}: expected an object")
                continue
            valid_warnings.append(warning)
            allowed_warning_fields = WARNING_REQUIRED_FIELDS | WARNING_OPTIONAL_FIELDS
            missing_warning_fields = WARNING_REQUIRED_FIELDS - set(warning)
            extra_warning_fields = set(warning) - allowed_warning_fields
            if missing_warning_fields:
                errors.add(
                    f"{warning_label}: missing fields {sorted(missing_warning_fields)!r}"
                )
            if extra_warning_fields:
                errors.add(
                    f"{warning_label}: unexpected fields {sorted(extra_warning_fields)!r}"
                )
            warning_code = warning.get("code")
            if not isinstance(warning_code, str) or not WARNING_CODE_RE.fullmatch(
                warning_code
            ):
                errors.add(f"{warning_label}.code: expected a snake_case warning code")
            message = warning.get("message")
            if not isinstance(message, str) or not message.strip():
                errors.add(f"{warning_label}.message: expected a non-empty string")
            if "source_page" in warning:
                validate_page_number(
                    warning["source_page"], warning_label, errors, page_count
                )
            if "clo_code" in warning:
                warning_clo = warning["clo_code"]
                if not isinstance(warning_clo, str) or not CLO_CODE_RE.fullmatch(
                    warning_clo
                ):
                    errors.add(
                        f"{warning_label}.clo_code: expected a normalized CLO code"
                    )
            if "clo_index" in warning:
                warning_index = warning["clo_index"]
                if (
                    isinstance(warning_index, bool)
                    or not isinstance(warning_index, int)
                    or warning_index < 0
                    or not isinstance(clos, list)
                    or warning_index >= len(clos)
                ):
                    errors.add(
                        f"{warning_label}.clo_index: expected a valid zero-based CLO index"
                    )
                elif isinstance(clos[warning_index], dict):
                    target = clos[warning_index]
                    if "source_page" in warning and warning.get(
                        "source_page"
                    ) != target.get("source_page"):
                        errors.add(
                            f"{warning_label}.source_page: must match the indexed CLO"
                        )
                    if "clo_code" in warning and warning.get("clo_code") != target.get(
                        "code"
                    ):
                        errors.add(
                            f"{warning_label}.clo_code: must match the indexed CLO"
                        )

        warning_keys: List[str] = []
        for warning in valid_warnings:
            try:
                warning_keys.append(canonical_json(warning))
            except (TypeError, ValueError):
                warning_keys.append(repr(warning))
        if len(warning_keys) != len(set(warning_keys)):
            errors.add(f"{label}.warnings: duplicate warning records are not allowed")
        warning_order = sorted(
            valid_warnings,
            key=lambda item: (
                item.get("source_page")
                if isinstance(item.get("source_page"), int)
                and not isinstance(item.get("source_page"), bool)
                else 0,
                item.get("clo_index")
                if isinstance(item.get("clo_index"), int)
                and not isinstance(item.get("clo_index"), bool)
                else -1,
                item.get("clo_code") if isinstance(item.get("clo_code"), str) else "",
                item.get("code") if isinstance(item.get("code"), str) else "",
                item.get("message") if isinstance(item.get("message"), str) else "",
            ),
        )
        if len(valid_warnings) == len(warnings) and valid_warnings != warning_order:
            errors.add(f"{label}.warnings: warning records are not in canonical order")

    warning_codes_by_index = {
        (warning.get("code"), warning.get("clo_index")) for warning in valid_warnings
    }
    has_pdf_failure = any(
        warning.get("code") == "pdf_extraction_failed" for warning in valid_warnings
    )
    if (
        course_name is None
        and not has_pdf_failure
        and not any(
            warning.get("code") == "course_name_unresolved"
            for warning in valid_warnings
        )
    ):
        errors.add(f"{label}.warnings: null course_name is not explained by a warning")
    if (
        isinstance(clos, list)
        and not clos
        and not has_pdf_failure
        and not any(
            warning.get("code") == "course_outcomes_missing"
            for warning in valid_warnings
        )
    ):
        errors.add(f"{label}.warnings: empty clos is not explained by a warning")
    for clo_index, clo in enumerate(valid_clos):
        code = clo.get("code")
        if code is None:
            expected_code_warning = (
                "clo_code_missing_in_source"
                if isinstance(clo.get("source_code"), str) and clo.get("source_code")
                else "clo_code_unreadable"
            )
            if (expected_code_warning, clo_index) not in warning_codes_by_index:
                errors.add(
                    f"{label}.warnings: null CLO code at index {clo_index} requires "
                    f"{expected_code_warning}"
                )
        if clo.get("text") is None and not has_pdf_failure:
            expected_text_warning = (
                "clo_text_blank_in_source"
                if clo.get("source_status") == "source_blank"
                else "clo_text_unreadable"
            )
            if (expected_text_warning, clo_index) not in warning_codes_by_index:
                errors.add(
                    f"{label}.warnings: null text for CLO index {clo_index} "
                    f"requires {expected_text_warning}"
                )
        mappings = clo.get("plo_mappings")
        if (
            isinstance(mappings, list)
            and any(
                isinstance(mapping, dict)
                and mapping.get("status") in UNRESOLVED_MAPPING_STATUSES
                for mapping in mappings
            )
            and ("plo_mapping_unresolved", clo_index) not in warning_codes_by_index
        ):
            errors.add(
                f"{label}.warnings: unresolved PLO mapping for CLO index {clo_index} is unexplained"
            )
        if (
            clo.get("assessment") is None
            and not has_pdf_failure
            and (
                "direct_assessment_unresolved",
                clo_index,
            )
            not in warning_codes_by_index
        ):
            errors.add(
                f"{label}.warnings: null direct assessment for CLO index {clo_index} is unexplained"
            )

    targeted_warning_codes = {
        "clo_text_blank_in_source",
        "clo_text_unreadable",
        "plo_mapping_unresolved",
        "direct_assessment_unresolved",
        "clo_code_missing_in_source",
        "clo_code_unreadable",
        "duplicate_source_clo_code",
        "plo_numeric_text_untrusted",
    }
    for warning_index, warning in enumerate(valid_warnings):
        warning_code = warning.get("code")
        if warning_code not in targeted_warning_codes:
            continue
        target_index = warning.get("clo_index")
        if (
            isinstance(target_index, bool)
            or not isinstance(target_index, int)
            or target_index < 0
            or target_index >= len(valid_clos)
        ):
            errors.add(
                f"{label}.warnings[{warning_index}]: {warning_code} requires clo_index"
            )
            continue
        target = valid_clos[target_index]
        mappings = target.get("plo_mappings")
        unresolved = isinstance(mappings, list) and any(
            isinstance(mapping, dict)
            and mapping.get("status") in UNRESOLVED_MAPPING_STATUSES
            for mapping in mappings
        )
        consistent = {
            "clo_text_blank_in_source": target.get("text") is None
            and target.get("source_status") == "source_blank",
            "clo_text_unreadable": target.get("text") is None
            and target.get("source_status") == "unreadable",
            "plo_mapping_unresolved": unresolved,
            "direct_assessment_unresolved": target.get("assessment") is None,
            "clo_code_missing_in_source": target.get("code") is None
            and isinstance(target.get("source_code"), str)
            and bool(target.get("source_code")),
            "clo_code_unreadable": target.get("code") is None
            and "source_code" not in target,
            "duplicate_source_clo_code": target.get("code") is not None,
            "plo_numeric_text_untrusted": unresolved,
        }[warning_code]
        if not consistent:
            errors.add(
                f"{label}.warnings[{warning_index}]: {warning_code} contradicts "
                f"the indexed CLO"
            )

    duplicate_groups: Dict[str, List[int]] = {}
    for clo_index, clo in enumerate(valid_clos):
        code = clo.get("code")
        if isinstance(code, str):
            duplicate_groups.setdefault(code, []).append(clo_index)
    duplicate_groups = {
        code: indexes for code, indexes in duplicate_groups.items() if len(indexes) > 1
    }
    for code, indexes in duplicate_groups.items():
        warned = {
            warning.get("clo_index")
            for warning in valid_warnings
            if warning.get("code") == "duplicate_source_clo_code"
            and warning.get("clo_code") == code
        }
        if warned != set(indexes):
            errors.add(
                f"{label}.clos: duplicate source code {code!r} requires an indexed "
                "duplicate_source_clo_code warning for every row"
            )
        texts = [
            normalize_arabic_identity(valid_clos[index].get("text"))
            for index in indexes
        ]
        pages = {valid_clos[index].get("source_page") for index in indexes}
        if any(not text for text in texts) or len(texts) != len(set(texts)):
            errors.add(
                f"{label}.clos: duplicate source code {code!r} rows must have distinct "
                "substantive texts"
            )
        integer_pages = {
            page
            for page in pages
            if isinstance(page, int) and not isinstance(page, bool)
        }
        if (
            len(integer_pages) != len(pages)
            or len(integer_pages) > 2
            or (
                len(integer_pages) == 2 and max(integer_pages) - min(integer_pages) != 1
            )
        ):
            errors.add(
                f"{label}.clos: duplicate source code {code!r} rows must be on "
                "one source page or its immediately adjacent continuation page"
            )
    if (
        isinstance(assessment_plan, list)
        and not assessment_plan
        and not has_pdf_failure
        and not any(
            warning.get("code") == "assessment_plan_missing"
            for warning in valid_warnings
        )
    ):
        errors.add(f"{label}.warnings: empty assessment_plan is not explained")
    for index, assessment in enumerate(valid_assessments):
        assessment_page = assessment.get("source_page")
        if assessment.get("label") is None and not any(
            warning.get("code")
            in {"assessment_label_unresolved", "assessment_label_unreadable"}
            and warning.get("source_page") == assessment_page
            for warning in valid_warnings
        ):
            errors.add(
                f"{label}.warnings: null label for assessment_plan[{index}] "
                f"on page {assessment_page!r} is unexplained"
            )
        if assessment.get("weight") is None and not any(
            warning.get("code")
            in {"assessment_weight_conflict", "assessment_weight_ocr_failed"}
            and (
                "source_page" not in warning
                or warning.get("source_page") == assessment_page
            )
            for warning in valid_warnings
        ):
            errors.add(
                f"{label}.warnings: null weight for assessment_plan[{index}] "
                f"on page {assessment_page!r} is unexplained"
            )
    if (
        calculated_total is not None
        and abs(calculated_total - 100.0) > 0.01
        and not any(
            warning.get("code")
            in {
                "assessment_plan_total_not_100",
                "assessment_plan_source_total_not_100",
            }
            for warning in valid_warnings
        )
    ):
        errors.add(
            f"{label}.warnings: assessment plan total {calculated_total:g} "
            "is not 100 and is unexplained"
        )
    if (
        isinstance(scopes, list)
        and not scopes
        and not has_pdf_failure
        and not any(
            warning.get("code") == "variant_scope_unresolved"
            for warning in valid_warnings
        )
    ):
        errors.add(
            f"{label}.warnings: an unscoped catalog variant requires "
            "variant_scope_unresolved"
        )

    extraction_status = value.get("extraction_status")
    if extraction_status not in EXTRACTION_STATUSES:
        errors.add(
            f"{label}.extraction_status: expected one of "
            f"{sorted(EXTRACTION_STATUSES)!r}"
        )
    if has_pdf_failure:
        if extraction_status != "failed":
            errors.add(
                f"{label}.warnings: pdf_extraction_failed is allowed only when "
                "extraction_status is 'failed'"
            )
        if page_count is not None:
            errors.add(
                f"{label}.warnings: pdf_extraction_failed requires a null page_count"
            )
        if course_name is not None:
            errors.add(
                f"{label}.warnings: pdf_extraction_failed requires a null course_name"
            )
        if isinstance(clos, list) and clos:
            errors.add(
                f"{label}.warnings: pdf_extraction_failed cannot accompany CLO records"
            )
        if isinstance(assessment_plan, list) and assessment_plan:
            errors.add(
                f"{label}.warnings: pdf_extraction_failed cannot accompany assessment rows"
            )
        if recorded_total is not None:
            errors.add(
                f"{label}.warnings: pdf_extraction_failed requires a null "
                "assessment_plan_total"
            )
        if plan_complete is not False:
            errors.add(
                f"{label}.warnings: pdf_extraction_failed requires "
                "assessment_plan_complete=false"
            )
        if source_row_count is not None:
            errors.add(
                f"{label}.source_clo_row_count: pdf_extraction_failed requires null"
            )
        if captured_row_count not in {None, 0}:
            errors.add(
                f"{label}.captured_clo_row_count: pdf_extraction_failed requires 0"
            )
        if source_status != "unreadable":
            errors.add(
                f"{label}.source_status: pdf_extraction_failed requires 'unreadable'"
            )

    # ``extraction_status`` answers one question only: did the extractor retain
    # every physical CLO row in the document?  Missing source text, assessment
    # cells, PLO mappings, titles, or assessment-plan values are represented by
    # their own fields and warnings and must not turn a complete row capture
    # into ``partial``.
    expected_status: Optional[str]
    if captured_row_count is None:
        expected_status = None
    elif captured_row_count == 0:
        expected_status = "failed"
    elif (
        source_row_count is not None
        and source_row_count > 0
        and captured_row_count == source_row_count
    ):
        expected_status = "complete"
    else:
        expected_status = "partial"

    row_count_warning_codes = {
        warning.get("code")
        for warning in valid_warnings
        if warning.get("code") in {"clo_row_count_unverified", "clo_row_count_mismatch"}
    }
    if expected_status == "partial":
        expected_count_warning = (
            "clo_row_count_unverified"
            if source_row_count is None
            else "clo_row_count_mismatch"
        )
        if expected_count_warning not in row_count_warning_codes:
            errors.add(
                f"{label}.warnings: partial row capture requires "
                f"{expected_count_warning}"
            )
    elif (
        expected_status == "failed"
        and not has_pdf_failure
        and source_row_count is not None
        and source_row_count > 0
        and "clo_row_count_mismatch" not in row_count_warning_codes
    ):
        errors.add(
            f"{label}.warnings: zero captured rows from a non-empty source requires "
            "clo_row_count_mismatch"
        )
    if extraction_status == "complete" and row_count_warning_codes:
        errors.add(
            f"{label}.warnings: complete extraction cannot carry a CLO row-count "
            "warning"
        )
    if (
        extraction_status in EXTRACTION_STATUSES
        and expected_status is not None
        and extraction_status != expected_status
    ):
        errors.add(
            f"{label}.extraction_status: expected {expected_status!r} from extracted data, "
            f"found {extraction_status!r}"
        )
    if extraction_status in {"partial", "failed"} and not valid_warnings:
        errors.add(
            f"{label}.warnings: {extraction_status} extraction must explain its gaps"
        )
    if page_count is None:
        if extraction_status != "failed":
            errors.add(
                f"{label}.page_count: null is allowed only for failed extraction"
            )
        if valid_clos or valid_assessments:
            errors.add(f"{label}.page_count: null cannot accompany source-page records")
        if not has_pdf_failure:
            errors.add(
                f"{label}.warnings: null page_count requires pdf_extraction_failed"
            )

    validate_normalized_extracted_strings(value, label, errors)


def parse_field_path(field: str) -> List[Any]:
    if not FIELD_PATH_RE.fullmatch(field):
        raise ValueError("invalid field-path syntax")
    tokens: List[Any] = []
    for match in FIELD_TOKEN_RE.finditer(field):
        key, index = match.groups()
        tokens.append(key if key is not None else int(index))
    return tokens


def resolve_field_path(root: Any, field: str) -> Any:
    current = root
    for token in parse_field_path(field):
        if isinstance(token, str):
            if not isinstance(current, dict) or token not in current:
                raise KeyError(token)
            current = current[token]
        else:
            if not isinstance(current, list) or token >= len(current):
                raise IndexError(token)
            current = current[token]
    return current


def validate_override_value(
    field: str,
    value: Any,
    label: str,
    errors: ErrorCollector,
) -> None:
    """Validate the small, value-only surface humans may override.

    Extraction provenance, statuses, warnings, identifiers, and containers are
    intentionally immutable.  In particular, a human PLO correction changes
    only the effective value; the automatic mapping status remains evidence of
    what the extractor itself did, while reason/author/date record the human
    provenance.
    """

    text_leaf = bool(
        field == "course_name"
        or re.fullmatch(r"clos\[\d+\]\.(?:text|assessment)", field)
        or re.fullmatch(r"assessment_plan\[\d+\]\.label", field)
    )
    code_leaf = bool(re.fullmatch(r"clos\[\d+\]\.code", field))
    plo_leaf = bool(re.fullmatch(r"clos\[\d+\]\.plo_mappings\[\d+\]\.plo_codes", field))
    weight_leaf = bool(re.fullmatch(r"assessment_plan\[\d+\]\.weight", field))
    if not (text_leaf or code_leaf or plo_leaf or weight_leaf):
        errors.add(
            f"{label}.field: only course_name, CLO code/text/assessment/PLO, "
            "and assessment label/weight leaves may be overridden"
        )
        return

    if text_leaf:
        if not validate_nonempty_nullable_string(value, f"{label}.value", errors):
            return
        validate_normalized_extracted_strings(value, f"{label}.value", errors)
        return
    if code_leaf:
        if value is not None and (
            not isinstance(value, str) or not CLO_CODE_RE.fullmatch(value)
        ):
            errors.add(f"{label}.value: expected a normalized CLO code or null")
        return
    if plo_leaf:
        if value is None:
            return
        if not isinstance(value, list):
            errors.add(f"{label}.value: expected a PLO-code array or null")
            return
        seen_codes: Set[str] = set()
        for index, code in enumerate(value):
            if not isinstance(code, str) or not PLO_CODE_RE.fullmatch(code):
                errors.add(f"{label}.value[{index}]: expected a normalized PLO code")
            elif code in seen_codes:
                errors.add(f"{label}.value[{index}]: duplicate PLO code {code!r}")
            else:
                seen_codes.add(code)
        return
    if value is not None and (
        not is_finite_number(value) or not 0 < float(value) <= 100
    ):
        errors.add(
            f"{label}.value: assessment weight must be null or a finite number "
            "greater than 0 and at most 100"
        )


def validate_overrides(
    value: Any,
    extracted: Any,
    label: str,
    errors: ErrorCollector,
) -> None:
    if not isinstance(value, list):
        errors.add(f"{label}: overrides must be a list")
        return
    seen_fields: Set[str] = set()
    for index, override in enumerate(value):
        override_label = f"{label}[{index}]"
        if not isinstance(override, dict):
            errors.add(f"{override_label}: expected an object")
            continue
        missing = OVERRIDE_FIELDS - set(override)
        extra = set(override) - OVERRIDE_FIELDS
        if missing:
            errors.add(f"{override_label}: missing fields {sorted(missing)!r}")
        if extra:
            errors.add(f"{override_label}: unexpected fields {sorted(extra)!r}")

        field = override.get("field")
        if not isinstance(field, str) or not field:
            errors.add(f"{override_label}.field: expected a non-empty string")
        else:
            if field in seen_fields:
                errors.add(f"{override_label}.field: duplicate override path {field!r}")
            seen_fields.add(field)
            try:
                resolve_field_path(extracted, field)
            except (ValueError, KeyError, IndexError):
                errors.add(
                    f"{override_label}.field: path does not resolve inside extracted: {field!r}"
                )
            validate_override_value(
                field,
                override.get("value"),
                override_label,
                errors,
            )

        for required_text in ("reason", "author"):
            item = override.get(required_text)
            if not isinstance(item, str) or not item.strip():
                errors.add(
                    f"{override_label}.{required_text}: expected a non-empty string"
                )
        raw_date = override.get("date")
        if not isinstance(raw_date, str):
            errors.add(f"{override_label}.date: expected YYYY-MM-DD")
        else:
            try:
                parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                if parsed_date.isoformat() != raw_date:
                    raise ValueError
            except ValueError:
                errors.add(f"{override_label}.date: expected a real YYYY-MM-DD date")

    if isinstance(extracted, dict) and isinstance(extracted.get("clos"), list):
        effective_codes = [
            clo.get("code") if isinstance(clo, dict) else None
            for clo in extracted["clos"]
        ]
        for override in value:
            if not isinstance(override, dict):
                continue
            field = override.get("field")
            if not isinstance(field, str):
                continue
            match = re.fullmatch(r"clos\[(\d+)\]\.code", field)
            if match and int(match.group(1)) < len(effective_codes):
                effective_codes[int(match.group(1))] = override.get("value")
        effective_groups: Dict[str, Set[int]] = {}
        for index, code in enumerate(effective_codes):
            if isinstance(code, str) and CLO_CODE_RE.fullmatch(code):
                effective_groups.setdefault(code, set()).add(index)
        baseline_groups: Dict[str, Set[int]] = {}
        for index, clo in enumerate(extracted["clos"]):
            code = clo.get("code") if isinstance(clo, dict) else None
            if isinstance(code, str) and CLO_CODE_RE.fullmatch(code):
                baseline_groups.setdefault(code, set()).add(index)
        warned_indexes = {
            warning.get("clo_index")
            for warning in extracted.get("warnings", [])
            if isinstance(warning, dict)
            and warning.get("code") == "duplicate_source_clo_code"
        }
        for code, indexes in effective_groups.items():
            if len(indexes) < 2:
                continue
            if baseline_groups.get(code) != indexes or not indexes <= warned_indexes:
                errors.add(
                    f"{label}: effective CLO code {code!r} would create an unverified collision"
                )


def validate_variant_record(
    *,
    root: Path,
    code: str,
    index: int,
    variant: Any,
    expected_by_id: Dict[str, Dict[str, Any]],
    all_expected_id_to_course: Dict[str, str],
    actual_active_pdfs: Set[str],
    global_variant_ids: Set[str],
    hash_cache: Dict[Path, str],
    errors: ErrorCollector,
) -> Optional[str]:
    label = f"courses[{code!r}].variants[{index}]"
    if not isinstance(variant, dict):
        errors.add(f"{label}: expected an object")
        return None
    validate_exact_fields(variant, VARIANT_FIELDS, label, errors)

    variant_id_value = variant.get("variant_id")
    valid_id = isinstance(variant_id_value, str) and bool(
        SHA256_RE.fullmatch(variant_id_value)
    )
    if not valid_id:
        errors.add(f"{label}.variant_id: expected a 64-character lowercase SHA-256")
    elif variant_id_value in global_variant_ids:
        errors.add(f"{label}.variant_id: duplicate id {variant_id_value}")
    else:
        global_variant_ids.add(variant_id_value)

    source_pdf = variant.get("source_pdf")
    source_path = safe_repository_path(root, source_pdf, f"{label}.source_pdf", errors)
    if isinstance(source_pdf, str):
        if not source_pdf.startswith("assets/course-specifications/"):
            errors.add(f"{label}.source_pdf: path is outside course specifications")
        elif not source_pdf.lower().endswith(".pdf"):
            errors.add(f"{label}.source_pdf: source is not a PDF")
        else:
            actual_active_pdfs.add(source_pdf)

    digest_value = variant.get("source_sha256")
    digest_valid = validate_sha256(digest_value, f"{label}.source_sha256", errors)
    if source_path is not None:
        if not source_path.is_file():
            errors.add(f"{label}: source PDF does not exist: {source_pdf!r}")
        else:
            try:
                actual_digest = sha256_file(source_path, hash_cache)
                if digest_valid and digest_value != actual_digest:
                    errors.add(
                        f"{label}: source_sha256 mismatch; "
                        f"recorded={digest_value}, actual={actual_digest}"
                    )
            except VerificationInputError as exc:
                errors.add(str(exc))

    scopes = variant.get("scopes")
    catalog = variant.get("catalog")
    if not isinstance(scopes, list):
        errors.add(f"{label}.scopes: expected a list")
    if not isinstance(catalog, dict):
        errors.add(f"{label}.catalog: expected an object")
    else:
        unexpected_catalog = set(catalog) - set(CATALOG_FIELDS)
        if unexpected_catalog:
            errors.add(
                f"{label}.catalog: unexpected fields {sorted(unexpected_catalog)!r}"
            )
        for field in ("title", "summary", "specification_code", "match_status"):
            item = catalog.get(field)
            if not isinstance(item, str) or not item.strip():
                errors.add(f"{label}.catalog.{field}: expected a non-empty string")
        for field in ("match_note", "catalog_id"):
            if field in catalog and (
                not isinstance(catalog[field], str) or not catalog[field].strip()
            ):
                errors.add(f"{label}.catalog.{field}: expected a non-empty string")
        if catalog.get("specification_code") != code:
            errors.add(
                f"{label}.catalog.specification_code: expected outer course code {code!r}"
            )

    if (
        valid_id
        and isinstance(source_pdf, str)
        and isinstance(scopes, list)
        and isinstance(catalog, dict)
    ):
        try:
            recomputed_id = variant_identity(code, source_pdf, scopes, catalog)
            if recomputed_id != variant_id_value:
                errors.add(
                    f"{label}.variant_id: identity payload hashes to {recomputed_id}, "
                    f"not {variant_id_value}"
                )
        except (TypeError, ValueError) as exc:
            errors.add(f"{label}: cannot canonicalize identity payload: {exc}")

    expected = expected_by_id.get(variant_id_value) if valid_id else None
    if expected is None and valid_id:
        owner = all_expected_id_to_course.get(variant_id_value)
        if owner is None:
            errors.add(f"{label}: unexpected variant_id {variant_id_value}")
        else:
            errors.add(f"{label}: variant_id belongs to course {owner!r}, not {code!r}")
    elif expected is not None:
        for field in ("source_pdf", "scopes", "catalog"):
            if variant.get(field) != expected[field]:
                errors.add(
                    f"{label}.{field}: does not match normalized data.json metadata; "
                    f"expected={expected[field]!r}, found={variant.get(field)!r}"
                )

    extracted = variant.get("extracted")
    validate_extracted(
        extracted,
        scopes,
        f"{label}.extracted",
        errors,
        source_sha256=digest_value,
    )
    validate_overrides(
        variant.get("overrides"),
        extracted,
        f"{label}.overrides",
        errors,
    )
    return variant_id_value if valid_id else None


def validate_courses(
    outcomes: Dict[str, Any],
    expected: Dict[str, List[Dict[str, Any]]],
    *,
    root: Path,
    hash_cache: Dict[Path, str],
    errors: ErrorCollector,
) -> Set[str]:
    courses = outcomes.get("courses")
    if not isinstance(courses, dict):
        errors.add("courses: expected an object")
        return set()

    expected_codes = set(expected)
    actual_codes = set(courses)
    if list(courses) != sorted(courses):
        errors.add("courses: course records must be sorted by course code")
    for code in sorted(expected_codes - actual_codes):
        errors.add(f"courses: missing course {code!r}")
    for code in sorted(actual_codes - expected_codes):
        errors.add(f"courses: unexpected course {code!r}")

    all_expected_id_to_course = {
        variant["variant_id"]: code
        for code, variants in expected.items()
        for variant in variants
    }
    actual_active_pdfs: Set[str] = set()
    global_variant_ids: Set[str] = set()

    for raw_code, course_record in courses.items():
        code = str(raw_code)
        if not isinstance(course_record, dict):
            errors.add(f"courses[{code!r}]: expected an object")
            continue
        validate_exact_fields(
            course_record, COURSE_FIELDS, f"courses[{code!r}]", errors
        )
        variants = course_record.get("variants")
        if not isinstance(variants, list):
            errors.add(f"courses[{code!r}].variants: expected a list")
            continue
        expected_by_id = {
            variant["variant_id"]: variant for variant in expected.get(code, [])
        }
        ordered_ids = [
            variant.get("variant_id")
            for variant in variants
            if isinstance(variant, dict) and isinstance(variant.get("variant_id"), str)
        ]
        if len(ordered_ids) == len(variants) and ordered_ids != sorted(ordered_ids):
            errors.add(
                f"courses[{code!r}].variants: records must be sorted by variant_id"
            )
        seen_for_course: Set[str] = set()
        for index, variant in enumerate(variants):
            variant_id_value = validate_variant_record(
                root=root,
                code=code,
                index=index,
                variant=variant,
                expected_by_id=expected_by_id,
                all_expected_id_to_course=all_expected_id_to_course,
                actual_active_pdfs=actual_active_pdfs,
                global_variant_ids=global_variant_ids,
                hash_cache=hash_cache,
                errors=errors,
            )
            if variant_id_value is not None:
                seen_for_course.add(variant_id_value)
        for missing_id in sorted(set(expected_by_id) - seen_for_course):
            expected_variant = expected_by_id[missing_id]
            errors.add(
                f"courses[{code!r}]: missing variant {missing_id} "
                f"for {expected_variant['source_pdf']!r}"
            )
    return actual_active_pdfs


def repository_pdf_inventory(specifications_dir: Path, root: Path) -> Set[str]:
    if not specifications_dir.is_dir():
        raise VerificationInputError(
            f"course-specifications directory does not exist: {specifications_dir}"
        )
    return {
        path.relative_to(root).as_posix()
        for path in specifications_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    }


def expected_excluded_reason(path: str) -> str:
    name = PurePosixPath(path).name
    if "/quarantine/" in path:
        return "quarantined_not_published_in_data_json"
    if name == "program-specification.pdf":
        return "program_specification_not_a_course_specification"
    if name.startswith("pending-code-"):
        return "pending_course_code_not_published_in_data_json"
    if "/clo-plo-corrections-20260901/" in path:
        return "corrected_scope_copy_not_selected_by_data_json"
    return "superseded_or_unpublished_pdf_not_referenced_by_data_json"


def validate_excluded_sources(
    outcomes: Dict[str, Any],
    *,
    root: Path,
    hash_cache: Dict[Path, str],
    errors: ErrorCollector,
) -> Set[str]:
    excluded = outcomes.get("excluded_sources")
    if not isinstance(excluded, list):
        errors.add("excluded_sources: expected a list")
        return set()
    paths: Set[str] = set()
    for index, record in enumerate(excluded):
        label = f"excluded_sources[{index}]"
        if not isinstance(record, dict):
            errors.add(f"{label}: expected an object")
            continue
        validate_exact_fields(record, EXCLUDED_SOURCE_FIELDS, label, errors)
        source_pdf = record.get("source_pdf")
        path = safe_repository_path(root, source_pdf, f"{label}.source_pdf", errors)
        if isinstance(source_pdf, str):
            if source_pdf in paths:
                errors.add(
                    f"{label}.source_pdf: duplicate excluded path {source_pdf!r}"
                )
            paths.add(source_pdf)
            if not source_pdf.startswith("assets/course-specifications/"):
                errors.add(f"{label}.source_pdf: path is outside course specifications")
            if not source_pdf.lower().endswith(".pdf"):
                errors.add(f"{label}.source_pdf: source is not a PDF")

        reason = record.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.add(f"{label}.reason: expected a non-empty string")
        elif isinstance(source_pdf, str):
            expected_reason = expected_excluded_reason(source_pdf)
            if reason != expected_reason:
                errors.add(
                    f"{label}.reason: expected {expected_reason!r}, found {reason!r}"
                )
        digest = record.get("source_sha256")
        digest_valid = validate_sha256(digest, f"{label}.source_sha256", errors)
        if path is not None:
            if not path.is_file():
                errors.add(f"{label}: excluded PDF does not exist: {source_pdf!r}")
            else:
                try:
                    actual_digest = sha256_file(path, hash_cache)
                    if digest_valid and digest != actual_digest:
                        errors.add(
                            f"{label}: source_sha256 mismatch; "
                            f"recorded={digest}, actual={actual_digest}"
                        )
                except VerificationInputError as exc:
                    errors.add(str(exc))
    ordered_paths = [
        record.get("source_pdf")
        for record in excluded
        if isinstance(record, dict) and isinstance(record.get("source_pdf"), str)
    ]
    if len(ordered_paths) == len(excluded) and ordered_paths != sorted(ordered_paths):
        errors.add("excluded_sources: records must be sorted by source_pdf")
    return paths


def validate_inventory(
    *,
    expected: Dict[str, List[Dict[str, Any]]],
    actual_active: Set[str],
    excluded: Set[str],
    disk_pdfs: Set[str],
    errors: ErrorCollector,
) -> Set[str]:
    expected_active = {
        variant["source_pdf"] for variants in expected.values() for variant in variants
    }
    for path in sorted(expected_active - actual_active):
        errors.add(
            f"referenced source PDF is not represented by an active variant: {path}"
        )
    for path in sorted(actual_active - expected_active):
        errors.add(f"active variant references a PDF absent from data.json: {path}")

    overlap = actual_active & excluded
    for path in sorted(overlap):
        errors.add(f"PDF is both active and excluded: {path}")

    represented = actual_active | excluded
    for path in sorted(disk_pdfs - represented):
        errors.add(f"repository PDF is neither active nor excluded: {path}")
    for path in sorted(represented - disk_pdfs):
        errors.add(
            f"represented PDF does not exist in the repository inventory: {path}"
        )

    expected_excluded = disk_pdfs - expected_active
    for path in sorted(expected_excluded - excluded):
        errors.add(
            f"unreferenced repository PDF is missing from excluded_sources: {path}"
        )
    for path in sorted(excluded - expected_excluded):
        errors.add(f"excluded_sources contains a PDF that data.json references: {path}")
    return expected_active


def validate_source_metadata(
    outcomes: Dict[str, Any],
    *,
    root: Path,
    data_relative_path: str,
    hash_cache: Dict[Path, str],
    errors: ErrorCollector,
) -> int:
    source_data = outcomes.get("source_data")
    if isinstance(source_data, dict):
        validate_exact_fields(source_data, SOURCE_DATA_FIELDS, "source_data", errors)
    validate_file_record(
        source_data,
        root=root,
        label="source_data",
        hash_cache=hash_cache,
        errors=errors,
        expected_path=data_relative_path,
    )

    auxiliary = outcomes.get("auxiliary_sources")
    if not isinstance(auxiliary, list):
        errors.add("auxiliary_sources: expected a list")
        return 0
    seen_paths: Set[str] = set()
    for index, record in enumerate(auxiliary):
        if not isinstance(record, dict):
            errors.add(f"auxiliary_sources[{index}]: expected an object")
        else:
            validate_exact_fields(
                record,
                AUXILIARY_SOURCE_FIELDS,
                f"auxiliary_sources[{index}]",
                errors,
            )
            purpose = record.get("purpose")
            if not isinstance(purpose, str) or not purpose.strip():
                errors.add(
                    f"auxiliary_sources[{index}].purpose: expected a non-empty string"
                )
        path = validate_file_record(
            record,
            root=root,
            label=f"auxiliary_sources[{index}]",
            hash_cache=hash_cache,
            errors=errors,
        )
        if path is not None:
            if path in seen_paths:
                errors.add(
                    f"auxiliary_sources[{index}].path: duplicate auxiliary path {path!r}"
                )
            seen_paths.add(path)
            if path == "course-outcomes.json":
                errors.add(
                    f"auxiliary_sources[{index}].path: cannot hash the output file itself"
                )
            expected_purpose = AUXILIARY_SOURCES.get(path)
            if expected_purpose is not None and isinstance(record, dict):
                if record.get("purpose") != expected_purpose:
                    errors.add(
                        f"auxiliary_sources[{index}].purpose: expected "
                        f"{expected_purpose!r} for {path!r}"
                    )
    expected_paths = set(AUXILIARY_SOURCES)
    for path in sorted(expected_paths - seen_paths):
        errors.add(f"auxiliary_sources: missing required source {path!r}")
    for path in sorted(seen_paths - expected_paths):
        errors.add(f"auxiliary_sources: unexpected source {path!r}")
    actual_order = [
        record.get("path")
        for record in auxiliary
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    ]
    if len(actual_order) == len(auxiliary) and actual_order != sorted(actual_order):
        errors.add("auxiliary_sources: records must be sorted by path")
    return len(auxiliary)


def recompute_statistics(
    outcomes: Dict[str, Any], errors: ErrorCollector
) -> Optional[Dict[str, Any]]:
    """Reproduce the extractor's ``_statistics`` calculation literally."""

    courses = outcomes.get("courses")
    excluded = outcomes.get("excluded_sources")
    if not isinstance(courses, dict) or not isinstance(excluded, list):
        errors.add(
            "statistics: cannot recompute without valid courses/excluded_sources"
        )
        return None

    variants: List[Dict[str, Any]] = []
    for code, course in courses.items():
        if not isinstance(course, dict) or not isinstance(course.get("variants"), list):
            errors.add(f"statistics: cannot recompute malformed course {code!r}")
            return None
        if not all(isinstance(variant, dict) for variant in course["variants"]):
            errors.add(f"statistics: cannot recompute malformed variants for {code!r}")
            return None
        variants.extend(course["variants"])

    statuses = {"complete": 0, "partial": 0, "failed": 0}
    variant_source_status_counts = {status: 0 for status in sorted(SOURCE_STATUSES)}
    clo_source_status_counts = {status: 0 for status in sorted(SOURCE_STATUSES)}
    clo_count = 0
    mappings = 0
    mapped = 0
    plo_code_assignments = 0
    multi_plo_mappings = 0
    explicitly_unmapped = 0
    plo_status_counts = {status: 0 for status in sorted(MAPPING_STATUSES)}
    active_paths: Set[str] = set()
    for variant in variants:
        source_pdf = variant.get("source_pdf")
        extracted = variant.get("extracted")
        if not isinstance(source_pdf, str) or not isinstance(extracted, dict):
            errors.add("statistics: cannot recompute malformed variant metadata")
            return None
        active_paths.add(source_pdf)
        status = extracted.get("extraction_status")
        if status not in statuses:
            errors.add(
                f"statistics: cannot recompute unknown extraction_status {status!r}"
            )
            return None
        statuses[status] += 1
        source_status = extracted.get("source_status")
        if source_status not in variant_source_status_counts:
            errors.add(
                f"statistics: cannot recompute unknown source_status {source_status!r}"
            )
            return None
        variant_source_status_counts[source_status] += 1
        clos = extracted.get("clos")
        if not isinstance(clos, list) or not all(isinstance(clo, dict) for clo in clos):
            errors.add("statistics: cannot recompute malformed clos")
            return None
        clo_count += len(clos)
        for clo in clos:
            clo_source_status = clo.get("source_status")
            if clo_source_status not in clo_source_status_counts:
                errors.add(
                    "statistics: cannot recompute unknown CLO source_status "
                    f"{clo_source_status!r}"
                )
                return None
            clo_source_status_counts[clo_source_status] += 1
            plo_mappings = clo.get("plo_mappings")
            if not isinstance(plo_mappings, list) or not all(
                isinstance(mapping, dict) for mapping in plo_mappings
            ):
                errors.add("statistics: cannot recompute malformed plo_mappings")
                return None
            for mapping in plo_mappings:
                mappings += 1
                mapping_status = mapping.get("status")
                if mapping_status not in plo_status_counts:
                    errors.add(
                        "statistics: cannot recompute unknown PLO mapping status "
                        f"{mapping_status!r}"
                    )
                    return None
                plo_status_counts[mapping_status] += 1
                plo_codes = mapping.get("plo_codes")
                if isinstance(plo_codes, list) and plo_codes:
                    mapped += 1
                    plo_code_assignments += len(plo_codes)
                    if len(plo_codes) > 1:
                        multi_plo_mappings += 1
                elif mapping_status == "explicitly_unmapped":
                    explicitly_unmapped += 1

    applicable = sum(
        plo_status_counts[status]
        for status in ("mapped", "missing", "conflict", "ambiguous_for_scope")
    )
    resolved_or_explicit_denominator = applicable + explicitly_unmapped

    return {
        "course_codes": len(courses),
        "variants": len(variants),
        "active_pdf_sources": len(active_paths),
        "excluded_pdf_sources": len(excluded),
        "complete_variants": statuses["complete"],
        "partial_variants": statuses["partial"],
        "failed_variants": statuses["failed"],
        "variant_source_status_counts": variant_source_status_counts,
        "clos": clo_count,
        "clo_source_status_counts": clo_source_status_counts,
        "scoped_clo_mappings": mappings,
        "plo_mappings_with_codes": mapped,
        "plo_code_assignments": plo_code_assignments,
        "multi_plo_mappings": multi_plo_mappings,
        "plo_non_null": mapped,
        "plo_explicitly_unmapped": explicitly_unmapped,
        "plo_non_null_rate": round(mapped / mappings, 6) if mappings else None,
        "plo_status_counts": plo_status_counts,
        "plo_applicable_mappings": applicable,
        "plo_applicable_non_null_rate": (
            round(mapped / applicable, 6) if applicable else None
        ),
        "plo_applicable_with_codes_rate": (
            round(mapped / applicable, 6) if applicable else None
        ),
        "plo_resolved_or_explicit_rate": (
            round(
                (mapped + explicitly_unmapped) / resolved_or_explicit_denominator,
                6,
            )
            if resolved_or_explicit_denominator
            else None
        ),
    }


def validate_statistics(outcomes: Dict[str, Any], errors: ErrorCollector) -> None:
    recorded = outcomes.get("statistics")
    if not isinstance(recorded, dict):
        errors.add("statistics: expected an object")
        return
    computed = recompute_statistics(outcomes, errors)
    if computed is None:
        return
    missing = set(computed) - set(recorded)
    extra = set(recorded) - set(computed)
    if missing:
        errors.add(f"statistics: missing fields {sorted(missing)!r}")
    if extra:
        errors.add(f"statistics: unexpected fields {sorted(extra)!r}")
    for field, expected_value in computed.items():
        if field in recorded and (
            recorded[field] != expected_value
            or type(recorded[field]) is not type(expected_value)
        ):
            errors.add(
                f"statistics.{field}: expected recomputed value {expected_value!r}, "
                f"found {recorded[field]!r}"
            )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root (defaults to the script's parent repository)",
    )
    parser.add_argument(
        "--data",
        default="data.json",
        help="repository-relative source data path (default: data.json)",
    )
    parser.add_argument(
        "--outcomes",
        default="course-outcomes.json",
        help="repository-relative pinned extraction path",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    errors = ErrorCollector()

    data_path = safe_repository_path(root, args.data, "--data", errors)
    outcomes_path = safe_repository_path(root, args.outcomes, "--outcomes", errors)
    if data_path is None or outcomes_path is None or errors.count:
        for message in errors.messages:
            print(f"ERROR: {message}", file=sys.stderr)
        return 2

    try:
        data = load_json(data_path)
        outcomes = load_json(outcomes_path)
        expected, stats = rebuild_expected_variants(data)
        disk_pdfs = repository_pdf_inventory(
            root / "assets" / "course-specifications", root
        )
    except VerificationInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    hash_cache: Dict[Path, str] = {}
    validate_generated_metadata(outcomes, root, hash_cache, errors)
    try:
        data_relative_path = data_path.relative_to(root).as_posix()
    except ValueError:
        print("ERROR: --data must be inside the repository", file=sys.stderr)
        return 2
    auxiliary_count = validate_source_metadata(
        outcomes,
        root=root,
        data_relative_path=data_relative_path,
        hash_cache=hash_cache,
        errors=errors,
    )
    actual_active = validate_courses(
        outcomes,
        expected,
        root=root,
        hash_cache=hash_cache,
        errors=errors,
    )
    excluded = validate_excluded_sources(
        outcomes,
        root=root,
        hash_cache=hash_cache,
        errors=errors,
    )
    validate_statistics(outcomes, errors)
    expected_active = validate_inventory(
        expected=expected,
        actual_active=actual_active,
        excluded=excluded,
        disk_pdfs=disk_pdfs,
        errors=errors,
    )

    print("Course outcomes verification summary")
    print(f"  courses rebuilt from data.json: {stats['courses']}")
    print(f"  variants rebuilt from data.json: {stats['variants']}")
    print(f"  normalized scopes: {stats['scopes']}")
    print(
        "  legacy direct records/scopes inferred: "
        f"{stats['legacy_records']}/{stats['legacy_scopes']}"
    )
    print(f"  referenced source PDFs: {len(expected_active)}")
    print(f"  excluded source PDFs: {len(excluded)}")
    print(f"  repository source PDFs: {len(disk_pdfs)}")
    print(f"  auxiliary hashed sources: {auxiliary_count}")

    if errors.count:
        print(
            f"Course outcomes verification FAILED with {errors.count} error(s).",
            file=sys.stderr,
        )
        for message in errors.messages:
            print(f"  - {message}", file=sys.stderr)
        omitted = errors.count - len(errors.messages)
        if omitted:
            print(f"  - ... {omitted} additional error(s) omitted", file=sys.stderr)
        return 1

    print("Course outcomes verification PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
