import json
import redis
from typing import Dict, Any, Optional

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

SESSION_TTL_SECONDS = 20 * 60 

def _get_session_key(patient_id: str) -> str:
    return f"session:{patient_id}"

def _get_long_term_key(patient_id: str) -> str:
    return f"memory:patient:{patient_id}"

def _get_data_key(patient_id: str) -> str:
    return f"data:{patient_id}"

def get_state(patient_id: str) -> Dict[str, Any]:
    key = _get_session_key(patient_id)
    data = redis_client.get(key)
    
    if data:
        redis_client.expire(key, SESSION_TTL_SECONDS)
        return json.loads(data)
    
    return {
        "state": "IDLE",
        "history": [],
        "language_preference": get_language_preference(patient_id) or "en"
    }

def update_state(patient_id: str, new_state: str, new_message: Optional[Dict[str, Any]] = None, language: str = None) -> None:
    current_data = get_state(patient_id)
    
    current_data["state"] = new_state
    
    if new_message:
        current_data["history"].append(new_message)
        
    if language:
        current_data["language_preference"] = language
        set_language_preference(patient_id, language)
        
    session_key = _get_session_key(patient_id)
    redis_client.setex(
        session_key, 
        SESSION_TTL_SECONDS, 
        json.dumps(current_data)
    )

def get_memory(patient_id: str) -> Dict[str, Any]:
    key = _get_long_term_key(patient_id)
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return {}

def update_memory(patient_id: str, updates: Dict[str, Any]) -> None:
    current_memory = get_memory(patient_id)
    current_memory.update(updates)
    
    key = _get_long_term_key(patient_id)
    redis_client.set(key, json.dumps(current_memory))

def get_language_preference(patient_id: str) -> Optional[str]:
    memory = get_memory(patient_id)
    return memory.get("language_preference")

def set_language_preference(patient_id: str, language_code: str) -> None:
    update_memory(patient_id, {"language_preference": language_code})

def get_campaign_flag(patient_id: str) -> Optional[str]:
    memory = get_memory(patient_id)
    return memory.get("pending_campaign")

def set_campaign_flag(patient_id: str, campaign_text: str) -> None:
    update_memory(patient_id, {"pending_campaign": campaign_text})
    
def clear_campaign_flag(patient_id: str) -> None:
    current = get_memory(patient_id)
    if "pending_campaign" in current:
        del current["pending_campaign"]
        key = _get_long_term_key(patient_id)
        redis_client.set(key, json.dumps(current))

def get_session_data(patient_id: str) -> Dict[str, Any]:
    key = _get_data_key(patient_id)
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return {
        "patient_name": None,
        "doctor_id": None,
        "doctor_name": None,
        "date": None,
        "time": None,
        "slot_id": None
    }

def update_session_data(patient_id: str, updates: Dict[str, Any]) -> None:
    current = get_session_data(patient_id)
    current.update(updates)
    key = _get_data_key(patient_id)
    redis_client.setex(key, SESSION_TTL_SECONDS, json.dumps(current))

def clear_session_data(patient_id: str) -> None:
    key = _get_data_key(patient_id)
    redis_client.delete(key)
