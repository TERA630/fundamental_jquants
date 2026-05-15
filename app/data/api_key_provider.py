"""Data-layer utility: resolve J-Quants API key from env/files."""

from __future__ import annotations

import os
from pathlib import Path


def _parse_api_key_text(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""
    if "=" in raw:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"JQUANTS_API_KEY", "JQUANTS_KEY", "GITHUB_JQUANTS_API_KEY"}:
                return value.strip().strip('"').strip("'")
    return raw


def fetch_api_key_fallback() -> str:
    env_candidates = [
        os.environ.get("JQUANTS_API_KEY", ""),
        os.environ.get("JQUANTS_KEY", ""),
        os.environ.get("GITHUB_JQUANTS_API_KEY", ""),
    ]
    for value in env_candidates:
        api_key = str(value).strip()
        if api_key:
            return api_key

    file_candidates = [
        Path.cwd() / "jquants_key.env",
        Path.cwd() / "jquants_key",
        Path.cwd() / "jquants_key.txt",
        Path.cwd() / ".jquants_key",
        Path.home() / "jquants_key.env",
        Path.home() / "jquants_key",
        Path.home() / "jquants_key.txt",
        Path.home() / ".jquants_key",
    ]
    for path in file_candidates:
        try:
            api_key = _parse_api_key_text(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if api_key:
            return api_key
    return ""


__all__ = ["fetch_api_key_fallback"]
