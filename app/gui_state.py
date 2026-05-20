"""GUI state model and helper builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GuiState:
    """GUI表示に必要な状態を保持する。"""

    watchlist_path: Path | None = None
    kabutan_html_dir: Path | None = None
    allow_kabutan_web_fallback: bool = True
    watchlist: list[tuple[str, str]] = field(default_factory=list)
    display_to_code: dict[str, tuple[str, str]] = field(default_factory=dict)
    output_cache: dict[str, str] = field(default_factory=dict)
    is_fetching: bool = False


def build_stock_choices(watchlist: list[tuple[str, str]]) -> tuple[list[str], dict[str, tuple[str, str]]]:
    values: list[str] = []
    mapping: dict[str, tuple[str, str]] = {}
    for name, code in watchlist:
        display = f"{name} ({code})"
        values.append(display)
        mapping[display] = (name, code)
    return values, mapping


def get_selected_stock(display_to_code: dict[str, tuple[str, str]], label: str) -> tuple[str, str] | None:
    key = label.strip()
    if not key:
        return None
    return display_to_code.get(key)


def build_default_output_filename(selected: tuple[str, str] | None) -> str:
    if selected is None:
        return "stock_fundamental_prompt.txt"
    _, code = selected
    return f"stock_fundamental_prompt_{code}.txt"


__all__ = [
    "GuiState",
    "build_stock_choices",
    "get_selected_stock",
    "build_default_output_filename",
]
