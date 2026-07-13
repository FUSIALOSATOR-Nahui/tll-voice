import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.gemini import GeminiClient
from core.engine import TLLVoiceEngine

class TestProxyConfig(unittest.TestCase):

    @patch("core.gemini.genai.Client")
    def test_gemini_client_configure_without_proxy(self, mock_client_cls):
        client = GeminiClient()
        # Normal configuration
        success = client.configure("valid_api_key")
        self.assertTrue(success)
        mock_client_cls.assert_called_once_with(api_key="valid_api_key")

    @patch("core.gemini.genai.Client")
    def test_gemini_client_configure_with_proxy(self, mock_client_cls):
        client = GeminiClient()
        # Configuration with api_host proxy
        success = client.configure("valid_api_key", api_host="http://127.0.0.1:3002")
        self.assertTrue(success)
        # Check that it passed http_options with the base_url set
        mock_client_cls.assert_called_once()
        args, kwargs = mock_client_cls.call_args
        self.assertEqual(kwargs.get("api_key"), "valid_api_key")
        http_opts = kwargs.get("http_options")
        self.assertIsNotNone(http_opts)
        self.assertEqual(http_opts.base_url, "http://127.0.0.1:3002")

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    @patch("core.engine.GeminiClient")
    def test_engine_setup_gemini_config_host(self, mock_gemini_client_cls, mock_overlay_cls, mock_tray_cls, mock_sd):
        mock_gemini_client = mock_gemini_client_cls.return_value
        root = MagicMock()
        
        # Test config having api_host
        config = {
            "api_key": "dummy_key",
            "api_host": "http://127.0.0.1:3002",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        
        engine = TLLVoiceEngine(root, config, adapter)
        mock_gemini_client.configure.assert_called_once_with("dummy_key", api_host="http://127.0.0.1:3002")

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    @patch("core.engine.GeminiClient")
    @patch.dict(os.environ, {"GEMINI_API_HOST": "http://178.159.94.14/gemini"})
    def test_engine_setup_gemini_env_host(self, mock_gemini_client_cls, mock_overlay_cls, mock_tray_cls, mock_sd):
        mock_gemini_client = mock_gemini_client_cls.return_value
        root = MagicMock()
        
        # Test env variable fallback
        config = {
            "api_key": "dummy_key",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        
        engine = TLLVoiceEngine(root, config, adapter)
        mock_gemini_client.configure.assert_called_once_with("dummy_key", api_host="http://178.159.94.14/gemini")

if __name__ == "__main__":
    unittest.main()
