# app/models/session_state.py
from dataclasses import dataclass
from typing import Dict

# Simple in-memory session storage
sessions = {}

@dataclass
class SessionState:
    conversation_history: list = None

def get_session_state(session_id):
    """Get or create a session state for the given ID"""
    if session_id not in sessions:
        sessions[session_id] = SessionState(conversation_history=[])
    return sessions[session_id]
# ADD THIS METHOD TO YOUR EXISTING utils/session_manager.py FILE

def update_session_state(self, session_id, state):
    """Update the entire session state."""
    if session_id in self.session_states:
        self.session_states[session_id] = state
        self.session_states[session_id]["last_activity"] = datetime.datetime.now()
        logger.info(f"Updated session state for {session_id}")
    else:
        logger.warning(f"Attempted to update non-existent session {session_id}")