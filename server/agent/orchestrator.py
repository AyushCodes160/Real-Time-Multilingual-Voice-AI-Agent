import json
import re
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from server.agent.memory import (
    get_state,
    update_state,
    get_session_data,
    update_session_data,
    clear_session_data
)
from server.agent.prompts import EXTRACTION_PROMPT
from server.agent.llm_caller import call_llm
from server.agent.tools import (
    book_slot,
    cancel_slot,
    reschedule_slot,
    get_patient_history,
    get_doctor_by_name
)

# ─── Hardcoded field-specific questions ──────────────────────────────────────
FIELD_QUESTIONS = {
    "patient_name": "What's your name?",
    "doctor_name":  "Which doctor would you like to see?",
    "date":         "What date would you like the appointment?",
    "time":         "What time would you like the appointment?",
}

# Keywords that mean "yes, proceed, book it"
CONFIRMATION_WORDS = {"yes", "yep", "yeah", "correct", "book", "confirm", "proceed",
                      "okay", "ok", "sure", "go ahead", "do it", "right", "perfect"}

CANCEL_KEYWORDS = {"cancel", "remove", "delete"}
RESCHEDULE_KEYWORDS = {"reschedule", "change", "move", "modify", "update", "shift"}

def _is_confirmation(text: str) -> bool:
    words = set(text.lower().split())
    return bool(words & CONFIRMATION_WORDS)

def _detect_intent(text: str) -> str:
    """Detect user intent from text. Returns 'cancel', 'reschedule', 'history', 'greeting', or 'book'."""
    lowered = text.lower()
    if any(kw in lowered for kw in CANCEL_KEYWORDS) and "book" not in lowered:
        return "cancel"
    if any(kw in lowered for kw in RESCHEDULE_KEYWORDS):
        return "reschedule"
    # "history" / check upcoming
    history_phrases = {"my appointment", "upcoming", "scheduled", "when is", "what are"}
    if any(kw in lowered for kw in history_phrases) and "book" not in lowered and "cancel" not in lowered:
        return "history"
    # Generic greetings
    greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}
    if lowered.strip().rstrip("!.,") in greetings:
        return "greeting"
    return "book"

def _friendly_dt(iso_str: str) -> str:
    """Convert ISO datetime string to friendly format."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%A, %d %B %Y at %I:%M %p").lstrip("0")
    except Exception:
        return iso_str

def _clean_dr_name(name: str) -> str:
    """Title-case and deduplicate doctor name."""
    words = name.title().split()
    seen, unique = set(), []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            unique.append(w)
    return " ".join(unique)


def _mentions_doctor(text: str) -> bool:
    lowered = text.lower()
    return "doctor" in lowered or "dr " in lowered or "dr." in lowered


def _mentions_name(text: str) -> bool:
    lowered = text.lower()
    return "my name" in lowered or "i am" in lowered or "i'm" in lowered


async def _extract_entities(user_input: str, session_data: dict) -> dict:
    """Call the LLM purely for entity extraction. Returns a safe dict."""
    extracted = {}

    # Deterministic fallback for common phrases like
    # "doctor michelle" / "dr michelle" and "my name is ayush".
    lower = user_input.lower().strip()

    doctor_match = re.search(r"(?:\bdoctor\b|\bdr\.?\b)\s+([a-z][a-z\s'-]{1,40})", lower, flags=re.IGNORECASE)
    if doctor_match:
        doctor_raw = doctor_match.group(1).strip(" .,!?:;")
        if doctor_raw:
            extracted["doctor_name"] = _clean_dr_name(doctor_raw)

    name_match = re.search(r"\b(?:my name is|i am|i'm)\s+([a-z][a-z\s'-]{1,40})", lower, flags=re.IGNORECASE)
    if name_match:
        patient_raw = name_match.group(1).strip(" .,!?:;")
        if patient_raw:
            extracted["patient_name"] = " ".join(w.capitalize() for w in patient_raw.split())

    prompt = EXTRACTION_PROMPT.format(
        session_data=json.dumps(session_data, indent=2),
        user_input=user_input
    )
    result = await call_llm(prompt)

    for key in ["doctor_name", "patient_name", "date", "time"]:
        val = result.get(key) or result.get("extracted_info", {}).get(key)
        if val and str(val).lower() not in ("null", "none", ""):
            extracted[key] = val
    return extracted


def _to_iso(date_str: str, time_str: str) -> str:
    """Convert any natural-language date + HH:MM time to ISO datetime."""
    import re

    # Strategy 1: Parse "date time" together via dateparser
    try:
        import dateparser
        combined = f"{date_str} {time_str}"
        parsed = dateparser.parse(combined, settings={"PREFER_DATES_FROM": "future"})
        if parsed:
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass

    # Strategy 2: Parse just the date via dateparser, append time
    try:
        import dateparser
        parsed = dateparser.parse(date_str, settings={"PREFER_DATES_FROM": "future"})
        if parsed:
            return f"{parsed.strftime('%Y-%m-%d')}T{time_str}:00"
    except Exception:
        pass

    # Strategy 3: Manual regex — handles "31 march", "march 31", etc.
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12
    }
    s = date_str.strip().lower()
    m = re.search(r'(\d{1,2})\s+([a-z]+)', s) or re.search(r'([a-z]+)\s+(\d{1,2})', s)
    if m:
        try:
            g = m.groups()
            if g[0].isdigit():
                day, mon_str = int(g[0]), g[1][:3]
            else:
                mon_str, day = g[0][:3], int(g[1])
            month = month_map.get(mon_str)
            if month:
                now = datetime.now()
                year = now.year
                candidate = datetime(year, month, day)
                if candidate < now:
                    candidate = datetime(year + 1, month, day)
                return f"{candidate.strftime('%Y-%m-%d')}T{time_str}:00"
        except Exception:
            pass

    raise ValueError(f"Cannot parse date: {date_str!r}")



async def _translate_response(text: str, language_code: str) -> str:
    if language_code == "en":
        return text
    prompt = f"""You are an expert medical translator. Translate the following text accurately and politely into the ISO 639-1 language '{language_code}'.
