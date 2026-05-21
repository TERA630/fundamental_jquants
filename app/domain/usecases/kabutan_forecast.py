"""Use case for loading Kabutan current/next annual forecast."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastSnapshot


class KabutanForecastRepositoryPort(Protocol):
    def fetch_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair: ...
    def fetch_kabutan_html_from_file(self, html_path: str) -> str: ...


@dataclass
class FetchKabutanForecastUseCase:
    repository: KabutanForecastRepositoryPort

    def get_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        return self.repository.fetch_kabutan_forecast_pair(code=code, target_years=target_years)

    def get_kabutan_forecast_snapshot_from_rows(self, rows: list, base_year: int) -> KabutanForecastSnapshot:
        from app.data.kabutan_repository import build_kabutan_forecast_snapshot

        return build_kabutan_forecast_snapshot(rows, base_year=base_year)


__all__ = ["KabutanForecastRepositoryPort", "FetchKabutanForecastUseCase"]
