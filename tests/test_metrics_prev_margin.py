import unittest
from types import SimpleNamespace

from app.domain.models.metrics import calc_metrics


class _Rec:
    def __init__(self, row, fy, pt='FY'):
        self.row = row
        self.fiscal_year = fy
        self.period_type = pt
        self.cur_per_st = ''
        self.cur_per_en = ''
        self.disclosed_at = ''


class TestMetricsPrevMargin(unittest.TestCase):
    def test_calc_prev_op_margin_and_prev_ordinary(self):
        latest = _Rec({"Sales": "1100", "OP": "121", "OdP": "101", "NP": "70", "EPS": "55", "BPS": "500"}, 2024)
        prev = _Rec({"Sales": "1000", "OP": "100", "OdP": "90", "NP": "60", "EPS": "50", "BPS": "480"}, 2023)
        periods = SimpleNamespace(latest_fy=latest, prev_fy=prev, latest_quarter=None)

        metrics = calc_metrics(periods, price=1000)

        self.assertAlmostEqual(metrics.get("op_margin"), 11.0)
        self.assertAlmostEqual(metrics.get("prev_op_margin"), 10.0)
        self.assertEqual(metrics.get("prev_ordinary"), 90.0)


if __name__ == "__main__":
    unittest.main()
