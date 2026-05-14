#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fundamental_jquants_v7_period_index_yfinance.py

J-Quants API V2で財務データを取得し、株価・時価総額はyFinanceで取得する日本株ファンダメンタル評価GUI。
J-Quantsのfins/summaryレスポンスは、calc_metricsへ渡す前に年度×期間種別へ正規化する。
既存の Stock_Entry_Prompt_dropdown_gui_Stage5_prev_evaluation.py に近い操作感：
- 監視銘柄ファイルを開く
- ドロップダウンで銘柄を選ぶ
- APIキーを入力または環境変数 JQUANTS_API_KEY から読む
- 1銘柄ずつ取得
- 株価・時価総額はyFinanceから取得
- 評価テキストを生成、コピー、保存

依存:
    pip install requests pandas yfinance

注意:
- J-Quants Free プランは 5回/分。1銘柄取得では master + summary を主に呼びます。
  株価はJ-Quants日足を使わず、yFinanceから取得します。
- /v2/fins/summary の項目名は V2短縮キーと旧/長いキーの両方を拾うようにしています。
- Freeプランの財務取得期間制限に合わせ、成長性は売上YoYを主指標にします。
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any, Callable

from app.services import calc_metrics as service_calc_metrics, calc_yoy as service_calc_yoy, grade_summary as service_grade_summary, progress_rank as service_progress_rank, rank_forecast_yoy as service_rank_forecast_yoy, rank_next_yoy as service_rank_next_yoy, rank_symbol as service_rank_symbol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    raise SystemExit("tkinter が必要です。GUI対応の Python を使ってください。") from exc

try:
    import yfinance as yf
except ImportError:
    yf = None

BASE_URL = "https://api.jquants.com/v2"
REQUEST_SLEEP_SEC = float(os.environ.get("JQUANTS_REQUEST_SLEEP_SEC", "13.0"))  # Free: 5 requests/min 対策。キャッシュヒット時は待機なし。
HTTP_TIMEOUT_SEC = 30
CACHE_DIR_NAME = ".jquants_cache"
CACHE_TTL_MASTER_SEC = 30 * 24 * 60 * 60
CACHE_TTL_SUMMARY_SEC = 24 * 60 * 60
CACHE_TTL_DAILY_SEC = 60 * 60  # 互換用。v6では株価取得に使わない。
CACHE_TTL_YF_SEC = 12 * 60 * 60

# 共通基準
THRESHOLDS = {
    "op_margin": 10.0,
    "sales_yoy": 10.0,
    "op_yoy": 10.0,
    "equity_ratio": 50.0,
    "roe": 10.0,
    "ocf_np_ratio": 1.0,
    "peg": 1.0,
}


