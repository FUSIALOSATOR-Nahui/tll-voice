"""
core/audio.py
Cross-platform audio recording via sounddevice (in-memory, no temp files).
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import sys
import io
import wave
import queue

import numpy as np
import sounddevice as sd


class AudioRecorder:
    """
    Captures audio from a microphone into an in-memory WAV buffer.
    Uses sounddevice for cross-platform support.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self._q: queue.Queue = queue.Queue()
        self._stream = None
        self.recording = False
        self.current_rms: float = 0.0
        self.last_audio_data = None

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[Audio Status] {status}", file=sys.stderr)
        self._q.put(indata.copy())
        try:
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            self.current_rms = rms
        except Exception:
            self.current_rms = 0.0

    def _probe_sample_rates(self) -> list[int]:
        """Return sample rates to try, starting with configured rate."""
        rates = [self.sample_rate]
        try:
            dev_info = sd.query_devices(self.device_index)
            dev_default = int(dev_info.get("default_samplerate", 0))
            if dev_default > 0 and dev_default not in rates:
                rates.append(dev_default)
        except Exception:
            pass
        for r in [16000, 48000, 44100, 32000, 24000, 8000]:
            if r not in rates:
                rates.append(r)
        return rates

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the input stream and begin capturing audio."""
        self._q = queue.Queue()
        self.recording = True
        self.current_rms = 0.0
        self.last_audio_data = None

        last_error = None
        for rate in self._probe_sample_rates():
            try:
                self._stream = sd.InputStream(
                    samplerate=rate,
                    channels=self.channels,
                    device=self.device_index,
                    dtype="int16",
                    callback=self._callback,
                )
                self._stream.start()
                if rate != self.sample_rate:
                    print(
                        f"[Audio] Sample rate adjusted: {self.sample_rate} → {rate} "
                        f"(device compatibility)"
                    )
                    self.sample_rate = rate
                return
            except Exception as e:
                last_error = e
                continue

        self.recording = False
        raise last_error if last_error else RuntimeError("Could not open InputStream")

    def stop(self) -> bytes | None:
        """
        Stop capturing, drain the queue, and return a WAV-encoded bytes object.
        Returns None if no audio was captured.
        """
        self.recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        chunks = []
        while not self._q.empty():
            chunks.append(self._q.get())

        if not chunks:
            self.last_audio_data = None
            return None

        audio_data = np.concatenate(chunks, axis=0)
        self.last_audio_data = audio_data

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())
        return wav_io.getvalue()
