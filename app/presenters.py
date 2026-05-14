"""Presentation helpers: bridge GUI use-cases and domain/output builders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fundamental_jquants_v7 as legacy

from app.domain.builders.fundamental_output import build_fundamental_output_text


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
    """ドメイン層の出力生成ビルダーを呼び出す。"""
    return build_fundamental_output_text(
        name=name,
        code4=code4,
        master=master,
        summary_rows=summary_rows,
        price=price,
        market_cap=market_cap,
    )
