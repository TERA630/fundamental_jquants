"""Presentation helpers: bridge GUI use-cases and domain/output builders."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.domain.builders.fundamental_output import build_fundamental_output_text


def fetch_watchlist(path: Path) -> list[tuple[str, str]]:
    """監視銘柄ファイルを読み込み、GUI用の銘柄一覧へ整形して返す。"""
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp932"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise ValueError(f"監視銘柄ファイルを読み込めませんでした: {last_error}")
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
        if not code or code in seen:
            continue
        seen.add(code)
        out.append((name, code))
    if not out:
        raise ValueError("監視銘柄ファイルから銘柄を抽出できませんでした。")
    return out


def build_fundamental_output(
    *,
    name: str,
    code4: str,
    master: dict[str, Any] | None,
    summary_rows: list[dict[str, Any]],
    price: float | None,
    market_cap: float | None,
) -> str:
    """ドメイン層の出力生成ビルダーを呼び出す。"""
    return build_fundamental_output_text(
        name=name,
        code4=code4,
        master=master,
        summary_rows=summary_rows,
        price=price,
        market_cap=market_cap,
    )
