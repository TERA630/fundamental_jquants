"""Data-layer utility for resolving J-Quants API key sources."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_KEY_ENV_FILE = "jquants_key.env"
API_KEY_ENV_NAME = "JQUANTS_API_KEY"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch_jquants_api_key(preferred_key: str, env_file_path: Path | None = None) -> str:
    """Resolve API key with precedence: input text -> environment -> local env file."""
    input_key = preferred_key.strip()
    if input_key:
        return input_key

    env_key = os.environ.get(API_KEY_ENV_NAME, "").strip()
    if env_key:
        return env_key

    candidate_path = env_file_path or Path.cwd() / DEFAULT_KEY_ENV_FILE
    if candidate_path.is_file():
        values = _parse_env_file(candidate_path)
        file_key = values.get(API_KEY_ENV_NAME, "").strip()
        if file_key:
            return file_key

    raise ValueError(
        "J-Quants APIキーが見つかりません。入力欄、環境変数 JQUANTS_API_KEY、"
        f"{candidate_path} を確認してください。"
    )


__all__ = ["fetch_jquants_api_key", "DEFAULT_KEY_ENV_FILE", "API_KEY_ENV_NAME"]