class FileCache:
    """単純なJSONファイルキャッシュ。API回数削減を最優先にする。"""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(__file__).resolve().parent / CACHE_DIR_NAME)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
        return self.base_dir / f"{safe_key}.json"

    def get(self, key: str, ttl_sec: int | float) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            saved_at = float(payload.get("saved_at", 0))
            if time.time() - saved_at > ttl_sec:
                return None
            return payload.get("data")
        except Exception:
            return None

    def set(self, key: str, data: Any) -> None:
        path = self._path(key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = {"saved_at": time.time(), "data": data}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def get_or_fetch(self, key: str, ttl_sec: int | float, fetcher: Callable[[], Any]) -> Any:
        cached = self.get(key, ttl_sec)
        if cached is not None:
            return cached
        data = fetcher()
        self.set(key, data)
        return data


def fmt_market_cap(v: float | None) -> str:
    if v is None:
        return "N/A"
    oku = v / 100_000_000
    if oku >= 10_000:
        return f"{oku / 10_000:,.2f}兆円"
    return f"{oku:,.0f}億円"


def market_cap_band(v: float | None) -> str:
    if v is None:
        return "N/A"
    oku = v / 100_000_000
    if oku >= 100_000:
        return "超大型"
    if oku >= 10_000:
        return "主役大型"
    if oku >= 3_000:
        return "中型主役"
    if oku >= 1_000:
        return "小〜中型"
    return "小型"




def build_fy_compare_line(
    label: str,
    current_value: float | None,
    previous_value: float | None,
    current_year: str | None,
    previous_year: str | None,
    *,
    value_kind: str = "money",
    is_percent: bool = False,
    include_yoy: bool = True,
    unit_suffix: str = "",
) -> str:
    resolved_kind = "percent" if is_percent else value_kind
    if resolved_kind == "percent":
        current_text = fmt_plain_pct(current_value)
        previous_text = fmt_plain_pct(previous_value)
    elif resolved_kind == "number":
        current_text = f"{fmt_num(current_value)}{unit_suffix}"
        previous_text = f"{fmt_num(previous_value)}{unit_suffix}"
    else:
        current_text = f"{fmt_money(current_value)}{unit_suffix}"
        previous_text = f"{fmt_money(previous_value)}{unit_suffix}"
    yoy_text = f" YoY {fmt_pct(calc_yoy(current_value, previous_value))}" if include_yoy else ""
    y_current = current_year or "N/A"
    y_previous = previous_year or "N/A"
    return f"{label}：{current_text}（{y_current}年{yoy_text}） ← {previous_text}（{y_previous}年）"

def calc_yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    if previous < 0:
        return None
    return (current / previous - 1) * 100


def profit_yoy_label(current: float | None, previous: float | None, yoy: float | None) -> str:
    if current is None or previous is None:
        return "N/A"
    if previous < 0 <= current:
        return "黒字転換"
    if previous < 0 and current < 0:
        return "赤字縮小" if current > previous else "赤字拡大"
    if current < 0:
        return "営業赤字"
    return fmt_pct(yoy)

# 業種コメント補正用。J-Quants の33業種名（日本語/英語）を幅広く拾う。
SECTOR_HINTS = [
    {
        "keys": ["電気機器", "精密機器", "機械", "Electrical", "Precision", "Machinery"],
        "comment": "製造・半導体関連では、売上成長と営業利益率の両方を見る。共通基準の売上YoY10%・営業利益率10%は合格ラインだが、半導体色が強い銘柄では売上YoY15%以上、営業利益率15%以上ならより強い評価にする。",
    },
    {
        "keys": ["情報・通信", "サービス", "Information", "Communication", "Services"],
        "comment": "IT・サービス系では、売上成長率と営業利益率、ROEを重視する。無形資産中心のためROAよりROEを優先し、営業CFが純利益を裏付けているかを見る。",
    },
    {
        "keys": ["卸売", "商社", "Wholesale"],
        "comment": "商社・卸売系は営業利益率が低く出やすい。営業利益率だけで過小評価せず、ROE、営業CF、自己資本比率、配当余力を重視する。",
    },
    {
        "keys": ["銀行", "証券", "保険", "その他金融", "Bank", "Securities", "Insurance", "Financial"],
        "comment": "金融業は一般事業会社と財務構造が異なるため、営業利益率・自己資本比率・営業CFの解釈は弱くなる。ROE、利益成長、配当性向、業種内比較を重視する。",
    },
    {
        "keys": ["電気・ガス", "陸運", "海運", "空運", "倉庫", "通信", "Electric Power", "Gas", "Land Transportation", "Marine", "Air Transportation", "Warehouse"],
        "comment": "インフラ・ディフェンシブ系では、売上成長率が低くても安定性が評価される。営業CF、自己資本比率、配当余力を重視し、成長率だけで見送りにしない。",
    },
    {
        "keys": ["鉱業", "石油", "非鉄", "鉄鋼", "Mining", "Oil", "Coal", "Nonferrous", "Iron", "Steel"],
        "comment": "資源・素材系は市況循環で売上・利益が大きく振れる。単年成長率より、営業CF、財務耐久力、直近市況、サイクル上の位置を重視する。",
    },
]


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value in ("", "-", "None", "null", "NaN"):
            return None
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def first_present(d: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def fmt_num(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{v:,.{digits}f}"


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.2f}%"


def fmt_plain_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.2f}%"


def fmt_money(v: float | None) -> str:
    if v is None:
        return "N/A"
    # J-Quantsの財務数値は円ベース想定。億円表示にする。
    return f"{v / 100_000_000:,.1f}億円"


def normalize_code(code: str) -> str:
    code = str(code).strip()
    code = re.sub(r"\D", "", code)
    if len(code) == 4:
        return code + "0"
    return code


def display_code(code: str) -> str:
    code = str(code).strip()
    if len(code) == 5 and code.endswith("0"):
        return code[:4]
    return code


def parse_watchlist_text(text: str) -> list[tuple[str, str]]:
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
        if not code:
            continue
        if code in seen:
            continue
        seen.add(code)
        out.append((name, code))
    return out


def load_watchlist(path: Path) -> list[tuple[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp932"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"監視銘柄ファイルを読み込めませんでした: {last_error}")

    parsed = parse_watchlist_text(text)
    if not parsed:
        raise ValueError(
            "監視銘柄ファイルから銘柄を抽出できませんでした。対応形式例: '銘柄名 (1234)', '1234  銘柄名', '銘柄名,1234'"
        )
    return parsed


class JQuantsClient:
    def __init__(self, api_key: str, sleep_sec: float = REQUEST_SLEEP_SEC):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("J-Quants APIキーが空です。")
        self.sleep_sec = sleep_sec
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": self.api_key})
        retry = Retry(
            total=2,
            backoff_factor=2.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._last_request_at = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_request_at
        wait = self.sleep_sec - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self._throttle()
        url = BASE_URL + path
        try:
            resp = self.session.get(url, params=params, timeout=HTTP_TIMEOUT_SEC)
        except requests.RequestException as exc:
            self._last_request_at = time.time()
            raise RuntimeError(f"J-Quants APIへの接続に失敗しました: {exc}") from exc
        self._last_request_at = time.time()
        if resp.status_code == 429:
            raise RuntimeError(
                "J-Quants APIのレート制限に達しました。Freeプランは1分あたり5回までです。1分以上待ってから再試行してください。"
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"J-Quants API error {resp.status_code}: {resp.text[:500]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError("J-Quants APIのレスポンスJSONを解析できませんでした。") from exc

    def get_all(self, path: str, params: dict[str, Any], data_key_candidates: list[str]) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        next_key = None
        while True:
            p = dict(params)
            if next_key:
                p["pagination_key"] = next_key
            js = self.get(path, p)
            data = None
            for key in data_key_candidates:
                if key in js:
                    data = js[key]
                    break
            if data is None:
                data = js.get("data", [])
            if isinstance(data, list):
                all_rows.extend(data)
            next_key = js.get("pagination_key") or js.get("paginationKey")
            if not next_key:
                break
        return all_rows

    def get_master(self, code: str) -> dict[str, Any] | None:
        rows = self.get_all(
        "/equities/master",
        {"code": normalize_code(code)},
        ["data", "info", "issues"]
        )
        return rows[0] if rows else None

    def get_summary(self, code: str) -> list[dict[str, Any]]:
        return self.get_all("/fins/summary", {"code": normalize_code(code)}, ["data", "statements", "summary"])

    def get_daily_latest_close(self, code: str) -> float | None:
        # J-Quantsの株価はFreeでは遅延がある。PEG用のPER近似のために最新クローズだけ拾う。
        rows = self.get_all("/equities/bars/daily", {"code": normalize_code(code)}, ["data", "daily_quotes", "prices"])
        if not rows:
            return None
        rows = sorted(rows, key=lambda r: str(first_present(r, ["Date", "date", "d"]) or ""))
        latest = rows[-1]
        return safe_float(first_present(latest, ["Close", "close", "C", "AdjustmentClose", "AdjClose"]))


def fetch_yfinance_snapshot(code4: str) -> dict[str, float | None]:
    """株価と時価総額をyFinanceから取得。失敗時はNoneを返すだけにする。"""
    result = {"price": None, "market_cap": None}
    if yf is None:
        return result
    try:
        t = yf.Ticker(f"{code4}.T")
        hist = t.history(period="5d", auto_adjust=False)
        if hist is not None and not hist.empty:
            result["price"] = safe_float(hist["Close"].dropna().iloc[-1])
        try:
            info = getattr(t, "fast_info", None)
            if info is not None:
                result["market_cap"] = safe_float(getattr(info, "market_cap", None) or info.get("market_cap"))
        except Exception:
            pass
        if result["market_cap"] is None:
            try:
                result["market_cap"] = safe_float(t.info.get("marketCap"))
            except Exception:
                pass
    except Exception:
        return result
    return result


def maybe_yfinance_price(code4: str) -> float | None:
    return fetch_yfinance_snapshot(code4).get("price")


# =========================
# J-Quants summary period normalization
# =========================
PERIOD_ORDER = {"1Q": 1, "2Q": 2, "3Q": 3, "FY": 4}


@dataclass(frozen=True)
class PeriodRecord:
    """J-Quants fins/summary 1行を、会計年度と期間種別で扱いやすくしたもの。"""

    code: str
    fiscal_year: int
    period_type: str
    cur_per_st: str
    cur_per_en: str
    disclosed_at: str
    row: dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.fiscal_year}年度 {self.period_type}"


@dataclass(frozen=True)
class FinancialPeriods:
    """銘柄ごとのsummaryレスポンスを年度×期間種別に整理した中間データ。"""

    code: str
    periods_by_year: dict[int, dict[str, PeriodRecord]]
    latest_fy: PeriodRecord | None
    prev_fy: PeriodRecord | None
    latest_quarter: PeriodRecord | None
    latest_any: PeriodRecord | None


@dataclass(frozen=True)
class OutputViewModel:
    """GUI出力向けの表示DTO。ドメイン計算結果を表示責務に合わせて束ねる。"""

    company_name: str
    code4: str
    sector33: str
    market_cap_text: str
    market_cap_band_label: str
    latest_year: str | None
    prev_year: str | None


def build_output_view_model(
    company_name: str,
    code4: str,
    sector33: str,
    market_cap: float | None,
    periods: FinancialPeriods,
) -> OutputViewModel:
    return OutputViewModel(
        company_name=company_name,
        code4=code4,
        sector33=sector33 or "N/A",
        market_cap_text=fmt_market_cap(market_cap),
        market_cap_band_label=market_cap_band(market_cap),
        latest_year=str(getattr(periods.latest_fy, "fiscal_year", "")) if periods.latest_fy else None,
        prev_year=str(getattr(periods.prev_fy, "fiscal_year", "")) if periods.prev_fy else None,
    )

def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_year_from_date_text(value: Any) -> int | None:
    text = _as_text(value)
    if len(text) < 4:
        return None
    m = re.search(r"(\d{4})", text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _period_type_from_row(row: dict[str, Any]) -> str | None:
    raw = _as_text(first_present(row, [
        "CurPerType", "TypeOfCurrentPeriod", "CurrentPeriod", "PeriodType", "ToCP", "Tocp"
    ])).upper().replace(" ", "")
    raw_j = _as_text(first_present(row, ["TypeOfDocument", "DocType", "DocumentType"]))
    text = f"{raw} {raw_j}".upper()

    if raw in {"1Q", "Q1"} or "1Q" in text or "Q1" in text or "第1" in raw_j or "１Ｑ" in raw_j:
        return "1Q"
    if raw in {"2Q", "Q2", "HALF", "HY"} or "2Q" in text or "Q2" in text or "HALF" in text or "中間" in raw_j or "上半期" in raw_j or "第2" in raw_j:
        return "2Q"
    if raw in {"3Q", "Q3"} or "3Q" in text or "Q3" in text or "第3" in raw_j or "３Ｑ" in raw_j:
        return "3Q"
    if raw in {"FY", "FULL", "ANNUAL"} or "FY" in text or "FULL" in text or "ANNUAL" in text or "通期" in raw_j or "年度" in raw_j:
        return "FY"
    return None


def _cur_per_start(row: dict[str, Any]) -> str:
    return _as_text(first_present(row, [
        "CurPerSt", "CurrentPeriodStartDate", "CurrentFiscalYearStartDate", "FiscalYearStart", "PeriodStart"
    ]))


def _cur_per_end(row: dict[str, Any]) -> str:
    return _as_text(first_present(row, [
        "CurPerEn", "CurrentPeriodEndDate", "CurrentFiscalYearEndDate", "FiscalYearEnd", "FYEnd", "FYE", "PeriodEnd"
    ]))


def _disclosed_at(row: dict[str, Any]) -> str:
    d = _as_text(first_present(row, ["DisclosedDate", "DiscDate", "Date"]))
    t = _as_text(first_present(row, ["DisclosedTime", "DiscTime"]))
    no = _as_text(first_present(row, ["DisclosureNumber", "DiscNo"]))
    return " ".join(x for x in [d, t, no] if x)


def period_record_from_row(row: dict[str, Any]) -> PeriodRecord | None:
    """
    J-Quants fins/summaryの1行をPeriodRecordへ変換する。
    fiscal_yearはCurPerStの年を優先する。3月決算企業のFY 2024-04-01〜2025-03-31は2024年度として扱う。
    """
    period_type = _period_type_from_row(row)
    if period_type is None:
        return None

    cur_st = _cur_per_start(row)
    cur_en = _cur_per_end(row)
    fiscal_year = _parse_year_from_date_text(cur_st)
    if fiscal_year is None:
        # 互換フォールバック。CurPerStが無い古い/別名レスポンスでは期間終了日から推定する。
        fiscal_year = _parse_year_from_date_text(cur_en) or _parse_year_from_date_text(disclosure_key(row))
    if fiscal_year is None:
        return None

    return PeriodRecord(
        code=_as_text(first_present(row, ["Code", "code", "LocalCode", "LocalCodeStr"])),
        fiscal_year=fiscal_year,
        period_type=period_type,
        cur_per_st=cur_st,
        cur_per_en=cur_en,
        disclosed_at=_disclosed_at(row),
        row=row,
    )


def build_merged_period_row(preferred_row: dict[str, Any], supplement_row: dict[str, Any]) -> dict[str, Any]:
    """preferred_rowを優先し、空値のみsupplement_rowで補完する。"""
    merged = dict(supplement_row)
    for key, value in preferred_row.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def build_merged_period_record(preferred: PeriodRecord, supplement: PeriodRecord) -> PeriodRecord:
    """開示優先レコードを維持しつつ、空値は同年度同期間の別レコードで補完する。"""
    return PeriodRecord(
        code=preferred.code or supplement.code,
        fiscal_year=preferred.fiscal_year,
        period_type=preferred.period_type,
        cur_per_st=preferred.cur_per_st or supplement.cur_per_st,
        cur_per_en=preferred.cur_per_en or supplement.cur_per_en,
        disclosed_at=preferred.disclosed_at or supplement.disclosed_at,
        row=build_merged_period_row(preferred.row, supplement.row),
    )


def build_period_index(summary_rows: list[dict[str, Any]]) -> FinancialPeriods:
    """summaryレスポンスを年度×1Q/2Q/3Q/FYに整理する。同年度・同期間の重複は開示日時が新しい行を採用。"""
    periods_by_year: dict[int, dict[str, PeriodRecord]] = {}
    latest_any: PeriodRecord | None = None

    for row in summary_rows:
        rec = period_record_from_row(row)
        if rec is None:
            continue
        year_map = periods_by_year.setdefault(rec.fiscal_year, {})
        old = year_map.get(rec.period_type)
        if old is None:
            year_map[rec.period_type] = rec
        elif rec.disclosed_at >= old.disclosed_at:
            year_map[rec.period_type] = build_merged_period_record(rec, old)
        else:
            year_map[rec.period_type] = build_merged_period_record(old, rec)
        if latest_any is None or rec.disclosed_at >= latest_any.disclosed_at:
            latest_any = rec

    fy_years = sorted((y for y, per in periods_by_year.items() if "FY" in per), reverse=True)
    latest_fy = periods_by_year[fy_years[0]]["FY"] if fy_years else None
    prev_fy = None
    if latest_fy is not None:
        prev_fy = periods_by_year.get(latest_fy.fiscal_year - 1, {}).get("FY")
        if prev_fy is None and len(fy_years) >= 2:
            prev_fy = periods_by_year[fy_years[1]]["FY"]

    latest_quarter: PeriodRecord | None = None
    for year in sorted(periods_by_year.keys(), reverse=True):
        for ptype in ("3Q", "2Q", "1Q"):
            rec = periods_by_year[year].get(ptype)
            if rec is not None:
                latest_quarter = rec
                break
        if latest_quarter is not None:
            break

    code = latest_any.code if latest_any is not None else ""
    return FinancialPeriods(
        code=code,
        periods_by_year=periods_by_year,
        latest_fy=latest_fy,
        prev_fy=prev_fy,
        latest_quarter=latest_quarter,
        latest_any=latest_any,
    )


def row_from_record(record: PeriodRecord | None) -> dict[str, Any] | None:
    return None if record is None else record.row


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


def format_period_record(record: PeriodRecord | None) -> str:
    if record is None:
        return "N/A"
    period = f"{record.cur_per_st}〜{record.cur_per_en}" if record.cur_per_st or record.cur_per_en else "期間N/A"
    disclosed = f" / 開示 {record.disclosed_at}" if record.disclosed_at else ""
    return f"{record.label}（{period}{disclosed}）"


def is_full_year(row: dict[str, Any]) -> bool:
    # FY / Annual 系を広く拾う。
    vals = [
        first_present(row, ["TypeOfCurrentPeriod", "CurrentPeriod", "PeriodType", "ToCP", "Tocp"]),
        first_present(row, ["TypeOfDocument", "DocType", "DocumentType"]),
    ]
    text = " ".join(str(v) for v in vals if v is not None).upper()
    if any(x in text for x in ["FY", "ANNUAL", "FULL"]):
        return True
    # 日本語ラベル対策
    text_j = " ".join(str(v) for v in vals if v is not None)
    if "通期" in text_j or "年度" in text_j:
        return True
    return False


def fiscal_year_key(row: dict[str, Any]) -> str:
    return str(first_present(row, ["CurrentFiscalYearEndDate", "FiscalYearEnd", "FYEnd", "FYE", "PeriodEnd", "CurrentPeriodEndDate", "DisclosedDate", "DiscDate", "Date"]) or "")


def disclosure_key(row: dict[str, Any]) -> str:
    return str(first_present(row, ["DisclosedDate", "DiscDate", "Date", "DisclosedTime", "DiscTime", "DisclosureNumber", "DiscNo"]) or "")


def pick_fy_rows(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not summary_rows:
        return []
    fy_rows = [r for r in summary_rows if is_full_year(r)]
    if not fy_rows:
        # FreeプランなどでFY識別が難しい場合は全件から年度末キーで推定。
        fy_rows = summary_rows[:]
    # 同じ年度末で複数開示がある場合は後の開示を優先。
    best_by_year: dict[str, dict[str, Any]] = {}
    for r in fy_rows:
        fy = fiscal_year_key(r)
        if not fy:
            fy = disclosure_key(r)
        old = best_by_year.get(fy)
        if old is None or disclosure_key(r) >= disclosure_key(old):
            best_by_year[fy] = r
    return sorted(best_by_year.values(), key=fiscal_year_key, reverse=True)


def get_value(row: dict[str, Any] | None, short_keys: list[str], long_keys: list[str] | None = None) -> float | None:
    if not row:
        return None
    keys = list(short_keys)
    if long_keys:
        keys += long_keys
    return safe_float(first_present(row, keys))



def calc_progress_base(row: dict[str, Any] | None) -> tuple[str, float | None]:
    """決算短信の期間種別から進捗基準を返す。CurPerTypeを最優先する。"""
    if not row:
        return "N/A", None
    return progress_base_from_period_type(_period_type_from_row(row))


def calc_progress(actual: float | None, forecast: float | None) -> float | None:
    if actual is None or forecast in (None, 0):
        return None
    # 赤字予想や赤字実績は単純進捗率が誤解を招くためN/A扱いにする。
    if forecast <= 0 or actual < 0:
        return None
    return actual / forecast * 100


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


def rank_to_point(rank: str) -> int:
    return {"◎": 2, "○": 1, "△": 0, "×": 0, "N/A": 0}.get(rank, 0)


def rank_ok_ng(rank: str) -> str:
    if rank == "N/A":
        return "N/A"
    if rank in ("◎", "○"):
        return rank
    return rank


def eval_symbol(value: float | None, metric: str) -> str:
    """総合評価欄用の記号評価。"""
    return rank_symbol(value, metric)


def value_keys(*keys: str) -> list[str]:
    return list(keys)


def latest_summary_row(summary_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not summary_rows:
        return None
    return sorted(summary_rows, key=disclosure_key, reverse=True)[0]


def calc_metrics(periods: FinancialPeriods, price: float | None) -> dict[str, float | str | None]:
    """年度×期間種別へ正規化済みのFinancialPeriodsから、実績・予想・進捗指標を計算する。"""
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
    yoy_sales = service_calc_yoy(sales, prev_sales)
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

    # 会社予想は最新四半期を優先し、四半期が無ければ最新FY行を使う。
    forecast_source = latest_quarter or latest_fy
    forecast_sales = get_value(forecast_source, ["FSales"], ["ForecastSales"])
    forecast_op = get_value(forecast_source, ["FOP"], ["ForecastOperatingProfit"])
    forecast_eps = get_value(forecast_source, ["FEPS"], ["ForecastEarningsPerShare"])
    forecast_sales_2q = get_value(forecast_source, ["FSales2Q"], ["ForecastSales2Q", "ForecastSalesSecondQuarter"])
    forecast_op_2q = get_value(forecast_source, ["FOP2Q"], ["ForecastOperatingProfit2Q", "ForecastOperatingProfitSecondQuarter"])
    forecast_eps_2q = get_value(forecast_source, ["FEPS2Q"], ["ForecastEPS2Q", "ForecastEarningsPerShareSecondQuarter"])

    next_sales = get_value(forecast_source, ["NxFSales"], ["NextFiscalYearForecastSales"])
    next_op = get_value(forecast_source, ["NxFOP"], ["NextFiscalYearForecastOperatingProfit"])
    next_eps = get_value(forecast_source, ["NxFEPS"], ["NextFiscalYearForecastEarningsPerShare"])
    next_sales_2q = get_value(forecast_source, ["NxFSales2Q"], ["NextFiscalYearForecastSales2Q"])
    next_op_2q = get_value(forecast_source, ["NxFOP2Q"], ["NextFiscalYearForecastOperatingProfit2Q"])
    next_eps_2q = get_value(forecast_source, ["NxFEPS2Q"], ["NextFiscalYearForecastEPS2Q"])

    forecast_sales_yoy = service_calc_yoy(forecast_sales, sales)
    forecast_op_yoy = service_calc_yoy(forecast_op, op)
    forecast_eps_yoy = service_calc_yoy(forecast_eps, eps)
    next_sales_yoy = service_calc_yoy(next_sales, forecast_sales)
    next_op_yoy = service_calc_yoy(next_op, forecast_op)
    next_eps_yoy = service_calc_yoy(next_eps, forecast_eps)

    progress_label, progress_base = progress_base_from_period_type(latest_quarter_rec.period_type if latest_quarter_rec else None)
    actual_progress_sales = get_value(latest_quarter, ["Sales"], ["NetSales", "Revenue", "TotalRevenue"])
    actual_progress_op = get_value(latest_quarter, ["OP", "Op"], ["OperatingProfit", "OperatingIncome"])
    sales_progress = calc_progress(actual_progress_sales, forecast_sales)
    op_progress = calc_progress(actual_progress_op, forecast_op)

    return {
        "sales": sales,
        "prev_sales": prev_sales,
        "op": op,
        "prev_op": prev_op,
        "ordinary": ordinary,
        "np": np,
        "prev_np": prev_np,
        "eps": eps,
        "prev_eps": prev_eps,
        "bps": bps,
        "eq_ratio": eq_ratio,
        "div_ann": div_ann,
        "payout": payout,
        "ocf": ocf,
        "icf": icf,
        "fcf": fcf,
        "op_margin": op_margin,
        "yoy_sales": yoy_sales,
        "op_yoy": op_yoy,
        "roe": roe,
        "ocf_np_ratio": ocf_np_ratio,
        "per": per,
        "pbr": pbr,
        "div_yield": div_yield,
        "peg": peg,
        "forecast_sales": forecast_sales,
        "forecast_op": forecast_op,
        "forecast_eps": forecast_eps,
        "forecast_sales_2q": forecast_sales_2q,
        "forecast_op_2q": forecast_op_2q,
        "forecast_eps_2q": forecast_eps_2q,
        "forecast_sales_yoy": forecast_sales_yoy,
        "forecast_op_yoy": forecast_op_yoy,
        "forecast_eps_yoy": forecast_eps_yoy,
        "next_sales": next_sales,
        "next_op": next_op,
        "next_eps": next_eps,
        "next_sales_2q": next_sales_2q,
        "next_op_2q": next_op_2q,
        "next_eps_2q": next_eps_2q,
        "next_sales_yoy": next_sales_yoy,
        "next_op_yoy": next_op_yoy,
        "next_eps_yoy": next_eps_yoy,
        "sales_progress": sales_progress,
        "op_progress": op_progress,
        "progress_label": progress_label,
        "progress_base": progress_base,
        "latest_fy_label": format_period_record(latest_fy_rec),
        "prev_fy_label": format_period_record(prev_fy_rec),
        "latest_quarter_label": format_period_record(latest_quarter_rec),
        "forecast_source_label": format_period_record(latest_quarter_rec or latest_fy_rec),
    }


def eval_mark(value: float | None, threshold: float, higher_is_better: bool = True) -> str:
    if value is None:
        return "N/A"
    ok = value >= threshold if higher_is_better else value <= threshold
    return "OK" if ok else "NG"


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


def sector_comment(sector: str) -> str:
    if not sector:
        return "業種情報が取れないため、共通基準のみで評価する。"
    for item in SECTOR_HINTS:
        if any(k in sector for k in item["keys"]):
            return item["comment"]
    return "この業種では、共通基準をベースにしつつ、同業他社との相対比較を追加すると評価精度が上がる。"


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
    forecast_available = any(metrics.get(k) is not None for k in [
        "forecast_sales_yoy", "forecast_op_yoy", "forecast_eps_yoy", "op_progress", "next_op_yoy"
    ])
    forecast_score = sum(bool(x) for x in forecast_checks) if forecast_available else 0
    total_score = actual_score + forecast_score
    total_max = 12 if forecast_available else 7
    judge_base = total_score if forecast_available else actual_score

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


def fmt_score(actual_score: int, forecast_score: int, total_score: int, total_max: int) -> str:
    if total_max == 7:
        return f"実績 {actual_score}/7 / 予想進捗 N/A / 総合 {actual_score}/7"
    return f"実績 {actual_score}/7 / 予想進捗 {forecast_score}/5 / 総合 {total_score}/{total_max}"


def _money_or_na_from_row(row: dict[str, Any] | None, keys: list[str], long_keys: list[str] | None = None) -> str:
    return fmt_money(get_value(row, keys, long_keys))


def render_period_index_table(periods: FinancialPeriods) -> list[str]:
    """取得済み決算期間を、Markdown表ではなくプレーンテキストで表示する。"""
    lines = ["■取得済み決算期間の整理"]
    if not periods.periods_by_year:
        lines.append("  N/A")
        return lines

    for year in sorted(periods.periods_by_year.keys(), reverse=True):
        per = periods.periods_by_year[year]
        cells = []
        for ptype in ("1Q", "2Q", "3Q", "FY"):
            rec = per.get(ptype)
            if rec is None:
                cells.append(f"{ptype}: -")
            else:
                end = rec.cur_per_en or "期間N/A"
                disc = rec.disclosed_at.split()[0] if rec.disclosed_at else "開示N/A"
                cells.append(f"{ptype}: {end} / {disc}")
        lines.append(f"  {year}年度：" + " ｜ ".join(cells))
    return lines


def render_fy_compare_table(latest_fy: PeriodRecord | None, prev_fy: PeriodRecord | None) -> list[str]:
    """通期実績比較をプレーンテキストで表示する。"""
    lines = ["■通期実績比較"]
    records = [rec for rec in [latest_fy, prev_fy] if rec is not None]
    if not records:
        lines.append("  N/A")
        return lines

    for rec in records:
        row = rec.row
        period = f"{rec.cur_per_st}〜{rec.cur_per_en}" if rec.cur_per_st or rec.cur_per_en else "N/A"
        lines.extend([
            f"  {rec.fiscal_year}年度 {rec.period_type}（{period}）",
            f"    売上：{_money_or_na_from_row(row, ['Sales'], ['NetSales', 'Revenue', 'TotalRevenue'])}",
            f"    営業利益：{_money_or_na_from_row(row, ['OP', 'Op'], ['OperatingProfit', 'OperatingIncome'])}",
            f"    経常利益：{_money_or_na_from_row(row, ['OrdP', 'OdP', 'OrdinaryProfit'], ['OrdinaryIncome'])}",
            f"    純利益：{_money_or_na_from_row(row, ['NP'], ['Profit', 'NetIncome', 'ProfitAttributableToOwnersOfParent'])}",
            f"    EPS：{fmt_num(get_value(row, ['EPS'], ['EarningsPerShare']))}円",
        ])
    return lines


def render_quarter_table(periods: FinancialPeriods, metrics: dict[str, Any]) -> list[str]:
    """直近四半期・進捗をプレーンテキストで表示する。"""
    rec = periods.latest_quarter
    row = row_from_record(rec)
    lines = ["■直近四半期・進捗"]
    if rec is None or row is None:
        lines.append("  N/A")
        return lines

    lines.extend([
        f"  直近期：{rec.label}",
        f"  売上累計：{_money_or_na_from_row(row, ['Sales'], ['NetSales', 'Revenue', 'TotalRevenue'])}",
        f"  営業利益累計：{_money_or_na_from_row(row, ['OP', 'Op'], ['OperatingProfit', 'OperatingIncome'])}",
        f"  売上進捗：{fmt_plain_pct(metrics.get('sales_progress'))}",
        f"  営業利益進捗：{fmt_plain_pct(metrics.get('op_progress'))}",
        f"  基準進捗：{metrics.get('progress_label')} {fmt_plain_pct(metrics.get('progress_base'))}",
    ])
    return lines


def build_output(name: str, code4: str, master: dict[str, Any] | None, summary_rows: list[dict[str, Any]], price: float | None, market_cap: float | None = None) -> str:
    company_name = name
    sector33 = ""
    sector17 = ""
    market_segment = ""

    if master:
        company_name = str(first_present(master, [
            "CompanyName", "Name", "LocalCodeName", "CompanyNameEnglish", "CompanyNameFull"
        ]) or name)
        sector17 = str(first_present(master, ["S17Nm", "Sector17CodeName", "Sector17Name", "s17n", "Sector17"]) or "")
        sector33 = str(first_present(master, ["S33Nm", "Sector33CodeName", "Sector33Name", "s33n", "Sector33"]) or "")
        market_segment = str(first_present(master, ["ScaleCategory", "MarketCodeName", "MarketSegment", "MarketSegmentName", "Section", "SectionName"]) or "")

    periods = build_period_index(summary_rows)
    if periods.latest_fy is None:
        period_lines = render_period_index_table(periods)
        return "\n".join([
            f"【銘柄】{name} ({code4})",
            "",
            "取得失敗：CurPerType=FY の通期決算データを抽出できませんでした。",
            "J-Quantsのsummaryレスポンス自体は取得できている可能性があるため、下の期間整理を確認してください。",
            "",
            *period_lines,
        ])

    metrics = service_calc_metrics(periods, price)
    actual_score, forecast_score, total_score, total_max, grade = service_grade_summary(metrics)

    sales_rank = service_rank_symbol(metrics.get("yoy_sales"), "growth")
    op_rank = service_rank_symbol(metrics.get("op_yoy"), "op_growth")
    profitability_rank = service_rank_symbol(metrics.get("op_margin"), "op_margin")
    roe_rank = service_rank_symbol(metrics.get("roe"), "roe")
    cf_rank = service_rank_symbol(metrics.get("ocf_np_ratio"), "cf")
    financial_rank = service_rank_symbol(metrics.get("eq_ratio"), "equity_ratio")
    valuation_rank = service_rank_symbol(metrics.get("peg"), "peg")

    forecast_rank = service_rank_forecast_yoy(metrics.get("forecast_op_yoy") if metrics.get("forecast_op_yoy") is not None else metrics.get("forecast_sales_yoy"))
    progress_rank_value = service_progress_rank(metrics.get("op_progress"), metrics.get("progress_base"))
    next_rank_value = service_rank_next_yoy(metrics.get("next_op_yoy") if metrics.get("next_op_yoy") is not None else metrics.get("next_sales_yoy"))

    lines: list[str] = []
    lines.extend([
        f"【銘柄】{company_name} ({code4})",
        "",
        "■総合評価",
        f"判定：{grade}",
        f"スコア：{fmt_score(actual_score, forecast_score, total_score, total_max)}",
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

    view_model = build_output_view_model(company_name, code4, sector33, market_cap, periods)

    lines.extend([
        "■株価･割安性",
        f"株価　　　　：{fmt_num(price, 0)}円（yFinance取得）",
        f"PER(PEG)　　：{fmt_num(metrics.get('per'))}倍（{fmt_num(metrics.get('peg'))}倍）",
        f"PBR　　　 　：{fmt_num(metrics.get('pbr'))}倍",
        f"EPS/BPS　 　：{fmt_num(metrics.get('eps'))}円 / {fmt_num(metrics.get('bps'))}円",
        f"配当利回り　：{fmt_plain_pct(metrics.get('div_yield'))}（配当性向 {fmt_plain_pct(metrics.get('payout'))}）",
        "",
        "■時価総額･業種",
        f"時価総額　　：{view_model.market_cap_text}　({view_model.market_cap_band_label})",
        f"業種　　　　：{view_model.sector33}",
        "",
        "■主要指標",
        "",
        build_fy_compare_line("売上高　　　", metrics.get("sales"), metrics.get("prev_sales"), view_model.latest_year, view_model.prev_year),
        build_fy_compare_line("営業利益　　", metrics.get("op"), metrics.get("prev_op"), view_model.latest_year, view_model.prev_year),
        build_fy_compare_line("営業利益率　", metrics.get("op_margin"), metrics.get("prev_op_margin"), view_model.latest_year, view_model.prev_year, value_kind="percent", include_yoy=False),
        build_fy_compare_line("経常利益　　", metrics.get("ordinary"), metrics.get("prev_ordinary"), view_model.latest_year, view_model.prev_year),
        build_fy_compare_line("純利益　　　", metrics.get("np"), metrics.get("prev_np"), view_model.latest_year, view_model.prev_year),
        build_fy_compare_line("EPS　　　 　", metrics.get("eps"), metrics.get("prev_eps"), view_model.latest_year, view_model.prev_year, value_kind="number"),
        "",
        f"ROE　　　　 ：{fmt_plain_pct(metrics.get('roe'))}",
        f"自己資本比率：{fmt_plain_pct(metrics.get('eq_ratio'))}",
        f"営業CF　　　：{fmt_money(metrics.get('ocf'))}",
        "",
        "■今期会社予想",
        f"売上予想：{fmt_money(metrics.get('forecast_sales'))}（YoY {fmt_pct(metrics.get('forecast_sales_yoy'))}） → {service_rank_forecast_yoy(metrics.get('forecast_sales_yoy'))}",
        f"営業利益予想：{fmt_money(metrics.get('forecast_op'))}（YoY {fmt_pct(metrics.get('forecast_op_yoy'))}） → {service_rank_forecast_yoy(metrics.get('forecast_op_yoy'))}",
        f"EPS予想：{fmt_num(metrics.get('forecast_eps'))}円（YoY {fmt_pct(metrics.get('forecast_eps_yoy'))}）",
        "",
        "■直近四半期･進捗",
        *render_quarter_table(periods, metrics)[1:],
        "",
        "■来季予想",
        f"売上予想：{fmt_money(metrics.get('next_sales'))}（今期比 {fmt_pct(metrics.get('next_sales_yoy'))}） → {service_rank_next_yoy(metrics.get('next_sales_yoy'))}",
        f"営業利益予想：{fmt_money(metrics.get('next_op'))}（今期比 {fmt_pct(metrics.get('next_op_yoy'))}） → {service_rank_next_yoy(metrics.get('next_op_yoy'))}",
        f"経常利益予想：{fmt_money(metrics.get('next_ordinary'))}（今期比 {fmt_pct(metrics.get('next_ordinary_yoy'))}）",
        f"当期純利益予想：{fmt_money(metrics.get('next_np'))}（今期比 {fmt_pct(metrics.get('next_np_yoy'))}）",
        f"EPS予想：{fmt_num(metrics.get('next_eps'))}円（今期比 {fmt_pct(metrics.get('next_eps_yoy'))}）",
        "",
        "■ キャッシュフロー",
        f"営業CF：{fmt_money(metrics.get('ocf'))}",
        f"投資CF：{fmt_money(metrics.get('icf'))}",
        f"簡易FCF：{fmt_money(metrics.get('fcf'))}",
        f"営業CF/純利益：{fmt_num(metrics.get('ocf_np_ratio'))}倍 → {eval_mark(metrics.get('ocf_np_ratio'), THRESHOLDS['ocf_np_ratio'])}",
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

    lines.extend(["", "■取得済み決算期間整理", *render_period_index_table(periods)[1:]])
    return "\n".join(lines)


class FundamentalAnalyzer:
    """取得・計算・レンダリングをGUIから分離する薄いアプリケーション層。"""

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
        """株価・時価総額はyFinance固定。J-Quants daily closeにはフォールバックしない。"""
        snapshot = self.cache.get_or_fetch(
            f"yf_{code4}",
            CACHE_TTL_YF_SEC,
            lambda: fetch_yfinance_snapshot(code4),
        )
        if not isinstance(snapshot, dict):
            return {"price": None, "market_cap": None}
        return {
            "price": safe_float(snapshot.get("price")),
            "market_cap": safe_float(snapshot.get("market_cap")),
        }

    def analyze_one(self, name: str, code4: str) -> str:
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

class FundamentalApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("J-Quants ファンダメンタル評価 v7（プレーンテキスト / 株価yFinance固定）")
        self.master.geometry("1040x820")

        self.watchlist_path: Path | None = None
        self.watchlist: list[tuple[str, str]] = []
        self.display_to_code: dict[str, tuple[str, str]] = {}
        self.output_cache: dict[str, str] = {}
        self.file_cache = FileCache()
        self.is_fetching = False

        self.api_key_var = tk.StringVar(value=os.environ.get("JQUANTS_API_KEY", ""))
        self.path_var = tk.StringVar(value="監視銘柄ファイル未選択")
        self.stock_var = tk.StringVar()
        self.status_var = tk.StringVar(value="監視銘柄ファイルを読み込んでください。")

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self.master, padding=10)
        root.pack(fill="both", expand=True)

        api_frame = ttk.Frame(root)
        api_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(api_frame, text="J-Quants APIキー").pack(side="left")
        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, show="*", width=56)
        self.api_entry.pack(side="left", padx=(8, 8))
        ttk.Label(api_frame, text="環境変数 JQUANTS_API_KEY も可").pack(side="left")

        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 8))
        self.open_button = ttk.Button(top, text="監視銘柄ファイルを開く", command=self.open_watchlist)
        self.open_button.pack(side="left")
        ttk.Label(top, textvariable=self.path_var).pack(side="left", padx=10, fill="x", expand=True)

        control = ttk.Frame(root)
        control.pack(fill="x", pady=(0, 8))
        ttk.Label(control, text="銘柄選択").pack(side="left")
        self.stock_combo = ttk.Combobox(control, textvariable=self.stock_var, state="readonly", width=42)
        self.stock_combo.pack(side="left", padx=(8, 12))
        self.stock_combo.bind("<<ComboboxSelected>>", self.on_stock_selected)
        ttk.Label(control, text="株価: yFinance固定").pack(side="left", padx=(0, 12))
        self.fetch_button = ttk.Button(control, text="取得", command=self.generate_text)
        self.fetch_button.pack(side="left", padx=(0, 6))
        self.copy_button = ttk.Button(control, text="コピー", command=self.copy_text)
        self.copy_button.pack(side="left", padx=(0, 6))
        self.save_button = ttk.Button(control, text="保存", command=self.save_text)
        self.save_button.pack(side="left")

        ttk.Label(root, textvariable=self.status_var).pack(fill="x", pady=(0, 6))

        text_frame = ttk.Frame(root)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, wrap="word", font=("Yu Gothic UI", 11))
        self.text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)

    def set_busy(self, busy: bool, status: str | None = None):
        self.is_fetching = busy
        state = "disabled" if busy else "normal"
        readonly_state = "disabled" if busy else "readonly"
        self.open_button.configure(state=state)
        self.fetch_button.configure(state=state)
        self.copy_button.configure(state=state)
        self.save_button.configure(state=state)
        self.api_entry.configure(state=state)
        self.stock_combo.configure(state=readonly_state)
        if status is not None:
            self.status_var.set(status)
        self.master.update_idletasks()

    def open_watchlist(self):
        path = filedialog.askopenfilename(
            title="監視銘柄ファイルを選択",
            filetypes=[("Markdown/Text", "*.md *.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            watchlist = load_watchlist(Path(path))
        except Exception as exc:
            messagebox.showerror("読込失敗", str(exc))
            return

        self.watchlist_path = Path(path)
        self.watchlist = watchlist
        self.output_cache.clear()
        self.path_var.set(str(self.watchlist_path))
        self._populate_stock_choices()

    def _populate_stock_choices(self) -> None:
        values: list[str] = []
        self.display_to_code.clear()
        for name, code in self.watchlist:
            label = f"{name} ({code})"
            values.append(label)
            self.display_to_code[label] = (name, code)

        self.stock_combo["values"] = values
        if not values:
            self.stock_var.set("")
            self.text.delete("1.0", tk.END)
            self.status_var.set("銘柄が見つかりませんでした。")
            return

        self.stock_var.set(values[0])
        self.status_var.set(f"{len(values)}銘柄を読み込みました。銘柄を選んで取得してください。")

    def on_stock_selected(self, _event=None):
        self.status_var.set("銘柄を選択しました。取得ボタンを押してください。")

    def selected_stock(self) -> tuple[str, str] | None:
        label = self.stock_var.get().strip()
        if not label:
            return None
        return self.display_to_code.get(label)

    def _require_selected_stock(self) -> tuple[str, str] | None:
        selected = self.selected_stock()
        if selected is not None:
            return selected
        self.status_var.set("先に監視銘柄ファイルと銘柄を選んでください。")
        return None

    def _require_api_key(self) -> str | None:
        api_key = self.api_key_var.get().strip()
        if api_key:
            return api_key
        messagebox.showerror("APIキー未入力", "J-Quants APIキーを入力してください。")
        return None

    def _render_output(self, output: str, status: str):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", output)
        self.set_busy(False, status)

    def _handle_fetch_error(self, message: str):
        self.set_busy(False, "取得に失敗しました。")
        messagebox.showerror("取得失敗", message)

    def _fetch_worker(self, name: str, code4: str, api_key: str):
        try:
            from app.services import FundamentalAnalysisService

            service = FundamentalAnalysisService(api_key=api_key, file_cache=self.file_cache)
            output = service.build_analysis_output(name, code4, build_output_fn=build_output)
            self.output_cache[code4] = output
            self.master.after(0, lambda: self._render_output(output, f"生成完了: {name} ({code4}) / 財務=J-Quants / 株価=yFinance"))
        except Exception as exc:
            self.master.after(0, lambda: self._handle_fetch_error(str(exc)))

    def generate_text(self):
        if self.is_fetching:
            return

        selected = self._require_selected_stock()
        if selected is None:
            return

        api_key = self._require_api_key()
        if api_key is None:
            return

        name, code4 = selected
        cached_output = self.output_cache.get(code4)
        if cached_output is not None:
            self._render_output(cached_output, f"キャッシュ表示: {name} ({code4})")
            return

        self.set_busy(True, f"取得中: {name} ({code4}) / 財務=J-Quants / 株価=yFinance")
        thread = threading.Thread(target=self._fetch_worker, args=(name, code4, api_key), daemon=True)
        thread.start()

    def copy_text(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.status_var.set("コピーするテキストがありません。")
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(content)
        self.status_var.set("クリップボードにコピーしました。")

    def save_text(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.status_var.set("保存するテキストがありません。")
            return
        selected = self.selected_stock()
        default_name = "stock_fundamental_prompt.txt"
        if selected is not None:
            _, code = selected
            default_name = f"stock_fundamental_prompt_{code}.txt"
        initial_dir = str(self.watchlist_path.parent) if self.watchlist_path else str(Path.cwd())
        path = filedialog.asksaveasfilename(
            title="保存先を選択",
            defaultextension=".txt",
            initialdir=initial_dir,
            initialfile=default_name,
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(content + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("保存失敗", f"ファイルを書き込めませんでした: {exc}")
            self.status_var.set("保存に失敗しました。")
            return
        self.status_var.set(f"保存完了: {path}")


def main():
    root = tk.Tk()
    FundamentalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
    
