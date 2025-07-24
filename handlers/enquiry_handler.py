import datetime
import uuid
from .base_handler import BaseHandler

class EnquiryHandler(BaseHandler):
    """Handles enquiry-related interactions."""
    
    def show_enquiry_menu(self, state, session_id):
        """Display the enquiry menu with FAQ and Ask Question options."""
        self.logger.info(f"Session {session_id} entering enquiry menu.")

        buttons = [
            {"type": "reply", "reply": {"id": "faq", "title": "📚 FAQ"}},
            {"type": "reply", "reply": {"id": "ask_question", "title": "❓ Ask Question"}},
            {"type": "reply", "reply": {"id": "back_to_main", "title": "🔙 Back"}}
        ]
        
        return self.whatsapp_service.create_button_message(
            session_id,
            "How can we help you today?\n\n📚 *FAQ* - Get instant answers to common questions\n❓ *Ask Question* - Send us your specific question",
            buttons
        )

    def handle_enquiry_menu_state(self, state, message, session_id):
        """Handle enquiry menu state."""
        if message == "faq":
            state["current_state"] = "faq_categories"
            self.session_manager.update_session_state(session_id, state) # Update state before redirect
            return {"redirect": "faq_handler"}  # Signal to route to FAQ handler
        elif message == "ask_question":
            state["current_state"] = "enquiry"
            self.session_manager.update_session_state(session_id, state) # Update state for enquiry input
            return self.whatsapp_service.create_text_message(
                session_id,
                "❓ What would you like to know? Please type your question and we'll get back to you soon!"
            )
        elif message == "back_to_main":
            return self.handle_back_to_main(state, session_id)
        else:
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please select an option from the menu above."
            )
    
    def handle_enquiry_state(self, state, original_message, session_id):
        """Handle enquiry submission."""
        enquiry_id = str(uuid.uuid4())
        enquiry_data = {
            "enquiry_id": enquiry_id,
            "user_name": state.get("user_name", "Unknown"), # Use .get for robustness
            "phone_number": state.get("phone_number", "Unknown"), # Ensure phone_number is in state
            "enquiry_text": original_message.strip(),
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "pending",
            "priority": self._assess_enquiry_priority(original_message)
        }
        
        self.data_manager.save_enquiry(enquiry_data)
        
        # Clear the session after the enquiry is submitted
        self.session_manager.clear_full_session(session_id)
        
        return self.whatsapp_service.create_text_message(
            session_id,
            f"✅ Thank you for your enquiry!\n\n"
            f"*Enquiry ID:* {enquiry_id}\n\n"
            f"We've received your question: \"{original_message.strip()[:50]}{'...' if len(original_message.strip()) > 50 else ''}\"\n\n"
            f"Our team will review it and get back to you within 24 hours. "
            f"We appreciate your patience! 😊\n\n"
            f"*You can reference enquiry ID {enquiry_id} in future communications.*"
        )
    
    def _assess_enquiry_priority(self, enquiry_text):
        """Assess enquiry priority based on keywords."""
        urgent_keywords = [
            "urgent", "emergency", "asap", "immediately", "critical",
            "problem", "issue", "error", "broken", "not working"
        ]
        
        enquiry_lower = enquiry_text.lower()
        
        if any(keyword in enquiry_lower for keyword in urgent_keywords):
            return "high"
        else:
            return "normal"