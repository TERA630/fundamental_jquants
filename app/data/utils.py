"""Data-layer utility helpers."""

from __future__ import annotations

import math
import re
from typing import Any


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value in ("", "-", "None", "null", "NaN"):
            return None
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def normalize_code(code: str) -> str:
    text = str(code).strip()
    text = re.sub(r"\D", "", text)
    if len(text) == 4:
        return text + "0"
    return text


__all__ = ["safe_float", "first_present", "normalize_code"]
