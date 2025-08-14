from .base_handler import BaseHandler
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GreetingHandler(BaseHandler):
    """Handles greeting and main menu interactions, including new user onboarding and customized menus for paid users."""

    def _is_new_order_keyword(self, message: str) -> bool:
        """
        Checks if the message contains keywords that should trigger a return to the main menu
        or a new order process. This handles messages like "Jollof rice and fried rice".
        """
        message = message.lower().strip()
        # Define keywords that indicate a new order
        new_order_keywords = [
            "jollof", "fried rice", "order", "menu", "let lola order",
            "new order", "i want", "can i get"
        ]
        
        # Check if any of the keywords are present in the message
        return any(keyword in message for keyword in new_order_keywords)

    def handle_greeting_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Handle greeting state messages based on user's main menu selection.
        Also dispatches to new user onboarding states.
        """
        self.logger.info(f"GreetingHandler: Handling message '{message}' in greeting state for session {session_id}.")

        if state.get("current_state") == "collect_preferred_name":
            return self.handle_collect_preferred_name_state(state, message, session_id)
        elif state.get("current_state") == "collect_delivery_address":
            return self.handle_collect_delivery_address_state(state, message, session_id)
            
        # Check for new order keywords before anything else
        if self._is_new_order_keyword(original_message):
            self.logger.info(f"Session {session_id}: New order keyword '{original_message}' detected. Redirecting to AI bulk order.")
            return self._handle_ai_bulk_order_direct(state, session_id)

        if self._has_user_made_payment(session_id):
            if message == "track_order":
                return self._handle_track_order(state, session_id)
            elif message == "order_again":
                return self._handle_order_again(state, session_id)
            elif message == "enquiry":
                return self._handle_enquiry_request(state, session_id)
            elif message == "complain":
                return self._handle_complaint_request(state, session_id)
            else:
                return self._handle_invalid_option_paid(state, session_id, message)
        else:
            if message == "ai_bulk_order_direct":
                return self._handle_ai_bulk_order_direct(state, session_id)
            elif message == "enquiry":
                return self._handle_enquiry_request(state, session_id)
            elif message == "complain":
                return self._handle_complaint_request(state, session_id)
            else:
                return self._handle_invalid_option(state, session_id, message)

    def _has_user_made_payment(self, session_id: str) -> bool:
        """
        Check if the user has made a payment using SessionManager's paid status.
        """
        try:
            is_paid = self.session_manager.is_paid_user_session(session_id)
            if is_paid:
                self.logger.info(f"Session {session_id}: User has an active paid session.")
            return is_paid
        except Exception as e:
            self.logger.error(f"Error checking payment status for session {session_id}: {e}")
            return False

    def _handle_track_order(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle track order request by querying the latest order status."""
        self.logger.info(f"Session {session_id}: Processing track order request.")
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)

        order = self.data_manager.get_latest_order_by_customer_id(session_id)
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"

        if not order:
            self.logger.info(f"Session {session_id}: No orders found for customer.")
            return self.send_main_menu_paid(
                session_id,
                user_name,
                "No orders found. What would you like to do?"
            )

        status = order.get("status", "unknown").lower()
        order_id = order.get("order_id", "N/A")
        status_messages = {
            "on transit": f"Your order #{order_id} is on transit 🚚 and will arrive soon!",
            "delivered": f"Your order #{order_id} has been delivered 🎉. Enjoy!",
            "processing": f"Your order #{order_id} is being processed 🛠️. We'll update you soon.",
            "pending payment": f"Your order #{order_id} is awaiting payment 💳. Please complete the payment to proceed.",
            "packaged": f"Your order #{order_id} is packaged 📦 and ready for shipping!",
            "cancelled": f"Your order #{order_id} has been cancelled ❌. Please place a new order if needed.",
            "expired": f"Your order #{order_id} has expired ⏰. Please place a new order."
        }
        message = status_messages.get(status, f"Your order #{order_id} has an unknown status. Please contact support.")
        return self.send_main_menu_paid(
            session_id,
            user_name,
            f"{message}\n\nWhat would you like to do?"
        )

    def _handle_order_again(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle order again request by redirecting to AI Bulk Order."""
        self.logger.info(f"Session {session_id} redirecting to AIHandler for Order Again.")
        state["current_state"] = "ai_bulk_order"
        state["current_handler"] = "ai_handler"
        self.session_manager.update_session_state(session_id, state)
        return {"redirect": "ai_handler", "redirect_message": "start_ai_bulk_order"}

    def _handle_ai_bulk_order_direct(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle direct AI Bulk Order entry from main menu (Let Lola Order)."""
        self.logger.info(f"Session {session_id} redirecting to AIHandler for AI Bulk Order (Let Lola Order).")
        state["current_state"] = "ai_bulk_order"
        state["current_handler"] = "ai_handler"
        self.session_manager.update_session_state(session_id, state)
        return {"redirect": "ai_handler", "redirect_message": "start_ai_bulk_order"}

    def _handle_enquiry_request(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle enquiry request with FAQ options."""
        state["current_state"] = "enquiry_menu"
        state["current_handler"] = "enquiry_handler"
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id} redirecting to EnquiryHandler for enquiry menu.")
        return {"redirect": "enquiry_handler", "redirect_message": "show_enquiry_menu"}

    def _handle_complaint_request(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle complaint request."""
        state["current_state"] = "complain"
        state["current_handler"] = "complaint_handler"
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id} entering complaint state.")
        return self.whatsapp_service.create_text_message(
            session_id, 
            "We're sorry to hear you're having an issue. Please tell us about it and we'll forward it to our team."
        )

    def _handle_invalid_option(self, state: Dict, session_id: str, message: str) -> Dict[str, Any]:
        """Handle invalid options for non-paid users and provide a hint."""
        self.logger.warning(f"Session {session_id}: Invalid option '{message}' from a non-paid user.")
        return self.send_main_menu(
            session_id,
            "I'm sorry, I didn't understand that. Please select a valid option from the menu."
        )

    def _handle_invalid_option_paid(self, state: Dict, session_id: str, message: str) -> Dict[str, Any]:
        """Handle invalid options for paid users and provide a hint."""
        self.logger.warning(f"Session {session_id}: Invalid option '{message}' from a paid user.")
        return self.send_main_menu_paid(
            session_id,
            state.get("user_name", "Guest"),
            "I'm sorry, I didn't understand that. Please select a valid option from the menu."
        )

    def handle_back_to_main(self, state: Dict, session_id: str, message: Optional[str] = None) -> Dict[str, Any]:
        """Resets the state and returns to the main menu with an optional custom message."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)

        if self._has_user_made_payment(session_id):
            return self.send_main_menu_paid(session_id, user_name, message)
        else:
            return self.send_main_menu(session_id, message)
