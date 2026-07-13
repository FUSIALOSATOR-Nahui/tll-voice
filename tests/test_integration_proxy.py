import unittest
import sys
import io
import wave
import numpy as np
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.config import load_config
from core.gemini import GeminiClient

class TestIntegrationProxy(unittest.TestCase):

    def test_end_to_end_transcription_with_failover(self):
        # Load the configuration from config.json & .env
        config = load_config()
        
        client = GeminiClient()
        
        # Read keys & hosts
        import os
        api_key = config.get("api_key", "")
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            api_key = os.environ.get("GEMINI_API_KEY", "")
            
        api_host = config.get("api_host", "")
        if not api_host:
            api_host = os.environ.get("GEMINI_API_HOST", "")
        
        fallback_key = config.get("fallback_api_key", "")
        if not fallback_key:
            fallback_key = os.environ.get("GEMINI_FALLBACK_API_KEY", "")
            
        fallback_host = config.get("fallback_api_host", "")
        if not fallback_host:
            fallback_host = os.environ.get("GEMINI_FALLBACK_API_HOST", "")
        
        print(f"Integration config - Primary: host={api_host}, key_len={len(api_key) if api_key else 0}")
        print(f"Integration config - Fallback: host={fallback_host}, key_len={len(fallback_key) if fallback_key else 0}")
        
        configured = client.configure(
            api_key=api_key,
            api_host=api_host or None,
            fallback_key=fallback_key or None,
            fallback_host=fallback_host or None
        )
        self.assertTrue(configured)
        self.assertTrue(client.is_configured)
        self.assertIsNotNone(client.client)
        self.assertIsNotNone(client.fallback_client)
        
        # Generate dummy 1 second WAV audio
        sample_rate = 16000
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        audio_data = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.tobytes())
        wav_bytes = wav_io.getvalue()
        
        # --- Run 1: Test Primary Direct Channel ---
        print("\n[Run 1] Sending transcription request through primary direct client...")
        try:
            text = client.transcribe(
                wav_bytes=wav_bytes,
                system_instruction="Ты — голосовой ассистент, опиши звук.",
                prompt="If it's a sine wave, return 'SINE_WAVE_DETECTED'."
            )
            print(f"[Run 1] Response: {text}")
        except Exception as e:
            print(f"[Run 1] Primary channel call failed: {e}")
        
        # --- Run 2: Test Force Fallback ---
        print("\n[Run 2] Forcing primary channel failure to test automatic fallback...")
        from google import genai
        client.client = genai.Client(api_key="completely_invalid_key_to_force_failure")
        
        try:
            text = client.transcribe(
                wav_bytes=wav_bytes,
                system_instruction="Ты — голосовой ассистент, опиши звук.",
                prompt="If it's a sine wave, return 'SINE_WAVE_DETECTED'."
            )
            print(f"[Run 2] Fallback Response: {text}")
            self.assertIn("SINE_WAVE_DETECTED", text.upper())
            print("[Run 2] Fallback worked successfully!")
        except Exception as e:
            self.fail(f"Resilient fallback failed: {e}")

if __name__ == "__main__":
    unittest.main()
