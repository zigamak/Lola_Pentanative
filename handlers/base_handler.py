import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class BaseHandler:
    """Base class for all message handlers."""

    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        self.config = config
        self.session_manager = session_manager
        self.data_manager = data_manager
        self.whatsapp_service = whatsapp_service
        self.logger = logger

    def create_main_menu_buttons(self, is_paid_user: bool) -> List[Dict[str, Any]]:
        """
        Create standard main menu buttons based on user type,
        ensuring all button titles comply with WhatsApp's 20-character limit.
        """
        if is_paid_user:
            buttons = [
                # Paid user menu
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
        else:
            buttons = [
                # Non-paid (guest) user menu
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
        return buttons

    def send_main_menu(self, session_id: str, user_name: str = "Guest", message: str = "How can I help you today?") -> Dict:
        """
        Sends the main menu to the user.
        The menu buttons are dynamically generated based on the user's paid status.
        """
        is_paid_user = self.session_manager.is_paid_user_session(session_id)
        buttons = self.create_main_menu_buttons(is_paid_user)

        # The 'message' parameter now fully contains the greeting
        # (e.g., "Hello [User Name]! 👋\n\nHow can I help you today?")
        # or the "Invalid option..." message.
        return self.whatsapp_service.create_button_message(
            session_id,
            message,
            buttons
        )

    def handle_back_to_main(self, state: Dict, session_id: str, message: str = "Welcome back! How can I help you today?") -> Dict:
        """
        Handles returning to the main menu by resetting the current state
        and sending the main menu options.
        """
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        # Clear order-related data but keep user info
        if "cart" in state:
            state["cart"] = {}
        if "selected_category" in state:
            del state["selected_category"]
        if "selected_item" in state:
            del state["selected_item"]
            
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id} returned to main menu (greeting state).")
        
        # When returning to main, use the user's known name if available, otherwise "Guest"
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        
        # The message already includes the greeting for returning users.
        return self.send_main_menu(session_id, user_name, message=message)