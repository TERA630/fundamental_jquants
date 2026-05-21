"""Data layer repository for fetching and parsing Kabutan finance forecasts."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import TypedDict
from urllib.request import Request, urlopen

from app.data.file_cache import FileCache
from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastRow, KabutanForecastSnapshot


KABUTAN_HEADER_ALIASES = {
    "revised_eps": ("1株益",),
    "dividend": ("配当", "1株配"),
}


class KabutanCacheRow(TypedDict):
    fiscal_year: str
    forecast_type: str
    period_type: str
    sales: int | None
    op_income: int | None
    ordinary_income: int | None
    np: int | None
    eps: float | None
    div: float | None


def _to_int(text: str) -> int | None:
    normalized = text.replace(",", "").replace("－", "").strip()
    return int(normalized) if normalized else None


def _to_float(text: str) -> float | None:
    normalized = text.replace(",", "").replace("－", "").strip()
    return float(normalized) if normalized else None


def _parse_period(text: str) -> tuple[str, int, int] | None:
    match = re.search(r"(\d{4})\.(\d{2})", text)
    if not match:
        return None
    return match.group(0), int(match.group(1)), int(match.group(2))


def _build_kabutan_url(code: str) -> str:
    return f"https://kabutan.jp/stock/finance?code={code}"


def _clean_cell_text(text: str) -> str:
    text_no_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text_no_tags)).strip()


def _fetch_kabutan_table_html(html: str) -> str:
    table_match = re.search(
        r'<div[^>]*class="[^"]*fin_year_result_d[^"]*"[^>]*>[\s\S]*?<table[^>]*>([\s\S]*?)</table>',
        html,
        flags=re.DOTALL,
    )
    if table_match is None:
        raise ValueError("通期・業績推移テーブルが見つかりません")
    return table_match.group(1)


def _get_kabutan_header_index(header_cells: list[str], metric_key: str) -> int | None:
    aliases = KABUTAN_HEADER_ALIASES.get(metric_key, ())
    return next((idx for idx, col in enumerate(header_cells) if any(alias in col for alias in aliases)), None)


def fetch_kabutan_header_indices(header_cells: list[str]) -> dict[str, int | None]:
    return {
        "revised_eps": _get_kabutan_header_index(header_cells, "revised_eps"),
        "dividend": _get_kabutan_header_index(header_cells, "dividend"),
    }


def build_kabutan_forecast_row_from_cells(cleaned_cells: list[str], header_indices: dict[str, int | None]) -> KabutanForecastRow | None:
    parsed_period = _parse_period(cleaned_cells[0])
    if parsed_period is None:
        return None

    period_label, year, month = parsed_period
    heading = cleaned_cells[0]
    revised_eps_idx = header_indices.get("revised_eps")
    dividend_idx = header_indices.get("dividend")
    return KabutanForecastRow(
        period_label=period_label,
        year=year,
        month=month,
        section="予想" if "予" in heading else "実績",
        sales=_to_int(cleaned_cells[1]),
        operating_profit=_to_int(cleaned_cells[2]),
        ordinary_profit=_to_int(cleaned_cells[3]),
        final_profit=_to_int(cleaned_cells[4]),
        revised_eps=_to_float(cleaned_cells[revised_eps_idx]) if revised_eps_idx is not None and len(cleaned_cells) > revised_eps_idx else None,
        dividend=_to_float(cleaned_cells[dividend_idx]) if dividend_idx is not None and len(cleaned_cells) > dividend_idx else None,
    )


def build_kabutan_cache_row(row: KabutanForecastRow) -> KabutanCacheRow:
    return {
        "fiscal_year": f"{row.year}/{row.month:02d}",
        "forecast_type": row.section,
        "period_type": "通期",
        "sales": row.sales,
        "op_income": row.operating_profit,
        "ordinary_income": row.ordinary_profit,
        "np": row.final_profit,
        "eps": row.revised_eps,
        "div": row.dividend,
    }


def build_kabutan_forecast_row_from_cache(cache_row: KabutanCacheRow) -> KabutanForecastRow:
    fiscal_year = str(cache_row["fiscal_year"])
    year_text, month_text = fiscal_year.split("/")
    return KabutanForecastRow(
        period_label=fiscal_year.replace("/", "."),
        year=int(year_text),
        month=int(month_text),
        section=str(cache_row.get("forecast_type", "実績")),
        sales=cache_row.get("sales"),
        operating_profit=cache_row.get("op_income"),
        ordinary_profit=cache_row.get("ordinary_income"),
        final_profit=cache_row.get("np"),
        revised_eps=cache_row.get("eps"),
        dividend=cache_row.get("div"),
    )


def fetch_kabutan_forecast_rows_from_cache_payload(cached_payload: dict[str, object]) -> list[KabutanForecastRow]:
    rows = cached_payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return []

    parsed_rows: list[KabutanForecastRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            parsed_rows.append(build_kabutan_forecast_row_from_cache(row))
        except (KeyError, ValueError, TypeError):
            continue
    return parsed_rows


def _parse_kabutan_forecast_rows(html: str) -> list[KabutanForecastRow]:
    block = _fetch_kabutan_table_html(html)
    rows: list[KabutanForecastRow] = []
    header_cells: list[str] = []
    header_indices = {"revised_eps": None, "dividend": None}
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", block, flags=re.DOTALL):
        cells = re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", row_html, flags=re.DOTALL)
        if len(cells) < 5:
            continue
        cleaned_cells = [_clean_cell_text(cell) for cell in cells]
        if "売上高" in "".join(cleaned_cells):
            header_cells = cleaned_cells
            header_indices = fetch_kabutan_header_indices(header_cells)
            continue
        row = build_kabutan_forecast_row_from_cells(cleaned_cells, header_indices)
        if row is not None:
            rows.append(row)
    return rows


def build_kabutan_forecast_snapshot(rows: list[KabutanForecastRow], base_year: int) -> KabutanForecastSnapshot:
    has_current_year_actual = any(row.section == "実績" and row.year == base_year for row in rows)
    if has_current_year_actual:
        actual_years = {base_year - 2, base_year - 1, base_year}
        forecast_years = {base_year + 1}
    else:
        actual_years = {base_year - 2, base_year - 1}
        forecast_years = {base_year, base_year + 1}

    actual_rows = tuple(row for row in rows if row.section == "実績" and row.year in actual_years)
    forecast_rows = tuple(row for row in rows if row.section == "予想" and row.year in forecast_years)
    return KabutanForecastSnapshot(actual_rows=actual_rows, forecast_rows=forecast_rows)


def _extract_kabutan_visible_body(html: str) -> str:
    block_match = re.search(
        r'(<div[^>]*class="[^"]*fin_year_result_d[^"]*"[^>]*>[\s\S]*?<table[^>]*>[\s\S]*?</table>[\s\S]*?</div>)',
        html,
        flags=re.DOTALL,
    )
    if block_match is None:
        return html
    return block_match.group(0)


def _build_forecast_pair_from_rows(rows: list[KabutanForecastRow], target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
    forecast_idx = next((idx for idx, row in enumerate(rows) if row.section == "予想"), None)
    if forecast_idx is None:
        raise ValueError("予想行が見つかりません")

    current_forecast = rows[forecast_idx]
    previous_actual = rows[forecast_idx - 1] if forecast_idx > 0 else None
    next_forecast = rows[forecast_idx + 1] if len(rows) > forecast_idx + 1 and rows[forecast_idx + 1].section == "予想" else None

    if target_years is not None:
        year_set = set(target_years)
        if current_forecast.year not in year_set:
            raise ValueError(f"今期予想の年度 {current_forecast.year} が対象年度 {sorted(year_set)} に含まれません")
        if next_forecast is not None and next_forecast.year not in year_set:
            next_forecast = None

    return KabutanForecastPair(previous_actual=previous_actual, current_forecast=current_forecast, next_forecast=next_forecast)


class KabutanForecastRepository:
    def __init__(self, timeout_sec: int = 10, file_cache: FileCache | None = None):
        self.timeout_sec = timeout_sec
        self.file_cache = file_cache or FileCache()

    @staticmethod
    def build_cache_key_kabutan_forecast(code: str) -> str:
        return f"kabutan_forecast_{code}"

    @staticmethod
    def build_cache_key_kabutan_html(path: Path) -> str:
        return f"kabutan_html_{path.resolve()}"

    def fetch_kabutan_html(self, code: str) -> str:
        url = _build_kabutan_url(code)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=self.timeout_sec) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="ignore")

    def fetch_kabutan_html_from_file(self, html_path: str | Path) -> str:
        path = Path(html_path)
        cache_key = self.build_cache_key_kabutan_html(path)
        cached_html = self.file_cache.get(cache_key, ttl_sec=365 * 24 * 60 * 60)
        if isinstance(cached_html, str) and cached_html:
            return cached_html
        html = path.read_text(encoding="utf-8")
        visible_html = _extract_kabutan_visible_body(html)
        self.file_cache.set(cache_key, visible_html)
        return visible_html

    def fetch_kabutan_forecast_pair_from_file(self, html_path: str | Path, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        html = self.fetch_kabutan_html_from_file(html_path)
        return self._fetch_forecast_pair_from_html(html, target_years=target_years)

    @staticmethod
    def get_kabutan_cache_payload(pair: KabutanForecastPair) -> dict[str, object]:
        rows = []
        for row in (pair.previous_actual, pair.current_forecast, pair.next_forecast):
            if row is None:
                continue
            rows.append(build_kabutan_cache_row(row))
        return {"rows": rows}

    def _fetch_forecast_pair_from_html(self, html: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        rows = _parse_kabutan_forecast_rows(html)
        return _build_forecast_pair_from_rows(rows, target_years=target_years)

    def fetch_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        cache_key = self.build_cache_key_kabutan_forecast(code)
        cached_payload = self.file_cache.get(cache_key, ttl_sec=12 * 60 * 60)
        if isinstance(cached_payload, dict):
            parsed_rows = fetch_kabutan_forecast_rows_from_cache_payload(cached_payload)
            if parsed_rows:
                try:
                    return _build_forecast_pair_from_rows(parsed_rows, target_years=target_years)
                except ValueError:
                    pass

        html = self.fetch_kabutan_html(code)
        pair = self._fetch_forecast_pair_from_html(html, target_years=target_years)
        self.file_cache.set(cache_key, self.get_kabutan_cache_payload(pair))
        return pair


__all__ = ["KabutanForecastRepository", "_parse_kabutan_forecast_rows", "_extract_kabutan_visible_body"]
