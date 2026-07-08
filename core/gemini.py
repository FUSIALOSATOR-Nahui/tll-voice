"""
core/gemini.py
Gemini API client: STT transcription and TTS synthesis.
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import sys
import io
import wave

import numpy as np
from google import genai
from google.genai import types


class GeminiClient:
    """
    Wraps Google Generative AI SDK for two tasks:
      - transcribe(): speech-to-text with prompt-guided editing
      - synthesize(): text-to-speech, returns raw audio bytes
    """

    def __init__(self):
        self.client: genai.Client | None = None

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
            self.client = None
            return False
        self.client = genai.Client(api_key=api_key)
        return True

    @property
    def is_configured(self) -> bool:
        return self.client is not None

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
        if not self.client:
            raise RuntimeError("Gemini API key not configured.")

        audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
        
        # Explicitly configure thinking_budget = 0 to completely disable step-by-step thinking
        config = types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
        
        response = self.client.models.generate_content(
            model=model_name,
            contents=[audio_part, prompt],
            config=config,
        )
        
        if not response or not response.text:
            return ""
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
        if not self.client:
            raise RuntimeError("Gemini API key not configured.")

        # Apply pace tag
        try:
            float_pace = float(pace)
            text_to_speak = f"[speed={float_pace}] {text}"
        except ValueError:
            text_to_speak = f"[{pace}] {text}" if pace in ("fast", "slow") else text

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            max_output_tokens=8192,
            system_instruction=system_prompt or None,
        )
        
        response = self.client.models.generate_content(
            model=tts_model,
            contents=text_to_speak,
            config=config,
        )

        if response and response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        inline_data = getattr(part, "inline_data", None)
                        if inline_data and inline_data.mime_type and "audio" in inline_data.mime_type:
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
