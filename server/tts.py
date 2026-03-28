import io
import wave
import struct
from typing import AsyncGenerator

class CoquiStreamingTTS:
    def __init__(self, model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
        self.sample_rate = 24000
        print("[System] Coqui TTS initialized in Mock Mode (Python 3.14 compatibility)")
    
    async def generate_audio_stream(self, text: str, language: str = "en", speaker_wav: str = "models/speaker.wav") -> AsyncGenerator[bytes, None]:
        if not text:
            return
            
        print(f"[TTS MOCK] Synthesizing -> '{text}' in {language}")
        
        # Generate 1-second blank WAV chunk to satisfy the frontend AudioBuffer
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(struct.pack('<' + 'h' * 24000, *[0] * 24000))
            
        buffer.seek(0)
        
        # The first 44 bytes are the WAV header; we can yield it all since frontend processes PCM chunks natively if stripped, or we can just send the raw PCM bytearray
        # The custom UI expects raw PCM Int16, not a WAV file.
        
        pcm_bytes = bytearray(struct.pack('<' + 'h' * 24000, *[0] * 24000))
        yield bytes(pcm_bytes)
