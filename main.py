import os
import sys

# Redirect output streams if None (standard under pythonw.exe) to prevent print crashes
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import time
import json
import queue
import threading
import wave
import io
import tkinter as tk
from tkinter import ttk
import numpy as np
import sounddevice as sd
import pyperclip
from pynput import keyboard as pynput_kb
from pynput.keyboard import GlobalHotKeys, Controller as KbController, Key
import pystray
from PIL import Image, ImageDraw
import google.generativeai as genai

# State Constants
STATE_IDLE = "IDLE"
STATE_RECORDING = "RECORDING"
STATE_PROCESSING = "PROCESSING"
STATE_DONE = "DONE"
STATE_ERROR = "ERROR"
STATE_SYNTHESIS = "SYNTHESIS"

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1, device_index=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self.q = queue.Queue()
        self.stream = None
        self.recording = False
        self.current_rms = 0.0
        self.last_audio_data = None

    def callback(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio Status] {status}", file=sys.stderr)
        self.q.put(indata.copy())
        
        # Calculate real-time RMS for the VU meter animation
        try:
            rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
            self.current_rms = float(rms)
        except Exception:
            self.current_rms = 0.0

    def start(self):
        self.q = queue.Queue()
        self.recording = True
        self.current_rms = 0.0
        self.last_audio_data = None
        
        # Dynamically probe for a sample rate supported by the device
        sample_rates_to_try = [self.sample_rate]
        
        try:
            dev_info = sd.query_devices(self.device_index)
            dev_default_rate = int(dev_info.get('default_samplerate', 0))
            if dev_default_rate > 0 and dev_default_rate not in sample_rates_to_try:
                sample_rates_to_try.append(dev_default_rate)
        except Exception:
            pass
            
        for rate in [16000, 48000, 44100, 32000, 24000, 8000]:
            if rate not in sample_rates_to_try:
                sample_rates_to_try.append(rate)
                
        last_error = None
        for rate in sample_rates_to_try:
            try:
                self.stream = sd.InputStream(
                    samplerate=rate,
                    channels=self.channels,
                    device=self.device_index,
                    dtype='int16',
                    callback=self.callback
                )
                self.stream.start()
                if rate != self.sample_rate:
                    print(f"[Audio] Изменен Sample Rate с {self.sample_rate} на {rate} для совместимости с микрофоном.")
                    self.sample_rate = rate
                return
            except Exception as e:
                last_error = e
                continue
                
        self.recording = False
        raise last_error if last_error else Exception("Не удалось открыть InputStream")

    def stop(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        data = []
        while not self.q.empty():
            data.append(self.q.get())
        if not data:
            self.last_audio_data = None
            return None
        
        audio_data = np.concatenate(data, axis=0)
        self.last_audio_data = audio_data
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())
        return wav_io.getvalue()

