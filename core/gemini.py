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
      - transcribe(): speech-to-text with prompt-guided editing, with automated resilient fallback
    """

    def __init__(self):
        self.client: genai.Client | None = None
        self.fallback_client: genai.Client | None = None

    def configure(
        self,
        api_key: str,
        api_host: str | None = None,
        fallback_key: str | None = None,
        fallback_host: str | None = None,
    ) -> bool:
        """
        Configure the SDK with the primary API key/host and optional fallback API key/host.
        Returns True on success, False if no keys are successfully configured.
        """
        # Configure Primary Client
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            print(
                "[Gemini] Primary API key not set. Direct access disabled.",
                file=sys.stderr,
            )
            self.client = None
        else:
            if api_host:
                self.client = genai.Client(
                    api_key=api_key,
                    http_options=types.HttpOptions(base_url=api_host)
                )
            else:
                self.client = genai.Client(api_key=api_key)

        # Configure Fallback Client
        if fallback_key and fallback_key != "YOUR_GEMINI_API_KEY":
            if fallback_host:
                self.fallback_client = genai.Client(
                    api_key=fallback_key,
                    http_options=types.HttpOptions(base_url=fallback_host)
                )
            else:
                self.fallback_client = genai.Client(api_key=fallback_key)
        else:
            self.fallback_client = None

        if not self.client and not self.fallback_client:
            return False
        
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
        return self.client is not None or self.fallback_client is not None

    def transcribe(
        self,
        wav_bytes: bytes,
        system_instruction: str,
        prompt: str | None = None,
        model_name: str = "gemini-3.1-flash-lite",
        temperature: float = 0.3,
    ) -> str:
        """
        Send WAV audio + system instruction + optional prompt to Gemini.
        Tries the primary client first, and falls back to the fallback proxy client if it fails.
        """
        if not self.is_configured:
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
        
        last_exception = None

        # 1. Try Primary Client
        if self.client:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                if response and response.text:
                    return response.text.strip()
                return ""
            except Exception as e:
                print(f"[Gemini] Primary channel failed: {e}. Swapping to fallback proxy...", file=sys.stderr)
                last_exception = e

        # 2. Try Fallback Client
        if self.fallback_client:
            try:
                response = self.fallback_client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                if response and response.text:
                    return response.text.strip()
                return ""
            except Exception as e:
                print(f"[Gemini] Fallback channel failed: {e}", file=sys.stderr)
                last_exception = e

        # If we reached here, all attempted clients failed
        if last_exception:
            raise last_exception
        
        return ""
