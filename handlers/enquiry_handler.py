import logging
import datetime
import uuid
from typing import Dict, Any
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class EnquiryHandler(BaseHandler):
    """Handles enquiry-related interactions, including FAQ navigation and question submission."""
    
    def handle(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Top-level handler for enquiry-related states and redirects.
        Routes to appropriate methods based on state and redirect message.
        """
        self.logger.info(f"Session {session_id}: Handling message '{message}' in state '{state.get('current_state')}'.")
        
        current_state = state.get("current_state")
        
        if message == "show_enquiry_menu":
            return self.show_enquiry_menu(state, session_id)
        elif current_state == "enquiry_menu":
            return self.handle_enquiry_menu_state(state, message, session_id)
        elif current_state == "enquiry":
            return self.handle_enquiry_state(state, original_message, session_id)
        elif message == "back_to_main":
            return self.handle_back_to_main(state, session_id)
        else:
            self.logger.warning(f"Session {session_id}: Unhandled state '{current_state}' with message '{message}'.")
            return self._handle_invalid_state(state, session_id)

    def show_enquiry_menu(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Display the enquiry menu with Ask Question option."""
        self.logger.info(f"Session {session_id}: Displaying enquiry menu.")
        
        state["current_state"] = "enquiry_menu"
        state["current_handler"] = "enquiry_handler"
        self.session_manager.update_session_state(session_id, state)
        
        buttons = [
            {"type": "reply", "reply": {"id": "ask_question", "title": "❓ Ask Question"}},
            {"type": "reply", "reply": {"id": "back_to_main", "title": "🔙 Back"}}
        ]
        
        return self.whatsapp_service.create_button_message(
            session_id,
            "How can we help you today?\n\n❓ *Ask Question* - Send us your specific question",
            buttons
        )

    def handle_enquiry_menu_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """Handle user inputs in the enquiry menu state."""
        self.logger.info(f"Session {session_id}: Processing enquiry menu option '{message}'.")
        
        if message == "ask_question":
            state["current_state"] = "enquiry"
            state["current_handler"] = "enquiry_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"Session {session_id}: Entering enquiry input state.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "❓ What would you like to know? Please type your question and we'll get back to you soon!"
            )
        elif message == "back_to_main":
            self.logger.info(f"Session {session_id}: Returning to main menu from enquiry menu.")
            return self.handle_back_to_main(state, session_id)
        else:
            self.logger.warning(f"Session {session_id}: Invalid option '{message}' in enquiry menu state.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please select an option from the menu above."
            )
    
    def handle_enquiry_state(self, state: Dict, original_message: str, session_id: str) -> Dict[str, Any]:
        """Handle enquiry submission and return to main menu."""
        try:
            enquiry_text = original_message.strip()
            if not enquiry_text:
                self.logger.warning(f"Session {session_id}: Empty enquiry text received.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "It looks like you didn't enter a question. Please type your question or select 'Back' to return to the main menu."
                )
            
            enquiry_data = {
                "user_name": state.get("user_name", "Guest"),
                "user_id": session_id,
                "enquiry_text": enquiry_text,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "enquiry_categories": self._assess_enquiry_priority(enquiry_text), # Using priority as category
                "channel": "whatsapp"
            }
            
            # The data_manager.save_enquiry method returns the refId on success, or None on failure.
            enquiry_id = self.data_manager.save_enquiry(enquiry_data)
            
            if enquiry_id is None:
                self.logger.error(f"Session {session_id}: Failed to save enquiry to database.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Sorry, there was an issue saving your enquiry. Please try again or contact support."
                )
            
            self.logger.info(f"Session {session_id}: Enquiry with ID {enquiry_id} saved successfully.")
            
            # Reset session state to greeting
            user_data = self.data_manager.get_user_data(session_id)
            user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            
            # Prepare confirmation message
            confirmation_message = (
                f"✅ Thank you for your enquiry!\n\n"
                f"*Enquiry ID:* {enquiry_id}\n\n"
                f"We've received your question: \"{enquiry_text[:50]}{'...' if len(enquiry_text) > 50 else ''}\"\n\n"
                f"Our team will respond within 24 hours. "
                f"Please reference enquiry ID {enquiry_id} in future communications.\n\n"
                f"What would you like to do next?"
            )
            
            return self.handle_back_to_main(state, session_id, confirmation_message)
        
        except Exception as e:
            self.logger.error(f"Session {session_id}: Error handling enquiry submission: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ An error occurred while processing your enquiry. Please try again or contact support."
            )
    
    def _assess_enquiry_priority(self, enquiry_text: str) -> str:
        """Assess enquiry priority based on keywords."""
        urgent_keywords = [
            "urgent", "emergency", "asap", "immediately", "critical",
            "problem", "issue", "error", "broken", "not working"
        ]
        
        enquiry_lower = enquiry_text.lower()
        
        if any(keyword in enquiry_lower for keyword in urgent_keywords):
            self.logger.debug(f"Enquiry contains urgent keywords: {enquiry_lower}")
            return "high"
        return "normal"
    
    def _handle_invalid_state(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle invalid or unexpected states."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        
        self.session_manager.update_session_state(session_id, state)
        
        message = (
            f"Sorry, something went wrong. Let's start over.\n\n"
            f"What would you like to do?"
        )
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            self.logger.info(f"Session {session_id}: Returning to paid user main menu (invalid state).")
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\n{message}",
                buttons
            )
        else:
            self.logger.info(f"Session {session_id}: Returning to non-paid user main menu (invalid state).")
            buttons = [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Hi {user_name}, {message}",
                buttons
            )

    def handle_back_to_main(self, state: Dict, session_id: str, message: str = None) -> Dict[str, Any]:
        """Handle navigation back to the main menu."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id}: Returned to main menu from enquiry handler.")
        
        if message is None:
            message = "What would you like to do?"
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\n{message}",
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
                f"Hi {user_name}, {message}",
                buttons
            )