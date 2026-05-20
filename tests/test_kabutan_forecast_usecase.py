from dataclasses import dataclass

from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastRow
from app.domain.usecases.kabutan_forecast import FetchKabutanForecastUseCase


@dataclass
class StubRepository:
    result: KabutanForecastPair

    def fetch_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        return self.result


def test_get_kabutan_forecast_pair_returns_repository_result():
    expected = KabutanForecastPair(
        previous_actual=KabutanForecastRow("2025.03", 2025, 3, "実績", 1000, 100, 90, 80),
        current_forecast=KabutanForecastRow("2026.03", 2026, 3, "予想", 1200, 130, 120, 110),
        next_forecast=KabutanForecastRow("2027.03", 2027, 3, "予想", 1350, 150, 140, 120),
    )
    usecase = FetchKabutanForecastUseCase(repository=StubRepository(result=expected))

    actual = usecase.get_kabutan_forecast_pair(code="7203", target_years=(2026, 2027))

    assert actual == expected
