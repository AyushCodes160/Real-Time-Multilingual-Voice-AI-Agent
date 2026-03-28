import edge_tts
from typing import AsyncGenerator

class CoquiStreamingTTS:
    def __init__(self, model_name: str = "edge-tts"):
        print("[System] Switched TTS from Mock to Edge-TTS")
    
    async def generate_audio_stream(self, text: str, language: str = "en", speaker_wav: str = "") -> AsyncGenerator[bytes, None]:
        if not text:
            return
            
        voices = {
            "en": "en-US-AriaNeural",
            "hi": "hi-IN-SwaraNeural",
            "ta": "ta-IN-PallaviNeural"
        }
        voice = voices.get(language, "en-US-AriaNeural")
        print(f"[TTS EDGE] Synthesizing -> '{text}' in {language} with {voice}")
        
        communicate = edge_tts.Communicate(text, voice)
        
        # We collect the full MP3 stream in memory so the frontend can decode a complete valid MP3 header
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
                
        if audio_data:
            yield audio_data
