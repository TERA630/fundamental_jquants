"""GUI controller: UIイベントからユースケース呼び出しを仲介する。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.data.file_cache import FileCache
from app.data.watchlist_repository import fetch_watchlist_entries
from app.domain.usecases.fundamental_analysis import FundamentalAnalysisService
from app.presenters import build_fundamental_output


class FundamentalGuiController:
    """GUI層コントローラー: 表示以外のオーケストレーションを担当。"""

    def __init__(
        self,
        file_cache: FileCache | None = None,
        build_fundamental_service: Callable[[str, FileCache], FundamentalAnalysisService] | None = None,
    ):
        self.file_cache = file_cache or FileCache()
        self.build_fundamental_service = build_fundamental_service or (
            lambda api_key, cache: FundamentalAnalysisService(api_key=api_key, file_cache=cache)
        )

    def fetch_watchlist_entries(self, path: Path) -> list[tuple[str, str]]:
        return fetch_watchlist_entries(path)

    def fetch_api_key(self, raw_api_key: str) -> str | None:
        normalized_api_key = raw_api_key.strip()
        return normalized_api_key or None

    def fetch_analysis_output(
        self,
        *,
        api_key: str,
        name: str,
        code4: str,
        output_cache: dict[str, str],
        output_cache_key: str,
        kabutan_html_dir: Path | None = None,
    ) -> str:
        cached_output = output_cache.get(output_cache_key)
        if cached_output is not None:
            return cached_output

        service = self.build_fundamental_service(api_key, self.file_cache)
        output = service.build_analysis_output(
            name,
            code4,
            build_output_fn=build_fundamental_output,
            kabutan_html_dir=kabutan_html_dir,
        )
        output_cache[output_cache_key] = output
        return output


__all__ = ["FundamentalGuiController"]
