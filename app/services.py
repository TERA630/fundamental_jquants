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




def calc_metrics(periods: Any, price: float | None) -> dict[str, float | str | None]:
    """年度×期間種別へ正規化済みデータから、実績・予想・進捗指標を計算する。"""
    from fundamental_jquants_v7 import (
        format_period_record,
        get_value,
        progress_base_from_period_type,
        row_from_record,
    )

    latest_fy_rec = periods.latest_fy
    prev_fy_rec = periods.prev_fy
    latest_quarter_rec = periods.latest_quarter

    latest_fy = row_from_record(latest_fy_rec)
    prev_fy = row_from_record(prev_fy_rec)
    latest_quarter = row_from_record(latest_quarter_rec)

    if latest_fy is None:
        return {}

    sales = get_value(latest_fy, ["Sales"], ["NetSales", "Revenue", "TotalRevenue"])
    prev_sales = get_value(prev_fy, ["Sales"], ["NetSales", "Revenue", "TotalRevenue"])

    op = get_value(latest_fy, ["OP", "Op"], ["OperatingProfit", "OperatingIncome"])
    prev_op = get_value(prev_fy, ["OP", "Op"], ["OperatingProfit", "OperatingIncome"])
    ordinary = get_value(latest_fy, ["OrdP", "OdP", "OrdinaryProfit"], ["OrdinaryIncome"])
    np = get_value(latest_fy, ["NP"], ["Profit", "NetIncome", "ProfitAttributableToOwnersOfParent"])
    prev_np = get_value(prev_fy, ["NP"], ["Profit", "NetIncome", "ProfitAttributableToOwnersOfParent"])

    eps = get_value(latest_fy, ["EPS"], ["EarningsPerShare"])
    prev_eps = get_value(prev_fy, ["EPS"], ["EarningsPerShare"])
    bps = get_value(latest_fy, ["BPS"], ["BookValuePerShare"])
    eq_ratio = get_value(latest_fy, ["EqAR"], ["EquityToAssetRatio", "CapitalAdequacyRatio"])
    if eq_ratio is not None and eq_ratio <= 1.0:
        eq_ratio *= 100
    div_ann = get_value(latest_fy, ["DivAnn"], ["AnnualDividendPerShare", "DividendPerShareAnnual"])
    payout = get_value(latest_fy, ["PayoutRatioAnn"], ["PayoutRatio"])
    if payout is not None and payout <= 1.0:
        payout *= 100

    ocf = get_value(latest_fy, ["OCF", "CFO", "NCFO"], ["NetCashProvidedByUsedInOperatingActivities", "OperatingCashFlow"])
    icf = get_value(latest_fy, ["GFI", "CFI", "ICF"], ["NetCashProvidedByUsedInInvestmentActivities", "InvestingCashFlow"])
    fcf = None if ocf is None or icf is None else ocf + icf

    op_margin = None if sales in (None, 0) or op is None else op / sales * 100
    yoy_sales = calc_yoy(sales, prev_sales)
    op_yoy = None
    if op is not None and prev_op not in (None, 0) and prev_op is not None and prev_op > 0 and op >= 0:
        op_yoy = (op / prev_op - 1) * 100
    roe = eps / bps * 100 if bps not in (None, 0) and eps is not None else None
    ocf_np_ratio = None if ocf is None or np in (None, 0) else ocf / np
    per = None if price in (None, 0) or eps in (None, 0) else price / eps
    pbr = None if price in (None, 0) or bps in (None, 0) else price / bps
    div_yield = None if price in (None, 0) or div_ann is None else div_ann / price * 100
    growth_for_peg = yoy_sales
    peg = None if per is None or growth_for_peg in (None, 0) or growth_for_peg is None or growth_for_peg <= 0 else per / growth_for_peg

    forecast_source = latest_quarter or latest_fy
    forecast_sales = get_value(forecast_source, ["FSales"], ["ForecastSales"])
    forecast_op = get_value(forecast_source, ["FOP"], ["ForecastOperatingProfit"])
    forecast_eps = get_value(forecast_source, ["FEPS"], ["ForecastEarningsPerShare"])
    next_sales = get_value(forecast_source, ["NxFSales"], ["NextFiscalYearForecastSales"])
    next_op = get_value(forecast_source, ["NxFOP"], ["NextFiscalYearForecastOperatingProfit"])
    next_eps = get_value(forecast_source, ["NxFEPS"], ["NextFiscalYearForecastEarningsPerShare"])

    forecast_sales_yoy = calc_yoy(forecast_sales, sales)
    forecast_op_yoy = calc_yoy(forecast_op, op)
    forecast_eps_yoy = calc_yoy(forecast_eps, eps)
    next_sales_yoy = calc_yoy(next_sales, forecast_sales)
    next_op_yoy = calc_yoy(next_op, forecast_op)
    next_eps_yoy = calc_yoy(next_eps, forecast_eps)

    progress_label, progress_base = progress_base_from_period_type(latest_quarter_rec.period_type if latest_quarter_rec else None)
    actual_progress_sales = get_value(latest_quarter, ["Sales"], ["NetSales", "Revenue", "TotalRevenue"])
    actual_progress_op = get_value(latest_quarter, ["OP", "Op"], ["OperatingProfit", "OperatingIncome"])
    sales_progress = None if actual_progress_sales is None or forecast_sales in (None, 0) or forecast_sales <= 0 else actual_progress_sales / forecast_sales * 100
    op_progress = None if actual_progress_op is None or forecast_op in (None, 0) or forecast_op <= 0 or actual_progress_op < 0 else actual_progress_op / forecast_op * 100

    return {
        "sales": sales, "prev_sales": prev_sales, "op": op, "prev_op": prev_op, "ordinary": ordinary,
        "np": np, "prev_np": prev_np, "eps": eps, "prev_eps": prev_eps, "bps": bps, "eq_ratio": eq_ratio,
        "div_ann": div_ann, "payout": payout, "ocf": ocf, "icf": icf, "fcf": fcf, "op_margin": op_margin,
        "yoy_sales": yoy_sales, "op_yoy": op_yoy, "roe": roe, "ocf_np_ratio": ocf_np_ratio, "per": per,
        "pbr": pbr, "div_yield": div_yield, "peg": peg, "forecast_sales": forecast_sales, "forecast_op": forecast_op,
        "forecast_eps": forecast_eps, "forecast_sales_yoy": forecast_sales_yoy, "forecast_op_yoy": forecast_op_yoy,
        "forecast_eps_yoy": forecast_eps_yoy, "next_sales": next_sales, "next_op": next_op, "next_eps": next_eps,
        "next_sales_yoy": next_sales_yoy, "next_op_yoy": next_op_yoy, "next_eps_yoy": next_eps_yoy,
        "sales_progress": sales_progress, "op_progress": op_progress, "progress_label": progress_label,
        "progress_base": progress_base, "latest_fy_label": format_period_record(latest_fy_rec),
        "prev_fy_label": format_period_record(prev_fy_rec), "latest_quarter_label": format_period_record(latest_quarter_rec),
        "forecast_source_label": format_period_record(latest_quarter_rec or latest_fy_rec),
    }


__all__ = ["FundamentalAnalysisService", "calc_yoy", "calc_metrics", "progress_rank", "rank_forecast_yoy", "rank_next_yoy", "rank_symbol", "grade_summary"]
