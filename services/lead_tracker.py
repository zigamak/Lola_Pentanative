import json
import os
import datetime
import logging
from typing import Dict, List, Optional, Any # Added Any for more flexible type hinting

logger = logging.getLogger(__name__)

class LeadTracker:
    """Tracks leads and cart abandonment for marketing insights."""
    
    def __init__(self, config=None):
        self.config = config
        self.leads_file = "data/leads.json"
        self.cart_abandonment_file = "data/addedtocart.json"
        
        # Ensure data files exist
        self._ensure_files_exist()
        logger.info("LeadTracker initialized")
    
    def _ensure_files_exist(self):
        """Ensure lead tracking files exist."""
        files_to_create = [self.leads_file, self.cart_abandonment_file]
        
        for file_path in files_to_create:
            if not os.path.exists(file_path):
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Create empty JSON file
                with open(file_path, 'w') as f:
                    json.dump([], f, indent=2)
                logger.info(f"Created lead tracking file: {file_path}")
    
    def track_new_lead(self, phone_number: str, user_name: str, source: str = "whatsapp") -> bool:
        """
        Track a new lead when someone starts messaging.
        
        Args:
            phone_number (str): User's phone number
            user_name (str): User's name from WhatsApp profile
            source (str): Source of the lead (default: whatsapp)
            
        Returns:
            bool: True if new lead, False if existing
        """
        try:
            # Check if lead already exists
            if self._is_existing_lead(phone_number):
                logger.debug(f"Lead already exists for {phone_number}")
                return False
            
            # Load existing leads
            leads = self._load_json_file(self.leads_file)
            
            # Create new lead entry
            new_lead = {
                "phone_number": phone_number,
                "user_name": user_name or "Unknown",
                "source": source,
                "first_contact": datetime.datetime.now().isoformat(),
                "last_interaction": datetime.datetime.now().isoformat(),
                "interaction_count": 1,
                "status": "new",
                "has_added_to_cart": False,
                "has_placed_order": False,
                "total_cart_value": 0,
                "conversion_stage": "initial_contact"
            }
            
            # Add to leads list
            leads.append(new_lead)
            
            # Save updated leads
            self._save_json_file(self.leads_file, leads)
            
            logger.info(f"New lead tracked: {phone_number} ({user_name})")
            return True
            
        except Exception as e:
            logger.error(f"Error tracking new lead {phone_number}: {e}")
            return False
    
    def update_lead_interaction(self, phone_number: str) -> None:
        """Update lead interaction count and timestamp."""
        try:
            leads = self._load_json_file(self.leads_file)
            
            for lead in leads:
                if lead["phone_number"] == phone_number:
                    lead["last_interaction"] = datetime.datetime.now().isoformat()
                    lead["interaction_count"] = lead.get("interaction_count", 0) + 1
                    break
            
            self._save_json_file(self.leads_file, leads)
            
        except Exception as e:
            logger.error(f"Error updating lead interaction for {phone_number}: {e}")
    
    def track_cart_addition(self, phone_number: str, user_name: str, cart: List[Dict[str, Any]], total_value: float) -> None:
        """
        Track when a user adds items to cart.
        The 'cart' parameter is now expected to be a List of Dictionaries.
        
        Args:
            phone_number (str): User's phone number
            user_name (str): User's name
            cart (List[Dict[str, Any]]): Cart contents as a list of item dictionaries
            total_value (float): Total cart value in naira
        """
        try:
            # Update lead status
            self._update_lead_cart_status(phone_number, True, total_value)
            
            # Load existing cart data
            cart_data = self._load_json_file(self.cart_abandonment_file)
            
            # Check if user already has cart entry
            existing_entry_index: Optional[int] = None
            for i, entry in enumerate(cart_data):
                if entry["phone_number"] == phone_number:
                    existing_entry_index = i
                    break
            
            # Calculate items_count and most_expensive_item based on the list-based cart
            items_count = sum(item.get("quantity", 0) for item in cart)
            most_expensive_item_price = 0.0
            if cart:
                most_expensive_item_price = max(cart, key=lambda x: x.get("price", 0.0)).get("price", 0.0)

            # Create or update cart entry
            cart_entry = {
                "phone_number": phone_number,
                "user_name": user_name or "Unknown",
                "cart_items": cart, # Storing the list directly
                "total_value": total_value,
                "cart_created": cart_data[existing_entry_index]["cart_created"] if existing_entry_index is not None else datetime.datetime.now().isoformat(),
                "last_updated": datetime.datetime.now().isoformat(),
                "status": "active",
                "reminder_sent": False,
                "conversion_probability": self._calculate_conversion_probability(phone_number, cart),
                "items_count": items_count,
                "most_expensive_item": most_expensive_item_price,
                "cart_sessions": cart_data[existing_entry_index].get("cart_sessions", 0) + 1 if existing_entry_index is not None else 1
            }
            
            if existing_entry_index is not None:
                # Update existing entry
                cart_data[existing_entry_index] = cart_entry
            else:
                # Add new entry
                cart_data.append(cart_entry)
            
            # Save updated cart data
            self._save_json_file(self.cart_abandonment_file, cart_data)
            
            logger.info(f"Cart addition tracked for {phone_number}: ₦{total_value:,} ({len(cart)} items)")
            
        except Exception as e:
            logger.error(f"Error tracking cart addition for {phone_number}: {e}", exc_info=True)
    
    def track_order_completion(self, phone_number: str, order_id: str, order_value: float) -> None:
        """
        Track when a user completes an order.
        
        Args:
            phone_number (str): User's phone number
            order_id (str): Order ID
            order_value (float): Order value in naira
        """
        try:
            # Update lead status
            self._update_lead_conversion(phone_number, order_value)
            
            # Update cart abandonment status
            cart_data = self._load_json_file(self.cart_abandonment_file)
            
            for entry in cart_data:
                if entry["phone_number"] == phone_number:
                    entry["status"] = "converted"
                    entry["converted_at"] = datetime.datetime.now().isoformat()
                    entry["order_id"] = order_id
                    entry["final_order_value"] = order_value
                    break
            
            self._save_json_file(self.cart_abandonment_file, cart_data)
            
            logger.info(f"Order completion tracked for {phone_number}: {order_id} (₦{order_value:,})")
            
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
            cart_data = self._load_json_file(self.cart_abandonment_file)
            abandoned_carts = []
            
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours_ago)
            
            for entry in cart_data:
                if entry["status"] == "active":
                    last_updated = datetime.datetime.fromisoformat(entry["last_updated"])
                    
                    if last_updated < cutoff_time:
                        entry["hours_since_abandonment"] = (datetime.datetime.now() - last_updated).total_seconds() / 3600
                        abandoned_carts.append(entry)
            
            # Sort by conversion probability (highest first)
            abandoned_carts.sort(key=lambda x: x.get("conversion_probability", 0), reverse=True)
            
            return abandoned_carts
            
        except Exception as e:
            logger.error(f"Error getting abandoned carts: {e}", exc_info=True)
            return []
    
    def get_lead_analytics(self) -> Dict:
        """Get comprehensive lead analytics."""
        try:
            leads = self._load_json_file(self.leads_file)
            cart_data = self._load_json_file(self.cart_abandonment_file)
            
            total_leads = len(leads)
            converted_leads = len([lead for lead in leads if lead.get("has_placed_order", False)])
            cart_additions = len([lead for lead in leads if lead.get("has_added_to_cart", False)])
            
            # Calculate conversion rates
            cart_conversion_rate = (cart_additions / total_leads * 100) if total_leads > 0 else 0
            order_conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
            
            # Calculate cart abandonment
            active_carts = len([cart_entry for cart_entry in cart_data if cart_entry["status"] == "active"])
            abandoned_rate = (active_carts / cart_additions * 100) if cart_additions > 0 else 0
            
            # Calculate average cart value
            total_cart_value = sum(cart_entry["total_value"] for cart_entry in cart_data)
            avg_cart_value = total_cart_value / len(cart_data) if cart_data else 0
            
            return {
                "total_leads": total_leads,
                "cart_additions": cart_additions,
                "converted_leads": converted_leads,
                "active_abandoned_carts": active_carts,
                "cart_conversion_rate": round(cart_conversion_rate, 2),
                "order_conversion_rate": round(order_conversion_rate, 2),
                "cart_abandonment_rate": round(abandoned_rate, 2),
                "average_cart_value": round(avg_cart_value, 2),
                "total_cart_value": round(total_cart_value, 2),
                "last_updated": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting lead analytics: {e}", exc_info=True)
            return {}
    
    def _is_existing_lead(self, phone_number: str) -> bool:
        """Check if phone number is already a tracked lead."""
        try:
            leads = self._load_json_file(self.leads_file)
            return any(lead["phone_number"] == phone_number for lead in leads)
        except Exception as e: # Catch specific exception for more robust error handling
            logger.error(f"Error checking existing lead for {phone_number}: {e}", exc_info=True)
            return False
    
    def _update_lead_cart_status(self, phone_number: str, has_cart: bool, cart_value: float) -> None:
        """Update lead's cart status."""
        try:
            leads = self._load_json_file(self.leads_file)
            
            for lead in leads:
                if lead["phone_number"] == phone_number:
                    lead["has_added_to_cart"] = has_cart
                    lead["total_cart_value"] = cart_value
                    lead["conversion_stage"] = "cart_addition"
                    lead["last_interaction"] = datetime.datetime.now().isoformat()
                    break
            
            self._save_json_file(self.leads_file, leads)
            
        except Exception as e:
            logger.error(f"Error updating lead cart status for {phone_number}: {e}", exc_info=True)
    
    def _update_lead_conversion(self, phone_number: str, order_value: float) -> None:
        """Update lead's conversion status."""
        try:
            leads = self._load_json_file(self.leads_file)
            
            for lead in leads:
                if lead["phone_number"] == phone_number:
                    lead["has_placed_order"] = True
                    lead["status"] = "converted"
                    lead["conversion_stage"] = "order_completed"
                    lead["final_order_value"] = order_value
                    lead["converted_at"] = datetime.datetime.now().isoformat()
                    lead["last_interaction"] = datetime.datetime.now().isoformat()
                    break
            
            self._save_json_file(self.leads_file, leads)
            
        except Exception as e:
            logger.error(f"Error updating lead conversion for {phone_number}: {e}", exc_info=True)
    
    def _calculate_conversion_probability(self, phone_number: str, cart: List[Dict[str, Any]]) -> float:
        """
        Calculate conversion probability based on various factors.
        Now expects 'cart' as a List of Dictionaries.
        """
        try:
            probability = 0.5   # Base probability
            
            # Factor 1: Cart value (higher value = higher probability)
            # Calculate cart value from the list of dictionaries
            cart_value = sum(item.get("price", 0.0) * item.get("quantity", 0) for item in cart)
            if cart_value > 5000:
                probability += 0.2
            elif cart_value > 2000:
                probability += 0.1
            
            # Factor 2: Number of items (more items = higher commitment)
            # Get item count from the length of the list
            item_count = len(cart)
            if item_count > 3:
                probability += 0.15
            elif item_count > 1:
                probability += 0.1
            
            # Factor 3: Previous interaction history
            leads = self._load_json_file(self.leads_file)
            for lead in leads:
                if lead["phone_number"] == phone_number:
                    interaction_count = lead.get("interaction_count", 1)
                    if interaction_count > 5:
                        probability += 0.1
                    break
            
            return min(probability, 1.0)   # Cap at 100%
            
        except Exception as e:
            logger.error(f"Error calculating conversion probability: {e}", exc_info=True)
            return 0.5
    
    def _load_json_file(self, file_path: str) -> List[Dict]:
        """Load data from JSON file."""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding error loading {file_path}: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}", exc_info=True)
            return []
    
    def _save_json_file(self, file_path: str, data: List[Dict]) -> None:
        """Save data to JSON file."""
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving {file_path}: {e}", exc_info=True)
