import sys
import types
import unittest


def _install_stub_modules() -> None:
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")

        class DummySession:
            def __init__(self):
                self.headers = {}

            def mount(self, *_args, **_kwargs):
                return None

            def get(self, *_args, **_kwargs):
                raise RuntimeError("network disabled in test")

        requests.Session = DummySession
        requests.RequestException = Exception
        sys.modules["requests"] = requests

        adapters = types.ModuleType("requests.adapters")
        class HTTPAdapter:
            def __init__(self, *args, **kwargs):
                pass
        adapters.HTTPAdapter = HTTPAdapter
        sys.modules["requests.adapters"] = adapters

    if "urllib3" not in sys.modules:
        urllib3 = types.ModuleType("urllib3")
        sys.modules["urllib3"] = urllib3

    if "urllib3.util" not in sys.modules:
        urllib3_util = types.ModuleType("urllib3.util")
        sys.modules["urllib3.util"] = urllib3_util

    if "urllib3.util.retry" not in sys.modules:
        retry_mod = types.ModuleType("urllib3.util.retry")
        class Retry:
            def __init__(self, *args, **kwargs):
                pass
        retry_mod.Retry = Retry
        sys.modules["urllib3.util.retry"] = retry_mod


_install_stub_modules()

from fundamental_jquants_v7 import build_period_index


class TestPeriodMerge(unittest.TestCase):
    def test_prev_fy_is_merged_when_revision_row_has_blanks(self):
        rows = [
            {"Code": "80580", "CurPerType": "FY", "CurPerSt": "2023-04-01", "CurPerEn": "2024-03-31", "DisclosedDate": "2024-05-08", "Sales": "1000", "OP": "100", "OdP": "90", "NP": "60", "EPS": "50"},
            {"Code": "80580", "CurPerType": "FY", "CurPerSt": "2023-04-01", "CurPerEn": "2024-03-31", "DisclosedDate": "2024-06-01", "Sales": "", "OP": None, "OdP": "", "NP": "", "EPS": ""},
            {"Code": "80580", "CurPerType": "FY", "CurPerSt": "2024-04-01", "CurPerEn": "2025-03-31", "DisclosedDate": "2025-05-08", "Sales": "1100", "OP": "120", "OdP": "100", "NP": "70", "EPS": "55"},
        ]

        periods = build_period_index(rows)

        self.assertIsNotNone(periods.latest_fy)
        self.assertIsNotNone(periods.prev_fy)
        self.assertEqual(periods.latest_fy.fiscal_year, 2024)
        self.assertEqual(periods.prev_fy.fiscal_year, 2023)
        self.assertEqual(periods.prev_fy.row.get("Sales"), "1000")
        self.assertEqual(periods.prev_fy.row.get("OP"), "100")
        self.assertEqual(periods.prev_fy.row.get("OdP"), "90")
        self.assertEqual(periods.prev_fy.row.get("NP"), "60")
        self.assertEqual(periods.prev_fy.row.get("EPS"), "50")


if __name__ == "__main__":
    unittest.main()
