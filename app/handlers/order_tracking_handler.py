import json
import os
import datetime
import logging
from typing import Dict, List, Any, Optional
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)

class OrderTrackingHandler(BaseHandler):
    """Handles order status tracking and updates."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.order_status_file = "data/order_status.json"
        self._ensure_order_status_file_exists()
        logger.info("OrderTrackingHandler initialized.")
    
    def _ensure_order_status_file_exists(self):
        """Ensure order status JSON file exists."""
        if not os.path.exists(self.order_status_file):
            os.makedirs(os.path.dirname(self.order_status_file), exist_ok=True)
            with open(self.order_status_file, 'w') as f:
                json.dump({}, f, indent=2)
            logger.info(f"Created order status file: {self.order_status_file}")
    
    def track_order_status(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """
        Track order status for the user's recent order.
        
        Args:
            state (Dict): Session state
            session_id (str): User's session ID
            
        Returns:
            Dict: WhatsApp message response
        """
        try:
            order_id = state.get("recent_order_id")
            if not order_id:
                logger.warning(f"No recent order found for session {session_id}")
                return self.whatsapp_service.create_text_message(
                    session_id,
                    "❌ No recent order found to track. Please place a new order."
                )
            
            # Get order status
            order_status = self._get_order_status(order_id)
            status_message = self._format_order_status_message(order_id, order_status)
            
            # Add tracking options
            buttons = [
                {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
                {"type": "reply", "reply": {"id": "track_refresh", "title": "🔄 Refresh Status"}},
                {"type": "reply", "reply": {"id": "contact_support", "title": "📞 Contact Support"}}
            ]
            
            return self.whatsapp_service.create_button_message(
                session_id,
                status_message,
                buttons
            )
            
        except Exception as e:
            logger.error(f"Error tracking order for session {session_id}: {e}", exc_info=True)
            return self.whatsapp_service.create_text_message(
                session_id,
                "❌ Sorry, there was an error tracking your order. Please try again or contact support."
            )
    
    def handle_tracking_action(self, state: Dict, message: str, session_id: str) -> Dict[str, Any]:
        """Handle tracking-related actions."""
        logger.debug(f"Handling tracking action '{message}' for session {session_id}")
        
        if message == "order_again":
            return self._handle_order_again(state, session_id)
        elif message == "track_refresh":
            return self.track_order_status(state, session_id)
        elif message == "contact_support":
            return self._handle_contact_support(state, session_id)
        else:
            # Invalid action, show tracking status again
            return self.track_order_status(state, session_id)
    
    def _get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get order status from file or database."""
        try:
            # Load order status data
            status_data = {}
            if os.path.exists(self.order_status_file):
                with open(self.order_status_file, 'r') as f:
                    status_data = json.load(f)
            
            # Return status or default
            return status_data.get(order_id, {
                "status": "received",
                "status_text": "Order Received",
                "description": "Your order has been received and is being processed.",
                "updated_at": datetime.datetime.now().isoformat(),
                "estimated_delivery": self._calculate_estimated_delivery()
            })
            
        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}", exc_info=True)
            return {
                "status": "unknown",
                "status_text": "Status Unknown",
                "description": "Unable to retrieve order status. Please contact support.",
                "updated_at": datetime.datetime.now().isoformat()
            }
    
    def _format_order_status_message(self, order_id: str, status_info: Dict) -> str:
        """Format order status message for user."""
        status = status_info.get("status", "unknown")
        status_text = status_info.get("status_text", "Unknown")
        description = status_info.get("description", "")
        updated_at = status_info.get("updated_at", "")
        estimated_delivery = status_info.get("estimated_delivery", "")
        
        # Status emojis
        status_emojis = {
            "received": "📋",
            "confirmed": "✅", 
            "preparing": "👨‍🍳",
            "ready": "🍽️",
            "on_the_way": "🚚",
            "delivered": "✅",
            "cancelled": "❌"
        }
        
        emoji = status_emojis.get(status, "📋")
        
        message = f"📦 *Order Tracking*\n\n"
        message += f"📋 *Order ID:* {order_id}\n"
        message += f"{emoji} *Status:* {status_text}\n\n"
        message += f"💬 *Details:* {description}\n\n"
        
        if estimated_delivery and status not in ["delivered", "cancelled"]:
            message += f"⏰ *Estimated Delivery:* {estimated_delivery}\n\n"
        
        if updated_at:
            try:
                updated_time = datetime.datetime.fromisoformat(updated_at)
                formatted_time = updated_time.strftime("%I:%M %p")
                message += f"🕐 *Last Updated:* {formatted_time}\n\n"
            except:
                pass
        
        # Add status-specific messages
        if status == "delivered":
            message += "🎉 Your order has been delivered! We hope you enjoyed your meal!"
        elif status == "on_the_way":
            message += "🚚 Your order is on the way! Please be available to receive it."
        elif status == "ready":
            message += "🍽️ Your order is ready for pickup/delivery!"
        elif status == "preparing":
            message += "👨‍🍳 Our kitchen is preparing your delicious meal!"
        else:
            message += "📱 We'll keep you updated on your order progress."
        
        return message
    
    def _calculate_estimated_delivery(self) -> str:
        """Calculate estimated delivery time."""
        try:
            # Add 30-45 minutes from now
            estimated_time = datetime.datetime.now() + datetime.timedelta(minutes=37)
            return estimated_time.strftime("%I:%M %p")
        except:
            return "30-45 minutes"
    
    def _handle_order_again(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle when user wants to order again."""
        # Reset to normal session flow but keep paid user status
        state["current_state"] = "greeting"
        state["current_handler"] = "greeting_handler"
        self.session_manager.update_session_state(session_id, state)
        
        return {"redirect": "greeting_handler", "redirect_message": "order"}
    
    def _handle_contact_support(self, state: Dict, session_id: str) -> Dict[str, Any]:
        """Handle contact support request."""
        order_id = state.get("recent_order_id", "N/A")
        
        support_message = (
            f"📞 *Customer Support*\n\n"
            f"📋 *Your Order ID:* {order_id}\n\n"
            f"📱 *WhatsApp:* +234-XXX-XXXX\n"
            f"📧 *Email:* support@lolaskitchen.com\n"
            f"⏰ *Hours:* 9:00 AM - 10:00 PM daily\n\n"
            f"💬 You can also send us a message here and we'll respond shortly!"
        )
        
        buttons = [
            {"type": "reply", "reply": {"id": "track_refresh", "title": "🔄 Check Status"}},
            {"type": "reply", "reply": {"id": "order_again", "title": "🛒 Order Again"}},
            {"type": "reply", "reply": {"id": "back_to_main", "title": "🏠 Main Menu"}}
        ]
        
        return self.whatsapp_service.create_button_message(
            session_id,
            support_message,
            buttons
        )
    
    def update_order_status(self, order_id: str, status: str, description: str = "") -> bool:
        """
        Update order status (to be called by admin/kitchen staff).
        
        Args:
            order_id (str): Order ID to update
            status (str): New status (received/confirmed/preparing/ready/on_the_way/delivered)
            description (str): Optional description
            
        Returns:
            bool: Success status
        """
        try:
            # Load existing status data
            status_data = {}
            if os.path.exists(self.order_status_file):
                with open(self.order_status_file, 'r') as f:
                    status_data = json.load(f)
            
            # Status text mapping
            status_texts = {
                "received": "Order Received",
                "confirmed": "Order Confirmed", 
                "preparing": "Preparing Your Order",
                "ready": "Ready for Delivery",
                "on_the_way": "On The Way",
                "delivered": "Delivered",
                "cancelled": "Cancelled"
            }
            
            # Update status
            status_data[order_id] = {
                "status": status,
                "status_text": status_texts.get(status, status.title()),
                "description": description or f"Your order is {status_texts.get(status, status)}.",
                "updated_at": datetime.datetime.now().isoformat(),
                "estimated_delivery": self._calculate_estimated_delivery() if status not in ["delivered", "cancelled"] else ""
            }
            
            # Save updated status
            with open(self.order_status_file, 'w') as f:
                json.dump(status_data, f, indent=2, default=str)
            
            logger.info(f"Updated order {order_id} status to: {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating order status for {order_id}: {e}", exc_info=True)
            return False
    
    def get_order_analytics(self) -> Dict[str, Any]:
        """Get order status analytics."""
        try:
            if not os.path.exists(self.order_status_file):
                return {"total_orders": 0, "message": "No order data available"}
            
            with open(self.order_status_file, 'r') as f:
                status_data = json.load(f)
            
            if not status_data:
                return {"total_orders": 0, "message": "No order data available"}
            
            total_orders = len(status_data)
            status_counts = {}
            
            for order_id, order_info in status_data.items():
                status = order_info.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_orders": total_orders,
                "status_counts": status_counts,
                "status_percentages": {
                    status: round((count / total_orders) * 100, 1)
                    for status, count in status_counts.items()
                },
                "last_updated": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting order analytics: {e}", exc_info=True)
            return {"error": "Failed to load order analytics"}