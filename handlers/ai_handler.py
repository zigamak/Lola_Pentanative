import logging
import json
import re
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
from .base_handler import BaseHandler
from services.ai_service import AIService 

logger = logging.getLogger(__name__)

@dataclass
class OrderItem:
    item_id: str
    name: str
    quantity: int
    variations: Dict[str, str]
    price: float

class AIHandler(BaseHandler):
    """Handles AI-powered order processing and chatbot interactions."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.ai_service = AIService(config, data_manager)
        self.ai_enabled = self.ai_service.ai_enabled
        self.menu_image_urls = {
            "Monday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-monday.jpg",
            "Tuesday": "https://rsvp.eventio.africa/wp-content/uploads/2025/08/tuesday.jpg",
            "Wednesday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-wednesday.jpg",
            "Thursday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-thursday.jpg",
            "Friday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-friday.jpg",
            "Saturday": "https://rsvp.eventio.africa/wp-content/uploads/2025/08/tuesday.jpg",
            "Sunday": "https://rsvp.eventio.africa/wp-content/uploads/2025/08/tuesday.jpg"
        }

        if not self.ai_enabled:
            logger.warning("AIHandler: AI features disabled as AIService could not be initialized.")
        else:
            logger.info("AIHandler: AIService successfully initialized.")

    def _get_daily_menu_url(self):
        """
        Helper method to get the menu image URL for the current day of the week.
        """
        current_day = datetime.now().strftime("%A")
        return self.menu_image_urls.get(current_day, "https://test.mackennytutors.com/wp-content/uploads/2025/06/ganador.jpg")

    def handle_ai_menu_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI menu selection state."""
        self.logger.info(f"AIHandler: Handling message '{message}' in AI menu state for session {session_id}. Original: '{original_message}'")

        if message == "lola_chatbot":
            return self._handle_lola_chatbot(state, session_id)
        elif message == "ai_bulk_order":
            return self._handle_ai_bulk_order(state, session_id)
        elif message == "back_to_main":
            return self.handle_back_to_main(state, session_id)
        elif message == "initial_entry" or message not in ["lola_chatbot", "ai_bulk_order", "back_to_main"]:
            return self._show_ai_menu_options(state, session_id, "Please select an AI option:")
        else:
            return self._show_ai_menu_options(state, session_id, "Please select a valid option:")
    
    def _handle_lola_chatbot(self, state: Dict, session_id: str) -> Dict:
        """Handle Lola chatbot interaction, setting state and sending welcome message."""
        state["current_state"] = "lola_chat"
        state["ai_mode"] = "chatbot"
        state["current_handler"] = "ai_handler"
        self.session_manager.update_session_state(session_id, state)
        
        image_url = self._get_daily_menu_url()
        self.whatsapp_service.send_image_message(session_id, image_url, caption="Our Delicious Menu!")

        welcome_message = (
            "🤖 *Hi! I'm Lola, your AI assistant!*\n\n"
            "I can help you with:\n"
            "• Menu recommendations\n"
            "• Order assistance\n"
            "• General questions about our food\n"
            "• Nutritional information\n\n"
            "What would you like to know? Just ask me anything! 😊\n\n"
            "_Type 'menu' to go back to the main menu_"
        )
        return self.whatsapp_service.create_text_message(session_id, welcome_message)
    
    def _handle_ai_bulk_order(self, state: Dict, session_id: str) -> Dict:
        """Handle AI bulk order processing, setting state and sending welcome message."""
        state["current_state"] = "ai_bulk_order"
        state["ai_mode"] = "bulk_order"
        state["current_handler"] = "ai_handler"
        state["temp_order"] = {}  # Initialize temporary order storage
        self.session_manager.update_session_state(session_id, state)
        
        image_url = self._get_daily_menu_url()
        self.whatsapp_service.send_image_message(session_id, image_url, caption="Our Delicious Menu!")
        bulk_order_message = (
            "Hi, I'm Lola from Ganador Express!\n\n"
            "How to order:\n"
            "• List the items and portions\n"
            "• Say how many packs you want\n\n"
            "Example: '1 portion of Jollof Rice and 1 portion of Fried Rice in 2 packs'\n\n"
            "Take a look at the menu and tell me what you'd like to order.\n\n"
        )

        return self.whatsapp_service.create_text_message(session_id, bulk_order_message)
    
    def handle_lola_chat_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle Lola chatbot conversation state."""
        self.logger.info(f"AIHandler: Handling message '{message}' in Lola chat state for session {session_id}. Original: '{original_message}'")
        
        if message == "start_lola_chat":
            return self._handle_lola_chatbot(state, session_id)
        
        if message and message.lower() == "menu":
            return self.handle_back_to_main(state, session_id)
        
        if not self.ai_service.ai_enabled:
            return self.whatsapp_service.create_text_message(
                session_id,
                "🤖 Sorry, the AI assistant is currently unavailable. Please try the regular menu options.\n\nType 'menu' to return to the main menu."
            )
        
        try:
            ai_response = self.ai_service.generate_lola_response(original_message)
            return self.whatsapp_service.create_text_message(session_id, ai_response)
        
        except Exception as e:
            logger.error(f"Error in Lola chat for session {session_id} when calling AIService: {e}", exc_info=True)
            error_message = (
                "🤖 Sorry, I'm having trouble processing that right now. "
                "Please try again or type 'menu' to return to the main menu."
            )
            return self.whatsapp_service.create_text_message(session_id, error_message)
    
    def handle_ai_bulk_order_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI bulk order processing state."""
        self.logger.info(f"AIHandler: Handling message '{message}' in AI bulk order state for session {session_id}. Original: '{original_message}'")

        if message == "start_ai_bulk_order":
            return self._handle_ai_bulk_order(state, session_id)

        if message and message.lower() == "menu":
            return self.handle_back_to_main(state, session_id)
        
        if not self.ai_service.ai_enabled:
            return self.whatsapp_service.create_text_message(
                session_id,
                "🤖 Sorry, the AI bulk order feature is currently unavailable. Please use the regular order menu.\n\nType 'menu' to return to the main menu."
            )
        
        try:
            parsed_order = self.ai_service.parse_order_with_llm(original_message)
            
            if not parsed_order.get("success"):
                error_message = (
                    f"❌ {parsed_order.get('error', 'Could not process your order')}\n\n"
                    "Please try rephrasing your order or type 'menu' to return to main menu."
                )
                return self.whatsapp_service.create_text_message(session_id, error_message)
            
            # Save the parsed order to temp_order
            state["temp_order"] = parsed_order
            self.session_manager.update_session_state(session_id, state)
            
            # Check for unrecognized items
            if parsed_order.get("unrecognized_items"):
                summary = self._create_order_summary(parsed_order)
                response_message = (
                    f"{summary}\n\n"
                    "🚫 *Some items in your order were not found in our menu (Unrecognized Items above).*\n"
                    "Please ensure you are selecting from our *existing products* only. "
                    "You can rephrase your order, or type 'menu' to go back to the main menu."
                )
                state["current_state"] = "ai_bulk_order"
                state["current_handler"] = "ai_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(session_id, response_message)
            
            # Check for unspecified portions
            unspecified_items = []
            if "pack_groups" in parsed_order:
                for group in parsed_order["pack_groups"]:
                    unspecified_items.extend([item for item in group.get("items", []) if item.get("portions") == "unspecified"])
            else:
                unspecified_items = [item for item in parsed_order.get("items", []) if item.get("portions") == "unspecified"]
            if unspecified_items:
                state["parsed_order"] = parsed_order
                state["current_state"] = "ai_portion_clarification"
                state["current_handler"] = "ai_handler"
                self.session_manager.update_session_state(session_id, state)
                
                items_needing_clarification = ", ".join([item["name"] for item in unspecified_items])
                response_message = (
                    f"🛒 *Order Summary:*\n\n{self._create_order_summary(parsed_order)}\n\n"
                    f"You mentioned {items_needing_clarification} but didn’t specify how many portions. "
                    "How many portions would you like for each, and how should we pack them? "
                    "For example, '2 portions of Jollof Rice, 1 portion of Fried Rice, in 1 pack'."
                )
                return self.whatsapp_service.create_text_message(session_id, response_message)
            
            # If no unrecognized items or unspecified portions, proceed to confirmation
            state["parsed_order"] = parsed_order
            state["current_state"] = "ai_order_confirmation"
            state["current_handler"] = "ai_handler"
            self.session_manager.update_session_state(session_id, state)
            
            buttons = [
                {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Order"}},
                {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
            ]
            
            return self.whatsapp_service.create_button_message(
                session_id,
                self._create_order_summary(parsed_order) + "\n\nWould you like to proceed with this order?",
                buttons
            )
        
        except Exception as e:
            logger.error(f"Error in AI bulk order processing for session {session_id} when calling AIService: {e}", exc_info=True)
            error_message = (
                "🤖 Sorry, I'm having trouble processing your order right now. "
                "Please try again or type 'menu' to return to the main menu."
            )
            return self.whatsapp_service.create_text_message(session_id, error_message)
    
    def handle_ai_portion_clarification_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI portion clarification state for unspecified portions."""
        self.logger.debug(f"Handling AI portion clarification state for session {session_id}, message: {message}. Original: '{original_message}'")
        
        parsed_order = state.get("parsed_order", {})
        if ("pack_groups" not in parsed_order and not parsed_order.get("items")):
            self.logger.warning(f"No items in parsed order for portion clarification in session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "No items to clarify. Please provide your order again or type 'menu' to go back."
            )
        
        try:
            # Parse the clarification response
            clarification_response = self.ai_service.parse_order_with_llm(original_message)
            if not clarification_response.get("success"):
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"❌ Could not process your clarification: {clarification_response.get('error', 'Unknown error')}.\n"
                    "Please specify the portions, e.g., '2 portions of Jollof Rice, 1 portion of Fried Rice'. "
                    "Or type 'menu' to go back."
                )
            
            # Update portions
            if "pack_groups" in parsed_order or "pack_groups" in clarification_response:
                # If grouped, merge or update
                if "pack_groups" in clarification_response:
                    parsed_order["pack_groups"] = clarification_response["pack_groups"]
                    parsed_order["packs"] = clarification_response["packs"]
                else:
                    # Apply clarifications to existing pack_groups
                    for group in parsed_order["pack_groups"]:
                        for item in group.get("items", []):
                            if item.get("portions") == "unspecified":
                                for clarified_item in clarification_response.get("items", []):
                                    if clarified_item["name"].lower() == item["name"].lower() and clarified_item["portions"] != "unspecified":
                                        item["portions"] = clarified_item["portions"]
                                        item["total_price"] = float(item["price"]) * float(clarified_item["portions"])
            else:
                for item in parsed_order["items"]:
                    if item.get("portions") == "unspecified":
                        for clarified_item in clarification_response.get("items", []):
                            if clarified_item["name"].lower() == item["name"].lower() and clarified_item["portions"] != "unspecified":
                                item["portions"] = clarified_item["portions"]
                                item["total_price"] = float(item["price"]) * float(clarified_item["portions"])
            
            # Update packs, grouping, and special instructions if provided
            if clarification_response.get("packs") != "unspecified" and "pack_groups" not in parsed_order:
                parsed_order["packs"] = clarification_response["packs"]
            if clarification_response.get("grouping"):
                parsed_order["grouping"] = clarification_response["grouping"]
            if clarification_response.get("special_instructions"):
                parsed_order["special_instructions"] = clarification_response["special_instructions"]
            
            # Recalculate order total
            if "pack_groups" in parsed_order:
                total = 0.0
                for group in parsed_order["pack_groups"]:
                    for item in group.get("items", []):
                        total += float(item.get("total_price", 0.0))
                parsed_order["order_total"] = total
            else:
                parsed_order["order_total"] = sum(float(item["total_price"]) for item in parsed_order["items"] if item.get("portions") != "unspecified")
            
            # Update temp_order with the clarified order
            state["temp_order"] = parsed_order
            self.session_manager.update_session_state(session_id, state)
            
            # Check if all portions are now specified
            unspecified_items = []
            if "pack_groups" in parsed_order:
                for group in parsed_order["pack_groups"]:
                    unspecified_items.extend([item for item in group.get("items", []) if item.get("portions") == "unspecified"])
            else:
                unspecified_items = [item for item in parsed_order.get("items", []) if item.get("portions") == "unspecified"]
            if unspecified_items:
                state["parsed_order"] = parsed_order
                self.session_manager.update_session_state(session_id, state)
                items_needing_clarification = ", ".join([item["name"] for item in unspecified_items])
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"🛒 *Order Summary:*\n\n{self._create_order_summary(parsed_order)}\n\n"
                    f"You still haven’t specified portions for {items_needing_clarification}. "
                    "How many portions would you like for each, and how should we pack them?"
                )
            
            # All portions clarified, move to confirmation
            state["parsed_order"] = parsed_order
            state["current_state"] = "ai_order_confirmation"
            state["current_handler"] = "ai_handler"
            self.session_manager.update_session_state(session_id, state)
            
            buttons = [
                {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Order"}},
                {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
            ]
            
            return self.whatsapp_service.create_button_message(
                session_id,
                self._create_order_summary(parsed_order) + "\n\nAll portions clarified! Would you like to proceed with this order?",
                buttons
            )
        
        except Exception as e:
            logger.error(f"Error in AI portion clarification for session {session_id}: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "🤖 Sorry, I'm having trouble understanding your clarification. "
                "Please specify the portions, e.g., '2 portions of Jollof Rice, 1 portion of Fried Rice'. "
                "Or type 'menu' to go back."
            )
    
    def handle_ai_order_confirmation_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI order confirmation state."""
        self.logger.debug(f"Handling AI order confirmation state for session {session_id}, message: {message}. Original: '{original_message}'")
        if message == "confirm_ai_order":
            parsed_order = state.get("parsed_order", {})
            cart = self._convert_parsed_order_to_cart(parsed_order)
            
            if cart:
                state["cart"] = cart
                state["total_price"] = parsed_order.get("order_total", 0.0)
                state["current_state"] = "confirm_details"
                state["current_handler"] = "order_handler"
                # Clear temp_order upon confirmation
                if "temp_order" in state:
                    del state["temp_order"]
                self.session_manager.update_session_state(session_id, state)
                self.logger.info(f"AI order confirmed. Cart: {state['cart']}. Redirecting to order handler.")
                
                return {"redirect": "order_handler", "redirect_message": "process_final_order"}
            else:
                self.logger.warning(f"Attempted to confirm empty or invalid AI order for session {session_id}.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "❌ Error processing your order. It seems your cart is empty or invalid. Please try again."
                )
        
        elif message == "modify_ai_order":
            state["current_state"] = "ai_order_modification"
            state["current_handler"] = "ai_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"User chose to modify AI order for session {session_id}.")
            
            parsed_order = state.get("temp_order", {})
            summary = self._create_order_summary(parsed_order) if parsed_order else "No items in your current order."
            return self.whatsapp_service.create_text_message(
                session_id,
                f"🛒 *Current Order:*\n\n{summary}\n\n"
                "Please specify changes (e.g., 'add 2 portions of Fried Rice', 'remove Jollof Rice', or 'change to 3 packs')."
            )
        
        elif message == "cancel_ai_order":
            self.logger.info(f"User cancelled AI order for session {session_id}.")
            if "parsed_order" in state:
                del state["parsed_order"]
            if "temp_order" in state:
                del state["temp_order"]
            self.session_manager.update_session_state(session_id, state)
            return self.handle_back_to_main(state, session_id, "Order cancelled. How can I help you?")
        
        else:
            self.logger.debug(f"Invalid input '{message}' in AI order confirmation state for session {session_id}.")
            return self.whatsapp_service.create_button_message(
                session_id,
                "Please choose from the available options.",
                [
                    {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                    {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Order"}},
                    {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
                ]
            )
    
    def handle_ai_order_modification_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI order modification state for adding or removing items."""
        self.logger.debug(f"Handling AI order modification state for session {session_id}, message: {message}. Original: '{original_message}'")
        
        parsed_order = state.get("temp_order", {})
        if not parsed_order.get("items") and not parsed_order.get("pack_groups"):
            self.logger.info(f"No previous order found for modification in session {session_id}. Treating as new order.")
            parsed_order = {
                "success": True,
                "items": [],
                "packs": 1,
                "grouping": "",
                "special_instructions": "",
                "order_total": 0.0,
                "unrecognized_items": []
            }
        
        try:
            # Parse the modification request
            modification_response = self.ai_service.parse_order_with_llm(original_message)
            if not modification_response.get("success"):
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"❌ Could not process your modification: {modification_response.get('error', 'Unknown error')}.\n"
                    "Please specify changes, e.g., 'add 2 portions of Fried Rice', 'remove Jollof Rice'. "
                    "Or type 'menu' to go back."
                )
            
            # Handle modifications
            if "pack_groups" in parsed_order or "pack_groups" in modification_response:
                # Handle grouped orders
                if "pack_groups" in modification_response:
                    # Replace with new grouped structure if provided
                    parsed_order["pack_groups"] = modification_response["pack_groups"]
                    parsed_order["packs"] = modification_response["packs"]
                else:
                    # Update existing pack_groups with flat modifications
                    for group in parsed_order.get("pack_groups", []):
                        items = group.get("items", [])
                        # Handle removals
                        items_to_remove = [item["name"].lower() for item in modification_response.get("items", []) if item.get("portions") == 0]
                        group["items"] = [item for item in items if item["name"].lower() not in items_to_remove]
                        
                        # Handle additions or updates
                        for new_item in modification_response.get("items", []):
                            if new_item.get("portions") == 0:
                                continue  # Skip items marked for removal
                            existing_item = next((item for item in group["items"] if item["name"].lower() == new_item["name"].lower()), None)
                            if existing_item and new_item["portions"] != "unspecified":
                                existing_item["portions"] += new_item["portions"]
                                existing_item["total_price"] = float(existing_item["price"]) * float(existing_item["portions"])
                            elif new_item["portions"] != "unspecified":
                                group["items"].append(new_item)
            else:
                # Handle flat orders
                # Handle removals
                items_to_remove = [item["name"].lower() for item in modification_response.get("items", []) if item.get("portions") == 0]
                parsed_order["items"] = [item for item in parsed_order.get("items", []) if item["name"].lower() not in items_to_remove]
                
                # Handle additions or updates
                for new_item in modification_response.get("items", []):
                    if new_item.get("portions") == 0:
                        continue  # Skip items marked for removal
                    existing_item = next((item for item in parsed_order["items"] if item["name"].lower() == new_item["name"].lower()), None)
                    if existing_item and new_item["portions"] != "unspecified":
                        existing_item["portions"] += new_item["portions"]
                        existing_item["total_price"] = float(existing_item["price"]) * float(existing_item["portions"])
                    elif new_item["portions"] != "unspecified":
                        parsed_order["items"].append(new_item)
            
            # Update packs, grouping, and special instructions if provided
            if modification_response.get("packs") != "unspecified" and "pack_groups" not in parsed_order:
                parsed_order["packs"] = modification_response["packs"]
            if modification_response.get("grouping"):
                parsed_order["grouping"] = modification_response["grouping"]
            if modification_response.get("special_instructions"):
                parsed_order["special_instructions"] = modification_response["special_instructions"]
            
            # Recalculate order total
            if "pack_groups" in parsed_order:
                total = 0.0
                for group in parsed_order["pack_groups"]:
                    for item in group.get("items", []):
                        total += float(item.get("total_price", 0.0))
                parsed_order["order_total"] = total
            else:
                parsed_order["order_total"] = sum(float(item["total_price"]) for item in parsed_order["items"] if item.get("portions") != "unspecified")
            
            # Update temp_order and parsed_order
            state["temp_order"] = parsed_order
            state["parsed_order"] = parsed_order
            self.session_manager.update_session_state(session_id, state)
            
            # Check for unrecognized items
            if modification_response.get("unrecognized_items"):
                summary = self._create_order_summary(parsed_order)
                response_message = (
                    f"{summary}\n\n"
                    "🚫 *Some items in your modification were not found in our menu:*\n"
                    + "\n".join([f"🚫 {item['input']} ({item['message']})" for item in modification_response["unrecognized_items"]]) +
                    "\n\nPlease ensure you are selecting from our *existing products* only. "
                    "You can rephrase your changes or proceed to confirm."
                )
                buttons = [
                    {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                    {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Again"}},
                    {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
                ]
                return self.whatsapp_service.create_button_message(session_id, response_message, buttons)
            
            # Check for unspecified portions
            unspecified_items = []
            if "pack_groups" in parsed_order:
                for group in parsed_order["pack_groups"]:
                    unspecified_items.extend([item for item in group.get("items", []) if item.get("portions") == "unspecified"])
            else:
                unspecified_items = [item for item in parsed_order.get("items", []) if item.get("portions") == "unspecified"]
            if unspecified_items:
                state["current_state"] = "ai_portion_clarification"
                state["current_handler"] = "ai_handler"
                self.session_manager.update_session_state(session_id, state)
                items_needing_clarification = ", ".join([item["name"] for item in unspecified_items])
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"🛒 *Order Summary:*\n\n{self._create_order_summary(parsed_order)}\n\n"
                    f"You mentioned {items_needing_clarification} but didn’t specify how many portions. "
                    "How many portions would you like for each, and how should we pack them?"
                )
            
            # Move to confirmation
            state["current_state"] = "ai_order_confirmation"
            state["current_handler"] = "ai_handler"
            self.session_manager.update_session_state(session_id, state)
            
            buttons = [
                {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Again"}},
                {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
            ]
            
            return self.whatsapp_service.create_button_message(
                session_id,
                self._create_order_summary(parsed_order) + "\n\nYour order has been updated! Would you like to proceed?",
                buttons
            )
        
        except Exception as e:
            logger.error(f"Error in AI order modification for session {session_id}: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "🤖 Sorry, I'm having trouble processing your changes. "
                "Please specify changes, e.g., 'add 2 portions of Fried Rice', 'remove Jollof Rice'. "
                "Or type 'menu' to go back."
            )

    def handle_ai_order_clarification_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI order clarification state for ambiguous items."""
        self.logger.debug(f"Handling AI order clarification state for session {session_id}, message: {message}. Original: '{original_message}'")

        parsed_order = state.get("parsed_order", {})
        ambiguous_items = parsed_order.get("ambiguous_items", [])
        
        if not ambiguous_items:
            self.logger.warning(f"No ambiguous items found for clarification in session {session_id}.")
            state["current_state"] = "ai_order_confirmation"
            state["current_handler"] = "ai_handler"
            self.session_manager.update_session_state(session_id, state)
            buttons = [
                {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                "No further clarification needed. Ready to confirm?",
                buttons
            )
        
        first_ambiguous = ambiguous_items[0]
        possible_matches = first_ambiguous.get("possible_matches", [])
        
        selected_item_name = None
        for match_name in possible_matches:
            if message.lower().strip() == match_name.lower().replace(" ", "_").replace("-", "_"):
                selected_item_name = match_name
                break
        
        if selected_item_name:
            item_price = 0.0
            item_id = None
            found_item_data = None

            for category, items_data in self.data_manager.menu_data.items():
                for item_dict in items_data:
                    if isinstance(item_dict, dict) and item_dict.get("name") == selected_item_name:
                        item_price = item_dict.get("price", 0.0)
                        item_id = item_dict.get("id", f"{category.lower().replace(' ', '_')}_{selected_item_name.lower().replace(' ', '_')}")
                        found_item_data = item_dict
                        break
                if found_item_data:
                    break

            if found_item_data:
                original_qty = first_ambiguous.get("quantity", 1)
                recognized_item = {
                    "item_id": item_id,
                    "name": selected_item_name,
                    "portions": original_qty,
                    "price": item_price,
                    "total_price": original_qty * item_price,
                    "variations": found_item_data.get("variations", {}),
                    "food_share_pattern": found_item_data.get("food_share_pattern", "single")
                }
                
                if "recognized_items" not in parsed_order:
                    parsed_order["recognized_items"] = []
                parsed_order["recognized_items"].append(recognized_item)
                parsed_order["order_total"] = parsed_order.get("order_total", 0.0) + recognized_item["total_price"]
                ambiguous_items.pop(0)
                state["parsed_order"] = parsed_order
                state["temp_order"] = parsed_order  # Update temp_order
                self.session_manager.update_session_state(session_id, state)
                
                if ambiguous_items:
                    state["current_state"] = "ai_order_clarification"
                    state["current_handler"] = "ai_handler"
                    self.session_manager.update_session_state(session_id, state)
                    next_ambiguous = ambiguous_items[0]
                    clarification_buttons = self._create_clarification_buttons([next_ambiguous])
                    return self.whatsapp_service.create_button_message(
                        session_id,
                        f"Okay, understood! Now, for the next one:\n\n{self._create_order_summary(parsed_order)}\n\nPlease help me clarify: *{next_ambiguous['clarification_needed']}*",
                        clarification_buttons
                    )
                else:
                    state["current_state"] = "ai_order_confirmation"
                    state["current_handler"] = "ai_handler"
                    self.session_manager.update_session_state(session_id, state)
                    buttons = [
                        {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                        {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Order"}},
                        {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
                    ]
                    return self.whatsapp_service.create_button_message(
                        session_id,
                        self._create_order_summary(parsed_order) + "\n\nAll items clarified! Would you like to proceed with this order?",
                        buttons
                    )
            else:
                self.logger.error(f"Selected item '{selected_item_name}' not found in menu data during clarification for session {session_id}.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Sorry, I couldn't find details for that item in our menu. Please try again or type 'menu' to go back."
                )
        else:
            first_ambiguous = ambiguous_items[0]
            clarification_buttons = self._create_clarification_buttons([first_ambiguous])
            self.logger.debug(f"Invalid clarification input '{message}' for session {session_id}. Expected one of {first_ambiguous.get('possible_matches', [])}")
            return self.whatsapp_service.create_button_message(
                session_id,
                "Please choose one of the *exact* options for clarification or type 'menu' to go back to the main menu:",
                clarification_buttons
            )

    def _show_ai_menu_options(self, state: Dict, session_id: str, message: str = "Choose an AI option:") -> Dict:
        """Show AI menu options."""
        if not self.ai_service.ai_enabled:
            fallback_message = (
                "🤖 *AI Assistant Currently Unavailable*\n\n"
                "Our AI features are temporarily offline. Please use our regular menu options instead.\n\n"
                "You can still:\n"
                "📱 Browse our full menu\n"
                "❓ Check our FAQ\n"
                "📝 Send us your feedback"
            )
            buttons = [
                {"type": "reply", "reply": {"id": "order", "title": "📱 Order Menu"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "back_to_main", "title": "🔙 Back to Main"}}
            ]
            return self.whatsapp_service.create_button_message(session_id, fallback_message, buttons)
        
        buttons = [
            {"type": "reply", "reply": {"id": "lola_chatbot", "title": "🤖 Lola Chatbot"}},
            {"type": "reply", "reply": {"id": "ai_bulk_order", "title": "🛒 AI Bulk Order"}},
            {"type": "reply", "reply": {"id": "back_to_main", "title": "🔙 Back to Main"}}
        ]
        full_message = (
            f"🤖 *AI Assistant Options*\n\n"
            f"🤖 *Lola Chatbot* - Chat with our AI assistant\n"
            f"🛒 *AI Bulk Order* - Order multiple items at once\n\n"
            f"{message}"
        )
        return self.whatsapp_service.create_button_message(session_id, full_message, buttons)
    
    def _create_order_summary(self, parsed_order: Dict[str, Any]) -> str:
        """Create formatted order summary, breaking down items by packs."""
        if not parsed_order.get("success"):
            return f"❌ Error: {parsed_order.get('error', 'Unknown error')}"
            
        summary = "🛒 *Order Summary:*\n\n"
        packs = parsed_order.get("packs", 1)
        
        if "pack_groups" in parsed_order:
            # Use grouped structure
            pack_groups = sorted(parsed_order["pack_groups"], key=lambda x: x["pack"])
            for group in pack_groups:
                pack_num = group["pack"]
                summary += f"*Pack {pack_num}:*\n"
                pack_items = []
                for item in group.get("items", []):
                    portions = item.get("portions", "unspecified")
                    if portions != "unspecified" and portions != 0:
                        pack_items.append(
                            f"✅ {item['name']} ({portions} portion{'s' if portions != 1 else ''})"
                            + (f" [Combo]" if item.get("food_share_pattern") == "combo" else "")
                            + f" - ₦{item.get('total_price', 0.0):,.2f}"
                        )
                if pack_items:
                    summary += "\n".join(pack_items) + "\n\n"
                else:
                    summary += "No items assigned to this pack.\n\n"
        else:
            # Flat items, distribute evenly
            items = parsed_order.get("items", [])
            if not items:
                return "No items in the order."
            
            for pack_num in range(1, packs + 1):
                summary += f"*Pack {pack_num}:*\n"
                pack_items = []
                for item in items:
                    portions = item.get("portions", 0)
                    if portions == "unspecified" or portions == 0:
                        continue
                    portions_per_pack = portions // packs + (1 if pack_num <= portions % packs else 0)
                    if portions_per_pack > 0:
                        pack_items.append(
                            f"✅ {item['name']} ({portions_per_pack} portion{'s' if portions_per_pack != 1 else ''})"
                            + (f" [Combo]" if item.get("food_share_pattern") == "combo" else "")
                            + f" - ₦{float(item['price']) * portions_per_pack:,.2f}"
                        )
                if pack_items:
                    summary += "\n".join(pack_items) + "\n\n"
                else:
                    summary += "No items assigned to this pack.\n\n"
        
        # Add unrecognized items
        if parsed_order.get("unrecognized_items"):
            summary += "*Unrecognized Items:*\n"
            for item in parsed_order["unrecognized_items"]:
                summary += f"🚫 {item['input']} ({item['message']})\n"
            summary += "\n"
                
        # Add grouping and special instructions
        summary += f"*Total Packs*: {packs}\n"
        summary += f"*Grouping*: {parsed_order.get('grouping', 'No specific grouping')}\n"
        if parsed_order.get("special_instructions"):
            summary += f"*Special Instructions*: {parsed_order.get('special_instructions')}\n"
        summary += f"*Total*: ₦{parsed_order.get('order_total', 0.0):,.2f}"
        
        return summary

    def _create_clarification_buttons(self, ambiguous_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create buttons for clarifying an ambiguous item."""
        buttons = []
        if ambiguous_items:
            ambiguous_item = ambiguous_items[0]
            for i, match in enumerate(ambiguous_item.get("possible_matches", [])):
                button_id = match.lower().replace(" ", "_").replace("-", "_")
                buttons.append({"type": "reply", "reply": {"id": button_id, "title": match}})
            buttons.append({"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel Order"}})
        return buttons

    def _convert_parsed_order_to_cart(self, parsed_order: Dict[str, Any]) -> Dict[str, Any]:
        """Converts the AI-parsed order into the standard cart format for the OrderHandler."""
        cart_items = {}
        if "pack_groups" in parsed_order:
            for group in parsed_order["pack_groups"]:
                for item in group.get("items", []):
                    name = item["name"]
                    if name in cart_items:
                        cart_items[name]["quantity"] += item["portions"]
                        cart_items[name]["total_price"] += item["total_price"]
                    else:
                        cart_items[name] = {
                            "item_id": item["item_id"],
                            "quantity": item["portions"],
                            "price": item["price"],
                            "total_price": item["total_price"],
                            "variations": item.get("variations", {}),
                            "food_share_pattern": item.get("food_share_pattern", "single")
                        }
        elif parsed_order.get("items"):
            for item in parsed_order["items"]:
                if item.get("portions") != "unspecified":
                    cart_items[item["name"]] = {
                        "item_id": item["item_id"],
                        "quantity": item["portions"],
                        "price": item["price"],
                        "total_price": item["total_price"],
                        "variations": item.get("variations", {}),
                        "food_share_pattern": item.get("food_share_pattern", "single")
                    }
        return cart_items