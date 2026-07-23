import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import sys
import os

# Добавляем корень проекта в sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.config import load_prompt_by_mode
from core.gemini import GeminiClient

class TestGeminiSplit(unittest.TestCase):

    def test_load_prompt_by_mode_no_split(self):
        # Тестируем поведение при отсутствии маркера ===
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            mode1_file = prompts_dir / "mode1.md"
            mode1_file.write_text("Hello, this is standard prompt.", encoding="utf-8")
            
            # Подменяем пути в config.py, временно пропатчив Path
            with patch("core.config.Path") as mock_path:
                # Настраиваем mock_path так, чтобы filepath указывал на наш временный файл
                mock_path.return_value.resolve.return_value.parent.parent = Path(tmpdir)
                system_instr, user_prompt = load_prompt_by_mode("mode1")
                
            self.assertEqual(system_instr, "Hello, this is standard prompt.")
            self.assertIsNone(user_prompt)

    def test_load_prompt_by_mode_with_split(self):
        # Тестируем поведение при наличии маркера ===
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()
            mode1_file = prompts_dir / "mode1.md"
            mode1_file.write_text("System role instruction\n===\nUser query prompt", encoding="utf-8")
            
            with patch("core.config.Path") as mock_path:
                mock_path.return_value.resolve.return_value.parent.parent = Path(tmpdir)
                system_instr, user_prompt = load_prompt_by_mode("mode1")
                
            self.assertEqual(system_instr, "System role instruction")
            self.assertEqual(user_prompt, "User query prompt")

    def test_load_prompt_by_mode_fallback(self):
        # Тестируем фолбек при отсутствии файла
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("core.config.Path") as mock_path:
                mock_path.return_value.resolve.return_value.parent.parent = Path(tmpdir)
                system_instr, user_prompt = load_prompt_by_mode("nonexistent_mode")
                
            # Проверяем, что возвращается дефолтный текст и None
            self.assertTrue(len(system_instr) > 0)
            self.assertIsNone(user_prompt)

    @patch("core.gemini.genai")
    def test_gemini_client_transcribe_no_user_prompt(self, mock_genai):
        # Тестируем вызов transcribe() без пользовательского промпта
        client = GeminiClient()
        client.client = MagicMock()
        
        # Симулируем успешный ответ
        mock_response = MagicMock()
        mock_response.text = "Transcribed text"
        client.client.models.generate_content.return_value = mock_response
        
        wav_bytes = b"fake wav bytes"
        system_instr = "You are a transcriber"
        
        res = client.transcribe(
            wav_bytes=wav_bytes,
            system_instruction=system_instr,
            prompt=None,
            model_name="gemini-3.5-flash-lite"
        )
        
        self.assertEqual(res, "Transcribed text")
        
        # Проверяем аргументы вызова generate_content
        client.client.models.generate_content.assert_called_once()
        args, kwargs = client.client.models.generate_content.call_args
        
        self.assertEqual(kwargs["model"], "gemini-3.5-flash-lite")
        # Проверяем contents: должен быть только audio_part
        self.assertEqual(len(kwargs["contents"]), 1)
        self.assertEqual(kwargs["contents"][0].inline_data.mime_type, "audio/wav")
        self.assertEqual(kwargs["contents"][0].inline_data.data, wav_bytes)
        
        # Проверяем GenerateContentConfig
        config = kwargs["config"]
        self.assertEqual(config.system_instruction, system_instr)
        from google.genai import types
        self.assertEqual(config.thinking_config.thinking_level, types.ThinkingLevel.MINIMAL)

    @patch("core.gemini.genai")
    def test_gemini_client_transcribe_with_user_prompt(self, mock_genai):
        # Тестируем вызов transcribe() с пользовательским промптом
        client = GeminiClient()
        client.client = MagicMock()
        
        mock_response = MagicMock()
        mock_response.text = "Transcribed text with prompt"
        client.client.models.generate_content.return_value = mock_response
        
        wav_bytes = b"fake wav bytes"
        system_instr = "You are a transcriber"
        user_prompt = "Do a structured transcription"
        
        res = client.transcribe(
            wav_bytes=wav_bytes,
            system_instruction=system_instr,
            prompt=user_prompt,
            model_name="gemini-3.5-flash-lite"
        )
        
        self.assertEqual(res, "Transcribed text with prompt")
        
        # Проверяем аргументы вызова generate_content
        client.client.models.generate_content.assert_called_once()
        args, kwargs = client.client.models.generate_content.call_args
        
        # Проверяем contents: должен содержать audio_part и текст промпта
        self.assertEqual(len(kwargs["contents"]), 2)
        self.assertEqual(kwargs["contents"][0].inline_data.mime_type, "audio/wav")
        self.assertEqual(kwargs["contents"][0].inline_data.data, wav_bytes)
        self.assertEqual(kwargs["contents"][1], user_prompt)
        
        # Проверяем GenerateContentConfig
        config = kwargs["config"]
        self.assertEqual(config.system_instruction, system_instr)
        from google.genai import types
        self.assertEqual(config.thinking_config.thinking_level, types.ThinkingLevel.MINIMAL)

if __name__ == "__main__":
    unittest.main()
