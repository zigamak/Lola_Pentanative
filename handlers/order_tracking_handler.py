import logging
from typing import Dict, Any
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class TrackOrderHandler(BaseHandler):
    """Handles order tracking interactions by checking the whatsapp_orders table."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
    
    def handle(self, state: Dict, message: str, original_message: str, session_id: str) -> Dict[str, Any]:
        """Top-level handler for track order state and redirects."""
        self.logger.info(f"Session {session_id}: Handling message '{message}' in state '{state.get('current_state')}'.")
        
        current_state = state.get("current_state")
        
        if message == "start_track_order":
            state["current_state"] = "track_order"
            state["current_handler"] = "track_order_handler"
            self.session_manager.update_session_state(session_id, state)
            return self.handle_track_order_state(state, original_message, session_id)
        elif current_state == "track_order":
            return self.handle_track_order_state(state, original_message, session_id)
        else:
            self.logger.warning(f"Session {session_id}: Unhandled state '{current_state}' with message '{message}'.")
            return self._handle_invalid_state(state, session_id)
    
    def handle_track_order_state(self, state: Dict, original_message: str, session_id: str) -> Dict[str, Any]:
        """
        Handles the 'track_order' state by querying the whatsapp_orders table for the latest order status.
        Returns the user to the main menu after displaying the status.
        """
        try:
            # Fetch the latest order for the user (session_id matches customer_id)
            order = self.data_manager.get_latest_order_by_customer_id(session_id)
            if not order:
                self.logger.info(f"Session {session_id}: No orders found for tracking.")
                return self._handle_no_orders_found(state, session_id)
            
            order_id = order.get("id", "Unknown")
            status = order.get("status", "").lower()
            timestamp = order.get("timestamp", None)
            user_data = self.data_manager.get_user_data(session_id)
            user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
            
            # Format timestamp if available
            timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
            
            # Map status to user-friendly message
            status_messages = {
                "confirmed": "Your order is confirmed and being prepared to be delivered.",
                "in_transit": "Your order is on its way, it has been sent out.",
                "delivered": "Your order has been delivered."
            }
            
            status_message = status_messages.get(status, None)
            if not status_message:
                self.logger.warning(f"Session {session_id}: Invalid order status '{status}' for order ID {order_id}.")
                return self._handle_invalid_order_status(state, session_id)
            
            self.logger.info(f"Session {session_id}: Retrieved status '{status}' for order ID {order_id}.")
            
            # Prepare status message
            tracking_message = (
                f"📍 Order Status for Order ID: {order_id}\n"
                f"Placed on: {timestamp_str}\n\n"
                f"{status_message}\n\n"
                f"What would you like to do next?"
            )
            
            # Reset session state to main menu
            state["current_state"] = "greeting"
            state["current_handler"] = "greeting_handler"
            # Clear order-related data but preserve user info
            state["cart"] = {}
            if "selected_category" in state:
                del state["selected_category"]
            if "selected_item" in state:
                del state["selected_item"]
            self.session_manager.update_session_state(session_id, state)
            
            # Check if user is paid to show appropriate menu
            if self.session_manager.is_paid_user_session(session_id):
                self.logger.info(f"Session {session_id}: Returning to paid user main menu after tracking order.")
                buttons = [
                    {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                    {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                    {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"Welcome Back {user_name}\n{tracking_message}",
                    buttons
                )
            else:
                self.logger.info(f"Session {session_id}: Returning to non-paid user main menu after tracking order.")
                buttons = [
                    {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                    {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                    {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
                ]
                return self.whatsapp_service.create_button_message(
                    session_id,
                    f"Hi {user_name}, {tracking_message}",
                    buttons
                )
        
        except Exception as e:
            self.logger.error(f"Session {session_id}: Error handling order tracking: {e}", exc_info=True)
            return self._handle_invalid_state(state, session_id)
    
    def _handle_no_orders_found(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle case where no orders are found for the user."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        # Clear order-related data
        state["cart"] = {}
        if "selected_category" in state:
            del state["selected_category"]
        if "selected_item" in state:
            del state["selected_item"]
        self.session_manager.update_session_state(session_id, state)
        
        message = (
            f"No orders found for your account. Would you like to place a new order or do something else?"
        )
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            self.logger.info(f"Session {session_id}: Returning to paid user main menu (no orders found).")
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\n{message}",
                buttons
            )
        else:
            self.logger.info(f"Session {session_id}: Returning to non-paid user main menu (no orders found).")
            buttons = [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Hi {user_name}, {message}",
                buttons
            )
    
    def _handle_invalid_order_status(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle case where the order status is invalid."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        # Clear order-related data
        state["cart"] = {}
        if "selected_category" in state:
            del state["selected_category"]
        if "selected_item" in state:
            del state["selected_item"]
        self.session_manager.update_session_state(session_id, state)
        
        message = (
            f"Unable to retrieve your order status at this time. Please contact support or try again later.\n\n"
            f"What would you like to do next?"
        )
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            self.logger.info(f"Session {session_id}: Returning to paid user main menu (invalid order status).")
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\n{message}",
                buttons
            )
        else:
            self.logger.info(f"Session {session_id}: Returning to non-paid user main menu (invalid order status).")
            buttons = [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Hi {user_name}, {message}",
                buttons
            )
    
    def _handle_invalid_state(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle general errors during order tracking."""
        user_data = self.data_manager.get_user_data(session_id)
        user_name = user_data.get("display_name", "Guest") if user_data else "Guest"
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        # Clear order-related data
        state["cart"] = {}
        if "selected_category" in state:
            del state["selected_category"]
        if "selected_item" in state:
            del state["selected_item"]
        self.session_manager.update_session_state(session_id, state)
        
        message = (
            f"⚠️ An error occurred while tracking your order. Please try again or contact support.\n\n"
            f"What would you like to do next?"
        )
        
        # Check if user is paid to show appropriate menu
        if self.session_manager.is_paid_user_session(session_id):
            self.logger.info(f"Session {session_id}: Returning to paid user main menu (error).")
            buttons = [
                {"type": "reply", "reply": {"id": "track_order", "title": "📍 Track Order"}},
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Welcome Back {user_name}\n{message}",
                buttons
            )
        else:
            self.logger.info(f"Session {session_id}: Returning to non-paid user main menu (error).")
            buttons = [
                {"type": "reply", "reply": {"id": "ai_bulk_order_direct", "title": "👩🏾‍🍳 Let Lola Order"}},
                {"type": "reply", "reply": {"id": "enquiry", "title": "❓ Enquiry"}},
                {"type": "reply", "reply": {"id": "complain", "title": "📝 Complain"}}
            ]
            return self.whatsapp_service.create_button_message(
                session_id,
                f"Hi {user_name}, {message}",
                buttons
            )