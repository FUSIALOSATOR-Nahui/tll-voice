"""
core/gemini.py
Gemini API client: STT transcription and TTS synthesis.
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import sys
import io
import wave

import numpy as np
import google.generativeai as genai


class GeminiClient:
    """
    Wraps Google Generative AI SDK for two tasks:
      - transcribe(): speech-to-text with prompt-guided editing
      - synthesize(): text-to-speech, returns raw audio bytes
    """

    def __init__(self):
        self._configured = False

    def configure(self, api_key: str) -> bool:
        """
        Configure the SDK with the provided API key.
        Returns True on success, False if key is missing/placeholder.
        """
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            print(
                "[Gemini] API key not set. Provide it in config.json or GEMINI_API_KEY env var.",
                file=sys.stderr,
            )
            self._configured = False
            return False
        genai.configure(api_key=api_key)
        self._configured = True
        return True

    @property
    def is_configured(self) -> bool:
        return self._configured

    def transcribe(
        self,
        wav_bytes: bytes,
        prompt: str,
        model_name: str = "gemini-2.0-flash",
        temperature: float = 0.3,
    ) -> str:
        """
        Send WAV audio + text prompt to Gemini; return transcribed/edited text.
        Raises RuntimeError if not configured.
        """
        if not self._configured:
            raise RuntimeError("Gemini API key not configured.")

        audio_part = {"mime_type": "audio/wav", "data": wav_bytes}
        model = genai.GenerativeModel(model_name=model_name)
        response = model.generate_content(
            contents=[audio_part, prompt],
            generation_config=genai.GenerationConfig(temperature=temperature),
        )
        return response.text.strip()

    def synthesize(
        self,
        text: str,
        tts_model: str = "gemini-2.5-flash-preview-tts",
        system_prompt: str = "",
        pace: str = "1.75",
    ) -> bytes | None:
        """
        Convert text to speech using Gemini TTS model.
        Returns raw audio bytes or None if no audio in response.
        Raises RuntimeError if not configured.
        """
        if not self._configured:
            raise RuntimeError("Gemini API key not configured.")

        # Apply pace tag
        try:
            float_pace = float(pace)
            text_to_speak = f"[speed={float_pace}] {text}"
        except ValueError:
            text_to_speak = f"[{pace}] {text}" if pace in ("fast", "slow") else text

        model = genai.GenerativeModel(
            model_name=tts_model,
            system_instruction=system_prompt or None,
        )
        response = model.generate_content(
            text_to_speak,
            generation_config=genai.protos.GenerationConfig(
                response_modalities=["AUDIO"],
                max_output_tokens=8192,
            ),
        )

        for candidate in response.candidates:
            for part in candidate.content.parts:
                inline_data = getattr(part, "inline_data", None)
                if inline_data and "audio" in inline_data.mime_type:
                    return inline_data.data
        return None

    @staticmethod
    def decode_audio(audio_bytes: bytes) -> tuple[np.ndarray, int]:
        """
        Decode raw audio bytes into (numpy array, sample_rate).
        Falls back to raw PCM 16-bit 24kHz (Gemini TTS default).
        """
        try:
            wav_io = io.BytesIO(audio_bytes)
            with wave.open(wav_io, "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())

            dtype = np.int16 if sampwidth == 2 else (np.uint8 if sampwidth == 1 else np.int16)
            samples = np.frombuffer(raw, dtype=dtype)
            if n_channels > 1:
                samples = samples.reshape(-1, n_channels)
            return samples, framerate
        except Exception:
            # Fallback: treat as raw PCM 16-bit 24kHz
            safe = audio_bytes[: len(audio_bytes) - (len(audio_bytes) % 2)]
            return np.frombuffer(safe, dtype=np.int16), 24000
