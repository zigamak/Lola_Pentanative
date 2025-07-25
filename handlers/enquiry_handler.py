import datetime
import uuid
from .base_handler import BaseHandler

class EnquiryHandler(BaseHandler):
    """Handles enquiry-related interactions, including FAQ navigation and question submission."""
    
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
            state["current_handler"] = "faq_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"Session {session_id} redirecting to FAQHandler.")
            return {"redirect": "faq_handler", "redirect_message": "show_faq_categories"}
        elif message == "ask_question":
            state["current_state"] = "enquiry"
            state["current_handler"] = "enquiry_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"Session {session_id} entering enquiry input state.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "❓ What would you like to know? Please type your question and we'll get back to you soon!"
            )
        elif message == "back_to_main":
            self.logger.info(f"Session {session_id} returning to main menu from enquiry menu.")
            return self.handle_back_to_main(state, session_id)
        else:
            self.logger.warning(f"Session {session_id}: Invalid option '{message}' in enquiry menu state.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please select an option from the menu above."
            )
    
    def handle_enquiry_state(self, state, original_message, session_id):
        """Handle enquiry submission and return to main menu."""
        try:
            enquiry_text = original_message.strip()
            if not enquiry_text:
                self.logger.warning(f"Session {session_id}: Empty enquiry text received.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "It looks like you didn't enter a question. Please type your question or select 'Back' to return to the main menu."
                )
            
            enquiry_id = str(uuid.uuid4())
            enquiry_data = {
                "enquiry_id": enquiry_id,
                "user_name": state.get("user_name", "Guest"),
                "phone_number": state.get("phone_number", session_id),
                "enquiry_text": enquiry_text,
                "timestamp": datetime.datetime.now().isoformat(),
                "status": "pending",
                "priority": self._assess_enquiry_priority(enquiry_text)
            }
            
            success = self.data_manager.save_enquiry(enquiry_data)
            if not success:
                self.logger.error(f"Session {session_id}: Failed to save enquiry {enquiry_id} to database.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "⚠️ Sorry, there was an issue saving your enquiry. Please try again or contact support."
                )
            
            self.logger.info(f"Session {session_id}: Enquiry {enquiry_id} saved successfully.")
            
            # Reset session state to greeting instead of clearing the session
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
                f"✅ Thank you for your enquiry!\n\n"
                f"*Enquiry ID:* {enquiry_id}\n\n"
                f"We've received your question: \"{enquiry_text[:50]}{'...' if len(enquiry_text) > 50 else ''}\"\n\n"
                f"Our team will respond within 24 hours. "
                f"Please reference enquiry ID {enquiry_id} in future communications.\n\n"
                f"What would you like to do next?"
            )
            
            # Check if user is paid to show appropriate menu
            if self.session_manager.is_paid_user_session(session_id):
                self.logger.info(f"Session {session_id}: Returning to paid user main menu after enquiry submission.")
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
                self.logger.info(f"Session {session_id}: Returning to non-paid user main menu after enquiry submission.")
                buttons = [
                    {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Let Lola Order"}},
                    {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                    {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"Hello {user_name}, {confirmation_message}",
                    buttons
                )
        
        except Exception as e:
            self.logger.error(f"Session {session_id}: Error handling enquiry submission: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "⚠️ An error occurred while processing your enquiry. Please try again or contact support."
            )
    
    def _assess_enquiry_priority(self, enquiry_text):
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

    def handle_back_to_main(self, state, session_id, message=None):
        """Handle navigation back to the main menu."""
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
        self.logger.info(f"Session {session_id} returned to main menu from enquiry handler.")
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\nWhat would you like to do?",
                buttons
            )
        else:
            buttons = [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Hello {user_name}, What would you like to do?",
                buttons
            )