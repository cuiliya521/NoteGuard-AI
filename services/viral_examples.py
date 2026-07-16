from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAX_EXAMPLES = 20
MAX_TITLE_CHARS = 200
MAX_CONTENT_CHARS = 3000
MAX_METADATA_CHARS = 1000

EXAMPLE_FIELDS = (
    "title",
    "content",
    "category",
    "structure",
    "opening_style",
    "pain_points",
    "selling_points",
    "conversion_style",
)


def normalize_viral_example(record: dict[str, Any]) -> dict[str, str] | None:
    normalized = {
        field: str(record.get(field, "")).strip()[:MAX_METADATA_CHARS]
        for field in EXAMPLE_FIELDS
    }
    normalized["title"] = normalized["title"][:MAX_TITLE_CHARS]
    normalized["content"] = normalized["content"][:MAX_CONTENT_CHARS]
    if not normalized["title"] and not normalized["content"]:
        return None
    return normalized


def load_viral_examples(path: Path, limit: int = MAX_EXAMPLES) -> list[dict[str, str]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")

    try:
        raw_examples = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw_examples, list):
        return []
    if limit <= 0:
        return []

    examples: list[dict[str, str]] = []
    for record in raw_examples:
        if not isinstance(record, dict):
            continue
        normalized = normalize_viral_example(record)
        if normalized:
            examples.append(normalized)
        if len(examples) >= limit:
            break
    return examples
