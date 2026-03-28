import asyncio
import json
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

# Robust mount for both Local Dev and Docker/HuggingFace
STATIC_DIR = "server/static" if os.path.exists("server/static") else "static"
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

DATABASE_URL = "sqlite:///./clinic_db.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

stt_engine = VoskStreamingSTT({
    "en": "models/vosk-en",
    "hi": "models/vosk-hi",
    "ta": "models/vosk-ta"
})
tts_engine = CoquiStreamingTTS()

@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    config_msg = await websocket.receive_text()
    config = json.loads(config_msg)
    
    patient_id = 1 
    transcript_buffer = ""
    language = config.get("language", "en")
    
    barge_in = BargeInController()
    db_session = SessionLocal()
    tracker = LatencyTracker()
    
    recognizer = stt_engine.create_recognizer(language)
    
    await websocket.send_json({"type": "config_ack", "language": language})
    
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
                    detected_lang = language
                    
                    tracker.start("LLM_TOOL")
                    response_text = await process_user_input(db_session, patient_id, final_text, detected_lang)
                    tracker.stop("LLM_TOOL")
                    
                    barge_in.set_speaking(True)
                    
                    await websocket.send_json({
                        "type": "response", 
                        "text": response_text,
                        "state": "ACTIVE", 
                        "latency": tracker.log_pipeline()
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
