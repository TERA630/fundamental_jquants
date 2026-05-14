"""Data-layer J-Quants HTTP client."""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.data.utils import first_present, normalize_code, safe_float

BASE_URL = "https://api.jquants.com/v2"
REQUEST_SLEEP_SEC = float(os.environ.get("JQUANTS_REQUEST_SLEEP_SEC", "13.0"))
HTTP_TIMEOUT_SEC = 30


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
        rows = sorted(rows, key=lambda row: str(first_present(row, ["Date", "date", "d"]) or ""))
        latest = rows[-1]
        return safe_float(first_present(latest, ["Close", "close", "C", "AdjustmentClose", "AdjClose"]))


__all__ = ["JQuantsClient", "BASE_URL", "REQUEST_SLEEP_SEC", "HTTP_TIMEOUT_SEC"]
