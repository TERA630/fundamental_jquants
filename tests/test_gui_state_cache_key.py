from pathlib import Path

from app.gui_state import build_output_cache_key


def test_build_output_cache_key_changes_by_dir(tmp_path: Path):
    code = "7203"
    key1 = build_output_cache_key(code, None)
    key2 = build_output_cache_key(code, tmp_path / "a")

    assert key1 != key2
