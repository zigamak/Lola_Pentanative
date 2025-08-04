import datetime
import logging
from threading import Lock # Import Lock for thread safety

logger = logging.getLogger(__name__)

# Global in-memory store for sessions, protected by a Lock for thread safety.
# This ensures that concurrent requests don't corrupt session data.
_sessions_store = {}
_sessions_lock = Lock()

class SessionManager:
    """Manages user sessions and their states."""

    # Default timeouts for different session types
    SESSION_TIMEOUT_SECONDS = 3000  # 10 minutes for unpaid/active sessions
    PAID_SESSION_TIMEOUT_SECONDS = 12000

    # Define a short grace period for freshly reset sessions (e.g., 2 seconds)
    # This prevents the bot from immediately sending a menu message after a handler
    # has just reset the state and sent its final message.
    FRESH_RESET_GRACE_PERIOD_SECONDS = 2


    def __init__(self, session_timeout=None):
        self.timeout_minutes = session_timeout / 60 if session_timeout else self.SESSION_TIMEOUT_SECONDS / 60
        logger.info("SessionManager initialized. Default timeouts: Unpaid=%ds, Paid=%ds",
                     self.SESSION_TIMEOUT_SECONDS, self.PAID_SESSION_TIMEOUT_SECONDS)

    def _get_timeout_duration(self, session_data: dict) -> int:
        """
        Determines the correct timeout duration based on whether the session
        is marked as paid.
        """
        if session_data.get('is_paid_user') and session_data.get('extended_session'):
            paid_expires_str = session_data.get("paid_session_expires")
            if paid_expires_str:
                try:
                    paid_expires = datetime.datetime.fromisoformat(paid_expires_str)
                    if datetime.datetime.now() < paid_expires:
                        return self.PAID_SESSION_TIMEOUT_SECONDS
                except ValueError:
                    logger.warning(f"Invalid 'paid_session_expires' format for session. Treating as unpaid.")
                    # Fall through to default if format is bad
            else:
                logger.warning(f"Session marked as paid but missing 'paid_session_expires'. Treating as unpaid.")
                # Fall through to default if timestamp is missing
        return self.SESSION_TIMEOUT_SECONDS

    def get_session_state(self, session_id: str) -> dict:
        """
        Retrieves the current session state for a given session ID.
        If the session does not exist or has timed out, it initializes a new one.
        Updates the 'last_activity' timestamp for active sessions.
        """
        with _sessions_lock: # Acquire lock before accessing the shared store
            session_data = _sessions_store.get(session_id)

            if session_data:
                # Check for explicit paid session expiration first
                if session_data.get("is_paid_user") and session_data.get("extended_session"):
                    paid_expires_str = session_data.get("paid_session_expires")
                    if paid_expires_str:
                        try:
                            paid_expires = datetime.datetime.fromisoformat(paid_expires_str)
                            if datetime.datetime.now() > paid_expires:
                                logger.info(f"Paid session {session_id} expired. Resetting to normal session.")
                                self._reset_paid_session_internal(session_id, session_data) # Use internal reset
                                session_data = _sessions_store.get(session_id) # Re-fetch updated data
                        except ValueError:
                            logger.warning(f"Invalid 'paid_session_expires' format for session {session_id} during retrieval. Resetting paid status.")
                            self._reset_paid_session_internal(session_id, session_data)
                            session_data = _sessions_store.get(session_id)

                # Now apply general timeout logic
                time_since_last_activity = (datetime.datetime.now() - session_data["last_activity"]).total_seconds()
                timeout_duration = self._get_timeout_duration(session_data)

                if time_since_last_activity > timeout_duration:
                    logger.info(f"Session {session_id} timed out after {time_since_last_activity:.2f} seconds (timeout limit: {timeout_duration}s). Resetting.")
                    # Reset session, preserving user info (name, address, phone number)
                    user_name = session_data.get("user_name")
                    address = session_data.get("address")

                    # Create a new default state, preserving key user info
                    new_session_data = {
                        "current_state": "start",
                        "current_handler": "greeting_handler", # Ensure handler is also reset
                        "cart": {},
                        "selected_category": None,
                        "selected_item": None,
                        "user_name": user_name,
                        "phone_number": session_id,
                        "address": address,
                        "quantity_prompt_sent": False,
                        "last_activity": datetime.datetime.now(),
                        "payment_reference": None,
                        "order_id": None,
                        "total_cost": 0, # Initialize total_cost
                        "is_paid_user": False, # Reset paid status on timeout
                        "extended_session": False,
                        "recent_order_id": None,
                        "paid_session_expires": None,
                        "freshly_reset_timestamp": datetime.datetime.now() # Set timestamp on reset
                    }
                    _sessions_store[session_id] = new_session_data
                    return new_session_data
                else:
                    # Session is active and not timed out, update last activity and return its data
                    session_data["last_activity"] = datetime.datetime.now()
                    # If the user is actively interacting, it's no longer "freshly reset" by a system action
                    session_data["freshly_reset_timestamp"] = None
                    logger.debug(f"Session {session_id} retrieved (active). Activity updated.")
                    return session_data
            else:
                # Session does not exist, initialize a brand new one
                new_session_data = {
                    "current_state": "start",
                    "current_handler": "greeting_handler", # Default handler
                    "cart": {},
                    "selected_category": None,
                    "selected_item": None,
                    "user_name": None,
                    "phone_number": session_id,
                    "address": None,
                    "quantity_prompt_sent": False,
                    "last_activity": datetime.datetime.now(),
                    "payment_reference": None,
                    "order_id": None,
                    "total_cost": 0, # Initialize total_cost
                    "is_paid_user": False,
                    "extended_session": False,
                    "recent_order_id": None,
                    "paid_session_expires": None,
                    "freshly_reset_timestamp": None # No initial reset for new sessions
                }
                _sessions_store[session_id] = new_session_data
                logger.info(f"New session {session_id} initialized.")
                return new_session_data

    def update_session_state(self, session_id: str, new_state_data: dict):
        """
        Explicitly updates the entire session state for a given session ID.
        This method should be called after a handler modifies the 'state' dictionary
        and needs to persist those changes back to the SessionManager's store.
        
        Args:
            session_id (str): The ID of the session to update.
            new_state_data (dict): The complete dictionary of the updated session state.
        """
        if not isinstance(new_state_data, dict):
            logger.error(f"Attempted to update session {session_id} with non-dictionary data (type: {type(new_state_data)}). Update aborted.")
            return # Prevent further errors if invalid data is passed

        with _sessions_lock: # Acquire lock for writing to the shared store
            # Get the old state to determine if a "fresh reset" is occurring
            old_state_data = _sessions_store.get(session_id, {})

            # Ensure 'last_activity' is always updated on state persist
            new_state_data['last_activity'] = datetime.datetime.now()
            
            # --- Freshly Reset Logic ---
            old_handler = old_state_data.get("current_handler")
            old_state = old_state_data.get("current_state")
            new_handler = new_state_data.get("current_handler")
            new_current_state = new_state_data.get("current_state")

            # A fresh reset occurs when we transition to greeting_handler/start/greeting
            # from a *different* handler or a *different* state within greeting_handler.
            is_transitioning_to_greeting_state = (
                new_handler == "greeting_handler" and
                new_current_state in ["start", "greeting"]
            )
            was_already_in_greeting_state = (
                old_handler == "greeting_handler" and
                old_state in ["start", "greeting"]
            )

            if is_transitioning_to_greeting_state and not was_already_in_greeting_state:
                new_state_data["freshly_reset_timestamp"] = datetime.datetime.now()
                logger.debug(f"Session {session_id}: Setting freshly_reset_timestamp due to state transition to '{new_handler}'/'{new_current_state}'.")
            else:
                # If we are not transitioning to a fresh greeting state, clear the timestamp
                new_state_data["freshly_reset_timestamp"] = None
                
            _sessions_store[session_id] = new_state_data
            logger.debug(f"Session {session_id} state updated to '{new_state_data.get('current_state', 'N/A')}'")

    def update_session_activity(self, session_id: str):
        """
        Updates the 'last_activity' timestamp for a given session.
        This is typically called by the MessageProcessor on every incoming message
        to keep the session alive.
        """
        with _sessions_lock: # Acquire lock for writing
            if session_id in _sessions_store:
                _sessions_store[session_id]["last_activity"] = datetime.datetime.now()
                # When a user sends a new message, it's no longer "freshly reset" by a system action.
                _sessions_store[session_id]["freshly_reset_timestamp"] = None
                logger.debug(f"Updated activity for session {session_id}")
            else:
                logger.warning(f"Attempted to update activity for non-existent session {session_id}.")

    def set_session_paid_status(self, session_id: str, paid_status: bool):
        """
        Explicitly sets the paid status for a session.
        This should be called by the PaymentHandler after a successful payment
        to ensure the session benefits from the longer paid_session_timeout.
        """
        with _sessions_lock: # Acquire lock for writing
            session_data = _sessions_store.get(session_id)
            if session_data:
                session_data['is_paid_user'] = paid_status
                # When setting paid status, also mark for extended session and set expiration
                if paid_status:
                    session_data['extended_session'] = True
                    session_data['paid_session_expires'] = (
                        datetime.datetime.now() + datetime.timedelta(seconds=self.PAID_SESSION_TIMEOUT_SECONDS)
                    ).isoformat()
                    logger.info(f"Session {session_id} paid status set to {paid_status} and extended for {self.PAID_SESSION_TIMEOUT_SECONDS / 3600} hours.")
                else:
                    # If setting to unpaid, remove extended session flags
                    session_data['extended_session'] = False
                    session_data['recent_order_id'] = None
                    session_data['paid_session_expires'] = None
                    logger.info(f"Session {session_id} paid status set to {paid_status} (normal timeout).")

                # Always update last activity when status changes to refresh timeout logic
                session_data['last_activity'] = datetime.datetime.now()
                # When setting paid status, we're not 'freshly resetting' to greeting.
                session_data['freshly_reset_timestamp'] = None
                self.update_session_state(session_id, session_data) # Persist changes
            else:
                logger.warning(f"Attempted to set paid status for non-existent session {session_id}.")

    def extend_session_for_paid_user(self, session_id: str, order_id: str, hours: int = 24):
        """
        Extend session timeout for paid users to allow order tracking.
        This method will leverage `set_session_paid_status` to ensure consistency.
        
        Args:
            session_id (str): User's session ID
            order_id (str): Order ID for tracking
            hours (int): Hours to extend session (default 24 hours)
        """
        try:
            with _sessions_lock:
                # IMPORTANT: get_session_state already handles expired sessions and returns a fresh state.
                # Avoid re-fetching or creating conflicting logic here.
                state = _sessions_store.get(session_id)
                if not state:
                    # If session doesn't exist, create it via get_session_state, then update it
                    state = self.get_session_state(session_id)
                    logger.warning(f"Session {session_id} did not exist when extending for paid user; a new one was initialized.")

                # Mark as paid user with extended session and set expiration
                state["is_paid_user"] = True
                state["extended_session"] = True
                state["recent_order_id"] = order_id
                
                # Calculate expiration based on provided hours, not just self.PAID_SESSION_TIMEOUT_SECONDS
                # This allows for dynamic extension periods if needed.
                paid_expires = datetime.datetime.now() + datetime.timedelta(hours=hours)
                state["paid_session_expires"] = paid_expires.isoformat()
                
                # Ensure the 'last_activity' is updated to reflect the new longer timeout window
                state["last_activity"] = datetime.datetime.now()
                # This is not a 'fresh reset' to greeting, so ensure timestamp is None
                state["freshly_reset_timestamp"] = None
                
                self.update_session_state(session_id, state) # Persist the updated state
                logger.info(f"Extended session for paid user {session_id} for {hours} hours. Order: {order_id}")
                
        except Exception as e:
            logger.error(f"Error extending session for paid user {session_id}: {e}", exc_info=True)

    def is_paid_user_session(self, session_id: str) -> bool:
        """Check if this is an active paid user session."""
        try:
            with _sessions_lock: # Acquire lock for reading session data
                state = _sessions_store.get(session_id)
                if not state:
                    return False # Session doesn't exist

                if not state.get("is_paid_user") or not state.get("extended_session"):
                    return False
                
                # Check if paid session has expired
                paid_expires_str = state.get("paid_session_expires")
                if paid_expires_str:
                    try:
                        paid_expires = datetime.datetime.fromisoformat(paid_expires_str)
                        if datetime.datetime.now() > paid_expires:
                            # Paid session expired, reset to normal user and return False
                            logger.info(f"Paid session {session_id} expired during is_paid_user_session check. Resetting.")
                            self._reset_paid_session_internal(session_id, state) # Use internal reset
                            return False
                    except ValueError:
                        logger.warning(f"Invalid 'paid_session_expires' format for session {session_id}. Resetting paid status.")
                        self._reset_paid_session_internal(session_id, state)
                        return False
                else:
                    # If extended_session is true but paid_session_expires is missing, something is off.
                    # Treat as expired and reset.
                    logger.warning(f"Session {session_id} has 'extended_session' but no 'paid_session_expires'. Resetting.")
                    self._reset_paid_session_internal(session_id, state)
                    return False
                
                return True
                
        except Exception as e:
            logger.error(f"Error checking paid user session {session_id}: {e}", exc_info=True)
            return False

    def _reset_paid_session_internal(self, session_id: str, state: dict):
        """
        Internal helper to reset a paid session back to normal.
        Assumes the _sessions_lock is already held by the calling method.
        """
        # Remove paid user flags
        paid_keys = ["is_paid_user", "extended_session", "recent_order_id", "paid_session_expires"]
        for key in paid_keys:
            if key in state:
                del state[key]
        
        # Reset to normal timeout (implicitly handled by _get_timeout_duration on next access)
        # Update last activity to reflect the reset to normal timeout
        state["last_activity"] = datetime.datetime.now()
        
        # This is a system-initiated reset (due to expiry), so it might be a 'fresh reset'
        # if the user was just interacting before it expired.
        # We need to decide if this specific reset should set freshly_reset_timestamp.
        # For an expiry-based reset, we might want to trigger the greeting behavior.
        # If the goal is to send a "Your session expired, here's the menu" message,
        # then setting this timestamp here might be counterproductive to the _route_to_handler logic
        # that looks for it to suppress messages.
        # Let's *not* set it here, and let the `get_session_state` or `update_session_state`
        # when called by MessageProcessor handle the reset to 'start' or 'greeting' and set it.
        state["freshly_reset_timestamp"] = None # Ensure it's cleared if it was somehow set

        # Persist the state change. Use update_session_state to ensure all logic is applied.
        # Note: calling update_session_state from within a locked context might be tricky if
        # update_session_state also acquires the lock. However, since it's operating on `state`
        # which is already in the `_sessions_store`, it should be fine.
        self.update_session_state(session_id, state)
        logger.info(f"Reset paid session for {session_id} back to normal session")
            
    def clear_session_cart(self, session_id: str):
        """Clear the cart for a specific session."""
        with _sessions_lock: # Acquire lock for writing
            if session_id in _sessions_store:
                _sessions_store[session_id]["cart"] = {}
                self.update_session_state(session_id, _sessions_store[session_id]) # Persist change
                logger.info(f"Cart cleared for session {session_id}")
            else:
                logger.warning(f"Attempted to clear cart for non-existent session {session_id}.")

    def reset_session_order_data(self, session_id: str):
        """
        Reset order-specific data in session (e.g., after order completion or cancellation).
        """
        with _sessions_lock: # Acquire lock for writing
            if session_id in _sessions_store:
                state = _sessions_store[session_id]
                state["order_id"] = None
                state["payment_reference"] = None
                state["total_cost"] = 0 # Also reset total cost related to the order
                # This is not a 'fresh reset' to greeting, so ensure timestamp is None
                state["freshly_reset_timestamp"] = None
                self.update_session_state(session_id, state) # Persist change
            else:
                logger.warning(f"Attempted to reset order data for non-existent session {session_id}.")

    def clear_full_session(self, session_id: str):
        """
        Completely removes a session from the manager's store.
        Use with caution, as all session history for that user will be lost.
        """
        with _sessions_lock: # Acquire lock for deletion
            if session_id in _sessions_store:
                del _sessions_store[session_id]
                logger.info(f"Full session {session_id} cleared.")
            else:
                logger.warning(f"Attempted to clear non-existent session {session_id}.")

    def cleanup_expired_sessions(self):
        """
        Iterates through all sessions and removes those that have timed out.
        This method is designed to be called periodically by a background task
        (e.g., a separate thread or a scheduled job).
        """
        cleaned_count = 0
        sessions_to_clear = [] # List to hold IDs of sessions to be removed

        with _sessions_lock: # Acquire lock for iterating and modifying the store
            for session_id, session_data in list(_sessions_store.items()): # Use list() to iterate over a copy
                                                                        # to avoid RuntimeError during deletion
                # First, check if it's a paid session and its explicit expiry
                if session_data.get("is_paid_user") and session_data.get("extended_session"):
                    paid_expires_str = session_data.get("paid_session_expires")
                    if paid_expires_str:
                        try:
                            paid_expires = datetime.datetime.fromisoformat(paid_expires_str)
                            if datetime.datetime.now() > paid_expires:
                                logger.info(f"Cleanup: Paid session {session_id} explicitly expired. Resetting to normal.")
                                self._reset_paid_session_internal(session_id, session_data)
                                # After internal reset, session_data is modified and will fall under normal timeout rules
                        except ValueError:
                            logger.warning(f"Cleanup: Invalid 'paid_session_expires' format for session {session_id}. Resetting paid status.")
                            self._reset_paid_session_internal(session_id, session_data)
                    else:
                        logger.warning(f"Cleanup: Session {session_id} marked as paid but missing 'paid_session_expires'. Resetting.")
                        self._reset_paid_session_internal(session_id, session_data)


                # Now apply the general timeout logic based on its current status (paid or unpaid)
                time_since_last_activity = (datetime.datetime.now() - session_data["last_activity"]).total_seconds()
                timeout_duration = self._get_timeout_duration(session_data)
                
                if time_since_last_activity > timeout_duration:
                    sessions_to_clear.append(session_id) # Mark for removal

            for session_id in sessions_to_clear:
                del _sessions_store[session_id]
                cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"Cleanup job: Removed {cleaned_count} expired sessions.")
            return cleaned_count

    def is_freshly_reset(self, session_id: str) -> bool:
        """
        Checks if the session was recently reset to the greeting/start state
        by a system action (e.g., another handler completing its flow).
        This helps prevent sending an immediate menu message right after
        another handler has completed its task and reset the state.
        """
        with _sessions_lock: # Acquire lock for reading
            state = _sessions_store.get(session_id)
            if not state:
                return False # Session doesn't exist

            freshly_reset_timestamp = state.get("freshly_reset_timestamp")
            current_handler = state.get("current_handler")
            current_state = state.get("current_state")

            if freshly_reset_timestamp and \
               (current_handler == "greeting_handler" and current_state in ["greeting", "start"]):
                time_since_reset = (datetime.datetime.now() - freshly_reset_timestamp).total_seconds()
                return time_since_reset < self.FRESH_RESET_GRACE_PERIOD_SECONDS
            return False

    def reset_freshly_reset_flag(self, session_id: str):
        """
        Manually resets the freshly_reset_timestamp for a session.
        This can be called by `MessageProcessor` or a handler if it determines
        that the "freshly reset" state has been handled (e.g., a message was sent).
        """
        with _sessions_lock:
            if session_id in _sessions_store:
                _sessions_store[session_id]["freshly_reset_timestamp"] = None
                logger.debug(f"Freshly reset flag cleared for session {session_id}.")
            else:
                logger.warning(f"Attempted to clear freshly reset flag for non-existent session {session_id}.")