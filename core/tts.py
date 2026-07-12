import torch
import numpy as np
import os
import re
from pathlib import Path

class LocalTTSEngine:
    def __init__(self, lang="ru", speaker="xenia"):
        self.lang = lang
        self.speaker = speaker
        self.sample_rate = 48000  # Максимальное Hi-Fi качество (48000 Гц)
        self.device = torch.device('cpu')
        
        # Для отключения лишних логов от torch.hub
        torch.set_num_threads(4) # Ограничиваем потоки процессора
        
        # Определение локального кэша репозитория для оффлайн режима
        home = str(Path.home())
        self.local_hub_dir = os.path.join(home, ".cache", "torch", "hub", "snakers4_silero-models_master")
        
        # Загрузка русской модели (приоритет локальному кэшу)
        if os.path.isdir(self.local_hub_dir):
            print(f"[TTS Engine] Loading Russian model from local cache: {self.local_hub_dir}")
            self.model, _ = torch.hub.load(
                repo_or_dir=self.local_hub_dir,
                model='silero_tts',
                language='ru',
                speaker='v5_5_ru',
                source='local',
                trust_repo=True
            )
        else:
            print("[TTS Engine] Local cache not found. Downloading Russian model from GitHub...")
            self.model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language='ru',
                speaker='v5_5_ru',
                trust_repo=True
            )
        self.model.to(self.device)
        
        # Английская модель загружается лениво
        self.model_en = None

    def _split_by_language(self, text: str):
        # Разделяем на слова, знаки препинания и пробелы
        tokens = re.split(r'(\s+|[^\w\s])', text)
        
        result = []
        current_lang = None
        current_chunk = []
        
        for token in tokens:
            if not token:
                continue
                
            # Классифицируем токен по наличию алфавитных символов
            if re.search(r'[a-zA-Z]', token):
                token_lang = 'en'
            elif re.search(r'[а-яА-ЯёЁ]', token):
                token_lang = 'ru'
            else:
                # Пробелы и знаки препинания наследуют текущий активный язык
                token_lang = current_lang if current_lang is not None else 'ru'
                
            if current_lang is None:
                current_lang = token_lang
                current_chunk.append(token)
            elif token_lang == current_lang:
                current_chunk.append(token)
            else:
                # Смена языка: сохраняем накопленный чанк
                chunk_str = "".join(current_chunk).strip()
                # Проверяем наличие букв или цифр соответствующего языка в чанке для защиты от ValueError
                has_letters = (re.search(r'[a-zA-Z\d]', chunk_str) if current_lang == 'en' 
                               else re.search(r'[а-яА-ЯёЁ\d]', chunk_str))
                if chunk_str and has_letters:
                    result.append((current_lang, chunk_str))
                current_lang = token_lang
                current_chunk = [token]
                
        # Сохраняем последний чанк
        if current_chunk:
            chunk_str = "".join(current_chunk).strip()
            has_letters = (re.search(r'[a-zA-Z\d]', chunk_str) if current_lang == 'en' 
                           else re.search(r'[а-яА-ЯёЁ\d]', chunk_str))
            if chunk_str and has_letters:
                result.append((current_lang, chunk_str))
                
        return result

    def _normalize_numbers(self, text: str, lang: str) -> str:
        from num2words import num2words
        
        # Сначала заменяем знак процента % на слово
        if lang == 'ru':
            text = text.replace("%", " процентов")
        else:
            text = text.replace("%", " percent")
            
        # Нормализация вещественных (дробных) чисел (например, 2.0 или 2,0)
        def replace_float(match):
            num_str = match.group(0).replace(',', '.')
            try:
                parts = num_str.split('.')
                integer_part = int(parts[0])
                decimal_part = int(parts[1])
                
                if lang == 'ru':
                    int_words = num2words(integer_part, lang='ru')
                    dec_words = num2words(decimal_part, lang='ru')
                    return f"{int_words} точка {dec_words}"
                else:
                    int_words = num2words(integer_part, lang='en')
                    dec_words = num2words(decimal_part, lang='en')
                    return f"{int_words} point {dec_words}"
            except Exception:
                return match.group(0)
                
        text = re.sub(r'\d+[.,]\d+', replace_float, text)
        
        # Нормализация целых чисел
        def replace_int(match):
            try:
                val = int(match.group(0))
                return num2words(val, lang=lang)
            except Exception:
                return match.group(0)
                
        text = re.sub(r'\d+', replace_int, text)
        return text

    def synthesize(self, text: str, speed: float = 2.0):
        parts = self._split_by_language(text)
        
        if not parts:
            return np.array([], dtype=np.float32), self.sample_rate
            
        audio_chunks = []
        # Микропауза 80мс между фрагментами разных языков для естественности стыковки
        silence = np.zeros(int(self.sample_rate * 0.08), dtype=np.float32)
        
        for lang, fragment in parts:
            # Нормализация чисел в слова перед отправкой в модель
            fragment = self._normalize_numbers(fragment, lang)
            if not fragment.strip():
                continue
                
            if lang == 'en':
                # Ленивая загрузка английской модели при первом обнаружении латиницы
                if self.model_en is None:
                    if os.path.isdir(self.local_hub_dir):
                        print(f"[TTS Engine] Loading English model from local cache: {self.local_hub_dir}")
                        self.model_en, _ = torch.hub.load(
                            repo_or_dir=self.local_hub_dir,
                            model='silero_tts',
                            language='en',
                            speaker='v3_en',
                            source='local',
                            trust_repo=True
                        )
                    else:
                        print("[TTS Engine] Local cache not found. Downloading English model (v3_en)...")
                        self.model_en, _ = torch.hub.load(
                            repo_or_dir='snakers4/silero-models',
                            model='silero_tts',
                            language='en',
                            speaker='v3_en',
                            trust_repo=True
                        )
                    self.model_en.to(self.device)
                
                # Подбор тембрально близкого английского спикера
                # en_116 - женский голос (гармонирует с xenia/baya)
                # en_110 - мужской голос (гармонирует с aidar/yaroslav)
                speaker_en = "en_110" if self.speaker in ["aidar", "yaroslav"] else "en_116"
                
                chunk_tensor = self.model_en.apply_tts(
                    text=fragment,
                    speaker=speaker_en,
                    sample_rate=self.sample_rate
                )
            else:
                chunk_tensor = self.model.apply_tts(
                    text=fragment,
                    speaker=self.speaker,
                    sample_rate=self.sample_rate,
                    put_accent=True,
                    put_yo=True
                )
                
            chunk_data = chunk_tensor.numpy()
            if audio_chunks:
                audio_chunks.append(silence)
            audio_chunks.append(chunk_data)
            
        if not audio_chunks:
            return np.array([], dtype=np.float32), self.sample_rate
            
        audio_data = np.concatenate(audio_chunks)
        
        if speed != 1.0:
            audio_data = self._stretch_audio(audio_data, speed)
            
        return audio_data, self.sample_rate

    def _stretch_audio(self, audio: np.ndarray, speed: float, hop_length: int = 256, win_length: int = 1024) -> np.ndarray:
        if speed == 1.0:
            return audio
            
        # Создаем Hann window
        window = np.hanning(win_length)
        
        # Разбиваем аудио на кадры и вычисляем rfft
        frames = []
        for i in range(0, len(audio) - win_length, hop_length):
            frames.append(np.fft.rfft(audio[i : i + win_length] * window))
            
        if not frames:
            return audio
            
        stft = np.array(frames) # Shape: (num_frames, win_length // 2 + 1)
        num_frames, num_bins = stft.shape
        new_num_frames = int(num_frames / speed)
        
        # Новый массив для измененного STFT
        new_stft = np.zeros((new_num_frames, num_bins), dtype=np.complex64)
        
        # Инициализируем фазу первым кадром
        phase_acc = np.angle(stft[0])
        new_stft[0] = stft[0]
        
        # Ожидаемое изменение фазы на один шаг hop_length
        omega = 2 * np.pi * np.arange(num_bins) * hop_length / win_length
        
        for i in range(1, new_num_frames):
            # Соответствующий индекс во входном stft
            src_idx = i * speed
            idx_floor = int(np.floor(src_idx))
            idx_ceil = min(idx_floor + 1, num_frames - 1)
            alpha = src_idx - idx_floor
            
            # Интерполируем амплитуду
            mag = (1 - alpha) * np.abs(stft[idx_floor]) + alpha * np.abs(stft[idx_ceil])
            
            # Разность фаз во входном сигнале
            phase_diff = np.angle(stft[idx_ceil]) - np.angle(stft[idx_floor])
            
            # Вычитаем ожидаемую разность фаз
            delta_phase = phase_diff - omega
            
            # Ограничиваем в пределах [-pi, pi]
            delta_phase = np.mod(delta_phase + np.pi, 2 * np.pi) - np.pi
            
            # Реальная частота
            true_freq = omega + delta_phase
            
            # Накапливаем фазу с новым шагом hop_length
            phase_acc += true_freq
            
            # Восстанавливаем комплексный спектральный отсчет
            new_stft[i] = mag * np.exp(1j * phase_acc)
            
        # Обратное преобразование (ISTFT)
        output_len = new_num_frames * hop_length + win_length
        output = np.zeros(output_len, dtype=np.float32)
        norm = np.zeros(output_len, dtype=np.float32)
        
        for i in range(new_num_frames):
            frame = np.fft.irfft(new_stft[i])
            ptr = i * hop_length
            output[ptr : ptr + win_length] += frame * window
            norm[ptr : ptr + win_length] += window ** 2
            
        norm[norm < 1e-4] = 1.0
        output = output / norm
        return output
