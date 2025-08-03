import logging
from typing import Dict, List, Any, Union
from .data_manager import DataManager, Lead
import datetime

logger = logging.getLogger(__name__)

class LeadTracker:
    """Handles lead tracking and management using DataManager for database operations."""

    def __init__(self, config):
        self.config = config
        self.data_manager = DataManager(config)
        logger.info("LeadTracker initialized.")

    def track_new_lead(self, phone_number: str, user_name: str) -> bool:
        """
        Tracks a new lead if it doesn't exist in the database.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            
        Returns:
            bool: True if a new lead was created, False if it already exists.
        """
        try:
            # Check if lead already exists
            existing_lead = self.data_manager.get_lead_by_phone_number(phone_number)
            if existing_lead:
                logger.debug(f"Lead already exists for {phone_number}. Not creating a new lead.")
                return False

            # Create a new lead
            lead = Lead(
                merchant_details_id=getattr(self.config, 'MERCHANT_ID', '18'),
                phone_number=phone_number,
                user_name=user_name,
                user_id=phone_number,  # Default to phone_number if no specific user_id
                source="whatsapp",
                status="new_lead",
                first_contact=datetime.datetime.now(datetime.timezone.utc),
                last_interaction=datetime.datetime.now(datetime.timezone.utc),
                interaction_count=1
            )
            success = self.data_manager.create_or_update_lead(lead)
            if success:
                logger.info(f"New lead created for {phone_number} ({user_name}).")
                return True
            else:
                logger.error(f"Failed to create new lead for {phone_number}.")
                return False
        except Exception as e:
            logger.error(f"Error tracking new lead for {phone_number}: {e}", exc_info=True)
            return False

    def update_lead_interaction(self, phone_number: str) -> None:
        """
        Updates the interaction count and last interaction timestamp for a lead.
        
        Args:
            phone_number (str): The user's phone number.
        """
        try:
            lead_data = self.data_manager.get_lead_by_phone_number(phone_number)
            if not lead_data:
                logger.debug(f"No lead found for {phone_number}. Cannot update interaction.")
                return

            # Update interaction details
            lead_data['last_interaction'] = datetime.datetime.now(datetime.timezone.utc)
            lead_data['interaction_count'] = lead_data.get('interaction_count', 0) + 1
            success = self.data_manager.create_or_update_lead(lead_data)
            if success:
                logger.debug(f"Updated interaction for lead {phone_number}.")
            else:
                logger.error(f"Failed to update interaction for lead {phone_number}.")
        except Exception as e:
            logger.error(f"Error updating lead interaction for {phone_number}: {e}", exc_info=True)

    def track_cart_addition(self, phone_number: str, user_name: str, cart_items: List[Dict[str, Any]], total_value: float) -> None:
        """
        Tracks when a user adds items to their cart.
        
        Args:
            phone_number (str): The user's phone number.
            user_name (str): The user's name.
            cart_items (List[Dict[str, Any]]): List of cart items.
            total_value (float): Total value of the cart.
        """
        try:
            lead_data = self.data_manager.get_lead_by_phone_number(phone_number)
            if not lead_data:
                # Create a new lead if it doesn't exist
                lead = Lead(
                    merchant_details_id=getattr(self.config, 'MERCHANT_ID', '18'),
                    phone_number=phone_number,
                    user_name=user_name,
                    user_id=phone_number,
                    source="whatsapp",
                    status="new_lead",
                    first_contact=datetime.datetime.now(datetime.timezone.utc),
                    last_interaction=datetime.datetime.now(datetime.timezone.utc),
                    interaction_count=1,
                    has_added_to_cart=True,
                    total_cart_value=total_value,
                    conversion_stage="cart_added"
                )
                self.data_manager.create_or_update_lead(lead)
                logger.info(f"Created new lead with cart activity for {phone_number}.")
            else:
                # Update existing lead with cart activity
                lead_data['last_interaction'] = datetime.datetime.now(datetime.timezone.utc)
                lead_data['interaction_count'] = lead_data.get('interaction_count', 0) + 1
                lead_data['has_added_to_cart'] = True
                lead_data['total_cart_value'] = total_value
                lead_data['conversion_stage'] = "cart_added"
                success = self.data_manager.create_or_update_lead(lead_data)
                if success:
                    logger.debug(f"Updated lead {phone_number} with cart activity: ₦{total_value:,.2f}.")
                else:
                    logger.error(f"Failed to update lead {phone_number} with cart activity.")
        except Exception as e:
            logger.error(f"Error tracking cart addition for {phone_number}: {e}", exc_info=True)

    def track_order_completion(self, phone_number: str, order_id: str, order_value: float) -> None:
        """
        Tracks a successful order completion for a lead.
        
        Args:
            phone_number (str): The user's phone number.
            order_id (str): The unique ID of the completed order.
            order_value (float): The total value of the completed order.
        """
        try:
            lead_data = self.data_manager.get_lead_by_phone_number(phone_number)
            if not lead_data:
                logger.warning(f"No lead found for {phone_number}. Creating new lead for order completion.")
                lead = Lead(
                    merchant_details_id=getattr(self.config, 'MERCHANT_ID', '18'),
                    phone_number=phone_number,
                    user_name="Unknown",
                    user_id=phone_number,
                    source="whatsapp",
                    status="converted",
                    first_contact=datetime.datetime.now(datetime.timezone.utc),
                    last_interaction=datetime.datetime.now(datetime.timezone.utc),
                    interaction_count=1,
                    has_placed_order=True,
                    final_order_value=order_value,
                    conversion_stage="order_completed",
                    converted_at=datetime.datetime.now(datetime.timezone.utc)
                )
                self.data_manager.create_or_update_lead(lead)
                logger.info(f"Created new lead with order completion for {phone_number}: {order_id} (₦{order_value:,.2f}).")
            else:
                lead_data['last_interaction'] = datetime.datetime.now(datetime.timezone.utc)
                lead_data['interaction_count'] = lead_data.get('interaction_count', 0) + 1
                lead_data['has_placed_order'] = True
                lead_data['final_order_value'] = order_value
                lead_data['status'] = "converted"
                lead_data['conversion_stage'] = "order_completed"
                lead_data['converted_at'] = datetime.datetime.now(datetime.timezone.utc)
                success = self.data_manager.create_or_update_lead(lead_data)
                if success:
                    logger.debug(f"Updated lead {phone_number} with order completion: {order_id} (₦{order_value:,.2f}).")
                else:
                    logger.error(f"Failed to update lead {phone_number} with order completion.")
        except Exception as e:
            logger.error(f"Error tracking order completion for {phone_number}: {e}", exc_info=True)

    def get_lead_analytics(self) -> Dict[str, Any]:
        """
        Retrieves lead analytics summary from DataManager.
        
        Returns:
            Dict[str, Any]: Analytics metrics for leads.
        """
        return self.data_manager.get_lead_analytics()

    def get_abandoned_carts(self, hours_ago: int = 24) -> List[Dict]:
        """
        Retrieves abandoned carts for remarketing from DataManager.
        
        Args:
            hours_ago (int): The number of hours ago to consider for abandonment.
            
        Returns:
            List[Dict]: List of abandoned cart details.
        """
        return self.data_manager.get_abandoned_carts(hours_ago)