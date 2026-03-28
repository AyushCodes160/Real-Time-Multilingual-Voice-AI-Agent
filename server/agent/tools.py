from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict, Any
from server.models.db import Slot, Appointment, AppointmentStatus

def check_availability(session: Session, doctor_id: int, after_date: datetime) -> List[Dict[str, Any]]:
    slots = session.query(Slot).filter(
        Slot.doctor_id == doctor_id,
        Slot.is_available == True,
        Slot.start_time >= after_date
    ).order_by(Slot.start_time).limit(10).all()
    
    return [
        {"slot_id": s.id, "start": s.start_time.isoformat(), "end": s.end_time.isoformat()}
        for s in slots
    ]

def book_slot(session: Session, patient_id: int, doctor_id: int, slot_id: int, reason: str = "") -> Dict[str, Any]:
    slot = session.query(Slot).filter(Slot.id == slot_id, Slot.is_available == True).first()
    if not slot:
        return {"success": False, "error": "Slot unavailable"}
        
    slot.is_available = False
    
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_id=slot_id,
        status=AppointmentStatus.SCHEDULED,
        reason=reason
    )
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    
    return {"success": True, "appointment_id": appointment.id}

def reschedule_slot(session: Session, appointment_id: int, new_slot_id: int) -> Dict[str, Any]:
    appointment = session.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return {"success": False, "error": "Appointment not found"}
        
    new_slot = session.query(Slot).filter(Slot.id == new_slot_id, Slot.is_available == True).first()
    if not new_slot:
        return {"success": False, "error": "New slot unavailable"}
        
    if appointment.slot:
        appointment.slot.is_available = True
        
    new_slot.is_available = False
    appointment.slot_id = new_slot_id
    appointment.doctor_id = new_slot.doctor_id 
    
    session.commit()
    return {"success": True, "appointment_id": appointment.id}

def cancel_slot(session: Session, appointment_id: int) -> Dict[str, Any]:
    appointment = session.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return {"success": False, "error": "Appointment not found"}
        
    appointment.status = AppointmentStatus.CANCELLED
    if appointment.slot:
        appointment.slot.is_available = True
        
    session.commit()
    return {"success": True, "appointment_id": appointment.id}

def get_patient_history(session: Session, patient_id: int) -> List[Dict[str, Any]]:
    history = session.query(Appointment).filter(Appointment.patient_id == patient_id).order_by(Appointment.created_at.desc()).all()
    return [
        {
            "appointment_id": a.id,
            "doctor_id": a.doctor_id,
            "status": a.status,
            "reason": a.reason,
            "date": a.slot.start_time.isoformat() if a.slot else None
        }
        for a in history
    ]
