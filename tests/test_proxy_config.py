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
        success = client.configure("valid_api_key")
        self.assertTrue(success)
        mock_client_cls.assert_called_once()
        args, kwargs = mock_client_cls.call_args
        self.assertEqual(kwargs.get("api_key"), "valid_api_key")
        http_opts = kwargs.get("http_options")
        self.assertIsNotNone(http_opts)
        self.assertEqual(http_opts.timeout, 10000)

    @patch("core.gemini.genai.Client")
    def test_gemini_client_configure_with_proxy(self, mock_client_cls):
        client = GeminiClient()
        success = client.configure("valid_api_key", api_host="http://127.0.0.1:3002")
        self.assertTrue(success)
        mock_client_cls.assert_called_once()
        args, kwargs = mock_client_cls.call_args
        self.assertEqual(kwargs.get("api_key"), "valid_api_key")
        http_opts = kwargs.get("http_options")
        self.assertIsNotNone(http_opts)
        self.assertEqual(http_opts.base_url, "http://127.0.0.1:3002")
        self.assertEqual(http_opts.timeout, 10000)

    @patch("core.gemini.genai.Client")
    def test_gemini_client_configure_with_fallback(self, mock_client_cls):
        client = GeminiClient()
        client_primary = MagicMock()
        client_fallback = MagicMock()
        mock_client_cls.side_effect = [client_primary, client_fallback]

        success = client.configure(
            api_key="primary_key",
            api_host="http://primary:3000",
            fallback_key="fallback_key",
            fallback_host="http://fallback:3002"
        )
        self.assertTrue(success)
        self.assertEqual(client.client, client_primary)
        self.assertEqual(client.fallback_client, client_fallback)
        self.assertEqual(mock_client_cls.call_count, 2)
        
        # Check call arguments
        calls = mock_client_cls.call_args_list
        primary_kwargs = calls[0].kwargs
        fallback_kwargs = calls[1].kwargs
        
        self.assertEqual(primary_kwargs.get("http_options").timeout, 10000)
        self.assertEqual(fallback_kwargs.get("http_options").timeout, 30000)

    def test_transcribe_with_fallback_success_on_primary_failure(self):
        client = GeminiClient()
        client.client = MagicMock()
        client.fallback_client = MagicMock()

        # Primary client fails with an API Error
        client.client.models.generate_content.side_effect = Exception("Primary failed")
        
        # Fallback client succeeds
        mock_response = MagicMock()
        mock_response.text = "Fallback transcription text"
        client.fallback_client.models.generate_content.return_value = mock_response

        wav_bytes = b"fake wav bytes"
        res = client.transcribe(
            wav_bytes=wav_bytes,
            system_instruction="System prompt",
            prompt="User prompt",
            model_name="gemini-3.1-flash-lite"
        )

        self.assertEqual(res, "Fallback transcription text")
        # Check both were called
        client.client.models.generate_content.assert_called_once()
        client.fallback_client.models.generate_content.assert_called_once()

    def test_transcribe_both_primary_and_fallback_fail(self):
        client = GeminiClient()
        client.client = MagicMock()
        client.fallback_client = MagicMock()

        client.client.models.generate_content.side_effect = Exception("Primary failed")
        client.fallback_client.models.generate_content.side_effect = Exception("Fallback failed")

        wav_bytes = b"fake wav bytes"
        with self.assertRaises(Exception) as context:
            client.transcribe(
                wav_bytes=wav_bytes,
                system_instruction="System prompt",
                prompt="User prompt"
            )
        self.assertIn("Fallback failed", str(context.exception))

    def test_transcribe_primary_success_no_fallback_called(self):
        client = GeminiClient()
        client.client = MagicMock()
        client.fallback_client = MagicMock()

        mock_response = MagicMock()
        mock_response.text = "Primary transcription text"
        client.client.models.generate_content.return_value = mock_response

        wav_bytes = b"fake wav bytes"
        res = client.transcribe(
            wav_bytes=wav_bytes,
            system_instruction="System prompt",
            prompt="User prompt"
        )

        self.assertEqual(res, "Primary transcription text")
        client.client.models.generate_content.assert_called_once()
        # Fallback client should NOT be called
        client.fallback_client.models.generate_content.assert_not_called()

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    @patch("core.engine.GeminiClient")
    @patch.dict(os.environ, {
        "GEMINI_API_KEY": "",
        "GEMINI_API_HOST": "",
        "GEMINI_FALLBACK_API_KEY": "",
        "GEMINI_FALLBACK_API_HOST": ""
    })
    def test_engine_setup_gemini_config_host(self, mock_gemini_client_cls, mock_overlay_cls, mock_tray_cls, mock_sd):
        mock_gemini_client = mock_gemini_client_cls.return_value
        root = MagicMock()
        
        config = {
            "api_key": "dummy_key",
            "api_host": "http://127.0.0.1:3002",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        
        engine = TLLVoiceEngine(root, config, adapter)
        mock_gemini_client.configure.assert_called_once_with(
            "dummy_key", 
            api_host="http://127.0.0.1:3002",
            fallback_key=None,
            fallback_host=None
        )

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    @patch("core.engine.GeminiClient")
    @patch.dict(os.environ, {
        "GEMINI_API_HOST": "http://primary:3000",
        "GEMINI_FALLBACK_API_KEY": "fallback_val",
        "GEMINI_FALLBACK_API_HOST": "http://fallback:3002"
    })
    def test_engine_setup_gemini_fallback_env(self, mock_gemini_client_cls, mock_overlay_cls, mock_tray_cls, mock_sd):
        mock_gemini_client = mock_gemini_client_cls.return_value
        root = MagicMock()
        
        config = {
            "api_key": "dummy_key",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        
        engine = TLLVoiceEngine(root, config, adapter)
        mock_gemini_client.configure.assert_called_once_with(
            "dummy_key",
            api_host="http://primary:3000",
            fallback_key="fallback_val",
            fallback_host="http://fallback:3002"
        )

if __name__ == "__main__":
    unittest.main()
