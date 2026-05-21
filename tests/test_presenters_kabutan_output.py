from app.domain.models.kabutan_forecast import KabutanForecastPair, KabutanForecastRow
from app.presenters import build_kabutan_forecast_output


def test_build_kabutan_forecast_output_appends_section():
    base = "base output"
    pair = KabutanForecastPair(
        previous_actual=KabutanForecastRow("2025.03", 2025, 3, "実績", 1000, 100, 90, 80),
        current_forecast=KabutanForecastRow("2026.03", 2026, 3, "予想", 1200, 130, 120, 110),
        next_forecast=KabutanForecastRow("2027.03", 2027, 3, "予想", 1350, 150, 140, 120),
    )

    text = build_kabutan_forecast_output(base, pair, "html", None)

    assert "■株探 業績推移（通期）" in text
    assert "2025年" in text
    assert "2026年(予)" in text
    assert "2027年(予)" in text
    assert "■予想チェーン（通期） [ソース: 株探]" in text
    assert "売上：実績 2025" in text


def test_build_kabutan_forecast_output_chain_includes_eps_and_dividend():
    base = "base output"
    pair = KabutanForecastPair(
        previous_actual=KabutanForecastRow("2025.03", 2025, 3, "実績", 1000, 100, 90, 80, revised_eps=50.5, dividend=20.0),
        current_forecast=KabutanForecastRow("2026.03", 2026, 3, "予想", 1200, 130, 120, 110, revised_eps=65.2, dividend=24.0),
        next_forecast=KabutanForecastRow("2027.03", 2027, 3, "予想", 1350, 150, 140, 120, revised_eps=70.1, dividend=26.0),
    )

    text = build_kabutan_forecast_output(base, pair, "html", None)

    assert "修正1株益：実績 2025 50.5円[KBT]" in text
    assert "配当：実績 2025 20.0円[KBT]" in text


def test_build_kabutan_forecast_output_renders_na_rows_when_none():
    text = build_kabutan_forecast_output("base output", None, "none", "HTML解析に失敗")
    assert "■株探 業績推移（通期）" in text
    assert "株探ソース: 取得不可 (HTML解析に失敗)" in text
    assert "実績(N/A)" in text
    assert "今期予想(N/A)" in text
    assert "来期予想(N/A)" in text
    assert "2025年" not in text
    assert "N/A" in text
    assert "予想チェーン" not in text
