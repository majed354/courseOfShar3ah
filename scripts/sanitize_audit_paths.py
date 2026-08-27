#!/usr/bin/env python3
"""Make generated audit JSON portable before it is committed publicly."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORIES = (
    ROOT / "assets/course-specifications/specialty-recovery-20260826",
    ROOT / "assets/course-specifications/raw-recovery-20260827",
)


def portable_string(value: str) -> str:
    if value.lower().startswith("file:///"):
        return "local-file-link"
    root_text = str(ROOT)
    if value == root_text:
        return "."
    if value.startswith(root_text + "/"):
        return Path(value).relative_to(ROOT).as_posix()
    if value.startswith("/Users/"):
        return f"local-asset/{Path(value).name}"
    return value


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return portable_string(value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", type=Path, nargs="*", default=DEFAULT_DIRECTORIES)
    args = parser.parse_args()

    files = sorted(path for directory in args.directories for path in directory.glob("*.json"))
    changed = 0
    for path in files:
        original = json.loads(path.read_text(encoding="utf-8"))
        cleaned = sanitize(original)
        if cleaned == original:
            continue
        path.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        changed += 1
    print(f"sanitized={changed}/{len(files)}")


if __name__ == "__main__":
    main()
