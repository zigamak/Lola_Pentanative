import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

from utils.data_manager import DataManager, Lead

logger = logging.getLogger(__name__)

class LeadTracker:
    """Tracks leads and cart abandonment for marketing insights using DataManager."""
    
    def __init__(self, config, data_manager: DataManager):
        self.config = config
        self.data_manager = data_manager
        logger.info("LeadTracker initialized with DataManager")
    
    def track_user_interaction(self, phone_number: str, user_name: str, is_new_session: bool = False) -> None:
        """
        Track user interaction for lead generation.
        
        Args:
            phone_number (str): User's phone number
            user_name (str): User's name from WhatsApp profile
            is_new_session (bool): True if this is a new session
        """
        try:
            merchant_id = getattr(self.config, 'MERCHANT_ID', None)
            if not merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return

            existing_lead = self.data_manager.get_lead_by_phone_number(phone_number)
            
            if is_new_session:
                is_existing_customer = phone_number in self.data_manager.user_details
                
                if not is_existing_customer and not existing_lead:
                    lead = Lead(
                        merchant_details_id=merchant_id,
                        phone_number=phone_number,
                        user_name=user_name or "Unknown",
                        user_id=phone_number,
                        source="whatsapp",
                        first_contact=datetime.now(timezone.utc),
                        last_interaction=datetime.now(timezone.utc),
                        interaction_count=1,
                        status="new_lead"
                    )
                    self.data_manager.save_lead(lead)  # Use save_lead instead of create_or_update_lead
                    logger.info(f"🆕 New lead created: {phone_number} ({user_name})")
                else:
                    lead = existing_lead or Lead(
                        merchant_details_id=merchant_id,
                        phone_number=phone_number,
                        user_name=user_name or "Unknown",
                        user_id=phone_number,
                        source="whatsapp",
                        first_contact=datetime.now(timezone.utc),
                        last_interaction=datetime.now(timezone.utc),
                        interaction_count=1,
                        status="new_lead"
                    )
                    lead.last_interaction = datetime.now(timezone.utc)
                    lead.interaction_count = (lead.interaction_count or 0) + 1
                    lead.status = lead.status or "new_lead"
                    self.data_manager.save_lead(lead)
                    logger.info(f"Updated lead interaction: {phone_number}")
            else:
                if existing_lead:
                    lead = existing_lead
                    lead.last_interaction = datetime.now(timezone.utc)
                    lead.interaction_count = (lead.interaction_count or 0) + 1
                    self.data_manager.save_lead(lead)
                    logger.info(f"Updated ongoing interaction: {phone_number}")
                
        except Exception as e:
            logger.error(f"Error tracking user interaction for {phone_number}: {e}", exc_info=True)
    
    def track_cart_addition(self, phone_number: str, user_name: str, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
    
        try:
            if not cart:
                logger.debug(f"No items in cart for tracking for {phone_number}. Skipping cart activity track.")
                return
                
            # Normalize cart format
            cart_items = self._normalize_cart_format(cart)
            if not cart_items:
                logger.debug(f"No valid items in cart for tracking for {phone_number}. Skipping cart activity track.")
                return
                
            # Calculate total cart value
            total_value = sum(float(item.get("price", 0.0)) * float(item.get("quantity", 0)) for item in cart_items)
            
            # Get or create lead
            merchant_id = getattr(self.config, 'MERCHANT_ID', None)
            if not merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return
                
            existing_lead = self.data_manager.get_lead_by_phone_number(phone_number)
            
            # Ensure all required fields have proper values
            current_time = datetime.now(timezone.utc)
            lead = existing_lead or Lead(
                merchant_details_id=merchant_id,
                phone_number=phone_number,
                user_name=user_name or "Unknown",
                user_id=phone_number,
                source="whatsapp",
                first_contact=current_time,
                last_interaction=current_time,
                interaction_count=0,  # Will be incremented below
                status="new_lead",
                has_added_to_cart=False,
                has_placed_order=False,
                total_cart_value=0.0,
                conversion_stage="initial_contact",
                final_order_value=0.0,
                converted_at=None
            )
            
            # Update lead fields
            lead.last_interaction = current_time
            lead.interaction_count = (lead.interaction_count or 0) + 1
            lead.has_added_to_cart = True
            lead.total_cart_value = float(total_value)  # Ensure this is a float
            lead.conversion_stage = "cart_added"
            
            # Ensure all required fields are set
            if not lead.first_contact:
                lead.first_contact = current_time
            if not lead.status:
                lead.status = "new_lead"
            if lead.total_cart_value is None:
                lead.total_cart_value = 0.0
                
            logger.debug(f"Saving lead with data: {lead.__dict__}")
            self.data_manager.save_lead(lead)
            logger.info(f"🛒 Cart activity tracked: {phone_number} - ₦{total_value:,.2f}")
            
        except Exception as e:
            logger.error(f"Error tracking cart addition for {phone_number}: {e}", exc_info=True)
    def _normalize_cart_format(self, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize cart format to ensure it's a list of dictionaries.
        
        Args:
            cart: Cart in either list or dictionary format
            
        Returns:
            List[Dict[str, Any]]: Normalized cart as list of item dictionaries
        """
        try:
            if isinstance(cart, list):
                return cart
            
            if isinstance(cart, dict):
                cart_items = []
                for item_name, item_data in cart.items():
                    if isinstance(item_data, dict):
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
                        logger.warning(f"Unexpected cart item format for {item_name}: {item_data}")
                return cart_items
                
            logger.warning(f"Unexpected cart format: {type(cart)}. Expected list or dict.")
            return []
            
        except Exception as e:
            logger.error(f"Error normalizing cart format: {e}", exc_info=True)
            return []
    
    def track_order_completion(self, phone_number: str, order_id: str, order_value: float) -> None:
        """
        Track when a user completes an order.
        
        Args:
            phone_number (str): User's phone number
            order_id (str): Order ID
            order_value (float): Order value in naira
        """
        try:
            merchant_id = getattr(self.config, 'MERCHANT_ID', None)
            if not merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return
                
            existing_lead = self.data_manager.get_lead_by_phone_number(phone_number)
            lead = existing_lead or Lead(
                merchant_details_id=merchant_id,
                phone_number=phone_number,
                user_id=phone_number,
                source="whatsapp",
                first_contact=datetime.now(timezone.utc),
                last_interaction=datetime.now(timezone.utc),
                status="new_lead"
            )
            
            lead.last_interaction = datetime.now(timezone.utc)
            lead.interaction_count = (lead.interaction_count or 0) + 1
            lead.has_placed_order = True
            lead.final_order_value = order_value
            lead.converted_at = datetime.now(timezone.utc)
            lead.status = "converted"
            lead.conversion_stage = "order_completed"
            
            self.data_manager.save_lead(lead)
            logger.info(f"💰 Conversion tracked: {phone_number} - {order_id} (₦{order_value:,})")
            
        except Exception as e:
            logger.error(f"Error tracking order completion for {phone_number}: {e}", exc_info=True)
    
    def get_abandoned_carts(self, hours_ago: int = 24) -> List[Dict]:
        """
        Get list of abandoned carts from specified hours ago.
        
        Args:
            hours_ago (int): Hours ago to check for abandonment
            
        Returns:
            List[Dict]: List of abandoned cart entries
        """
        try:
            return self.data_manager.get_abandoned_cart_leads(hours_ago)
        except Exception as e:
            logger.error(f"Error getting abandoned carts: {e}", exc_info=True)
            return []
    
    def get_lead_analytics(self) -> Dict:
        """
        Get comprehensive lead analytics.
        
        Returns:
            Dict: Lead analytics metrics
        """
        try:
            return self.data_manager.get_lead_analytics()
        except Exception as e:
            logger.error(f"Error getting lead analytics: {e}", exc_info=True)
            return {}