import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import psycopg2.errors

from utils.data_manager import DataManager, Lead

logger = logging.getLogger(__name__)

class LeadTracker:
    """Tracks leads and cart abandonment for marketing insights using DataManager."""
    
    def __init__(self, config, data_manager: DataManager):
        self.config = config
        self.data_manager = data_manager
        self.merchant_id = getattr(self.config, 'MERCHANT_ID', None)
        if not self.merchant_id:
            logger.error("MERCHANT_ID not set in config. Using default '20'.")
            self.merchant_id = '20'
        logger.info("LeadTracker initialized with DataManager")
    
    def track_user_interaction(self, phone_number: str, user_name: str, is_new_session: bool = False) -> bool:
        """
        Track user interaction for lead generation.
        
        Args:
            phone_number (str): User's phone number
            user_name (str): User's name from WhatsApp profile
            is_new_session (bool): True if this is a new session
        
        Returns:
            bool: True if the interaction was tracked successfully
        """
        try:
            if not self.merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return False

            # Use phone_number as user_id, as per Lead class convention
            existing_lead = self.data_manager.get_lead(self.merchant_id, phone_number)
            current_time = datetime.now(timezone.utc)
            
            if is_new_session:
                is_existing_customer = phone_number in getattr(self.data_manager, 'user_details', {})
                
                lead = existing_lead or Lead(
                    merchant_details_id=self.merchant_id,
                    phone_number=phone_number,
                    user_name=user_name or "Unknown",
                    user_id=phone_number,
                    source="whatsapp",
                    first_contact=current_time,
                    last_interaction=current_time,
                    interaction_count=1,
                    status="new_lead"
                )
                
                if existing_lead:
                    lead.last_interaction = current_time
                    lead.interaction_count = (lead.interaction_count or 0) + 1
                    lead.user_name = user_name or lead.user_name or "Unknown"
                
                self.data_manager.save_lead(lead)
                logger.info(f"{'🆕 New lead created' if not existing_lead else 'Updated lead interaction'}: {phone_number} ({user_name})")
            else:
                if existing_lead:
                    lead = existing_lead
                    lead.last_interaction = current_time
                    lead.interaction_count = (lead.interaction_count or 0) + 1
                    self.data_manager.save_lead(lead)
                    logger.info(f"Updated ongoing interaction: {phone_number}")
                else:
                    logger.debug(f"No existing lead for {phone_number} and not a new session. Skipping interaction tracking.")
                    return True

            return True
        except AttributeError as e:
            logger.error(f"DataManager method error for {phone_number}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error tracking user interaction for {phone_number}: {e}", exc_info=True)
            raise
    
    def track_cart_addition(self, phone_number: str, user_name: str, cart: Union[List[Dict[str, Any]], Dict[str, Any]]) -> bool:
        """
        Track when a user adds items to cart or modifies their cart.
        
        Args:
            phone_number (str): User's-linebreak: User's phone number
            user_name (str): User's name from WhatsApp profile
            cart (Union[List[Dict[str, Any]], Dict[str, Any]]): The current cart contents
        
        Returns:
            bool: True if cart activity was tracked successfully
        """
        try:
            if not cart:
                logger.debug(f"No items in cart for tracking for {phone_number}. Skipping cart activity track.")
                return True
                
            # Normalize cart format
            cart_items = self._normalize_cart_format(cart)
            if not cart_items:
                logger.debug(f"No valid items in cart for tracking for {phone_number}. Skipping cart activity track.")
                return True
                
            # Calculate total cart value
            total_value = sum(float(item.get("price", 0.0)) * float(item.get("quantity", 0)) for item in cart_items)
            
            if not self.merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return False
                
            existing_lead = self.data_manager.get_lead(self.merchant_id, phone_number)
            current_time = datetime.now(timezone.utc)
            
            lead = existing_lead or Lead(
                merchant_details_id=self.merchant_id,
                phone_number=phone_number,
                user_name=user_name or "Unknown",
                user_id=phone_number,
                source="whatsapp",
                first_contact=current_time,
                last_interaction=current_time,
                interaction_count=0,
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
            lead.total_cart_value = float(total_value)
            lead.conversion_stage = "cart_added"
            lead.user_name = user_name or lead.user_name or "Unknown"
            
            logger.debug(f"Saving lead with data: {lead.__dict__}")
            self.data_manager.save_lead(lead)
            logger.info(f"🛒 Cart activity tracked: {phone_number} - ₦{total_value:,.2f}")
            return True
            
        except AttributeError as e:
            logger.error(f"DataManager method error for {phone_number}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error tracking cart addition for {phone_number}: {e}", exc_info=True)
            raise
    
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
                return [item for item in cart if item.get("price") is not None and item.get("quantity") is not None]
            
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
                        if cart_item["price"] is not None and cart_item["quantity"] is not None:
                            cart_items.append(cart_item)
                    else:
                        logger.warning(f"Unexpected cart item format for {item_name}: {item_data}")
                return cart_items
                
            logger.warning(f"Unexpected cart format: {type(cart)}. Expected list or dict.")
            return []
            
        except Exception as e:
            logger.error(f"Error normalizing cart format: {e}", exc_info=True)
            return []
    
    def track_order_completion(self, phone_number: str, order_id: str, order_value: float) -> bool:
        """
        Track when a user completes an order.
        
        Args:
            phone_number (str): User's phone number
            order_id (str): Order ID
            order_value (float): Order value in naira
        
        Returns:
            bool: True if order completion was tracked successfully
        """
        try:
            if not self.merchant_id:
                logger.error("MERCHANT_ID not set in config")
                return False
                
            existing_lead = self.data_manager.get_lead(self.merchant_id, phone_number)
            current_time = datetime.now(timezone.utc)
            
            lead = existing_lead or Lead(
                merchant_details_id=self.merchant_id,
                phone_number=phone_number,
                user_id=phone_number,
                user_name="Unknown",
                source="whatsapp",
                first_contact=current_time,
                last_interaction=current_time,
                interaction_count=0,
                status="new_lead"
            )
            
            lead.last_interaction = current_time
            lead.interaction_count = (lead.interaction_count or 0) + 1
            lead.has_placed_order = True
            lead.final_order_value = float(order_value)
            lead.converted_at = current_time
            lead.status = "converted"
            lead.conversion_stage = "order_completed"
            
            self.data_manager.save_lead(lead)
            logger.info(f"💰 Conversion tracked: {phone_number} - {order_id} (₦{order_value:,.2f})")
            return True
            
        except AttributeError as e:
            logger.error(f"DataManager method error for {phone_number}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error tracking order completion for {phone_number}: {e}", exc_info=True)
            raise
    
    def get_abandoned_carts(self, hours_ago: int = 24) -> List[Dict]:
        """
        Get list of abandoned carts from specified hours ago.
        
        Args:
            hours_ago (int): Hours ago to check for abandonment
            
        Returns:
            List[Dict]: List of abandoned cart entries
        """
        try:
            abandoned_carts = self.data_manager.get_abandoned_cart_leads(hours_ago)
            logger.info(f"Retrieved {len(abandoned_carts)} abandoned carts")
            return abandoned_carts
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
            merchant_id = getattr(self.config, 'MERCHANT_ID', '20')
            with psycopg2.connect(**self.data_manager.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            status, 
                            COUNT(*) as count,
                            SUM(total_cart_value) as total_cart_value,
                            SUM(final_order_value) as total_order_value
                        FROM whatsapp_leads
                        WHERE merchant_details_id = %s
                        GROUP BY status
                    """, (merchant_id,))
                    results = cur.fetchall()
                    analytics = {
                        "total_leads": sum(row['count'] for row in results),
                        "by_status": {row['status']: row['count'] for row in results},
                        "total_cart_value": sum(row['total_cart_value'] or 0 for row in results),
                        "total_order_value": sum(row['total_order_value'] or 0 for row in results),
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                    logger.info(f"Retrieved lead analytics: {analytics}")
                    return analytics
        except psycopg2.Error as e:
            logger.error(f"Database error retrieving lead analytics: {e}", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"Unexpected error retrieving lead analytics: {e}", exc_info=True)
            return {}