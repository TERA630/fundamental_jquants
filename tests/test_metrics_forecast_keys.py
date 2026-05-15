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


class TestMetricsForecastKeys(unittest.TestCase):
    def test_next_forecast_reads_nxfsales_variant_from_latest_fy(self):
        latest_fy = _Rec({
            'Sales': '1000', 'OP': '100', 'OdP': '90', 'NP': '60', 'EPS': '50', 'BPS': '500',
            'NxFsales': '1200', 'NxFOP': '130', 'NxFOdP': '115', 'NxFNP': '80', 'NxFEPS': '65'
        }, 2024)
        prev_fy = _Rec({'Sales': '900', 'OP': '90', 'OdP': '80', 'NP': '55', 'EPS': '45', 'BPS': '450'}, 2023)
        latest_quarter = _Rec({'FSales': '1050', 'FOP': '110', 'FOdP': '95', 'FNP': '62', 'FEPS': '52'}, 2024, '3Q')
        periods = SimpleNamespace(latest_fy=latest_fy, prev_fy=prev_fy, latest_quarter=latest_quarter)

        metrics = calc_metrics(periods, price=1000)

        self.assertEqual(metrics.get('next_sales'), 1200.0)
        self.assertEqual(metrics.get('next_op'), 130.0)
        self.assertEqual(metrics.get('next_ordinary'), 115.0)
        self.assertEqual(metrics.get('next_np'), 80.0)
        self.assertEqual(metrics.get('next_eps'), 65.0)
        self.assertEqual(metrics.get('prev_op_margin'), 10.0)


if __name__ == '__main__':
    unittest.main()