Return ONLY a valid JSON object with the key "translation". No markdown, no extra text.
Text to translate: "{text}"

{{
  "translation": "<translated text here>"
}}"""
    try:
        result = await call_llm(prompt)
        translated = result.get("translation")
        if translated:
            return translated
    except Exception:
        pass
    return text

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
async def process_user_input(
    session: Session,
    patient_id: int,
    user_input: str,
    detected_language: str = "en"
) -> Tuple[str, Dict[str, Any]]:

    session_data = get_session_data(patient_id)
    state_data   = get_state(patient_id)

    # Recover sticky values if the active session dict ever drops fields.
    sticky_updates = {}
    if not session_data.get("doctor_name") and session_data.get("doctor_name_snapshot"):
        sticky_updates["doctor_name"] = session_data["doctor_name_snapshot"]
    if not session_data.get("patient_name") and session_data.get("patient_name_snapshot"):
        sticky_updates["patient_name"] = session_data["patient_name_snapshot"]
    if sticky_updates:
        update_session_data(patient_id, sticky_updates)
        session_data = get_session_data(patient_id)

    async def finish(resp: str, data: dict, state: str) -> Tuple[str, Dict[str, Any]]:
        final_resp = await _translate_response(resp, detected_language)
        update_state(patient_id, state, {"user": user_input, "agent": final_resp}, detected_language)
        return final_resp, data


    # ── RESUME PENDING RESCHEDULE (multi-turn) ────────────────────────────────
    # If we previously asked for a new date/time during a reschedule, the user's
    # reply won't contain reschedule keywords — so check session state first.
    if session_data.get("reschedule_appt_id"):
        extracted = await _extract_entities(user_input, session_data)
        new_date = extracted.get("date")
        new_time = extracted.get("time")

        if not new_date:
            response = "Please tell me the new date for the appointment, like '1 April'."
            return await finish(response, {}, 'RESCHEDULING')

        if not new_time:
            new_time = "09:00"  # default

        appt_id = session_data["reschedule_appt_id"]
        dr_name_raw = session_data.get("doctor_name", "")

        # Look up the old appointment to get doctor_id
        records = get_patient_history(session, patient_id)
        old_appt = next((r for r in records if r["appointment_id"] == appt_id), None)
        if not old_appt:
            clear_session_data(patient_id)
            response = "That appointment no longer exists. Is there anything else I can help with?"
            return await finish(response, {}, 'IDLE')

        old_doctor_id = old_appt["doctor_id"]
        cancel_result = cancel_slot(session, appt_id)

        try:
            date_val = _to_iso(new_date, new_time)
        except ValueError:
            response = f"I couldn't understand the date '{new_date}'. Please say it like '1 April'."
            return await finish(response, {}, 'IDLE')

        book_result = book_slot(session, int(patient_id), int(old_doctor_id), slot_id=None, date_str=date_val, reason="Rescheduled Booking")
        clear_session_data(patient_id)

        if book_result.get("success"):
            dr = _clean_dr_name(book_result.get("doctor", dr_name_raw))
            response = f"Done! Your appointment with Dr. {dr} has been rescheduled to {_friendly_dt(date_val)}."
            return await finish(response, {"booking": book_result, "cancelled": True}, 'IDLE')
        else:
            response = f"I couldn't reschedule: {book_result.get('error', 'Unknown error')}"
            return await finish(response, {"error": book_result.get("error")}, 'IDLE')

    intent = _detect_intent(user_input)

    # ── GREETING ──────────────────────────────────────────────────────────────
    if intent == "greeting":
        response = "Hello! How can I help you today? I can book, cancel, or reschedule appointments."
        return await finish(response, {}, 'IDLE')

    # ── HISTORY ───────────────────────────────────────────────────────────────
    if intent == "history":
        records = get_patient_history(session, patient_id)
        if not records:
            response = "You have no appointments booked yet."
        else:
            lines = []
            for r in records:
                dr = _clean_dr_name(r.get("doctor_name", "Unknown"))
                dt = _friendly_dt(r.get("date", ""))
                lines.append(f"Appointment #{r['appointment_id']} with Dr. {dr} on {dt}")
            response = "Here are your appointments: " + "; ".join(lines)
        return await finish(response, {}, 'IDLE')

    # ── CANCEL ────────────────────────────────────────────────────────────────
    if intent == "cancel":
        records = get_patient_history(session, patient_id)
        if not records:
            response = "You don't have any appointments to cancel."
            return await finish(response, {}, 'IDLE')

        # Try to find which appointment the user wants to cancel
        # Extract doctor name from user input via LLM
        extracted = await _extract_entities(user_input, session_data)
        target_doctor = extracted.get("doctor_name", "").lower()

        # Try matching by doctor name
        matched = None
        if target_doctor:
            for r in records:
                if target_doctor in r.get("doctor_name", "").lower():
                    matched = r
                    break

        # If only one appointment, cancel it directly
        if not matched and len(records) == 1:
            matched = records[0]

        if matched:
            result = cancel_slot(session, matched["appointment_id"])
            if result.get("success"):
                dr = _clean_dr_name(result.get("doctor", matched.get("doctor_name", "")))
                response = f"Done! Your appointment with Dr. {dr} has been cancelled."
                return await finish(response, {"cancelled": True}, 'IDLE')
            else:
                response = f"I couldn't cancel the appointment: {result.get('error', 'Unknown error')}"
                return await finish(response, {}, 'IDLE')
        else:
            # Multiple appointments, can't determine which one
            lines = []
            for r in records:
                dr = _clean_dr_name(r.get("doctor_name", "Unknown"))
                dt = _friendly_dt(r.get("date", ""))
                lines.append(f"#{r['appointment_id']} with Dr. {dr} on {dt}")
            response = "Which appointment would you like to cancel? " + "; ".join(lines)
            return await finish(response, {}, 'IDLE')

    # ── RESCHEDULE ────────────────────────────────────────────────────────────
    if intent == "reschedule":
        records = get_patient_history(session, patient_id)
        if not records:
            response = "You don't have any appointments to reschedule."
            return await finish(response, {}, 'IDLE')

        # Extract entities from user input
        extracted = await _extract_entities(user_input, session_data)
        target_doctor = extracted.get("doctor_name", "").lower()
        new_date = extracted.get("date")
        new_time = extracted.get("time")

        # Find the matching appointment
        matched = None
        if target_doctor:
            for r in records:
                if target_doctor in r.get("doctor_name", "").lower():
                    matched = r
                    break
        if not matched and len(records) == 1:
            matched = records[0]

        if not matched:
            lines = []
            for r in records:
                dr = _clean_dr_name(r.get("doctor_name", "Unknown"))
                dt = _friendly_dt(r.get("date", ""))
                lines.append(f"#{r['appointment_id']} with Dr. {dr} on {dt}")
            response = "Which appointment would you like to reschedule? " + "; ".join(lines)
            return await finish(response, {}, 'IDLE')

        # We have a match, now we need the new date/time
        if not new_date:
            response = f"What new date would you like for your appointment with Dr. {_clean_dr_name(matched.get('doctor_name', ''))}?"
            update_session_data(patient_id, {"reschedule_appt_id": matched["appointment_id"], "doctor_name": matched.get("doctor_name", "")})
            return await finish(response, {}, 'RESCHEDULING')
        if not new_time:
            # Default to same time as original
            try:
                orig_dt = datetime.fromisoformat(matched["date"])
                new_time = orig_dt.strftime("%H:%M")
            except Exception:
                new_time = "09:00"

        # Cancel old appointment and book new one
        old_doctor_id = matched.get("doctor_id")
        cancel_result = cancel_slot(session, matched["appointment_id"])

        try:
            date_val = _to_iso(new_date, new_time)
        except ValueError:
            response = f"I couldn't understand the new date '{new_date}'. Please say it like '1 April'."
            return await finish(response, {}, 'IDLE')

        book_result = book_slot(session, int(patient_id), int(old_doctor_id), slot_id=None, date_str=date_val, reason="Rescheduled Booking")

        if book_result.get("success"):
            dr = _clean_dr_name(book_result.get("doctor", matched.get("doctor_name", "")))
            response = f"Done! Your appointment with Dr. {dr} has been rescheduled to {_friendly_dt(date_val)}."
            return await finish(response, {"booking": book_result, "cancelled": True}, 'IDLE')
        else:
            response = f"I couldn't reschedule: {book_result.get('error', 'Unknown error')}"
            return await finish(response, {"error": book_result.get("error")}, 'IDLE')

    # ── BOOKING (default intent) ──────────────────────────────────────────────
    # Extract entities from user message
    extracted = await _extract_entities(user_input, session_data)

    # Merge into session
    updates = {}
    extracted_doctor = extracted.get("doctor_name")
    extracted_patient = extracted.get("patient_name")

    # Keep previously captured doctor unless the user explicitly mentions a doctor.
    if extracted_doctor:
        if not session_data.get("doctor_name") or _mentions_doctor(user_input):
            updates["doctor_name"] = extracted_doctor
            updates["doctor_name_snapshot"] = extracted_doctor

    # Keep patient name stable unless user explicitly provides/changes it.
    if extracted_patient:
        if not session_data.get("patient_name") or _mentions_name(user_input):
            updates["patient_name"] = extracted_patient
            updates["patient_name_snapshot"] = extracted_patient

    for key in ["date", "time"]:
        if extracted.get(key):
            updates[key] = extracted[key]

    # Maintain sticky snapshots when no explicit update came in this turn.
    if session_data.get("doctor_name") and not updates.get("doctor_name_snapshot"):
        updates["doctor_name_snapshot"] = session_data["doctor_name"]
    if session_data.get("patient_name") and not updates.get("patient_name_snapshot"):
        updates["patient_name_snapshot"] = session_data["patient_name"]

    if updates:
        update_session_data(patient_id, updates)
        session_data = get_session_data(patient_id)

    # Check missing fields
    required = ["patient_name", "doctor_name", "date", "time"]
    missing = [f for f in required if not session_data.get(f)]

    # If something missing AND not a pure confirmation → ask for next field
    if missing and not _is_confirmation(user_input):
        next_field = missing[0]
        collected = {k: session_data[k] for k in required if session_data.get(k)}
        if collected:
            summary = ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in collected.items())
            response = f"Got it. I have: {summary}. {FIELD_QUESTIONS[next_field]}"
        else:
            response = FIELD_QUESTIONS[next_field]
        return await finish(response, {"extracted_info": extracted}, 'BOOKING')

    # If user said confirm but fields missing → ask
    if missing and _is_confirmation(user_input):
        next_field = missing[0]
        response = FIELD_QUESTIONS[next_field]
        return await finish(response, {}, 'BOOKING')

    # ── All 4 fields present — BOOK IT! ──────────────────────────────────────
    if not session_data.get("doctor_id"):
        dr_result = get_doctor_by_name(session, session_data["doctor_name"])
        if not dr_result.get("success"):
            response = f"Sorry, I couldn't find a doctor named {session_data['doctor_name']}. Could you check the name?"
            return await finish(response, {}, 'IDLE')
        update_session_data(patient_id, {"doctor_id": dr_result["doctor_id"], "doctor_name": dr_result["name"]})
        session_data = get_session_data(patient_id)

    date_val = session_data["date"]
    time_val = session_data["time"]

    try:
        date_val = _to_iso(date_val, time_val)
    except ValueError:
        response = f"I couldn't understand the date '{session_data['date']}'. Could you say it again like '31 March'?"
        update_state(patient_id, "BOOKING", {"user": user_input, "agent": response}, detected_language)
        update_session_data(patient_id, {"date": None})
        return response, {}

    result = book_slot(session, int(patient_id), int(session_data["doctor_id"]), slot_id=None, date_str=date_val, reason="Voice Booking")

    if result.get("success"):
        clear_session_data(patient_id)
        dr_name = _clean_dr_name(result.get("doctor", session_data.get("doctor_name", "")))
        patient_name = session_data.get("patient_name", "").title()
        response = (
            f"All done, {patient_name}! Your appointment with Dr. {dr_name} is confirmed "
            f"for {_friendly_dt(date_val)}. See you then!"
        )
        return await finish(response, {"booking": result}, 'IDLE')
    else:
        error = result.get("error", "Unknown error")
        response = f"I couldn't book the appointment. {error} Please try again."
        return await finish(response, {"error": error}, 'BOOKING')
