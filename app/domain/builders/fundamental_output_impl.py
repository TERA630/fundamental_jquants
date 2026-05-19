"""Domain output implementation without legacy module dependency."""

from __future__ import annotations

from typing import Any

from app.domain.models.metrics import calc_metrics
from app.domain.models.periods import fetch_period_set
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


def _build_periods(summary_rows: list[dict[str, Any]]):
    """互換API: 期間抽出の本体はmodels.periodsへ移譲。"""
    return fetch_period_set(summary_rows)


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
        "■EPS/PER比較（来期予想・今期末予想・直近四半期）",
        f"EPS(円)：来期 {_fmt_num(metrics.get('eps_next'),1)} / 今期末 {_fmt_num(metrics.get('eps_forecast'),1)} / 直近四半期 {_fmt_num(metrics.get('eps_quarter'),1)}",
        f"PER(倍)：来期 {_fmt_num(metrics.get('per_next'))} / 今期末 {_fmt_num(metrics.get('per_forecast'))} / 直近四半期 {_fmt_num(metrics.get('per_quarter'))}",
        "",
        f"■売り上げ予想({getattr(periods.latest_fy, 'fiscal_year', 'N/A') + 1 if periods.latest_fy else 'N/A'}年FY)",
        f"売上予想：{_fmt_money(metrics.get('next_sales'))}（今期比 {_fmt_pct(metrics.get('next_sales_yoy'))}）",
        f"営業利益予想：{_fmt_money(metrics.get('next_op'))}（今期比 {_fmt_pct(metrics.get('next_op_yoy'))}）",
        f"予想EPS：{_fmt_num(metrics.get('next_eps'),0)}円(今期比 {_fmt_pct(metrics.get('next_eps_yoy'))})",
        f"ランク：成長 {rank_symbol(metrics.get('yoy_sales'),'growth')} / 収益 {rank_symbol(metrics.get('op_margin'),'op_margin')} / 進捗 {rank_progress(metrics.get('op_progress'), metrics.get('progress_base'))} / 来期 {rank_next_yoy(metrics.get('next_op_yoy'))}",
    ]
    return "\n".join(lines)
