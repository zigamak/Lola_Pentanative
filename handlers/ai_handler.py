import logging
import os
import json
import re
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime # Import the datetime module

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
        
        # Dictionary to map day names to their respective menu image URLs
        self.menu_image_urls = {
            "Monday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-monday.jpg",
            "Tuesday": "https://rsvp.eventio.africa/wp-content/uploads/2025/08/tuesday.jpg",
            "Wednesday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-wednesday.jpg",
            "Thursday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-thursday.jpg",
            "Friday": "https://eventio.africa/wp-content/uploads/2025/08/ganador-friday.jpg",
            "Saturday": "https://rsvp.eventio.africa/wp-content/uploads/2025/08/tuesday.jpg", # Fallback for weekends
            "Sunday": "https://rsvp.eventio.africa/wp-content/uploads/2025/08/tuesday.jpg" # Fallback for weekends
        }

        if not self.ai_enabled:
            logger.warning("AIHandler: AI features disabled as AIService could not be initialized.")
        else:
            logger.info("AIHandler: AIService successfully initialized.")

    def _get_daily_menu_url(self):
        """
        Helper method to get the menu image URL for the current day of the week.
        It uses the datetime module to get the weekday name (e.g., "Monday").
        If a day is not in the dictionary, it will return a default URL.
        """
        current_day = datetime.now().strftime("%A") # Returns the full weekday name
        # Use .get() with a default fallback URL for safety
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
        
        # Get the correct image URL for the day using the new helper method
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
        self.session_manager.update_session_state(session_id, state)
        
        # Get the correct image URL for the day using the new helper method
        image_url = self._get_daily_menu_url()
        self.whatsapp_service.send_image_message(session_id, image_url, caption="Our Delicious Menu!")

        bulk_order_message = (
            "Hi, I'm Lola from Ganador \n\n"
            "Take a look at the menu and type in your order\n\n"
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
            
            # --- NEW LOGIC START ---
            # If any items are unrecognized, prioritize this message and ask user to rephrase.
            # This prevents entering clarification for ambiguous items if there are clear unrecognized ones.
            if parsed_order.get("unrecognized_items"):
                summary_with_unrecognized = self._create_order_summary(parsed_order)
                
                response_message = (
                    f"{summary_with_unrecognized}\n\n"
                    "🚫 *Some items in your order were not found in our menu (Unrecognized Items above).*\n"
                    "Please ensure you are selecting from our *existing products* only. "
                    "You can rephrase your order, or type 'menu' to go back to the main menu."
                )
                
                # Keep the user in the 'ai_bulk_order' state to allow them to retry or go back
                state["current_state"] = "ai_bulk_order" 
                state["current_handler"] = "ai_handler"
                self.session_manager.update_session_state(session_id, state)
                
                return self.whatsapp_service.create_text_message(session_id, response_message)
            # --- NEW LOGIC END ---

            # If no unrecognized items, proceed with existing logic for ambiguous or recognized items
            state["parsed_order"] = parsed_order
            state["current_handler"] = "ai_handler" # Keep handler consistent
            
            if parsed_order.get("ambiguous_items"):
                state["current_state"] = "ai_order_clarification"
                self.session_manager.update_session_state(session_id, state)
                
                clarification_buttons = self._create_clarification_buttons(parsed_order["ambiguous_items"])
                
                return self.whatsapp_service.create_button_message(
                    session_id,
                    self._create_order_summary(parsed_order) + "\n\nPlease help me clarify:",
                    clarification_buttons
                )
            
            elif parsed_order.get("recognized_items"):
                state["current_state"] = "ai_order_confirmation"
                self.session_manager.update_session_state(session_id, state)
                
                summary = self._create_order_summary(parsed_order)
                
                buttons = [
                    {"type": "reply", "reply": {"id": "confirm_ai_order", "title": "✅ Confirm Order"}},
                    {"type": "reply", "reply": {"id": "modify_ai_order", "title": "✏️ Modify Order"}},
                    {"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel"}}
                ]
                
                return self.whatsapp_service.create_button_message(
                    session_id,
                    summary + "\n\nWould you like to proceed with this order?",
                    buttons
                )
            
            else: # Fallback for cases where no items are recognized, ambiguous, or unrecognized
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "I couldn't find any items to add to your order. Would you like to try again or see our menu?"
                )
        
        except Exception as e:
            logger.error(f"Error in AI bulk order processing for session {session_id} when calling AIService: {e}", exc_info=True)
            error_message = (
                "🤖 Sorry, I'm having trouble processing your order right now. "
                "Please try again or type 'menu' to return to the main menu."
            )
            return self.whatsapp_service.create_text_message(session_id, error_message)
    
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
            state["current_state"] = "ai_bulk_order"
            state["current_handler"] = "ai_handler"
            self.session_manager.update_session_state(session_id, state)
            self.logger.info(f"User chose to modify AI order for session {session_id}.")
            
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please tell me your updated order:"
            )
        
        elif message == "cancel_ai_order":
            self.logger.info(f"User cancelled AI order for session {session_id}.")
            if "parsed_order" in state:
                del state["parsed_order"]
                self.session_manager.update_session_state(session_id, state)
            return self.handle_back_to_main(state, session_id, "Order cancelled. How can I help you?")
        
        else:
            self.logger.debug(f"Invalid input '{message}' in AI order confirmation state for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please choose from the available options."
            )
    
    def handle_ai_order_clarification_state(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict:
        """Handle AI order clarification state."""
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
            # Use original message for matching if needed, or stick to processed 'message'
            # Assuming 'message' is already cleaned for button IDs
            if message.lower().strip() == match_name.lower().replace(" ", "_").replace("-", "_"):
                selected_item_name = match_name
                break
        
        if selected_item_name:
            item_price = 0.0
            item_id = None
            found_item_data = None

            # Iterate through menu_data to find the selected item's full details
            for category, items_data in self.data_manager.menu_data.items():
                if isinstance(items_data, dict): # Old format, likely not used with product_inventory sync
                    if selected_item_name in items_data:
                        item_price = items_data[selected_item_name]
                        item_id = f"{category.lower().replace(' ', '_')}_{selected_item_name.lower().replace(' ', '_')}"
                        found_item_data = {"name": selected_item_name, "price": item_price, "id": item_id}
                        break
                elif isinstance(items_data, list): # Expected format from product_inventory sync
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
                    "quantity": original_qty, 
                    "variations": found_item_data.get("variations", {}), # Use variations from found_item_data
                    "price": item_price,
                    "total_price": original_qty * item_price
                }
                
                if "recognized_items" not in parsed_order:
                    parsed_order["recognized_items"] = []
                parsed_order["recognized_items"].append(recognized_item)
                
                parsed_order["order_total"] = parsed_order.get("order_total", 0.0) + recognized_item["total_price"]

                ambiguous_items.pop(0) # Remove the clarified item

                state["parsed_order"] = parsed_order
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
                    # All ambiguous items clarified, move to confirmation
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
        """Create formatted order summary."""
        if not parsed_order.get("success"):
            return f"❌ Error: {parsed_order.get('error', 'Unknown error')}"
            
        summary = "🛒 *Order Summary:*\n\n"
        
        if parsed_order.get("recognized_items"):
            for item in parsed_order["recognized_items"]:
                summary += f"✅ {item['quantity']}x {item['name']} - ₦{item['total_price']:,}\n"
        
        if parsed_order.get("ambiguous_items"):
            summary += "\n❓ *Need Clarification:*\n"
            for item in parsed_order["ambiguous_items"]:
                summary += f"⚠️ {item.get('quantity', 1)}x {item['input']} ({item['clarification_needed']})\n"
        
        if parsed_order.get("unrecognized_items"):
            summary += "\n❌ *Unrecognized Items:*\n"
            for item in parsed_order["unrecognized_items"]:
                summary += f"🚫 {item['input']} ({item['message']})\n"
                
        summary += f"\n*Total: ₦{parsed_order.get('order_total', 0.0):,.2f}*"
        
        return summary

    def _create_clarification_buttons(self, ambiguous_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create buttons for clarifying an ambiguous item."""
        buttons = []
        if ambiguous_items:
            ambiguous_item = ambiguous_items[0] # Only create buttons for the first ambiguous item
            for i, match in enumerate(ambiguous_item.get("possible_matches", [])):
                button_id = match.lower().replace(" ", "_").replace("-", "_") 
                buttons.append({"type": "reply", "reply": {"id": button_id, "title": match}})
            
            buttons.append({"type": "reply", "reply": {"id": "cancel_ai_order", "title": "❌ Cancel Order"}})
            
        return buttons

    def _convert_parsed_order_to_cart(self, parsed_order: Dict[str, Any]) -> Dict[str, Any]:
        """Converts the AI-parsed order into the standard cart format for the OrderHandler."""
        cart_items = {}
        if parsed_order and parsed_order.get("recognized_items"):
            for item in parsed_order["recognized_items"]:
                cart_items[item["name"]] = {
                    "item_id": item["item_id"],
                    "quantity": item["quantity"],
                    "price": item["price"],
                    "total_price": item["total_price"],
                    "variations": item.get("variations", {})
                }
        return cart_items
