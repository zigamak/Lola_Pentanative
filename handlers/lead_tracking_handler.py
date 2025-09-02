import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import uuid
import psycopg2.errors

from .base_handler import BaseHandler
from utils.data_manager import DataManager, Lead
from services.lead_tracker import LeadTracker

logger = logging.getLogger(__name__)

class LeadTrackingHandler(BaseHandler):
    """Handles lead tracking integration with message processing."""
    
    def __init__(self, config, session_manager, data_manager: DataManager, whatsapp_service):
        super().__init__(config, session_manager, data_manager, whatsapp_service)
        self.lead_tracker = LeadTracker(config, data_manager)
        logger.info("LeadTrackingHandler initialized.")
    
    def track_user_interaction(self, phone_number: str, user_name: str, is_new_session: bool = False) -> bool:
        """
        Track user interaction for lead generation.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            is_new_session (bool): True if this is the start of a new session.
        
        Returns:
            bool: True if the interaction was tracked successfully.
        """
        try:
            result = self.lead_tracker.track_user_interaction(phone_number, user_name, is_new_session)
            logger.info(f"Successfully tracked user interaction for phone number {phone_number}")
            return result
        except Exception as e:
            logger.error(f"Error tracking user interaction for {phone_number}: {e}", exc_info=True)
            raise
    
    def track_cart_activity(self, phone_number: str, user_name: str, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> bool:
        """
        Track when a user adds items to cart or modifies their cart.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            cart (Union[List[Dict[str, Any]], Dict[str, Any]]): The current cart contents.
        
        Returns:
            bool: True if the cart activity was tracked successfully.
        """
        try:
            result = self.lead_tracker.track_cart_addition(phone_number, user_name, cart)
            logger.info(f"Successfully tracked cart activity for phone number {phone_number}")
            return result
        except Exception as e:
            logger.error(f"Error tracking cart activity for {phone_number}: {e}", exc_info=True)
            raise
    
    def track_order_conversion(self, phone_number: str, order_id: str, order_value: float) -> bool:
        """
        Track successful order conversion.
        
        Args:
            phone_number (str): The user's phone number.
            order_id (str): The unique ID of the completed order.
            order_value (float): The total value of the completed order in naira.
        
        Returns:
            bool: True if the order conversion was tracked successfully.
        """
        try:
            result = self.lead_tracker.track_order_completion(phone_number, order_id, order_value)
            logger.info(f"Successfully tracked order conversion for phone number {phone_number}, order ID {order_id}")
            return result
        except Exception as e:
            logger.error(f"Error tracking order conversion for {phone_number}: {e}", exc_info=True)
            raise
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """
        Get lead tracking analytics summary.
        
        Returns:
            Dict[str, Any]: A dictionary containing various lead analytics metrics.
        """
        try:
            analytics = self.lead_tracker.get_lead_analytics()
            logger.info("Successfully retrieved lead analytics summary")
            return analytics
        except Exception as e:
            logger.error(f"Error getting analytics summary: {e}", exc_info=True)
            return {}
    
    def get_abandoned_carts_for_remarketing(self, hours_ago: int = 24) -> List[Dict]:
        """
        Get abandoned carts for remarketing campaigns.
        
        Args:
            hours_ago (int): The number of hours ago to consider for abandonment.
            
        Returns:
            List[Dict]: A list of dictionaries, each representing an abandoned cart.
        """
        try:
            abandoned_carts = self.lead_tracker.get_abandoned_carts(hours_ago)
            logger.info(f"Successfully retrieved {len(abandoned_carts)} abandoned carts for remarketing")
            return abandoned_carts
        except Exception as e:
            logger.error(f"Error getting abandoned carts for remarketing: {e}", exc_info=True)
            return []