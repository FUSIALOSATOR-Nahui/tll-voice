import unittest
from pathlib import Path
import sys
import numpy as np

# Добавляем корень проекта в sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.tts import LocalTTSEngine

class TestTTSMinimal(unittest.TestCase):
    def test_tts_synthesis(self):
        # Инициализируем TTS движок
        engine = LocalTTSEngine(lang="ru", speaker="xenia")
        
        # Запускаем синтез
        text = "Тест"
        audio_data, target_sample_rate = engine.synthesize(text, speed=1.5)
        
        # Проверяем возвращаемые типы и значения
        self.assertIsInstance(audio_data, np.ndarray)
        self.assertGreater(len(audio_data), 0)
        self.assertIsInstance(target_sample_rate, int)
        
        # 24000 * 1.5 = 36000
        self.assertEqual(target_sample_rate, 36000)

if __name__ == "__main__":
    unittest.main()