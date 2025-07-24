import logging
import uuid
import datetime
from typing import Dict, Any
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class ComplaintHandler(BaseHandler):
    """Handles complaint-related interactions."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
    
    def handle_complaint_state(self, state: Dict, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the 'complain' state where the user provides their complaint.
        Saves the complaint, sends a confirmation, and ends the session.
        """
        current_state = state.get("current_state")

        if current_state == "complain":
            complaint_text = original_message.strip()

            if not complaint_text:
                # User sent an empty message
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Please tell us about your complaint. What issue are you experiencing?"
                )

            try:
                # Generate a unique complaint ID
                complaint_id = str(uuid.uuid4())
                
                # Save the complaint
                complaint_data = {
                    "complaint_id": complaint_id,
                    "user_name": state.get("user_name", "Guest"),
                    "phone_number": session_id,
                    "complaint_text": complaint_text,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "status": "pending",
                    "priority": self._assess_complaint_priority(complaint_text)
                }
                self.data_manager.save_complaint(complaint_data)
                logger.info(f"Complaint saved for session {session_id}: {complaint_id}")

                # Send confirmation and end session
                thank_you_msg = (
                    f"✅ Thank you for your complaint!\n\n"
                    f"*Complaint ID:* {complaint_id}\n\n"
                    f"We've received your issue: \"{complaint_text[:50]}{'...' if len(complaint_text) > 50 else ''}\"\n\n"
                    f"Our team will review it and get back to you within 24 hours. "
                    f"We appreciate your patience! 😊\n\n"
                    f"*You can reference complaint ID {complaint_id} in future communications.*"
                )
                
                # Clear session
                self.session_manager.clear_full_session(session_id)
                
                return self.whatsapp_service.create_text_message(session_id, thank_you_msg)
            
            except Exception as e:
                logger.error(f"Error saving complaint for session {session_id}: {e}", exc_info=True)
                # End session with fallback message
                self.session_manager.clear_full_session(session_id)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "✅ Thank you for your complaint! We've received it and will address it soon."
                )
        
        else:
            # Initial entry into the complaint flow
            state["current_state"] = "complain"
            state["current_handler"] = "complaint_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "We're sorry to hear you're having an issue. Please tell us about your complaint and we'll address it promptly."
            )
    
    def _assess_complaint_priority(self, complaint_text: str) -> str:
        """Assess complaint priority based on keywords."""
        urgent_keywords = [
            "urgent", "emergency", "asap", "immediately", "critical",
            "problem", "issue", "error", "broken", "not working"
        ]
        
        complaint_lower = complaint_text.lower()
        
        if any(keyword in complaint_lower for keyword in urgent_keywords):
            return "high"
        return "normal"