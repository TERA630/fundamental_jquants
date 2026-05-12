"""Business layer: use-case orchestration for fundamental analysis."""

from __future__ import annotations

from typing import Any

from app.repositories import (
    FileCache,
    JQuantsClient,
    fetch_yfinance_snapshot,
    normalize_code,
)

CACHE_TTL_MASTER_SEC = 30 * 24 * 60 * 60
CACHE_TTL_SUMMARY_SEC = 24 * 60 * 60
CACHE_TTL_YF_SEC = 12 * 60 * 60


class FundamentalAnalysisService:
    """ビジネス層: 取得済みデータから分析出力を構築するユースケース。"""

    def __init__(self, api_key: str, file_cache: FileCache | None = None):
        self.client = JQuantsClient(api_key)
        self.cache = file_cache or FileCache()

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
        snapshot = self.cache.get_or_fetch(
            f"yf_{code4}",
            CACHE_TTL_YF_SEC,
            lambda: fetch_yfinance_snapshot(code4),
        )
        if not isinstance(snapshot, dict):
            return {"price": None, "market_cap": None}
        return {
            "price": snapshot.get("price"),
            "market_cap": snapshot.get("market_cap"),
        }

    def build_analysis_output(self, name: str, code4: str) -> str:
        from fundamental_jquants_v7 import build_output

        master = self.fetch_master(code4)
        summary_rows = self.fetch_summary_rows(code4)
        price_snapshot = self.fetch_price_snapshot(code4)
        return build_output(
            name=name,
            code4=code4,
            master=master,
            summary_rows=summary_rows,
            price=price_snapshot.get("price"),
            market_cap=price_snapshot.get("market_cap"),
        )


__all__ = ["FundamentalAnalysisService"]
