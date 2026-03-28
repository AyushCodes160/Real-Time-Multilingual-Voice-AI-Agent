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
