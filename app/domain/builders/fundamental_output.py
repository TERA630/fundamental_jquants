"""Domain builder for fundamental analysis output text."""

from __future__ import annotations

from typing import Any

import fundamental_jquants_v7 as legacy


def build_fundamental_output_text(
    *,
    name: str,
    code4: str,
    master: dict[str, Any] | None,
    summary_rows: list[dict[str, Any]],
    price: float | None,
    market_cap: float | None,
) -> str:
    """ドメイン層の出力生成エントリポイント。"""
    return legacy.build_output(
        name=name,
        code4=code4,
        master=master,
        summary_rows=summary_rows,
        price=price,
        market_cap=market_cap,
    )


__all__ = ["build_fundamental_output_text"]
