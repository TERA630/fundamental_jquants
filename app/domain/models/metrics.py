"""Domain models: financial metric calculations."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def calc_yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    if previous < 0:
        return None
    return (current / previous - 1) * 100


def calc_metrics(periods: Any, price: float | None) -> dict[str, float | str | None]:
    """年度×期間種別へ正規化済みデータから、実績・予想・進捗指標を計算する。"""
    def row_from_record(record: Any) -> dict[str, Any] | None:
        return None if record is None else record.row

    def format_period_record(record: Any) -> str:
        if record is None:
            return "N/A"
        period = f"{record.cur_per_st}〜{record.cur_per_en}" if record.cur_per_st or record.cur_per_en else "期間N/A"
        disclosed = f" / 開示 {record.disclosed_at}" if record.disclosed_at else ""
        return f"{record.fiscal_year}年度 {record.period_type}（{period}{disclosed}）"

    def progress_base_from_period_type(period_type: str | None) -> tuple[str, float | None]:
        if period_type == "1Q":
            return "1Q", 25.0
        if period_type == "2Q":
            return "2Q", 50.0
        if period_type == "3Q":
            return "3Q", 75.0
        if period_type == "FY":
            return "通期", 100.0
        return "N/A", None

    def safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", ""))
        except Exception:
            return None

    def first_present(data: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    def get_value(row: dict[str, Any] | None, short_keys: list[str], long_keys: list[str] | None = None) -> float | None:
        if not row:
            return None
        short_value = first_present(row, short_keys)
        if short_value not in (None, ""):
            return safe_float(short_value)
        if long_keys:
            long_value = first_present(row, long_keys)
            if long_value not in (None, ""):
                logger.warning("V2短縮キー未検出のため互換キーを使用: short=%s long=%s", short_keys, long_keys)
                return safe_float(long_value)
        return None

    def get_forecast_value(short_keys: list[str], long_keys: list[str] | None = None) -> float | None:
        for source in (latest_quarter, current_forecast, latest_fy):
            value = get_value(source, short_keys, long_keys)
            if value is not None:
                return value
        return None

    def get_next_forecast_value(short_keys: list[str], long_keys: list[str] | None = None) -> float | None:
        for source in (next_forecast, current_forecast, latest_fy):
            value = get_value(source, short_keys, long_keys)
            if value is not None:
                return value
        return None

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
    prev_ordinary = get_value(prev_fy, ["OrdP", "OdP", "OrdinaryProfit"], ["OrdinaryIncome"])
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
    prev_op_margin = None if prev_sales in (None, 0) or prev_op is None else prev_op / prev_sales * 100
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

    current_forecast_rec = getattr(periods, "current_forecast", None)
    next_forecast_rec = getattr(periods, "next_forecast", None)
    current_forecast = row_from_record(current_forecast_rec)
    next_forecast = row_from_record(next_forecast_rec)

    forecast_source = latest_quarter or current_forecast or latest_fy
    forecast_sales = get_forecast_value(["FSales", "Fsales"], ["ForecastSales"])
    forecast_op = get_forecast_value(["FOP"], ["ForecastOperatingProfit"])
    forecast_ordinary = get_forecast_value(["FOdP", "FODP"], ["ForecastOrdinaryProfit"])
    forecast_np = get_forecast_value(["FNP"], ["ForecastProfit", "ForecastNetIncome"])
    forecast_eps = get_forecast_value(["FEPS"], ["ForecastEarningsPerShare"])
    next_sales = get_next_forecast_value(["NxFSales", "NxFsales"], ["NextFiscalYearForecastSales"])
    next_op = get_next_forecast_value(["NxFOP"], ["NextFiscalYearForecastOperatingProfit"])
    next_ordinary = get_next_forecast_value(["NxFOdP", "NxFODP"], ["NextFiscalYearForecastOrdinaryProfit"])
    next_np = get_next_forecast_value(["NxFNP"], ["NextFiscalYearForecastProfit", "NextFiscalYearForecastNetIncome"])
    next_eps = get_next_forecast_value(["NxFEPS"], ["NextFiscalYearForecastEarningsPerShare"])

    forecast_sales_yoy = calc_yoy(forecast_sales, sales)
    forecast_op_yoy = calc_yoy(forecast_op, op)
    forecast_ordinary_yoy = calc_yoy(forecast_ordinary, ordinary)
    forecast_np_yoy = calc_yoy(forecast_np, np)
    forecast_eps_yoy = calc_yoy(forecast_eps, eps)
    next_sales_yoy = calc_yoy(next_sales, forecast_sales)
    next_op_yoy = calc_yoy(next_op, forecast_op)
    next_ordinary_yoy = calc_yoy(next_ordinary, forecast_ordinary)
    next_np_yoy = calc_yoy(next_np, forecast_np)
    next_eps_yoy = calc_yoy(next_eps, forecast_eps)

    quarter_eps = get_value(latest_quarter, ["EPS"], ["EarningsPerShare"])
    per_forecast = None if price in (None, 0) or forecast_eps in (None, 0) else price / forecast_eps
    per_next = None if price in (None, 0) or next_eps in (None, 0) else price / next_eps
    per_quarter = None if price in (None, 0) or quarter_eps in (None, 0) else price / quarter_eps

    progress_label, progress_base = progress_base_from_period_type(latest_quarter_rec.period_type if latest_quarter_rec else None)
    actual_progress_sales = get_value(latest_quarter, ["Sales"], ["NetSales", "Revenue", "TotalRevenue"])
    actual_progress_op = get_value(latest_quarter, ["OP", "Op"], ["OperatingProfit", "OperatingIncome"])
    sales_progress = None if actual_progress_sales is None or forecast_sales in (None, 0) or forecast_sales <= 0 else actual_progress_sales / forecast_sales * 100
    op_progress = None if actual_progress_op is None or forecast_op in (None, 0) or forecast_op <= 0 or actual_progress_op < 0 else actual_progress_op / forecast_op * 100

    return {
        "sales": sales, "prev_sales": prev_sales, "op": op, "prev_op": prev_op, "ordinary": ordinary, "prev_ordinary": prev_ordinary,
        "np": np, "prev_np": prev_np, "eps": eps, "prev_eps": prev_eps, "bps": bps, "eq_ratio": eq_ratio,
        "div_ann": div_ann, "payout": payout, "ocf": ocf, "icf": icf, "fcf": fcf, "op_margin": op_margin, "prev_op_margin": prev_op_margin,
        "yoy_sales": yoy_sales, "op_yoy": op_yoy, "roe": roe, "ocf_np_ratio": ocf_np_ratio, "per": per,
        "pbr": pbr, "div_yield": div_yield, "peg": peg, "forecast_sales": forecast_sales, "forecast_op": forecast_op,
        "forecast_ordinary": forecast_ordinary, "forecast_np": forecast_np, "forecast_eps": forecast_eps,
        "forecast_sales_yoy": forecast_sales_yoy, "forecast_op_yoy": forecast_op_yoy,
        "forecast_ordinary_yoy": forecast_ordinary_yoy, "forecast_np_yoy": forecast_np_yoy, "forecast_eps_yoy": forecast_eps_yoy,
        "next_sales": next_sales, "next_op": next_op, "next_ordinary": next_ordinary, "next_np": next_np, "next_eps": next_eps,
        "next_sales_yoy": next_sales_yoy, "next_op_yoy": next_op_yoy, "next_ordinary_yoy": next_ordinary_yoy, "next_np_yoy": next_np_yoy, "next_eps_yoy": next_eps_yoy,
        "eps_forecast": forecast_eps, "eps_next": next_eps, "eps_quarter": quarter_eps,
        "per_forecast": per_forecast, "per_next": per_next, "per_quarter": per_quarter,
        "sales_progress": sales_progress, "op_progress": op_progress, "progress_label": progress_label,
        "progress_base": progress_base, "latest_fy_label": format_period_record(latest_fy_rec),
        "prev_fy_label": format_period_record(prev_fy_rec), "latest_quarter_label": format_period_record(latest_quarter_rec),
        "forecast_source_label": format_period_record(latest_quarter_rec or current_forecast_rec or latest_fy_rec),
    }

__all__ = ["calc_yoy", "calc_metrics"]
