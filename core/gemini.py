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


class RepetitionDetectedError(Exception):
    """Выбрасывается при обнаружении бесконечного зацикливания в ответе модели."""
    pass


def detect_repetition(text: str) -> bool:
    # Normalize text (lower case and keep alphanumeric words)
    words = [w.lower() for w in text.split() if w.isalnum()]
    if len(words) < 10:
        return False

    # 1. Check for consecutive word repetitions (4+ times)
    consecutive_count = 1
    for i in range(1, len(words)):
        if words[i] == words[i-1]:
            consecutive_count += 1
            if consecutive_count >= 4:
                return True
        else:
            consecutive_count = 1

    # 2. Check phrase repetitions of 2, 3 or 4 words (3+ times consecutively)
    for n in [2, 3, 4]:
        if len(words) >= n * 3:
            for i in range(len(words) - 3 * n + 1):
                chunk1 = words[i : i + n]
                chunk2 = words[i + n : i + 2 * n]
                chunk3 = words[i + 2 * n : i + 3 * n]
                if chunk1 == chunk2 == chunk3:
                    return True
    return False


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
                    http_options=types.HttpOptions(base_url=api_host, timeout=10000)
                )
            else:
                self.client = genai.Client(
                    api_key=api_key,
                    http_options=types.HttpOptions(timeout=10000)
                )

        # Configure Fallback Client
        if fallback_key and fallback_key != "YOUR_GEMINI_API_KEY":
            if fallback_host:
                self.fallback_client = genai.Client(
                    api_key=fallback_key,
                    http_options=types.HttpOptions(base_url=fallback_host, timeout=30000)
                )
            else:
                self.fallback_client = genai.Client(
                    api_key=fallback_key,
                    http_options=types.HttpOptions(timeout=30000)
                )
        else:
            self.fallback_client = None

        if not self.client and not self.fallback_client:
            return False
        
        # Warm up Pydantic schemas in the main thread to prevent deadlocks in background threads on Windows
        try:
            _ = types.GenerateContentConfig(
                temperature=0.3,
                system_instruction="warmup",
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
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
        model_name: str = "gemini-3.5-flash-lite",
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
        
        # Explicitly configure thinking_level = MINIMAL to optimize low-latency responses
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
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
                    res_text = response.text.strip()
                    if detect_repetition(res_text):
                        raise RepetitionDetectedError("Обнаружено зацикливание!")
                    return res_text
                return ""
            except RepetitionDetectedError:
                raise
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
                    res_text = response.text.strip()
                    if detect_repetition(res_text):
                        raise RepetitionDetectedError("Обнаружено зацикливание!")
                    return res_text
                return ""
            except RepetitionDetectedError:
                raise
            except Exception as e:
                print(f"[Gemini] Fallback channel failed: {e}", file=sys.stderr)
                last_exception = e

        # If we reached here, all attempted clients failed
        if last_exception:
            raise last_exception
        
        return ""
