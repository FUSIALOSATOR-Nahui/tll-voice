import torch
import numpy as np
import os

class LocalTTSEngine:
    def __init__(self, lang="ru", speaker="xenia"):
        self.lang = lang
        self.speaker = speaker
        self.sample_rate = 24000  # Дефолтный битрейт для v5_5_ru (максимальное качество)
        self.device = torch.device('cpu')
        
        # Для отключения лишних логов от torch.hub
        torch.set_num_threads(4) # Ограничиваем потоки процессора
        
        # Эта функция САМА скачает модель при первом запуске 
        # в ~/.cache/torch/hub/snakers4_silero-models_master/
        self.model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-models',
            model='silero_tts',
            language=self.lang,
            speaker='v5_5_ru', # Используем последнюю версию для максимального качества
            trust_repo=True
        )
        self.model.to(self.device)

    def synthesize(self, text: str, speed: float = 2.0):
        # Silero v5_5_ru принимает текст и возвращает тензор аудиоданных.
        # Встроенного параметра speed в самом вызове apply_tts нет, 
        # поэтому для скорости x2 мы применяем хак: отдадим аудио как есть, 
        # но вернем sample_rate * speed, чтобы плеер проиграл его в 2 раза быстрее.
        # Это даст эффект ускорения (для параллельного чтения подходит идеально).
        
        audio_tensor = self.model.apply_tts(
            text=text,
            speaker=self.speaker,
            sample_rate=self.sample_rate,
            put_accent=True,
            put_yo=True
        )
        
        # Превращаем 1D тензор PyTorch в плоский numpy-массив
        audio_data = audio_tensor.numpy()
        
        target_sample_rate = int(self.sample_rate * speed)
        
        return audio_data, target_sample_rate
