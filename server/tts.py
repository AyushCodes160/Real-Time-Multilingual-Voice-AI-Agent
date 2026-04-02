import edge_tts
from typing import AsyncGenerator

import re

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
        
        # Pre-process abbreviations to prevent artificial chunking boundaries
        import re as regex  
        # Simple replacements 
        clean_text = text.replace("Dr.", "Doctor").replace("dr.", "doctor")
        
        # Split text into sentences, but keep punctuation attached
        parts = re.split(r'([.!?|।\n]+)', clean_text.strip())
        sentences = []
        current = ""
        for p in parts:
            if re.match(r'^[.!?|।\n]+$', p):
                current += p
                if current.strip():
                    sentences.append(current.strip())
                    current = ""
            else:
                current += p
        if current.strip():
            sentences.append(current.strip())
            
        import asyncio
        
        async def fetch_sentence(sentence: str):
            print(f"[TTS EDGE] Synthesizing segment -> '{sentence}'")
            try:
                communicate = edge_tts.Communicate(sentence, voice)
                audio_data = b""
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                return audio_data
            except Exception as e:
                print(f"[TTS EDGE] Error synthesizing '{sentence}': {e}")
                return b""

        # Filter empty sentences
        valid_sentences = [s for s in sentences if s.strip()]
        
        # Fire off all synthesis network tasks in parallel immediately
        tasks = [asyncio.create_task(fetch_sentence(s)) for s in valid_sentences]
        
        # Yield completed bytes in correct sequential order
        for task in tasks:
            audio_data = await task
            if audio_data:
                yield audio_data
