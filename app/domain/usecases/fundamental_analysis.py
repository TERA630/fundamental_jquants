"""Domain use-case: orchestration for fundamental analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
from pathlib import Path
import re

from app.data.file_cache import FileCache
from app.data.jquants_client import JQuantsClient
from app.data.kabutan_repository import KabutanForecastRepository
from app.data.market_data_provider import fetch_yfinance_snapshot
from app.data.utils import normalize_code
from app.domain.models.kabutan_forecast import KabutanForecastPair
from app.domain.usecases.kabutan_forecast import FetchKabutanForecastUseCase

CACHE_TTL_MASTER_SEC = 30 * 24 * 60 * 60
CACHE_TTL_SUMMARY_SEC = 24 * 60 * 60
CACHE_TTL_YF_SEC = 12 * 60 * 60


class JQuantsClientPort(Protocol):
    def get_master(self, code: str) -> dict[str, Any] | None: ...
    def get_summary(self, code: str) -> list[dict[str, Any]]: ...


class MarketDataProviderPort(Protocol):
    def __call__(self, code4: str) -> dict[str, float | None]: ...


@dataclass(frozen=True)
class KabutanFetchResult:
    pair: KabutanForecastPair | None
    source: str
    message: str | None = None


class FundamentalAnalysisService:
    """ドメイン層ユースケース: 分析出力の組み立て実行を担当。"""

    def __init__(
        self,
        api_key: str,
        file_cache: FileCache | None = None,
        client: JQuantsClientPort | None = None,
        fetch_market_snapshot: MarketDataProviderPort | None = None,
        kabutan_usecase: FetchKabutanForecastUseCase | None = None,
    ):
        self.client = client or JQuantsClient(api_key)
        self.cache = file_cache or FileCache()
        self.fetch_market_snapshot = fetch_market_snapshot or fetch_yfinance_snapshot
        self.kabutan_usecase = kabutan_usecase or FetchKabutanForecastUseCase(repository=KabutanForecastRepository())

    def build_cache_key_master(self, code4: str) -> str:
        return f"master_{normalize_code(code4)}"

    def build_cache_key_summary(self, code4: str) -> str:
        return f"summary_{normalize_code(code4)}"

    def build_cache_key_price_snapshot(self, code4: str) -> str:
        return f"yf_{code4}"

    def fetch_master(self, code4: str) -> dict[str, Any] | None:
        return self.cache.get_or_fetch(
            self.build_cache_key_master(code4),
            CACHE_TTL_MASTER_SEC,
            lambda: self.client.get_master(code4),
        )

    def fetch_summary_rows(self, code4: str) -> list[dict[str, Any]]:
        rows = self.cache.get_or_fetch(
            self.build_cache_key_summary(code4),
            CACHE_TTL_SUMMARY_SEC,
            lambda: self.client.get_summary(code4),
        )
        return rows if isinstance(rows, list) else []

    def fetch_price_snapshot(self, code4: str) -> dict[str, float | None]:
        cache_key = self.build_cache_key_price_snapshot(code4)
        cached = self.cache.get(cache_key, CACHE_TTL_YF_SEC)
        if isinstance(cached, dict):
            return {
                "price": cached.get("price"),
                "market_cap": cached.get("market_cap"),
            }

        snapshot = self.fetch_market_snapshot(code4)
        if isinstance(snapshot, dict) and snapshot.get("price") is not None:
            self.cache.set(cache_key, snapshot)
            return {
                "price": snapshot.get("price"),
                "market_cap": snapshot.get("market_cap"),
            }
        return {"price": None, "market_cap": None}

    def build_analysis_output(
        self,
        name: str,
        code4: str,
        build_output_fn: Callable[..., str],
        kabutan_html_dir: Path | None = None,
        allow_kabutan_web_fallback: bool = True,
    ) -> str:
        master = self.fetch_master(code4)
        summary_rows = self.fetch_summary_rows(code4)
        price_snapshot = self.fetch_price_snapshot(code4)
        kabutan_fetch_result = self.fetch_kabutan_forecast_pair(
            code4,
            html_dir=kabutan_html_dir,
            allow_kabutan_web_fallback=allow_kabutan_web_fallback,
        )
        return build_output_fn(
            name=name,
            code4=code4,
            master=master,
            summary_rows=summary_rows,
            price=price_snapshot.get("price"),
            market_cap=price_snapshot.get("market_cap"),
            kabutan_forecast_pair=kabutan_fetch_result.pair,
            kabutan_source=kabutan_fetch_result.source,
            kabutan_source_message=kabutan_fetch_result.message,
        )

    def fetch_kabutan_forecast_pair(
        self, code4: str, html_dir: Path | None = None, allow_kabutan_web_fallback: bool = True
    ) -> KabutanFetchResult:
        if html_dir is not None:
            html_candidates = self._build_kabutan_html_candidates(code4=code4, html_dir=html_dir)
            for html_path in html_candidates:
                if html_path.exists():
                    try:
                        repository = self.kabutan_usecase.repository
                        return KabutanFetchResult(pair=repository.fetch_kabutan_forecast_pair_from_file(html_path), source="html")
                    except Exception:
                        continue
            if html_candidates and not allow_kabutan_web_fallback:
                return KabutanFetchResult(pair=None, source="none", message="HTML解析に失敗（Webフォールバック無効）")
            if not allow_kabutan_web_fallback:
                return KabutanFetchResult(pair=None, source="none", message="HTMLファイル未検出（Webフォールバック無効）")
        if allow_kabutan_web_fallback:
            try:
                pair = self.kabutan_usecase.get_kabutan_forecast_pair(code4)
                source_msg = "HTML失敗のためWeb取得" if html_dir is not None else None
                return KabutanFetchResult(pair=pair, source="web", message=source_msg)
            except Exception:
                return KabutanFetchResult(pair=None, source="none", message="Web取得に失敗")
        return KabutanFetchResult(pair=None, source="none", message="株探データ取得を実行しませんでした")

    @staticmethod
    def _build_kabutan_html_candidates(code4: str, html_dir: Path) -> list[Path]:
        direct_candidates = [html_dir / f"{code4}.html", html_dir / f"{code4}.htm"]
        regex = re.compile(rf"(?<!\d){re.escape(code4)}(?!\d)")
        matched_candidates = sorted(
            [
                path
                for path in html_dir.iterdir()
                if path.is_file()
                and path.suffix.lower() in {".html", ".htm"}
                and regex.search(path.stem) is not None
            ]
        )

        candidates: list[Path] = []
        for path in [*direct_candidates, *matched_candidates]:
            if path not in candidates:
                candidates.append(path)
        return candidates


__all__ = ["FundamentalAnalysisService"]
