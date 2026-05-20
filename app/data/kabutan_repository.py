"""Data layer repository for fetching and parsing Kabutan finance forecasts."""

from __future__ import annotations

import re
from html import unescape
from urllib.request import Request, urlopen

from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastRow


def _to_int(text: str) -> int | None:
    normalized = text.replace(",", "").replace("－", "").strip()
    return int(normalized) if normalized else None


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


def _parse_kabutan_forecast_rows(html: str) -> list[KabutanForecastRow]:
    block_match = re.search(r'<div[^>]*class="[^"]*fin_year_result_d[^"]*"[^>]*>(.*?)</div>', html, flags=re.DOTALL)
    if block_match is None:
        raise ValueError("通期・業績推移テーブルが見つかりません")

    block = block_match.group(1)
    rows: list[KabutanForecastRow] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", block, flags=re.DOTALL):
        cells = re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", row_html, flags=re.DOTALL)
        if len(cells) < 5:
            continue
        parsed_period = _parse_period(_clean_cell_text(cells[0]))
        if parsed_period is None:
            continue
        period_label, year, month = parsed_period
        heading = _clean_cell_text(cells[0])
        rows.append(
            KabutanForecastRow(
                period_label=period_label,
                year=year,
                month=month,
                section="予想" if "予" in heading else "実績",
                sales=_to_int(_clean_cell_text(cells[1])),
                operating_profit=_to_int(_clean_cell_text(cells[2])),
                ordinary_profit=_to_int(_clean_cell_text(cells[3])),
                final_profit=_to_int(_clean_cell_text(cells[4])),
            )
        )
    return rows


class KabutanForecastRepository:
    def __init__(self, timeout_sec: int = 10):
        self.timeout_sec = timeout_sec

    def fetch_kabutan_html(self, code: str) -> str:
        url = _build_kabutan_url(code)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=self.timeout_sec) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="ignore")

    def fetch_kabutan_forecast_pair(self, code: str, target_years: tuple[int, int] | None = None) -> KabutanForecastPair:
        html = self.fetch_kabutan_html(code)
        rows = _parse_kabutan_forecast_rows(html)

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


__all__ = ["KabutanForecastRepository", "_parse_kabutan_forecast_rows"]
