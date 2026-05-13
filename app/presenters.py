"""Presentation helpers: bridge GUI use-cases and legacy output builders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fundamental_jquants_v7 as legacy


def fetch_watchlist(path: Path) -> list[tuple[str, str]]:
    """監視銘柄ファイルを読み込み、GUI用の銘柄一覧へ整形して返す。"""
    return legacy.load_watchlist(path)


def build_fundamental_output(
    *,
    name: str,
    code4: str,
    master: dict[str, Any] | None,
    summary_rows: list[dict[str, Any]],
    price: float | None,
    market_cap: float | None,
) -> str:
    """既存の出力生成を呼び出すプレゼンテーション向けアダプター。"""
    return legacy.build_output(
        name=name,
        code4=code4,
        master=master,
        summary_rows=summary_rows,
        price=price,
        market_cap=market_cap,
    )
