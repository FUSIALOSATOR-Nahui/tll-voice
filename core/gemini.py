"""
core/gemini.py
Gemini API client: STT transcription.
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
    Wraps Google Generative AI SDK for transcription:
      - transcribe(): speech-to-text with prompt-guided editing
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
        
        # Warm up Pydantic schemas in the main thread to prevent deadlocks in background threads on Windows
        try:
            _ = types.GenerateContentConfig(
                temperature=0.3,
                system_instruction="warmup",
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
            _ = types.Part.from_bytes(data=b"", mime_type="audio/wav")
            print("[Gemini] Warmup completed successfully.")
        except Exception as e:
            print(f"[Gemini] Warmup warning: {e}", file=sys.stderr)
            
        return True

    @property
    def is_configured(self) -> bool:
        return self.client is not None

    def transcribe(
        self,
        wav_bytes: bytes,
        system_instruction: str,
        prompt: str | None = None,
        model_name: str = "gemini-3.1-flash-lite",
        temperature: float = 0.3,
    ) -> str:
        """
        Send WAV audio + system instruction + optional prompt to Gemini; return transcribed/edited text.
        Raises RuntimeError if not configured.
        """
        if not self.client:
            raise RuntimeError("Gemini API key not configured.")

        audio_part = types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav")
        
        contents = [audio_part]
        if prompt:
            contents.append(prompt)
        
        # Explicitly configure thinking_budget = 0 to completely disable step-by-step thinking
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
        
        response = self.client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
        
        if not response or not response.text:
            return ""
        return response.text.strip()
