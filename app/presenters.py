"""Presentation helpers: bridge GUI use-cases and domain/output builders."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.domain.builders.fundamental_output import build_fundamental_output_text
from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastRow


def fetch_watchlist(path: Path) -> list[tuple[str, str]]:
    """監視銘柄ファイルを読み込み、GUI用の銘柄一覧へ整形して返す。"""
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp932"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"監視銘柄ファイルを読み込めませんでした: {last_error}")
    patterns = [
        re.compile(r"[-*]?\s*([^\n()（）]+?)\s*[\(（]\s*(\d{4})\s*[\)）]"),
        re.compile(r"^\s*(\d{4})\s*[-,:：\t ]+\s*([^\n]+?)\s*$"),
        re.compile(r"^\s*([^\n,，\t]+?)\s*[,，\t]\s*(\d{4})\s*$"),
    ]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = ""
        code = ""
        for idx, pattern in enumerate(patterns):
            m = pattern.search(line)
            if not m:
                continue
            if idx == 1:
                code = m.group(1).strip()
                name = m.group(2).strip()
            else:
                name = m.group(1).strip()
                code = m.group(2).strip()
            break
        if not code or code in seen:
            continue
        seen.add(code)
        out.append((name, code))
    if not out:
        raise ValueError("監視銘柄ファイルから銘柄を抽出できませんでした。")
    return out


def build_fundamental_output(
    *,
    name: str,
    code4: str,
    master: dict[str, Any] | None,
    summary_rows: list[dict[str, Any]],
    price: float | None,
    market_cap: float | None,
    kabutan_forecast_pair: KabutanForecastPair | None = None,
    kabutan_source: str = "none",
    kabutan_source_message: str | None = None,
) -> str:
    """ドメイン層の出力生成ビルダーを呼び出す。"""
    base_output = build_fundamental_output_text(
        name=name,
        code4=code4,
        master=master,
        summary_rows=summary_rows,
        price=price,
        market_cap=market_cap,
    )
    return build_kabutan_forecast_output(base_output, kabutan_forecast_pair, kabutan_source, kabutan_source_message)


def _fmt_oku(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 100:,.1f}億"


def _build_kabutan_row_line(row: KabutanForecastRow) -> str:
    year_label = f"{row.year}年(予)" if row.section == "予想" else f"{row.year}年"
    return (
        f"{year_label:<10}"
        f"{_fmt_oku(row.sales):>10}"
        f"{_fmt_oku(row.operating_profit):>10}"
        f"{_fmt_oku(row.ordinary_profit):>10}"
        f"{_fmt_oku(row.final_profit):>10}"
    )


def _build_kabutan_na_row_line(label: str) -> str:
    return f"{label:<10}{'N/A':>10}{'N/A':>10}{'N/A':>10}{'N/A':>10}"


def _build_kabutan_source_label(source: str, message: str | None) -> str:
    source_label = {"html": "HTML", "web": "Web", "none": "取得不可"}.get(source, "取得不可")
    return f"株探ソース: {source_label}" if not message else f"株探ソース: {source_label} ({message})"


def build_kabutan_forecast_output(
    base_output: str, kabutan_forecast_pair: KabutanForecastPair | None, kabutan_source: str, kabutan_source_message: str | None
) -> str:
    rows: list[KabutanForecastRow] = []
    if kabutan_forecast_pair is not None:
        rows = [
            row
            for row in (
                kabutan_forecast_pair.previous_actual,
                kabutan_forecast_pair.current_forecast,
                kabutan_forecast_pair.next_forecast,
            )
            if row is not None
        ]
    header = "　　　　　　売上高　　営業利益　　経常利益　　最終利益"
    row_lines = (
        [_build_kabutan_row_line(row) for row in rows]
        if rows
        else [
            _build_kabutan_na_row_line("実績(N/A)"),
            _build_kabutan_na_row_line("今期予想(N/A)"),
            _build_kabutan_na_row_line("来期予想(N/A)"),
        ]
    )
    section = "\n".join(["", "■株探 業績推移（通期）", _build_kabutan_source_label(kabutan_source, kabutan_source_message), header, *row_lines])
    return f"{base_output}\n{section}"
