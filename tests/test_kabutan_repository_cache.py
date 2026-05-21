from pathlib import Path

from app.data.file_cache import FileCache
from app.data.kabutan_repository import KabutanForecastRepository


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


def test_fetch_kabutan_html_from_file_uses_cache(tmp_path: Path):
    cache = FileCache(base_dir=tmp_path / "cache")
    repo = KabutanForecastRepository(file_cache=cache)
    path = tmp_path / "kabutan_saved.html"
    path.write_text('<html><body><div class="fin_year_result_d">v1</div><div>noise</div></body></html>', encoding="utf-8")

    first = repo.fetch_kabutan_html_from_file(path)
    path.write_text('<html><body><div class="fin_year_result_d">v2</div></body></html>', encoding="utf-8")
    second = repo.fetch_kabutan_html_from_file(path)

    assert first == '<div class="fin_year_result_d">v1</div>'
    assert second == '<div class="fin_year_result_d">v1</div>'
