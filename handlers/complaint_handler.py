import logging
import datetime
import json
from typing import Dict, Any, List
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class ComplaintHandler(BaseHandler):
    """
    Handles complaint-related interactions, including submission and state reset to main menu.
    This version is updated to work with the `whatsapp_complaint_details` table schema.
    """
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
    
    def handle(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Top-level handler for complaint-related states.
        Routes to appropriate methods based on state and redirect message.
        """
        self.logger.info(f"Session {session_id}: Handling message '{message}' in state '{state.get('current_state')}'.")
        
        current_state = state.get("current_state")
        
        if message == "show_complaint_prompt":
            return self.show_complaint_prompt(state, session_id)
        elif current_state == "complain":
            return self.handle_complaint_state(state, original_message, session_id)
        else:
            self.logger.warning(f"Session {session_id}: Unhandled state '{current_state}' with message '{message}'.")
            return self._handle_invalid_state(state, session_id)

    def show_complaint_prompt(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Prompts the user to enter their complaint and sets the session state."""
        self.logger.info(f"Session {session_id}: Entering complaint input state.")
        state["current_state"] = "complain"
        state["current_handler"] = "complaint_handler"
        self.session_manager.update_session_state(session_id, state)
        
        return self.whatsapp_service.create_text_message(
            session_id,
            "📝 What issue are you experiencing? Please describe your complaint in detail and we'll get back to you as soon as possible."
        )

    def handle_complaint_state(self, state: Dict, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the 'complain' state where the user provides their complaint.
        Saves the complaint to the database and returns to the main menu.
        """
        try:
            complaint_text = original_message.strip()
            if not complaint_text:
                self.logger.warning(f"Session {session_id}: Empty complaint text received.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Please tell us about your complaint. What issue are you experiencing?"
                )
            
            # Assess the priority based on keywords in the complaint text
            priority = self._assess_complaint_priority(complaint_text)
            
            # The database schema uses 'open' as the initial status.
            status = "open"

            # Retrieve user data for context (user_id is typically the session_id)
            user_data = self.data_manager.get_user_data(session_id)
            user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
            phone_number = user_data.get("phone_number", session_id) if user_data else session_id

            # Prepare complaint data matching the whatsapp_complaint_details table schema
            complaint_data = {
                "merchant_details_id": getattr(self.config, 'MERCHANT_ID', None),
                "user_name": user_name,
                "user_id": session_id,  # Corresponds to the user_id column
                "phone_number": phone_number,
                "complaint_categories": json.dumps(["General"]), # JSONB column requires JSON string
                "complaint_text": complaint_text,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "channel": "whatsapp",
                "status": status,
                "priority": priority
            }
            
            # Save the complaint and get the ref_id
            ref_id = self.data_manager.save_complaint(complaint_data)
            if ref_id is None:
                self.logger.error(f"Session {session_id}: Failed to save complaint to database.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Sorry, there was an issue saving your complaint. Please try again or contact support."
                )
            
            self.logger.info(f"Session {session_id}: Complaint {ref_id} saved for user {user_name} (phone: {phone_number}) with text: {complaint_text[:50]}{'...' if len(complaint_text) > 50 else ''}")
            
            # Reset session state to greeting
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            
            # Prepare confirmation message
            confirmation_message = (
                f"✅ Thank you for your complaint, {user_name}!\n\n"
                f"*Complaint ID:* {ref_id}\n\n"
                f"We've received your issue: \"{complaint_text[:50]}{'...' if len(complaint_text) > 50 else ''}\"\n\n"
                f"Our team will respond within 24 hours. "
                f"Please reference complaint ID {ref_id} in future communications."
            )
            
            return self._return_to_main_menu(state, session_id, confirmation_message, user_name)
        
        except Exception as e:
            self.logger.error(f"Session {session_id}: Error handling complaint submission: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ An error occurred while processing your complaint. Please try again or contact support."
            )
    
    def _assess_complaint_priority(self, complaint_text: str) -> str:
        """Assess complaint priority based on content."""
        urgent_keywords = [
            "urgent", "emergency", "asap", "immediately", "critical",
            "problem", "issue", "error", "broken", "not working", "stuck"
        ]
        
        complaint_lower = complaint_text.lower()
        if any(keyword in complaint_lower for keyword in urgent_keywords):
            self.logger.debug(f"Complaint contains urgent keywords: {complaint_lower}")
            return "high"
        return "medium" # Changed default to 'medium' to align with schema
    
    def _handle_invalid_state(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle invalid or unexpected states."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        
        message = (
            f"Sorry, something went wrong. Let's start over."
        )
        return self._return_to_main_menu(state, session_id, message, user_name)

    def _return_to_main_menu(self, state: Dict, session_id: str, message: str, user_name: str) -> Dict[str, Any]:
        """Handles navigation back to the main menu with a specific message."""
        # Clear order-related data but preserve user info
        state.pop("cart", None)
        state.pop("selected_category", None)
        state.pop("selected_item", None)
        
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id}: Returned to main menu from complaint handler.")
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\n\n{message}\n\nWhat would you like to do next?",
                buttons
            )
        else:
            buttons = [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Hi {user_name}, {message}\n\nWhat would you like to do next?",
                buttons
            )