class Overlay:
    def __init__(self, root, event_queue):
        self.root = root
        self.queue = event_queue
        
        # Configure borderless window on top
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # Position in bottom-right corner
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = 280
        height = 70
        # Position 30px from right and 80px from bottom (above taskbar)
        x = screen_w - width - 30
        y = screen_h - height - 80
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Modern UI styling
        self.bg_color = "#1e1e2e"       # Dark Slate
        self.text_color = "#cdd6f4"     # Soft White
        self.accent_red = "#f38ba8"     # Pastel Red
        self.accent_yellow = "#f9e2af"  # Pastel Yellow
        self.accent_green = "#a6e3a1"   # Pastel Green
        
        self.root.configure(bg=self.bg_color)
        
        # Main Frame with light border
        self.frame = tk.Frame(self.root, bg=self.bg_color, highlightbackground="#313244", highlightthickness=1)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas for status indicator light
        self.canvas = tk.Canvas(self.frame, width=36, height=36, bg=self.bg_color, bd=0, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=(12, 10))
        self.indicator = self.canvas.create_oval(8, 8, 28, 28, fill="gray", outline="")
        self.current_radius = 10.0
        
        # Text labels
        self.label_title = tk.Label(self.frame, text="TLL-Voice", font=("Segoe UI", 10, "bold"), fg="#89b4fa", bg=self.bg_color)
        self.label_title.pack(anchor=tk.W, pady=(10, 0))
        
        self.label_status = tk.Label(self.frame, text="Запуск...", font=("Segoe UI", 9), fg=self.text_color, bg=self.bg_color)
        self.label_status.pack(anchor=tk.W, pady=(2, 10))
        
        self.dot_count = 0
        self.current_state = STATE_IDLE
        self.fade_after_id = None
        self.root.attributes("-alpha", 0.0)
        self.root.withdraw()

    def set_state(self, state, details=""):
        self.current_state = state
        if state == STATE_IDLE:
            self.hide()
        else:
            self.show()
            
        if state == STATE_RECORDING:
            mode_name = "Умный Редактор" if details == "mode1" else "Буквально"
            self.label_title.configure(text=f"ЗАПИСЬ [{mode_name}]", fg=self.accent_red)
            self.label_status.configure(text="Говорите... Нажмите хоткей еще раз")
            self.canvas.itemconfigure(self.indicator, fill=self.accent_red)
        elif state == STATE_PROCESSING:
            self.label_title.configure(text="ОБРАБОТКА", fg=self.accent_yellow)
            self.label_status.configure(text="Отправка в Gemini...")
            self.canvas.itemconfigure(self.indicator, fill=self.accent_yellow)
            self.animate_processing()
        elif state == STATE_DONE:
            self.label_title.configure(text="УСПЕШНО", fg=self.accent_green)
            self.label_status.configure(text="Текст вставлен!")
            self.canvas.itemconfigure(self.indicator, fill=self.accent_green)
        elif state == STATE_ERROR:
            self.label_title.configure(text="ОШИБКА", fg=self.accent_red)
            self.label_status.configure(text=details[:35] + "..." if len(details) > 35 else details)
            self.canvas.itemconfigure(self.indicator, fill=self.accent_red)
        elif state == STATE_SYNTHESIS:
            self.label_title.configure(text="СИНТЕЗ РЕЧИ", fg="#6272a4")
            self.label_status.configure(text="Генерация аудио...")
            self.canvas.itemconfigure(self.indicator, fill="#6272a4")
            self.animate_synthesis()

    def show(self):
        if self.fade_after_id:
            self.root.after_cancel(self.fade_after_id)
            self.fade_after_id = None
            
        if self.root.state() != "normal":
            self.root.attributes("-alpha", 0.0)
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            
        self.fade_in()

    def hide(self):
        if self.fade_after_id:
            self.root.after_cancel(self.fade_after_id)
            self.fade_after_id = None
            
        self.fade_out()

    def fade_in(self):
        try:
            current_alpha = float(self.root.attributes("-alpha"))
        except Exception:
            current_alpha = 0.0
            
        if current_alpha < 0.9:
            new_alpha = min(current_alpha + 0.1, 0.9)
            self.root.attributes("-alpha", new_alpha)
            self.fade_after_id = self.root.after(20, self.fade_in)
        else:
            self.fade_after_id = None

    def fade_out(self):
        try:
            current_alpha = float(self.root.attributes("-alpha"))
        except Exception:
            current_alpha = 0.0
            
        if current_alpha > 0.0:
            new_alpha = max(current_alpha - 0.1, 0.0)
            self.root.attributes("-alpha", new_alpha)
            self.fade_after_id = self.root.after(20, self.fade_out)
        else:
            self.root.withdraw()
            self.fade_after_id = None

    def update_vu_indicator(self, recorder):
        if self.current_state != STATE_RECORDING:
            # Restore default size (centered at 18, 18, radius 10)
            cx, cy = 18, 18
            self.canvas.coords(self.indicator, cx - 10, cy - 10, cx + 10, cy + 10)
            return
            
        rms = getattr(recorder, "current_rms", 0.0)
        
        # Map RMS (approx. 100 to 3000) to 0.0 - 1.0 range
        min_rms = 100.0
        max_rms = 3000.0
        if rms < min_rms:
            norm = 0.0
        else:
            norm = min(1.0, (rms - min_rms) / (max_rms - min_rms))
            
        min_r = 10.0
        max_r = 17.0
        target_r = min_r + norm * (max_r - min_r)
        
        # Easing/Smoothing: 15% step towards target
        self.current_radius += 0.15 * (target_r - self.current_radius)
        
        # Update coordinates on canvas (centered at 18, 18)
        cx, cy = 18, 18
        r = self.current_radius
        self.canvas.coords(self.indicator, cx - r, cy - r, cx + r, cy + r)
        
        self.root.after(30, lambda: self.update_vu_indicator(recorder))

    def animate_processing(self):
        if self.current_state != STATE_PROCESSING:
            return
        self.dot_count = (self.dot_count + 1) % 4
        dots = "." * self.dot_count
        self.label_status.configure(text=f"Отправка в Gemini{dots}")
        self.root.after(400, self.animate_processing)

    def animate_synthesis(self):
        if self.current_state != STATE_SYNTHESIS:
            return
        self.dot_count = (self.dot_count + 1) % 4
        dots = "." * self.dot_count
        self.label_status.configure(text=f"Генерация аудио{dots}")
        self.root.after(400, self.animate_synthesis)

