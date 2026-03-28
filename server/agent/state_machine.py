import enum
from typing import List, Dict

class State(str, enum.Enum):
    IDLE = "IDLE"
    BOOKING = "BOOKING"
    RESCHEDULING = "RESCHEDULING"
    CANCELLING = "CANCELLING"
    CONFIRMING = "CONFIRMING"

VALID_TRANSITIONS: Dict[State, List[State]] = {
    State.IDLE: [State.BOOKING, State.RESCHEDULING, State.CANCELLING],
    State.BOOKING: [State.CONFIRMING, State.IDLE],
    State.RESCHEDULING: [State.CONFIRMING, State.IDLE],
    State.CANCELLING: [State.CONFIRMING, State.IDLE],
    State.CONFIRMING: [State.IDLE]
}

def can_transition(current_state: str, next_state: str) -> bool:
    try:
        curr = State(current_state.upper())
        nxt = State(next_state.upper())
        return nxt in VALID_TRANSITIONS.get(curr, [])
    except ValueError:
        return False

def get_next_possible_states(current_state: str) -> List[str]:
    try:
        curr = State(current_state.upper())
        return [s.value for s in VALID_TRANSITIONS.get(curr, [])]
    except ValueError:
        return []

def transition_state(current_state: str, requested_state: str) -> str:
    if can_transition(current_state, requested_state):
        return requested_state.upper()
    return current_state.upper()
