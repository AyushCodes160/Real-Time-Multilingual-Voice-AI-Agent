from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from server.agent.memory import get_language_preference, set_language_preference
from server.models.db import Appointment, Slot
from server.models.db import SessionLocal, Patient

router = APIRouter(prefix="/api/patient")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class LanguageUpdate(BaseModel):
    language: str


class LoginRequest(BaseModel):
    name: str
    phone: str
    language: str = "en"


@router.post("/login")
async def login_or_register(data: LoginRequest, db: Session = Depends(get_db)):
    """Simple login/register using phone number for demo purposes."""
    name = data.name.strip()
    phone = data.phone.strip()
    language = (data.language or "en").strip().lower()

    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")

    patient = db.query(Patient).filter(Patient.phone == phone).first()
    if patient:
        patient.name = name
        patient.language_preference = language
    else:
        patient = Patient(name=name, phone=phone, language_preference=language)
        db.add(patient)

    db.commit()
    db.refresh(patient)

    # Keep Redis language preference in sync with login choice.
    set_language_preference(str(patient.id), language)

    return {
        "status": "success",
        "patient_id": patient.id,
        "name": patient.name,
        "phone": patient.phone,
        "language": patient.language_preference or "en",
    }

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

@router.get("/appointments")
async def get_all_appointments(patient_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    """Return appointments with doctor name and time for the live panel."""
    query = db.query(Appointment).join(Slot, Appointment.slot_id == Slot.id, isouter=True)
    if patient_id is not None:
        query = query.filter(Appointment.patient_id == patient_id)
    appts = query.all()
    return [
        {
            "id": a.id,
            "doctor": a.doctor.name if a.doctor else "Unknown",
            "date": a.slot.start_time.isoformat() if a.slot else None,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        }
        for a in reversed(appts)
    ]

@router.delete("/appointments/{appointment_id}")
async def delete_appointment(appointment_id: int, db: Session = Depends(get_db)):
    """Delete an appointment entirely from the database and free up the slot."""
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appointment:
        patient_id = appointment.patient_id
        if appointment.slot:
            appointment.slot.is_available = True
        db.delete(appointment)
        db.commit()
        
        # CLEAR LLM MEMORY
        from server.agent.memory import clear_session_data, update_state
        clear_session_data(str(patient_id))
        update_state(str(patient_id), "IDLE", None)
        
        return {"status": "success"}
    return {"status": "error", "message": "Appointment not found"}
