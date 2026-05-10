#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock_Fundamental_Summary_MD.py

J-Quants API V2 + yfinance を使い、監視銘柄を一括クロールして
ファンダメンタル要約Markdownを生成するスクリプト。

前提:
    pip install requests pandas yfinance

使い方:
    1) 環境変数 JQUANTS_API_KEY を設定して実行
       python Stock_Fundamental_Summary_MD.py

    2) GUIで監視銘柄ファイルを選択
       監視銘柄の形式例:
         フジクラ (5803)
         5803 フジクラ
         フジクラ,5803

出力:
    Fundamental_Summary_yyyy-mm-dd_hhmm.md

設計方針:
    - 位置判定はしない。ファンダメンタルの一括評価に特化。
    - 既存の stock_fundamental_jquants_gui_prototype_v4_1.py と同じ .jquants_cache を使う。
    - master: 90日, summary: 24時間, daily: 1時間, yfinance: 12時間キャッシュ。
    - スコアは現行7項目を踏襲。
    - 429 Too Many Requests は即時リトライしない。70秒待って1回だけ再試行する。
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
except Exception:
    tk = None
    filedialog = None
    messagebox = None
    simpledialog = None

BASE_URL = "https://api.jquants.com/v2"
HTTP_TIMEOUT_SEC = 30
REQUEST_SLEEP_SEC = float(os.environ.get("JQUANTS_REQUEST_SLEEP_SEC", "16.0"))
CACHE_DIR_NAME = ".jquants_cache"
CACHE_TTL_MASTER_SEC = 90 * 24 * 60 * 60
RATE_LIMIT_WAIT_SEC = float(os.environ.get("JQUANTS_RATE_LIMIT_WAIT_SEC", "70.0"))
CACHE_TTL_SUMMARY_SEC = 24 * 60 * 60
CACHE_TTL_DAILY_SEC = 60 * 60
CACHE_TTL_YF_SEC = 12 * 60 * 60
MAX_HISTORY_YEARS = 5

THRESHOLDS = {
    "op_margin": 10.0,
    "sales_yoy": 10.0,
    "op_yoy": 10.0,
    "equity_ratio": 50.0,
    "roe": 10.0,
    "ocf_np_ratio": 1.0,
    "peg": 1.0,
}

GRADE_ORDER = [
    "A. ファンダ優良候補",
    "B. 監視上位",
    "C. 監視継続",
    "D. ファンダ面では慎重",
    "E. データ不足",
]

SECTOR_HINTS = [
    {
        "keys": ["電気機器", "精密機器", "機械", "Electrical", "Precision", "Machinery"],
        "comment": "製造・半導体関連では、売上成長と営業利益率の両方を見る。半導体色が強い銘柄では売上YoY15%以上、営業利益率15%以上ならより強い。",
    },
    {
        "keys": ["情報・通信", "サービス", "Information", "Communication", "Services"],
        "comment": "IT・サービス系では、売上成長率、営業利益率、ROEを重視する。営業CFが純利益を裏付けているかも確認する。",
    },
    {
        "keys": ["卸売", "商社", "Wholesale"],
        "comment": "商社・卸売系は営業利益率が低く出やすい。営業利益率だけで過小評価せず、ROE、営業CF、自己資本比率、配当余力を見る。",
    },
    {
        "keys": ["銀行", "証券", "保険", "その他金融", "Bank", "Securities", "Insurance", "Financial"],
        "comment": "金融業は一般事業会社と財務構造が異なる。営業利益率・自己資本比率・営業CFの解釈は弱め、ROE、利益成長、配当性向を重視する。",
    },
    {
        "keys": ["電気・ガス", "陸運", "海運", "空運", "倉庫", "通信", "Electric Power", "Gas", "Transportation", "Warehouse"],
        "comment": "インフラ・ディフェンシブ系では、売上成長率が低くても安定性が評価される。営業CF、自己資本比率、配当余力を重視する。",
    },
    {
        "keys": ["鉱業", "石油", "非鉄", "鉄鋼", "Mining", "Oil", "Coal", "Nonferrous", "Iron", "Steel"],
        "comment": "資源・素材系は市況循環で売上・利益が大きく振れる。単年成長率より、営業CF、財務耐久力、サイクル上の位置を重視する。",
    },
]


