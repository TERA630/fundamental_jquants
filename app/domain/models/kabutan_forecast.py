"""Domain models for Kabutan annual forecast rows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KabutanForecastRow:
    period_label: str
    year: int
    month: int
    section: str
    sales: int | None
    operating_profit: int | None
    ordinary_profit: int | None
    final_profit: int | None


@dataclass(frozen=True)
class KabutanForecastPair:
    previous_actual: KabutanForecastRow | None
    current_forecast: KabutanForecastRow
    next_forecast: KabutanForecastRow | None


__all__ = ["KabutanForecastRow", "KabutanForecastPair"]
