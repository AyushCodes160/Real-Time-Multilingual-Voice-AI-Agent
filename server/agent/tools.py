from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict, Any
from server.models.db import Slot, Appointment, AppointmentStatus, Doctor

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

def book_slot(session: Session, patient_id: int, doctor_id: int, slot_id: int = None, date_str: str = None, reason: str = "") -> Dict[str, Any]:
    from datetime import timedelta
    
    if not slot_id and date_str:
        # Auto-create a slot on the fly for the demo
        try:
            start_time = datetime.fromisoformat(date_str)
            end_time = start_time + timedelta(minutes=30)
            slot = Slot(doctor_id=doctor_id, start_time=start_time, end_time=end_time, is_available=False)
            session.add(slot)
            session.flush()
            slot_id = slot.id
        except Exception as e:
            return {"success": False, "error": f"Invalid date format: {e}"}
            
    slot = session.query(Slot).filter(Slot.id == slot_id).first()
    if not slot:
        return {"success": False, "error": "Slot not found"}
        
    slot.is_available = False
    
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_id=slot.id,
        status=AppointmentStatus.SCHEDULED,
        reason=reason
    )
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    
    return {"success": True, "appointment_id": appointment.id, "doctor": slot.doctor.name, "time": slot.start_time.isoformat()}

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

def get_doctor_by_name(session: Session, name: str) -> Dict[str, Any]:
    doctor = session.query(Doctor).filter(Doctor.name.ilike(f"%{name}%")).first()
    if not doctor:
        # Zero-friction: Create the doctor if it doesn't exist for the demo
        doctor = Doctor(name=name, specialty="Medical Specialist")
        session.add(doctor)
        session.commit()
        session.refresh(doctor)
        
    return {
        "success": True,
        "doctor_id": doctor.id,
        "name": doctor.name,
        "specialty": doctor.specialty
    }
