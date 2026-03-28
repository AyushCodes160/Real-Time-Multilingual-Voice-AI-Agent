from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from server.models.db import Appointment, Slot
from server.agent.memory import set_campaign_flag

def check_upcoming_appointments():
    print("[CAMPAIGN_WORKER] Scanning database for upcoming appointments...")
    from server.main import SessionLocal 
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        tomorrow_start = now + timedelta(days=1)
        tomorrow_end = tomorrow_start + timedelta(days=1)
        
        upcoming = session.query(Appointment).join(Slot).filter(
            Slot.start_time >= tomorrow_start,
            Slot.start_time < tomorrow_end
        ).all()
        
        for appt in upcoming:
            context_prompt = f"OUTBOUND CAMPAIGN TRIGGER: The user has an appointment scheduled with Dr. {appt.doctor.name} tomorrow at {appt.slot.start_time.isoformat()}. Your ONLY goal right now is to proactively greet them and ask: do you want to keep or reschedule this appointment? You must speak to them first."
            set_campaign_flag(str(appt.patient_id), context_prompt)
            print(f"[CAMPAIGN_WORKER] Queued outbound call for Patient {appt.patient_id}")
            
    except Exception as e:
        print(f"[CAMPAIGN_WORKER] Error: {e}")
    finally:
        session.close()

def start_campaign_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_upcoming_appointments, 'interval', minutes=1)
    scheduler.start()
    print("[System] Background Campaign Scheduler started.")
