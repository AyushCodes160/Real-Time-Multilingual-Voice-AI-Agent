import json
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

def _is_confirmation(text: str) -> bool:
    words = set(text.lower().split())
    return bool(words & CONFIRMATION_WORDS)

async def _extract_entities(user_input: str, session_data: dict) -> dict:
    """Call the LLM purely for entity extraction. Returns a safe dict."""
    prompt = EXTRACTION_PROMPT.format(
        session_data=json.dumps(session_data, indent=2),
        user_input=user_input
    )
    result = await call_llm(prompt)
    # call_llm may wrap things in the orchestrator-style keys, try to get extraction directly
    # The raw JSON from the LLM should have doctor_name, patient_name, date, time keys
    extracted = {}
    for key in ["doctor_name", "patient_name", "date", "time"]:
        val = result.get(key) or result.get("extracted_info", {}).get(key)
        if val and str(val).lower() not in ("null", "none", ""):
            extracted[key] = val
    return extracted


async def process_user_input(
    session: Session,
    patient_id: int,
    user_input: str,
    detected_language: str = "en"
) -> Tuple[str, Dict[str, Any]]:

    session_data = get_session_data(patient_id)
    state_data   = get_state(patient_id)
    history      = state_data.get("history", [])

    # ── 1. Check if user is asking about their history ────────────────────────
    history_keywords = {"history", "appointment", "upcoming", "scheduled", "when is", "booked"}
    lowered = user_input.lower()
    if any(kw in lowered for kw in history_keywords) and "book" not in lowered:
        records = get_patient_history(session, patient_id)
        if not records:
            response = "You have no appointments booked yet."
        else:
            lines = [f"#{r['appointment_id']} – Dr. {r.get('doctor_id', '?')} on {r.get('date', '?')}" for r in records]
            response = "Your appointments: " + "; ".join(lines)
        update_state(patient_id, "IDLE", {"user": user_input, "agent": response}, detected_language)
        return response, {}

    # ── 2. Extract entities from user message ─────────────────────────────────
    extracted = await _extract_entities(user_input, session_data)

    # Merge into session (only overwrite if LLM found something new)
    updates = {}
    for key in ["doctor_name", "patient_name", "date", "time"]:
        if extracted.get(key):
            updates[key] = extracted[key]
    if updates:
        update_session_data(patient_id, updates)
        session_data = get_session_data(patient_id)  # fresh copy

    # ── 3. Check missing fields ───────────────────────────────────────────────
    required = ["patient_name", "doctor_name", "date", "time"]
    missing = [f for f in required if not session_data.get(f)]

    # ── 4a. If something missing AND not a pure confirmation → ask for next field
    if missing and not _is_confirmation(user_input):
        next_field = missing[0]
        # Build a context-aware reply mentioning what we HAVE
        collected = {k: session_data[k] for k in required if session_data.get(k)}
        if collected:
            summary = ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in collected.items())
            response = f"Got it. I have: {summary}. {FIELD_QUESTIONS[next_field]}"
        else:
            response = FIELD_QUESTIONS[next_field]
        update_state(patient_id, "BOOKING", {"user": user_input, "agent": response}, detected_language)
        return response, {"extracted_info": extracted}

    # ── 4b. If user said "yes/book it" but fields are still missing → ask again
    if missing and _is_confirmation(user_input):
        next_field = missing[0]
        response = FIELD_QUESTIONS[next_field]
        update_state(patient_id, "BOOKING", {"user": user_input, "agent": response}, detected_language)
        return response, {}

    # ── 5. All 4 fields present — BOOK IT! ───────────────────────────────────
    # Step A: Resolve doctor name → doctor_id (if not already done)
    if not session_data.get("doctor_id"):
        dr_result = get_doctor_by_name(session, session_data["doctor_name"])
        if not dr_result.get("success"):
            response = f"Sorry, I couldn't find a doctor named {session_data['doctor_name']}. Could you check the name?"
            update_state(patient_id, "IDLE", {"user": user_input, "agent": response}, detected_language)
            return response, {}
        update_session_data(patient_id, {"doctor_id": dr_result["doctor_id"], "doctor_name": dr_result["name"]})
        session_data = get_session_data(patient_id)

    # Step B: Parse date + time → ISO datetime string
    date_val = session_data["date"]
    time_val = session_data["time"]  # already HH:MM from extraction

    def _to_iso(date_str: str, time_str: str) -> str:
        """Convert any natural-language date + HH:MM time to ISO datetime."""
        import re
        from datetime import datetime as _dt
        
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

        # Strategy 3: Manual regex — handles "31 march", "march 31", "31/03" etc.
        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10,
            "november": 11, "december": 12
        }
        s = date_str.strip().lower()
        # Try "DD month" or "month DD"
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
                    now = _dt.now()
                    year = now.year
                    candidate = _dt(year, month, day)
                    if candidate < now:
                        candidate = _dt(year + 1, month, day)
                    return f"{candidate.strftime('%Y-%m-%d')}T{time_str}:00"
            except Exception:
                pass

        raise ValueError(f"Cannot parse date: {date_str!r}")

    try:
        date_val = _to_iso(date_val, time_val)
    except ValueError as e:
        response = f"I couldn't understand the date you provided ({session_data['date']}). Could you say it again clearly, like '31 March'?"
        update_state(patient_id, "BOOKING", {"user": user_input, "agent": response}, detected_language)
        # Clear bad date so user can re-enter
        update_session_data(patient_id, {"date": None})
        return response, {}


    # Step C: Call book_slot
    result = book_slot(
        session,
        int(patient_id),
        int(session_data["doctor_id"]),
        slot_id=None,
        date_str=date_val,
        reason="Voice Booking"
    )

    if result.get("success"):
        clear_session_data(patient_id)
        raw_time = result.get("time", date_val)
        dr_name  = result.get("doctor", session_data.get("doctor_name", ""))
        # Title-case and deduplicate repeated words (e.g. "libert libert" → "Libert")
        dr_words = dr_name.title().split()
        seen, unique_words = set(), []
        for w in dr_words:
            if w.lower() not in seen:
                seen.add(w.lower())
                unique_words.append(w)
        dr_name = " ".join(unique_words)
        # Format the ISO timestamp into a friendly string
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(raw_time)
            friendly_time = dt.strftime("%A, %d %B %Y at %I:%M %p").lstrip("0")
        except Exception:
            friendly_time = raw_time
        patient_name = session_data.get("patient_name", "").title()
        response = (
            f"All done, {patient_name}! Your appointment with Dr. {dr_name} is confirmed "
            f"for {friendly_time}. See you then!"
        )
        update_state(patient_id, "IDLE", {"user": user_input, "agent": response}, detected_language)
        return response, {"booking": result}
    else:
        error = result.get("error", "Unknown error")
        response = f"I couldn't book the appointment. {error} Please try again."
        update_state(patient_id, "BOOKING", {"user": user_input, "agent": response}, detected_language)
        return response, {"error": error}
