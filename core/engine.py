"""
core/engine.py
TLLVoiceEngine — the application orchestrator.

This is the CORE LAYER. It is completely ignorant of the OS.
It receives a PlatformAdapter via constructor injection (DI) and calls:
  - adapter.register_hotkeys(...)
  - adapter.inject_text(text)
  - adapter.cleanup()

INVARIANT:
  - NO imports of keyboard, pynput.
  - NO `if platform.system()` checks.
  - NO direct audio device or clipboard manipulation (delegated to adapter).
"""

import os
import sys
import queue
import threading
import tkinter as tk

import sounddevice as sd
import numpy as np

from core.state import (
    STATE_IDLE,
    STATE_RECORDING,
    STATE_PROCESSING,
    STATE_DONE,
    STATE_ERROR,
)
from core.audio import AudioRecorder
from core.gemini import GeminiClient
from core.gui.overlay import Overlay
from core.gui.tray import TrayIcon


def _log_debug(message: str) -> None:
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(project_root, "tll_voice.log")
        from datetime import datetime
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time_str}] {message}\n")
    except Exception:
        pass


class TLLVoiceEngine:
    """
    Main application engine. Wires audio, Gemini API, GUI, and the platform
    adapter together. All state transitions flow through a thread-safe queue
    polled by Tkinter's .after() loop.
    """

    def __init__(self, root: tk.Tk, config: dict, adapter) -> None:
        """
        Parameters
        ----------
        root    : Tkinter root window (must be created in the main thread)
        config  : Parsed config.json dict
        adapter : PlatformAdapter instance (WindowsAdapter or LinuxAdapter)
        """
        self.root = root
        self.config = config
        self.adapter = adapter
        self.queue: queue.Queue = queue.Queue()
        self.current_mode: int | None = None

        # --- Sub-systems ---
        self.overlay = Overlay(self.root)
        self.tray = TrayIcon(on_exit_callback=self.on_exit)

        self.recorder = AudioRecorder(
            sample_rate=config["audio"].get("sample_rate", 16000),
            channels=config["audio"].get("channels", 1),
            device_index=config["audio"].get("device_index"),
        )
        self._setup_audio_device()

        self.gemini = GeminiClient()
        self._setup_gemini()

        # --- Launch sub-systems ---
        self.tray.start()
        self._bind_hotkeys()

        # Start Tkinter queue poller
        self.root.after(50, self._poll_queue)

    # ==================================================================
    # Initialisation helpers
    # ==================================================================

    def _setup_audio_device(self) -> None:
        """Validate configured device_index; auto-detect fallback."""
        device_idx = self.config["audio"].get("device_index")
        try:
            devices = sd.query_devices()
        except Exception as e:
            print(f"[Audio] Cannot enumerate devices: {e}", file=sys.stderr)
            return

        def is_valid(idx):
            if idx is None or not isinstance(idx, int):
                return False
            if idx < 0 or idx >= len(devices):
                return False
            return devices[idx].get("max_input_channels", 0) > 0

        def first_input():
            for i, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    return i
            return None

        if is_valid(device_idx):
            print(f"[Audio] Using configured device #{device_idx}: {devices[device_idx]['name']}")
            return

        if device_idx is not None:
            print(
                f"[Audio] Configured device #{device_idx} unavailable, auto-detecting.",
                file=sys.stderr,
            )

        # Fallback 1: system default
        try:
            default = sd.default.device[0]
        except Exception:
            default = -1

        if is_valid(default):
            self.config["audio"]["device_index"] = default
            self.recorder.device_index = default
            print(f"[Audio] Using system default device #{default}: {devices[default]['name']}")
            return

        # Fallback 2: first available input
        first = first_input()
        if first is not None:
            self.config["audio"]["device_index"] = first
            self.recorder.device_index = first
            print(f"[Audio] Using first available input device #{first}: {devices[first]['name']}")
        else:
            self.config["audio"]["device_index"] = None
            self.recorder.device_index = None
            print("[Audio] No input devices found!", file=sys.stderr)

    def _setup_gemini(self) -> None:
        api_key = self.config.get("api_key", "")
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            api_key = os.environ.get("GEMINI_API_KEY", "")
        self.gemini.configure(api_key)

    def _bind_hotkeys(self) -> None:
        """Build hotkey→callback mapping and hand it to the platform adapter."""
        hk = self.config.get("hotkeys", {})
        m1 = str(hk.get("mode1", "alt+caps lock")).strip().lower()
        m2 = str(hk.get("mode2", "ctrl+caps lock")).strip().lower()

        bindings = {
            m1: lambda: self.queue.put(("hotkey", 1)),
            m2: lambda: self.queue.put(("hotkey", 2)),
        }
        try:
            self.adapter.register_hotkeys(bindings)
        except Exception as e:
            print(f"[Engine] Failed to bind hotkeys: {e}", file=sys.stderr)
            self.root.after(500, lambda: self.queue.put(("error", "Ошибка хоткеев!")))

    # ==================================================================
    # Tkinter queue poller (main thread)
    # ==================================================================

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                kind = msg[0]

                if kind == "hotkey":
                    self._handle_hotkey(msg[1])
                elif kind == "ui_state":
                    state = msg[1]
                    details = msg[2] if len(msg) > 2 else ""
                    self.overlay.set_state(state, details)
                elif kind == "error":
                    self.overlay.set_state(STATE_ERROR, msg[1])
                    self.root.after(2500, lambda: self.overlay.set_state(STATE_IDLE))
                elif kind == "done":
                    self.overlay.set_state(STATE_DONE)
                    self.root.after(800, lambda: self.overlay.set_state(STATE_IDLE))
                elif kind == "exit":
                    self.root.destroy()
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    # ==================================================================
    # Hotkey dispatch
    # ==================================================================

    def _handle_hotkey(self, mode: int) -> None:
        # Any hotkey immediately stops active audio playback
        sd.stop()

        if self.current_mode is not None:
            # Second press: stop and process
            self.current_mode = None
            self._stop_and_process(mode)
        else:
            # First press: start recording
            self.current_mode = mode
            self._start_recording(mode)

    # ==================================================================
    # Recording
    # ==================================================================

    def _start_recording(self, mode: int) -> None:
        print(f"[Engine] Start recording mode {mode}")
        try:
            self.recorder.start()
            self.overlay.set_state(STATE_RECORDING, f"mode{mode}")
            self.overlay.current_radius = 10.0
            self.overlay.update_vu_indicator(self.recorder)
        except Exception as e:
            print(f"[Engine] Audio start error: {e}", file=sys.stderr)
            self.current_mode = None
            self.queue.put(("error", f"Ошибка аудио: {e}"))

    def _stop_and_process(self, mode: int) -> None:
        print("[Engine] Stop recording, sending to API…")
        self.overlay.set_state(STATE_PROCESSING)

        try:
            wav_bytes = self.recorder.stop()
        except Exception as e:
            print(f"[Engine] Recorder stop error: {e}", file=sys.stderr)
            self.queue.put(("error", "Ошибка записи"))
            return

        if not wav_bytes:
            print("[Engine] Empty recording.")
            self.queue.put(("error", "Пустая запись"))
            return

        # Silence detection (strip 150ms from each end, check RMS)
        audio_data = self.recorder.last_audio_data
        if audio_data is not None and len(audio_data) > 0:
            trim = int(0.15 * self.recorder.sample_rate)
            check = audio_data[trim:-trim] if len(audio_data) > 2 * trim else np.array([], dtype=audio_data.dtype)
            rms = float(np.sqrt(np.mean(check.astype(np.float32) ** 2))) if len(check) > 0 else 0.0
            threshold = self.config["audio"].get("silence_threshold", 100)
            print(f"[Silence] RMS={rms:.1f}  threshold={threshold}")
            if rms < threshold:
                print("[Silence] Silent recording — aborting.")
                self.queue.put(("error", "Микрофон молчит!"))
                return

        threading.Thread(
            target=self._process_audio, args=(wav_bytes, mode), daemon=True
        ).start()

    def _process_audio(self, wav_bytes: bytes, mode: int) -> None:
        _log_debug(f"[Audio] Start processing mode {mode}. Wav size: {len(wav_bytes)}")
        if not self.gemini.is_configured:
            _log_debug("[Audio] Error: Gemini is not configured")
            self.queue.put(("error", "Не настроен API Ключ!"))
            return
        try:
            model = self.config.get("model", "gemini-2.0-flash")
            temp = float(self.config.get("temperature", 0.3))
            from core.config import load_prompt_by_mode
            _log_debug("[Audio] Loading prompt...")
            system_instr, user_prompt = load_prompt_by_mode(f"mode{mode}")
            _log_debug(f"[Audio] Loaded prompt. Sys instruction length: {len(system_instr)}, User prompt present: {user_prompt is not None}")

            _log_debug(f"[Audio] Invoking transcribe with model {model}...")
            text = self.gemini.transcribe(
                wav_bytes=wav_bytes,
                system_instruction=system_instr,
                prompt=user_prompt,
                model_name=model,
                temperature=temp
            )
            _log_debug(f"[Audio] Transcribe completed. Response length: {len(text) if text else 0}")
            print(f"[API] Response: {text}")

            if text:
                # Delegate platform-specific text injection to the adapter
                _log_debug(f"[Audio] Injecting text: {text[:30]}...")
                self.adapter.inject_text(text)
                _log_debug("[Audio] Text injection completed.")
                self.queue.put(("done",))
            else:
                _log_debug("[Audio] Empty response from API")
                self.queue.put(("error", "Пустой ответ API"))
        except Exception as e:
            _log_debug(f"[Audio] Exception during processing: {e}")
            print(f"[API] Error: {e}", file=sys.stderr)
            self.queue.put(("error", f"API Ошибка: {e}"))

    # ==================================================================
    # Exit
    # ==================================================================

    def on_exit(self) -> None:
        print("[Engine] Exiting…")
        sd.stop()
        self.tray.stop()
        self.adapter.cleanup()
        self.queue.put(("exit",))
