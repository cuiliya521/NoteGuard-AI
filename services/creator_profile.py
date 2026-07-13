from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROFILE_FIELDS = (
    "name",
    "subjects",
    "target_grades",
    "target_students",
    "teaching_format",
    "session_duration",
    "pricing",
    "teaching_features",
    "personal_experience",
    "public_cases",
    "do_not_invent",
    "desired_action",
    "writing_style",
)


def empty_creator_profile() -> dict[str, str]:
    return {field: "" for field in PROFILE_FIELDS}


def ensure_creator_profile(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            json.dumps(empty_creator_profile(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def load_creator_profile(path: Path) -> dict[str, str]:
    ensure_creator_profile(path)
    try:
        raw_profile = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty_creator_profile()

    if not isinstance(raw_profile, dict):
        return empty_creator_profile()

    return {
        field: str(raw_profile.get(field, "")).strip()
        for field in PROFILE_FIELDS
    }


def save_creator_profile(path: Path, profile: dict[str, Any]) -> None:
    normalized_profile = {
        field: str(profile.get(field, "")).strip()
        for field in PROFILE_FIELDS
    }
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(normalized_profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def build_creator_profile_context(profile: dict[str, str] | None) -> dict[str, str]:
    if not profile:
        return {}
    return {
        field: value.strip()
        for field, value in profile.items()
        if field in PROFILE_FIELDS and value and value.strip()
    }
