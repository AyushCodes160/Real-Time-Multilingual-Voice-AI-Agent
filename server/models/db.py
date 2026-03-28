import datetime
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NOSHOW = "NOSHOW"

class Patient(Base):
    __tablename__ = "patients"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    language_preference = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    appointments = relationship("Appointment", back_populates="patient")

class Doctor(Base):
    __tablename__ = "doctors"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    specialty = Column(String, nullable=False)
    
    slots = relationship("Slot", back_populates="doctor")
    appointments = relationship("Appointment", back_populates="doctor")

class Slot(Base):
    __tablename__ = "slots"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    is_available = Column(Boolean, default=True)
    
    doctor = relationship("Doctor", back_populates="slots")
    appointment = relationship("Appointment", back_populates="slot", uselist=False)

class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=True)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.SCHEDULED)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
    slot = relationship("Slot", back_populates="appointment")
