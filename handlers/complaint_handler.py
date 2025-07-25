import logging
import uuid
import datetime
from typing import Dict, Any
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class ComplaintHandler(BaseHandler):
    """Handles complaint-related interactions, including submission and state reset to main menu."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
    
    def handle_complaint_state(self, state: Dict, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the 'complain' state where the user provides their complaint.
        Saves the complaint, sends a confirmation, and returns to the main menu.
        """
        try:
            complaint_text = original_message.strip()
            if not complaint_text:
                self.logger.warning(f"Session {session_id}: Empty complaint text received.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Please tell us about your complaint. What issue are you experiencing?"
                )
            
            # Generate a unique complaint ID
            complaint_id = str(uuid.uuid4())
            
            # Save the complaint
            complaint_data = {
                "complaint_id": complaint_id,
                "user_name": state.get("user_name", "Guest"),
                "phone_number": state.get("phone_number", session_id),
                "complaint_text": complaint_text,
                "timestamp": datetime.datetime.now().isoformat(),
                "status": "pending",
                "priority": self._assess_complaint_priority(complaint_text)
            }
            success = self.data_manager.save_complaint(complaint_data)
            if not success:
                self.logger.error(f"Session {session_id}: Failed to save complaint {complaint_id} to database.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Sorry, there was an issue saving your complaint. Please try again or contact support."
                )
            
            self.logger.info(f"Session {session_id}: Complaint {complaint_id} saved successfully.")
            
            # Reset session state to greeting
            user_data = self.data_manager.get_user_data(session_id)
            user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            # Clear order-related data but preserve user info
            state["cart"] = {}
            if "selected_category" in state:
                del state["selected_category"]
            if "selected_item" in state:
                del state["selected_item"]
            self.session_manager.update_session_state(session_id, state)
            
            # Prepare confirmation message
            confirmation_message = (
                f"✅ Thank you for your complaint!\n\n"
                f"*Complaint ID:* {complaint_id}\n\n"
                f"We've received your issue: \"{complaint_text[:50]}{'...' if len(complaint_text) > 50 else ''}\"\n\n"
                f"Our team will respond within 24 hours. "
                f"Please reference complaint ID {complaint_id} in future communications.\n\n"
                f"What would you like to do next?"
            )
            
            # Check if user is paid to show appropriate menu
            if self.session_manager.is_paid_user_session(session_id):
                self.logger.info(f"Session {session_id}: Returning to paid user main menu after complaint submission.")
                buttons = [
                    {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                    {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                    {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"Welcome Back {user_name}\n{confirmation_message}",
                    buttons
                )
            else:
                self.logger.info(f"Session {session_id}: Returning to non-paid user main menu after complaint submission.")
                buttons = [
                    {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                    {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                    {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"Hi {user_name}, {confirmation_message}",
                    buttons
                )
        
        except Exception as e:
            self.logger.error(f"Session {session_id}: Error handling complaint submission: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ An error occurred while processing your complaint. Please try again or contact support."
            )
    
    def _assess_complaint_priority(self, complaint_text: str) -> str:
        """Assess complaint priority based on keywords."""
        urgent_keywords = [
            "urgent", "emergency", "asap", "immediately", "critical",
            "problem", "issue", "error", "broken", "not working"
        ]
        
        complaint_lower = complaint_text.lower()
        
        if any(keyword in complaint_lower for keyword in urgent_keywords):
            self.logger.debug(f"Complaint contains urgent keywords: {complaint_lower}")
            return "high"
        return "normal"