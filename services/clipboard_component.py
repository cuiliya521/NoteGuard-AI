from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import Optional

import streamlit.components.v1 as components
from PIL import Image


_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "components" / "clipboard_paste"
_component = components.declare_component(
    "noteguard_clipboard_paste",
    path=str(_FRONTEND_DIR),
)


@dataclass
class PasteResult:
    image_data: Image.Image | None = None


def _data_url_to_image(data_url: str) -> Image.Image:
    _, encoded = data_url.split(";base64,", 1)
    return Image.open(BytesIO(base64.b64decode(encoded)))


def paste_image_button(
    label: str,
    text_color: Optional[str] = "#ffffff",
    background_color: Optional[str] = "#ef4f5f",
    hover_background_color: Optional[str] = "#dc3f50",
    key: Optional[str] = "paste_button",
    errors: Optional[str] = "ignore",
) -> PasteResult:
    value = _component(
        label=label,
        text_color=text_color,
        background_color=background_color,
        hover_background_color=hover_background_color,
        key=key,
        default=None,
    )
    if value is None:
        return PasteResult()
    if isinstance(value, str) and value.startswith("error"):
        if errors == "raise":
            raise ValueError(re.sub(r"^error:\s*", "", value))
        return PasteResult()
    if not isinstance(value, str) or ";base64," not in value:
        return PasteResult()
    return PasteResult(image_data=_data_url_to_image(value))
