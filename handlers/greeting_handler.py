import logging
from typing import Dict, Any, List, Optional
import sys
from services.ai_service import AIService
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
handler.stream.reconfigure(encoding='utf-8')
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class GreetingHandler(BaseHandler):
    """Handles greeting and main menu interactions, including new user onboarding and customized menus for paid users."""

    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.ai_service = AIService(config, data_manager)  # Initialize AIService for name parsing

    def handle_greeting_state(self, state: Dict, message: str, original_message: str, session_id: str, whatsapp_username: str = None) -> Dict[str, Any]:
        """Handle greeting state messages based on user's main menu selection. Also dispatches to new user onboarding states."""
        self.logger.info(f"Session {session_id}: Handling message '{message}' in greeting state with WhatsApp username '{whatsapp_username}'.")

        if state.get("current_state") == "collect_preferred_name":
            return self.handle_collect_preferred_name_state(state, message, session_id, whatsapp_username)
        elif state.get("current_state") in ["collect_delivery_address", "waiting_for_address_input"]:
            return self.handle_collect_delivery_address_state(state, message, session_id, whatsapp_username)

        if self._has_user_made_payment(session_id):
            if message == "track_order":
                return self._handle_track_order(state, session_id, whatsapp_username)
            elif message == "order_again":
                return self._handle_order_again(state, session_id)
            elif message == "enquiry":
                return self._handle_enquiry_request(state, session_id)
            elif message == "complain":
                return self._handle_complaint_request(state, session_id)
            else:
                return self._handle_invalid_option_paid(state, session_id, message, whatsapp_username)
        else:
            if message == "ai_bulk_order_direct":
                return self._handle_ai_bulk_order_direct(state, session_id)
            elif message == "enquiry":
                return self._handle_enquiry_request(state, session_id)
            elif message == "complain":
                return self._handle_complaint_request(state, session_id)
            else:
                return self._handle_invalid_option(state, session_id, message, whatsapp_username)

    def _has_user_made_payment(self, session_id: str) -> bool:
        """Checks if the user has made a payment by looking at the session state."""
        try:
            session_state = self.session_manager.get_session_state(session_id)
            has_paid = session_state.get("payment_reference") is not None or session_state.get("order_id") is not None
            if has_paid:
                self.logger.info(f"Session {session_id}: User has a paid session.")
            return has_paid
        except Exception as e:
            self.logger.error(f"Error checking payment status for session {session_id}: {e}")
            return False

    def _handle_track_order(self, state: Dict, session_id: str, whatsapp_username: str = None) -> Dict[str, Any]:
        """Handle track order request by querying the latest order status."""
        self.logger.info(f"Session {session_id}: Processing track order request.")
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        order = self.data_manager.get_latest_order_by_customer_id(session_id)
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", user_data.get("name", whatsapp_username or "Guest")) if user_data else (whatsapp_username or "Guest")
        if not order:
            self.logger.info(f"Session {session_id}: No orders found for customer.")
            return self._send_main_menu_paid(session_id, user_name, "No orders found.")
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
        return self._send_main_menu_paid(session_id, user_name, f"{message}")

    def _handle_order_again(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle order again request by redirecting to AI Bulk Order."""
        self.logger.info(f"Session {session_id} redirecting to AIHandler for Order Again.")
        state["current_state"] = "ai_bulk_order"
        state["current_handler"] = "ai_handler"
        self.session_manager.update_session_state(session_id, state)
        return {"redirect": "ai_handler", "redirect_message": "start_ai_bulk_order"}

    def _handle_ai_bulk_order_direct(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle direct AI Bulk Order entry from main menu (Make an Order)."""
        self.logger.info(f"Session {session_id} redirecting to AIHandler for AI Bulk Order (Make an Order).")
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

    def _handle_invalid_option(self, state: Dict, session_id: str, message_received: str, whatsapp_username: str = None) -> Dict[str, Any]:
        """Handle invalid option selection for non-paid users."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", user_data.get("name", whatsapp_username or "Guest")) if user_data else (whatsapp_username or "Guest")
        self.logger.warning(f"Session {session_id}: Invalid option '{message_received}' in greeting state for non-paid user.")
        return self._send_main_menu(session_id, user_name, f"Invalid option, {user_name}.")

    def _handle_invalid_option_paid(self, state: Dict, session_id: str, message_received: str, whatsapp_username: str = None) -> Dict[str, Any]:
        """Handle invalid option selection for paid users."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", user_data.get("name", whatsapp_username or "Guest")) if user_data else (whatsapp_username or "Guest")
        self.logger.warning(f"Session {session_id}: Invalid option '{message_received}' in greeting state for paid user.")
        return self._send_main_menu_paid(session_id, user_name, f"Invalid option, {user_name}.")

    def generate_initial_greeting(self, state: Dict, session_id: str, whatsapp_username: Optional[str] = None) -> Dict[str, Any]:
        """Generate initial greeting message and set initial state. Uses whatsapp_username for new users."""
        user_data = self.data_manager.get_user_data(session_id)
        self.logger.info(f"Session {session_id}: user_data={user_data}, provided whatsapp_username={whatsapp_username}")
        whatsapp_username = whatsapp_username or user_data.get("name", "Guest") if user_data else "Guest"

        if not user_data or not user_data.get("user_perferred_name") or not user_data.get("address"):
            self.logger.info(f"Session {session_id}: New user or missing details. Initiating onboarding with username '{whatsapp_username}'.")
            state["current_state"] = "collect_preferred_name"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self._send_greeting_with_image(session_id, whatsapp_username, "onboarding")
        else:
            username = user_data.get("display_name", whatsapp_username)
            state["user_name"] = username
            state["address"] = user_data.get("address", "")
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"Session {session_id} greeted returning user '{username}'.")
            user_type = "paid" if self._has_user_made_payment(session_id) else "guest"
            return self._send_greeting_with_image(session_id, username, user_type)

    def handle_collect_preferred_name_state(self, state: Dict, message: str, session_id: str, whatsapp_username: str = None) -> Dict[str, Any]:
        """Handles the user's preferred name input using AIService and then asks for the delivery address."""
        user_data = self.data_manager.get_user_data(session_id)
        whatsapp_username = user_data.get("name", whatsapp_username or "Guest") if user_data else (whatsapp_username or "Guest")

        if not self.ai_service.ai_enabled:
            self.logger.warning(f"Session {session_id}: AI service disabled, using raw input as name.")
            preferred_name = message.strip()
        else:
            try:
                parsed_name = self.ai_service.parse_user_name(message)
                if parsed_name.get("success") and parsed_name.get("name"):
                    preferred_name = parsed_name["name"].strip()
                else:
                    self.logger.warning(f"Session {session_id}: AI failed to parse name from '{message}', using raw input.")
                    preferred_name = message.strip()
            except Exception as e:
                self.logger.error(f"Session {session_id}: Error parsing name with AI: {e}")
                preferred_name = message.strip()

        if not preferred_name:
            return self.whatsapp_service.create_text_message(
                session_id,
                f"Sorry, {whatsapp_username}, I didn't catch that. Please enter your preferred name."
            )

        self.logger.info(f"Session {session_id}: Preferred name parsed: '{preferred_name}'.")

        user_data = user_data or {}
        user_data.update({
            "user_perferred_name": preferred_name,
            "display_name": preferred_name,
            "user_id": session_id,
            "user_number": session_id,
            "name": whatsapp_username,  # Preserve WhatsApp username
            "phone_number": session_id
        })
        self.data_manager.save_user_details(session_id, user_data)
        state["user_name"] = preferred_name
        state["current_state"] = "collect_delivery_address"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        return self._send_address_menu(session_id, preferred_name)

    def _send_address_menu(self, session_id: str, user_name: str) -> Dict[str, Any]:
        """Sends a button message for the delivery address options."""
        buttons = [
            {"type": "reply", "reply": {"id": "palmpay_address", "title": "Palmpay Salvation"}},
            {"type": "reply", "reply": {"id": "howson_wright_address", "title": "Howson Wright Estate"}},
            {"type": "reply", "reply": {"id": "enter_custom_address", "title": "✍️ Enter my address"}}
        ]
        return self.whatsapp_service.send_button_message(
            session_id,
            f"Thanks, {user_name}! To make sure your orders get to you safely, could you share your delivery address?",
            buttons
        )

    def handle_collect_delivery_address_state(self, state: Dict, message: str, session_id: str, whatsapp_username: str = None) -> Dict[str, Any]:
        """Handles the user's delivery address input from a button selection or free text."""
        delivery_address = None
        if message == "palmpay_address":
            delivery_address = "Palmpay Salvation"
        elif message == "howson_wright_address":
            delivery_address = "Howson Wright Estate"
        elif message == "enter_custom_address":
            state["current_state"] = "waiting_for_address_input"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please enter your full delivery address."
            )
        elif state.get("current_state") == "waiting_for_address_input":
            delivery_address = message.strip()

        if not delivery_address:
            user_name = state.get("user_name", whatsapp_username or "Guest")
            return self._send_address_menu(session_id, user_name)

        self.logger.info(f"Session {session_id}: Delivery address received: '{delivery_address}'.")
        user_data = self.data_manager.get_user_data(session_id) or {}
        user_data.update({
            "address": delivery_address,
            "user_id": session_id,
            "user_number": session_id,
            "phone_number": session_id,
            "name": user_data.get("name", whatsapp_username or "Guest"),
            "user_perferred_name": state.get("user_name", whatsapp_username or "Guest"),
            "display_name": state.get("user_name", whatsapp_username or "Guest"),
            "address2": "",
            "address3": "",
            "latitude": None,
            "longitude": None,
            "map_link": ""
        })
        self.data_manager.save_user_details(session_id, user_data)
        state.update({
            "address": delivery_address,
            "user_name": state.get("user_name", whatsapp_username or "Guest"),
            "phone_number": session_id,
            "current_state": "greeting",
            "current_handler": "greeting_handler"
        })
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id} onboarding complete for {state.get('user_name')}. Address saved: {delivery_address}")
        user_type = "paid" if self._has_user_made_payment(session_id) else "guest"
        return self._send_greeting_with_image(session_id, state.get("user_name", whatsapp_username or "Guest"), user_type)

    def _send_main_menu(self, session_id: str, user_name: str, message: str = "") -> Dict[str, Any]:
        """Send main menu with buttons for non-paid users (max 3 buttons for WhatsApp)."""
        buttons = [
            {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Make an Order"}},
            {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
            {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
        ]
        return self.whatsapp_service.send_button_message(session_id, message or f"What would you like to do, {user_name}?", buttons)

    def _send_main_menu_paid(self, session_id: str, user_name: str, message: str = "") -> Dict[str, Any]:
        """Send main menu with buttons for paid users (max 3 buttons for WhatsApp)."""
        buttons = [
            {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
            {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
            {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
        ]
        return self.whatsapp_service.send_button_message(session_id, message or f"What would you like to do, {user_name}?", buttons)

    def handle_back_to_main(self, state: Dict, session_id: str, whatsapp_username: str = None, message: str = "") -> Dict[str, Any]:
        """Handle back to main menu navigation."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", user_data.get("name", whatsapp_username or "Guest")) if user_data else (whatsapp_username or "Guest")
        saved_address = state.get("address") or (user_data.get("address", "") if user_data else "")
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        state["user_name"] = user_name
        state["phone_number"] = session_id
        if saved_address:
            state["address"] = saved_address
        if "cart" in state:
            state["cart"] = {}
        if "selected_category" in state:
            del state["selected_category"]
        if "selected_item" in state:
            del state["selected_item"]
        state.pop("from_confirm_order", None)
        state.pop("from_confirm_details", None)
        state.pop("order_note", None)
        state.pop("order_id", None)
        self.session_manager.update_session_state(session_id, state)
        self.logger.info(f"Session {session_id} returned to main menu (greeting state). Address preserved: {saved_address}")
        user_type = "paid" if self._has_user_made_payment(session_id) else "guest"
        return self._send_greeting_with_image(session_id, user_name, user_type)

    def _send_greeting_with_image(self, session_id: str, user_name: str, user_type: str) -> Dict[str, Any]:
        """Sends a greeting message with an image, followed by a button message with a prompt."""
        image_url = "https://eventio.africa/wp-content/uploads/2025/08/img.jpg" if user_type != "onboarding" else "https://eventio.africa/wp-content/uploads/2025/08/lola-1.jpg"
        greeting_text = (
            f"Hi {user_name}! Welcome to Lola - your personal shopping assistant for "
            "discovering and ordering from your favorite stores. What name would you like me to call you?"
        ) if user_type == "onboarding" else (
            f"Hello {user_name}!\n"
            "Welcome to Ganador Express!\n"
            "🥘🍛 🎉\n"
            "My name is Lola"
        )
        button_prompt = f"What would you like to do, {user_name}?"
        buttons = (
            [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ] if user_type == "paid" else
            [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏼‍🍳 Make an Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
        ) if user_type != "onboarding" else []
        return self.whatsapp_service.send_image_with_buttons(
            session_id,
            image_url,
            greeting_text,
            buttons,
            button_prompt if buttons else ""
        )