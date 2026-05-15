"""Domain output builder implementation (Phase2 PR1)."""

from __future__ import annotations

from typing import Any

import fundamental_jquants_v7 as legacy


def build_fundamental_output_text_impl(
    *,
    name: str,
    code4: str,
    master: dict[str, Any] | None,
    summary_rows: list[dict[str, Any]],
    price: float | None,
    market_cap: float | None = None,
) -> str:
    """ドメイン層の出力生成実体（legacy依存を段階縮小するための移植第1段）。"""
    company_name = name
    sector33 = ""

    if master:
        company_name = str(legacy.first_present(master, [
            "CompanyName", "Name", "LocalCodeName", "CompanyNameEnglish", "CompanyNameFull"
        ]) or name)
        sector33 = str(legacy.first_present(master, ["S33Nm", "Sector33CodeName", "Sector33Name", "s33n", "Sector33"]) or "")

    periods = legacy.build_period_index(summary_rows)
    if periods.latest_fy is None:
        period_lines = legacy.render_period_index_table(periods)
        return "\n".join([
            f"【銘柄】{name} ({code4})",
            "",
            "取得失敗：CurPerType=FY の通期決算データを抽出できませんでした。",
            "J-Quantsのsummaryレスポンス自体は取得できている可能性があるため、下の期間整理を確認してください。",
            "",
            *period_lines,
        ])

    metrics = legacy.service_calc_metrics(periods, price)
    actual_score, forecast_score, total_score, total_max, grade = legacy.service_grade_summary(metrics)

    sales_rank = legacy.service_rank_symbol(metrics.get("yoy_sales"), "growth")
    op_rank = legacy.service_rank_symbol(metrics.get("op_yoy"), "op_growth")
    profitability_rank = legacy.service_rank_symbol(metrics.get("op_margin"), "op_margin")
    roe_rank = legacy.service_rank_symbol(metrics.get("roe"), "roe")
    cf_rank = legacy.service_rank_symbol(metrics.get("ocf_np_ratio"), "cf")
    financial_rank = legacy.service_rank_symbol(metrics.get("eq_ratio"), "equity_ratio")
    valuation_rank = legacy.service_rank_symbol(metrics.get("peg"), "peg")

    forecast_rank = legacy.service_rank_forecast_yoy(metrics.get("forecast_op_yoy") if metrics.get("forecast_op_yoy") is not None else metrics.get("forecast_sales_yoy"))
    progress_rank_value = legacy.service_progress_rank(metrics.get("op_progress"), metrics.get("progress_base"))
    next_rank_value = legacy.service_rank_next_yoy(metrics.get("next_op_yoy") if metrics.get("next_op_yoy") is not None else metrics.get("next_sales_yoy"))

    lines: list[str] = []
    lines.extend([
        f"【銘柄】{company_name} ({code4})",
        "",
        "■総合評価",
        f"判定：{grade}",
        f"スコア：{legacy.fmt_score(actual_score, forecast_score, total_score, total_max)}",
        "",
        f"成長性：売上 {sales_rank} / 営業利益 {op_rank}",
        f"会社予想：今期 {forecast_rank} / 進捗 {progress_rank_value} / 来期 {next_rank_value}",
        f"収益性：{profitability_rank}",
        f"資本効率：{roe_rank}",
        f"キャッシュ創出力：{cf_rank}",
        f"財務健全性：{financial_rank}",
        f"割安性：{valuation_rank}",
        "",
    ])

    view_model = legacy.build_output_view_model(company_name, code4, sector33, market_cap, periods)

    lines.extend([
        "■株価･割安性",
        f"株価　　　　：{legacy.fmt_num(price, 0)}円（yFinance取得）",
        f"PER(PEG)　　：{legacy.fmt_num(metrics.get('per'))}倍（{legacy.fmt_num(metrics.get('peg'))}倍）",
        f"PBR　　　 　：{legacy.fmt_num(metrics.get('pbr'))}倍",
        f"EPS/BPS　 　：{legacy.fmt_num(metrics.get('eps'))}円 / {legacy.fmt_num(metrics.get('bps'))}円",
        f"配当利回り　：{legacy.fmt_plain_pct(metrics.get('div_yield'))}（配当性向 {legacy.fmt_plain_pct(metrics.get('payout'))}）",
        "",
        "■時価総額･業種",
        f"時価総額　　：{view_model.market_cap_text}　({view_model.market_cap_band_label})",
        f"業種　　　　：{view_model.sector33}",
        "",
        "■主要指標",
        "",
        legacy.build_fy_compare_line("売上高　　　", metrics.get("sales"), metrics.get("prev_sales"), view_model.latest_year, view_model.prev_year),
        legacy.build_fy_compare_line("営業利益　　", metrics.get("op"), metrics.get("prev_op"), view_model.latest_year, view_model.prev_year),
        legacy.build_fy_compare_line("営業利益率　", metrics.get("op_margin"), metrics.get("prev_op_margin"), view_model.latest_year, view_model.prev_year, value_kind="percent", include_yoy=False),
        legacy.build_fy_compare_line("経常利益　　", metrics.get("ordinary"), metrics.get("prev_ordinary"), view_model.latest_year, view_model.prev_year),
        legacy.build_fy_compare_line("純利益　　　", metrics.get("np"), metrics.get("prev_np"), view_model.latest_year, view_model.prev_year),
        legacy.build_fy_compare_line("EPS　　　 　", metrics.get("eps"), metrics.get("prev_eps"), view_model.latest_year, view_model.prev_year, value_kind="number"),
        "",
        f"ROE　　　　 ：{legacy.fmt_plain_pct(metrics.get('roe'))}",
        f"自己資本比率：{legacy.fmt_plain_pct(metrics.get('eq_ratio'))}",
        f"営業CF　　　：{legacy.fmt_money(metrics.get('ocf'))}",
        "",
        "■今期会社予想",
        f"売上予想：{legacy.fmt_money(metrics.get('forecast_sales'))}（YoY {legacy.fmt_pct(metrics.get('forecast_sales_yoy'))}） → {legacy.service_rank_forecast_yoy(metrics.get('forecast_sales_yoy'))}",
        f"営業利益予想：{legacy.fmt_money(metrics.get('forecast_op'))}（YoY {legacy.fmt_pct(metrics.get('forecast_op_yoy'))}） → {legacy.service_rank_forecast_yoy(metrics.get('forecast_op_yoy'))}",
        f"EPS予想：{legacy.fmt_num(metrics.get('forecast_eps'))}円（YoY {legacy.fmt_pct(metrics.get('forecast_eps_yoy'))}）",
        "",
        "■直近四半期･進捗",
        *legacy.render_quarter_table(periods, metrics)[1:],
        "",
        "■来季予想",
        f"売上予想：{legacy.fmt_money(metrics.get('next_sales'))}（今期比 {legacy.fmt_pct(metrics.get('next_sales_yoy'))}） → {legacy.service_rank_next_yoy(metrics.get('next_sales_yoy'))}",
        f"営業利益予想：{legacy.fmt_money(metrics.get('next_op'))}（今期比 {legacy.fmt_pct(metrics.get('next_op_yoy'))}） → {legacy.service_rank_next_yoy(metrics.get('next_op_yoy'))}",
        f"EPS予想：{legacy.fmt_num(metrics.get('next_eps'))}円（今期比 {legacy.fmt_pct(metrics.get('next_eps_yoy'))}）",
        "",
        "■ キャッシュフロー",
        f"営業CF：{legacy.fmt_money(metrics.get('ocf'))}",
        f"投資CF：{legacy.fmt_money(metrics.get('icf'))}",
        f"簡易FCF：{legacy.fmt_money(metrics.get('fcf'))}",
        f"営業CF/純利益：{legacy.fmt_num(metrics.get('ocf_np_ratio'))}倍 → {legacy.eval_mark(metrics.get('ocf_np_ratio'), legacy.THRESHOLDS['ocf_np_ratio'])}",
        "",
        "■評価コメント",
    ])

    if metrics.get("yoy_sales") is not None and metrics["yoy_sales"] >= 10:
        lines.append("売上は高成長。")
    if metrics.get("op_yoy") is not None and metrics["op_yoy"] >= 10:
        lines.append("営業利益も増益基調。")
    if metrics.get("forecast_op_yoy") is not None and metrics["forecast_op_yoy"] >= 10:
        lines.append("今期会社予想も増益基調で、ファンダ面では監視優先度は高い。")
    elif metrics.get("forecast_op_yoy") is not None and metrics["forecast_op_yoy"] < 0:
        lines.append("今期会社予想は営業減益であり、実績が良くても今期の減速リスクを重視する。")
    if len(lines) > 0 and lines[-1] == "■評価コメント":
        lines.append("明確な強弱は限定的。テクニカル位置と決算進捗を併せて判断する。")

    lines.extend(["", "■取得済み決算期間整理", *legacy.render_period_index_table(periods)[1:]])
    return "\n".join(lines)


__all__ = ["build_fundamental_output_text_impl"]
