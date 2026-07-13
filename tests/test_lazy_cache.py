import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import shutil
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.engine import TLLVoiceEngine
from core.gemini import GeminiClient, RepetitionDetectedError

class TestLazyCache(unittest.TestCase):

    def setUp(self):
        self.dump_dir = project_root / "debug_dumps"
        # Clean up dump directory before each test
        if self.dump_dir.exists():
            shutil.rmtree(self.dump_dir)

    def tearDown(self):
        # Clean up dump directory after each test
        if self.dump_dir.exists():
            shutil.rmtree(self.dump_dir)

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    def test_no_dump_on_success(self, mock_overlay, mock_tray, mock_sd):
        # Setup engine with mock config, adapter
        root = MagicMock()
        config = {
            "api_key": "dummy_key",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        engine = TLLVoiceEngine(root, config, adapter)

        # Mock gemini client to succeed
        engine.gemini = MagicMock()
        engine.gemini.is_configured = True
        engine.gemini.transcribe.return_value = "Normal transcribed text"

        wav_bytes = b"fake successful wav bytes"
        
        # Invoke process_audio in synchronous fashion (avoid background thread to check state)
        engine._process_audio(wav_bytes, mode=1)

        # Assert no dumps created
        self.assertFalse(self.dump_dir.exists() and any(self.dump_dir.iterdir()))
        
        # Assert text injected
        adapter.inject_text.assert_called_once_with("Normal transcribed text")
        
        # Check queue has "done" message
        msgs = []
        while not engine.queue.empty():
            msgs.append(engine.queue.get())
        self.assertIn(("done",), msgs)

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    def test_dump_on_api_error(self, mock_overlay, mock_tray, mock_sd):
        root = MagicMock()
        config = {
            "api_key": "dummy_key",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        engine = TLLVoiceEngine(root, config, adapter)

        # Mock gemini to fail with Exception
        engine.gemini = MagicMock()
        engine.gemini.is_configured = True
        engine.gemini.transcribe.side_effect = Exception("API connection error")

        wav_bytes = b"fake error wav bytes"
        engine._process_audio(wav_bytes, mode=1)

        # Assert dump created with correct prefix and content
        self.assertTrue(self.dump_dir.exists())
        files = list(self.dump_dir.glob("err_*.wav"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), wav_bytes)

        # Check queue has error message
        msgs = []
        while not engine.queue.empty():
            msgs.append(engine.queue.get())
        
        # It should contain an error notification
        self.assertTrue(any(msg[0] == "error" and "API Ошибка" in msg[1] for msg in msgs))

    @patch("core.engine.sd")
    @patch("core.engine.TrayIcon")
    @patch("core.engine.Overlay")
    def test_dump_on_repetition_detected(self, mock_overlay, mock_tray, mock_sd):
        root = MagicMock()
        config = {
            "api_key": "dummy_key",
            "audio": {},
            "hotkeys": {}
        }
        adapter = MagicMock()
        engine = TLLVoiceEngine(root, config, adapter)

        # Mock gemini to raise RepetitionDetectedError
        engine.gemini = MagicMock()
        engine.gemini.is_configured = True
        engine.gemini.transcribe.side_effect = RepetitionDetectedError("Loop detected")

        wav_bytes = b"fake loop wav bytes"
        engine._process_audio(wav_bytes, mode=1)

        # Assert dump created with correct prefix and content
        self.assertTrue(self.dump_dir.exists())
        files = list(self.dump_dir.glob("loop_*.wav"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), wav_bytes)

        # Check queue has "error" with loop alert
        msgs = []
        while not engine.queue.empty():
            msgs.append(engine.queue.get())
        
        self.assertTrue(any(msg[0] == "error" and "Обнаружено зацикливание!" in msg[1] for msg in msgs))

    def test_detect_repetition_logic(self):
        from core.gemini import detect_repetition
        
        # Less than 10 words should not trigger loop detection
        self.assertFalse(detect_repetition("привет привет привет привет привет"))
        
        # 10+ words without loops
        self.assertFalse(detect_repetition("это очень хороший день и погода прекрасная мы идем гулять в парк"))

        # Consecutive word repetition (4+ times)
        self.assertTrue(detect_repetition("это очень плохой день потому что там дождь дождь дождь дождь и сыро"))
        
        # Consecutive phrase repetition of 2 words (3+ times)
        self.assertTrue(detect_repetition("я думаю что погода хорошая погода хорошая погода хорошая для прогулки"))

        # Consecutive phrase repetition of 3 words (3+ times)
        self.assertTrue(detect_repetition("мы пишем тесты пишем тесты пишем тесты для проверки корректности логики"))

        # Non-adjacent phrase repetitions (should NOT trigger)
        self.assertFalse(detect_repetition("сегодня хорошая погода я люблю гулять когда хорошая погода и завтра тоже будет хорошая погода"))

if __name__ == "__main__":
    unittest.main()
