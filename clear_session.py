import logging
from app import app, session_manager  # Import app and session_manager from app.py

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

PHONE_NUMBER = '2348055614455'

# Clear the session
session_manager.clear_full_session(PHONE_NUMBER)
logger.info(f"Cleared in-memory session for {PHONE_NUMBER}")

# Verify new session
new_state = session_manager.get_session_state(PHONE_NUMBER)
logger.info(f"New session state: user_name={new_state.get('user_name')}, address={new_state.get('address')}, current_state={new_state.get('current_state')}")
# Expected: user_name=None, address=None, current_state='start'