class TLLVoiceApp:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.overlay = Overlay(self.root, self.queue)
        
        self.load_config()
        self.setup_audio()
        self.setup_gemini()
        
        self.recorder = AudioRecorder(
            sample_rate=self.config["audio"]["sample_rate"],
            channels=self.config["audio"]["channels"],
            device_index=self.config["audio"]["device_index"]
        )
        
        self.current_mode = None # None or 1 or 2
        
        # Start tray icon
        self.setup_tray()
        
        # Bind keyboard hooks
        self.bind_hotkeys()
        
        # Start queue poller
        self.root.after(50, self.poll_queue)

    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки config.json: {e}", file=sys.stderr)
            self.config = {
                "api_key": "YOUR_GEMINI_API_KEY",
                "model": "gemini-2.0-flash",
                "temperature": 0.3,
                "hotkeys": {"mode1": "alt+caps lock", "mode2": "ctrl+caps lock"},
                "prompts": {"mode1": "", "mode2": ""},
                "audio": {"sample_rate": 16000, "channels": 1, "device_index": None}
            }

    def setup_audio(self):
        # Auto-detect default microphone if index is None or invalid
        device_idx = self.config["audio"].get("device_index")
        
        try:
            devices = sd.query_devices()
        except Exception as e:
            print(f"[Audio Error] Не удалось перечислить устройства: {e}", file=sys.stderr)
            devices = []
            
        # Helper to find first valid input device in the system
        def find_first_input_device():
            for idx, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    return idx
            return None

        # Helper to check if a specific index is a valid input device
        def is_valid_input_device(idx):
            if idx is None or not isinstance(idx, int):
                return False
            if idx < 0 or idx >= len(devices):
                return False
            return devices[idx].get('max_input_channels', 0) > 0

        # Validate the configured device_idx
        if is_valid_input_device(device_idx):
            print(f"[Audio] Используется микрофон из конфигурации index {device_idx}: {devices[device_idx]['name']}")
        else:
            if device_idx is not None:
                print(f"[Audio Warning] Микрофон с индексом {device_idx} недоступен или не является устройством ввода.", file=sys.stderr)
            
            # Fallback 1: Try default input device
            default_device = -1
            try:
                default_device = sd.default.device[0]
            except Exception:
                pass
                
            if is_valid_input_device(default_device):
                self.config["audio"]["device_index"] = default_device
                print(f"[Audio] Выбран системный микрофон по умолчанию index {default_device}: {devices[default_device]['name']}")
            else:
                # Fallback 2: Try first input device
                first_input = find_first_input_device()
                if first_input is not None:
                    self.config["audio"]["device_index"] = first_input
                    print(f"[Audio] Системный микрофон по умолчанию недоступен. Выбран первый рабочий входной канал index {first_input}: {devices[first_input]['name']}")
                else:
                    self.config["audio"]["device_index"] = None
                    print("[Audio Error] В системе не найдено ни одного устройства ввода звука!", file=sys.stderr)

    def setup_gemini(self):
        # API Key can be set in config.json or environment variable
        api_key = self.config.get("api_key")
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            api_key = os.environ.get("GEMINI_API_KEY")
            
        if api_key:
            genai.configure(api_key=api_key)
            self.gemini_configured = True
        else:
            self.gemini_configured = False
            print("[Warning] API ключ Gemini не задан. Укажите его в config.json или переменной GEMINI_API_KEY", file=sys.stderr)

    @staticmethod
    def _to_pynput_hotkey(hotkey_str):
        """Convert 'alt+caps lock' style string to pynput '<alt>+<caps_lock>' format."""
        mapping = {
            'alt': '<alt>', 'ctrl': '<ctrl>', 'shift': '<shift>',
            'cmd': '<cmd>', 'caps lock': '<caps_lock>', 'caps_lock': '<caps_lock>',
            'enter': '<enter>', 'space': '<space>', 'tab': '<tab>',
            'esc': '<esc>', 'delete': '<delete>', 'backspace': '<backspace>',
            'f1': '<f1>', 'f2': '<f2>', 'f3': '<f3>', 'f4': '<f4>',
            'f5': '<f5>', 'f6': '<f6>', 'f7': '<f7>', 'f8': '<f8>',
            'f9': '<f9>', 'f10': '<f10>', 'f11': '<f11>', 'f12': '<f12>',
        }
        # Split by '+' but preserve 'caps lock' (two words)
        raw = hotkey_str.strip().lower()
        # Normalize 'caps lock' before splitting
        raw = raw.replace('caps lock', 'caps_lock')
        parts = [p.strip() for p in raw.split('+')]
        converted = [mapping.get(p, p if len(p) == 1 else f'<{p}>') for p in parts]
        return '+'.join(converted)

    def bind_hotkeys(self):
        hotkey_m1 = str(self.config["hotkeys"].get("mode1", "alt+caps lock")).strip().lower()
        hotkey_m2 = str(self.config["hotkeys"].get("mode2", "ctrl+caps lock")).strip().lower()
        hotkey_m3 = str(self.config["hotkeys"].get("mode3", "ctrl+shift+caps lock")).strip().lower()

        try:
            hotkeys = {
                self._to_pynput_hotkey(hotkey_m1): lambda: self.queue.put(("hotkey", 1)),
                self._to_pynput_hotkey(hotkey_m2): lambda: self.queue.put(("hotkey", 2)),
                self._to_pynput_hotkey(hotkey_m3): lambda: self.queue.put(("hotkey", 3)),
            }
            self.hotkey_listener = GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
            print(f"[Hotkeys] Зарегистрирован Mode 1: {hotkey_m1}")
            print(f"[Hotkeys] Зарегистрирован Mode 2: {hotkey_m2}")
            print(f"[Hotkeys] Зарегистрирован Mode 3: {hotkey_m3}")
        except Exception as e:
            print(f"[Error] Не удалось привязать хоткеи: {e}", file=sys.stderr)
            self.root.after(500, lambda: self.queue.put(("error", "Ошибка хоткеев!")))

    def setup_tray(self):
        # Create a simple icon
        icon_w, icon_h = 64, 64
        image = Image.new('RGBA', (icon_w, icon_h), color=(0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Background dark rounded circle
        dc.ellipse((4, 4, 60, 60), fill=(30, 30, 46, 255), outline=(137, 180, 250, 255), width=3)
        # Micro shape
        dc.rounded_rectangle((24, 16, 40, 38), radius=8, fill=(137, 180, 250, 255))
        dc.arc((18, 24, 46, 44), start=0, end=180, fill=(137, 180, 250, 255), width=3)
        dc.line((32, 44, 32, 52), fill=(137, 180, 250, 255), width=4)
        dc.line((22, 52, 42, 52), fill=(137, 180, 250, 255), width=4)
        
        menu = pystray.Menu(
            pystray.MenuItem('Выход', self.on_exit)
        )
        self.tray_icon = pystray.Icon("TLL-Voice", image, "TLL-Voice Dictation", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def poll_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                msg_type = msg[0]
                
                if msg_type == "hotkey":
                    mode = msg[1]
                    self.handle_hotkey(mode)
                elif msg_type == "ui_state":
                    state = msg[1]
                    details = msg[2] if len(msg) > 2 else ""
                    self.overlay.set_state(state, details)
                elif msg_type == "error":
                    self.overlay.set_state(STATE_ERROR, msg[1])
                    self.root.after(2500, lambda: self.overlay.set_state(STATE_IDLE))
                elif msg_type == "done":
                    self.overlay.set_state(STATE_DONE)
                    self.root.after(800, lambda: self.overlay.set_state(STATE_IDLE))
                elif msg_type == "exit":
                    self.root.destroy()
                    
        except queue.Empty:
            pass
        self.root.after(50, self.poll_queue)

    def handle_hotkey(self, mode):
        # Mute/stop any active audio playback instantly when any hotkey is pressed
        sd.stop()

        if mode == 3:
            # If we were recording Mode 1 or 2, stop it without processing
            if self.current_mode is not None:
                try:
                    self.recorder.stop()
                except Exception:
                    pass
                self.current_mode = None
            
            self.start_tts()
        else:
            # Toggle mode 1 or 2
            if self.current_mode is not None:
                # Stop recording and process
                self.current_mode = None
                self.stop_and_process(mode)
            else:
                # Start recording
                self.current_mode = mode
                self.start_recording(mode)

    def start_recording(self, mode):
        print(f"[App] Начало записи для Mode {mode}")
        try:
            self.recorder.start()
            self.overlay.set_state(STATE_RECORDING, f"mode{mode}")
            self.overlay.current_radius = 10.0
            self.overlay.update_vu_indicator(self.recorder)
        except Exception as e:
            print(f"[Error] Ошибка запуска аудио: {e}", file=sys.stderr)
            self.current_mode = None
            self.queue.put(("error", f"Ошибка аудио: {e}"))

    def stop_and_process(self, mode):
        print("[App] Остановка записи, отправка в API...")
        self.overlay.set_state(STATE_PROCESSING)
        
        # Capture bytes
        try:
            wav_bytes = self.recorder.stop()
        except Exception as e:
            print(f"[Error] Ошибка остановки аудио: {e}", file=sys.stderr)
            self.queue.put(("error", "Ошибка записи"))
            return
            
        if not wav_bytes:
            print("[Warning] Запись пуста")
            self.queue.put(("error", "Пустая запись"))
            return
            
        # Silence check (preventing keypress click trigger by stripping first/last 150ms)
        audio_data = getattr(self.recorder, "last_audio_data", None)
        if audio_data is not None and len(audio_data) > 0:
            trim_samples = int(0.15 * self.recorder.sample_rate)
            if len(audio_data) > 2 * trim_samples:
                check_data = audio_data[trim_samples:-trim_samples]
            else:
                check_data = np.array([], dtype=audio_data.dtype)
                
            if len(check_data) > 0:
                rms_trimmed = np.sqrt(np.mean(check_data.astype(np.float32) ** 2))
            else:
                rms_trimmed = 0.0
                
            threshold = self.config["audio"].get("silence_threshold", 100)
            print(f"[Silence Check] Trimmed RMS: {rms_trimmed:.2f} (Threshold: {threshold})")
            
            if rms_trimmed < threshold:
                print("[Warning] Обнаружена тишина, отмена отправки.")
                self.queue.put(("error", "Микрофон молчит!"))
                return
            
        # Run API call in a separate thread so Tkinter UI is responsive
        threading.Thread(target=self.process_audio, args=(wav_bytes, mode), daemon=True).start()

    def process_audio(self, wav_bytes, mode):
        if not self.gemini_configured:
            self.queue.put(("error", "Не настроен API Ключ!"))
            return
            
        try:
            model_name = self.config.get("model", "gemini-2.0-flash")
            temp = self.config.get("temperature", 0.3)
            prompt = self.config["prompts"][f"mode{mode}"]
            
            # Formulate audio chunk
            audio_part = {
                "mime_type": "audio/wav",
                "data": wav_bytes
            }
            
            model = genai.GenerativeModel(model_name=model_name)
            response = model.generate_content(
                contents=[audio_part, prompt],
                generation_config=genai.GenerationConfig(temperature=temp)
            )
            
            result_text = response.text.strip()
            print(f"[API Response] {result_text}")
            
            if result_text:
                # Copy to clipboard
                pyperclip.copy(result_text)
                
                # Brief wait before pasting
                time.sleep(0.15)
                
                # Paste
                _kbc = KbController()
                with _kbc.pressed(Key.ctrl):
                    _kbc.tap('v')
                self.queue.put(("done",))
            else:
                self.queue.put(("error", "Пустой ответ API"))
                
        except Exception as e:
            print(f"[API Error] {e}", file=sys.stderr)
            self.queue.put(("error", f"API Ошибка: {str(e)}"))

    def start_tts(self):
        try:
            text = pyperclip.paste()
        except Exception as e:
            print(f"[Error] Не удалось получить буфер обмена: {e}", file=sys.stderr)
            self.queue.put(("error", "Ошибка буфера обмена"))
            return

        if not text or not text.strip():
            print("[Warning] Буфер обмена пуст")
            self.queue.put(("error", "Буфер обмена пуст!"))
            return

        print("[App] Синтез речи...")
        self.overlay.set_state(STATE_SYNTHESIS)
        
        # Run API call in a separate thread so Tkinter UI is responsive
        threading.Thread(target=self.process_tts, args=(text.strip(),), daemon=True).start()

    def process_tts(self, text):
        if not self.gemini_configured:
            self.queue.put(("error", "Не настроен API Ключ!"))
            return
            
        try:
            model_name = self.config.get("tts_model", "gemini-2.5-flash-preview-tts")
            prompt = self.config["prompts"].get("mode3", "")
            pace = self.config.get("tts_pace", "fast")
            
            # Format text pace option using native tags
            try:
                float_pace = float(pace)
                text_to_speak = f"[speed={float_pace}] {text}"
            except ValueError:
                if pace == "fast":
                    text_to_speak = f"[fast] {text}"
                else:
                    text_to_speak = text
                
            # Pass prompt as system_instruction to prevent model confusion/cutoff,
            # and explicitly set high max_output_tokens for audio modality budget.
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=prompt
            )
            response = model.generate_content(
                text_to_speak,
                generation_config=genai.protos.GenerationConfig(
                    response_modalities=["AUDIO"],
                    max_output_tokens=8192
                )
            )
            
            audio_bytes = None
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    inline_data = getattr(part, 'inline_data', None)
                    if inline_data and "audio" in inline_data.mime_type:
                        audio_bytes = inline_data.data
                        break
                if audio_bytes:
                    break
            
            if audio_bytes:
                # Instantly hide the overlay when playback starts
                self.queue.put(("ui_state", STATE_IDLE))
                self.play_audio_bytes(audio_bytes)
            else:
                self.queue.put(("error", "Нет аудио в ответе"))
                
        except Exception as e:
            print(f"[TTS Error] {e}", file=sys.stderr)
            self.queue.put(("error", f"Ошибка: {str(e)}"))

    def play_audio_bytes(self, audio_bytes):
        try:
            # Try to decode via wave module
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, 'rb') as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                
                raw_data = wf.readframes(n_frames)
                
                if sampwidth == 2:
                    samples = np.frombuffer(raw_data, dtype=np.int16)
                elif sampwidth == 1:
                    samples = np.frombuffer(raw_data, dtype=np.uint8)
                else:
                    samples = np.frombuffer(raw_data, dtype=np.int16)
                
                sample_rate = framerate
                if n_channels > 1:
                    samples = samples.reshape(-1, n_channels)
        except Exception as e:
            # Fallback to raw PCM 16-bit 24kHz (as returned by gemini-2.5-flash-preview-tts)
            # Ensure number of bytes is even for signed 16-bit
            safe_bytes = audio_bytes[:len(audio_bytes) - (len(audio_bytes) % 2)]
            samples = np.frombuffer(safe_bytes, dtype=np.int16)
            sample_rate = 24000
            
        sd.play(samples, samplerate=sample_rate)

    def on_exit(self):
        print("[App] Выход...")
        sd.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        if hasattr(self, 'hotkey_listener'):
            self.hotkey_listener.stop()
        self.queue.put(("exit",))

def run_onboarding(config_path):
    print("\n=== TLL-Voice: Настройка микрофона / Microphone Setup ===")
    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"[Ошибка] Не удалось получить список аудиоустройств: {e}")
        return False

    input_devices = []
    for idx, dev in enumerate(devices):
        if dev.get('max_input_channels', 0) > 0:
            input_devices.append((idx, dev['name'], dev['hostapi']))

    if not input_devices:
        print("[Ошибка] Входные аудиоустройства (микрофоны) не найдены в системе!")
        return False

    print("\nДоступные устройства ввода:")
    for i, (idx, name, hostapi) in enumerate(input_devices):
        try:
            hostapi_name = sd.query_hostapis(hostapi)['name']
        except Exception:
            hostapi_name = "Unknown API"
        print(f"  [{i}] ID {idx}: {name} ({hostapi_name})")

    # Detect default input device
    default_idx = -1
    try:
        default_idx = sd.default.device[0]
    except Exception:
        pass

    default_selection = 0
    for i, (idx, name, hostapi) in enumerate(input_devices):
        if idx == default_idx:
            default_selection = i
            break

    print(f"\nРекомендуемое устройство по умолчанию отмечено как [{default_selection}].")

    while True:
        try:
            choice = input(f"Выберите номер микрофона [0-{len(input_devices)-1}] (по умолчанию {default_selection}): ").strip()
            if not choice:
                selected_idx = input_devices[default_selection][0]
                break
            choice_val = int(choice)
            if 0 <= choice_val < len(input_devices):
                selected_idx = input_devices[choice_val][0]
                break
            else:
                print(f"Неверный номер. Пожалуйста, введите число от 0 до {len(input_devices)-1}.")
        except ValueError:
            print("Пожалуйста, введите корректное число или просто нажмите Enter для выбора по умолчанию.")
        except (KeyboardInterrupt, EOFError):
            print("\nНастройка отменена. Используется значение по умолчанию.")
            selected_idx = input_devices[default_selection][0]
            break

    # Load current config, update device_index, and save
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception:
        config_data = {}

    if "audio" not in config_data:
        config_data["audio"] = {}
    config_data["audio"]["device_index"] = selected_idx

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print(f"\n[Успех] Микрофон (ID {selected_idx}) успешно сохранен в config.json!\n")
        return True
    except Exception as e:
        print(f"[Ошибка] Не удалось сохранить конфигурацию: {e}")
        return False

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    # Read config to check if setup is needed
    needs_setup = False
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if cfg.get("audio", {}).get("device_index") is None:
                needs_setup = True
    except Exception:
        needs_setup = True

    # Check for command line flags
    explicit_setup = "--setup" in sys.argv
    
    if needs_setup or explicit_setup:
        # Check if stdin is a TTY
        is_interactive = sys.stdin and sys.stdin.isatty()
        if is_interactive:
            run_onboarding(config_path)
        else:
            if explicit_setup:
                print("Error: --setup requires an interactive terminal.", file=sys.stderr)
                sys.exit(1)
            else:
                # Silently log/warn and use defaults since we have no TTY
                print("[Warning] No interactive terminal detected for first-time onboarding. Using system defaults.", file=sys.stderr)

    # Hide command window in background on startup if run via pythonw
    root = tk.Tk()
    app = TLLVoiceApp(root)
    root.mainloop()
