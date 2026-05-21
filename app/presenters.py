"""Presentation helpers: bridge GUI use-cases and domain/output builders."""

from __future__ import annotations
from typing import Any

from app.domain.builders.fundamental_output import build_fundamental_output_text
from app.domain.builders.kabutan_output import build_kabutan_forecast_output
from app.domain.models.kabutan_forecast import KabutanForecastPair


def build_fundamental_output(
    *,
    name: str,
    code4: str,
    master: dict[str, Any] | None,
    summary_rows: list[dict[str, Any]],
    price: float | None,
    market_cap: float | None,
    kabutan_forecast_pair: KabutanForecastPair | None = None,
    kabutan_source: str = "none",
    kabutan_source_message: str | None = None,
) -> str:
    """ドメイン層の出力生成ビルダーを呼び出す。"""
    base_output = build_fundamental_output_text(
        name=name,
        code4=code4,
        master=master,
        summary_rows=summary_rows,
        price=price,
        market_cap=market_cap,
    )
    return build_kabutan_forecast_output(base_output, kabutan_forecast_pair, kabutan_source, kabutan_source_message)
