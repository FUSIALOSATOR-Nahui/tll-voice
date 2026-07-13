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

    def test_real_transcription_via_proxy(self):
        # Load the configuration from config.json & .env
        config = load_config()
        
        # Initialize GeminiClient
        client = GeminiClient()
        
        # Read API key & host
        import os
        api_key = config.get("api_key", "")
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            api_key = os.environ.get("GEMINI_API_KEY", "")
        api_host = config.get("api_host", "")
        if not api_host:
            api_host = os.environ.get("GEMINI_API_HOST", "")
            
        print(f"Loaded integration config: api_host={api_host}, key_len={len(api_key) if api_key else 0}")
        
        # Configure client
        configured = client.configure(api_key, api_host=api_host or None)
        self.assertTrue(configured)
        self.assertTrue(client.is_configured)
        
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
        
        # Transcribe
        print("Sending transcription request through integration client...")
        try:
            text = client.transcribe(
                wav_bytes=wav_bytes,
                system_instruction="Ты — голосовой ассистент, опиши звук.",
                prompt="If it's a sine wave, return 'SINE_WAVE_DETECTED'."
            )
            print(f"Integration response: {text}")
            self.assertIn("SINE_WAVE_DETECTED", text.upper())
        except Exception as e:
            self.fail(f"Real API request via proxy failed: {e}")

if __name__ == "__main__":
    unittest.main()
