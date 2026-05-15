import unittest
import sys
import types


def _install_stub_modules() -> None:
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")

        class DummySession:
            def __init__(self):
                self.headers = {}

            def mount(self, *_args, **_kwargs):
                return None

        requests.Session = DummySession
        requests.RequestException = Exception
        sys.modules["requests"] = requests

        adapters = types.ModuleType("requests.adapters")

        class HTTPAdapter:
            def __init__(self, *args, **kwargs):
                pass

        adapters.HTTPAdapter = HTTPAdapter
        sys.modules["requests.adapters"] = adapters

    if "urllib3.util.retry" not in sys.modules:
        retry_mod = types.ModuleType("urllib3.util.retry")

        class Retry:
            def __init__(self, *args, **kwargs):
                pass

        retry_mod.Retry = Retry
        sys.modules["urllib3.util.retry"] = retry_mod


_install_stub_modules()

from app.domain.usecases.fundamental_analysis import FundamentalAnalysisService


class InMemoryCache:
    def __init__(self):
        self.store = {}

    def get_or_fetch(self, key, _ttl, fetcher):
        if key in self.store:
            return self.store[key]
        value = fetcher()
        self.store[key] = value
        return value


class FakeClient:
    def __init__(self):
        self.master_calls = 0
        self.summary_calls = 0

    def get_master(self, _code):
        self.master_calls += 1
        return {"CompanyName": "テスト株式会社", "S33Nm": "卸売業"}

    def get_summary(self, _code):
        self.summary_calls += 1
        return [{"CurPerType": "FY", "CurPerSt": "2024-04-01", "Sales": "100", "OP": "10", "OdP": "9", "NP": "6", "EPS": "50", "BPS": "500"}]


class FakeMarketProvider:
    def __init__(self):
        self.calls = 0

    def __call__(self, _code4):
        self.calls += 1
        return {"price": 2000.0, "market_cap": 123_000_000_000.0}


class TestFundamentalAnalysisService(unittest.TestCase):
    def test_fetch_uses_injected_dependencies_and_cache(self):
        client = FakeClient()
        market = FakeMarketProvider()
        cache = InMemoryCache()
        service = FundamentalAnalysisService(
            api_key="dummy",
            file_cache=cache,
            client=client,
            fetch_market_snapshot=market,
        )

        master1 = service.fetch_master("8058")
        summary1 = service.fetch_summary_rows("8058")
        snap1 = service.fetch_price_snapshot("8058")

        master2 = service.fetch_master("8058")
        summary2 = service.fetch_summary_rows("8058")
        snap2 = service.fetch_price_snapshot("8058")

        self.assertEqual(master1, master2)
        self.assertEqual(summary1, summary2)
        self.assertEqual(snap1, snap2)
        self.assertEqual(client.master_calls, 1)
        self.assertEqual(client.summary_calls, 1)
        self.assertEqual(market.calls, 1)


if __name__ == "__main__":
    unittest.main()
