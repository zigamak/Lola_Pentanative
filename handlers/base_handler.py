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

    def create_main_menu_buttons(self) -> List[Dict[str, Any]]:
        """
        Create standard main menu buttons with updated options,
        ensuring all button titles comply with WhatsApp's 20-character limit.
        """
        buttons = [
            # Option 1: Standard menu Browse
            {"type": "reply", "reply": {"id": "order_menu_categories", "title": "🍔 Order Menu"}},
            # Option 2: AI-powered bulk ordering (direct to bulk order)
            {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Let Lola Order"}},
            # Option 3: Other options (enquiries, complaints, etc.)
            {"type": "reply", "reply": {"id": "others_menu", "title": "❓ Others"}}
        ]
        return buttons

    def send_main_menu(self, session_id: str, user_name: str = "Guest", message: str = "How can I help you today?") -> Dict:
        """
        Sends the main menu to the user.
        The greeting logic is now handled upstream by GreetingHandler.generate_initial_greeting
        which calls this method with the appropriate message.
        """
        buttons = self.create_main_menu_buttons()

        # The 'message' parameter now fully contains the greeting
        # (e.g., "Hello [User Name]! 👋\n\nHow can I help you today?")
        # or the "Invalid option..." message.
        return self.whatsapp_service.create_button_message(
            session_id,
            message, # Use the passed message directly, which includes the greeting
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
        user_name = state.get("user_name", "Guest") 
        
        # The message already includes the greeting for returning users.
        return self.send_main_menu(session_id, user_name, message=message)