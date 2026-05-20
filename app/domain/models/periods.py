"""Domain model: normalized financial periods extracted from summary rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.data.utils import first_present


PERIOD_TYPE_KEYS = ["CurPerType", "TypeOfCurrentPeriod", "CurrentPeriod", "PeriodType", "ToCP", "Tocp"]
PERIOD_START_KEYS = ["CurPerSt", "CurrentPeriodStartDate", "CurrentFiscalYearStartDate"]
PERIOD_END_KEYS = ["CurPerEn", "CurrentPeriodEndDate", "CurrentFiscalYearEndDate"]
DISCLOSED_DATE_KEYS = ["DisclosedDate", "Date"]
NEXT_FORECAST_KEYS = ["NxFSales", "NxFsales", "NxFOP", "NxFOdP", "NxFODP", "NxFNP", "NxFEPS"]
PERIOD_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("1Q", ("1Q", "Q1")),
    ("2Q", ("2Q", "Q2", "HALF")),
    ("3Q", ("3Q", "Q3")),
    ("FY", ("FY", "ANNUAL", "FULL")),
]


@dataclass(frozen=True)
class PeriodRecord:
    fiscal_year: int
    period_type: str
    row: dict[str, Any]
    cur_per_st: str = ""
    cur_per_en: str = ""
    disclosed_at: str = ""


@dataclass(frozen=True)
class PeriodSet:
    latest_fy: PeriodRecord | None
    prev_fy: PeriodRecord | None
    latest_quarter: PeriodRecord | None
    current_forecast: PeriodRecord | None
    next_forecast: PeriodRecord | None




def get_period_type(raw_period_type: str) -> str | None:
    text = raw_period_type.upper()
    for normalized, tokens in PERIOD_TYPE_RULES:
        if any(token in text for token in tokens):
            return normalized
    return None


def calc_non_empty_count(row: dict[str, Any], keys: list[str]) -> int:
    return sum(1 for key in keys if row.get(key) not in (None, ""))


def build_merged_period_row(preferred_row: dict[str, Any], supplement_row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(supplement_row)
    for key, value in preferred_row.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def build_merged_period_record(preferred: PeriodRecord, supplement: PeriodRecord) -> PeriodRecord:
    return PeriodRecord(
        fiscal_year=preferred.fiscal_year,
        period_type=preferred.period_type,
        row=build_merged_period_row(preferred.row, supplement.row),
        cur_per_st=preferred.cur_per_st or supplement.cur_per_st,
        cur_per_en=preferred.cur_per_en or supplement.cur_per_en,
        disclosed_at=preferred.disclosed_at or supplement.disclosed_at,
    )


def fetch_period_set(summary_rows: list[dict[str, Any]]) -> PeriodSet:
    periods_by_year: dict[int, dict[str, PeriodRecord]] = {}
    records_by_fy_end: dict[str, list[PeriodRecord]] = {}
    latest_any: PeriodRecord | None = None

    for row in summary_rows:
        raw_period_type = str(first_present(row, PERIOD_TYPE_KEYS) or "")
        period_type = get_period_type(raw_period_type)
        if period_type is None:
            continue

        cur_st = str(first_present(row, PERIOD_START_KEYS) or "")
        fiscal_year = int(cur_st[:4]) if len(cur_st) >= 4 and cur_st[:4].isdigit() else None
        if fiscal_year is None:
            continue

        rec = PeriodRecord(
            fiscal_year=fiscal_year,
            period_type=period_type,
            row=row,
            cur_per_st=cur_st,
            cur_per_en=str(first_present(row, PERIOD_END_KEYS) or ""),
            disclosed_at=str(first_present(row, DISCLOSED_DATE_KEYS) or ""),
        )

        if rec.cur_per_en:
            records_by_fy_end.setdefault(rec.cur_per_en, []).append(rec)
        if latest_any is None or rec.disclosed_at >= latest_any.disclosed_at:
            latest_any = rec

        year_map = periods_by_year.setdefault(rec.fiscal_year, {})
        old = year_map.get(rec.period_type)
        if old is None:
            year_map[rec.period_type] = rec
        elif rec.disclosed_at >= old.disclosed_at:
            year_map[rec.period_type] = build_merged_period_record(rec, old)
        else:
            year_map[rec.period_type] = build_merged_period_record(old, rec)

    fy_years = sorted((y for y, per in periods_by_year.items() if "FY" in per), reverse=True)
    latest_fy = periods_by_year[fy_years[0]]["FY"] if fy_years else None
    prev_fy = None
    if latest_fy is not None:
        prev_fy = periods_by_year.get(latest_fy.fiscal_year - 1, {}).get("FY")
        if prev_fy is None and len(fy_years) >= 2:
            prev_fy = periods_by_year[fy_years[1]]["FY"]

    latest_quarter = None
    for year in sorted(periods_by_year.keys(), reverse=True):
        for ptype in ("3Q", "2Q", "1Q"):
            rec = periods_by_year[year].get(ptype)
            if rec is not None:
                latest_quarter = rec
                break
        if latest_quarter is not None:
            break

    current_forecast = None
    next_forecast = None
    forecast_anchor_fy_end = ""
    if latest_quarter is not None and latest_quarter.cur_per_en:
        forecast_anchor_fy_end = latest_quarter.cur_per_en
    elif latest_any is not None and latest_any.cur_per_en and (latest_fy is None or latest_any.fiscal_year >= latest_fy.fiscal_year):
        forecast_anchor_fy_end = latest_any.cur_per_en
    elif latest_fy is not None and latest_fy.cur_per_en:
        forecast_anchor_fy_end = latest_fy.cur_per_en

    if forecast_anchor_fy_end and forecast_anchor_fy_end in records_by_fy_end:
        candidate_rows = sorted(records_by_fy_end[forecast_anchor_fy_end], key=lambda x: x.disclosed_at, reverse=True)
        current_forecast = candidate_rows[0]
        for rec in candidate_rows[1:]:
            current_forecast = build_merged_period_record(current_forecast, rec)

        next_forecast = max(
            candidate_rows,
            key=lambda rec: (calc_non_empty_count(rec.row, NEXT_FORECAST_KEYS), rec.disclosed_at),
        )

    return PeriodSet(
        latest_fy=latest_fy,
        prev_fy=prev_fy,
        latest_quarter=latest_quarter,
        current_forecast=current_forecast,
        next_forecast=next_forecast,
    )


__all__ = [
    "PeriodRecord",
    "PeriodSet",
    "fetch_period_set",
    "get_period_type",
    "build_merged_period_row",
    "build_merged_period_record",
    "calc_non_empty_count",
]
