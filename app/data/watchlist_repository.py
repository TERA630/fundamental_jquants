"""Data-layer repository for watchlist file loading/parsing."""

from __future__ import annotations

import re
from pathlib import Path


def parse_watchlist_text(text: str) -> list[tuple[str, str]]:
    patterns = [
        re.compile(r"[-*]?\s*([^\n()（）]+?)\s*[\(（]\s*(\d{4})\s*[\)）]"),
        re.compile(r"^\s*(\d{4})\s*[-,:：\t ]+\s*([^\n]+?)\s*$"),
        re.compile(r"^\s*([^\n,，\t]+?)\s*[,，\t]\s*(\d{4})\s*$"),
    ]
    entries: list[tuple[str, str]] = []
    seen_codes: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        stock_name = ""
        code4 = ""
        for idx, pattern in enumerate(patterns):
            matched = pattern.search(line)
            if not matched:
                continue
            if idx == 1:
                code4 = matched.group(1).strip()
                stock_name = matched.group(2).strip()
            else:
                stock_name = matched.group(1).strip()
                code4 = matched.group(2).strip()
            break

        if not code4 or code4 in seen_codes:
            continue

        seen_codes.add(code4)
        entries.append((stock_name, code4))

    return entries


def fetch_watchlist_entries(path: Path) -> list[tuple[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp932"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"監視銘柄ファイルを読み込めませんでした: {last_error}")

    parsed_entries = parse_watchlist_text(text)
    if not parsed_entries:
        raise ValueError(
            "監視銘柄ファイルから銘柄を抽出できませんでした。対応形式例: '銘柄名 (1234)', '1234  銘柄名', '銘柄名,1234'"
        )

    return parsed_entries


__all__ = ["parse_watchlist_text", "fetch_watchlist_entries"]
