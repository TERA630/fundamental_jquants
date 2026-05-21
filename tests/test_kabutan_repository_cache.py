from pathlib import Path

from app.data.file_cache import FileCache
from app.data.kabutan_repository import KabutanForecastRepository, fetch_kabutan_forecast_rows_from_cache_payload


class DummyKabutanForecastRepository(KabutanForecastRepository):
    def __init__(self, html: str, file_cache: FileCache):
        super().__init__(timeout_sec=1, file_cache=file_cache)
        self.html = html
        self.calls = 0

    def fetch_kabutan_html(self, code: str) -> str:
        self.calls += 1
        return self.html


def test_fetch_kabutan_forecast_pair_uses_cache(tmp_path: Path):
    html = """
    <div class=\"fin_year_result_d\"><table><tbody>
      <tr><th>2025.03</th><td>1,000</td><td>100</td><td>90</td><td>80</td></tr>
      <tr><th>2026.03予</th><td>1,200</td><td>130</td><td>120</td><td>110</td></tr>
      <tr><th>2027.03予</th><td>1,350</td><td>150</td><td>140</td><td>120</td></tr>
    </tbody></table></div>
    """
    repo = DummyKabutanForecastRepository(html=html, file_cache=FileCache(base_dir=tmp_path / "cache"))

    first = repo.fetch_kabutan_forecast_pair("7203")
    second = repo.fetch_kabutan_forecast_pair("7203")

    assert first.current_forecast.year == 2026
    assert second.next_forecast is not None
    assert repo.calls == 1


def test_fetch_kabutan_forecast_pair_restores_eps_and_dividend_from_cache(tmp_path: Path):
    html = """
    <div class="fin_year_result_d"><table><tbody>
      <tr><th>決算期</th><th>売上高</th><th>営業益</th><th>経常益</th><th>最終益</th><th>修正1株益</th><th>配当</th></tr>
      <tr><th>2025.03</th><td>1,000</td><td>100</td><td>90</td><td>80</td><td>50.5</td><td>20.0</td></tr>
      <tr><th>2026.03予</th><td>1,200</td><td>130</td><td>120</td><td>110</td><td>65.2</td><td>24.0</td></tr>
      <tr><th>2027.03予</th><td>1,350</td><td>150</td><td>140</td><td>120</td><td>70.1</td><td>26.0</td></tr>
    </tbody></table></div>
    """
    repo = DummyKabutanForecastRepository(html=html, file_cache=FileCache(base_dir=tmp_path / "cache"))

    first = repo.fetch_kabutan_forecast_pair("7203")
    second = repo.fetch_kabutan_forecast_pair("7203")

    assert first.current_forecast.revised_eps == 65.2
    assert first.current_forecast.dividend == 24.0
    assert second.current_forecast.revised_eps == 65.2
    assert second.current_forecast.dividend == 24.0
    assert second.next_forecast is not None
    assert second.next_forecast.revised_eps == 70.1
    assert second.next_forecast.dividend == 26.0
    assert repo.calls == 1


def test_fetch_kabutan_html_from_file_uses_cache(tmp_path: Path):
    cache = FileCache(base_dir=tmp_path / "cache")
    repo = KabutanForecastRepository(file_cache=cache)
    path = tmp_path / "kabutan_saved.html"
    path.write_text('<html><body><div class="fin_year_result_d"><table><tbody><tr><th>2026.03予</th><td>1</td><td>2</td><td>3</td><td>4</td></tr></tbody></table></div><div>noise</div></body></html>', encoding="utf-8")

    first = repo.fetch_kabutan_html_from_file(path)
    path.write_text('<html><body><div class="fin_year_result_d"><table><tbody><tr><th>2027.03予</th><td>9</td><td>9</td><td>9</td><td>9</td></tr></tbody></table></div></body></html>', encoding="utf-8")
    second = repo.fetch_kabutan_html_from_file(path)

    assert '2026.03予' in first
    assert '2027.03予' not in second


def test_fetch_kabutan_forecast_rows_from_cache_payload_skips_invalid_rows():
    payload = {
        "rows": [
            {"fiscal_year": "2026/03", "forecast_type": "予想", "period_type": "通期", "sales": 1200, "op_income": 130, "ordinary_income": 120, "np": 110, "eps": 65.2, "div": 24.0},
            {"fiscal_year": "broken", "forecast_type": "予想", "period_type": "通期"},
            "invalid-row",
        ]
    }

    rows = fetch_kabutan_forecast_rows_from_cache_payload(payload)

    assert len(rows) == 1
    assert rows[0].year == 2026
    assert rows[0].revised_eps == 65.2
