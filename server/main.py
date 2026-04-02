import asyncio
import json
from dotenv import load_dotenv
load_dotenv()  # Load GROQ_API_KEY and other env vars from .env file
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.agent.orchestrator import process_user_input
from server.stt import VoskStreamingSTT
from server.tts import CoquiStreamingTTS
from server.barge_in import BargeInController
from server.models.db import Base
from server.api import router as api_router
from server.latency import LatencyTracker
from server.models.db import Patient
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

from server.models.db import engine, SessionLocal, Base
Base.metadata.create_all(bind=engine)

# Only initialize models that exist on disk
VOSK_MODELS = {}
for lang, path in {"en": "models/vosk-en", "hi": "models/vosk-hi", "ta": "models/vosk-ta"}.items():
    if os.path.exists(path):
        VOSK_MODELS[lang] = path
    else:
        print(f"[BOOT] Skip missing Vosk model for {lang}: {path}")

stt_engine = VoskStreamingSTT(VOSK_MODELS)
tts_engine = CoquiStreamingTTS()

@app.on_event("startup")
def startup_event():
    from server.campaign import start_campaign_scheduler
    start_campaign_scheduler()

@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    db_session = SessionLocal()

    config_msg = await websocket.receive_text()
    config = json.loads(config_msg)
    
    patient_id = config.get("patient_id")
    patient_name = (config.get("patient_name") or "").strip()
    patient_phone = (config.get("patient_phone") or "").strip()

    # Resolve patient from config payload. Fallback keeps demo compatibility.
    if not patient_id:
        patient = None
        if patient_phone:
            patient = db_session.query(Patient).filter(Patient.phone == patient_phone).first()
        if not patient and patient_name and patient_phone:
            patient = Patient(name=patient_name, phone=patient_phone)
            db_session.add(patient)
            db_session.commit()
            db_session.refresh(patient)
        patient_id = patient.id if patient else 1

    patient_id = int(patient_id)

    transcript_buffer = ""
    language = config.get("language", "en")
    
    barge_in = BargeInController()
    tracker = LatencyTracker()
    
    recognizer = stt_engine.create_recognizer(language)

    if patient_name:
        from server.agent.memory import update_session_data
        update_session_data(patient_id, {"patient_name": patient_name, "patient_name_snapshot": patient_name})
    
    await websocket.send_json({"type": "config_ack", "language": language})
    
    # [CAMPAIGN MODE CHECK] - Proactive Outbound Call Processing
    from server.agent.memory import get_campaign_flag, clear_campaign_flag
    campaign_prompt = get_campaign_flag(str(patient_id))
    if campaign_prompt:
        print(f"[SYSTEM] Outbound Campaign Triggered for Patient {patient_id}")
        clear_campaign_flag(str(patient_id))
        
        barge_in.reset()
        tracker.start("LLM_TOOL")
        response_text, llm_response = await process_user_input(db_session, patient_id, campaign_prompt, language)
        tracker.stop("LLM_TOOL")
        
        barge_in.set_speaking(True)
        await websocket.send_json({
            "type": "response", 
            "text": response_text,
            "state": "OUTBOUND_CALL", 
            "latency": tracker.log_pipeline(),
            "reasoning": llm_response
        })
        
        tracker.start("TTS")
        try:
            async for audio_chunk in tts_engine.generate_audio_stream(response_text, language=language):
                await websocket.send_bytes(audio_chunk)
                await asyncio.sleep(0.001)
        except Exception as e:
            print(f"TTS Error on Outbound {e}")
        tracker.stop("TTS")
        barge_in.set_speaking(False)
        await websocket.send_json({"type": "audio_end", "tts_latency_ms": tracker.metrics.get("TTS", 0)})
    
    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                data = message["bytes"]
                
                if barge_in._is_speaking:
                    barge_in.register_user_speech()
                
                tracker.start("STT")
                stt_result = stt_engine.process_audio_chunk(recognizer, data)
                tracker.stop("STT")
                
                if stt_result["type"] == "partial":
                    display_text = transcript_buffer + " " + stt_result["text"]
                    await websocket.send_json({"type": "partial", "text": display_text.strip()})
                    
                elif stt_result["type"] == "final":
                    text = stt_result["text"]
                    if text.strip() and text != "[Vosk model not downloaded yet]":
                        transcript_buffer += text + " "
                        await websocket.send_json({"type": "partial", "text": transcript_buffer.strip()})
                        barge_in.reset()
                    
            elif "text" in message:
                data = json.loads(message["text"])
                if data.get("type") == "config":
                    language = data.get("language", language)
                    recognizer = stt_engine.create_recognizer(language)
                    await websocket.send_json({"type": "config_ack", "language": language})
                    
                elif data.get("type") == "clear_buffer":
                    transcript_buffer = ""
                    from server.agent.memory import clear_session_data, update_state
                    clear_session_data(patient_id)
                    update_state(patient_id, "IDLE", None)
                    await websocket.send_json({"type": "partial", "text": ""})
                    
                elif data.get("type") == "send_message":
                    frontend_text = data.get("text", "").strip()
                    final_text = frontend_text if frontend_text else transcript_buffer.strip()
                    
                    if not final_text:
                        continue
                        
                    transcript_buffer = ""
                    
                    if final_text.startswith("[EN] ") or final_text.startswith("[HI] ") or final_text.startswith("[TA] "):
                        final_text = final_text[5:]
                        
                    await websocket.send_json({"type": "transcript", "text": final_text})
                    
                    barge_in.reset()
                    
                    # ── AUTO-DETECT LANGUAGE ─────────────────────────────────
                    detected_lang = language  # fallback to user selection
                    try:
                        from langdetect import detect
                        _iso = detect(final_text)
                        _map = {"hi": "hi", "ta": "ta", "en": "en"}
                        if _iso in _map and _iso != language:
                            detected_lang = _map[_iso]
                            language = detected_lang
                            recognizer = stt_engine.create_recognizer(language)
                            await websocket.send_json({"type": "config_ack", "language": language})
                    except Exception:
                        pass  # langdetect failed, keep user preference
                    # ─────────────────────────────────────────────────────────
                    
                    tracker.start("LLM_TOOL")
                    response_text, llm_response = await process_user_input(db_session, patient_id, final_text, detected_lang)
                    tracker.stop("LLM_TOOL")
                    
                    barge_in.set_speaking(True)
                    
                    await websocket.send_json({
                        "type": "response", 
                        "text": response_text,
                        "state": "ACTIVE", 
                        "latency": tracker.log_pipeline(),
                        "reasoning": llm_response
                    })
                    
                    tracker.start("TTS")
                    async for audio_chunk in tts_engine.generate_audio_stream(response_text, language=detected_lang):
                        if barge_in.check_interrupted():
                            await websocket.send_json({"type": "barge_in"})
                            break
                        
                        await websocket.send_bytes(audio_chunk)
                        await asyncio.sleep(0.001)
                    tracker.stop("TTS")
                        
                    barge_in.set_speaking(False)
                    await websocket.send_json({"type": "audio_end", "tts_latency_ms": tracker.metrics.get("TTS", 0)})
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[CRITICAL SOCKET ERROR] {e}")
    finally:
        db_session.close()

# Robust mount for both Local Dev and Docker/HuggingFace (MUST BE LAST)
STATIC_DIR = "server/static" if os.path.exists("server/static") else "static"
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
