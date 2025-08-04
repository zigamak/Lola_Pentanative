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
                    self.data_manager.create_or_update_lead(lead)
                    logger.info(f"🆕 New lead created: {phone_number} ({user_name})")
                else:
                    lead_data = existing_lead or {}
                    lead_data.update({
                        'merchant_details_id': merchant_id,
                        'phone_number': phone_number,
                        'user_name': user_name or "Unknown",
                        'user_id': phone_number,
                        'last_interaction': datetime.now(timezone.utc),
                        'interaction_count': (lead_data.get('interaction_count', 0) + 1),
                        'status': lead_data.get('status', 'new_lead')
                    })
                    self.data_manager.create_or_update_lead(lead_data)
                    logger.info(f"Updated lead interaction: {phone_number}")
            else:
                if existing_lead:
                    lead_data = existing_lead
                    lead_data.update({
                        'last_interaction': datetime.now(timezone.utc),
                        'interaction_count': lead_data.get('interaction_count', 0) + 1
                    })
                    self.data_manager.create_or_update_lead(lead_data)
                    logger.info(f"Updated ongoing interaction: {phone_number}")
                
        except Exception as e:
            logger.error(f"Error tracking user interaction for {phone_number}: {e}", exc_info=True)
    
    def track_cart_addition(self, phone_number: str, user_name: str, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """
        Track when a user adds items to cart.
        
        Args:
            phone_number (str): User's phone number
            user_name (str): User's name
            cart (Union[List[Dict[str, Any]], Dict[str, Any]]): Cart contents
        """
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
            total_value = sum(item.get("price", 0.0) * item.get("quantity", 0) for item in cart_items)
            
            # Get or create lead
            merchant_id = getattr(self.config, 'MERCHANT_ID', None)
            if not merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return
                
            existing_lead = self.data_manager.get_lead_by_phone_number(phone_number)
            lead_data = existing_lead or {
                'merchant_details_id': merchant_id,
                'phone_number': phone_number,
                'user_name': user_name or "Unknown",
                'user_id': phone_number,
                'source': 'whatsapp',
                'first_contact': datetime.now(timezone.utc),
                'status': 'new_lead'
            }
            
            lead_data.update({
                'last_interaction': datetime.now(timezone.utc),
                'interaction_count': lead_data.get('interaction_count', 0) + 1,
                'has_added_to_cart': True,
                'total_cart_value': total_value,
                'conversion_stage': 'cart_added'
            })
            
            self.data_manager.create_or_update_lead(lead_data)
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
            lead_data = existing_lead or {
                'merchant_details_id': merchant_id,
                'phone_number': phone_number,
                'user_id': phone_number,
                'source': 'whatsapp',
                'first_contact': datetime.now(timezone.utc),
                'status': 'new_lead'
            }
            
            lead_data.update({
                'last_interaction': datetime.now(timezone.utc),
                'interaction_count': lead_data.get('interaction_count', 0) + 1,
                'has_placed_order': True,
                'final_order_value': order_value,
                'converted_at': datetime.now(timezone.utc),
                'status': 'converted',
                'conversion_stage': 'order_completed'
            })
            
            self.data_manager.create_or_update_lead(lead_data)
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
            return self.data_manager.get_abandoned_carts(hours_ago)
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