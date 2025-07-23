import json
import os
import datetime
import logging
from typing import Dict, List, Optional, Any, Union

from .base_handler import BaseHandler
from services.lead_tracker import LeadTracker

logger = logging.getLogger(__name__)

class LeadTrackingHandler(BaseHandler):
    """Handles lead tracking integration with message processing."""
    
    def __init__(self, config, session_manager, data_manager, whatsapp_service, lead_tracker=None):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        # Initialize LeadTracker, allowing an external instance to be passed for testing/dependency injection
        self.lead_tracker = lead_tracker or LeadTracker(config)
        logger.info("LeadTrackingHandler initialized.")
    
    def track_user_interaction(self, phone_number: str, user_name: str, is_new_session: bool = False) -> None:
        """
        Track user interaction for lead generation.
        This method checks if it's a new session or an existing customer interaction,
        and updates lead data accordingly.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            is_new_session (bool): True if this is the start of a new session.
        """
        try:
            if is_new_session:
                # Determine if the user is an existing customer based on data_manager
                is_existing_customer = phone_number in self.data_manager.user_details # Assuming user_details holds known customers
                
                if not is_existing_customer:
                    # If not an existing customer, attempt to track as a new lead
                    is_new_lead = self.lead_tracker.track_new_lead(phone_number, user_name)
                    if is_new_lead:
                        logger.info(f"🆕 New lead detected: {phone_number} ({user_name})")
                    else:
                        # If not a new lead (i.e., already tracked), just update their interaction
                        self.lead_tracker.update_lead_interaction(phone_number)
                else:
                    # Existing customer - just update their interaction timestamp and count
                    self.lead_tracker.update_lead_interaction(phone_number)
            else:
                # For ongoing interactions within a session, simply update interaction
                self.lead_tracker.update_lead_interaction(phone_number)
                
        except Exception as e:
            logger.error(f"Error tracking user interaction for {phone_number}: {e}", exc_info=True)
    
    def track_cart_activity(self, phone_number: str, user_name: str, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """
        Track when a user adds items to cart or modifies their cart.
        This method handles both list of dictionaries and dictionary formats for cart.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            cart (Union[List[Dict[str, Any]], Dict[str, Any]]): The current cart contents.
        """
        try:
            if cart:  # Only track if cart has items
                # Convert cart to list format if it's a dictionary
                cart_items = self._normalize_cart_format(cart)
                
                if cart_items:  # Only proceed if we have valid cart items
                    # Calculate total cart value from the list of dictionaries
                    total_value = sum(item.get("price", 0.0) * item.get("quantity", 0) for item in cart_items)
                    
                    # Track cart addition (or update) using the LeadTracker service
                    self.lead_tracker.track_cart_addition(phone_number, user_name, cart_items, total_value)
                    
                    logger.info(f"🛒 Cart activity tracked: {phone_number} - ₦{total_value:,.2f}")
                else:
                    logger.debug(f"No valid items in cart for tracking for {phone_number}. Skipping cart activity track.")
            else:
                logger.debug(f"No items in cart for tracking for {phone_number}. Skipping cart activity track.")
                
        except Exception as e:
            logger.error(f"Error tracking cart activity for {phone_number}: {e}", exc_info=True)
    
    def _normalize_cart_format(self, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize cart format to ensure it's a list of dictionaries.
        
        Args:
            cart: Cart in either list or dictionary format
            
        Returns:
            List[Dict[str, Any]]: Normalized cart as list of item dictionaries
        """
        try:
            # If cart is already a list, return as is
            if isinstance(cart, list):
                return cart
            
            # If cart is a dictionary, convert to list format
            if isinstance(cart, dict):
                cart_items = []
                for item_name, item_data in cart.items():
                    if isinstance(item_data, dict):
                        # Extract item details from the nested dictionary
                        cart_item = {
                            "name": item_name,
                            "item_id": item_data.get("item_id", item_name),
                            "quantity": item_data.get("quantity", 0),
                            "price": item_data.get("price", 0.0),
                            "total_price": item_data.get("total_price", 0.0),
                            "variations": item_data.get("variations", {})
                        }
                        cart_items.append(cart_item)
                    else:
                        # Handle case where item_data might be a simple value
                        logger.warning(f"Unexpected cart item format for {item_name}: {item_data}")
                
                return cart_items
            
            # If cart is neither list nor dict, log warning and return empty list
            logger.warning(f"Unexpected cart format: {type(cart)}. Expected list or dict.")
            return []
            
        except Exception as e:
            logger.error(f"Error normalizing cart format: {e}", exc_info=True)
            return []
    
    def track_order_conversion(self, phone_number: str, order_id: str, order_value: float) -> None:
        """
        Track successful order conversion.
        
        Args:
            phone_number (str): The user's phone number.
            order_id (str): The unique ID of the completed order.
            order_value (float): The total value of the completed order in naira.
        """
        try:
            self.lead_tracker.track_order_completion(phone_number, order_id, order_value)
            logger.info(f"💰 Conversion tracked: {phone_number} - {order_id} (₦{order_value:,})")
            
        except Exception as e:
            logger.error(f"Error tracking order conversion for {phone_number}: {e}", exc_info=True)
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """
        Get lead tracking analytics summary from the LeadTracker service.
        
        Returns:
            Dict[str, Any]: A dictionary containing various lead analytics metrics.
        """
        try:
            return self.lead_tracker.get_lead_analytics()
        except Exception as e:
            logger.error(f"Error getting analytics summary: {e}", exc_info=True)
            return {}
    
    def get_abandoned_carts_for_remarketing(self, hours_ago: int = 24) -> List[Dict]:
        """
        Get abandoned carts for remarketing campaigns from the LeadTracker service.
        
        Args:
            hours_ago (int): The number of hours ago to consider for abandonment.
            
        Returns:
            List[Dict]: A list of dictionaries, each representing an abandoned cart.
        """
        try:
            return self.lead_tracker.get_abandoned_carts(hours_ago)
        except Exception as e:
            logger.error(f"Error getting abandoned carts for remarketing: {e}", exc_info=True)
            return []