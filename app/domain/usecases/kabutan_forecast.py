"""Use case for loading Kabutan current/next annual forecast."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models.kabutan_forecast import KabutanForecastPair


class KabutanForecastRepositoryPort(Protocol):
    def fetch_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair: ...


@dataclass
class FetchKabutanForecastUseCase:
    repository: KabutanForecastRepositoryPort

    def get_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        return self.repository.fetch_kabutan_forecast_pair(code=code, target_years=target_years)


__all__ = ["KabutanForecastRepositoryPort", "FetchKabutanForecastUseCase"]
