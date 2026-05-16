"""Domain use-case: orchestration for fundamental analysis."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from app.data.file_cache import FileCache
from app.data.jquants_client import JQuantsClient
from app.data.market_data_provider import fetch_yfinance_snapshot
from app.data.utils import normalize_code

CACHE_TTL_MASTER_SEC = 30 * 24 * 60 * 60
CACHE_TTL_SUMMARY_SEC = 24 * 60 * 60
CACHE_TTL_YF_SEC = 12 * 60 * 60


class JQuantsClientPort(Protocol):
    def get_master(self, code: str) -> dict[str, Any] | None: ...
    def get_summary(self, code: str) -> list[dict[str, Any]]: ...


class MarketDataProviderPort(Protocol):
    def __call__(self, code4: str) -> dict[str, float | None]: ...


class FundamentalAnalysisService:
    """ドメイン層ユースケース: 分析出力の組み立て実行を担当。"""

    def __init__(
        self,
        api_key: str,
        file_cache: FileCache | None = None,
        client: JQuantsClientPort | None = None,
        fetch_market_snapshot: MarketDataProviderPort | None = None,
    ):
        self.client = client or JQuantsClient(api_key)
        self.cache = file_cache or FileCache()
        self.fetch_market_snapshot = fetch_market_snapshot or fetch_yfinance_snapshot

    def fetch_master(self, code4: str) -> dict[str, Any] | None:
        code5 = normalize_code(code4)
        return self.cache.get_or_fetch(
            f"master_{code5}",
            CACHE_TTL_MASTER_SEC,
            lambda: self.client.get_master(code4),
        )

    def fetch_summary_rows(self, code4: str) -> list[dict[str, Any]]:
        code5 = normalize_code(code4)
        rows = self.cache.get_or_fetch(
            f"summary_{code5}",
            CACHE_TTL_SUMMARY_SEC,
            lambda: self.client.get_summary(code4),
        )
        return rows if isinstance(rows, list) else []

    def fetch_price_snapshot(self, code4: str) -> dict[str, float | None]:
        cache_key = f"yf_{code4}"
        if hasattr(self.cache, "get") and hasattr(self.cache, "set"):
            cached = self.cache.get(cache_key, CACHE_TTL_YF_SEC)
            if cached is not None and isinstance(cached, dict):
                return {
                    "price": cached.get("price"),
                    "market_cap": cached.get("market_cap"),
                }
            snapshot = self.fetch_market_snapshot(code4)
            if isinstance(snapshot, dict) and snapshot.get("price") is not None:
                self.cache.set(cache_key, snapshot)
        else:
            snapshot = self.cache.get_or_fetch(
                cache_key,
                CACHE_TTL_YF_SEC,
                lambda: self.fetch_market_snapshot(code4),
            )
        if not isinstance(snapshot, dict):
            return {"price": None, "market_cap": None}
        return {
            "price": snapshot.get("price"),
            "market_cap": snapshot.get("market_cap"),
        }

    def build_analysis_output(self, name: str, code4: str, build_output_fn: Callable[..., str]) -> str:
        master = self.fetch_master(code4)
        summary_rows = self.fetch_summary_rows(code4)
        price_snapshot = self.fetch_price_snapshot(code4)
        return build_output_fn(
            name=name,
            code4=code4,
            master=master,
            summary_rows=summary_rows,
            price=price_snapshot.get("price"),
            market_cap=price_snapshot.get("market_cap"),
        )


__all__ = ["FundamentalAnalysisService"]
