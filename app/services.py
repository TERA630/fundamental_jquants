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




THRESHOLDS = {
    "op_margin": 10.0,
    "sales_yoy": 10.0,
    "op_yoy": 10.0,
    "equity_ratio": 50.0,
    "roe": 10.0,
    "ocf_np_ratio": 1.0,
    "peg": 1.0,
}


def calc_yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    if previous < 0:
        return None
    return (current / previous - 1) * 100


def progress_rank(progress: float | None, base: float | None) -> str:
    if progress is None or base is None:
        return "N/A"
    diff = progress - base
    if diff >= 10:
        return "◎"
    if diff >= -10:
        return "○"
    if diff >= -15:
        return "△"
    return "×"


def rank_forecast_yoy(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 20:
        return "◎"
    if value >= 10:
        return "○"
    if value >= 0:
        return "△"
    return "×"


def rank_next_yoy(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 15:
        return "◎"
    if value >= 5:
        return "○"
    if value >= 0:
        return "△"
    return "×"


def rank_symbol(value: float | None, metric: str) -> str:
    if value is None:
        return "N/A"
    if metric == "growth":
        if value >= 20:
            return "◎"
        if value >= 10:
            return "○"
        if value >= 0:
            return "△"
        return "×"
    if metric == "op_growth":
        if value >= 30:
            return "◎"
        if value >= 10:
            return "○"
        if value >= 0:
            return "△"
        return "×"
    if metric == "op_margin":
        if value >= 20:
            return "◎"
        if value >= 10:
            return "○"
        if value >= 5:
            return "△"
        return "×"
    if metric == "equity_ratio":
        if value >= 60:
            return "◎"
        if value >= 40:
            return "○"
        if value >= 30:
            return "△"
        return "×"
    if metric == "roe":
        if value >= 15:
            return "◎"
        if value >= 10:
            return "○"
        if value >= 5:
            return "△"
        return "×"
    if metric == "cf":
        if value >= 1.2:
            return "◎"
        if value >= 1.0:
            return "○"
        if value >= 0.8:
            return "△"
        return "×"
    if metric == "peg":
        if value < 1.0:
            return "◎"
        if value < 1.5:
            return "○"
        if value < 2.5:
            return "△"
        return "×"
    return "N/A"


def grade_summary(metrics: dict[str, Any]) -> tuple[int, int, int, int, str]:
    actual_checks = [
        metrics.get("yoy_sales") is not None and metrics["yoy_sales"] >= THRESHOLDS["sales_yoy"],
        metrics.get("op_yoy") is not None and metrics["op_yoy"] >= THRESHOLDS["op_yoy"],
        metrics.get("op_margin") is not None and metrics["op_margin"] >= THRESHOLDS["op_margin"],
        metrics.get("eq_ratio") is not None and metrics["eq_ratio"] >= THRESHOLDS["equity_ratio"],
        metrics.get("roe") is not None and metrics["roe"] >= THRESHOLDS["roe"],
        metrics.get("ocf_np_ratio") is not None and metrics["ocf_np_ratio"] >= THRESHOLDS["ocf_np_ratio"],
        metrics.get("peg") is not None and metrics["peg"] <= THRESHOLDS["peg"],
    ]
    actual_score = sum(bool(x) for x in actual_checks)

    forecast_checks = [
        metrics.get("forecast_sales_yoy") is not None and metrics["forecast_sales_yoy"] >= 10,
        metrics.get("forecast_op_yoy") is not None and metrics["forecast_op_yoy"] >= 10,
        metrics.get("forecast_eps_yoy") is not None and metrics["forecast_eps_yoy"] >= 10,
        metrics.get("op_progress") is not None and metrics.get("progress_base") is not None and metrics["op_progress"] >= metrics["progress_base"] - 10,
        metrics.get("next_op_yoy") is not None and metrics["next_op_yoy"] >= 5,
    ]
    forecast_available = any(metrics.get(k) is not None for k in ["forecast_sales_yoy", "forecast_op_yoy", "forecast_eps_yoy", "op_progress", "next_op_yoy"])
    forecast_score = sum(bool(x) for x in forecast_checks) if forecast_available else 0
    total_score = actual_score + forecast_score
    total_max = 12 if forecast_available else 7

    if forecast_available:
        if total_score >= 9:
            label = "A. ファンダ優良候補"
        elif total_score >= 7:
            label = "B. 監視上位"
        elif total_score >= 5:
            label = "C. 監視継続"
        else:
            label = "D. ファンダ面では慎重"
    else:
        if actual_score >= 6:
            label = "A. ファンダ優良候補"
        elif actual_score >= 5:
            label = "B. 監視上位"
        elif actual_score >= 3:
            label = "C. 監視継続"
        else:
            label = "D. ファンダ面では慎重"
    return actual_score, forecast_score, total_score, total_max, label


__all__ = ["FundamentalAnalysisService", "calc_yoy", "progress_rank", "rank_forecast_yoy", "rank_next_yoy", "rank_symbol", "grade_summary"]
