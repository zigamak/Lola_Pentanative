import datetime
import logging
import uuid
from utils.helpers import format_cart
from .base_handler import BaseHandler
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class OrderHandler(BaseHandler):
    """Handles order processing and cart management, integrated with DataManager for database operations."""

    # Configurable charges
    DELIVERY_FEE = 500.00  # Flat delivery fee
    SERVICE_CHARGE_PERCENTAGE = 0.10  # 10% of subtotal

    def __init__(self, config, session_manager, data_manager, whatsapp_service, payment_service=None, location_service=None, lead_tracking_handler=None):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.payment_service = payment_service
        self.location_service = location_service
        self.lead_tracking_handler = lead_tracking_handler
        logger.info("OrderHandler initialized.")

    def _get_order_summary_buttons(self) -> List[Dict[str, Any]]:
        """Helper to return the standard buttons for order summary state."""
        return [
            {"type": "reply", "reply": {"id": "checkout", "title": "Checkout"}},
            {"type": "reply", "reply": {"id": "order_more", "title": "Order More"}},
            {"type": "reply", "reply": {"id": "add_note", "title": "Add Note"}},
            {"type": "reply", "reply": {"id": "other_actions", "title": "Other Options"}}
        ]

    def _get_order_summary_message_text(self, state: Dict) -> str:
        """Helper to return the message for order summary state."""
        cart_content = format_cart(state.get('cart', {}))
        return (
            f"{cart_content}\n\nWhat would you like to do next?\n\n"
            f"Press 'Checkout' to finalize.\n"
            f"Press 'Order More' to add more items.\n"
            f"Press 'Add Note' to add a note to your order.\n"
            f"Or, press 'Other Options' for cart management."
        )

    def handle_quantity_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle quantity input state."""
        logger.debug(f"Handling quantity state for session {session_id}, message: {message}")
        
        if "cart" not in state:
            state["cart"] = {}

        if message.isdigit() and int(message) > 0:
            quantity = int(message)
            item_name = state.get("selected_item")
            selected_category = state.get("selected_category")
            
            if selected_category and item_name and selected_category in self.data_manager.menu_data:
                category_items = self.data_manager.menu_data[selected_category]
                price = None

                if isinstance(category_items, dict) and item_name in category_items:
                    price = category_items[item_name]
                elif isinstance(category_items, list):
                    for item_dict in category_items:
                        if isinstance(item_dict, dict) and item_dict.get("name") == item_name:
                            price = item_dict.get("price")
                            break
                
                if price is not None:
                    total_price = quantity * float(price)
                    
                    if item_name not in state["cart"]:
                        state["cart"][item_name] = {
                            "item_id": item_name,
                            "quantity": quantity, 
                            "price": float(price),
                            "total_price": total_price,
                            "variations": {}
                        }
                    else:
                        existing_qty = state["cart"][item_name]["quantity"]
                        new_qty = existing_qty + quantity
                        state["cart"][item_name]["quantity"] = new_qty
                        state["cart"][item_name]["total_price"] = new_qty * float(price)

                    state["current_state"] = "order_summary"
                    self.session_manager.update_session_state(session_id, state)
                    logger.info(f"Item '{item_name}' added to cart for session {session_id}. Cart: {state['cart']}")

                    try:
                        user_data = self.data_manager.get_user_data(session_id)
                        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
                        self.track_cart_activity(session_id, user_name, state["cart"])
                    except Exception as e:
                        logger.error(f"Error tracking cart activity: {e}")

                    return self.whatsapp_service.create_button_message(
                        session_id,
                        self._get_order_summary_message_text(state),
                        self._get_order_summary_buttons()
                    )
                else:
                    logger.warning(f"Price for item '{item_name}' not found in menu data for session {session_id}.")
                    state["current_state"] = "menu"
                    self.session_manager.update_session_state(session_id, state)
                    return self.whatsapp_service.create_text_message(
                        session_id,
                        "The selected item is no longer available or its price could not be determined. Please choose from the menu again."
                    )
            else:
                logger.warning(f"Selected item '{item_name}' or category '{selected_category}' not found in menu data for session {session_id}.")
                state["current_state"] = "menu"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "The selected item is no longer available. Please choose from the menu again."
                )
        else:
            logger.debug(f"Invalid quantity input '{message}' for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please enter a number greater than zero."
            )

    def handle_order_summary_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle order summary state."""
        logger.debug(f"Handling order summary state for session {session_id}, message: {message}")
        message_strip = message.strip()

        if message_strip == "order_more":
            state["current_state"] = "ai_bulk_order"
            state["current_handler"] = "ai_bulk_handler"
            self.session_manager.update_session_state(session_id, state)
            logger.info(f"User selected 'Order More' for session {session_id}, redirecting to AI bulk handler.")
            
            cart_content = format_cart(state.get('cart', {}))
            return {
                "redirect": "ai_bulk_handler",
                "redirect_message": "handle_ai_bulk_order",
                "additional_message": f"Your current cart:\n{cart_content}\n\nYou can now add more items to your order."
            }
        
        elif message_strip == "checkout":
            user_data = self.data_manager.get_user_data(session_id)
            state["user_name"] = user_data.get("display_name", "Guest") if user_data else "Guest"
            state["phone_number"] = user_data.get("phone_number", session_id) if user_data else session_id
            state["address"] = user_data.get("address", "") if user_data else ""
            state["current_state"] = "confirm_details"
            self.session_manager.update_session_state(session_id, state)
            logger.info(f"User selected 'Checkout' for session {session_id}.")
            
            buttons = [
                {"type": "reply", "reply": {"id": "details_correct", "title": "✅ Correct"}},
                {"type": "reply", "reply": {"id": "change_all_details", "title": "✏️ Change Details"}}
            ]

            return self.whatsapp_service.create_button_message(
                session_id,
                f"📋 **Confirm Delivery Details:**\n\n"
                f"👤 **Name:** {state['user_name']}\n"
                f"📱 **Phone:** {state['phone_number']}\n"
                f"📍 **Address:** {state['address'] or 'Not set'}\n\n"
                f"Is this information correct?",
                buttons
            )
        elif message_strip == "add_note":
            logger.info(f"User chose to add a note for session {session_id}.")
            state["current_state"] = "add_note"
            state["from_order_summary"] = True  # Flag to indicate origin
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please type your note for the order (e.g., 'Please deliver after 5 PM'). Type 'back' to return to the order summary."
            )
        elif message_strip == "other_actions":
            logger.info(f"User selected 'Other Options' for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "You can:\n"
                "- Type *'remove'* to remove an item from your cart.\n"
                "- Type *'cancel'* to cancel your entire order.\n"
                "- Type *'note'* to add or update a note for your order."
            )
        elif message_strip == "remove":
            logger.info(f"User typed 'remove' for session {session_id}.")
            if not state.get("cart"):
                logger.debug(f"Cart is empty for session {session_id}, cannot remove items.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Your cart is empty. Nothing to remove!"
                )
            else:
                state["current_state"] = "remove_item_selection"
                self.session_manager.update_session_state(session_id, state)
                
                item_list_message = "Which item would you like to remove? Please type the *exact name* of the item from the list below:\n\n"
                for idx, item in enumerate(state["cart"].keys()):
                    item_list_message += f"*{idx + 1}. {item}*\n"
                item_list_message += "\nType 'back' to go back to the order summary."

                return self.whatsapp_service.create_text_message(
                    session_id,
                    item_list_message
                )
        elif message_strip == "cancel":
            logger.info(f"User typed 'cancel' to cancel order for session {session_id}.")
            state["cart"] = {}
            return self.handle_back_to_main(
                state,
                session_id,
                message="Your order has been cancelled. How can I help you today?"
            )
        elif message_strip == "note":
            logger.info(f"User typed 'note' to add a note for session {session_id}.")
            state["current_state"] = "add_note"
            state["from_order_summary"] = True  # Flag to indicate origin
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please type your note for the order (e.g., 'Please deliver after 5 PM'). Type 'back' to return to the order summary."
            )
        else:
            logger.debug(f"Invalid input '{message}' in order summary state for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please select 'Checkout', 'Order More', 'Add Note', 'Other Options', or type 'remove', 'cancel', or 'note'."
            )

    def handle_remove_item_selection_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle user selection of item to remove by exact name."""
        logger.debug(f"Handling remove item selection state for session {session_id}, message: {message}")
        message_strip = message.strip()

        if message_strip == "back":
            state["current_state"] = "order_summary"
            self.session_manager.update_session_state(session_id, state)
            logger.info(f"User typed 'back' from remove item selection for session {session_id}.")
            return self.whatsapp_service.create_button_message(
                session_id,
                self._get_order_summary_message_text(state),
                self._get_order_summary_buttons()
            )

        matched_item = None
        for item_name_in_cart in state["cart"].keys():
            if item_name_in_cart == message_strip:
                matched_item = item_name_in_cart
                break

        if matched_item:
            del state["cart"][matched_item]
            self.session_manager.update_session_state(session_id, state)
            logger.info(f"Item '{matched_item}' removed from cart for session {session_id}.")

            try:
                user_data = self.data_manager.get_user_data(session_id)
                user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
                if state["cart"]:
                    self.track_cart_activity(session_id, user_name, state["cart"])
            except Exception as e:
                logger.error(f"Error tracking cart activity after removal: {e}")

            if not state["cart"]:
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    f"'{matched_item}' has been removed from your cart. Your cart is now empty. "
                    "What would you like to do next? You can type 'menu' to see our items."
                )
            else:
                state["current_state"] = "order_summary"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"'{matched_item}' has been removed.\n\n{self._get_order_summary_message_text(state)}",
                    self._get_order_summary_buttons()
                )
        else:
            logger.debug(f"Item '{message}' not found in cart for removal for session {session_id}.")
            return self.whatsapp_service.create_text_message(
                session_id,
                f"❌ '{message}' is not in your cart. Please type the *exact name* of an item from the list to remove it, or 'back' to return."
            )

    def handle_add_note_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle adding or updating a note for the order."""
        logger.debug(f"Handling add note state for session {session_id}, message: {message}")
        message_strip = message.strip()

        if message_strip == "back":
            if state.get("from_ai_order", False):
                state["current_state"] = "prompt_add_note"
                state.pop("from_order_summary", None)
                self.session_manager.update_session_state(session_id, state)
                logger.info(f"User typed 'back' from add note state for AI order for session {session_id}.")
                buttons = [
                    {"type": "reply", "reply": {"id": "add_note", "title": "📝 Yes"}},
                    {"type": "reply", "reply": {"id": "proceed_to_confirmation", "title": "❌ No"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    "Would you like to add a note to your order (e.g., 'Please deliver after 5 PM')?",
                    buttons
                )
            elif state.get("from_order_summary", False):
                state["current_state"] = "order_summary"
                state.pop("from_order_summary", None)
                self.session_manager.update_session_state(session_id, state)
                logger.info(f"User typed 'back' from add note state to order summary for session {session_id}.")
                return self.whatsapp_service.create_button_message(
                    session_id,
                    self._get_order_summary_message_text(state),
                    self._get_order_summary_buttons()
                )
            else:
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                logger.info(f"User typed 'back' from add note state with no specific origin for session {session_id}.")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "🔙 Back to main menu. How can I assist you today?"
                )

        state["order_note"] = message_strip
        state["current_state"] = "confirm_order"
        state.pop("from_order_summary", None)
        self.session_manager.update_session_state(session_id, state)
        logger.info(f"Note '{message_strip}' added for session {session_id}.")

        return self._show_order_confirmation(state, session_id)

    def handle_confirm_details_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle confirm details state."""
        logger.debug(f"Handling confirm details state for session {session_id}, message: {message}")
        message_strip = message.strip()

        user_data = self.data_manager.get_user_data(session_id)
        state.setdefault("user_name", user_data.get("display_name", "Guest") if user_data else "Guest")
        state.setdefault("phone_number", user_data.get("phone_number", session_id) if user_data else session_id)
        state.setdefault("address", user_data.get("address", "") if user_data else "")

        if message_strip == "process_final_order":
            logger.info(f"AI initiated order processing for session {session_id}.")
            if not state.get("cart"):
                logger.warning(f"Cart is empty during AI-initiated confirm_details state for session {session_id}. Redirecting to greeting.")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "It looks like your AI order resulted in an empty cart. Please try again or start fresh. How can I help you today?"
                )

            if not state.get("address"):
                logger.info(f"Address not set after AI order, redirecting to location handler for session {session_id}.")
                state["current_state"] = "address_collection_menu"
                state["current_handler"] = "location_handler"
                state["from_confirm_details"] = True  # Flag to return to confirm_details
                self.session_manager.update_session_state(session_id, state)
                return {
                    "redirect": "location_handler",
                    "redirect_message": "initiate_address_collection"
                }
            else:
                state["from_ai_order"] = True
                state["current_state"] = "prompt_add_note"
                self.session_manager.update_session_state(session_id, state)
                logger.info(f"Prompting for note after AI order confirmation for session {session_id}.")
                buttons = [
                    {"type": "reply", "reply": {"id": "add_note", "title": "📝 Yes"}},
                    {"type": "reply", "reply": {"id": "proceed_to_confirmation", "title": "❌ No"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    "Would you like to add a note to your order (e.g., 'Please deliver after 5 PM')?",
                    buttons
                )

        elif message_strip == "details_correct":
            logger.info(f"User confirmed details are correct for session {session_id}.")
            if not state.get("cart"):
                logger.warning(f"Cart is empty during manual confirm_details state for session {session_id}. Redirecting to greeting.")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "It looks like your cart is empty. Let's start fresh. How can I help you today?"
                )

            if not state.get("address"):
                logger.info(f"Address not set, redirecting to location handler for session {session_id}.")
                state["current_state"] = "address_collection_menu"
                state["current_handler"] = "location_handler"
                state["from_confirm_details"] = True  # Flag to return to confirm_details
                self.session_manager.update_session_state(session_id, state)
                return {
                    "redirect": "location_handler",
                    "redirect_message": "initiate_address_collection"
                }
            else:
                user_data_to_save = {
                    "name": state.get("user_name", "Guest"),
                    "phone_number": state.get("phone_number", session_id),
                    "address": state.get("address", ""),
                    "user_perferred_name": state.get("user_name", "Guest"),
                    "address2": "",
                    "address3": ""
                }
                try:
                    self.data_manager.save_user_details(session_id, user_data_to_save)
                    logger.info(f"User details saved for session {session_id} during checkout.")
                except Exception as e:
                    logger.error(f"Failed to save user details for session {session_id}: {e}")
                    return self.whatsapp_service.create_text_message(
                        session_id,
                        "❌ Sorry, there was an error saving your details. Please try again."
                    )

                state["current_state"] = "prompt_add_note"
                self.session_manager.update_session_state(session_id, state)
                logger.info(f"Address set, prompting for note for manual session {session_id}.")
                buttons = [
                    {"type": "reply", "reply": {"id": "add_note", "title": "📝 Yes"}},
                    {"type": "reply", "reply": {"id": "proceed_to_confirmation", "title": "❌ No"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    "Would you like to add a note to your order (e.g., 'Please deliver after 5 PM')?",
                    buttons
                )
        
        elif message_strip == "change_all_details":
            logger.info(f"User opted to change details for session {session_id}.")
            state["current_state"] = "address_collection_menu"
            state["current_handler"] = "location_handler"
            state["from_confirm_details"] = True  # Flag to return to confirm_details
            self.session_manager.update_session_state(session_id, state)
            return {
                "redirect": "location_handler",
                "redirect_message": "initiate_address_collection"
            }
        else:
            logger.debug(f"Invalid input '{message}' in confirm details state for session {session_id}. Re-presenting details prompt.")
            buttons = [
                {"type": "reply", "reply": {"id": "details_correct", "title": "✅ Correct"}},
                {"type": "reply", "reply": {"id": "change_all_details", "title": "✏️ Change Details"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"I didn't understand that. Please use the buttons to confirm your details or change them.\n\n"
                f"📋 **Confirm Delivery Details:**\n\n"
                f"👤 **Name:** {state.get('user_name', 'N/A')}\n"
                f"📱 **Phone:** {state.get('phone_number', 'N/A')}\n"
                f"📍 **Address:** {state.get('address', 'Not set')}\n\n"
                f"Is this information correct?",
                buttons
            )

    def handle_prompt_add_note_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle the prompt to add a note after AI or manual order confirmation."""
        logger.debug(f"Handling prompt add note state for session {session_id}, message: {message}")
        message_strip = message.strip()

        if message_strip == "add_note":
            logger.info(f"User chose to add a note after confirmation for session {session_id}.")
            state["current_state"] = "add_note"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please type your note for the order (e.g., 'Please deliver after 5 PM'). Type 'back' to skip adding a note."
            )
        
        elif message_strip == "proceed_to_confirmation":
            logger.info(f"User chose to proceed to final confirmation without adding a note for session {session_id}.")
            state["current_state"] = "confirm_order"
            self.session_manager.update_session_state(session_id, state)
            return self._show_order_confirmation(state, session_id)
        
        else:
            logger.debug(f"Invalid input '{message}' in prompt add note state for session {session_id}.")
            buttons = [
                {"type": "reply", "reply": {"id": "add_note", "title": "📝 Yes"}},
                {"type": "reply", "reply": {"id": "proceed_to_confirmation", "title": "❌ No"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                "I didn't understand that. Would you like to add a note to your order (e.g., 'Please deliver after 5 PM')?",
                buttons
            )

    def _show_order_confirmation(self, state: Dict, session_id: str) -> Dict:
        """Show final order confirmation with cart details, charges, and payment options."""
        try:
            cart = state.get("cart", {})
            if not cart:
                logger.warning(f"Cannot show order confirmation - cart is empty for session {session_id}")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Your cart appears to be empty. Let's start fresh. How can I help you today?"
                )
            
            # Calculate charges
            subtotal = sum(
                item_data.get("total_price", item_data.get("quantity", 1) * item_data.get("price", 0.0))
                for item_data in cart.values()
            )
            service_charge = subtotal * self.SERVICE_CHARGE_PERCENTAGE
            charges = self.DELIVERY_FEE + service_charge
            total_amount = subtotal + charges
            
            order_details = "🛒 *Final Order Confirmation*\n\n"
            order_details += "📋 *Items Ordered:*\n"
            
            for item_name, item_data in cart.items():
                quantity = item_data.get("quantity", 1)
                price = item_data.get("price", 0.0)
                total_price = item_data.get("total_price", quantity * price)
                
                order_details += f"• {quantity}x {item_name} - ₦{total_price:,.2f}\n"
            
            user_data = self.data_manager.get_user_data(session_id)
            user_name = user_data.get("display_name", state.get("user_name", "Guest")) if user_data else state.get("user_name", "Guest")
            phone_number = user_data.get("phone_number", session_id) if user_data else session_id
            address = state.get("address", user_data.get("address", "Not provided") if user_data else "Not provided")
            
            order_details += f"\n📍 *Delivery Details:*\n"
            order_details += f"👤 Name: {user_name}\n"
            order_details += f"📱 Phone: {phone_number}\n"
            order_details += f"🏠 Address: {address}\n"
            order_details += f"📝 Note: {state.get('order_note', 'None')}\n"
            order_details += f"\n💰 *Cost Breakdown:*\n"
            order_details += f"Subtotal: ₦{subtotal:,.2f}\n"
            order_details += f"Charges: ₦{charges:,.2f}\n"
            order_details += f"Total Amount: ₦{total_amount:,.2f}\n\n"
            
            buttons = [
                {"type": "reply", "reply": {"id": "final_confirm", "title": "✅ Confirm & Pay"}},
                {"type": "reply", "reply": {"id": "update_address", "title": "📍 Update Address"}},
                {"type": "reply", "reply": {"id": "cancel_order", "title": "❌ Cancel Order"}}
            ]
            
            # Check if message length exceeds WhatsApp's limit (4096 characters)
            MAX_MESSAGE_LENGTH = 4096
            if len(order_details) > MAX_MESSAGE_LENGTH - 100:  # Reserve space for buttons
                # Split into main message and follow-up
                main_message = "🛒 *Final Order Confirmation*\n\n"
                main_message += "📋 *Items Ordered:*\n"
                for item_name, item_data in cart.items():
                    quantity = item_data.get("quantity", 1)
                    price = item_data.get("price", 0.0)
                    total_price = item_data.get("total_price", quantity * price)
                    main_message += f"• {quantity}x {item_name} - ₦{total_price:,.2f}\n"
                
                main_message += f"\n💰 *Cost Breakdown:*\n"
                main_message += f"Subtotal: ₦{subtotal:,.2f}\n"
                main_message += f"Charges (Delivery + {self.SERVICE_CHARGE_PERCENTAGE*100:.0f}% Service): ₦{charges:,.2f}\n"
                main_message += f"Total Amount: ₦{total_amount:,.2f}\n\n"
                main_message += "Please wait for delivery details and options..."

                # Send main message first
                self.whatsapp_service.create_text_message(session_id, main_message)
                
                # Send delivery details and buttons as follow-up
                delivery_message = f"📍 *Delivery Details:*\n"
                delivery_message += f"👤 Name: {user_name}\n"
                delivery_message += f"📱 Phone: {phone_number}\n"
                delivery_message += f"🏠 Address: {address}\n"
                delivery_message += f"📝 Note: {state.get('order_note', 'None')}\n\n"
                delivery_message += "Please confirm to proceed with payment via Paystack or update your address."
                
                logger.info(f"Showing split order confirmation for session {session_id}. Total: ₦{total_amount:,.2f}")
                return self.whatsapp_service.create_button_message(
                    session_id,
                    delivery_message,
                    buttons
                )
            else:
                order_details += "Please confirm to proceed with payment via Paystack or update your address."
                logger.info(f"Showing final order confirmation for session {session_id}. Total: ₦{total_amount:,.2f}")
                return self.whatsapp_service.create_button_message(
                    session_id,
                    order_details,
                    buttons
                )
            
        except Exception as e:
            logger.error(f"Error showing order confirmation for session {session_id}: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "❌ Sorry, there was an error processing your order confirmation. Please try again or contact support."
            )

    def handle_confirm_order_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle the final order confirmation state."""
        logger.debug(f"Handling confirm order state for session {session_id}, message: {message}")
        message_strip = message.strip()
        
        if message_strip == "final_confirm":
            cart = state.get("cart", {})
            if not cart:
                logger.warning(f"Cannot proceed to payment - cart is empty for session {session_id}")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "Your cart appears to be empty. Let's start fresh. How can I help you today?"
                )
            
            if not session_id or session_id.strip() == "":
                logger.error(f"Invalid or missing session_id for order confirmation: {session_id}")
                state["current_state"] = "greeting"
                state["current_handler"] = "greeting_handler"
                self.session_manager.update_session_state(session_id, state)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "❌ Sorry, there was an error processing your order due to an invalid session. Please try again or contact support."
                )
            
            # Calculate total including charges
            subtotal = sum(
                item_data.get("total_price", item_data.get("quantity", 1) * item_data.get("price", 0.0))
                for item_data in cart.values()
            )
            service_charge = subtotal * self.SERVICE_CHARGE_PERCENTAGE
            charges = self.DELIVERY_FEE + service_charge
            total_amount = subtotal + charges
            
            user_data = self.data_manager.get_user_data(session_id)
            user_name = user_data.get("display_name", state.get("user_name", "Guest")) if user_data else state.get("user_name", "Guest")
            phone_number = user_data.get("phone_number", session_id) if user_data else session_id
            address = state.get("address", user_data.get("address", "") if user_data else "")
            
            items = []
            for item_name, item_data in cart.items():
                product_id = item_data.get("product_id")
                if not product_id:
                    product_id = self.data_manager._get_product_id_by_name(item_name)
                    if not product_id:
                        logger.error(f"Could not find product_id for item: {item_name}")
                        continue
                    
                items.append({
                    "item_name": item_name,
                    "quantity": item_data.get("quantity", 1),
                    "unit_price": item_data.get("price", 0.0),
                    "product_id": product_id
                })
            
            if not items:
                logger.error(f"No valid items in cart for session {session_id}")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "❌ Error: No valid items in your cart. Please try ordering again."
                )
            
            order_data = {
                "customer_id": session_id,
                "business_type_id": getattr(self.config, 'BUSINESS_TYPE_ID', "1"),
                "address": address,
                "status": "pending_payment",
                "total_amount": total_amount,
                "charges": charges,
                "payment_reference": f"TEMP-{uuid.uuid4().hex[:8]}",
                "payment_method_type": "paystack",
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "customers_note": state.get("order_note", ""),
                "items": items
            }
            
            try:
                order_id = self.data_manager.save_user_order(order_data)
                if not order_id:
                    logger.error(f"Failed to save order - no order_id returned for session {session_id}")
                    raise Exception("No order_id returned from save_user_order")
                    
                logger.info(f"Order {order_id} saved to database for session {session_id}")
                state["order_id"] = str(order_id)
                state["total_amount"] = total_amount
                state["charges"] = charges
                state["order_status"] = "pending_payment"
                state["order_timestamp"] = order_data["timestamp"].isoformat()
                
                user_data_to_save = {
                    "name": user_name,
                    "phone_number": phone_number,
                    "address": address,
                    "user_perferred_name": user_name,
                    "address2": user_data.get("address2", "") if user_data else "",
                    "address3": user_data.get("address3", "") if user_data else ""
                }
                self.data_manager.save_user_details(session_id, user_data_to_save)
                
                if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                    self.lead_tracking_handler.track_order_conversion(session_id, str(order_id), total_amount)
                
                if hasattr(self, 'payment_service') and self.payment_service:
                    state["current_state"] = "payment_processing"
                    state["current_handler"] = "payment_handler"
                    self.session_manager.update_session_state(session_id, state)
                    return {
                        "redirect": "payment_handler",
                        "redirect_message": "initiate_payment",
                        "order_id": str(order_id),
                        "total_amount": total_amount,
                        "phone_number": phone_number
                    }
                else:
                    logger.error(f"Payment service not available for session {session_id}")
                    return self.whatsapp_service.create_text_message(
                        session_id,
                        f"🎉 Order #{order_id} created!\n\n"
                        f"Total: ₦{total_amount:,.2f}\n\n"
                        f"⚠️ Payment service is currently unavailable. Please contact support."
                    )
                    
            except Exception as e:
                logger.error(f"Failed to process order for session {session_id}: {e}", exc_info=True)
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "❌ Sorry, there was an error processing your order. Please try again or contact support."
                )
        
        elif message_strip == "update_address":
            logger.info(f"User opted to update address for session {session_id}.")
            state["current_state"] = "address_collection_menu"
            state["current_handler"] = "location_handler"
            state["from_confirm_order"] = True  # Flag to return to confirm_order
            self.session_manager.update_session_state(session_id, state)
            return {
                "redirect": "location_handler",
                "redirect_message": "update_address"  # This will be handled by the location handler
            }
        
        elif message_strip == "add_note":
            logger.info(f"User chose to add a note after confirmation for session {session_id}.")
            state["current_state"] = "add_note"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Please type your note for the order (e.g., 'Please deliver after 5 PM'). Type 'back' to skip adding a note."
            )
        
        elif message_strip == "cancel_order":
            logger.info(f"User cancelled order for session {session_id}.")
            state["cart"] = {}
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.whatsapp_service.create_text_message(
                session_id,
                "Your order has been cancelled. How can I help you today?"
            )
        
        else:
            logger.debug(f"Invalid input '{message}' in confirm order state for session {session_id}.")
            # Re-show the order confirmation if invalid input
            return self._show_order_confirmation(state, session_id)

    def handle_get_new_name_address_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle user providing new name and address via LocationAddressHandler."""
        logger.debug(f"Handling get new name and address state for session {session_id}, message: {message}")
        
        state["current_state"] = "address_collection_menu"
        state["current_handler"] = "location_handler"
        state["from_confirm_details"] = True  # Flag to return to confirm_details
        self.session_manager.update_session_state(session_id, state)
        return {"redirect": "location_handler", "redirect_message": "initiate_address_collection"}

    def handle_payment_pending_state(self, state: Dict, message: str, session_id: str) -> Dict:
        """Handle messages when payment is pending with Paystack."""
        logger.debug(f"Handling payment pending state for session {session_id}, message: {message}")
        
        message_strip = message.strip()
        order_id = state.get("order_id", "N/A")
        
        if any(keyword in message_strip for keyword in ["paid", "payment", "transferred", "sent"]):
            logger.info(f"User indicated payment completion for session {session_id}, order {order_id}")
            return self.whatsapp_service.create_text_message(
                session_id,
                f"📋 Order ID: {order_id}\n"
                f"💳 Your payment is being processed via Paystack. Please wait for confirmation.\n"
                f"Type 'status' to check your order status or contact support if you encounter issues."
            )
        elif "status" in message_strip or "order" in message_strip:
            logger.debug(f"User requested order status for session {session_id}, order {order_id}")
            return self.whatsapp_service.create_text_message(
                session_id,
                f"📋 Order ID: {order_id}\n"
                f"Status: Payment Pending\n\n"
                f"💳 Your payment is being processed via Paystack. You'll receive a confirmation soon.\n"
                f"Contact support if you need assistance."
            )
        else:
            logger.debug(f"Invalid input '{message}' in payment pending state for session {session_id}")
            return self.whatsapp_service.create_text_message(
                session_id,
                f"📋 Order ID: {order_id}\n"
                f"💳 Your order is awaiting payment confirmation via Paystack.\n"
                f"Type 'status' to check your order status or contact support."
            )

    def track_order_conversion(self, session_id: str, order_id: str, order_value: float) -> None:
        """Track order conversion for lead analytics."""
        try:
            if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                self.lead_tracking_handler.track_order_conversion(session_id, order_id, order_value)
                logger.info(f"Order conversion tracked: {session_id} - {order_id} (₦{order_value:,.2f})")
            else:
                logger.debug("Lead tracking handler not available for order conversion tracking")
        except Exception as e:
            logger.error(f"Error tracking order conversion for {session_id}: {e}", exc_info=True)

    def track_cart_activity(self, session_id: str, user_name: str, cart) -> None:
        """Track cart activity for lead analytics."""
        try:    
            if hasattr(self, 'lead_tracking_handler') and self.lead_tracking_handler:
                self.lead_tracking_handler.track_cart_activity(session_id, user_name, cart)
                logger.debug(f"Cart activity tracked for {session_id}")
            else:
                logger.debug("Lead tracking handler not available for cart activity tracking")
        except Exception as e:
            logger.error(f"Error tracking cart activity for {session_id}: {e}", exc_info=True)