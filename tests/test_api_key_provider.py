import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.data.api_key_provider import fetch_api_key_fallback


class TestApiKeyProvider(unittest.TestCase):
    def test_fetch_api_key_from_env_priority(self):
        with patch.dict(os.environ, {"JQUANTS_API_KEY": "env-key", "JQUANTS_KEY": "k2"}, clear=False):
            self.assertEqual(fetch_api_key_fallback(), "env-key")

    def test_fetch_api_key_from_jquants_key_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            (cwd / "jquants_key.env").write_text('JQUANTS_API_KEY="file-key"\n', encoding="utf-8")
            with patch.dict(os.environ, {"JQUANTS_API_KEY": "", "JQUANTS_KEY": "", "GITHUB_JQUANTS_API_KEY": ""}, clear=False):
                old = Path.cwd()
                os.chdir(cwd)
                try:
                    self.assertEqual(fetch_api_key_fallback(), "file-key")
                finally:
                    os.chdir(old)


if __name__ == "__main__":
    unittest.main()
