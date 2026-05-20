"""GUI controller: UIイベントからユースケース呼び出しを仲介する。"""

from __future__ import annotations

from pathlib import Path

from app.presenters import build_fundamental_output, fetch_watchlist
from app.repositories import FileCache
from app.services import FundamentalAnalysisService


class FundamentalGuiController:
    """GUI層コントローラー: 表示以外のオーケストレーションを担当。"""

    def __init__(self, file_cache: FileCache | None = None):
        self.file_cache = file_cache or FileCache()

    def fetch_watchlist_entries(self, path: Path) -> list[tuple[str, str]]:
        return fetch_watchlist(path)

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
        kabutan_html_dir: Path | None = None,
    ) -> str:
        cached_output = output_cache.get(code4)
        if cached_output is not None:
            return cached_output

        service = FundamentalAnalysisService(api_key=api_key, file_cache=self.file_cache)
        output = service.build_analysis_output(name, code4, build_output_fn=build_fundamental_output, kabutan_html_dir=kabutan_html_dir)
        output_cache[code4] = output
        return output


__all__ = ["FundamentalGuiController"]
