"""Data-layer market data providers (yfinance)."""

from __future__ import annotations

from app.data.utils import safe_float

try:
    import yfinance as yf
except ImportError:
    yf = None


def fetch_yfinance_snapshot(code4: str) -> dict[str, float | None]:
    result = {"price": None, "market_cap": None}
    if yf is None:
        return result
    try:
        ticker = yf.Ticker(f"{code4}.T")
        hist = ticker.history(period="5d", auto_adjust=False)
        if hist is not None and not hist.empty:
            result["price"] = safe_float(hist["Close"].dropna().iloc[-1])
        try:
            info = getattr(ticker, "fast_info", None)
            if info is not None:
                result["market_cap"] = safe_float(getattr(info, "market_cap", None) or info.get("market_cap"))
        except Exception:
            pass
    except Exception:
        return result
    return result


def get_yfinance_price(code4: str) -> float | None:
    return fetch_yfinance_snapshot(code4).get("price")


__all__ = ["fetch_yfinance_snapshot", "get_yfinance_price"]
