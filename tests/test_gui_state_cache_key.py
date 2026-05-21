from pathlib import Path

from app.gui_state import build_output_cache_key


def test_build_output_cache_key_changes_by_dir_and_fallback(tmp_path: Path):
    code = "7203"
    key1 = build_output_cache_key(code, None, True)
    key2 = build_output_cache_key(code, tmp_path / "a", True)
    key3 = build_output_cache_key(code, tmp_path / "a", False)

    assert key1 != key2
    assert key2 != key3
