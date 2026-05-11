"""Data layer: API clients, cache, and external data sources."""

from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import yfinance as yf
except ImportError:
    yf = None

BASE_URL = "https://api.jquants.com/v2"
REQUEST_SLEEP_SEC = float(os.environ.get("JQUANTS_REQUEST_SLEEP_SEC", "13.0"))
HTTP_TIMEOUT_SEC = 30
CACHE_DIR_NAME = ".jquants_cache"


def _safe_float(value: Any) -> float | None:
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


def _first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def normalize_code(code: str) -> str:
    text = str(code).strip()
    text = re.sub(r"\D", "", text)
    if len(text) == 4:
        return text + "0"
    return text


class FileCache:
    """単純なJSONファイルキャッシュ。API回数削減を最優先にする。"""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(__file__).resolve().parent.parent / CACHE_DIR_NAME)
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


class JQuantsClient:
    def __init__(self, api_key: str, sleep_sec: float = REQUEST_SLEEP_SEC):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("J-Quants APIキーが空です。")
        self.sleep_sec = sleep_sec
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": self.api_key})
        retry = Retry(total=2, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",), respect_retry_after_header=True)
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
            raise RuntimeError("J-Quants APIのレート制限に達しました。")
        if resp.status_code >= 400:
            raise RuntimeError(f"J-Quants API error {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def get_all(self, path: str, params: dict[str, Any], data_key_candidates: list[str]) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        next_key = None
        while True:
            req_params = dict(params)
            if next_key:
                req_params["pagination_key"] = next_key
            js = self.get(path, req_params)
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
        rows = sorted(rows, key=lambda row: str(_first_present(row, ["Date", "date", "d"]) or ""))
        latest = rows[-1]
        return _safe_float(_first_present(latest, ["Close", "close", "C", "AdjustmentClose", "AdjClose"]))


def fetch_yfinance_snapshot(code4: str) -> dict[str, float | None]:
    result = {"price": None, "market_cap": None}
    if yf is None:
        return result
    try:
        ticker = yf.Ticker(f"{code4}.T")
        hist = ticker.history(period="5d", auto_adjust=False)
        if hist is not None and not hist.empty:
            result["price"] = _safe_float(hist["Close"].dropna().iloc[-1])
        try:
            info = getattr(ticker, "fast_info", None)
            if info is not None:
                result["market_cap"] = _safe_float(getattr(info, "market_cap", None) or info.get("market_cap"))
        except Exception:
            pass
    except Exception:
        return result
    return result


def maybe_yfinance_price(code4: str) -> float | None:
    return fetch_yfinance_snapshot(code4).get("price")


__all__ = [
    "FileCache",
    "JQuantsClient",
    "fetch_yfinance_snapshot",
    "maybe_yfinance_price",
    "normalize_code",
]
