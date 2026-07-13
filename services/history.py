from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_PATH = BASE_DIR / "data" / "history.json"


def ensure_history_file() -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORY_PATH.exists():
        HISTORY_PATH.write_text("[]\n", encoding="utf-8")


def load_history() -> list[dict[str, Any]]:
    ensure_history_file()
    try:
        raw_history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(raw_history, list):
        return []

    return [item for item in raw_history if isinstance(item, dict)]


def save_history(history: list[dict[str, Any]]) -> None:
    ensure_history_file()
    temporary_path = HISTORY_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(HISTORY_PATH)


def upsert_history_record(record: dict[str, Any]) -> None:
    history = load_history()
    record_id = str(record["id"])

    for index, existing_record in enumerate(history):
        if str(existing_record.get("id")) != record_id:
            continue

        updated_record = {
            **record,
            "time": existing_record.get("time", record["time"]),
        }
        if updated_record != existing_record:
            history[index] = updated_record
            save_history(history)
        return

    history.insert(0, record)
    save_history(history)


def create_history_record(
    record_id: str,
    title: str,
    body: str,
    safety_score: int,
    risk_level: str,
    risk_items: list[dict[str, str]],
    rewritten_title: str,
    rewritten_body: str,
    image_ocr_text: str = "",
    title_candidates: list[str] | None = None,
    cover_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "title": title,
        "body": body,
        "safety_score": safety_score,
        "risk_level": risk_level,
        "risk_items": risk_items,
        "safe_title": rewritten_title,
        "safe_body": rewritten_body,
        "image_ocr_text": image_ocr_text,
        "title_candidates": title_candidates or [],
        "cover_analysis": cover_analysis,
    }


def load_recent_history(limit: int = 10) -> list[dict[str, Any]]:
    return load_history()[:limit]
