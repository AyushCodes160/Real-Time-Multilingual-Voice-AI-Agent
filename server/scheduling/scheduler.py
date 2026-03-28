from server.scheduling.worker import celery_app
from server.agent.memory import update_state
from server.models.db import SessionLocal, Appointment

@celery_app.task
def initiate_outbound_call(patient_id: str, appointment_id: int):
    db = SessionLocal()
    try:
        app = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not app:
            return "Appointment not found"
            
        update_state(patient_id, "CONFIRMING", {
            "system_event": "OUTBOUND_CALL_INITIATED",
            "context": f"Reminding about appointment on {app.slot.start_time if app.slot else 'unknown'}"
        })
        
        return "Call initiated via background worker"
    finally:
        db.close()
