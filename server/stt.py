import json
import vosk

class VoskStreamingSTT:
    def __init__(self, model_paths: dict, lang_model_path: str = None):
        self.sample_rate = 16000
        self.models = {}
        for lang, path in model_paths.items():
            try:
                self.models[lang] = vosk.Model(path)
            except Exception:
                pass
                
        self.lang_model = vosk.SpkModel(lang_model_path) if lang_model_path else None
        
    def create_recognizer(self, language: str) -> vosk.KaldiRecognizer:
        model = self.models.get(language, self.models.get("en"))
        if not model:
             print(f"[STT MOCK] Vosk Model missing for {language}. Running without STT.")
             return None
             
        rec = vosk.KaldiRecognizer(model, self.sample_rate)
        if self.lang_model:
            rec.SetSpkModel(self.lang_model)
        return rec

    def process_audio_chunk(self, recognizer: vosk.KaldiRecognizer, chunk: bytes) -> dict:
        if recognizer is None:
            return {
                "type": "partial",
                "text": "[Vosk model not downloaded yet]",
                "detected_language": None
            }
            
        if recognizer.AcceptWaveform(chunk):
            res = json.loads(recognizer.Result())
            
            detected_lang = None
            if "spk" in res:
                detected_lang = self._infer_language_from_spk(res["spk"])
                
            text = res.get("text", "")
            if text:
                try:
                    from numerizer import numerize
                    text = numerize(text)
                except ImportError:
                    pass
                    
            return {
                "type": "final",
                "text": text,
                "detected_language": detected_lang
            }
        else:
            res = json.loads(recognizer.PartialResult())
            text = res.get("partial", "")
            if text:
                try:
                    from numerizer import numerize
                    text = numerize(text)
                except ImportError:
                    pass
                    
            return {
                "type": "partial",
                "text": text,
                "detected_language": None
            }
            
    def _infer_language_from_spk(self, spk_vector: list) -> str:
        return "en"
