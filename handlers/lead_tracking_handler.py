import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import uuid

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
    
    def track_user_interaction(self, phone_number: str, user_name: str, is_new_session: bool = False) -> None:
        """
        Track user interaction for lead generation.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            is_new_session (bool): True if this is the start of a new session.
        """
        try:
            self.lead_tracker.track_user_interaction(phone_number, user_name, is_new_session)
        except Exception as e:
            logger.error(f"Error tracking user interaction for {phone_number}: {e}", exc_info=True)
    
    def track_cart_activity(self, phone_number: str, user_name: str, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """
        Track when a user adds items to cart or modifies their cart.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            cart (Union[List[Dict[str, Any]], Dict[str, Any]]): The current cart contents.
        """
        try:
            self.lead_tracker.track_cart_addition(phone_number, user_name, cart)
        except Exception as e:
            logger.error(f"Error tracking cart activity for {phone_number}: {e}", exc_info=True)
    
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
        except Exception as e:
            logger.error(f"Error tracking order conversion for {phone_number}: {e}", exc_info=True)
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """
        Get lead tracking analytics summary.
        
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
        Get abandoned carts for remarketing campaigns.
        
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