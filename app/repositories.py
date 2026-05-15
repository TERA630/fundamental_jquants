"""Compatibility facade for data layer modules."""

from app.data.file_cache import FileCache
from app.data.jquants_client import JQuantsClient
from app.data.market_data_provider import fetch_yfinance_snapshot, get_yfinance_price
from app.data.utils import normalize_code

maybe_yfinance_price = get_yfinance_price

__all__ = [
    "fetch_jquants_api_key",
    "FileCache",
    "JQuantsClient",
    "fetch_yfinance_snapshot",
    "get_yfinance_price",
    "maybe_yfinance_price",
    "normalize_code",
]