class FileCache:
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
        tmp.write_text(json.dumps({"saved_at": time.time(), "data": data}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def get_or_fetch(self, key: str, ttl_sec: int | float, fetcher: Callable[[], Any]) -> Any:
        cached = self.get(key, ttl_sec)
        if cached is not None:
            return cached
        data = fetcher()
        self.set(key, data)
        return data


class JQuantsClient:
    def __init__(self, api_key: str, sleep_sec: float = REQUEST_SLEEP_SEC):
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("J-Quants APIキーが空です。環境変数 JQUANTS_API_KEY を設定するか、GUI入力してください。")
        self.sleep_sec = sleep_sec
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": api_key})
        retry = Retry(
            total=2,
            backoff_factor=2.0,
            # 429は即時retryしない。J-Quants Free制限では待機が必要なので、get()側で70秒待って1回だけ再試行する。
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        wait = self.sleep_sec - elapsed
        if wait > 0:
            time.sleep(wait)

    def _request_once(self, path: str, params: dict[str, Any]) -> requests.Response:
        self._throttle()
        url = BASE_URL + path
        try:
            resp = self.session.get(url, params=params, timeout=HTTP_TIMEOUT_SEC)
        except requests.RequestException as exc:
            self._last_request_at = time.time()
            raise RuntimeError(f"J-Quants APIへの接続に失敗しました: {exc}") from exc
        self._last_request_at = time.time()
        return resp

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._request_once(path, params)

        # Freeプランでは429が出たら即時retryせず、長めに待って1回だけ再試行する。
        if resp.status_code == 429:
            print(f"  [rate-limit] 429: {int(RATE_LIMIT_WAIT_SEC)}秒待機して1回だけ再試行します...")
            time.sleep(RATE_LIMIT_WAIT_SEC)
            resp = self._request_once(path, params)
            if resp.status_code == 429:
                raise RuntimeError("J-Quants APIのレート制限に再度達しました。ここまでのキャッシュは残ります。数分待って再実行してください。")

        if resp.status_code >= 400:
            raise RuntimeError(f"J-Quants API error {resp.status_code}: {resp.text[:500]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError("J-Quants APIのJSONを解析できませんでした。") from exc

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
        rows = self.get_all("/equities/master", {"code": normalize_code(code)}, ["data", "info", "issues"])
        return rows[0] if rows else None

    def get_summary(self, code: str) -> list[dict[str, Any]]:
        return self.get_all("/fins/summary", {"code": normalize_code(code)}, ["data", "statements", "summary"])

    def get_daily_latest_close(self, code: str) -> float | None:
        rows = self.get_all("/equities/bars/daily", {"code": normalize_code(code)}, ["data", "daily_quotes", "prices"])
        if not rows:
            return None
        rows = sorted(rows, key=lambda r: str(first_present(r, ["Date", "date", "d"]) or ""))
        latest = rows[-1]
        return safe_float(first_present(latest, ["Close", "close", "C", "AdjustmentClose", "AdjClose"]))


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


def first_present(d: dict[str, Any] | None, keys: list[str]) -> Any:
    if not d:
        return None
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def normalize_code(code: str) -> str:
    code = re.sub(r"\D", "", str(code).strip())
    if len(code) == 4:
        return code + "0"
    return code


def display_code(code: str) -> str:
    code = str(code).strip()
    if len(code) == 5 and code.endswith("0"):
        return code[:4]
    return code


def fmt_num(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{v:,.{digits}f}"


def fmt_price(v: float | None) -> str:
    if v is None:
        return "N/A"
    if abs(v) < 500:
        return f"{v:,.2f}円"
    return f"{int(round(v)):,}円"


def fmt_pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def fmt_money(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v / 100_000_000:,.1f}億円"


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
        return "超大型（10兆円以上）"
    if oku >= 10_000:
        return "大型主役（1兆〜10兆円）"
    if oku >= 3_000:
        return "中型主役（3000億〜1兆円）"
    if oku >= 1_000:
        return "小〜中型（1000億〜3000億円）"
    return "小型（1000億円未満）"


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
        if not line or line.startswith("#") or line.startswith("|"):
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
        out.append((name.strip(" -*"), code))
    return out


def load_watchlist(path: Path) -> list[tuple[str, str]]:
    last_error: Exception | None = None
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"監視銘柄ファイルを読み込めません: {last_error}")
    parsed = parse_watchlist_text(text)
    if not parsed:
        raise ValueError("監視銘柄ファイルから銘柄を抽出できませんでした。例: フジクラ (5803)")
    return parsed


def calc_yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0 or previous < 0:
        return None
    return (current / previous - 1.0) * 100


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


def is_full_year(row: dict[str, Any]) -> bool:
    vals = [
        first_present(row, ["TypeOfCurrentPeriod", "CurrentPeriod", "PeriodType", "ToCP", "Tocp"]),
        first_present(row, ["TypeOfDocument", "DocType", "DocumentType"]),
    ]
    text = " ".join(str(v) for v in vals if v is not None)
    text_upper = text.upper()
    if any(x in text_upper for x in ["FY", "ANNUAL", "FULL"]):
        return True
    return "通期" in text or "年度" in text


def fiscal_year_key(row: dict[str, Any] | None) -> str:
    return str(first_present(row, [
        "CurrentFiscalYearEndDate", "FiscalYearEnd", "FYEnd", "FYE", "PeriodEnd",
        "CurrentPeriodEndDate", "DisclosedDate", "DiscDate", "Date"
    ]) or "")


def disclosure_key(row: dict[str, Any] | None) -> str:
    return str(first_present(row, ["DisclosedDate", "DiscDate", "Date", "DisclosedTime", "DiscTime", "DisclosureNumber", "DiscNo"]) or "")


def pick_fy_rows(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not summary_rows:
        return []
    fy_rows = [r for r in summary_rows if is_full_year(r)] or summary_rows[:]
    best_by_year: dict[str, dict[str, Any]] = {}
    for r in fy_rows:
        fy = fiscal_year_key(r) or disclosure_key(r)
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


def extract_master_fields(name: str, master: dict[str, Any] | None) -> dict[str, str]:
    company_name = name
    sector33 = ""
    sector17 = ""
    market_segment = ""
    if master:
        company_name = str(first_present(master, ["CompanyName", "Name", "LocalCodeName", "CompanyNameEnglish", "CompanyNameFull"]) or name)
        sector17 = str(first_present(master, ["S17Nm", "Sector17CodeName", "Sector17Name", "s17n", "Sector17"]) or "")
        sector33 = str(first_present(master, ["S33Nm", "Sector33CodeName", "Sector33Name", "s33n", "Sector33"]) or "")
        market_segment = str(first_present(master, ["ScaleCategory", "MarketCodeName", "MarketSegment", "MarketSegmentName", "Section", "SectionName"]) or "")
    return {"company_name": company_name, "sector33": sector33, "sector17": sector17, "market_segment": market_segment}


def row_metrics(row: dict[str, Any] | None) -> dict[str, float | None]:
    return {
        "sales": get_value(row, ["Sales"], ["NetSales", "Revenue", "TotalRevenue"]),
        "op": get_value(row, ["OP", "Op"], ["OperatingProfit", "OperatingIncome"]),
        "ordinary": get_value(row, ["OrdP", "OdP", "OrdinaryProfit"], ["OrdinaryIncome"]),
        "np": get_value(row, ["NP"], ["Profit", "NetIncome", "ProfitAttributableToOwnersOfParent"]),
    }


def calc_metrics(latest: dict[str, Any], prev: dict[str, Any] | None, price: float | None) -> dict[str, float | None]:
    cur = row_metrics(latest)
    old = row_metrics(prev)
    sales = cur["sales"]
    prev_sales = old["sales"]
    op = cur["op"]
    prev_op = old["op"]
    np = cur["np"]
    prev_np = old["np"]

    eps = get_value(latest, ["EPS"], ["EarningsPerShare"])
    bps = get_value(latest, ["BPS"], ["BookValuePerShare"])
    eq_ratio = get_value(latest, ["EqAR"], ["EquityToAssetRatio", "CapitalAdequacyRatio"])
    if eq_ratio is not None and eq_ratio <= 1.0:
        eq_ratio *= 100
    div_ann = get_value(latest, ["DivAnn"], ["AnnualDividendPerShare", "DividendPerShareAnnual"])
    payout = get_value(latest, ["PayoutRatioAnn"], ["PayoutRatio"])
    if payout is not None and payout <= 1.0:
        payout *= 100

    ocf = get_value(latest, ["OCF", "CFO", "NCFO"], ["NetCashProvidedByUsedInOperatingActivities", "OperatingCashFlow"])
    icf = get_value(latest, ["GFI", "CFI", "ICF"], ["NetCashProvidedByUsedInInvestmentActivities", "InvestingCashFlow"])
    fcf = None if ocf is None or icf is None else ocf + icf

    op_margin = None if sales in (None, 0) or op is None else op / sales * 100
    yoy_sales = calc_yoy(sales, prev_sales)
    op_yoy = calc_yoy(op, prev_op) if op is not None and prev_op is not None and prev_op > 0 and op >= 0 else None
    roe = None if bps in (None, 0) or eps is None else eps / bps * 100
    ocf_np_ratio = None if ocf is None or np in (None, 0) else ocf / np
    per = None if price in (None, 0) or eps in (None, 0) else price / eps
    pbr = None if price in (None, 0) or bps in (None, 0) else price / bps
    div_yield = None if price in (None, 0) or div_ann is None else div_ann / price * 100
    eps_growth = None if np in (None, 0) or prev_np in (None, 0) else (np / prev_np - 1) * 100
    peg = None if per is None or yoy_sales in (None, 0) or yoy_sales <= 0 else per / yoy_sales

    return {
        "sales": sales,
        "prev_sales": prev_sales,
        "op": op,
        "prev_op": prev_op,
        "ordinary": cur["ordinary"],
        "np": np,
        "eps": eps,
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
        "eps_growth": eps_growth,
        "peg": peg,
    }


def grade_summary(metrics: dict[str, float | None]) -> tuple[int, str]:
    checks = [
        metrics.get("yoy_sales") is not None and metrics["yoy_sales"] >= THRESHOLDS["sales_yoy"],
        metrics.get("op_yoy") is not None and metrics["op_yoy"] >= THRESHOLDS["op_yoy"],
        metrics.get("op_margin") is not None and metrics["op_margin"] >= THRESHOLDS["op_margin"],
        metrics.get("eq_ratio") is not None and metrics["eq_ratio"] >= THRESHOLDS["equity_ratio"],
        metrics.get("roe") is not None and metrics["roe"] >= THRESHOLDS["roe"],
        metrics.get("ocf_np_ratio") is not None and metrics["ocf_np_ratio"] >= THRESHOLDS["ocf_np_ratio"],
        metrics.get("peg") is not None and metrics["peg"] <= THRESHOLDS["peg"],
    ]
    score = sum(bool(x) for x in checks)
    if score >= 6:
        return score, "A. ファンダ優良候補"
    if score >= 5:
        return score, "B. 監視上位"
    if score >= 3:
        return score, "C. 監視継続"
    return score, "D. ファンダ面では慎重"


def rank_symbol(value: float | None, metric: str) -> str:
    if value is None:
        return "N/A"
    if metric == "growth":
        return "◎" if value >= 15 else "○" if value >= 10 else "△" if value >= 0 else "×"
    if metric == "op_margin":
        return "◎" if value >= 20 else "○" if value >= 10 else "△" if value >= 5 else "×"
    if metric == "equity_ratio":
        return "◎" if value >= 60 else "○" if value >= 50 else "△" if value >= 30 else "×"
    if metric == "roe":
        return "◎" if value >= 15 else "○" if value >= 10 else "△" if value >= 5 else "×"
    if metric == "cf":
        return "◎" if value >= 1.2 else "○" if value >= 1.0 else "△" if value >= 0 else "×"
    if metric == "peg":
        return "◎" if value <= 0.8 else "○" if value <= 1.0 else "△" if value <= 1.5 else "×"
    return "N/A"


def sector_comment(sector: str) -> str:
    if not sector:
        return "業種情報が取れないため、共通基準のみで評価する。"
    for item in SECTOR_HINTS:
        if any(k in sector for k in item["keys"]):
            return item["comment"]
    return "共通基準をベースにしつつ、同業他社との相対比較を追加すると評価精度が上がる。"


def short_comment(metrics: dict[str, float | None], grade: str) -> str:
    parts: list[str] = []
    ys = metrics.get("yoy_sales")
    oy = metrics.get("op_yoy")
    opm = metrics.get("op_margin")
    peg = metrics.get("peg")
    dy = metrics.get("div_yield")

    if ys is not None and ys >= 10 and oy is not None and oy >= 10:
        parts.append("増収増益")
    elif ys is not None and ys >= 10:
        parts.append("売上成長")
    elif oy is not None and oy >= 10:
        parts.append("利益成長")
    elif ys is not None and ys < 0:
        parts.append("減収注意")
    else:
        parts.append("成長は中立")

    if opm is not None and opm >= 15:
        parts.append("高収益")
    elif opm is not None and opm < 5:
        parts.append("低収益")

    if peg is not None:
        if peg <= 1.0:
            parts.append("PEG良好")
        elif peg >= 2.0:
            parts.append("PEG重め")
    if dy is not None and dy >= 3.0:
        parts.append("配当あり")

    return "・".join(parts)[:35]


def fetch_yfinance_snapshot(code4: str) -> dict[str, float | None]:
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


@dataclass
class StockResult:
    name: str
    code4: str
    company_name: str = ""
    sector33: str = ""
    sector17: str = ""
    market_segment: str = ""
    price: float | None = None
    market_cap: float | None = None
    fy_rows: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, float | None] = field(default_factory=dict)
    score: int = 0
    grade: str = "E. データ不足"
    error: str | None = None


def analyze_one(name: str, code: str, client: JQuantsClient, cache: FileCache) -> StockResult:
    code4 = display_code(code)
    result = StockResult(name=name, code4=code4)
    try:
        master = cache.get_or_fetch(f"master_{normalize_code(code4)}", CACHE_TTL_MASTER_SEC, lambda: client.get_master(code4))
        fields = extract_master_fields(name, master)
        result.company_name = fields["company_name"]
        result.sector33 = fields["sector33"]
        result.sector17 = fields["sector17"]
        result.market_segment = fields["market_segment"]

        summary_rows = cache.get_or_fetch(f"summary_{normalize_code(code4)}", CACHE_TTL_SUMMARY_SEC, lambda: client.get_summary(code4))
        result.fy_rows = pick_fy_rows(summary_rows)
        if not result.fy_rows:
            result.error = "通期決算データを抽出できませんでした。"
            return result

        yf_snap = cache.get_or_fetch(f"yf_{code4}", CACHE_TTL_YF_SEC, lambda: fetch_yfinance_snapshot(code4))
        result.price = safe_float((yf_snap or {}).get("price"))
        result.market_cap = safe_float((yf_snap or {}).get("market_cap"))
        if result.price is None:
            result.price = cache.get_or_fetch(f"daily_close_{normalize_code(code4)}", CACHE_TTL_DAILY_SEC, lambda: client.get_daily_latest_close(code4))

        prev = result.fy_rows[1] if len(result.fy_rows) >= 2 else None
        result.metrics = calc_metrics(result.fy_rows[0], prev, result.price)
        result.score, result.grade = grade_summary(result.metrics)
        return result
    except Exception as exc:
        result.error = str(exc)
        return result


def history_table(fy_rows: list[dict[str, Any]]) -> list[str]:
    rows = list(reversed(fy_rows[:MAX_HISTORY_YEARS]))
    lines = ["| 決算期 | 売上高 | 営業利益 | 営業利益率 |", "|---|---:|---:|---:|"]
    for r in rows:
        m = row_metrics(r)
        sales = m.get("sales")
        op = m.get("op")
        opm = None if sales in (None, 0) or op is None else op / sales * 100
        lines.append(f"| {fiscal_year_key(r) or disclosure_key(r) or 'N/A'} | {fmt_money(sales)} | {fmt_money(op)} | {fmt_pct(opm, signed=False)} |")
    return lines


def render_summary_table(results: list[StockResult]) -> list[str]:
    lines = [
        "| 銘柄（銘柄番号） | 現在株価 | 業種 | 時価総額 | スコア | 売上YoY | 営業利益YoY | 営業利益率 | ROE | PEG | 配当利回り | コメント |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        if r.error:
            lines.append(f"| {r.name} ({r.code4}) | N/A | {r.sector33 or r.sector17 or 'N/A'} | N/A | - | N/A | N/A | N/A | N/A | N/A | N/A | 取得失敗 |")
            continue
        m = r.metrics
        sector = r.sector33 or r.sector17 or "N/A"
        lines.append(
            f"| {r.company_name or r.name} ({r.code4}) | {fmt_price(r.price)} | {sector} | {fmt_market_cap(r.market_cap)} | "
            f"{r.score}/7 | {fmt_pct(m.get('yoy_sales'))} | {profit_yoy_label(m.get('op'), m.get('prev_op'), m.get('op_yoy'))} | "
            f"{fmt_pct(m.get('op_margin'), signed=False)} | {fmt_pct(m.get('roe'), signed=False)} | {fmt_num(m.get('peg'))} | "
            f"{fmt_pct(m.get('div_yield'), signed=False)} | {short_comment(m, r.grade)} |"
        )
    return lines


def render_detail(r: StockResult) -> list[str]:
    m = r.metrics
    lines: list[str] = []
    lines.append(f"## {r.company_name or r.name}（{r.code4}）")
    lines.append("")
    if r.error:
        lines.append(f"取得失敗：{r.error}")
        lines.append("")
        return lines
    latest = r.fy_rows[0] if r.fy_rows else None
    prev = r.fy_rows[1] if len(r.fy_rows) >= 2 else None
    lines.extend([
        f"- 業種：33業種={r.sector33 or 'N/A'} / 17業種={r.sector17 or 'N/A'}",
        f"- 時価総額：{fmt_market_cap(r.market_cap)} / {market_cap_band(r.market_cap)}",
        f"- 現在株価：{fmt_price(r.price)}",
        f"- 基準決算：{fiscal_year_key(latest) or disclosure_key(latest) or 'N/A'}",
        f"- 売上高：{fmt_money(m.get('sales'))}（YoY {fmt_pct(m.get('yoy_sales'))}）",
        f"- 営業利益：{fmt_money(m.get('op'))}（利益率 {fmt_pct(m.get('op_margin'), signed=False)}）",
        "- 売上・営業利益推移：",
    ])
    lines.extend("  " + x for x in history_table(r.fy_rows))
    lines.extend([
        f"- EPS / BPS：{fmt_num(m.get('eps'))}円 / {fmt_num(m.get('bps'))}円",
        f"- PER / PBR：{fmt_num(m.get('per'))}倍 / {fmt_num(m.get('pbr'))}倍",
        f"- ROE：{fmt_pct(m.get('roe'), signed=False)}",
        f"- 自己資本比率：{fmt_pct(m.get('eq_ratio'), signed=False)}",
        f"- 営業CF／投資CF：{fmt_money(m.get('ocf'))} / {fmt_money(m.get('icf'))}",
        f"- FCF：{fmt_money(m.get('fcf'))}",
        f"- 配当利回り：{fmt_pct(m.get('div_yield'), signed=False)}（配当性向 {fmt_pct(m.get('payout'), signed=False)}）",
        f"- PEG：{fmt_num(m.get('peg'))}倍",
        f"- スコア：{r.score}/7",
        f"- 判定：{r.grade}",
        "",
        "### 評価コメント",
    ])

    ys = m.get("yoy_sales")
    oy_text = profit_yoy_label(m.get("op"), m.get("prev_op"), m.get("op_yoy"))
    opm = m.get("op_margin")
    ocf_ratio = m.get("ocf_np_ratio")
    peg = m.get("peg")

    if ys is None:
        lines.append("- 売上YoYは算出不能。Freeプランの期間制限または前期データ欠損の可能性あり。")
    elif ys >= 10:
        lines.append(f"- 売上YoYは{fmt_pct(ys)}で、成長性は合格圏。")
    elif ys >= 0:
        lines.append(f"- 売上YoYは{fmt_pct(ys)}で、成長はあるが強い成長株としては物足りない。")
    else:
        lines.append(f"- 売上YoYは{fmt_pct(ys)}で、売上縮小に注意。")

    if m.get("op_yoy") is not None and m["op_yoy"] >= 10:
        lines.append(f"- 営業利益YoYは{fmt_pct(m.get('op_yoy'))}で、利益成長は合格圏。")
    else:
        lines.append(f"- 営業利益YoYは{oy_text}。利益成長の質を確認する。")

    if opm is not None:
        lines.append(f"- 営業利益率は{fmt_pct(opm, signed=False)}。{'収益性は良好。' if opm >= 10 else '収益性は共通基準では弱め。'}")
    if ocf_ratio is not None:
        lines.append(f"- 営業CF/純利益は{fmt_num(ocf_ratio)}倍。{'利益の現金化は良好。' if ocf_ratio >= 1 else '利益の現金化はやや弱い。'}")
    if peg is not None:
        lines.append(f"- PEGは{fmt_num(peg)}倍。{'成長率対比では許容圏。' if peg <= 1 else '成長率対比ではやや重い。'}")

    lines.append(f"- 業種補正：{sector_comment(r.sector33 or r.sector17)}")
    lines.append("")
    return lines


def sort_results(results: list[StockResult]) -> list[StockResult]:
    grade_idx = {g: i for i, g in enumerate(GRADE_ORDER)}

    def key(r: StockResult):
        m = r.metrics or {}
        return (
            grade_idx.get(r.grade, 99),
            -r.score,
            m.get("peg") if m.get("peg") is not None else 9999,
            -(m.get("yoy_sales") if m.get("yoy_sales") is not None else -9999),
            -(r.market_cap if r.market_cap is not None else -1),
            r.code4,
        )

    return sorted(results, key=key)


def build_markdown(results: list[StockResult], source_path: Path) -> str:
    now = datetime.now()
    sorted_all = sort_results(results)
    lines: list[str] = []
    lines.extend([
        f"# Fundamental Summary {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"- 元ファイル: {source_path.name}",
        f"- 取得時刻: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 対象銘柄数: {len(results)}",
        "- スコア基準: 売上YoY / 営業利益YoY / 営業利益率 / 自己資本比率 / ROE / 営業CF純利益比 / PEG の7点満点",
        "- キャッシュ: master 30日 / summary 24時間 / daily 1時間 / yfinance 12時間",
        "",
        "# 総合ランキング",
        "",
    ])
    lines.extend(render_summary_table(sorted_all))
    lines.append("")

    for grade in GRADE_ORDER:
        group = [r for r in sorted_all if r.grade == grade]
        lines.extend([f"# {grade}", ""])
        if group:
            lines.extend(render_summary_table(group))
        else:
            lines.append("該当なし")
        lines.append("")

    lines.extend(["# 個別詳細：A/B銘柄のみ", ""])
    detail_targets = [r for r in sorted_all if r.grade.startswith("A.") or r.grade.startswith("B.")]
    if not detail_targets:
        lines.append("該当なし")
        lines.append("")
    for r in detail_targets:
        lines.extend(render_detail(r))

    errors = [r for r in results if r.error]
    if errors:
        lines.extend(["# 取得エラー", ""])
        for r in errors:
            lines.append(f"- {r.name} ({r.code4}): {r.error}")
        lines.append("")

    lines.extend([
        "# 注意",
        "",
        "- J-Quants Freeプランでは財務データの取得期間に制限があるため、成長性は原則として売上YoY・営業利益YoYで評価している。",
        "- PEGは PER ÷ 売上YoY で近似している。厳密なPEGではないため、割安性は参考扱い。",
        "- このスクリプトはファンダメンタル選別用。エントリー価格・押し目判断は別スクリプトで確認する。",
    ])
    return "\n".join(lines)


def choose_watchlist_gui() -> Path:
    if tk is None or filedialog is None:
        raise RuntimeError("tkinterが使えません。監視銘柄ファイルパスを引数で指定してください。")
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="監視銘柄ファイルを選択",
        filetypes=[("Markdown/Text", "*.md *.txt"), ("All files", "*.*")],
    )
    root.destroy()
    if not path:
        raise RuntimeError("監視銘柄ファイルが選択されませんでした。")
    return Path(path)


def ask_api_key_gui() -> str:
    key = os.environ.get("JQUANTS_API_KEY", "").strip()
    if key:
        return key
    if tk is None or simpledialog is None:
        return ""
    root = tk.Tk()
    root.withdraw()
    key = simpledialog.askstring("J-Quants APIキー", "J-Quants APIキーを入力してください", show="*") or ""
    root.destroy()
    return key.strip()


def run(watchlist_path: Path, api_key: str) -> Path:
    watchlist = load_watchlist(watchlist_path)
    cache = FileCache()
    client = JQuantsClient(api_key)
    print(f"J-Quants待機間隔: {REQUEST_SLEEP_SEC:.1f}秒 / 429待機: {RATE_LIMIT_WAIT_SEC:.1f}秒 / master TTL: {CACHE_TTL_MASTER_SEC // 86400}日")
    results: list[StockResult] = []

    print(f"対象銘柄数: {len(watchlist)}")
    for idx, (name, code) in enumerate(watchlist, start=1):
        print(f"[{idx}/{len(watchlist)}] {name} ({code}) 取得中...")
        result = analyze_one(name, code, client, cache)
        results.append(result)
        if result.error:
            print(f"  -> 失敗: {result.error}")
        else:
            print(f"  -> {result.grade} / {result.score}/7")

    md = build_markdown(results, watchlist_path)
    out_path = watchlist_path.parent / f"Fundamental_Summary_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\n出力完了: {out_path}")
    return out_path


def main() -> int:
    try:
        if len(sys.argv) >= 2:
            watchlist_path = Path(sys.argv[1]).expanduser().resolve()
        else:
            watchlist_path = choose_watchlist_gui()
        api_key = os.environ.get("JQUANTS_API_KEY", "").strip() or ask_api_key_gui()
        out = run(watchlist_path, api_key)
        if messagebox is not None:
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo("完了", f"Markdownを作成しました:\n{out}")
                root.destroy()
            except Exception:
                pass
        return 0
    except Exception as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        if messagebox is not None:
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("エラー", str(exc))
                root.destroy()
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
