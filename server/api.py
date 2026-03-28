from fastapi import APIRouter
from pydantic import BaseModel
from server.agent.memory import get_language_preference, set_language_preference

router = APIRouter(prefix="/api/patient")

class LanguageUpdate(BaseModel):
    language: str

@router.get("/{patient_id}/language")
async def get_patient_language(patient_id: str):
    lang = get_language_preference(patient_id)
    return {"language": lang or "en"}

@router.post("/{patient_id}/language")
async def update_patient_language(patient_id: str, data: LanguageUpdate):
    set_language_preference(patient_id, data.language)
    return {"status": "success", "language": data.language}

@router.post("/{patient_id}/trigger-campaign")
async def trigger_manual_campaign(patient_id: str):
    """Manual trigger to place a demo outbound call in the queue for the current user."""
    from server.agent.memory import set_campaign_flag
    prompt = "SYSTEM DIRECTIVE (OUTBOUND CAMPAIGN): You are proactively calling the patient right now. Tell them they have an upcoming health checkup tomorrow. Ask them if they would like to cancel it or keep it. YOU MUST INITIATE the conversation right now."
    set_campaign_flag(patient_id, prompt)
    return {"status": "campaign_queued"}
