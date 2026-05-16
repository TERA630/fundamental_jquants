from types import SimpleNamespace

from app.domain.models.metrics import calc_metrics


class _Rec:
    def __init__(self, row, fy, pt="FY"):
        self.row = row
        self.fiscal_year = fy
        self.period_type = pt
        self.cur_per_st = ""
        self.cur_per_en = ""
        self.disclosed_at = ""


def test_calc_metrics_has_eps_per_for_next_forecast_and_quarter():
    latest_fy = _Rec({"Sales": "1000", "OP": "100", "OdP": "90", "NP": "60", "EPS": "50", "BPS": "500"}, 2024)
    prev_fy = _Rec({"Sales": "900", "OP": "90", "OdP": "80", "NP": "55", "EPS": "45", "BPS": "450"}, 2023)
    latest_quarter = _Rec({"EPS": "12.5", "FSales": "1100", "FOP": "120", "FEPS": "55"}, 2024, "3Q")
    current_forecast = _Rec({"FEPS": "60"}, 2024, "FY")
    next_forecast = _Rec({"NxFEPS": "70"}, 2024, "FY")
    periods = SimpleNamespace(
        latest_fy=latest_fy,
        prev_fy=prev_fy,
        latest_quarter=latest_quarter,
        current_forecast=current_forecast,
        next_forecast=next_forecast,
    )

    metrics = calc_metrics(periods, price=1400)
    assert metrics.get("eps_next") == 70.0
    assert metrics.get("eps_forecast") == 55.0
    assert metrics.get("eps_quarter") == 12.5
    assert metrics.get("per_next") == 20.0
    assert round(metrics.get("per_forecast"), 6) == round(1400 / 55, 6)
    assert metrics.get("per_quarter") == 112.0
