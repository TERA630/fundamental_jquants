from pathlib import Path

from app.gui_controller import FundamentalGuiController


class DummyService:
    def __init__(self):
        self.calls = []

    def build_analysis_output(self, name, code4, build_output_fn, kabutan_html_dir=None):
        self.calls.append((name, code4, kabutan_html_dir))
        return f"OUT:{name}:{code4}:{kabutan_html_dir}"


def test_fetch_analysis_output_uses_injected_service_factory(tmp_path: Path):
    dummy_service = DummyService()

    def build_service(_api_key: str, _cache):
        return dummy_service

    controller = FundamentalGuiController(build_fundamental_service=build_service)
    output_cache = {}
    cache_key = "k1"

    out1 = controller.fetch_analysis_output(
        api_key="token",
        name="トヨタ",
        code4="7203",
        output_cache=output_cache,
        output_cache_key=cache_key,
        kabutan_html_dir=tmp_path,
    )
    out2 = controller.fetch_analysis_output(
        api_key="token",
        name="トヨタ",
        code4="7203",
        output_cache=output_cache,
        output_cache_key=cache_key,
        kabutan_html_dir=tmp_path,
    )

    assert out1 == out2
    assert len(dummy_service.calls) == 1
