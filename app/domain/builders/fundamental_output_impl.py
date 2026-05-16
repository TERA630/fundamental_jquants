"""Domain output implementation without legacy module dependency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.models.metrics import calc_metrics
from app.domain.policies.ranking import grade_summary, rank_forecast_yoy, rank_next_yoy, rank_progress, rank_symbol


def _first_present(data: dict[str, Any] | None, keys: list[str]) -> Any:
    if not data:
        return None
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _fmt_num(v: float | None, digits: int = 2) -> str:
    return "N/A" if v is None else f"{v:,.{digits}f}"


def _fmt_pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v:+.2f}%"


def _fmt_plain_pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v:.2f}%"


def _fmt_money(v: float | None) -> str:
    return "N/A" if v is None else f"{v / 100_000_000:,.1f}億円"

def _calc_yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100

def _build_market_cap_rank(v: float | None) -> str:
    if v is None:
        return "N/A"
    oku = v / 100_000_000
    if oku >= 100_000:
        return "超大型"
    if oku >= 10_000:
        return "大型主役"
    if oku >= 3_000:
        return "中型主役"
    if oku >= 1_000:
        return "小〜中型"
    return "小型"


@dataclass(frozen=True)
class _Record:
    fiscal_year: int
    period_type: str
    row: dict[str, Any]
    cur_per_st: str = ""
    cur_per_en: str = ""
    disclosed_at: str = ""


def _build_non_empty_count(row: dict[str, Any], keys: list[str]) -> int:
    return sum(1 for key in keys if row.get(key) not in (None, ""))


def _build_merged_period_row(preferred_row: dict[str, Any], supplement_row: dict[str, Any]) -> dict[str, Any]:
    """preferred_rowを優先し、空値のみsupplement_rowで補完する。"""
    merged = dict(supplement_row)
    for key, value in preferred_row.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _build_merged_period_record(preferred: _Record, supplement: _Record) -> _Record:
    """開示優先レコードを維持しつつ、空値は同年度同期間の別レコードで補完する。"""
    return _Record(
        fiscal_year=preferred.fiscal_year,
        period_type=preferred.period_type,
        row=_build_merged_period_row(preferred.row, supplement.row),
        cur_per_st=preferred.cur_per_st or supplement.cur_per_st,
        cur_per_en=preferred.cur_per_en or supplement.cur_per_en,
        disclosed_at=preferred.disclosed_at or supplement.disclosed_at,
    )


def _build_periods(summary_rows: list[dict[str, Any]]):
    periods_by_year: dict[int, dict[str, _Record]] = {}
    records_by_fy_end: dict[str, list[_Record]] = {}
    latest_any = None
    for row in summary_rows:
        ptype = str(_first_present(row, ["CurPerType", "TypeOfCurrentPeriod", "CurrentPeriod", "PeriodType", "ToCP", "Tocp"]) or "").upper()
        if "1Q" in ptype or "Q1" in ptype:
            pt = "1Q"
        elif "2Q" in ptype or "Q2" in ptype or "HALF" in ptype:
            pt = "2Q"
        elif "3Q" in ptype or "Q3" in ptype:
            pt = "3Q"
        elif "FY" in ptype or "ANNUAL" in ptype or "FULL" in ptype:
            pt = "FY"
        else:
            continue
        cur_st = str(_first_present(row, ["CurPerSt", "CurrentPeriodStartDate", "CurrentFiscalYearStartDate"]) or "")
        year = int(cur_st[:4]) if len(cur_st) >= 4 and cur_st[:4].isdigit() else None
        if year is None:
            continue
        rec = _Record(year, pt, row, cur_st, str(_first_present(row,["CurPerEn","CurrentPeriodEndDate","CurrentFiscalYearEndDate"]) or ""), str(_first_present(row,["DisclosedDate","Date"]) or ""))
        if rec.cur_per_en:
            records_by_fy_end.setdefault(rec.cur_per_en, []).append(rec)
        if latest_any is None or rec.disclosed_at >= latest_any.disclosed_at:
            latest_any = rec
        year_map = periods_by_year.setdefault(rec.fiscal_year, {})
        old = year_map.get(rec.period_type)
        if old is None:
            year_map[rec.period_type] = rec
        elif rec.disclosed_at >= old.disclosed_at:
            year_map[rec.period_type] = _build_merged_period_record(rec, old)
        else:
            year_map[rec.period_type] = _build_merged_period_record(old, rec)

    fy_years = sorted((y for y, per in periods_by_year.items() if "FY" in per), reverse=True)
    latest_fy = periods_by_year[fy_years[0]]["FY"] if fy_years else None
    prev_fy = None
    if latest_fy is not None:
        prev_fy = periods_by_year.get(latest_fy.fiscal_year - 1, {}).get("FY")
        if prev_fy is None and len(fy_years) >= 2:
            prev_fy = periods_by_year[fy_years[1]]["FY"]

    latest_q = None
    for year in sorted(periods_by_year.keys(), reverse=True):
        for ptype in ("3Q", "2Q", "1Q"):
            rec = periods_by_year[year].get(ptype)
            if rec is not None:
                latest_q = rec
                break
        if latest_q is not None:
            break
    current_forecast = None
    next_forecast = None
    forecast_anchor_fy_end = ""
    if latest_any is not None and latest_any.cur_per_en:
        forecast_anchor_fy_end = latest_any.cur_per_en
    elif latest_fy is not None and latest_fy.cur_per_en:
        forecast_anchor_fy_end = latest_fy.cur_per_en
    if forecast_anchor_fy_end and forecast_anchor_fy_end in records_by_fy_end:
        candidate_rows = sorted(records_by_fy_end[forecast_anchor_fy_end], key=lambda x: x.disclosed_at, reverse=True)
        current_forecast = candidate_rows[0]
        for rec in candidate_rows[1:]:
            current_forecast = _build_merged_period_record(current_forecast, rec)

        next_forecast = max(
            candidate_rows,
            key=lambda rec: (
                _build_non_empty_count(rec.row, ["NxFSales", "NxFsales", "NxFOP", "NxFOdP", "NxFODP", "NxFNP", "NxFEPS"]),
                rec.disclosed_at,
            ),
        )

    return type(
        "Periods",
        (),
        {
            "latest_fy": latest_fy,
            "prev_fy": prev_fy,
            "latest_quarter": latest_q,
            "current_forecast": current_forecast,
            "next_forecast": next_forecast,
        },
    )


def build_fundamental_output_text_impl(*, name: str, code4: str, master: dict[str, Any] | None, summary_rows: list[dict[str, Any]], price: float | None, market_cap: float | None) -> str:
    periods = _build_periods(summary_rows)
    if periods.latest_fy is None:
        return f"【銘柄】{name} ({code4})\n\n通期(FY)データを抽出できませんでした。"

    metrics = calc_metrics(periods, price)
    actual_score, forecast_score, total_score, total_max, grade = grade_summary(metrics)
    company_name = str(_first_present(master, ["CompanyName", "Name", "LocalCodeName"]) or name)
    sector33 = str(_first_present(master, ["S33Nm", "Sector33CodeName", "Sector33Name"]) or "N/A")

    lines = [
        f"【銘柄】{company_name} ({code4})",
        "■指標",
        f"株価：{_fmt_num(price,0)}円 / PER：{_fmt_num(metrics.get('per'))} / PBR：{_fmt_num(metrics.get('pbr'))}",
        f"業種：{sector33}　時価総額：{_fmt_money(market_cap)}({_build_market_cap_rank(market_cap)})",
        f"配当利回り：{_fmt_plain_pct(metrics.get('div_yield'))}(配当性向 {_fmt_plain_pct(metrics.get('payout'))})",
        "",
        f"スコア：実績 {actual_score}/7 / 予想進捗 {forecast_score}/5 / 総合 {total_score}/{total_max}",
        f"総合評価：{grade}",
        f"■実績比較（最新{getattr(periods.latest_fy, 'fiscal_year', 'N/A')}年FY←{getattr(periods.prev_fy, 'fiscal_year', 'N/A')}年FY）",
        f"売上高：{_fmt_money(metrics.get('sales'))}(YoY {_fmt_pct(metrics.get('yoy_sales'))})←{_fmt_money(metrics.get('prev_sales'))}",
        f"営業利益：{_fmt_money(metrics.get('op'))}(YoY {_fmt_pct(metrics.get('op_yoy'))})←{_fmt_money(metrics.get('prev_op'))}",
        f"営業利益率：{_fmt_plain_pct(metrics.get('op_margin'))} ← {_fmt_plain_pct(metrics.get('prev_op_margin'))}",
        f"純利益：{_fmt_money(metrics.get('np'))}(YoY {_fmt_pct(_calc_yoy(metrics.get('np'), metrics.get('prev_np')))})←{_fmt_money(metrics.get('prev_np'))}",
        f"EPS：{_fmt_num(metrics.get('eps'),0)}円(YoY {_fmt_pct(_calc_yoy(metrics.get('eps'), metrics.get('prev_eps')))})←{_fmt_num(metrics.get('prev_eps'),0)}円",
        "",
        f"■今期会社予想({getattr(periods.latest_quarter, 'fiscal_year', getattr(periods.latest_fy, 'fiscal_year', 'N/A'))}年{getattr(periods.latest_quarter, 'period_type', 'FY')})",
        f"売り上げ予想：{_fmt_money(metrics.get('forecast_sales'))}(YoY {_fmt_pct(metrics.get('forecast_sales_yoy'))})",
        f"営業利益予想：{_fmt_money(metrics.get('forecast_op'))}(YoY {_fmt_pct(metrics.get('forecast_op_yoy'))})",
        "",
        f"■売り上げ予想({getattr(periods.latest_fy, 'fiscal_year', 'N/A') + 1 if periods.latest_fy else 'N/A'}年FY)",
        f"売上予想：{_fmt_money(metrics.get('next_sales'))}（今期比 {_fmt_pct(metrics.get('next_sales_yoy'))}）",
        f"営業利益予想：{_fmt_money(metrics.get('next_op'))}（今期比 {_fmt_pct(metrics.get('next_op_yoy'))}）",
        f"予想EPS：{_fmt_num(metrics.get('next_eps'),0)}円(今期比 {_fmt_pct(metrics.get('next_eps_yoy'))})",
        f"ランク：成長 {rank_symbol(metrics.get('yoy_sales'),'growth')} / 収益 {rank_symbol(metrics.get('op_margin'),'op_margin')} / 進捗 {rank_progress(metrics.get('op_progress'), metrics.get('progress_base'))} / 来期 {rank_next_yoy(metrics.get('next_op_yoy'))}",
    ]
    return "\n".join(lines)
