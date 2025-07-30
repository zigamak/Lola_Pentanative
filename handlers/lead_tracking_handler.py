import logging
import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class LeadTracker:
    """
    Manages lead tracking and conversion stages using the DataManager for persistence.
    """

    def __init__(self, data_manager, config):
        self.data_manager = data_manager
        self.config = config
        self.merchant_id = getattr(self.config, 'MERCHANT_ID', None)
        if not self.merchant_id:
            logger.error("MERCHANT_ID is not set in config, lead tracking will be limited.")

    def get_lead(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves an existing lead from the database.
        
        Args:
            phone_number (str): The lead's phone number.
            
        Returns:
            Optional[Dict[str, Any]]: The lead data dictionary, or None if not found.
        """
        return self.data_manager.get_lead_by_phone_number(phone_number)

    def track_new_lead(self, phone_number: str, user_name: str) -> bool:
        """
        Tracks a new user interaction as a potential lead.
        If the user already exists as a lead, this method will just update their interaction timestamp.
        
        Args:
            phone_number (str): The new user's phone number.
            user_name (str): The user's name.
            
        Returns:
            bool: True if a new lead was created, False if an existing one was updated.
        """
        existing_lead = self.get_lead(phone_number)
        
        if existing_lead:
            # Lead already exists, update their interaction
            self.update_lead_interaction(phone_number)
            return False
        
        # New lead, create a new record
        lead_data = {
            'merchant_details_id': self.merchant_id,
            'user_id': phone_number,
            'user_name': user_name,
            'phone_number': phone_number,
            'source': 'whatsapp',
            'first_contact': datetime.datetime.now(datetime.timezone.utc),
            'last_interaction': datetime.datetime.now(datetime.timezone.utc),
            'interaction_count': 1,
            'status': 'new_lead',
            'has_added_to_cart': False,
            'has_placed_order': False,
            'total_cart_value': 0.0,
            'conversion_stage': 'initial_contact',
            'final_order_value': 0.0,
            'converted_at': None
        }
        
        return self.data_manager.create_or_update_lead(lead_data)

    def update_lead_interaction(self, phone_number: str) -> bool:
        """
        Updates the last interaction timestamp and increments interaction count for an existing lead.
        
        Args:
            phone_number (str): The lead's phone number.
            
        Returns:
            bool: True if the update was successful, False otherwise.
        """
        existing_lead = self.get_lead(phone_number)
        if not existing_lead:
            logger.warning(f"Attempted to update interaction for non-existent lead: {phone_number}")
            return False

        existing_lead['last_interaction'] = datetime.datetime.now(datetime.timezone.utc)
        existing_lead['interaction_count'] += 1 # This will be handled by the SQL query's `+ 1`
        
        return self.data_manager.create_or_update_lead(existing_lead)

    def track_cart_addition(self, phone_number: str, user_name: str, cart_items: List[Dict], total_value: float) -> bool:
        """
        Updates a lead's status when they add an item to their cart.
        
        Args:
            phone_number (str): The lead's phone number.
            user_name (str): The lead's name.
            cart_items (List[Dict]): The items in the cart.
            total_value (float): The total value of the cart.
            
        Returns:
            bool: True if the update was successful, False otherwise.
        """
        existing_lead = self.get_lead(phone_number)
        
        # If lead doesn't exist, create it first
        if not existing_lead:
            self.track_new_lead(phone_number, user_name)
            existing_lead = self.get_lead(phone_number)
            if not existing_lead:
                logger.error(f"Failed to create lead for cart addition: {phone_number}")
                return False

        existing_lead['has_added_to_cart'] = True
        existing_lead['total_cart_value'] = total_value
        existing_lead['conversion_stage'] = 'cart_added'
        existing_lead['last_interaction'] = datetime.datetime.now(datetime.timezone.utc)
        
        return self.data_manager.create_or_update_lead(existing_lead)

    def track_order_completion(self, phone_number: str, order_id: str, order_value: float) -> bool:
        """
        Updates a lead's status when they complete an order, marking them as converted.
        
        Args:
            phone_number (str): The lead's phone number.
            order_id (str): The completed order's ID.
            order_value (float): The total value of the order.
            
        Returns:
            bool: True if the update was successful, False otherwise.
        """
        existing_lead = self.get_lead(phone_number)
        
        # If the lead doesn't exist, we can't track a conversion for them.
        if not existing_lead:
            logger.warning(f"Order completed by unknown user. Cannot track conversion for {phone_number}.")
            return False

        existing_lead['has_placed_order'] = True
        existing_lead['status'] = 'converted'
        existing_lead['final_order_value'] = order_value
        existing_lead['converted_at'] = datetime.datetime.now(datetime.timezone.utc)
        existing_lead['conversion_stage'] = 'converted_to_customer'
        existing_lead['last_interaction'] = datetime.datetime.now(datetime.timezone.utc)
        
        return self.data_manager.create_or_update_lead(existing_lead)

    def get_abandoned_carts(self, hours_ago: int = 24) -> List[Dict]:
        """
        Delegates to DataManager to retrieve a list of abandoned carts.
        
        Args:
            hours_ago (int): The number of hours ago to consider for abandonment.
            
        Returns:
            List[Dict]: A list of dictionaries, each representing an abandoned cart.
        """
        return self.data_manager.get_abandoned_carts(hours_ago)

    def get_lead_analytics(self) -> Dict[str, Any]:
        """
        Delegates to DataManager to retrieve a summary of lead analytics.
        
        Returns:
            Dict[str, Any]: A dictionary containing various lead analytics metrics.
        """
        return self.data_manager.get_lead_analytics()