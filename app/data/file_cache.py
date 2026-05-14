"""Data-layer file cache implementation."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

CACHE_DIR_NAME = ".jquants_cache"


class FileCache:
    """単純なJSONファイルキャッシュ。API回数削減を最優先にする。"""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(__file__).resolve().parent.parent.parent / CACHE_DIR_NAME)
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


__all__ = ["FileCache", "CACHE_DIR_NAME"]
