from dataclasses import dataclass
from pathlib import Path
import sys
import types

from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastRow


def _install_stub_modules() -> None:
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")

        class DummySession:
            def __init__(self):
                self.headers = {}

            def mount(self, *_args, **_kwargs):
                return None

        requests.Session = DummySession
        requests.RequestException = Exception
        sys.modules["requests"] = requests

        adapters = types.ModuleType("requests.adapters")

        class HTTPAdapter:
            def __init__(self, *args, **kwargs):
                pass

        adapters.HTTPAdapter = HTTPAdapter
        sys.modules["requests.adapters"] = adapters

    if "urllib3.util.retry" not in sys.modules:
        retry_mod = types.ModuleType("urllib3.util.retry")

        class Retry:
            def __init__(self, *args, **kwargs):
                pass

        retry_mod.Retry = Retry
        sys.modules["urllib3.util.retry"] = retry_mod


_install_stub_modules()

from app.domain.usecases.fundamental_analysis import FundamentalAnalysisService


@dataclass
class StubRepository:
    result: KabutanForecastPair
    file_calls: int = 0
    web_calls: int = 0
    fail_suffixes: tuple[str, ...] = ()

    def fetch_kabutan_forecast_pair_from_file(self, html_path: Path) -> KabutanForecastPair:
        self.file_calls += 1
        if html_path.suffix in self.fail_suffixes:
            raise ValueError(f"failed: {html_path.name}")
        return self.result

    def fetch_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        self.web_calls += 1
        return self.result


@dataclass
class StubUseCase:
    repository: StubRepository

    def get_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        return self.repository.fetch_kabutan_forecast_pair(code, target_years)


def _build_pair() -> KabutanForecastPair:
    return KabutanForecastPair(
        previous_actual=KabutanForecastRow("2025.03", 2025, 3, "実績", 1000, 100, 90, 80),
        current_forecast=KabutanForecastRow("2026.03", 2026, 3, "予想", 1200, 130, 120, 110),
        next_forecast=KabutanForecastRow("2027.03", 2027, 3, "予想", 1350, 150, 140, 120),
    )


def test_fetch_kabutan_forecast_pair_prefers_html_dir(tmp_path: Path):
    pair = _build_pair()
    repo = StubRepository(result=pair)
    service = FundamentalAnalysisService(api_key="dummy", fetch_kabutan_forecast_usecase=StubUseCase(repository=repo))

    html_dir = tmp_path / "kabutan"
    html_dir.mkdir()
    (html_dir / "7203.html").write_text("<html></html>", encoding="utf-8")

    result = service.fetch_kabutan_forecast_pair("7203", html_dir=html_dir)

    assert result.pair == pair
    assert result.source == "html"
    assert repo.file_calls == 1
    assert repo.web_calls == 0


def test_fetch_kabutan_forecast_pair_returns_none_source_when_web_opt_out_and_html_missing(tmp_path: Path):
    pair = _build_pair()
    repo = StubRepository(result=pair)
    service = FundamentalAnalysisService(api_key="dummy", fetch_kabutan_forecast_usecase=StubUseCase(repository=repo))
    html_dir = tmp_path / "kabutan"
    html_dir.mkdir()

    result = service.fetch_kabutan_forecast_pair("7203", html_dir=html_dir, allow_kabutan_web_fallback=False)

    assert result.pair is None
    assert result.source == "none"
    assert repo.web_calls == 0


def test_fetch_kabutan_forecast_pair_supports_partial_filename_match(tmp_path: Path):
    pair = _build_pair()
    repo = StubRepository(result=pair)
    service = FundamentalAnalysisService(api_key="dummy", fetch_kabutan_forecast_usecase=StubUseCase(repository=repo))

    html_dir = tmp_path / "kabutan"
    html_dir.mkdir()
    (html_dir / "INPEX【1605】_finance.html").write_text("<html></html>", encoding="utf-8")

    result = service.fetch_kabutan_forecast_pair("1605", html_dir=html_dir, allow_kabutan_web_fallback=False)

    assert result.pair == pair
    assert result.source == "html"
    assert repo.file_calls == 1
    assert repo.web_calls == 0


def test_fetch_kabutan_forecast_pair_try_htm_after_html_parse_failure(tmp_path: Path):
    pair = _build_pair()
    repo = StubRepository(result=pair, fail_suffixes=(".html",))
    service = FundamentalAnalysisService(api_key="dummy", fetch_kabutan_forecast_usecase=StubUseCase(repository=repo))

    html_dir = tmp_path / "kabutan"
    html_dir.mkdir()
    (html_dir / "1605.html").write_text("<broken></broken>", encoding="utf-8")
    (html_dir / "1605.htm").write_text("<valid></valid>", encoding="utf-8")

    result = service.fetch_kabutan_forecast_pair("1605", html_dir=html_dir, allow_kabutan_web_fallback=False)

    assert result.pair == pair
    assert result.source == "html"
    assert repo.file_calls == 2
    assert repo.web_calls == 0
