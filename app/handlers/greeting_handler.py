from .base_handler import BaseHandler
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GreetingHandler(BaseHandler):
    """Handles greeting and main menu interactions, including new user onboarding."""
    
    def handle_greeting_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Handle greeting state messages based on user's main menu selection.
        Also dispatches to new user onboarding states.
        """
        self.logger.info(f"GreetingHandler: Handling message '{message}' in greeting state for session {session_id}.")

        # Handle new user onboarding flow
        if state.get("current_state") == "collect_preferred_name":
            return self.handle_collect_preferred_name_state(state, message, session_id)
        elif state.get("current_state") == "collect_delivery_address":
            return self.handle_collect_delivery_address_state(state, message, session_id)

        # Existing main menu handling
        if message == "order" or message == "order_menu_categories":
            return self._handle_order_menu_request(state, session_id)
        elif message == "ai_bulk_order_direct":
            return self._handle_ai_bulk_order_direct(state, session_id)
        elif message == "enquiry":
            return self._handle_enquiry_request(state, session_id)
        elif message == "complain":
            return self._handle_complaint_request(state, session_id)
        elif message == "others" or message == "others_menu":
            return self._handle_others_menu_request(state, session_id)
        else:
            # Handle invalid options - re-send main menu
            return self._handle_invalid_option(state, session_id, message)
    
    def _handle_order_menu_request(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle request to view the main order menu categories."""
        self.logger.info(f"Session {session_id} redirecting to menu_handler for classic menu.")

        if not self.data_manager.menu_data:
            self.whatsapp_service.create_text_message(
                session_id, 
                "Sorry, the menu is currently unavailable. Please try again later."
            )
            # Ensure proper return when menu is unavailable
            return self.handle_back_to_main(state, session_id, message="Menu unavailable, please choose another option.")
            
        state["current_state"] = "menu"
        state["current_handler"] = "menu_handler"
        self.session_manager.update_session_state(session_id, state)
        
        return {"redirect": "menu_handler", "redirect_message": "show_menu"}
        
    def _handle_ai_bulk_order_direct(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle direct AI Bulk Order entry from main menu (Let Lola Order)."""
        self.logger.info(f"Session {session_id} redirecting to AIHandler for AI Bulk Order (Let Lola Order).")
        state["current_state"] = "ai_bulk_order"
        state["current_handler"] = "ai_handler"
        self.session_manager.update_session_state(session_id, state)
        return {"redirect": "ai_handler", "redirect_message": "start_ai_bulk_order"}

    def _handle_others_menu_request(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle the 'Others' menu request, showing sub-options."""
        state["current_state"] = "others_menu_selection"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)

        # WhatsApp allows maximum 3 buttons
        buttons = [
            {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
            {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}},
            {"type": "reply", "reply": {"id": "back_to_main", "title": "🔙 Back"}}
        ]
        return self.whatsapp_service.create_button_message(
            session_id,
            "🔧 *Other Options*\n\nHere are other ways I can help you:",
            buttons
        )

    def handle_others_menu_selection_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """
        Handle selections within the 'Others' menu.
        """
        self.logger.info(f"GreetingHandler: Handling message '{message}' in 'others_menu_selection' state for session {session_id}.")
        
        if message == "enquiry":
            return self._handle_enquiry_request(state, session_id)
        elif message == "complain":
            return self._handle_complaint_request(state, session_id)
        elif message == "back_to_main":
            return self.handle_back_to_main(state, session_id)
        else:
            self.whatsapp_service.create_text_message(
                session_id,
                "Please choose a valid option from the 'Others' menu."
            )
            return self._handle_others_menu_request(state, session_id)

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
            "We're sorry to hear you're having an issue. Please tell us about your complaint and we'll address it promptly."
        )
    
    def _handle_invalid_option(self, state: Dict, session_id: str, message_received: str) -> Dict[str, Any]:
        """Handle invalid option selection."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        self.logger.warning(f"Session {session_id}: Invalid option '{message_received}' in greeting state.")     
        return self.send_main_menu(
            session_id, 
            user_name, 
            f"Invalid option, {user_name}. Please choose from the options below:"
        )
    
    def generate_initial_greeting(self, state: Dict, session_id: str, user_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate initial greeting message and set initial state.
        For new users, asks for preferred name and delivery address.
        """
        user_data = self.data_manager.get_user_data(session_id)
        
        if not user_data or not user_data.get("user_perferred_name") or not user_data.get("address"):
            # New user or missing preferred name/address
            username_display = user_data.get("name", "Guest") if user_data else "Guest"
            self.logger.info(f"Session {session_id}: New user or missing details. Initiating onboarding.")
            
            # Set initial state for onboarding
            state["current_state"] = "collect_preferred_name"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            
            # Prompt for preferred name
            return self.whatsapp_service.create_text_message(
                session_id,
                f"Hello {username_display}, welcome to Lola!\nPlease enter your preferred name."
            )
        else:
            # Returning user with all details
            username = user_data.get("display_name", "Guest")
            state["user_name"] = username
            state["delivery_address"] = user_data.get("address", "")
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"Session {session_id} greeted returning user '{username}'.")
            
            return self.send_main_menu(session_id, username, f"Hello {username}, What would you like to do?")

    def handle_collect_preferred_name_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the user's preferred name input and then asks for the delivery address.
        """
        preferred_name = message.strip()
        if not preferred_name:
            self.whatsapp_service.create_text_message(
                session_id,
                "It looks like you didn't enter a name. Please enter your preferred name."
            )
            return {"status": "continue"} # Stay in the same state

        self.logger.info(f"Session {session_id}: Preferred name received: '{preferred_name}'.")

        # Get existing user data
        user_data = self.data_manager.get_user_data(session_id) or {}
        user_data["user_perferred_name"] = preferred_name
        # Also update the 'display_name' which is used for greetings
        user_data["display_name"] = preferred_name 
        
        # Save the preferred name to the database
        # Ensure user_id and user_number are correctly passed
        user_data["user_id"] = session_id
        user_data["user_number"] = session_id # Assuming session_id is the phone number for WhatsApp
        self.data_manager.save_user_details(session_id, user_data)

        state["user_name"] = preferred_name
        state["current_state"] = "collect_delivery_address"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)

        return self.whatsapp_service.create_text_message(
            session_id,
            f"Thanks, {preferred_name}! Now, please enter your delivery address."
        )

    def handle_collect_delivery_address_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the user's delivery address input and then sends the main menu.
        """
        delivery_address = message.strip()
        if not delivery_address:
            self.whatsapp_service.create_text_message(
                session_id,
                "It looks like you didn't enter an address. Please enter your delivery address."
            )
            return {"status": "continue"} # Stay in the same state

        self.logger.info(f"Session {session_id}: Delivery address received: '{delivery_address}'.")

        # Get existing user data
        user_data = self.data_manager.get_user_data(session_id) or {}
        user_data["address"] = delivery_address

        # Save the delivery address to the database
        # Ensure user_id and user_number are correctly passed
        user_data["user_id"] = session_id
        user_data["user_number"] = session_id # Assuming session_id is the phone number for WhatsApp
        self.data_manager.save_user_details(session_id, user_data)
        
        state["delivery_address"] = delivery_address
        state["current_state"] = "greeting" # Transition back to the main greeting state
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        
        username = state.get("user_name", "Guest") # Use the preferred name if available
        self.logger.info(f"Session {session_id} onboarding complete. Greeting {username}.")
        return self.send_main_menu(
            session_id, 
            username, 
            f"Thank you! Hello {username}, What would you like to do?"
        )

    def send_main_menu(self, session_id: str, user_name: str, message: str = "How can I help you today?") -> Dict[str, Any]:
        """Send main menu with buttons (max 3 buttons for WhatsApp)."""
        greeting = f"{message}"
        
        # WhatsApp allows maximum 3 buttons
        buttons = [
            {"type": "reply", "reply": {"id": "order_menu_categories", "title": "🍔 Order Menu"}},
            {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Let Lola Order"}},
            {"type": "reply", "reply": {"id": "others_menu", "title": "❓ Others"}}
        ]
        
        return self.whatsapp_service.create_button_message(session_id, greeting, buttons)
    
    def handle_back_to_main(self, state: Dict, session_id: str, message: str = "Welcome back! How can I help you today?") -> Dict[str, Any]:
        """Handle back to main menu navigation."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        # Clear any order-related data but keep user info
        if "cart" in state:
            state["cart"] = {}
        if "selected_category" in state:
            del state["selected_category"]
        if "selected_item" in state:
            del state["selected_item"]
            
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id} returned to main menu (greeting state).")
        
        return self.send_main_menu(session_id, user_name, message)