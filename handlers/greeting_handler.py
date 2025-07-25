from .base_handler import BaseHandler
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GreetingHandler(BaseHandler):
    """Handles greeting and main menu interactions, including new user onboarding and customized menus for paid users."""
    
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

        # Check if user has made a payment
        if self._has_user_made_payment(session_id):
            # Handle paid user options
            if message == "track_order":
                return self._handle_track_order(state, session_id)
            elif message == "order_again":
                return self._handle_order_again(state, session_id)
            elif message == "enquiry":
                return self._handle_enquiry_request(state, session_id)
            elif message == "complain":
                return self._handle_complaint_request(state, session_id)
            else:
                # Handle invalid options for paid users
                return self._handle_invalid_option_paid(state, session_id, message)
        else:
            # Existing main menu handling for non-paid users
            if message == "ai_bulk_order_direct":
                return self._handle_ai_bulk_order_direct(state, session_id)
            elif message == "enquiry":
                return self._handle_enquiry_request(state, session_id)
            elif message == "complain":
                return self._handle_complaint_request(state, session_id)
            else:
                # Handle invalid options for non-paid users
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
        """Handle track order request."""
        self.logger.info(f"Session {session_id} redirecting to TrackOrderHandler for order tracking.")
        state["current_state"] = "track_order"
        state["current_handler"] = "track_order_handler"
        self.session_manager.update_session_state(session_id, state)
        return {"redirect": "track_order_handler", "redirect_message": "start_track_order"}
    
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
            "We're sorry to hear you're having an issue. Please tell us about your complaint and we'll address it promptly."
        )
    
    def _handle_invalid_option(self, state: Dict, session_id: str, message_received: str) -> Dict[str, Any]:
        """Handle invalid option selection for non-paid users."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        self.logger.warning(f"Session {session_id}: Invalid option '{message_received}' in greeting state for non-paid user.")
        return self.send_main_menu(
            session_id, 
            user_name, 
            f"Invalid option, {user_name}. Please choose from the options below:"
        )
    
    def _handle_invalid_option_paid(self, state: Dict, session_id: str, message_received: str) -> Dict[str, Any]:
        """Handle invalid option selection for paid users."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        self.logger.warning(f"Session {session_id}: Invalid option '{message_received}' in greeting state for paid user.")
        return self.send_main_menu_paid(
            session_id, 
            user_name, 
            f"Invalid option, {user_name}. Please choose from the options below:"
        )
    
    def generate_initial_greeting(self, state: Dict, session_id: str, user_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate initial greeting message and set initial state.
        For new users, asks for preferred name and delivery address.
        For paid users, shows customized menu.
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
            
            # Check if user has made a payment
            if self._has_user_made_payment(session_id):
                return self.send_main_menu_paid(
                    session_id, 
                    username, 
                    f"Welcome Back {username}\nWhat would you like to do?"
                )
            else:
                return self.send_main_menu(
                    session_id, 
                    username, 
                    f"Hello {username}, What would you like to do?"
                )

    def handle_collect_preferred_name_state(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the user's preferred name input and then asks for the delivery address.
        """
        preferred_name = message.strip()
        if not preferred_name:
            return self.whatsapp_service.create_text_message(
                session_id,
                "It looks like you didn't enter a name. Please enter your preferred name."
            )
        
        self.logger.info(f"Session {session_id}: Preferred name received: '{preferred_name}'.")
        
        # Get existing user data
        user_data = self.data_manager.get_user_data(session_id) or {}
        user_data["user_perferred_name"] = preferred_name
        user_data["display_name"] = preferred_name 
        
        # Save the preferred name to the database
        user_data["user_id"] = session_id
        user_data["user_number"] = session_id
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
            return self.whatsapp_service.create_text_message(
                session_id,
                "It looks like you didn't enter an address. Please enter your delivery address."
            )
        
        self.logger.info(f"Session {session_id}: Delivery address received: '{delivery_address}'.")
        
        # Get existing user data
        user_data = self.data_manager.get_user_data(session_id) or {}
        user_data["address"] = delivery_address
        
        # Save the delivery address to the database
        user_data["user_id"] = session_id
        user_data["user_number"] = session_id
        self.data_manager.save_user_details(session_id, user_data)
        
        state["delivery_address"] = delivery_address
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        
        username = state.get("user_name", "Guest")
        self.logger.info(f"Session {session_id} onboarding complete. Greeting {username}.")
        
        # Check if user has made a payment
        if self._has_user_made_payment(session_id):
            return self.send_main_menu_paid(
                session_id, 
                username, 
                f"Welcome Back {username}\nWhat would you like to do?"
            )
        else:
            return self.send_main_menu(
                session_id, 
                username, 
                f"Thank you! Hello {username}, What would you like to do?"
            )

    def send_main_menu(self, session_id: str, user_name: str, message: str = "How can I help you today?") -> Dict[str, Any]:
        """Send main menu with buttons for non-paid users (max 3 buttons for WhatsApp)."""
        greeting = f"{message}"
        
        # WhatsApp allows maximum 3 buttons
        buttons = [
            {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Let Lola Order"}},
            {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
            {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
        ]
        
        return self.whatsapp_service.create_button_message(session_id, greeting, buttons)
    
    def send_main_menu_paid(self, session_id: str, user_name: str, message: str = "How can I help you today?") -> Dict[str, Any]:
        """Send main menu with buttons for paid users (max 3 buttons for WhatsApp)."""
        greeting = f"{message}"
        
        # WhatsApp allows maximum 3 buttons
        buttons = [
            {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
            {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
            {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
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
        
        # Check if user has made a payment
        if self._has_user_made_payment(session_id):
            return self.send_main_menu_paid(session_id, user_name, f"Welcome Back {user_name}\nWhat would you like to do?")
        else:
            return self.send_main_menu(session_id, user_name, message)