import unittest
from pathlib import Path
import sys
import numpy as np
import sounddevice as sd

# Добавляем корень проекта в sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.tts import LocalTTSEngine

class TestTTSPlayback(unittest.TestCase):
    def test_tts_playback_real(self):
        print("\n[TTS Playback Test] Инициализация LocalTTSEngine...")
        engine = LocalTTSEngine(lang="ru", speaker="baya")
        
        test_text = "В данном сценарии проверяется mixed-language синтез. Мы используем Python и PyTorch для работы с моделями Silero на скорости 2.0, а также число 20 и показатель 50%."
        print(f"[TTS Playback Test] Синтез фразы: '{test_text}'")
        
        audio_data, target_sample_rate = engine.synthesize(test_text, speed=2.0)
        
        # Базовая проверка возвращаемых значений
        self.assertIsInstance(audio_data, np.ndarray)
        self.assertGreater(len(audio_data), 0)
        self.assertIsInstance(target_sample_rate, int)
        
        print(f"[TTS Playback Test] Воспроизведение звука на частоте {target_sample_rate} Гц...")
        # Воспроизводим звук без моков
        sd.play(audio_data, target_sample_rate)
        sd.wait()
        print("[TTS Playback Test] Воспроизведение завершено.")

if __name__ == "__main__":
    unittest.main()
