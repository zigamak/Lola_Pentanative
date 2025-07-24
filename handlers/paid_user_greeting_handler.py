import logging
from typing import Dict, Any
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class PaidUserGreetingHandler(BaseHandler):
    """Handles greetings and options for paid users with recent orders."""
    
    def handle_paid_user_greeting(self, state: Dict, session_id: str, user_name: str) -> Dict[str, Any]:
        """
        Handle greeting for paid users with recent orders.
        
        Args:
            state (Dict): Session state
            session_id (str): User's session ID
            user_name (str): User's name
            
        Returns:
            Dict: WhatsApp message response
        """
        try:
            order_id = state.get("recent_order_id", "N/A")
            
            # Personalized greeting for paid user
            greeting_message = (
                f"👋 *Hello again, {user_name}!*\n\n"
                f"🎉 Thank you for your recent order!\n"
                f"📋 *Order ID:* {order_id}\n\n"
                f"How can I help you today?"
            )
            
            # Options for paid users
            buttons = [
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "track_order", "title": "📦 Track Order"}},
                {"type": "reply", "reply": {"id": "other_options", "title": "⚙️ Other Options"}}
            ]
            
            # Set state for paid user menu
            state["current_state"] = "paid_user_menu"
            state["current_handler"] = "paid_user_greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            return self.whatsapp_service.create_button_message(
                session_id,
                greeting_message,
                buttons
            )
            
        except Exception as e:
            logger.error(f"Error handling paid user greeting for session {session_id}: {e}", exc_info=True)
            # Fallback to regular greeting
            return self._fallback_to_regular_greeting(state, session_id, user_name)
    
    def handle_show_paid_menu(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle showing paid menu after feedback or other redirects."""
        user_name = state.get("user_name", "Guest")
        return self.handle_paid_user_greeting(state, session_id, user_name)
    
    def handle_paid_user_menu_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """Handle paid user menu selections."""
        logger.debug(f"Handling paid user menu for session {session_id}, message: {message}")
        
        if message == "order_again":
            return self._handle_order_again(state, session_id)
        elif message == "track_order":
            return self._handle_track_order(state, session_id)
        elif message == "other_options":
            return self._handle_other_options(state, session_id)
        else:
            # Invalid option, show menu again
            user_name = state.get("user_name", "Guest")
            return self.handle_paid_user_greeting(state, session_id, user_name)
    
    def _handle_order_again(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle when paid user wants to order again."""
        logger.info(f"Paid user {session_id} chose to order again")
        
        # Transition to regular ordering flow but keep paid user status
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        
        # Redirect to greeting handler with order message
        return {"redirect": "greeting_handler", "redirect_message": "order"}
    
    def _handle_track_order(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle order tracking request."""
        logger.info(f"Paid user {session_id} chose to track order")
        
        # Transition to order tracking
        state["current_state"] = "order_tracking"
        state["current_handler"] = "order_tracking_handler"
        self.session_manager.update_session_state(session_id, state)
        
        # Redirect to order tracking handler
        return {"redirect": "order_tracking_handler", "redirect_message": "track_status"}
    
    def _handle_other_options(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle other options for paid users."""
        state["current_state"] = "paid_user_other_options"
        self.session_manager.update_session_state(session_id, state)
        
        other_options_message = (
            f"⚙️ *Other Options*\n\n"
            f"Here are additional ways I can help:"
        )
        
        buttons = [
            {"type": "reply", "reply": {"id": "contact_support", "title": "📞 Support"}},
            {"type": "reply", "reply": {"id": "feedback", "title": "💬 Feedback"}},
            {"type": "reply", "reply": {"id": "back_to_paid_menu", "title": "🔙 Back"}}
        ]
        
        return self.whatsapp_service.create_button_message(
            session_id,
            other_options_message,
            buttons
        )
    
    def handle_paid_user_other_options_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """Handle paid user other options selections."""
        if message == "contact_support":
            return self._handle_contact_support(state, session_id)
        elif message == "feedback":
            return self._handle_feedback_request(state, session_id)
        elif message == "back_to_paid_menu":
            # Go back to paid user main menu
            user_name = state.get("user_name", "Guest")
            return self.handle_paid_user_greeting(state, session_id, user_name)
        else:
            # Invalid option, show other options again
            return self._handle_other_options(state, session_id)
    
    def _handle_contact_support(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle contact support for paid users."""
        order_id = state.get("recent_order_id", "N/A")
        
        support_message = (
            f"📞 *Customer Support*\n\n"
            f"📋 *Your Order ID:* {order_id}\n\n"
            f"📱 *WhatsApp:* +234-XXX-XXXX\n"
            f"📧 *Email:* support@lolaskitchen.com\n"
            f"⏰ *Hours:* 9:00 AM - 10:00 PM daily\n\n"
            f"💬 You can also send us a message here and we'll respond shortly!\n\n"
            f"As a valued customer, you'll receive priority support! 🌟"
        )
        
        buttons = [
            {"type": "reply", "reply": {"id": "track_order", "title": "📦 Track Order"}},
            {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
            {"type": "reply", "reply": {"id": "back_to_paid_menu", "title": "🔙 Back"}}
        ]
        
        return self.whatsapp_service.create_button_message(
            session_id,
            support_message,
            buttons
        )
    
    def _handle_feedback_request(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle feedback request for paid users."""
        order_id = state.get("recent_order_id", "N/A")
        
        # Redirect to feedback handler if available
        if hasattr(self, 'feedback_handler'):
            state["current_state"] = "feedback_rating"
            state["current_handler"] = "feedback_handler"
            state["feedback_order_id"] = order_id
            self.session_manager.update_session_state(session_id, state)
            return {"redirect": "feedback_handler", "redirect_message": "provide_feedback"}
        else:
            # Fallback feedback collection
            feedback_message = (
                f"💬 *Feedback*\n\n"
                f"📋 *Order ID:* {order_id}\n\n"
                f"We'd love to hear about your experience! Please share your feedback:"
            )
            
            state["current_state"] = "collecting_feedback"
            self.session_manager.update_session_state(session_id, state)
            
            return self.whatsapp_service.create_text_message(session_id, feedback_message)
    
    def _fallback_to_regular_greeting(self, state: Dict, session_id: str, user_name: str) -> Dict[str, Any]:
        """Fallback to regular greeting if paid user greeting fails."""
        logger.warning(f"Falling back to regular greeting for session {session_id}")
        
        # Remove paid user status and use regular greeting
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        
        return {"redirect": "greeting_handler", "redirect_message": "greeting"}