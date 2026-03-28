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
from server.agent.state_machine import transition_state
from server.agent.prompts import MASTER_PROMPT
from server.agent.llm_caller import call_llm
from server.agent.tools import (
    check_availability, 
    book_slot, 
    reschedule_slot, 
    cancel_slot, 
    get_patient_history,
    get_doctor_by_name
)

async def _execute_tool(session: Session, tool_name: str, tool_args: Dict[str, Any], current_patient_id: str) -> Any:
    try:
        if tool_name == "check_availability":
            after_date = datetime.fromisoformat(tool_args.get("after_date", datetime.utcnow().isoformat()))
            return check_availability(session, int(tool_args.get("doctor_id", 0)), after_date)
            
        elif tool_name == "book_slot":
            date_val = tool_args.get("date", "")
            time_val = tool_args.get("time", "00:00")
            
            import dateparser
            parsed_dt = dateparser.parse(date_val)
            if parsed_dt:
                date_val = parsed_dt.strftime("%Y-%m-%d")
                
            if "T" not in date_val:
                date_val = f"{date_val}T{time_val}:00"
                
            return book_slot(
                session,
                int(current_patient_id),
                int(tool_args.get("doctor_id", 0)),
                slot_id=None,
                date_str=date_val,
                reason="Voice Booking"
            )
            
        elif tool_name == "reschedule_slot":
            return reschedule_slot(
                session,
                int(tool_args.get("appointment_id", 0)),
                int(tool_args.get("new_slot_id", 0))
            )
            
        elif tool_name == "cancel_slot":
            return cancel_slot(session, int(tool_args.get("appointment_id", 0)))
            
        elif tool_name == "get_patient_history":
            return get_patient_history(session, int(tool_args.get("patient_id", 0)))
            
        elif tool_name == "get_doctor_by_name":
            return get_doctor_by_name(session, tool_args.get("name", ""))
            
    except Exception as e:
        return {"error": str(e)}
        
    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    day_after = (now + timedelta(days=2)).strftime('%Y-%m-%d')
    
    return {"error": f"Unknown tool: {tool_name}"}

async def process_user_input(
    session: Session, 
    patient_id: int, 
    user_input: str,
    detected_language: str = "en"
) -> Tuple[str, Dict[str, Any]]:
    state_data = get_state(patient_id)
    session_data = get_session_data(patient_id)
    current_state = state_data["state"]
    history = state_data.get("history", [])
    
    now = datetime.utcnow()
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    day_after = (now + timedelta(days=2)).strftime('%Y-%m-%d')

    prompt = MASTER_PROMPT.format(
        current_state=current_state,
        language=detected_language,
        session_data=json.dumps(session_data, indent=2),
        context=f"Patient ID: {patient_id}. Current Date: {now.strftime('%Y-%m-%d')}",
        tomorrow=tomorrow,
        day_after=day_after,
        history=str(history[-5:]),
        user_input=user_input
    )
    
    llm_response = await call_llm(prompt)
    
    next_state_proposed = llm_response.get("next_state", current_state)
    new_state = transition_state(current_state, next_state_proposed)
    
    action = llm_response.get("action", "SPEAK")
    tool_name = llm_response.get("tool_name")
    tool_args = llm_response.get("tool_args") or {}
    response_text = llm_response.get("response") or ""
    extracted_info = llm_response.get("extracted_info") or {}
    
    # Immediately persist any newly extracted fields provided in this single turn
    updates = {}
    for key in ["date", "time", "doctor_name", "patient_name"]:
        if extracted_info.get(key) and extracted_info[key] != "null":
            updates[key] = extracted_info[key]
    if updates:
        update_session_data(patient_id, updates)
    
    # ── SAFETY NET: Force tool execution if LLM incorrectly chose SPEAK ──────
    # Refresh session after possible updates from extracted_info
    session_data = get_session_data(str(patient_id))
    has_all_fields = all([
        session_data.get("patient_name"),
        session_data.get("doctor_name"),
        session_data.get("date"),
        session_data.get("time"),
    ])
    if action == "SPEAK" and has_all_fields:
        if not session_data.get("doctor_id"):
            # LLM stalled — override to run get_doctor_by_name silently
            action = "CALL_TOOL"
            tool_name = "get_doctor_by_name"
            tool_args = {"name": session_data["doctor_name"]}
            new_state = "BOOKING"
        else:
            # Doctor ID already fetched — override to book directly
            action = "CALL_TOOL"
            tool_name = "book_slot"
            tool_args = {
                "doctor_id": session_data["doctor_id"],
                "date": session_data["date"],
                "time": session_data["time"],
            }
            new_state = "BOOKING"
    # ─────────────────────────────────────────────────────────────────────────

    iterations = 0
    while action == "CALL_TOOL" and tool_name and iterations < 3:
        iterations += 1
        tool_result = await _execute_tool(session, tool_name, tool_args, str(patient_id))
        
        # Persist important IDs back to session data
        if tool_name == "get_doctor_by_name" and tool_result.get("success"):
            update_session_data(patient_id, {
                "doctor_id": tool_result["doctor_id"],
                "doctor_name": tool_result["name"]
            })
        elif tool_name == "book_slot" and tool_result.get("success"):
            clear_session_data(patient_id)

        followup_prompt = prompt + f"\nSystem_Tool_Result for {tool_name}: {tool_result}\nIf you need to execute another tool to finish the booking (e.g. book_slot), return action='CALL_TOOL' and the next tool. If you are finished and want to notify the user, return action='SPEAK' and the final response text."
        llm_response = await call_llm(followup_prompt)
        
        action = llm_response.get("action", "SPEAK")
        tool_name = llm_response.get("tool_name")
        tool_args = llm_response.get("tool_args") or {}
        response_text = llm_response.get("response") or str(tool_result)
        new_state = transition_state(new_state, llm_response.get("next_state") or new_state)
    
    # Also attempt to update session data from LLM tool_args before turn ends
    if tool_args:
        updates = {}
        for key in ["date", "time", "doctor_id", "slot_id", "patient_name"]:
            if tool_args.get(key): updates[key] = tool_args[key]
        if updates: update_session_data(patient_id, updates)

    update_state(patient_id, new_state, {"user": user_input, "agent": response_text}, detected_language)
    
    return response_text, llm_response
