from app.domain.builders.fundamental_output_impl import _build_periods


def test_build_periods_builds_current_and_next_forecast_from_same_fy_end_rows():
    rows = [
        {
            "CurPerType": "3Q",
            "CurPerSt": "2025-04-01",
            "CurPerEn": "2026-03-31",
            "DisclosedDate": "2026-02-10",
            "FSales": "",
            "FOP": "",
            "NxFSales": "1700",
            "NxFOP": "180",
        },
        {
            "CurPerType": "FY",
            "CurPerSt": "2025-04-01",
            "CurPerEn": "2026-03-31",
            "DisclosedDate": "2026-05-12",
            "Sales": "1500",
            "OP": "150",
            "FSales": "1600",
            "FOP": "170",
            "NxFSales": "",
            "NxFOP": "",
        },
    ]

    periods = _build_periods(rows)
    assert periods.current_forecast is not None
    assert periods.current_forecast.row.get("FSales") == "1600"
    assert periods.current_forecast.row.get("FOP") == "170"
    assert periods.current_forecast.row.get("NxFSales") == "1700"
    assert periods.current_forecast.row.get("NxFOP") == "180"

    assert periods.next_forecast is not None
    assert periods.next_forecast.row.get("NxFSales") == "1700"
    assert periods.next_forecast.row.get("NxFOP") == "180"


def test_build_periods_uses_latest_disclosed_fy_end_as_forecast_anchor():
    rows = [
        {
            "CurPerType": "FY",
            "CurPerSt": "2023-04-01",
            "CurPerEn": "2024-03-31",
            "DisclosedDate": "2024-05-10",
            "Sales": "1000",
            "OP": "100",
        },
        {
            "CurPerType": "3Q",
            "CurPerSt": "2025-04-01",
            "CurPerEn": "2026-03-31",
            "DisclosedDate": "2026-02-12",
            "FSales": "1600",
            "FOP": "170",
            "NxFSales": "1750",
        },
    ]

    periods = _build_periods(rows)
    assert periods.current_forecast is not None
    assert periods.current_forecast.cur_per_en == "2026-03-31"
    assert periods.current_forecast.row.get("FSales") == "1600"
